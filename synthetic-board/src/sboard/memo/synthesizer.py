"""Memo synthesis: deterministic template fill + one constrained LLM call for prose."""

from __future__ import annotations

import time
import uuid
from datetime import UTC, date, datetime
from typing import Annotated

from pydantic import BaseModel, Field

from sboard.chair.meeting_state import MeetingState
from sboard.chair.voting import recalibrate
from sboard.schemas import (
    KillCriterion,
    MeetingType,
    Memo,
    MemoMetadata,
    MemoModelIds,
    MemoSource,
    NextAction,
    Position,
    Signature,
)
from sboard.seats.llm_client import AnthropicClient

MEMO_BODY_WORD_LIMIT = 500


class SynthesisOutput(BaseModel):
    """The only two fields the LLM writes. Everything else is code."""

    verdict_reasoning: Annotated[str, Field(min_length=50, max_length=1500)]
    dissent_summary: Annotated[str, Field(min_length=50, max_length=1200)]


def _count_words(text: str) -> int:
    return len(text.split())


def _deduplicate_kill_criteria(state: MeetingState) -> list[KillCriterion]:
    """Collect kill criteria from all seats' sealed openings, deduplicate by content."""
    seen: set[str] = set()
    criteria: list[KillCriterion] = []
    for sid in state.responding_seat_ids:
        ss = state.seat_states[sid]
        if ss.sealed_opening is None:
            continue
        for kc_text in ss.sealed_opening.kill_criteria:
            normalized = kc_text.strip().lower()
            if normalized not in seen:
                seen.add(normalized)
                criteria.append(KillCriterion(
                    criterion=kc_text,
                    owner_to_monitor="Founder",
                ))
    if state.devils_advocate_output:
        da_kc = state.devils_advocate_output.strongest_kill_condition
        normalized = da_kc.strip().lower()
        if normalized not in seen:
            seen.add(normalized)
            criteria.append(KillCriterion(
                criterion=da_kc,
                owner_to_monitor="Founder",
            ))
    return criteria[:5]


def _determine_dissent_source(state: MeetingState) -> str:
    """Determine who the dissent came from."""
    if state.forced_dissent_output:
        return state.forced_dissent_output.seat_id
    if not state.votes:
        return "unknown"
    majority = state.final_verdict
    for vote in state.votes:
        if vote.verdict != majority:
            return vote.seat_id
    return state.votes[0].seat_id


def _build_next_action(state: MeetingState) -> NextAction:
    """Build next action from the meeting result."""
    verdict = state.final_verdict or Position.CONDITIONAL
    if verdict == Position.KILL:
        action = "Document learnings and archive this concept before exploring alternatives."
    elif verdict == Position.CONDITIONAL:
        action = "Validate the top kill criterion within 30 days and report back to the board."
    else:
        action = "Proceed to detailed planning with a 30-day milestone review checkpoint."

    return NextAction(
        action=action,
        owner="Founder",
        deadline=date(2026, 7, 1),
    )


def _build_signatures(state: MeetingState) -> list[Signature]:
    """Build signatures from vote results with recalibrated confidence."""
    signatures: list[Signature] = []
    for vote in state.votes:
        factor = state.personas[vote.seat_id].protocol.recalibration_factor
        signatures.append(Signature(
            seat_id=vote.seat_id,
            verdict=vote.verdict,
            confidence_raw=vote.confidence_raw,
            confidence_recalibrated=round(
                recalibrate(vote.confidence_raw, factor), 4
            ),
        ))
    return signatures


def _compute_reasoning_overlap(state: MeetingState) -> float | None:
    """Compute Jaccard similarity over key terms from each seat's top_three_reasons."""
    all_term_sets: list[set[str]] = []
    for sid in state.responding_seat_ids:
        ss = state.seat_states[sid]
        if ss.sealed_opening is None:
            continue
        terms: set[str] = set()
        for reason in ss.sealed_opening.top_three_reasons:
            for word in reason.lower().split():
                if len(word) > 3:
                    terms.add(word)
        all_term_sets.append(terms)

    if len(all_term_sets) < 2:
        return None

    total_jaccard = 0.0
    pair_count = 0
    for i in range(len(all_term_sets)):
        for j in range(i + 1, len(all_term_sets)):
            intersection = all_term_sets[i] & all_term_sets[j]
            union = all_term_sets[i] | all_term_sets[j]
            if union:
                total_jaccard += len(intersection) / len(union)
            pair_count += 1

    return round(total_jaccard / pair_count, 4) if pair_count > 0 else None


