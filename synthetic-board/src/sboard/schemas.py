"""Pydantic v2 models for petition, seat output, and memo schemas."""

from __future__ import annotations

import json
import uuid
from datetime import date, datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

# --- Enums ---

class MeetingType(StrEnum):
    IDEA_SCREEN = "idea_screen"


class Position(StrEnum):
    PROCEED = "proceed"
    KILL = "kill"
    CONDITIONAL = "conditional"


class MajorityTrend(StrEnum):
    PROCEED = "proceed"
    KILL = "kill"
    CONDITIONAL = "conditional"
    SPLIT = "split"


class Agreement(StrEnum):
    AGREE = "agree"
    DISAGREE = "disagree"
    UNDECIDED = "undecided"


class MemoSource(StrEnum):
    BOARD = "board"
    BASELINE = "baseline"


# --- Petition ---

class PetitionConstraints(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_wall_clock_seconds: int = Field(default=120, ge=30, le=600)
    max_cost_usd: float = Field(default=5.0, ge=0.5, le=50.0)


class Petition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    petition_id: uuid.UUID
    submitted_at: datetime
    submitter: str | None = Field(default=None, max_length=100)
    meeting_type: MeetingType
    pitch: Annotated[str, Field(min_length=50, max_length=5000)]
    context: str | None = Field(default=None, max_length=10000)
    attachments: list[str] | None = None
    constraints: PetitionConstraints | None = None


# --- Seat Outputs ---

class SealedOpening(BaseModel):
    model_config = ConfigDict(extra="forbid")

    seat_id: str
    stage: Literal["sealed_opening"]
    position: Position
    one_paragraph_case: Annotated[str, Field(min_length=100, max_length=1500)]
    top_three_reasons: Annotated[
        list[Annotated[str, Field(min_length=10, max_length=250)]],
        Field(min_length=3, max_length=3),
    ]
    kill_criteria: Annotated[
        list[Annotated[str, Field(min_length=10, max_length=250)]],
        Field(min_length=1, max_length=5),
    ]
    confidence_raw: Annotated[float, Field(ge=0.0, le=1.0)]


class ReviewItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_label: Annotated[str, Field(pattern=r"^Seat [A-Z]$")]
    agreement: Agreement
    one_sentence_reason: Annotated[str, Field(min_length=10, max_length=300)]


class AnonymizedReview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    seat_id: str
    stage: Literal["anonymized_review"]
    reviews: Annotated[list[ReviewItem], Field(min_length=1)]


class Rebuttal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    seat_id: str
    stage: Literal["rebuttal"]
    position: Position
    position_changed: bool
    change_reason: str | None = Field(default=None, max_length=500)
    rebuttal_text: Annotated[str, Field(min_length=50, max_length=1500)]

    def model_post_init(self, __context: object) -> None:
        if self.position_changed and (
            self.change_reason is None or len(self.change_reason) < 10
        ):
            raise ValueError(
                "change_reason is required (min 10 chars) when position_changed is true"
            )


class DevilsAdvocateOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    seat_id: str
    stage: Literal["devils_advocate"]
    majority_trend: MajorityTrend
    steelman_against_majority: Annotated[str, Field(min_length=200, max_length=2000)]
    strongest_kill_condition: Annotated[str, Field(min_length=20, max_length=500)]


class Vote(BaseModel):
    model_config = ConfigDict(extra="forbid")

    seat_id: str
    stage: Literal["vote"]
    verdict: Position
    confidence_raw: Annotated[float, Field(ge=0.0, le=1.0)]
    one_sentence_rationale: Annotated[str, Field(min_length=20, max_length=300)]


class ForcedDissent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    seat_id: str
    stage: Literal["forced_dissent"]
    counter_verdict: Position
    counter_case: Annotated[str, Field(min_length=200, max_length=2000)]
    would_change_mind_if: Annotated[str, Field(min_length=20, max_length=500)]


# --- v2 stage outputs (Task v2.3) ---


class IdeaAnalysisOutput(BaseModel):
    """do_idea_analysis: what the business actually does, stripped of pitch language."""

    model_config = ConfigDict(extra="forbid")

    seat_id: str
    stage: Literal["idea_analysis"]
    plain_description: Annotated[str, Field(min_length=50, max_length=800)]
    core_bet: Annotated[str, Field(min_length=20, max_length=400)]
    load_bearing_assumption: Annotated[str, Field(min_length=20, max_length=400)]


class VisionaryOutput(BaseModel):
    """do_visionary_pass: the upside if it works. Always produced — `worth_building`
    False is itself signal (the 'nothing will save it' answer)."""

    model_config = ConfigDict(extra="forbid")

    seat_id: str
    stage: Literal["visionary_pass"]
    upside_if_it_works: Annotated[str, Field(min_length=50, max_length=1000)]
    worth_building: bool
    what_must_be_true: Annotated[str, Field(min_length=20, max_length=500)]


class GtmOutput(BaseModel):
    """do_gtm_stage: go-to-market analysis. Produced only when verdict trend != kill."""

    model_config = ConfigDict(extra="forbid")

    seat_id: str
    stage: Literal["gtm_stage"]
    one_promise: Annotated[str, Field(min_length=20, max_length=400)]
    primary_channel: Annotated[str, Field(min_length=10, max_length=300)]
    first_motion: Annotated[str, Field(min_length=20, max_length=400)]


# Union type for all seat / stage outputs
SeatOutput = (
    SealedOpening
    | AnonymizedReview
    | Rebuttal
    | DevilsAdvocateOutput
    | Vote
    | ForcedDissent
    | IdeaAnalysisOutput
    | VisionaryOutput
    | GtmOutput
)


# --- Memo ---

class KillCriterion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    criterion: Annotated[str, Field(min_length=20, max_length=300)]
    owner_to_monitor: Annotated[str, Field(min_length=1, max_length=100)]


class NextAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Annotated[str, Field(min_length=10, max_length=200)]
    owner: Annotated[str, Field(min_length=1, max_length=100)]
    deadline: date


class Signature(BaseModel):
    model_config = ConfigDict(extra="forbid")

    seat_id: str
    verdict: Position
    confidence_raw: Annotated[float, Field(ge=0.0, le=1.0)]
    confidence_recalibrated: Annotated[float, Field(ge=0.0, le=1.5)]


class MemoModelIds(BaseModel):
    model_config = ConfigDict(extra="forbid")

    seats: str
    synthesis: str


class MemoMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    persona_hashes: dict[str, str]
    model_ids: MemoModelIds
    seed: int
    wall_clock_seconds: Annotated[float, Field(ge=0.0)]
    llm_cost_usd: Annotated[float, Field(ge=0.0)]
    unanimous: bool
    forced_dissent_triggered: bool
    references_memo_id: uuid.UUID | None = None
    reasoning_overlap_score: Annotated[float, Field(ge=0.0, le=1.0)] | None = None


class Memo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    memo_id: uuid.UUID
    petition_id: uuid.UUID
    meeting_type: MeetingType
    protocol_version: Annotated[str, Field(pattern=r"^\d+\.\d+\.\d+$")]
    created_at: datetime
    source: MemoSource

    verdict: Position
    confidence_weighted: Annotated[float, Field(ge=0.0, le=3.0)]
    confidence_spread: Annotated[float, Field(ge=0.0)]

    verdict_reasoning: Annotated[str, Field(min_length=50, max_length=1500)]
    dissent_summary: Annotated[str, Field(min_length=50, max_length=1200)]
    dissent_source: str

    kill_criteria: Annotated[list[KillCriterion], Field(min_length=1, max_length=5)]

    next_action: NextAction

    signatures: Annotated[list[Signature], Field(min_length=1)]

    metadata: MemoMetadata


# --- Memo v2 (five-stage body, seven seats) ---


class MemoV2(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["2.0"] = "2.0"

    memo_id: uuid.UUID
    petition_id: uuid.UUID
    meeting_type: MeetingType
    protocol_version: Annotated[str, Field(pattern=r"^\d+\.\d+\.\d+$")]
    created_at: datetime
    source: MemoSource

    verdict: Position
    # Architectural ceiling = n_voting (5) x max recal (1.0) x max voting_weight (1.5)
    # = 7.5. (recal = confidence_raw[<=1] x recalibration_factor[<=1]; weight in
    # [0.5, 1.5] per the persona schema.) With the current personas all at weight
    # 1.0 the practical max is 5.0, but the schema permits 1.5 — see Decision 011.
    confidence_weighted: Annotated[float, Field(ge=0.0, le=7.5)]
    confidence_spread: Annotated[float, Field(ge=0.0)]

    # Five-stage body. Word budgets are enforced by the synthesizer (Task v2.5);
    # the character caps here are generous guards sized to the word targets.
    idea_analysis: Annotated[str, Field(min_length=50, max_length=1600)]      # ≤200 words
    verdict_reasoning: Annotated[str, Field(min_length=50, max_length=2400)]  # ≤300 words
    vision: Annotated[str, Field(min_length=50, max_length=2000)]             # ≤250 words
    dissent_summary: Annotated[str, Field(min_length=50, max_length=2000)]    # ≤250 words
    # Present only when verdict != kill (enforced below).
    gtm_analysis: Annotated[str, Field(min_length=50, max_length=1600)] | None = None  # ≤200 words

    dissent_source: str
    kill_criteria: Annotated[list[KillCriterion], Field(min_length=1, max_length=5)]
    next_action: NextAction
    signatures: Annotated[list[Signature], Field(min_length=1)]
    metadata: MemoMetadata

    def model_post_init(self, __context: object) -> None:
        # gtm_analysis is present iff the verdict is not kill.
        if self.verdict == Position.KILL and self.gtm_analysis is not None:
            raise ValueError("gtm_analysis must be omitted when verdict is kill")
        if self.verdict != Position.KILL and self.gtm_analysis is None:
            raise ValueError("gtm_analysis is required when verdict is not kill")


# Version-discriminated memo. Manual dispatch (not a pydantic discriminated union)
# because persisted v1 memos predate the schema_version field. See Decision 009.
AnyMemo = Memo | MemoV2


def parse_memo(data: dict[str, object]) -> AnyMemo:
    """Route raw memo data to the right model by version.

    v2 is tagged by `schema_version == "2.0"` (or the presence of the v2-only
    `idea_analysis` body field); anything else is v1.
    """
    if data.get("schema_version") == "2.0" or "idea_analysis" in data:
        return MemoV2.model_validate(data)
    return Memo.model_validate(data)


def parse_memo_json(raw: str) -> AnyMemo:
    """Parse a memo JSON string to whichever schema version it encodes."""
    return parse_memo(json.loads(raw))
