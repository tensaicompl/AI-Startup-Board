"""Tests for memo synthesis and formatting (Task 7)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import BaseModel

from sboard.chair.meeting_state import MeetingState
from sboard.chair.state_machine import run_meeting
from sboard.memo.formatter import format_memo_markdown
from sboard.memo.synthesizer import MemoSynthesisError
from sboard.schemas import Memo, Petition
from sboard.seats.llm_client import AnthropicClient, LLMResponse, MockClient
from sboard.seats.persona_loader import Persona, load_all_personas


PERSONAS_DIR = Path(__file__).parent.parent.parent / "personas"
FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "petitions"

FORBIDDEN_TOKENS = [
    "Welch", "Buffett", "Jack", "Warren", "Marek", "Berkshire",
    "General Electric", "GE", "Peabody", "Omaha", "Hathaway",
]


class SynthesisCountingClient(AnthropicClient):
    """Wraps MockClient and counts calls by stage."""

    def __init__(self) -> None:
        self._delegate = MockClient()
        self.stage_counts: dict[str, int] = {}

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
        self.stage_counts[stage] = self.stage_counts.get(stage, 0) + 1
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


@pytest.fixture()
def personas() -> dict[str, Persona]:
    return load_all_personas(PERSONAS_DIR)


@pytest.fixture()
def petition_01() -> Petition:
    data = json.loads((FIXTURES_DIR / "01-iso-compliance.json").read_text())
    return Petition.model_validate(data)


def _run_full_meeting(
    petition: Petition, personas: dict[str, Persona], client: AnthropicClient
) -> MeetingState:
    meeting = MeetingState(petition=petition, personas=personas, seed=42)
    return run_meeting(meeting, client)


def test_memo_produced_on_01_iso_compliance(
    petition_01: Petition, personas: dict[str, Persona]
) -> None:
    """End-to-end run produces a memo that validates against the schema."""
    result = _run_full_meeting(petition_01, personas, MockClient())
    assert result.memo is not None

    memo_json = result.memo.model_dump_json()
    roundtrip = Memo.model_validate_json(memo_json)
    assert roundtrip.memo_id == result.memo.memo_id
    assert roundtrip.petition_id == petition_01.petition_id


def test_memo_structural_fields_from_code(
    petition_01: Petition, personas: dict[str, Persona]
) -> None:
    """verdict, confidence_weighted, confidence_spread, kill_criteria, next_action,
    signatures, metadata are all filled by code — not the synthesis model."""
    result = _run_full_meeting(petition_01, personas, MockClient())
    memo = result.memo
    assert memo is not None

    assert memo.verdict == result.final_verdict
    assert memo.confidence_weighted == round(result.confidence_weighted, 4)
    assert memo.confidence_spread == round(result.confidence_spread, 4)
    assert len(memo.kill_criteria) >= 1
    assert memo.next_action.owner == "Founder"
    assert len(memo.signatures) == 3
    assert memo.metadata.seed == 42
    assert memo.metadata.unanimous == result.unanimous


def test_kill_criteria_from_seat_openings(
    petition_01: Petition, personas: dict[str, Persona]
) -> None:
    """Kill criteria come from seats' sealed_opening outputs, not the synthesis model."""
    result = _run_full_meeting(petition_01, personas, MockClient())
    memo = result.memo
    assert memo is not None

    all_seat_criteria: set[str] = set()
    for sid, ss in result.seat_states.items():
        if ss.sealed_opening:
            all_seat_criteria.update(ss.sealed_opening.kill_criteria)
    if result.devils_advocate_output:
        all_seat_criteria.add(result.devils_advocate_output.strongest_kill_condition)

    for kc in memo.kill_criteria:
        assert kc.criterion in all_seat_criteria, (
            f"Kill criterion '{kc.criterion}' not found in any seat's output"
        )


def test_synthesis_call_count_is_one(
    petition_01: Petition, personas: dict[str, Persona]
) -> None:
    """Exactly one LLM call for memo synthesis per meeting."""
    client = SynthesisCountingClient()
    _run_full_meeting(petition_01, personas, client)
    assert client.stage_counts.get("memo_synthesis", 0) == 1


