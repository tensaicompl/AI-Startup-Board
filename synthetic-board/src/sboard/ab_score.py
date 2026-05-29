"""A/B gate tally: read master mappings + rating CSVs, apply the three pass
criteria from docs/07-evaluation.md §5, emit pass / marginal / fail.

Logic lives here (typed, tested, mypy-covered); `tests/ab/score.py` is the
runnable entry point.

Criteria (all three must hold to PASS):
  1. mean board dissent_sharpness − baseline ≥ 0.5
  2. mean board kill_criteria_clarity − baseline ≥ 0.5
  3. forced-choice board preference ≥ 60% of petitions
Decisiveness is monitored but not gating. Two-of-three is MARGINAL; ≤1 is FAIL.
"""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

DELTA_THRESHOLD = 0.5
FORCED_CHOICE_THRESHOLD = 0.60
GATING_AXES = ("dissent_sharpness", "kill_criteria_clarity")
MONITORED_AXIS = "decisiveness"
TEMPLATE_RATER_ID = "RATER_ID"


@dataclass(frozen=True)
class RatingRow:
    petition_id: str
    rater_id: str
    memo: str  # "A" | "B"
    axis: str
    score: int | None
    forced_choice: str | None  # "A" | "B" | "neither" | None


@dataclass(frozen=True)
class AxisComparison:
    axis: str
    board_mean: float | None
    baseline_mean: float | None
    delta: float | None
    n_board: int
    n_baseline: int

    @property
    def passes(self) -> bool:
        return self.delta is not None and self.delta >= DELTA_THRESHOLD


@dataclass(frozen=True)
class GateResult:
    n_petitions: int
    n_rating_rows: int
    comparisons: dict[str, AxisComparison]
    forced_choice_board_petitions: int
    forced_choice_total_petitions: int
    forced_choice_rate: float | None

    @property
    def forced_choice_passes(self) -> bool:
        return (
            self.forced_choice_rate is not None
            and self.forced_choice_rate >= FORCED_CHOICE_THRESHOLD
        )

    @property
    def gating_passed(self) -> int:
        passed = sum(self.comparisons[a].passes for a in GATING_AXES)
        return passed + int(self.forced_choice_passes)

    @property
    def verdict(self) -> str:
        passed = self.gating_passed
        if passed == 3:
            return "PASS"
        if passed == 2:
            return "MARGINAL"
        return "FAIL"


def parse_rating_csv(path: Path) -> list[RatingRow]:
    """Parse one petition's rating.csv, skipping unfilled template rows."""
    rows: list[RatingRow] = []
    with path.open(encoding="utf-8", newline="") as fh:
        for raw in csv.DictReader(fh):
            rater_id = (raw.get("rater_id") or "").strip()
            if not rater_id or rater_id == TEMPLATE_RATER_ID:
                continue
            score_raw = (raw.get("score") or "").strip()
            score = int(score_raw) if score_raw else None
            fc_raw = (raw.get("forced_choice") or "").strip()
            rows.append(
                RatingRow(
                    petition_id=(raw.get("petition_id") or "").strip(),
                    rater_id=rater_id,
                    memo=(raw.get("memo") or "").strip().upper(),
                    axis=(raw.get("axis") or "").strip(),
                    score=score,
                    forced_choice=fc_raw.lower() or None,
                )
            )
    return rows


