"""Confidence recalibration and weighted vote tally."""

from __future__ import annotations

from sboard.schemas import Position, Vote


def recalibrate(confidence_raw: float, recalibration_factor: float) -> float:
    return confidence_raw * recalibration_factor


def tally_votes(
    votes: list[Vote],
    recalibration_factors: dict[str, float],
    voting_weights: dict[str, float],
) -> tuple[Position, float, float]:
    """Compute weighted tally.

    Returns (winning_verdict, winning_score, spread).
    """
    scores: dict[Position, float] = {
        Position.PROCEED: 0.0,
        Position.KILL: 0.0,
        Position.CONDITIONAL: 0.0,
    }

    for vote in votes:
        recal = recalibrate(vote.confidence_raw, recalibration_factors[vote.seat_id])
        weight = voting_weights.get(vote.seat_id, 1.0)
        scores[vote.verdict] += recal * weight

    sorted_scores = sorted(scores.values(), reverse=True)
    winning_score = sorted_scores[0]
    runner_up = sorted_scores[1]
    spread = winning_score - runner_up

    winning_verdict = max(scores, key=lambda v: scores[v])

    return winning_verdict, winning_score, spread


def is_unanimous(votes: list[Vote]) -> bool:
    verdicts = {v.verdict for v in votes}
    return len(verdicts) == 1


def select_forced_dissent_seat(
    votes: list[Vote],
    recalibration_factors: dict[str, float],
) -> str:
    """Select the lowest-confidence seat; ties broken alphabetically by seat_id."""
    recalibrated = [
        (v.seat_id, recalibrate(v.confidence_raw, recalibration_factors[v.seat_id]))
        for v in votes
    ]
    recalibrated.sort(key=lambda x: (x[1], x[0]))
    return recalibrated[0][0]
