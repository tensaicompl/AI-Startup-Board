"""A/B harness — the gate the MVP was built to pass (docs/07-evaluation.md).

`run_ab` runs the board and the single-LLM baseline on one petition in parallel,
strips all source-identifying detail from both memos, assigns blind A/B labels,
and writes the rater-facing bundle to `tests/ab/runs/<petition_id>/`. The label →
pipeline mapping is written to a SEPARATE `tests/ab/master/` directory so the
rater never sees which memo came from which pipeline.

Anonymization here is structural, not just metadata-stripping: the board memo
carries three signatures and the baseline one, so rendering only the neutral
decision surface (verdict / reasoning / dissent / kill criteria / next action)
is what actually keeps the two indistinguishable. See Decision 007.
"""

from __future__ import annotations

import json
import random
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from sboard.baseline import DEFAULT_BASELINE_PROMPT_PATH, run_baseline
from sboard.chair.meeting_state import MeetingState, ProtocolState
from sboard.chair.state_machine import run_meeting
from sboard.db.store import (
    get_petition,
    init_db,
    insert_memo,
    insert_petition,
    insert_transcript,
)
from sboard.schemas import Memo, Petition
from sboard.seats.llm_client import AnthropicClient, MockClient
from sboard.seats.persona_loader import load_all_personas
from sboard.service import DEFAULT_DB_PATH, DEFAULT_PERSONAS_DIR, DEFAULT_SEED, load_petition

DEFAULT_RUNS_DIR = Path("tests/ab/runs")
DEFAULT_MASTER_DIR = Path("tests/ab/master")
DEFAULT_AB_SEED = 1

AXES = ("dissent_sharpness", "kill_criteria_clarity", "decisiveness")


class ABError(Exception):
    """The A/B run could not complete (a pipeline failed)."""


@dataclass(frozen=True)
class ABResult:
    petition_id: str
    run_dir: Path
    master_path: Path
    rating_csv_path: Path
    board_memo: Memo
    baseline_memo: Memo
    label_to_pipeline: dict[str, str]  # {"A": "board"|"baseline", "B": ...}


def render_anonymized_memo(memo: Memo) -> str:
    """Render only the pipeline-neutral decision surface.

    Deliberately omits source, signatures, confidence internals, and all
    metadata — anything that would reveal whether this is the board or the
    baseline. Both pipelines produce an identically-structured document.
    """
    lines: list[str] = [
        f"# Advisory Memo — {memo.verdict.value.upper()}",
        "",
        "## Verdict Reasoning",
        "",
        memo.verdict_reasoning,
        "",
        "## Dissent",
        "",
        memo.dissent_summary,
        "",
        "## Kill Criteria",
        "",
    ]
    for i, kc in enumerate(memo.kill_criteria, 1):
        lines.append(f"{i}. {kc.criterion}")
        lines.append(f"   *Owner:* {kc.owner_to_monitor}")
    lines.extend(
        [
            "",
            "## Next Action",
            "",
            f"**Action:** {memo.next_action.action}",
            f"**Owner:** {memo.next_action.owner}",
            f"**Deadline:** {memo.next_action.deadline.isoformat()}",
            "",
        ]
    )
    return "\n".join(lines)


def _render_petition(petition: Petition) -> str:
    context = petition.context or "(none provided)"
    return "\n".join(
        [
            f"# Petition {petition.petition_id}",
            "",
            "## Pitch",
            "",
            petition.pitch,
            "",
            "## Context",
            "",
            context,
            "",
        ]
    )


def _rating_csv_template(petition_id: str) -> str:
    rows = ["petition_id,rater_id,memo,axis,score,forced_choice"]
    for label in ("A", "B"):
        for axis in AXES:
            rows.append(f"{petition_id},RATER_ID,{label},{axis},,")
    return "\n".join(rows) + "\n"


_HOW_TO_RATE = """\
# How to rate (blind)

You are scoring two advisory memos, A and B, written for the petition in
`petition.md`. You do NOT know which memo came from which process. Score each
memo on its own merits.

For EACH memo (A and B), give a 1-5 score on three axes (see scale below), then
make one forced choice across both memos.

## Axes (1-5)

- **dissent_sharpness** — 5: names a specific, non-obvious objection that
  materially affects the verdict. 3: a generic objection. 1: no real dissent.
- **kill_criteria_clarity** — 5: every kill criterion is measurable,
  time-bounded, and tied to a metric. 3: a mix. 1: aspirational or absent.
- **decisiveness** — 5: a clear verdict you could act on in 60 seconds.
  3: a verdict but hedged. 1: five hedges, no clear call.

## Forced choice

"If you were the founder, which memo would you act on?" — answer `A`, `B`, or
`neither`. Put it in the `forced_choice` cell of ONE of your rows.

## Filling `rating.csv`

Replace `RATER_ID` with your own id on every row you fill. Put your 1-5 score in
the `score` cell. There are 6 rows per rater (2 memos x 3 axes). Add more blocks
below for additional raters.
"""


