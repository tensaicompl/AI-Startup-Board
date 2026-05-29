"""Meeting state: the structured context that flows through the state machine."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from sboard.schemas import (
    AnonymizedReview,
    DevilsAdvocateOutput,
    ForcedDissent,
    Memo,
    Petition,
    Position,
    Rebuttal,
    SealedOpening,
    Vote,
)
from sboard.seats.persona_loader import Persona


class ProtocolState(str, Enum):
    CONVENE = "CONVENE"
    SEALED_OPENING = "SEALED_OPENING"
    ANONYMIZED_REVEAL = "ANONYMIZED_REVEAL"
    IDENTIFIED_REBUTTAL = "IDENTIFIED_REBUTTAL"
    DEVILS_ADVOCATE = "DEVILS_ADVOCATE"
    CONFIDENCE_VOTE = "CONFIDENCE_VOTE"
    FORCED_DISSENT_CHECK = "FORCED_DISSENT_CHECK"
    MEMO_SYNTHESIS = "MEMO_SYNTHESIS"
    COMPLETE = "COMPLETE"
    ABORTED = "ABORTED"


@dataclass
class SeatState:
    seat_id: str
    status: str = "pending"
    sealed_opening: SealedOpening | None = None
    anonymized_review: AnonymizedReview | None = None
    rebuttal: Rebuttal | None = None
    vote: Vote | None = None
    forced_dissent: ForcedDissent | None = None


@dataclass
class TranscriptEntry:
    state: str
    seat_id: str | None
    event: str
    data: dict[str, Any]
    timestamp: float = field(default_factory=time.time)


@dataclass
class MeetingState:
    petition: Petition
    personas: dict[str, Persona]
    seed: int
    protocol_version: str = "1.0.0"

    current_state: ProtocolState = ProtocolState.CONVENE
    seat_states: dict[str, SeatState] = field(default_factory=dict)
    transcript: list[TranscriptEntry] = field(default_factory=list)

    anonymization_map: dict[str, str] = field(default_factory=dict)
    anonymized_openings: list[dict[str, Any]] = field(default_factory=list)

    devils_advocate_output: DevilsAdvocateOutput | None = None
    majority_trend: Position | None = None

    votes: list[Vote] = field(default_factory=list)
    final_verdict: Position | None = None
    confidence_weighted: float = 0.0
    confidence_spread: float = 0.0
    unanimous: bool = False
    forced_dissent_triggered: bool = False
    forced_dissent_output: ForcedDissent | None = None

    memo: Memo | None = None

    total_llm_cost_usd: float = 0.0
    wall_clock_start: float = field(default_factory=time.monotonic)
    state_timings: dict[str, float] = field(default_factory=dict)

    error: str | None = None

    def log(
        self,
        event: str,
        data: dict[str, Any] | None = None,
        seat_id: str | None = None,
    ) -> None:
        self.transcript.append(
            TranscriptEntry(
                state=self.current_state.value,
                seat_id=seat_id,
                event=event,
                data=data or {},
            )
        )

    @property
    def responding_seat_ids(self) -> list[str]:
        return [
            sid for sid, ss in self.seat_states.items()
            if ss.status == "responded"
        ]

    @property
    def quorum_met(self) -> bool:
        return len(self.responding_seat_ids) >= 2
