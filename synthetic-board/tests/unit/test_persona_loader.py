"""Tests for persona loader against the three sample personas."""

from __future__ import annotations

from pathlib import Path

import pytest

from sboard.seats.persona_loader import (
    GroundingType,
    PersonaValidationError,
    load_all_personas,
    load_persona,
)

PERSONAS_DIR = Path(__file__).parent.parent.parent / "personas"


def test_load_operator_ceo() -> None:
    p = load_persona(PERSONAS_DIR / "operator-ceo.md")
    assert p.seat_id == "operator-ceo"
    assert p.role == "Operator-CEO"
    assert p.voting is True
    assert p.voting_weight == 1.0
    assert p.is_devils_advocate is False
    assert p.grounding_type == GroundingType.NATAL_CHART
    assert p.worldview.time_horizon.value == "medium"
    assert p.worldview.primary_lens.value == "operations"
    assert p.protocol.recalibration_factor == 0.78
    assert p.file_hash  # non-empty
    assert "Operator-CEO" in p.system_prompt or "operator" in p.system_prompt.lower()


def test_load_devils_advocate() -> None:
    p = load_persona(PERSONAS_DIR / "devils-advocate.md")
    assert p.seat_id == "devils-advocate"
    assert p.role == "Devil's Advocate"
    assert p.is_devils_advocate is True
    assert p.grounding_type == GroundingType.NATAL_CHART
    assert p.worldview.risk_appetite.value == "low"
    assert p.worldview.primary_lens.value == "numbers"
    assert p.protocol.recalibration_factor == 0.92
    assert p.chart_signature is not None
    assert p.chart_signature["sun"] == "virgo"


def test_load_outsider() -> None:
    p = load_persona(PERSONAS_DIR / "outsider.md")
    assert p.seat_id == "outsider"
    assert p.role == "Outsider"
    assert p.is_devils_advocate is False
    assert p.grounding_type == GroundingType.SYNTHETIC
    assert p.source_figure is None
    assert p.chart_signature is None
    assert p.worldview.primary_lens.value == "customer"
    assert p.protocol.recalibration_factor == 0.75


def test_load_all_personas() -> None:
    personas = load_all_personas(PERSONAS_DIR)
    assert len(personas) == 7  # v1 trio + v2 four
    assert set(personas.keys()) == {
        "operator-ceo", "devils-advocate", "outsider",
        "visionary", "technical", "growth-advisor", "marketing",
    }


def test_load_roster_subset() -> None:
    trio = load_all_personas(PERSONAS_DIR, seat_ids=("operator-ceo", "devils-advocate", "outsider"))
    assert set(trio) == {"operator-ceo", "devils-advocate", "outsider"}


def test_system_prompt_is_markdown_body() -> None:
    p = load_persona(PERSONAS_DIR / "operator-ceo.md")
    assert p.system_prompt.startswith("# Steering File:")
    assert "---" not in p.system_prompt.split("\n")[0]


def test_file_hash_is_deterministic() -> None:
    p1 = load_persona(PERSONAS_DIR / "operator-ceo.md")
    p2 = load_persona(PERSONAS_DIR / "operator-ceo.md")
    assert p1.file_hash == p2.file_hash


def test_voice_redaction_aliases_loaded() -> None:
    p = load_persona(PERSONAS_DIR / "operator-ceo.md")
    assert "GE" in p.voice.redaction_aliases
    assert "General Electric" in p.voice.redaction_aliases


def test_must_produce_loaded() -> None:
    p = load_persona(PERSONAS_DIR / "operator-ceo.md")
    assert "kill_criteria" in p.must_produce


def test_rejects_invalid_frontmatter(tmp_path: Path) -> None:
    bad_file = tmp_path / "bad.md"
    bad_file.write_text("---\nseat_id: x\n---\nBody here.")
    with pytest.raises(PersonaValidationError):
        load_persona(bad_file)


def test_rejects_missing_frontmatter(tmp_path: Path) -> None:
    bad_file = tmp_path / "nofm.md"
    bad_file.write_text("Just a markdown file with no frontmatter.")
    with pytest.raises(PersonaValidationError):
        load_persona(bad_file)


def test_worldview_diversity_across_personas() -> None:
    """The three personas should differ on at least 4 of 7 worldview axes."""
    personas = load_all_personas(PERSONAS_DIR)
    axes = [
        "time_horizon", "risk_appetite", "optimization_target",
        "evidence_weight", "decision_speed", "failure_response", "primary_lens",
    ]
    distinct_count = 0
    for axis in axes:
        values = {getattr(p.worldview, axis) for p in personas.values()}
        if len(values) > 1:
            distinct_count += 1
    assert distinct_count >= 4, f"Only {distinct_count} distinct worldview axes"