def load_masters(master_dir: Path) -> dict[str, dict[str, str]]:
    """Return {petition_id: {label: pipeline}} from the master mapping files."""
    masters: dict[str, dict[str, str]] = {}
    for path in sorted(master_dir.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        masters[data["petition_id"]] = data["label_to_pipeline"]
    return masters


def _axis_comparison(axis: str, scores: dict[str, list[int]]) -> AxisComparison:
    board = scores.get("board", [])
    baseline = scores.get("baseline", [])
    board_mean = sum(board) / len(board) if board else None
    baseline_mean = sum(baseline) / len(baseline) if baseline else None
    delta = (
        board_mean - baseline_mean
        if board_mean is not None and baseline_mean is not None
        else None
    )
    return AxisComparison(
        axis=axis,
        board_mean=board_mean,
        baseline_mean=baseline_mean,
        delta=delta,
        n_board=len(board),
        n_baseline=len(baseline),
    )


def evaluate(
    masters: dict[str, dict[str, str]],
    ratings_by_petition: dict[str, list[RatingRow]],
) -> GateResult:
    """Apply the gate criteria to the collected ratings."""
    # axis -> pipeline -> [scores]
    axis_scores: dict[str, dict[str, list[int]]] = defaultdict(lambda: defaultdict(list))
    n_rows = 0
    fc_board_petitions = 0
    fc_total_petitions = 0

    for pid, mapping in masters.items():
        rows = ratings_by_petition.get(pid, [])
        # forced choice: one decision per (rater); map letter -> pipeline.
        fc_by_rater: dict[str, str] = {}
        for row in rows:
            if row.score is not None and row.axis and row.memo in mapping:
                axis_scores[row.axis][mapping[row.memo]].append(row.score)
                n_rows += 1
            if row.forced_choice and row.rater_id not in fc_by_rater:
                choice = row.forced_choice
                pipeline = mapping.get(choice.upper(), "neither" if choice == "neither" else "")
                if pipeline:
                    fc_by_rater[row.rater_id] = pipeline

        if fc_by_rater:
            fc_total_petitions += 1
            board_votes = sum(p == "board" for p in fc_by_rater.values())
            baseline_votes = sum(p == "baseline" for p in fc_by_rater.values())
            if board_votes > baseline_votes:
                fc_board_petitions += 1

    comparisons = {
        axis: _axis_comparison(axis, axis_scores.get(axis, {}))
        for axis in (*GATING_AXES, MONITORED_AXIS)
    }
    fc_rate = fc_board_petitions / fc_total_petitions if fc_total_petitions else None

    return GateResult(
        n_petitions=len(masters),
        n_rating_rows=n_rows,
        comparisons=comparisons,
        forced_choice_board_petitions=fc_board_petitions,
        forced_choice_total_petitions=fc_total_petitions,
        forced_choice_rate=fc_rate,
    )


def run(runs_dir: Path, master_dir: Path) -> GateResult:
    masters = load_masters(master_dir)
    ratings_by_petition: dict[str, list[RatingRow]] = {}
    for pid in masters:
        csv_path = runs_dir / pid / "rating.csv"
        ratings_by_petition[pid] = parse_rating_csv(csv_path) if csv_path.exists() else []
    return evaluate(masters, ratings_by_petition)


def _fmt(x: float | None) -> str:
    return f"{x:.2f}" if x is not None else "—"


def format_report(result: GateResult) -> str:
    lines = [
        "A/B GATE TALLY",
        "=" * 60,
        f"Petitions with a master mapping: {result.n_petitions}",
        f"Scored rating rows:              {result.n_rating_rows}",
        "",
        "Axis means (board vs baseline):",
    ]
    for axis in (*GATING_AXES, MONITORED_AXIS):
        c = result.comparisons[axis]
        gating = "gating" if axis in GATING_AXES else "monitored"
        mark = "✓" if (axis in GATING_AXES and c.passes) else (" " if axis in GATING_AXES else "·")
        lines.append(
            f"  [{mark}] {axis:<22} board={_fmt(c.board_mean)} "
            f"baseline={_fmt(c.baseline_mean)} Δ={_fmt(c.delta)} "
            f"(need Δ≥{DELTA_THRESHOLD}, {gating})"
        )
    fc_mark = "✓" if result.forced_choice_passes else " "
    lines.extend(
        [
            "",
            f"  [{fc_mark}] forced-choice board preference: "
            f"{result.forced_choice_board_petitions}/{result.forced_choice_total_petitions} "
            f"petitions ({_fmt(result.forced_choice_rate)}, "
            f"need ≥{FORCED_CHOICE_THRESHOLD})",
            "",
            "-" * 60,
            f"GATING CRITERIA PASSED: {result.gating_passed}/3",
            f"VERDICT: {result.verdict}",
        ]
    )
    if result.verdict == "MARGINAL":
        lines.append("(2 of 3 — diagnose the failing axis; one re-test allowed.)")
    elif result.verdict == "FAIL":
        lines.append("(≤1 of 3 — per the gate, the project ends. Write the post-mortem.)")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Tally the synthetic-board A/B gate.")
    parser.add_argument("--runs-dir", type=Path, default=Path("tests/ab/runs"))
    parser.add_argument("--master-dir", type=Path, default=Path("tests/ab/master"))
    args = parser.parse_args(argv)

    if not args.master_dir.exists():
        print(f"No master directory at {args.master_dir}; run `sboard ab` first.")
        return 2

    result = run(args.runs_dir, args.master_dir)
    print(format_report(result))
    return 0 if result.verdict == "PASS" else 1
