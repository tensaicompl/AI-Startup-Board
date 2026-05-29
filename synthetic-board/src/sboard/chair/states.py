"""One function per protocol state. Each takes MeetingState + dependencies, mutates state."""

from __future__ import annotations

import json
import time
from typing import Any

from sboard.chair.anonymizer import anonymize_opening, build_anonymization_map, reverse_map
from sboard.chair.diversity import check_diversity
from sboard.chair.meeting_state import MeetingState, ProtocolState, SeatState
from sboard.chair.voting import (
    is_unanimous,
    recalibrate,
    select_forced_dissent_seat,
    tally_votes,
)
from sboard.schemas import (
    AnonymizedReview,
    DevilsAdvocateOutput,
    ForcedDissent,
    Position,
    Rebuttal,
    SealedOpening,
    Vote,
)
from sboard.seats.llm_client import AnthropicClient
from sboard.seats.seat import SeatStatus, run_seat


def do_convene(state: MeetingState) -> None:
    """S1: Validate petition, load personas, check diversity, init seats."""
    state.current_state = ProtocolState.CONVENE
    start = time.monotonic()

    passes, count = check_diversity(state.personas)
    if not passes:
        state.error = f"Diversity check failed: only {count} distinct axes (need {4})"
        state.current_state = ProtocolState.ABORTED
        state.log("diversity_check_failed", {"distinct_axes": count})
        return

    for sid, persona in state.personas.items():
        state.seat_states[sid] = SeatState(seat_id=sid, status="pending")

    state.log("convene", {
        "petition_id": str(state.petition.petition_id),
        "protocol_version": state.protocol_version,
        "seed": state.seed,
        "persona_hashes": {sid: p.file_hash for sid, p in state.personas.items()},
        "seat_ids": list(state.personas.keys()),
    })

    state.current_state = ProtocolState.SEALED_OPENING
    state.state_timings["CONVENE"] = time.monotonic() - start


def do_sealed_opening(state: MeetingState, client: AnthropicClient) -> None:
    """S2: Each seat drafts blind, in parallel (sequential in MVP)."""
    start = time.monotonic()

    pitch_text = state.petition.pitch
    context_text = state.petition.context or ""
    prompt = f"Petition:\n{pitch_text}\n\nContext:\n{context_text}"

    for sid, persona in state.personas.items():
        result = run_seat(client, persona, "sealed_opening", prompt, SealedOpening)
        ss = state.seat_states[sid]

        if result.status == SeatStatus.RESPONDED and result.output is not None:
            ss.status = "responded"
            ss.sealed_opening = result.output  # type: ignore[assignment]
            if result.response:
                state.total_llm_cost_usd += result.response.cost_usd
        else:
            ss.status = result.status

        state.log(
            "sealed_opening_result",
            {"status": ss.status, "position": getattr(result.output, "position", None)},
            seat_id=sid,
        )

    if not state.quorum_met:
        state.error = "Quorum not met after sealed opening"
        state.current_state = ProtocolState.ABORTED
        state.log("quorum_failed")
        return

    state.current_state = ProtocolState.ANONYMIZED_REVEAL
    state.state_timings["SEALED_OPENING"] = time.monotonic() - start


def do_anonymized_reveal(state: MeetingState, client: AnthropicClient) -> None:
    """S3: Anonymize openings, each seat critiques peers."""
    start = time.monotonic()

    responding = state.responding_seat_ids
    state.anonymization_map = build_anonymization_map(responding, state.seed)
    state.log("anonymization_map_created", {"map": state.anonymization_map})

    anon_openings = []
    for sid in responding:
        opening = state.seat_states[sid].sealed_opening
        assert opening is not None
        label = state.anonymization_map[sid]
        anon = anonymize_opening(opening, label, state.personas)
        anon_openings.append(anon)
    state.anonymized_openings = anon_openings

    for sid in responding:
        persona = state.personas[sid]
        my_label = state.anonymization_map[sid]
        peer_openings = [o for o in anon_openings if o["label"] != my_label]

        prompt_parts = [f"Your opening was labeled {my_label}.\n\nPeer openings to critique:"]
        for po in peer_openings:
            prompt_parts.append(
                f"\n--- {po['label']} ---\n"
                f"Position: {po['position']}\n"
                f"Case: {po['one_paragraph_case']}\n"
                f"Reasons: {json.dumps(po['top_three_reasons'])}"
            )
        prompt = "\n".join(prompt_parts)

        result = run_seat(client, persona, "anonymized_review", prompt, AnonymizedReview)
        ss = state.seat_states[sid]
        if result.status == SeatStatus.RESPONDED and result.output is not None:
            ss.anonymized_review = result.output  # type: ignore[assignment]
            if result.response:
                state.total_llm_cost_usd += result.response.cost_usd
        state.log(
            "anonymized_review_result",
            {"status": result.status},
            seat_id=sid,
        )

    state.current_state = ProtocolState.IDENTIFIED_REBUTTAL
    state.state_timings["ANONYMIZED_REVEAL"] = time.monotonic() - start


