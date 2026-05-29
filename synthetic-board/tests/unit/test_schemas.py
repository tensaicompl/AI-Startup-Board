"""Round-trip JSON tests for all Pydantic schemas."""

from __future__ import annotations

import json
import uuid
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from sboard.schemas import (
    AnonymizedReview,
    DevilsAdvocateOutput,
    ForcedDissent,
    KillCriterion,
    Memo,
    MemoMetadata,
    MemoModelIds,
    MemoSource,
    MeetingType,
    NextAction,
    Petition,
    PetitionConstraints,
    Position,
    Rebuttal,
    ReviewItem,
    SealedOpening,
    Signature,
    Vote,
)


FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "petitions"


# --- Petition ---


def _make_petition_dict() -> dict[str, object]:
    return {
        "petition_id": "00000000-0000-4000-8000-000000000001",
        "submitted_at": "2026-05-29T10:00:00Z",
        "submitter": "test_founder",
        "meeting_type": "idea_screen",
        "pitch": "x" * 100,
        "context": "Some additional context here.",
        "attachments": [],
        "constraints": {"max_wall_clock_seconds": 120, "max_cost_usd": 5.0},
    }


def test_petition_roundtrip() -> None:
    data = _make_petition_dict()
    p = Petition.model_validate(data)
    assert p.meeting_type == MeetingType.IDEA_SCREEN
    assert p.petition_id == uuid.UUID("00000000-0000-4000-8000-000000000001")
    dumped = json.loads(p.model_dump_json())
    p2 = Petition.model_validate(dumped)
    assert p2 == p


def test_petition_fixture_files() -> None:
    for fixture in sorted(FIXTURES_DIR.glob("*.json")):
        data = json.loads(fixture.read_text())
        p = Petition.model_validate(data)
        dumped = json.loads(p.model_dump_json())
        p2 = Petition.model_validate(dumped)
        assert p2 == p


def test_petition_rejects_short_pitch() -> None:
    data = _make_petition_dict()
    data["pitch"] = "too short"
    with pytest.raises(Exception):
        Petition.model_validate(data)


def test_petition_rejects_bad_meeting_type() -> None:
    data = _make_petition_dict()
    data["meeting_type"] = "pre_mortem"
    with pytest.raises(Exception):
        Petition.model_validate(data)


def test_petition_rejects_extra_fields() -> None:
    data = _make_petition_dict()
    data["rogue_field"] = "should fail"
    with pytest.raises(Exception):
        Petition.model_validate(data)


# --- Seat Outputs ---


def _sealed_opening_dict() -> dict[str, object]:
    return {
        "seat_id": "operator-ceo",
        "stage": "sealed_opening",
        "position": "proceed",
        "one_paragraph_case": "A" * 150,
        "top_three_reasons": [
            "Reason one is solid and well-founded",
            "Reason two addresses market need clearly",
            "Reason three covers the competitive angle",
        ],
        "kill_criteria": ["If CAC exceeds 1200 EUR by month six the unit economics collapse"],
        "confidence_raw": 0.75,
    }


def test_sealed_opening_roundtrip() -> None:
    data = _sealed_opening_dict()
    so = SealedOpening.model_validate(data)
    assert so.position == Position.PROCEED
    dumped = json.loads(so.model_dump_json())
    so2 = SealedOpening.model_validate(dumped)
    assert so2 == so


def test_sealed_opening_rejects_wrong_reason_count() -> None:
    data = _sealed_opening_dict()
    data["top_three_reasons"] = ["Only one reason here but it is long enough"]
    with pytest.raises(Exception):
        SealedOpening.model_validate(data)


def test_anonymized_review_roundtrip() -> None:
    data = {
        "seat_id": "operator-ceo",
        "stage": "anonymized_review",
        "reviews": [
            {
                "target_label": "Seat B",
                "agreement": "disagree",
                "one_sentence_reason": "The competitive moat argument is unconvincing without data.",
            },
            {
                "target_label": "Seat C",
                "agreement": "agree",
                "one_sentence_reason": "The customer validation point is well taken and grounded.",
            },
        ],
    }
    ar = AnonymizedReview.model_validate(data)
    dumped = json.loads(ar.model_dump_json())
    ar2 = AnonymizedReview.model_validate(dumped)
    assert ar2 == ar


def test_anonymized_review_rejects_bad_label() -> None:
    data = {
        "seat_id": "operator-ceo",
        "stage": "anonymized_review",
        "reviews": [
            {
                "target_label": "operator-ceo",
                "agreement": "agree",
                "one_sentence_reason": "This label should be Seat X format only.",
            }
        ],
    }
    with pytest.raises(Exception):
        AnonymizedReview.model_validate(data)


def test_rebuttal_roundtrip() -> None:
    data = {
        "seat_id": "operator-ceo",
        "stage": "rebuttal",
        "position": "conditional",
        "position_changed": True,
        "change_reason": "After seeing the competitive analysis I now believe conditional is more appropriate.",
        "rebuttal_text": "B" * 100,
    }
    r = Rebuttal.model_validate(data)
    dumped = json.loads(r.model_dump_json())
    r2 = Rebuttal.model_validate(dumped)
    assert r2 == r


def test_rebuttal_requires_reason_on_change() -> None:
    data = {
        "seat_id": "operator-ceo",
        "stage": "rebuttal",
        "position": "kill",
        "position_changed": True,
        "change_reason": None,
        "rebuttal_text": "C" * 100,
    }
    with pytest.raises(Exception):
        Rebuttal.model_validate(data)


