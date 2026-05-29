"""Diversity check: ensure seated personas are structurally distinct."""

from __future__ import annotations

from sboard.seats.persona_loader import Persona

WORLDVIEW_AXES = (
    "time_horizon",
    "risk_appetite",
    "optimization_target",
    "evidence_weight",
    "decision_speed",
    "failure_response",
    "primary_lens",
)

MIN_DISTINCT_AXES = 4


def check_diversity(personas: dict[str, Persona]) -> tuple[bool, int]:
    """Check that personas differ on enough worldview axes.

    Returns (passes, distinct_count).
    """
    distinct_count = 0
    for axis in WORLDVIEW_AXES:
        values = {getattr(p.worldview, axis) for p in personas.values()}
        if len(values) > 1:
            distinct_count += 1
    return distinct_count >= MIN_DISTINCT_AXES, distinct_count