def do_identified_rebuttal(state: MeetingState, client: AnthropicClient) -> None:
    """S4: Identities revealed, seats may revise positions."""
    start = time.monotonic()

    rev_map = reverse_map(state.anonymization_map)
    state.log("identity_reveal", {"reverse_map": rev_map})

    responding = state.responding_seat_ids
    for sid in responding:
        persona = state.personas[sid]
        peer_info: list[str] = []
        for peer_sid in responding:
            if peer_sid == sid:
                continue
            peer_opening = state.seat_states[peer_sid].sealed_opening
            assert peer_opening is not None
            label = state.anonymization_map[peer_sid]
            peer_info.append(
                f"{label} was {peer_sid} (role: {state.personas[peer_sid].role}).\n"
                f"Position: {peer_opening.position.value}\n"
                f"Case: {peer_opening.one_paragraph_case}"
            )

        my_reviews = state.seat_states[sid].anonymized_review
        reviews_text = ""
        if my_reviews:
            reviews_text = "\n".join(
                f"Your review of {r.target_label}: {r.agreement.value} — {r.one_sentence_reason}"
                for r in my_reviews.reviews
            )

        prompt = (
            f"Identities have been revealed.\n\n"
            f"Peer positions:\n" + "\n\n".join(peer_info) + "\n\n"
            f"Your earlier reviews:\n{reviews_text}\n\n"
            f"You may revise your position. If you change, you must explain why."
        )

        result = run_seat(client, persona, "rebuttal", prompt, Rebuttal)
        ss = state.seat_states[sid]
        if result.status == SeatStatus.RESPONDED and result.output is not None:
            ss.rebuttal = result.output  # type: ignore[assignment]
            if result.output.position_changed:  # type: ignore[union-attr]
                state.log(
                    "position_changed",
                    {
                        "from": getattr(ss.sealed_opening, "position", None),
                        "to": result.output.position.value,  # type: ignore[union-attr]
                        "reason": result.output.change_reason,  # type: ignore[union-attr]
                    },
                    seat_id=sid,
                )
            if result.response:
                state.total_llm_cost_usd += result.response.cost_usd

    state.current_state = ProtocolState.DEVILS_ADVOCATE
    state.state_timings["IDENTIFIED_REBUTTAL"] = time.monotonic() - start


def _determine_majority_trend(state: MeetingState) -> Position:
    """Determine the current majority trend from rebuttals (or openings if no rebuttal)."""
    position_counts: dict[Position, int] = {
        Position.PROCEED: 0, Position.KILL: 0, Position.CONDITIONAL: 0,
    }
    for sid in state.responding_seat_ids:
        ss = state.seat_states[sid]
        pos = (ss.rebuttal.position if ss.rebuttal else
               ss.sealed_opening.position if ss.sealed_opening else
               Position.CONDITIONAL)
        position_counts[pos] += 1
    return max(position_counts, key=lambda p: position_counts[p])


def do_devils_advocate(state: MeetingState, client: AnthropicClient) -> None:
    """S5: DA produces steelman against majority."""
    start = time.monotonic()

    da_sid: str | None = None
    for sid, persona in state.personas.items():
        if persona.is_devils_advocate:
            da_sid = sid
            break
    assert da_sid is not None, "No devil's advocate seat found"

    majority = _determine_majority_trend(state)
    state.majority_trend = majority

    rebuttals_text: list[str] = []
    for sid in state.responding_seat_ids:
        ss = state.seat_states[sid]
        if ss.rebuttal:
            rebuttals_text.append(
                f"{sid}: {ss.rebuttal.position.value} — {ss.rebuttal.rebuttal_text}"
            )

    prompt = (
        f"The current majority trend is: {majority.value}\n\n"
        f"Rebuttals:\n" + "\n\n".join(rebuttals_text) + "\n\n"
        f"Produce a steelmanned case AGAINST the majority position."
    )

    da_persona = state.personas[da_sid]
    result = run_seat(client, da_persona, "devils_advocate", prompt, DevilsAdvocateOutput)
    if result.status == SeatStatus.RESPONDED and result.output is not None:
        state.devils_advocate_output = result.output  # type: ignore[assignment]
        if result.response:
            state.total_llm_cost_usd += result.response.cost_usd
    state.log(
        "devils_advocate_result",
        {"status": result.status, "majority_trend": majority.value},
        seat_id=da_sid,
    )

    state.current_state = ProtocolState.CONFIDENCE_VOTE
    state.state_timings["DEVILS_ADVOCATE"] = time.monotonic() - start