def test_rebuttal_no_change_null_reason_ok() -> None:
    data = {
        "seat_id": "operator-ceo",
        "stage": "rebuttal",
        "position": "proceed",
        "position_changed": False,
        "change_reason": None,
        "rebuttal_text": "D" * 100,
    }
    r = Rebuttal.model_validate(data)
    assert r.change_reason is None


def test_devils_advocate_roundtrip() -> None:
    data = {
        "seat_id": "devils-advocate",
        "stage": "devils_advocate",
        "majority_trend": "proceed",
        "steelman_against_majority": "E" * 250,
        "strongest_kill_condition": "If the regulatory window closes before product launch the entire thesis is invalidated.",
    }
    da = DevilsAdvocateOutput.model_validate(data)
    dumped = json.loads(da.model_dump_json())
    da2 = DevilsAdvocateOutput.model_validate(dumped)
    assert da2 == da


def test_vote_roundtrip() -> None:
    data = {
        "seat_id": "outsider",
        "stage": "vote",
        "verdict": "kill",
        "confidence_raw": 0.85,
        "one_sentence_rationale": "The team lacks the technical depth to execute this within the runway.",
    }
    v = Vote.model_validate(data)
    dumped = json.loads(v.model_dump_json())
    v2 = Vote.model_validate(dumped)
    assert v2 == v


def test_vote_rejects_confidence_over_1() -> None:
    data = {
        "seat_id": "outsider",
        "stage": "vote",
        "verdict": "proceed",
        "confidence_raw": 1.5,
        "one_sentence_rationale": "Confidence should not exceed one point zero ever.",
    }
    with pytest.raises(Exception):
        Vote.model_validate(data)


def test_forced_dissent_roundtrip() -> None:
    data = {
        "seat_id": "operator-ceo",
        "stage": "forced_dissent",
        "counter_verdict": "kill",
        "counter_case": "F" * 250,
        "would_change_mind_if": "If the founding team adds a technical CTO with relevant domain experience.",
    }
    fd = ForcedDissent.model_validate(data)
    dumped = json.loads(fd.model_dump_json())
    fd2 = ForcedDissent.model_validate(dumped)
    assert fd2 == fd


# --- Memo ---


def _make_memo_dict() -> dict[str, object]:
    return {
        "memo_id": "11111111-1111-4111-8111-111111111111",
        "petition_id": "00000000-0000-4000-8000-000000000001",
        "meeting_type": "idea_screen",
        "protocol_version": "1.0.0",
        "created_at": "2026-05-29T11:00:00Z",
        "source": "board",
        "verdict": "conditional",
        "confidence_weighted": 1.85,
        "confidence_spread": 0.45,
        "verdict_reasoning": "G" * 100,
        "dissent_summary": "H" * 100,
        "dissent_source": "devils-advocate",
        "kill_criteria": [
            {
                "criterion": "Customer acquisition cost exceeds 1200 EUR by month six.",
                "owner_to_monitor": "Founder / Head of Growth",
            }
        ],
        "next_action": {
            "action": "Sign LOI with two pilot customers within 30 days.",
            "owner": "CEO",
            "deadline": "2026-06-30",
        },
        "signatures": [
            {
                "seat_id": "operator-ceo",
                "verdict": "proceed",
                "confidence_raw": 0.80,
                "confidence_recalibrated": 0.624,
            },
            {
                "seat_id": "devils-advocate",
                "verdict": "conditional",
                "confidence_raw": 0.70,
                "confidence_recalibrated": 0.644,
            },
            {
                "seat_id": "outsider",
                "verdict": "conditional",
                "confidence_raw": 0.65,
                "confidence_recalibrated": 0.4875,
            },
        ],
        "metadata": {
            "persona_hashes": {
                "operator-ceo": "abc123",
                "devils-advocate": "def456",
                "outsider": "ghi789",
            },
            "model_ids": {
                "seats": "claude-opus-4-7",
                "synthesis": "claude-sonnet-4-6",
            },
            "seed": 42,
            "wall_clock_seconds": 45.2,
            "llm_cost_usd": 2.15,
            "unanimous": False,
            "forced_dissent_triggered": False,
            "references_memo_id": None,
            "reasoning_overlap_score": 0.35,
        },
    }


def test_memo_roundtrip() -> None:
    data = _make_memo_dict()
    m = Memo.model_validate(data)
    assert m.verdict == Position.CONDITIONAL
    assert m.source == MemoSource.BOARD
    dumped = json.loads(m.model_dump_json())
    m2 = Memo.model_validate(dumped)
    assert m2 == m


def test_memo_rejects_empty_kill_criteria() -> None:
    data = _make_memo_dict()
    data["kill_criteria"] = []
    with pytest.raises(Exception):
        Memo.model_validate(data)


def test_memo_rejects_bad_protocol_version() -> None:
    data = _make_memo_dict()
    data["protocol_version"] = "v1.0"
    with pytest.raises(Exception):
        Memo.model_validate(data)


def test_memo_baseline_source() -> None:
    data = _make_memo_dict()
    data["source"] = "baseline"
    data["metadata"]["persona_hashes"] = {}  # type: ignore[index]
    m = Memo.model_validate(data)
    assert m.source == MemoSource.BASELINE