def test_combined_body_under_500_words(
    petition_01: Petition, personas: dict[str, Persona]
) -> None:
    """verdict_reasoning + dissent_summary + kill criteria text <= 500 words."""
    result = _run_full_meeting(petition_01, personas, MockClient())
    memo = result.memo
    assert memo is not None

    criteria_text = " ".join(kc.criterion for kc in memo.kill_criteria)
    combined = memo.verdict_reasoning + " " + memo.dissent_summary + " " + criteria_text
    word_count = len(combined.split())
    assert word_count <= 500, f"Combined body is {word_count} words, exceeds 500"


def test_markdown_format_no_forbidden_tokens(
    petition_01: Petition, personas: dict[str, Persona]
) -> None:
    """Markdown output must never surface source-figure names."""
    result = _run_full_meeting(petition_01, personas, MockClient())
    assert result.memo is not None

    md = format_memo_markdown(result.memo)
    assert len(md) > 100

    for token in FORBIDDEN_TOKENS:
        assert token not in md, (
            f"Forbidden token '{token}' found in Markdown output"
        )


def test_markdown_uses_role_names(
    petition_01: Petition, personas: dict[str, Persona]
) -> None:
    """Signatures in Markdown use role names."""
    result = _run_full_meeting(petition_01, personas, MockClient())
    assert result.memo is not None

    md = format_memo_markdown(result.memo)
    assert "Operator-CEO" in md
    assert "Devil's Advocate" in md
    assert "Outsider" in md


def test_memo_source_is_board(
    petition_01: Petition, personas: dict[str, Persona]
) -> None:
    result = _run_full_meeting(petition_01, personas, MockClient())
    assert result.memo is not None
    assert result.memo.source.value == "board"


def test_memo_signatures_match_votes(
    petition_01: Petition, personas: dict[str, Persona]
) -> None:
    result = _run_full_meeting(petition_01, personas, MockClient())
    memo = result.memo
    assert memo is not None

    vote_sids = {v.seat_id for v in result.votes}
    sig_sids = {s.seat_id for s in memo.signatures}
    assert vote_sids == sig_sids

    for sig in memo.signatures:
        vote = next(v for v in result.votes if v.seat_id == sig.seat_id)
        assert sig.verdict == vote.verdict
        assert sig.confidence_raw == vote.confidence_raw
        factor = personas[sig.seat_id].protocol.recalibration_factor
        expected_recal = round(vote.confidence_raw * factor, 4)
        assert sig.confidence_recalibrated == expected_recal


def test_all_three_petitions_produce_memo(
    personas: dict[str, Persona]
) -> None:
    for fixture in sorted(FIXTURES_DIR.glob("*.json")):
        data = json.loads(fixture.read_text())
        pet = Petition.model_validate(data)
        result = _run_full_meeting(pet, personas, MockClient())
        assert result.memo is not None, f"No memo produced for {fixture.name}"
        json.loads(result.memo.model_dump_json())


# --- 500-word retry path tests ---
# These patch _count_words to control the over-budget signal directly.
# The interaction between per-field char limits and combined word count
# is enforced structurally; these tests verify control flow only.


def test_synthesis_retries_once_on_over_budget_then_succeeds(
    petition_01: Petition, personas: dict[str, Persona], monkeypatch: pytest.MonkeyPatch
) -> None:
    """_count_words returns over-budget once, then normal. Synthesizer retries
    and succeeds. Synthesis LLM call count == 2."""
    call_count = 0
    original_count_words = __import__("sboard.memo.synthesizer", fromlist=["_count_words"])._count_words

    def _rigged_count_words(text: str) -> int:
        nonlocal call_count
        call_count += 1
        if call_count <= 3:
            return 999
        return original_count_words(text)

    monkeypatch.setattr("sboard.memo.synthesizer._count_words", _rigged_count_words)

    client = SynthesisCountingClient()
    result = _run_full_meeting(petition_01, personas, client)
    assert result.memo is not None
    assert client.stage_counts.get("memo_synthesis") == 2


def test_synthesis_hard_fails_on_two_over_budget(
    petition_01: Petition, personas: dict[str, Persona], monkeypatch: pytest.MonkeyPatch
) -> None:
    """_count_words always returns over-budget. Synthesizer retries once then
    raises MemoSynthesisError. Synthesis LLM call count == 2."""
    monkeypatch.setattr("sboard.memo.synthesizer._count_words", lambda text: 999)

    client = SynthesisCountingClient()
    with pytest.raises(MemoSynthesisError, match="500"):
        _run_full_meeting(petition_01, personas, client)
    assert client.stage_counts.get("memo_synthesis") == 2
