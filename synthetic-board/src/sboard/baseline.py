"""Single-LLM baseline pipeline for the A/B gate.

One Anthropic call against `tests/ab/baseline_prompt.txt` produces a memo in the
same schema as the board. This is the control arm the board must beat; per
docs/07-evaluation.md §7 it is written to be a fair competitor, never weakened.
"""

from __future__ import annotations

import json
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from sboard.schemas import (
    KillCriterion,
    MeetingType,
    Memo,
    MemoMetadata,
    MemoModelIds,
    MemoSource,
    NextAction,
    Petition,
    Position,
    Signature,
)
from sboard.seats.llm_client import AnthropicClient

DEFAULT_BASELINE_PROMPT_PATH = Path("tests/ab/baseline_prompt.txt")
BASELINE_SEAT_ID = "baseline"


class BaselineMemoOutput(BaseModel):
    """The fields the baseline LLM produces — the rater-relevant memo content.

    Mirrors the board's decision surface so both pipelines render identically
    after anonymization; structural metadata is filled by code, not the model.
    """

    model_config = ConfigDict(extra="forbid")

    verdict: Position
    verdict_reasoning: Annotated[str, Field(min_length=50, max_length=1500)]
    dissent_summary: Annotated[str, Field(min_length=50, max_length=1200)]
    kill_criteria: Annotated[list[KillCriterion], Field(min_length=1, max_length=5)]
    next_action: NextAction
    confidence: Annotated[float, Field(ge=0.0, le=1.0)]


class BaselineError(Exception):
    """The baseline pipeline could not produce a valid memo."""


def load_baseline_prompt(
    petition: Petition, prompt_path: Path = DEFAULT_BASELINE_PROMPT_PATH
) -> str:
    """Fill the {{PITCH}} / {{CONTEXT}} placeholders in the baseline prompt."""
    template = prompt_path.read_text(encoding="utf-8")
    context = petition.context or "(none provided)"
    return template.replace("{{PITCH}}", petition.pitch).replace("{{CONTEXT}}", context)


def run_baseline(
    petition: Petition,
    client: AnthropicClient,
    *,
    seed: int = 0,
    prompt_path: Path = DEFAULT_BASELINE_PROMPT_PATH,
) -> Memo:
    """Run the single-LLM baseline and assemble a `source=baseline` memo."""
    start = time.monotonic()
    model_id = client.get_default_seat_model()
    system_prompt = load_baseline_prompt(petition, prompt_path)

    response = client.call(
        system_prompt=system_prompt,
        user_message="Produce the board memo now as a single structured object.",
        output_schema=BaselineMemoOutput,
        seat_id=BASELINE_SEAT_ID,
        stage="baseline",
        model=model_id,
        max_tokens=2000,
    )

    try:
        out = BaselineMemoOutput.model_validate(json.loads(response.content))
    except (json.JSONDecodeError, ValueError) as exc:
        raise BaselineError(f"Baseline returned malformed memo: {exc!s}"[:500]) from exc

    wall_clock = time.monotonic() - start

    return Memo(
        memo_id=uuid.uuid4(),
        petition_id=petition.petition_id,
        meeting_type=MeetingType.IDEA_SCREEN,
        protocol_version="1.0.0",
        created_at=datetime.now(UTC),
        source=MemoSource.BASELINE,
        verdict=out.verdict,
        confidence_weighted=round(out.confidence, 4),
        confidence_spread=0.0,  # a single voice has no spread
        verdict_reasoning=out.verdict_reasoning,
        dissent_summary=out.dissent_summary,
        dissent_source=BASELINE_SEAT_ID,
        kill_criteria=out.kill_criteria,
        next_action=out.next_action,
        signatures=[
            Signature(
                seat_id=BASELINE_SEAT_ID,
                verdict=out.verdict,
                confidence_raw=out.confidence,
                confidence_recalibrated=round(out.confidence, 4),
            )
        ],
        metadata=MemoMetadata(
            persona_hashes={},  # baseline has no personas
            model_ids=MemoModelIds(seats=model_id, synthesis=model_id),
            seed=seed,
            wall_clock_seconds=round(wall_clock, 2),
            llm_cost_usd=round(response.cost_usd, 4),
            unanimous=False,
            forced_dissent_triggered=False,
        ),
    )
