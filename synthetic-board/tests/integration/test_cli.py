"""Task 9 — CLI: `sboard convene` and `sboard inspect` end-to-end.

Runs the real protocol against the deterministic MockClient (no API key needed),
through the actual Typer app, asserting the memo is written, the audit trail is
persisted, inspect round-trips by memo_id, and source-figure names never surface.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest
from typer.testing import CliRunner, Result

from sboard.cli import app

ROOT = Path(__file__).parent.parent.parent
PERSONAS_DIR = ROOT / "personas"
PETITION_01 = ROOT / "tests" / "fixtures" / "petitions" / "01-iso-compliance.json"

# Source-figure tokens that must never appear in any user-visible string (HANDOFF §8).
# Names, nicknames, companies, and birthplaces of the two charted source figures
# (J.F. "Jack" Welch — General Electric, Peabody MA; Warren Buffett — Berkshire
# Hathaway, Omaha NE), plus the Outsider's synthetic alias.
FORBIDDEN_NAMES = [
    "Welch",
    "Buffett",
    "Jack",
    "Warren",
    "Marek",
    "Berkshire",
    "General Electric",
    "GE",
    "Peabody",
    "Omaha",
    "Hathaway",
]

runner = CliRunner()


def _convene(out: Path, db: Path, *, extra: list[str] | None = None) -> Result:
    args = [
        "convene",
        str(PETITION_01),
        "--db",
        str(db),
        "--out",
        str(out),
        "--personas",
        str(PERSONAS_DIR),
        *(extra or []),
    ]
    return runner.invoke(app, args)


def _memo_id_from_out(out: Path) -> str:
    mds = list(out.glob("*.md"))
    assert len(mds) == 1, f"expected exactly one memo .md, found {mds}"
    return mds[0].stem


def test_convene_writes_memo_and_persists(tmp_path: Path) -> None:
    out = tmp_path / "out"
    db = tmp_path / "runs" / "sboard.db"

    result = _convene(out, db)

    assert result.exit_code == 0, result.output
    # Memo artifacts written to disk.
    memo_id = _memo_id_from_out(out)
    assert (out / f"{memo_id}.md").exists()
    assert (out / f"{memo_id}.json").exists()
    # Audit DB created and populated.
    assert db.exists()
    conn = sqlite3.connect(str(db))
    try:
        assert conn.execute("SELECT COUNT(*) FROM petitions").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM transcripts").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM memos").fetchone()[0] == 1
    finally:
        conn.close()
    # User-facing summary closes the loop to `inspect`.
    assert "Verdict:" in result.stdout
    assert f"sboard inspect {memo_id}" in result.stdout


def test_convene_missing_petition_is_usage_error(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        ["convene", str(tmp_path / "nope.json"), "--db", str(tmp_path / "x.db")],
    )
    assert result.exit_code == 2  # Typer rejects the non-existent path argument.


def test_convene_no_personas_aborts_cleanly(tmp_path: Path) -> None:
    empty = tmp_path / "no_personas"
    empty.mkdir()
    result = runner.invoke(
        app,
        [
            "convene",
            str(PETITION_01),
            "--db",
            str(tmp_path / "db.sqlite"),
            "--out",
            str(tmp_path / "out"),
            "--personas",
            str(empty),
        ],
    )
    assert result.exit_code == 1
    assert "No persona files found" in result.stderr


def test_inspect_round_trips_after_convene(tmp_path: Path) -> None:
    out = tmp_path / "out"
    db = tmp_path / "sboard.db"
    conv = _convene(out, db, extra=["--no-show-memo"])
    assert conv.exit_code == 0, conv.output
    memo_id = _memo_id_from_out(out)

    result = runner.invoke(app, ["inspect", memo_id, "--db", str(db)])
    assert result.exit_code == 0, result.output

    # Memo header + the full transcript with its protocol states are shown.
    assert "Board Memo" in result.stdout
    assert "## Transcript" in result.stdout
    for state in ("CONVENE", "SEALED_OPENING", "CONFIDENCE_VOTE"):
        assert state in result.stdout


def test_inspect_unknown_memo_id_exits_1(tmp_path: Path) -> None:
    out = tmp_path / "out"
    db = tmp_path / "sboard.db"
    assert _convene(out, db).exit_code == 0

    result = runner.invoke(
        app, ["inspect", "00000000-0000-4000-8000-deadbeef0000", "--db", str(db)]
    )
    assert result.exit_code == 1
    assert "No memo found" in result.stderr


def test_inspect_missing_db_exits_1(tmp_path: Path) -> None:
    result = runner.invoke(app, ["inspect", "whatever", "--db", str(tmp_path / "absent.db")])
    assert result.exit_code == 1


def test_reconvene_same_petition_is_append_only(tmp_path: Path) -> None:
    """Re-convening the same petition must not raise an integrity error: the
    petition row is written once, transcripts and memos accumulate."""
    out = tmp_path / "out"
    db = tmp_path / "sboard.db"

    r1 = _convene(out, db, extra=["--no-show-memo"])
    r2 = _convene(out, db, extra=["--no-show-memo"])
    assert r1.exit_code == 0, r1.output
    assert r2.exit_code == 0, r2.output

    conn = sqlite3.connect(str(db))
    try:
        assert conn.execute("SELECT COUNT(*) FROM petitions").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM transcripts").fetchone()[0] == 2
        assert conn.execute("SELECT COUNT(*) FROM memos").fetchone()[0] == 2
    finally:
        conn.close()


def test_no_source_figure_names_in_user_output(tmp_path: Path) -> None:
    """IP constraint (HANDOFF §8): no source-figure name in any visible string —
    not in the convene memo, not in the inspect transcript."""
    out = tmp_path / "out"
    db = tmp_path / "sboard.db"

    conv = _convene(out, db)  # show_memo defaults to True
    assert conv.exit_code == 0, conv.output
    memo_id = _memo_id_from_out(out)
    insp = runner.invoke(app, ["inspect", memo_id, "--db", str(db)])
    assert insp.exit_code == 0, insp.output

    combined = conv.stdout + conv.stderr + insp.stdout + insp.stderr
    for name in FORBIDDEN_NAMES:
        assert name not in combined, f"source-figure token leaked into output: {name!r}"

    # The on-disk memo artifact is clean too.
    md_text = (out / f"{memo_id}.md").read_text()
    assert not any(name in md_text for name in FORBIDDEN_NAMES)


def test_convene_seed_is_deterministic(tmp_path: Path) -> None:
    """Same seed → identical verdict and signatures across runs."""
    out_a, out_b = tmp_path / "a", tmp_path / "b"
    ra = _convene(out_a, tmp_path / "a.db", extra=["--no-show-memo", "--seed", "7"])
    rb = _convene(out_b, tmp_path / "b.db", extra=["--no-show-memo", "--seed", "7"])
    assert ra.exit_code == 0 and rb.exit_code == 0

    ma = json.loads((out_a / f"{_memo_id_from_out(out_a)}.json").read_text())
    mb = json.loads((out_b / f"{_memo_id_from_out(out_b)}.json").read_text())
    assert ma["verdict"] == mb["verdict"]
    assert ma["confidence_weighted"] == mb["confidence_weighted"]
    assert ma["signatures"] == mb["signatures"]


@pytest.mark.parametrize("command", ["convene", "inspect", "ab"])
def test_commands_are_registered(command: str) -> None:
    result = runner.invoke(app, [command, "--help"])
    assert result.exit_code == 0
    assert command in result.stdout
