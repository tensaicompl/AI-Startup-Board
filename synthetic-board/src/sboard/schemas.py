"""Pydantic v2 models for petition, seat output, and memo schemas."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from enum import Enum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


# --- Enums ---

class MeetingType(str, Enum):
    IDEA_SCREEN = "idea_screen"


class Position(str, Enum):
    PROCEED = "proceed"
    KILL = "kill"
    CONDITIONAL = "conditional"


class MajorityTrend(str, Enum):
    PROCEED = "proceed"
    KILL = "kill"
    CONDITIONAL = "conditional"
    SPLIT = "split"


class Agreement(str, Enum):
    AGREE = "agree"
    DISAGREE = "disagree"
    UNDECIDED = "undecided"


class MemoSource(str, Enum):
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


# Union type for all seat outputs
SeatOutput = (
    SealedOpening
    | AnonymizedReview
    | Rebuttal
    | DevilsAdvocateOutput
    | Vote
    | ForcedDissent
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