def _build_master(
    petition_id: str,
    *,
    seed: int,
    ab_seed: int,
    label_to_pipeline: dict[str, str],
    board_memo: Memo,
    baseline_memo: Memo,
) -> dict[str, object]:
    pipeline_to_label = {v: k for k, v in label_to_pipeline.items()}
    return {
        "petition_id": petition_id,
        "created_at": datetime.now(UTC).isoformat(),
        "seed": seed,
        "ab_seed": ab_seed,
        "label_to_pipeline": label_to_pipeline,
        "pipeline_to_label": pipeline_to_label,
        "memo_ids": {
            "board": str(board_memo.memo_id),
            "baseline": str(baseline_memo.memo_id),
        },
    }


def _persist_ab(
    db_path: Path,
    petition: Petition,
    board_state: MeetingState,
    board_memo: Memo,
    baseline_memo: Memo,
) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = init_db(db_path)
    try:
        pid = str(petition.petition_id)
        if get_petition(conn, pid) is None:
            insert_petition(conn, petition)
        insert_transcript(conn, pid, board_state.seed, board_state.transcript)
        insert_memo(conn, board_memo)
        insert_memo(conn, baseline_memo)
    finally:
        conn.close()


def _run_board(
    petition: Petition, personas_dir: Path, seed: int, client: AnthropicClient
) -> MeetingState:
    personas = load_all_personas(personas_dir)
    if not personas:
        raise ABError(f"No persona files found in {personas_dir}")
    state = MeetingState(petition=petition, personas=personas, seed=seed)
    final = run_meeting(state, client)
    if final.current_state == ProtocolState.ABORTED or final.memo is None:
        raise ABError(final.error or "Board aborted before producing a memo")
    return final


def run_ab(
    petition_path: Path,
    *,
    personas_dir: Path = DEFAULT_PERSONAS_DIR,
    runs_dir: Path = DEFAULT_RUNS_DIR,
    master_dir: Path = DEFAULT_MASTER_DIR,
    db_path: Path = DEFAULT_DB_PATH,
    baseline_prompt_path: Path = DEFAULT_BASELINE_PROMPT_PATH,
    seed: int = DEFAULT_SEED,
    ab_seed: int = DEFAULT_AB_SEED,
    client: AnthropicClient | None = None,
    persist_db: bool = True,
) -> ABResult:
    """Run board + baseline on one petition and write the blind rating bundle."""
    client = client or MockClient()
    petition = load_petition(petition_path)
    pid = str(petition.petition_id)

    # Both pipelines are independent; run them concurrently.
    with ThreadPoolExecutor(max_workers=2) as pool:
        board_future = pool.submit(_run_board, petition, personas_dir, seed, client)
        baseline_future = pool.submit(
            run_baseline, petition, client, seed=seed, prompt_path=baseline_prompt_path
        )
        board_state = board_future.result()
        baseline_memo = baseline_future.result()

    board_memo = board_state.memo
    assert board_memo is not None  # _run_board guarantees this

    # Deterministic blind A/B assignment, recorded only in the master file.
    rng = random.Random(ab_seed)
    board_label = "A" if rng.random() < 0.5 else "B"
    baseline_label = "B" if board_label == "A" else "A"
    label_to_pipeline = {board_label: "board", baseline_label: "baseline"}
    label_to_memo = {board_label: board_memo, baseline_label: baseline_memo}

    # Rater-facing bundle.
    run_dir = runs_dir / pid
    run_dir.mkdir(parents=True, exist_ok=True)
    for label in ("A", "B"):
        (run_dir / f"{label}.md").write_text(
            render_anonymized_memo(label_to_memo[label]), encoding="utf-8"
        )
    (run_dir / "petition.md").write_text(_render_petition(petition), encoding="utf-8")
    rating_csv_path = run_dir / "rating.csv"
    rating_csv_path.write_text(_rating_csv_template(pid), encoding="utf-8")
    (run_dir / "HOW_TO_RATE.md").write_text(_HOW_TO_RATE, encoding="utf-8")

    # Master mapping, held separately from the rater bundle.
    master_dir.mkdir(parents=True, exist_ok=True)
    master_path = master_dir / f"{pid}.json"
    master = _build_master(
        pid,
        seed=seed,
        ab_seed=ab_seed,
        label_to_pipeline=label_to_pipeline,
        board_memo=board_memo,
        baseline_memo=baseline_memo,
    )
    master_path.write_text(json.dumps(master, indent=2), encoding="utf-8")

    if persist_db:
        _persist_ab(db_path, petition, board_state, board_memo, baseline_memo)

    return ABResult(
        petition_id=pid,
        run_dir=run_dir,
        master_path=master_path,
        rating_csv_path=rating_csv_path,
        board_memo=board_memo,
        baseline_memo=baseline_memo,
        label_to_pipeline=label_to_pipeline,
    )
