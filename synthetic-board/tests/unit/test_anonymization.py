"""Exhaustive anonymization leak tests (Task 6, Part B)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel

from sboard.chair.anonymizer import build_anonymization_map, redact_text, reverse_map
from sboard.chair.meeting_state import MeetingState
from sboard.chair.state_machine import run_meeting
from sboard.schemas import Petition
from sboard.seats.llm_client import AnthropicClient, LLMResponse, MockClient
from sboard.seats.persona_loader import Persona, load_all_personas


PERSONAS_DIR = Path(__file__).parent.parent.parent / "personas"
FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "petitions"

PRE_REVEAL_STAGES = ("sealed_opening", "anonymized_review")


# --- Spy client: wraps MockClient, records every call ---


@dataclass
class RecordedCall:
    system_prompt: str
    user_message: str
    seat_id: str
    stage: str
    model: str


class SpyClient(AnthropicClient):
    """Wraps MockClient, records all call args for inspection."""

    def __init__(self) -> None:
        self._delegate = MockClient()
        self.calls: list[RecordedCall] = []

    def call(
        self,
        *,
        system_prompt: str,
        user_message: str,
        output_schema: type[BaseModel],
        seat_id: str,
        stage: str,
        model: str | None = None,
        max_tokens: int = 2000,
    ) -> LLMResponse:
        self.calls.append(RecordedCall(
            system_prompt=system_prompt,
            user_message=user_message,
            seat_id=seat_id,
            stage=stage,
            model=model or self.get_default_seat_model(),
        ))
        return self._delegate.call(
            system_prompt=system_prompt,
            user_message=user_message,
            output_schema=output_schema,
            seat_id=seat_id,
            stage=stage,
            model=model,
            max_tokens=max_tokens,
        )

    def get_default_seat_model(self) -> str:
        return self._delegate.get_default_seat_model()

    def get_default_synthesis_model(self) -> str:
        return self._delegate.get_default_synthesis_model()


# --- Fixtures ---


@pytest.fixture()
def personas() -> dict[str, Persona]:
    return load_all_personas(PERSONAS_DIR)


@pytest.fixture()
def fixture_petitions() -> list[Petition]:
    petitions = []
    for f in sorted(FIXTURES_DIR.glob("*.json")):
        data = json.loads(f.read_text())
        petitions.append(Petition.model_validate(data))
    return petitions


def _all_peer_seat_ids(seat_id: str, personas: dict[str, Persona]) -> set[str]:
    return {sid for sid in personas if sid != seat_id}


def _all_peer_redaction_aliases(seat_id: str, personas: dict[str, Persona]) -> set[str]:
    aliases: set[str] = set()
    for sid, p in personas.items():
        if sid == seat_id:
            continue
        aliases.update(p.voice.redaction_aliases)
    return aliases


# --- Test 1: Parametrized leak test ---

_PETITION_FILES = sorted(FIXTURES_DIR.glob("*.json"))
_SEAT_IDS = ["operator-ceo", "devils-advocate", "outsider"]


@pytest.mark.parametrize("petition_file", _PETITION_FILES, ids=[p.stem for p in _PETITION_FILES])
@pytest.mark.parametrize("stage", PRE_REVEAL_STAGES)
@pytest.mark.parametrize("seat_id", _SEAT_IDS)
def test_no_peer_identity_leak_in_pre_reveal_prompts(
    petition_file: Path,
    stage: str,
    seat_id: str,
    personas: dict[str, Persona],
) -> None:
    """For each fixture petition x pre-reveal stage x seat, the user_message
    sent to the LLM must contain zero peer seat_ids and zero peer redaction_aliases."""
    data = json.loads(petition_file.read_text())
    petition = Petition.model_validate(data)
    spy = SpyClient()
    meeting = MeetingState(petition=petition, personas=personas, seed=42)
    run_meeting(meeting, spy)

    peer_ids = _all_peer_seat_ids(seat_id, personas)
    peer_aliases = _all_peer_redaction_aliases(seat_id, personas)

    relevant_calls = [c for c in spy.calls if c.seat_id == seat_id and c.stage == stage]
    for call in relevant_calls:
        for peer_id in peer_ids:
            assert peer_id not in call.user_message, (
                f"Peer seat_id '{peer_id}' leaked into {stage} user_message for {seat_id}"
            )
        for alias in peer_aliases:
            pattern = r"\b" + re.escape(alias) + r"\b"
            assert not re.search(pattern, call.user_message, re.IGNORECASE), (
                f"Peer redaction alias '{alias}' leaked into {stage} user_message for {seat_id}"
            )


# --- Test 2: Label consistency ---

def test_label_consistency_across_seats(
    personas: dict[str, Persona],
    fixture_petitions: list[Petition],
) -> None:
    """The anonymization_map is stable: every Seat A/B/C reference in every
    seat's review output must reverse-map to the same underlying seat_id."""
    for petition in fixture_petitions:
        spy = SpyClient()
        meeting = MeetingState(petition=petition, personas=personas, seed=42)
        result = run_meeting(meeting, spy)

        rev = reverse_map(result.anonymization_map)
        assert len(rev) == len(result.anonymization_map)

        for sid, ss in result.seat_states.items():
            if ss.anonymized_review is None:
                continue
            for review in ss.anonymized_review.reviews:
                label = review.target_label
                assert label in rev, f"Label {label} has no reverse mapping"
                resolved = rev[label]
                assert resolved != sid, (
                    f"Seat {sid} reviewed itself under label {label}"
                )
                assert resolved in result.anonymization_map, (
                    f"Label {label} resolved to unknown seat {resolved}"
                )


