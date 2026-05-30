"""Task v2.3 — the three new v2 state functions, mock-tested in isolation.

Not yet wired into the graph (that is v2.4); each function is exercised directly
on a convened MeetingState for all three smoke petitions. Confirms participant
selection, structured output capture, the visionary pass running even on a kill
trend, and the GTM precondition refusing a kill verdict.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from sboard.chair.meeting_state import MeetingState, ProtocolState
from sboard.chair.states import (
    GtmPreconditionError,
    do_convene,
    do_gtm_stage,
    do_idea_analysis,
    do_visionary_pass,
)
from sboard.schemas import GtmOutput, IdeaAnalysisOutput, Petition, Position, VisionaryOutput
from sboard.seats.llm_client import MockClient
from sboard.seats.persona_loader import Persona, load_all_personas

ROOT = Path(__file__).parent.parent.parent
PERSONAS_DIR = ROOT / "personas"
FIXTURES = ROOT / "tests" / "fixtures" / "petitions"
V2_SEATS = (
    "operator-ceo",
    "devils-advocate",
    "outsider",
    "visionary",
    "technical",
    "growth-advisor",
    "marketing",
)
VOTING_PLUS_ADVISOR = {
    "operator-ceo",
    "devils-advocate",
    "outsider",
    "visionary",
    "technical",
    "growth-advisor",
}


def _petitions() -> list[Petition]:
    return [
        Petition.model_validate(json.loads(p.read_text()))
        for p in sorted(FIXTURES.glob("*.json"))
    ]


PETITIONS = _petitions()
PIDS = [p.pitch[:20] for p in PETITIONS]


@pytest.fixture()
def personas() -> dict[str, Persona]:
    return load_all_personas(PERSONAS_DIR, seat_ids=V2_SEATS)


def _convened(petition: Petition, personas: dict[str, Persona]) -> MeetingState:
    state = MeetingState(petition=petition, personas=personas, seed=42)
    do_convene(state)
    return state


@pytest.mark.parametrize("petition", PETITIONS, ids=PIDS)
def test_idea_analysis_runs_for_voting_plus_advisor(
    petition: Petition, personas: dict[str, Persona]
) -> None:
    state = _convened(petition, personas)
    do_idea_analysis(state, MockClient())
    assert set(state.idea_analysis_outputs) == VOTING_PLUS_ADVISOR
    assert "marketing" not in state.idea_analysis_outputs  # gtm-only seat excluded
    for sid, out in state.idea_analysis_outputs.items():
        assert isinstance(out, IdeaAnalysisOutput)
        assert out.seat_id == sid
    assert any(e.event == "idea_analysis_result" for e in state.transcript)


@pytest.mark.parametrize("petition", PETITIONS, ids=PIDS)
def test_visionary_pass_runs_for_visionary_plus_advisor(
    petition: Petition, personas: dict[str, Persona]
) -> None:
    state = _convened(petition, personas)
    do_visionary_pass(state, MockClient())
    assert set(state.visionary_outputs) == {"visionary", "growth-advisor"}
    for out in state.visionary_outputs.values():
        assert isinstance(out, VisionaryOutput)


def test_visionary_pass_runs_even_when_trend_is_kill(
    personas: dict[str, Persona],
) -> None:
    state = _convened(PETITIONS[0], personas)
    state.majority_trend = Position.KILL  # the DA trend says kill
    do_visionary_pass(state, MockClient())
    # It still ran — "nothing would save it" is captured, not skipped.
    assert set(state.visionary_outputs) == {"visionary", "growth-advisor"}


@pytest.mark.parametrize("petition", PETITIONS, ids=PIDS)
def test_gtm_stage_runs_when_verdict_not_kill(
    petition: Petition, personas: dict[str, Persona]
) -> None:
    state = _convened(petition, personas)
    state.final_verdict = Position.CONDITIONAL
    do_gtm_stage(state, MockClient())
    assert set(state.gtm_outputs) == {"marketing", "growth-advisor"}
    for out in state.gtm_outputs.values():
        assert isinstance(out, GtmOutput)


def test_gtm_stage_refuses_when_verdict_is_kill(personas: dict[str, Persona]) -> None:
    state = _convened(PETITIONS[0], personas)
    state.final_verdict = Position.KILL
    with pytest.raises(GtmPreconditionError):
        do_gtm_stage(state, MockClient())
    assert state.gtm_outputs == {}


def test_gtm_stage_refuses_when_no_verdict_yet(personas: dict[str, Persona]) -> None:
    state = _convened(PETITIONS[0], personas)
    assert state.final_verdict is None
    with pytest.raises(GtmPreconditionError):
        do_gtm_stage(state, MockClient())


def test_v2_state_functions_make_no_routing_decision(
    personas: dict[str, Persona],
) -> None:
    """Each function labels its own state but does not advance to the next."""
    state = _convened(PETITIONS[0], personas)
    do_idea_analysis(state, MockClient())
    assert state.current_state == ProtocolState.IDEA_ANALYSIS
    do_visionary_pass(state, MockClient())
    assert state.current_state == ProtocolState.VISIONARY_PASS
