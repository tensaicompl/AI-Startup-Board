"""Memo synthesis: deterministic template fill + one constrained LLM call for prose."""

from __future__ import annotations

import json
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
    MemoV2,
    NextAction,
    Position,
    Signature,
)
from sboard.seats.llm_client import AnthropicClient

MEMO_BODY_WORD_LIMIT = 500

# v2 five-section body budgets (Task v2.5). Per-section budgets are enforced at the
# schema boundary (right after the structured output validates); the combined cap is
# enforced separately. The per-section budgets sum to exactly the combined cap, so a
# kill memo (no GTM) tops out at 1000 words and a full memo at 1200.
MEMO_V2_SECTION_WORD_LIMITS: dict[str, int] = {
    "idea_analysis": 200,
    "verdict_reasoning": 300,
    "vision": 250,
    "dissent_summary": 250,
    "gtm_analysis": 200,
}
MEMO_V2_COMBINED_WORD_LIMIT = 1200


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
        action = "Validate the top kill criterion within 30 days and report back at the next review."
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
    """Build the prompt for the synthesis LLM call.

    The output memo is rated blind against a single-LLM baseline, so the prose
    must NOT reveal that it came from a multi-seat board. The input material may
    mention the mechanism; the output must not (see Decision 007).
    """
    parts: list[str] = [
        f"Provisional verdict: {state.final_verdict.value if state.final_verdict else 'unknown'}.",
        "",
        "Source material (internal — never quote it or describe its structure):",
        "",
        "Positions:",
    ]

    for sid in state.responding_seat_ids:
        ss = state.seat_states[sid]
        if ss.rebuttal:
            parts.append(f"  - {ss.rebuttal.position.value}: {ss.rebuttal.rebuttal_text}")

    if state.devils_advocate_output:
        parts.extend([
            "",
            "Strongest counter-case to the majority position:",
            f"  {state.devils_advocate_output.steelman_against_majority}",
        ])

    if state.forced_dissent_output:
        parts.extend([
            "",
            "Additional counter-case:",
            f"  {state.forced_dissent_output.counter_case}",
        ])

    parts.extend([
        "",
        "Write a standalone advisory memo in a single, decisive advisor voice.",
        "Output exactly two JSON fields:",
        '  "verdict_reasoning": the case for the verdict (≤200 words, concrete).',
        '  "dissent_summary": the strongest case against the verdict, charitably stated (≤150 words).',
        "",
        "Hard constraints on the prose (these are non-negotiable):",
        "- Do NOT mention a board, panel, committee, seats, members, a vote, a tally,",
        "  unanimity, dissent mechanics, a devil's advocate, an operator, or an outsider.",
        "- Do NOT cite confidence numbers, scores, or any internal deliberation process.",
        "- Write as one advisor addressing the founder directly. No hedging. No padding.",
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
            system_prompt=(
                "You are an advisory memo writer. Output valid JSON with exactly two "
                "fields. Write in a neutral, standalone advisor voice that never "
                "references any board, panel, seats, voting, or internal process."
            ),
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


# --- v2 synthesis (Task v2.4; word-budget + forbidden-token enforcement is v2.5) ---


class SynthesisV2Output(BaseModel):
    """The five prose body sections the v2 synthesis LLM writes in one call.
    gtm_analysis is optional: the synthesizer drops it on a kill verdict."""

    idea_analysis: Annotated[str, Field(min_length=50, max_length=1600)]
    verdict_reasoning: Annotated[str, Field(min_length=50, max_length=2400)]
    vision: Annotated[str, Field(min_length=50, max_length=2000)]
    dissent_summary: Annotated[str, Field(min_length=50, max_length=2000)]
    gtm_analysis: Annotated[str, Field(min_length=50, max_length=1600)] | None = None


def _build_synthesis_prompt_v2(state: MeetingState) -> str:
    """Assemble the v2 synthesis prompt from the stage outputs. Output prose must
    be pipeline-neutral (no board/seats/figures) — see Decision 007."""
    parts: list[str] = [
        f"Provisional verdict: {state.final_verdict.value if state.final_verdict else 'unknown'}.",
        "",
        "Source material (internal — never quote it or describe its structure):",
        "",
        "What the business actually is:",
    ]
    for ia in state.idea_analysis_outputs.values():
        parts.append(f"  - {ia.plain_description} (core bet: {ia.core_bet})")
    parts.append("\nPositions:")
    for sid in state.responding_seat_ids:
        ss = state.seat_states[sid]
        if ss.rebuttal:
            parts.append(f"  - {ss.rebuttal.position.value}: {ss.rebuttal.rebuttal_text}")
    if state.devils_advocate_output:
        parts.append("\nStrongest counter-case to the majority:")
        parts.append(f"  {state.devils_advocate_output.steelman_against_majority}")
    if state.visionary_outputs:
        parts.append("\nThe upside case:")
        for vo in state.visionary_outputs.values():
            parts.append(f"  - {vo.upside_if_it_works}")
    if state.gtm_outputs:
        parts.append("\nGo-to-market notes:")
        for go in state.gtm_outputs.values():
            parts.append(f"  - promise: {go.one_promise}; channel: {go.primary_channel}")

    parts.extend([
        "",
        "Write a standalone advisory memo as a single, decisive advisor voice.",
        "Output exactly these JSON fields:",
        '  "idea_analysis": what the business actually is and its core bet (≤200 words).',
        '  "verdict_reasoning": the case for the verdict (≤300 words).',
        '  "vision": the upside if it works (≤250 words).',
        '  "dissent_summary": the strongest case against the verdict (≤250 words).',
        '  "gtm_analysis": the go-to-market assessment (≤200 words) — OMIT if the '
        "verdict is kill.",
        "",
        "Hard constraints: do NOT mention a board, panel, seats, voting, a tally, a "
        "devil's advocate, or any internal process or scores. Write as one advisor "
        "to the founder.",
    ])
    return "\n".join(parts)


def _assemble_gtm(state: MeetingState) -> str | None:
    """Fallback GTM prose assembled from the GTM stage outputs (if the LLM omitted it)."""
    if not state.gtm_outputs:
        return None
    parts = [
        f"Promise: {g.one_promise} Channel: {g.primary_channel} First move: {g.first_motion}"
        for g in state.gtm_outputs.values()
    ]
    return " ".join(parts)[:1600]


def _v2_section_word_counts(out: SynthesisV2Output) -> dict[str, int]:
    """Word count of each present body section. gtm_analysis is skipped when None
    (a kill verdict drops it). Counting routes through `_count_words` so the
    retry-path tests can rig the budget signal (Decision 005)."""
    counts: dict[str, int] = {}
    for field in MEMO_V2_SECTION_WORD_LIMITS:
        value = getattr(out, field)
        if value is not None:
            counts[field] = _count_words(value)
    return counts


def _v2_within_budget(out: SynthesisV2Output) -> bool:
    """True iff every present section is within its per-section budget (the
    schema-boundary check) AND the combined body is within the 1,200-word cap (the
    separate check)."""
    counts = _v2_section_word_counts(out)
    sections_ok = all(wc <= MEMO_V2_SECTION_WORD_LIMITS[field] for field, wc in counts.items())
    combined_ok = sum(counts.values()) <= MEMO_V2_COMBINED_WORD_LIMIT
    return sections_ok and combined_ok


def synthesize_memo_v2(state: MeetingState, client: AnthropicClient) -> MemoV2:
    """Build a v2 memo: five body sections from one LLM call, structural fields by
    code. gtm_analysis is present iff the verdict is not kill.

    Word budgets mirror v1's discipline: validate the structured output, check the
    per-section + combined budgets, and on an over-budget result retry exactly once
    before raising MemoSynthesisError. The happy path is a single LLM call."""
    synthesis_model = client.get_default_synthesis_model()
    prompt = _build_synthesis_prompt_v2(state)

    out: SynthesisV2Output | None = None
    for attempt in range(2):
        response = client.call(
            system_prompt=(
                "You are an advisory memo writer. Output valid JSON with the five body "
                "fields. Write in a neutral, standalone advisor voice that never "
                "references any board, panel, seats, voting, or internal process."
            ),
            user_message=prompt,
            output_schema=SynthesisV2Output,
            seat_id="synthesis",
            stage="memo_synthesis_v2",
            model=synthesis_model,
            max_tokens=3000,
        )
        state.total_llm_cost_usd += response.cost_usd
        candidate = SynthesisV2Output.model_validate(json.loads(response.content))
        if _v2_within_budget(candidate):
            out = candidate
            break
        if attempt == 0:
            continue

    if out is None:
        raise MemoSynthesisError(
            f"v2 synthesis exceeded its word budgets after 2 attempts "
            f"(per-section {MEMO_V2_SECTION_WORD_LIMITS}, "
            f"combined cap {MEMO_V2_COMBINED_WORD_LIMIT} words)"
        )

    verdict = state.final_verdict or Position.CONDITIONAL
    # Conditional routing already gated GTM on verdict != kill; enforce the memo
    # invariant here too: gtm present iff not kill.
    gtm = None if verdict == Position.KILL else (out.gtm_analysis or _assemble_gtm(state))

    wall_clock = time.monotonic() - state.wall_clock_start

    return MemoV2(
        memo_id=uuid.uuid4(),
        petition_id=state.petition.petition_id,
        meeting_type=MeetingType.IDEA_SCREEN,
        protocol_version=state.protocol_version,
        created_at=datetime.now(UTC),
        source=MemoSource.BOARD,
        verdict=verdict,
        confidence_weighted=round(state.confidence_weighted, 4),
        confidence_spread=round(state.confidence_spread, 4),
        idea_analysis=out.idea_analysis,
        verdict_reasoning=out.verdict_reasoning,
        vision=out.vision,
        dissent_summary=out.dissent_summary,
        gtm_analysis=gtm,
        dissent_source=_determine_dissent_source(state),
        kill_criteria=_deduplicate_kill_criteria(state),
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
