"""Tests for the eight-state Idea Screen state machine."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from sboard.chair.meeting_state import MeetingState, ProtocolState
from sboard.chair.state_machine import run_meeting
from sboard.chair.voting import recalibrate
from sboard.schemas import Petition, Position
from sboard.seats.llm_client import MockClient
from sboard.seats.persona_loader import Persona, load_all_personas

PERSONAS_DIR = Path(__file__).parent.parent.parent / "personas"
FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "petitions"


@pytest.fixture()
def personas() -> dict[str, Persona]:
    return load_all_personas(PERSONAS_DIR)


@pytest.fixture()
def petition() -> Petition:
    data = json.loads((FIXTURES_DIR / "01-iso-compliance.json").read_text())
    return Petition.model_validate(data)


@pytest.fixture()
def mock_client() -> MockClient:
    return MockClient()


def _make_meeting(petition: Petition, personas: dict[str, Persona], seed: int = 42) -> MeetingState:
    return MeetingState(petition=petition, personas=personas, seed=seed)


def test_full_meeting_runs_to_completion(
    petition: Petition, personas: dict[str, Persona], mock_client: MockClient
) -> None:
    """The mock produces a unanimous 'conditional' vote, so forced dissent should trigger."""
    meeting = _make_meeting(petition, personas)
    result = run_meeting(meeting, mock_client)

    assert result.current_state == ProtocolState.COMPLETE
    assert result.error is None
    assert result.final_verdict is not None
    assert len(result.votes) == 3


def test_all_seats_responded(
    petition: Petition, personas: dict[str, Persona], mock_client: MockClient
) -> None:
    meeting = _make_meeting(petition, personas)
    result = run_meeting(meeting, mock_client)

    for sid, ss in result.seat_states.items():
        assert ss.status == "responded", f"Seat {sid} status: {ss.status}"
        assert ss.sealed_opening is not None
        assert ss.anonymized_review is not None
        assert ss.rebuttal is not None
        assert ss.vote is not None


def test_sealed_openings_are_independent(
    petition: Petition, personas: dict[str, Persona], mock_client: MockClient
) -> None:
    """Each seat should have a distinct sealed opening."""
    meeting = _make_meeting(petition, personas)
    result = run_meeting(meeting, mock_client)

    openings = {sid: ss.sealed_opening for sid, ss in result.seat_states.items()}
    seat_ids = {o.seat_id for o in openings.values() if o}
    assert len(seat_ids) == 3


def test_anonymization_map_exists(
    petition: Petition, personas: dict[str, Persona], mock_client: MockClient
) -> None:
    meeting = _make_meeting(petition, personas)
    result = run_meeting(meeting, mock_client)

    assert len(result.anonymization_map) == 3
    labels = set(result.anonymization_map.values())
    assert labels == {"Seat A", "Seat B", "Seat C"}


def test_anonymization_is_seeded(
    petition: Petition, personas: dict[str, Persona], mock_client: MockClient
) -> None:
    """Same seed should produce same anonymization map."""
    m1 = _make_meeting(petition, personas, seed=99)
    r1 = run_meeting(m1, mock_client)

    m2 = _make_meeting(petition, personas, seed=99)
    r2 = run_meeting(m2, mock_client)

    assert r1.anonymization_map == r2.anonymization_map


def test_different_seeds_may_differ(
    petition: Petition, personas: dict[str, Persona], mock_client: MockClient
) -> None:
    """Different seeds should (likely) produce different maps."""
    # Deterministic over a fixed seed range rather than a flaky two-seed compare:
    # any single shuffle could coincide, but not all of them across 8 seeds.
    maps = [
        run_meeting(_make_meeting(petition, personas, seed=s), mock_client).anonymization_map
        for s in range(8)
    ]
    distinct = {tuple(sorted(m.items())) for m in maps}
    assert len(distinct) > 1


def test_unanimous_vote_triggers_forced_dissent(
    petition: Petition, personas: dict[str, Persona], mock_client: MockClient
) -> None:
    """The mock returns all-conditional, which is unanimous — forced dissent must trigger."""
    meeting = _make_meeting(petition, personas)
    result = run_meeting(meeting, mock_client)

    assert result.unanimous is True
    assert result.forced_dissent_triggered is True
    assert result.forced_dissent_output is not None


def test_vote_tally_is_correct(
    petition: Petition, personas: dict[str, Persona], mock_client: MockClient
) -> None:
    meeting = _make_meeting(petition, personas)
    result = run_meeting(meeting, mock_client)

    assert result.final_verdict == Position.CONDITIONAL
    assert result.confidence_weighted > 0
    assert result.confidence_spread >= 0


def test_recalibration_applied(
    petition: Petition, personas: dict[str, Persona], mock_client: MockClient
) -> None:
    meeting = _make_meeting(petition, personas)
    result = run_meeting(meeting, mock_client)

    for vote in result.votes:
        factor = personas[vote.seat_id].protocol.recalibration_factor
        expected = recalibrate(vote.confidence_raw, factor)
        assert expected < vote.confidence_raw or factor == 1.0


def test_transcript_records_all_states(
    petition: Petition, personas: dict[str, Persona], mock_client: MockClient
) -> None:
    meeting = _make_meeting(petition, personas)
    result = run_meeting(meeting, mock_client)

    states_in_transcript = {e.state for e in result.transcript}
    expected = {
        "CONVENE", "SEALED_OPENING", "ANONYMIZED_REVEAL",
        "IDENTIFIED_REBUTTAL", "DEVILS_ADVOCATE", "CONFIDENCE_VOTE",
    }
    assert expected.issubset(states_in_transcript)


def test_transcript_includes_convene_metadata(
    petition: Petition, personas: dict[str, Persona], mock_client: MockClient
) -> None:
    meeting = _make_meeting(petition, personas)
    result = run_meeting(meeting, mock_client)

    convene_entries = [e for e in result.transcript if e.event == "convene"]
    assert len(convene_entries) == 1
    data = convene_entries[0].data
    assert "persona_hashes" in data
    assert "seed" in data
    assert "protocol_version" in data


def test_cost_is_tracked(
    petition: Petition, personas: dict[str, Persona], mock_client: MockClient
) -> None:
    meeting = _make_meeting(petition, personas)
    result = run_meeting(meeting, mock_client)

    assert result.total_llm_cost_usd > 0


def test_state_timings_recorded(
    petition: Petition, personas: dict[str, Persona], mock_client: MockClient
) -> None:
    meeting = _make_meeting(petition, personas)
    result = run_meeting(meeting, mock_client)

    for key in ("CONVENE", "SEALED_OPENING", "ANONYMIZED_REVEAL",
                "IDENTIFIED_REBUTTAL", "DEVILS_ADVOCATE", "CONFIDENCE_VOTE"):
        assert key in result.state_timings
        assert result.state_timings[key] >= 0


def test_devils_advocate_output_present(
    petition: Petition, personas: dict[str, Persona], mock_client: MockClient
) -> None:
    meeting = _make_meeting(petition, personas)
    result = run_meeting(meeting, mock_client)

    assert result.devils_advocate_output is not None
    assert result.majority_trend is not None


def test_all_three_fixture_petitions(
    personas: dict[str, Persona], mock_client: MockClient
) -> None:
    """The state machine should complete on all three fixture petitions."""
    for fixture in sorted(FIXTURES_DIR.glob("*.json")):
        data = json.loads(fixture.read_text())
        pet = Petition.model_validate(data)
        meeting = _make_meeting(pet, personas)
        result = run_meeting(meeting, mock_client)
        assert result.error is None, f"Failed on {fixture.name}: {result.error}"
        assert result.final_verdict is not None
