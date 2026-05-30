"""Task v2.2 — four new persona files (Jobs, Torvalds, Bezos, Ogilvy).

Validates that all seven seats load, the new advisor/gtm_only flags parse, the
chart grounding matches Decision 008 (Jobs AA + ascendant; the three relaxed
figures noon/X/no-ascendant), the diversity check passes with seven seats, the
founder-required redaction aliases are present, and no source-figure proper noun
leaks into a steering body.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from sboard.chair.diversity import check_diversity
from sboard.seats.persona_loader import (
    GroundingType,
    Persona,
    load_all_personas,
)

PERSONAS_DIR = Path(__file__).parent.parent.parent / "personas"
NEW_SEATS = ("visionary", "technical", "growth-advisor", "marketing")

# Proper nouns that must never appear in a steering body (word-boundary checked).
BODY_FORBIDDEN: dict[str, list[str]] = {
    "visionary": ["Jobs", "Steve", "Apple", "Pixar", "NeXT", "Wozniak", "Sculley", "Cupertino", "iPhone", "iPod"],
    "technical": ["Linus", "Torvalds", "Linux", "Helsinki", "Finland", "Transmeta"],
    "growth-advisor": ["Bezos", "Jeff", "Amazon", "Princeton", "Seattle", "Blue Origin"],
    "marketing": ["Ogilvy", "Mather", "Aga Khan"],
}

# The redaction aliases the founder required for each seat (must be a subset).
REQUIRED_ALIASES: dict[str, list[str]] = {
    "visionary": ["Steve", "Apple", "NeXT", "Pixar", "iPod", "iPhone", "Mac", "Wozniak", "Sculley", "Reed College", "Cupertino"],
    "technical": ["Linus", "Linux", "Git", "Helsinki", "Finland", "Transmeta", "Tovalds", "kernel"],
    "growth-advisor": ["Jeff", "Amazon", "AWS", "Blue Origin", "Washington Post", "Princeton", "D.E. Shaw", "Seattle", "Albuquerque"],
    "marketing": ["David", "Mather", "Aga Khan", "Touffou", "Confessions"],
}


@pytest.fixture()
def personas() -> dict[str, Persona]:
    return load_all_personas(PERSONAS_DIR)


def test_all_seven_seats_load(personas: dict[str, Persona]) -> None:
    assert set(personas) == {
        "operator-ceo",
        "devils-advocate",
        "outsider",
        "visionary",
        "technical",
        "growth-advisor",
        "marketing",
    }


def test_seat_flags(personas: dict[str, Persona]) -> None:
    assert personas["visionary"].voting is True
    assert personas["technical"].voting is True
    assert personas["growth-advisor"].voting is False
    assert personas["growth-advisor"].advisor is True
    assert personas["growth-advisor"].gtm_only is False
    assert personas["marketing"].voting is False
    assert personas["marketing"].gtm_only is True
    assert personas["marketing"].advisor is False


def test_exactly_five_voting_seats(personas: dict[str, Persona]) -> None:
    assert sum(p.voting for p in personas.values()) == 5
    assert sum(p.advisor for p in personas.values()) == 1
    assert sum(p.gtm_only for p in personas.values()) == 1


def test_chart_grounding_matches_decision_008(personas: dict[str, Persona]) -> None:
    jobs = personas["visionary"]
    assert jobs.chart_signature is not None
    assert jobs.chart_signature["rodden_rating"] == "AA"
    assert jobs.chart_signature["ascendant"] == "virgo"
    assert jobs.birth is not None and jobs.birth["time_known"] is True

    for seat in ("technical", "growth-advisor", "marketing"):
        p = personas[seat]
        assert p.grounding_type == GroundingType.NATAL_CHART
        assert p.chart_signature is not None
        assert p.chart_signature["rodden_rating"] == "X"
        assert p.chart_signature["ascendant"] is None
        assert p.birth is not None and p.birth["time_known"] is False


def test_diversity_passes_with_seven_seats(personas: dict[str, Persona]) -> None:
    passes, count = check_diversity(personas)
    assert passes
    assert count >= 5  # v2 requires >= 5 of 7 axes distinct


@pytest.mark.parametrize("seat", NEW_SEATS)
def test_required_redaction_aliases_present(seat: str, personas: dict[str, Persona]) -> None:
    aliases = set(personas[seat].voice.redaction_aliases)
    missing = [a for a in REQUIRED_ALIASES[seat] if a not in aliases]
    assert not missing, f"{seat} missing required redaction aliases: {missing}"


@pytest.mark.parametrize("seat", NEW_SEATS)
def test_body_has_no_source_figure_proper_nouns(seat: str, personas: dict[str, Persona]) -> None:
    body = personas[seat].system_prompt
    leaks = [t for t in BODY_FORBIDDEN[seat] if re.search(rf"\b{re.escape(t)}\b", body)]
    assert not leaks, f"{seat} body leaks proper nouns: {leaks}"


@pytest.mark.parametrize("seat", NEW_SEATS)
def test_source_figure_surname_only_in_frontmatter(seat: str, personas: dict[str, Persona]) -> None:
    p = personas[seat]
    assert p.source_figure is not None
    surname = p.source_figure.split()[-1]
    assert surname not in p.system_prompt