def _build_synthesis_prompt(state: MeetingState) -> str:
    """Build the prompt for the synthesis LLM call."""
    parts: list[str] = [
        f"The board has reached a verdict of: {state.final_verdict.value if state.final_verdict else 'unknown'}.",
        f"Confidence-weighted score: {state.confidence_weighted:.2f}",
        f"Confidence spread: {state.confidence_spread:.2f}",
        "",
        "Rebuttals from seats:",
    ]

    for sid in state.responding_seat_ids:
        ss = state.seat_states[sid]
        role = state.personas[sid].role
        if ss.rebuttal:
            parts.append(f"  {role}: {ss.rebuttal.position.value} — {ss.rebuttal.rebuttal_text}")

    if state.devils_advocate_output:
        parts.extend([
            "",
            f"Devil's Advocate steelman against {state.devils_advocate_output.majority_trend.value}:",
            f"  {state.devils_advocate_output.steelman_against_majority}",
        ])

    if state.forced_dissent_output:
        parts.extend([
            "",
            "Forced dissent (unanimous vote triggered this):",
            f"  Counter-verdict: {state.forced_dissent_output.counter_verdict.value}",
            f"  {state.forced_dissent_output.counter_case}",
        ])

    parts.extend([
        "",
        "Write exactly two fields as JSON:",
        '  "verdict_reasoning": the case for the winning verdict (≤200 words, concrete)',
        '  "dissent_summary": the minority\'s strongest case, charitably stated (≤150 words)',
        "",
        "No other fields. No hedging. No padding.",
    ])

    return "\n".join(parts)


class MemoSynthesisError(Exception):
    pass


def synthesize_memo(
    state: MeetingState,
    client: AnthropicClient,
) -> Memo:
    """Build the memo: code fills structural fields, one LLM call writes prose."""
    synthesis_model = client.get_default_synthesis_model()
    prompt = _build_synthesis_prompt(state)

    synthesis_output: SynthesisOutput | None = None
    for attempt in range(2):
        response = client.call(
            system_prompt="You are a board memo writer. Output valid JSON with exactly two fields.",
            user_message=prompt,
            output_schema=SynthesisOutput,
            seat_id="synthesis",
            stage="memo_synthesis",
            model=synthesis_model,
            max_tokens=1500,
        )
        state.total_llm_cost_usd += response.cost_usd

        import json as _json
        data = _json.loads(response.content)
        candidate = SynthesisOutput.model_validate(data)

        kill_criteria = _deduplicate_kill_criteria(state)
        criteria_text = " ".join(kc.criterion for kc in kill_criteria)
        combined_words = (
            _count_words(candidate.verdict_reasoning)
            + _count_words(candidate.dissent_summary)
            + _count_words(criteria_text)
        )

        if combined_words <= MEMO_BODY_WORD_LIMIT:
            synthesis_output = candidate
            break

        if attempt == 0:
            continue

    if synthesis_output is None:
        raise MemoSynthesisError(
            f"Synthesis exceeded {MEMO_BODY_WORD_LIMIT}-word body limit after 2 attempts"
        )

    kill_criteria = _deduplicate_kill_criteria(state)
    wall_clock = time.monotonic() - state.wall_clock_start

    return Memo(
        memo_id=uuid.uuid4(),
        petition_id=state.petition.petition_id,
        meeting_type=MeetingType.IDEA_SCREEN,
        protocol_version=state.protocol_version,
        created_at=datetime.now(UTC),
        source=MemoSource.BOARD,
        verdict=state.final_verdict or Position.CONDITIONAL,
        confidence_weighted=round(state.confidence_weighted, 4),
        confidence_spread=round(state.confidence_spread, 4),
        verdict_reasoning=synthesis_output.verdict_reasoning,
        dissent_summary=synthesis_output.dissent_summary,
        dissent_source=_determine_dissent_source(state),
        kill_criteria=kill_criteria,
        next_action=_build_next_action(state),
        signatures=_build_signatures(state),
        metadata=MemoMetadata(
            persona_hashes={sid: p.file_hash for sid, p in state.personas.items()},
            model_ids=MemoModelIds(
                seats=client.get_default_seat_model(),
                synthesis=synthesis_model,
            ),
            seed=state.seed,
            wall_clock_seconds=round(wall_clock, 2),
            llm_cost_usd=round(state.total_llm_cost_usd, 4),
            unanimous=state.unanimous,
            forced_dissent_triggered=state.forced_dissent_triggered,
            reasoning_overlap_score=_compute_reasoning_overlap(state),
        ),
    )