# --- Test 3: Reveal completeness ---

def test_reveal_completeness(
    personas: dict[str, Persona],
    fixture_petitions: list[Petition],
) -> None:
    """At IDENTIFIED_REBUTTAL, every A/B/C label has a real seat_id binding.
    No orphans, no extras."""
    for petition in fixture_petitions:
        spy = SpyClient()
        meeting = MeetingState(petition=petition, personas=personas, seed=42)
        result = run_meeting(meeting, spy)

        anon_map = result.anonymization_map
        labels_used = set(anon_map.values())
        seat_ids_mapped = set(anon_map.keys())

        assert labels_used == {"Seat A", "Seat B", "Seat C"}
        assert seat_ids_mapped == set(personas.keys())

        rev = reverse_map(anon_map)
        for label in labels_used:
            assert label in rev
            assert rev[label] in personas

        assert len(anon_map) == len(rev), "Map and reverse map have different sizes"


# --- Test 4: Seed reproducibility ---

def test_seed_reproducibility(
    personas: dict[str, Persona],
    fixture_petitions: list[Petition],
) -> None:
    """Same seed -> same map. Different seeds -> different maps (sampled N=10)."""
    petition = fixture_petitions[0]

    m1 = MeetingState(petition=petition, personas=personas, seed=777)
    r1 = run_meeting(m1, MockClient())
    m2 = MeetingState(petition=petition, personas=personas, seed=777)
    r2 = run_meeting(m2, MockClient())
    assert r1.anonymization_map == r2.anonymization_map

    maps_seen: list[dict[str, str]] = []
    for seed in range(10):
        m = MeetingState(petition=petition, personas=personas, seed=seed)
        r = run_meeting(m, MockClient())
        maps_seen.append(r.anonymization_map)

    unique_maps = [json.dumps(m, sort_keys=True) for m in maps_seen]
    assert len(set(unique_maps)) > 1, (
        "10 different seeds all produced the same anonymization map — shuffle is not seeded"
    )


# --- Test 5: Redaction edge cases ---


@pytest.mark.parametrize(
    "text,terms,expected",
    [
        (
            "Berkshire's approach to value investing is sound.",
            ["Berkshire"],
            "[REDACTED]'s approach to value investing is sound.",
        ),
        (
            "The BERKSHIRE model and berkshire methodology are proven.",
            ["Berkshire"],
            "The [REDACTED] model and [REDACTED] methodology are proven.",
        ),
        (
            "GE Capital and General Electric both restructured.",
            ["GE", "General Electric"],
            "[REDACTED] Capital and [REDACTED] both restructured.",
        ),
        (
            "As the Oracle of Omaha once said about Coca-Cola...",
            ["Oracle of", "Omaha", "Coca-Cola"],
            "As the [REDACTED] [REDACTED] once said about [REDACTED]...",
        ),
        (
            "No redaction terms present in this text.",
            ["Berkshire", "GE"],
            "No redaction terms present in this text.",
        ),
        (
            "Six Sigma improved Crotonville training.",
            ["Six Sigma", "Crotonville"],
            "[REDACTED] improved [REDACTED] training.",
        ),
        (
            "",
            ["Berkshire"],
            "",
        ),
        (
            "the target segment creates urgency in the budget",
            ["GE"],
            "the target segment creates urgency in the budget",
        ),
        (
            "I worked at GE for twenty years in Crotonville",
            ["GE", "Crotonville"],
            "I worked at [REDACTED] for twenty years in [REDACTED]",
        ),
    ],
    ids=[
        "substring-with-possessive",
        "case-insensitive-multiple",
        "standalone-short-term",
        "multiple-adjacent-terms",
        "no-match",
        "multi-word-terms",
        "empty-string",
        "short-alias-no-false-positive",
        "short-alias-standalone-match",
    ],
)
def test_redaction_edge_cases(text: str, terms: list[str], expected: str) -> None:
    result = redact_text(text, terms)
    assert result == expected
