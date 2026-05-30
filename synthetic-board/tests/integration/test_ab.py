"""Task 10 — the A/B harness and the gate tally.

Exercises `sboard ab` end-to-end against mocks: both pipelines run, the rater
bundle is written, the two memos are anonymized and structurally
indistinguishable, the master mapping is held separately, and the score tally
applies the three gate criteria. The live client's control flow is covered with
the Anthropic SDK patched (no API key, no network).
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest
from typer.testing import CliRunner, Result

from sboard.ab import AXES, ABError, run_ab
from sboard.ab_score import RatingRow, evaluate, parse_rating_csv, run
from sboard.baseline import run_baseline
from sboard.cli import app
from sboard.schemas import MemoSource
from sboard.seats.llm_client import LiveAnthropicClient, MockClient
from sboard.service import load_petition

ROOT = Path(__file__).parent.parent.parent
PERSONAS_DIR = ROOT / "personas"
PETITION_01 = ROOT / "tests" / "fixtures" / "petitions" / "01-iso-compliance.json"
BASELINE_PROMPT = ROOT / "tests" / "ab" / "baseline_prompt.txt"

FORBIDDEN = [
    "Welch",
    "Buffett",
    "operator-ceo",
    "devils-advocate",
    "outsider",
    "Source:",
    "Signatures",
    "Seed:",
    "persona",
    "claude-",
    "baseline",
    "board",
    "confidence",
]

runner = CliRunner()


def _run_ab(tmp_path: Path, **kw: object) -> object:
    return run_ab(
        PETITION_01,
        personas_dir=PERSONAS_DIR,
        runs_dir=tmp_path / "runs",
        master_dir=tmp_path / "master",
        db_path=tmp_path / "sboard.db",
        baseline_prompt_path=BASELINE_PROMPT,
        client=MockClient(),
        **kw,  # type: ignore[arg-type]
    )


# --- baseline pipeline ---


def test_run_baseline_builds_source_baseline_memo() -> None:
    petition = load_petition(PETITION_01)
    memo = run_baseline(petition, MockClient(), prompt_path=BASELINE_PROMPT)
    assert memo.source == MemoSource.BASELINE
    assert memo.metadata.persona_hashes == {}  # no personas in the baseline
    assert len(memo.signatures) == 1
    assert memo.confidence_spread == 0.0
    assert memo.kill_criteria  # at least one
    assert memo.petition_id == petition.petition_id


# --- harness end-to-end ---


def test_ab_end_to_end_writes_bundle_and_persists(tmp_path: Path) -> None:
    result = _run_ab(tmp_path)

    run_dir = tmp_path / "runs" / result.petition_id
    for name in ("A.md", "B.md", "petition.md", "rating.csv", "HOW_TO_RATE.md"):
        assert (run_dir / name).exists(), f"missing {name}"

    master_path = tmp_path / "master" / f"{result.petition_id}.json"
    assert master_path.exists()

    # Both memos persisted to the append-only audit DB.
    conn = sqlite3.connect(str(tmp_path / "sboard.db"))
    try:
        assert conn.execute("SELECT COUNT(*) FROM petitions").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM transcripts").fetchone()[0] == 1
        sources = {r[0] for r in conn.execute("SELECT source FROM memos").fetchall()}
        assert sources == {"board", "baseline"}
    finally:
        conn.close()


def test_ab_anonymized_memos_have_no_pipeline_tells(tmp_path: Path) -> None:
    result = _run_ab(tmp_path)
    run_dir = result.run_dir
    for label in ("A", "B"):
        text = (run_dir / f"{label}.md").read_text()
        low = text.lower()
        for token in FORBIDDEN:
            assert token.lower() not in low, f"{label}.md leaked {token!r}"
        # Neutral decision surface is present.
        assert "## Verdict Reasoning" in text
        assert "## Kill Criteria" in text


def test_ab_memos_structurally_indistinguishable(tmp_path: Path) -> None:
    result = _run_ab(tmp_path)
    run_dir = result.run_dir

    def sections(label: str) -> list[str]:
        return [
            ln for ln in (run_dir / f"{label}.md").read_text().splitlines()
            if ln.startswith("## ")
        ]

    expected = ["## Verdict Reasoning", "## Dissent", "## Kill Criteria", "## Next Action"]
    assert sections("A") == expected
    assert sections("B") == expected


def test_ab_master_maps_labels_to_both_pipelines(tmp_path: Path) -> None:
    result = _run_ab(tmp_path)
    master = json.loads(result.master_path.read_text())

    assert set(master["label_to_pipeline"].values()) == {"board", "baseline"}
    assert set(master["label_to_pipeline"].keys()) == {"A", "B"}
    assert master["memo_ids"]["board"] == str(result.board_memo.memo_id)
    assert master["memo_ids"]["baseline"] == str(result.baseline_memo.memo_id)
    # The master file is NOT inside the rater bundle directory.
    assert result.master_path.parent != result.run_dir


def test_ab_label_assignment_is_deterministic(tmp_path: Path) -> None:
    a = _run_ab(tmp_path / "one", ab_seed=7)
    b = _run_ab(tmp_path / "two", ab_seed=7)
    assert a.label_to_pipeline == b.label_to_pipeline


def test_ab_no_personas_raises(tmp_path: Path) -> None:
    empty = tmp_path / "no_personas"
    empty.mkdir()
    with pytest.raises(ABError):
        run_ab(
            PETITION_01,
            personas_dir=empty,
            runs_dir=tmp_path / "runs",
            master_dir=tmp_path / "master",
            db_path=tmp_path / "db.sqlite",
            baseline_prompt_path=BASELINE_PROMPT,
            client=MockClient(),
        )


def test_ab_via_cli(tmp_path: Path) -> None:
    result: Result = runner.invoke(
        app,
        [
            "ab",
            str(PETITION_01),
            "--personas",
            str(PERSONAS_DIR),
            "--runs-dir",
            str(tmp_path / "runs"),
            "--master-dir",
            str(tmp_path / "master"),
            "--db",
            str(tmp_path / "sboard.db"),
        ],
    )
    assert result.exit_code == 0, result.output
    assert "A/B bundle written" in result.stdout
    masters = list((tmp_path / "master").glob("*.json"))
    assert len(masters) == 1


# --- gate tally (sboard.ab_score) ---


def _rating_rows(
    pid: str, board_label: str, baseline_label: str, board: int, base: int, fc: str
) -> list[RatingRow]:
    rows: list[RatingRow] = []
    for axis in AXES:
        rows.append(RatingRow(pid, "r1", board_label, axis, board, None))
        rows.append(RatingRow(pid, "r1", baseline_label, axis, base, None))
    rows.append(RatingRow(pid, "r1", "", "", None, fc))  # forced-choice row
    return rows


def test_score_pass_when_board_wins_all_three() -> None:
    masters = {
        "p1": {"A": "board", "B": "baseline"},
        "p2": {"A": "baseline", "B": "board"},
    }
    ratings = {
        "p1": _rating_rows("p1", "A", "B", 5, 3, "a"),  # board=A, picks board
        "p2": _rating_rows("p2", "B", "A", 5, 3, "b"),  # board=B, picks board
    }
    res = evaluate(masters, ratings)
    assert res.comparisons["dissent_sharpness"].delta == 2.0
    assert res.comparisons["kill_criteria_clarity"].passes
    assert res.forced_choice_rate == 1.0
    assert res.verdict == "PASS"


def test_score_fail_when_baseline_wins() -> None:
    masters = {"p1": {"A": "board", "B": "baseline"}}
    ratings = {"p1": _rating_rows("p1", "A", "B", 2, 5, "b")}  # picks baseline
    res = evaluate(masters, ratings)
    assert not res.comparisons["dissent_sharpness"].passes
    assert not res.forced_choice_passes
    assert res.verdict == "FAIL"


def test_score_marginal_two_of_three() -> None:
    # Board wins both gating axes but raters still prefer the baseline.
    masters = {"p1": {"A": "board", "B": "baseline"}}
    ratings = {"p1": _rating_rows("p1", "A", "B", 5, 3, "b")}
    res = evaluate(masters, ratings)
    assert res.comparisons["dissent_sharpness"].passes
    assert res.comparisons["kill_criteria_clarity"].passes
    assert not res.forced_choice_passes
    assert res.verdict == "MARGINAL"


def test_score_run_reads_real_bundle(tmp_path: Path) -> None:
    """End-to-end: ab writes a bundle; a filled rating.csv tallies through run()."""
    result = _run_ab(tmp_path)
    board_label = next(k for k, v in result.label_to_pipeline.items() if v == "board")
    base_label = next(k for k, v in result.label_to_pipeline.items() if v == "baseline")

    csv_lines = ["petition_id,rater_id,memo,axis,score,forced_choice"]
    for axis in AXES:
        csv_lines.append(f"{result.petition_id},r1,{board_label},{axis},5,")
        csv_lines.append(f"{result.petition_id},r1,{base_label},{axis},3,")
    csv_lines.append(f"{result.petition_id},r1,,,,{board_label.lower()}")
    result.rating_csv_path.write_text("\n".join(csv_lines) + "\n", encoding="utf-8")

    gate = run(tmp_path / "runs", tmp_path / "master")
    assert gate.verdict == "PASS"


def test_parse_rating_csv_skips_template_rows(tmp_path: Path) -> None:
    csv = (
        "petition_id,rater_id,memo,axis,score,forced_choice\n"
        "p1,RATER_ID,A,dissent_sharpness,,\n"  # template placeholder, skipped
        "p1,alice,A,dissent_sharpness,4,a\n"
    )
    path = tmp_path / "rating.csv"
    path.write_text(csv, encoding="utf-8")
    rows = parse_rating_csv(path)
    assert len(rows) == 1
    assert rows[0].rater_id == "alice"
    assert rows[0].score == 4
    assert rows[0].forced_choice == "a"


# --- live client (SDK patched) ---


def test_live_client_requires_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(RuntimeError):
        LiveAnthropicClient()


def test_live_client_extracts_tool_use(monkeypatch: pytest.MonkeyPatch) -> None:
    from sboard.baseline import BaselineMemoOutput

    client = LiveAnthropicClient(api_key="test-key")

    payload = {"hello": "world", "n": 3}

    class _Block:
        type = "tool_use"
        input = payload

    class _Usage:
        input_tokens = 11
        output_tokens = 22

    class _Msg:
        content = [_Block()]
        model = "claude-opus-4-7"
        usage = _Usage()

    monkeypatch.setattr(client._client.messages, "create", lambda **_: _Msg())

    resp = client.call(
        system_prompt="sys",
        user_message="usr",
        output_schema=BaselineMemoOutput,
        seat_id="baseline",
        stage="baseline",
    )
    assert json.loads(resp.content) == payload
    assert resp.model == "claude-opus-4-7"
    assert resp.input_tokens == 11
    assert resp.output_tokens == 22


def test_extract_tool_payload_unwraps_and_strips() -> None:
    """Models intermittently wrap tool args under a generic key or add stray meta
    keys (seen live: 'parameter', '$PARAMETER_NAME', '$FUNCTION_NAME'). The
    extractor must recover the real payload in every case."""
    from sboard.schemas import SealedOpening
    from sboard.seats.llm_client import _extract_tool_payload

    real = {
        "seat_id": "operator-ceo",
        "stage": "sealed_opening",
        "position": "kill",
        "one_paragraph_case": "x" * 120,
        "top_three_reasons": ["a" * 12, "b" * 12, "c" * 12],
        "kill_criteria": ["k" * 12],
        "confidence_raw": 0.5,
    }
    # already-correct, dict wrapper, json-string wrapper, stray meta key
    assert _extract_tool_payload(real, SealedOpening) == real
    assert _extract_tool_payload({"parameter": real}, SealedOpening) == real
    assert _extract_tool_payload({"$PARAMETER_NAME": json.dumps(real)}, SealedOpening) == real
    assert _extract_tool_payload(
        {"$FUNCTION_NAME": "emit_structured_output", **real}, SealedOpening
    ) == real
    # the recovered payload actually validates
    assert SealedOpening.model_validate(
        _extract_tool_payload({"parameter": real}, SealedOpening)
    )


def test_run_seat_forces_canonical_seat_id() -> None:
    """A real model invents seat_id values ('devils_advocate'); the chair must
    overwrite them with the canonical persona id ('devils-advocate')."""
    from sboard.schemas import SealedOpening
    from sboard.seats.llm_client import LLMResponse
    from sboard.seats.persona_loader import load_all_personas
    from sboard.seats.seat import SeatStatus, run_seat

    persona = load_all_personas(PERSONAS_DIR)["devils-advocate"]

    class WrongIdClient(MockClient):
        def call(self, **kw: object) -> LLMResponse:
            data = {
                "seat_id": "devils_advocate",  # wrong: underscore, not canonical
                "stage": "sealed_opening",
                "position": "kill",
                "one_paragraph_case": "x" * 120,
                "top_three_reasons": ["a" * 12, "b" * 12, "c" * 12],
                "kill_criteria": ["k" * 12],
                "confidence_raw": 0.5,
            }
            return LLMResponse(content=json.dumps(data), model="m", input_tokens=1, output_tokens=1)

    res = run_seat(WrongIdClient(), persona, "sealed_opening", "msg", SealedOpening)
    assert res.status == SeatStatus.RESPONDED
    assert res.output is not None
    assert res.output.seat_id == "devils-advocate"
