"""Tests for the seat runner with mock client."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from sboard.schemas import (
    AnonymizedReview,
    DevilsAdvocateOutput,
    ForcedDissent,
    Rebuttal,
    SealedOpening,
    Vote,
)
from sboard.seats.llm_client import LLMResponse, MockClient
from sboard.seats.persona_loader import load_persona
from sboard.seats.seat import SeatStatus, run_seat

PERSONAS_DIR = Path(__file__).parent.parent.parent / "personas"


@pytest.fixture()
def mock_client() -> MockClient:
    return MockClient()


@pytest.fixture()
def operator_persona() -> object:
    return load_persona(PERSONAS_DIR / "operator-ceo.md")


@pytest.fixture()
def da_persona() -> object:
    return load_persona(PERSONAS_DIR / "devils-advocate.md")


@pytest.fixture()
def outsider_persona() -> object:
    return load_persona(PERSONAS_DIR / "outsider.md")


def test_sealed_opening_operator(mock_client: MockClient, operator_persona: object) -> None:
    result = run_seat(
        mock_client, operator_persona, "sealed_opening", "Evaluate this pitch.", SealedOpening  # type: ignore[arg-type]
    )
    assert result.status == SeatStatus.RESPONDED
    assert result.output is not None
    assert isinstance(result.output, SealedOpening)
    assert result.output.seat_id == "operator-ceo"
    assert result.output.stage == "sealed_opening"
    assert len(result.output.top_three_reasons) == 3


def test_sealed_opening_da(mock_client: MockClient, da_persona: object) -> None:
    result = run_seat(
        mock_client, da_persona, "sealed_opening", "Evaluate this pitch.", SealedOpening  # type: ignore[arg-type]
    )
    assert result.status == SeatStatus.RESPONDED
    assert isinstance(result.output, SealedOpening)
    assert result.output.seat_id == "devils-advocate"


def test_sealed_opening_outsider(mock_client: MockClient, outsider_persona: object) -> None:
    result = run_seat(
        mock_client, outsider_persona, "sealed_opening", "Evaluate this pitch.", SealedOpening  # type: ignore[arg-type]
    )
    assert result.status == SeatStatus.RESPONDED
    assert isinstance(result.output, SealedOpening)
    assert result.output.seat_id == "outsider"


def test_anonymized_review(mock_client: MockClient, operator_persona: object) -> None:
    result = run_seat(
        mock_client, operator_persona, "anonymized_review",  # type: ignore[arg-type]
        "Review these peer positions.", AnonymizedReview,
    )
    assert result.status == SeatStatus.RESPONDED
    assert isinstance(result.output, AnonymizedReview)
    assert len(result.output.reviews) == 2


def test_rebuttal(mock_client: MockClient, operator_persona: object) -> None:
    result = run_seat(
        mock_client, operator_persona, "rebuttal", "Rebut.", Rebuttal  # type: ignore[arg-type]
    )
    assert result.status == SeatStatus.RESPONDED
    assert isinstance(result.output, Rebuttal)


def test_devils_advocate_output(mock_client: MockClient, da_persona: object) -> None:
    result = run_seat(
        mock_client, da_persona, "devils_advocate", "Steelman against.", DevilsAdvocateOutput  # type: ignore[arg-type]
    )
    assert result.status == SeatStatus.RESPONDED
    assert isinstance(result.output, DevilsAdvocateOutput)


def test_vote(mock_client: MockClient, operator_persona: object) -> None:
    result = run_seat(
        mock_client, operator_persona, "vote", "Cast your vote.", Vote  # type: ignore[arg-type]
    )
    assert result.status == SeatStatus.RESPONDED
    assert isinstance(result.output, Vote)
    assert 0.0 <= result.output.confidence_raw <= 1.0


def test_forced_dissent(mock_client: MockClient, operator_persona: object) -> None:
    result = run_seat(
        mock_client, operator_persona, "forced_dissent", "Produce counter-case.", ForcedDissent  # type: ignore[arg-type]
    )
    assert result.status == SeatStatus.RESPONDED
    assert isinstance(result.output, ForcedDissent)


def test_timeout_produces_abstain(operator_persona: object) -> None:
    """Runner must catch TimeoutError on first attempt and return abstain_timeout."""
    client = MagicMock()
    client.get_default_seat_model.return_value = "claude-opus-4-7"
    client.call.side_effect = TimeoutError("timed out")
    result = run_seat(
        client, operator_persona, "sealed_opening", "Evaluate.", SealedOpening  # type: ignore[arg-type]
    )
    assert result.status == SeatStatus.ABSTAIN_TIMEOUT
    assert result.output is None
    assert client.call.call_count == 1


def test_malformed_output_retries_then_abstains(operator_persona: object) -> None:
    """Runner must retry once on malformed JSON, then abstain if still bad."""
    client = MagicMock()
    client.get_default_seat_model.return_value = "claude-opus-4-7"
    client.call.return_value = LLMResponse(
        content="not json at all",
        model="claude-opus-4-7",
    )
    result = run_seat(
        client, operator_persona, "sealed_opening", "Evaluate.", SealedOpening  # type: ignore[arg-type]
    )
    assert result.status == SeatStatus.ABSTAIN_MALFORMED
    assert result.output is None
    assert result.error is not None
    assert client.call.call_count == 2


def test_malformed_then_valid_succeeds(operator_persona: object) -> None:
    """Runner must succeed on second attempt when first returns garbage."""
    good_data = json.dumps({
        "seat_id": "operator-ceo",
        "stage": "sealed_opening",
        "position": "proceed",
        "one_paragraph_case": "X" * 150,
        "top_three_reasons": [
            "Reason one is well-grounded in data",
            "Reason two addresses the market clearly",
            "Reason three covers competitive dynamics",
        ],
        "kill_criteria": ["If CAC exceeds threshold by month six the model breaks"],
        "confidence_raw": 0.70,
    })

    client = MagicMock()
    client.get_default_seat_model.return_value = "claude-opus-4-7"
    client.call.side_effect = [
        LLMResponse(content="garbage", model="claude-opus-4-7"),
        LLMResponse(content=good_data, model="claude-opus-4-7"),
    ]
    result = run_seat(
        client, operator_persona, "sealed_opening", "Evaluate.", SealedOpening  # type: ignore[arg-type]
    )
    assert result.status == SeatStatus.RESPONDED
    assert isinstance(result.output, SealedOpening)
    assert result.output.seat_id == "operator-ceo"
    assert client.call.call_count == 2


def test_cost_tracking(mock_client: MockClient, operator_persona: object) -> None:
    result = run_seat(
        mock_client, operator_persona, "sealed_opening", "Evaluate.", SealedOpening  # type: ignore[arg-type]
    )
    assert result.response is not None
    assert result.response.cost_usd > 0