def do_confidence_vote(state: MeetingState, client: AnthropicClient) -> None:
    """S6: Each voting seat casts verdict + confidence."""
    start = time.monotonic()

    rebuttals_text: list[str] = []
    for sid in state.responding_seat_ids:
        ss = state.seat_states[sid]
        if ss.rebuttal:
            rebuttals_text.append(
                f"{sid}: {ss.rebuttal.position.value} — {ss.rebuttal.rebuttal_text}"
            )

    da_text = ""
    if state.devils_advocate_output:
        da_text = (
            f"\nDevil's Advocate case against {state.devils_advocate_output.majority_trend.value}:\n"
            f"{state.devils_advocate_output.steelman_against_majority}\n"
            f"Strongest kill condition: {state.devils_advocate_output.strongest_kill_condition}"
        )

    positions_summary: list[str] = []
    for sid in state.responding_seat_ids:
        ss = state.seat_states[sid]
        pos = ss.rebuttal.position.value if ss.rebuttal else "unknown"
        positions_summary.append(f"  {sid}: {pos}")

    prompt = (
        f"All rebuttals:\n" + "\n\n".join(rebuttals_text) +
        f"\n{da_text}\n\n"
        f"Current position summary:\n" + "\n".join(positions_summary) + "\n\n"
        f"Cast your final vote: verdict and confidence."
    )

    votes: list[Vote] = []
    for sid in state.responding_seat_ids:
        persona = state.personas[sid]
        if not persona.voting:
            continue
        result = run_seat(client, persona, "vote", prompt, Vote)
        ss = state.seat_states[sid]
        if result.status == SeatStatus.RESPONDED and result.output is not None:
            ss.vote = result.output  # type: ignore[assignment]
            votes.append(result.output)  # type: ignore[arg-type]
            if result.response:
                state.total_llm_cost_usd += result.response.cost_usd
        state.log("vote_result", {"status": result.status}, seat_id=sid)

    state.votes = votes

    recal_factors = {sid: p.protocol.recalibration_factor for sid, p in state.personas.items()}
    voting_weights = {sid: p.voting_weight for sid, p in state.personas.items()}
    verdict, weighted, spread = tally_votes(votes, recal_factors, voting_weights)
    state.final_verdict = verdict
    state.confidence_weighted = weighted
    state.confidence_spread = spread
    state.unanimous = is_unanimous(votes)

    state.log("tally", {
        "verdict": verdict.value,
        "confidence_weighted": weighted,
        "confidence_spread": spread,
        "unanimous": state.unanimous,
    })

    if state.unanimous:
        state.forced_dissent_triggered = True
        state.current_state = ProtocolState.FORCED_DISSENT_CHECK
    else:
        state.current_state = ProtocolState.MEMO_SYNTHESIS

    state.state_timings["CONFIDENCE_VOTE"] = time.monotonic() - start


def do_forced_dissent_check(state: MeetingState, client: AnthropicClient) -> None:
    """S7: On unanimity, lowest-confidence seat produces counter-case."""
    start = time.monotonic()

    recal_factors = {sid: p.protocol.recalibration_factor for sid, p in state.personas.items()}
    dissent_seat = select_forced_dissent_seat(state.votes, recal_factors)

    prompt = (
        f"The vote was unanimous: {state.final_verdict.value if state.final_verdict else 'unknown'}.\n"
        f"You are required to produce the strongest possible counter-case.\n"
        f"Argue for a different verdict than the one you voted for."
    )

    persona = state.personas[dissent_seat]
    result = run_seat(client, persona, "forced_dissent", prompt, ForcedDissent)
    if result.status == SeatStatus.RESPONDED and result.output is not None:
        state.forced_dissent_output = result.output  # type: ignore[assignment]
        state.seat_states[dissent_seat].forced_dissent = result.output  # type: ignore[assignment]
        if result.response:
            state.total_llm_cost_usd += result.response.cost_usd
    state.log(
        "forced_dissent_result",
        {"status": result.status, "dissent_seat": dissent_seat},
        seat_id=dissent_seat,
    )

    state.current_state = ProtocolState.MEMO_SYNTHESIS
    state.state_timings["FORCED_DISSENT_CHECK"] = time.monotonic() - start
