"""Tests for SQLite append-only persistence (Task 8)."""

from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path

import pytest

from sboard.chair.meeting_state import MeetingState
from sboard.chair.state_machine import run_meeting
from sboard.db.store import (
    get_memo,
    get_memo_by_petition,
    get_petition,
    get_transcript,
    init_db,
    insert_memo,
    insert_petition,
    insert_transcript,
)
from sboard.schemas import Memo, Petition
from sboard.seats.llm_client import MockClient
from sboard.seats.persona_loader import Persona, load_all_personas


PERSONAS_DIR = Path(__file__).parent.parent.parent / "personas"
FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "petitions"
DB_MODULE_DIR = Path(__file__).parent.parent.parent / "src" / "sboard" / "db"


@pytest.fixture()
def personas() -> dict[str, Persona]:
    return load_all_personas(PERSONAS_DIR)


@pytest.fixture()
def petition_01() -> Petition:
    data = json.loads((FIXTURES_DIR / "01-iso-compliance.json").read_text())
    return Petition.model_validate(data)


@pytest.fixture()
def db(tmp_path: Path) -> sqlite3.Connection:
    return init_db(tmp_path / "test.db")


@pytest.fixture()
def completed_meeting(
    petition_01: Petition, personas: dict[str, Persona]
) -> MeetingState:
    state = MeetingState(petition=petition_01, personas=personas, seed=42)
    return run_meeting(state, MockClient())


def test_tables_created(db: sqlite3.Connection) -> None:
    tables = {
        row[0]
        for row in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert {"petitions", "transcripts", "memos"}.issubset(tables)


def test_indexes_created(db: sqlite3.Connection) -> None:
    indexes = {
        row[0]
        for row in db.execute(
            "SELECT name FROM sqlite_master WHERE type='index'"
        ).fetchall()
    }
    assert "idx_transcripts_petition_id" in indexes
    assert "idx_memos_petition_id" in indexes


def test_insert_and_get_petition(db: sqlite3.Connection, petition_01: Petition) -> None:
    insert_petition(db, petition_01)
    loaded = get_petition(db, str(petition_01.petition_id))
    assert loaded is not None
    assert loaded.petition_id == petition_01.petition_id
    assert loaded.pitch == petition_01.pitch


def test_insert_and_get_memo(
    db: sqlite3.Connection, completed_meeting: MeetingState, petition_01: Petition
) -> None:
    insert_petition(db, petition_01)
    memo = completed_meeting.memo
    assert memo is not None
    insert_memo(db, memo)
    loaded = get_memo(db, str(memo.memo_id))
    assert loaded is not None
    assert loaded.memo_id == memo.memo_id
    assert loaded.verdict == memo.verdict
    assert loaded.signatures == memo.signatures


def test_insert_and_get_transcript(
    db: sqlite3.Connection, completed_meeting: MeetingState, petition_01: Petition
) -> None:
    insert_petition(db, petition_01)
    pid = str(completed_meeting.petition.petition_id)
    insert_transcript(
        db, pid, completed_meeting.seed, completed_meeting.transcript
    )
    loaded = get_transcript(db, pid)
    assert loaded is not None
    assert len(loaded) == len(completed_meeting.transcript)
    assert loaded[0]["event"] == completed_meeting.transcript[0].event


def test_audit_trail_reconstructable(
    db: sqlite3.Connection,
    completed_meeting: MeetingState,
    petition_01: Petition,
) -> None:
    """Given a memo_id, reconstruct the full meeting from DB alone:
    petition + transcript + memo, all fields intact, round-trip through Pydantic."""
    memo = completed_meeting.memo
    assert memo is not None

    insert_petition(db, petition_01)
    insert_transcript(
        db,
        str(petition_01.petition_id),
        completed_meeting.seed,
        completed_meeting.transcript,
    )
    insert_memo(db, memo)

    recovered_memo = get_memo(db, str(memo.memo_id))
    assert recovered_memo is not None

    recovered_petition = get_petition(db, str(recovered_memo.petition_id))
    assert recovered_petition is not None
    assert recovered_petition.petition_id == petition_01.petition_id
    assert recovered_petition.pitch == petition_01.pitch
    assert recovered_petition.meeting_type == petition_01.meeting_type

    recovered_transcript = get_transcript(db, str(recovered_memo.petition_id))
    assert recovered_transcript is not None
    assert len(recovered_transcript) > 0

    states_in_transcript = {e["state"] for e in recovered_transcript}
    assert "CONVENE" in states_in_transcript
    assert "SEALED_OPENING" in states_in_transcript
    assert "CONFIDENCE_VOTE" in states_in_transcript

    convene_entry = next(e for e in recovered_transcript if e["event"] == "convene")
    assert "persona_hashes" in convene_entry["data"]
    assert "seed" in convene_entry["data"]
    assert convene_entry["data"]["seed"] == 42

    assert recovered_memo.verdict == memo.verdict
    assert recovered_memo.confidence_weighted == memo.confidence_weighted
    assert recovered_memo.confidence_spread == memo.confidence_spread
    assert recovered_memo.dissent_summary == memo.dissent_summary
    assert recovered_memo.kill_criteria == memo.kill_criteria
    assert recovered_memo.signatures == memo.signatures
    assert recovered_memo.metadata.seed == memo.metadata.seed
    assert recovered_memo.metadata.unanimous == memo.metadata.unanimous
    assert recovered_memo.metadata.forced_dissent_triggered == memo.metadata.forced_dissent_triggered


def test_no_update_or_delete_in_db_module() -> None:
    """Grep the db module for UPDATE/DELETE SQL keywords. Assert zero matches
    outside comments. This enforces the append-only discipline mechanically."""
    violations: list[str] = []

    for py_file in DB_MODULE_DIR.rglob("*.py"):
        for i, line in enumerate(py_file.read_text().splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            upper = stripped.upper()
            if "UPDATE " in upper or "DELETE " in upper:
                violations.append(f"{py_file.name}:{i}: {stripped}")

    for sql_file in DB_MODULE_DIR.rglob("*.sql"):
        for i, line in enumerate(sql_file.read_text().splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("--"):
                continue
            upper = stripped.upper()
            if re.search(r"\bUPDATE\b", upper) or re.search(r"\bDELETE\b", upper):
                violations.append(f"{sql_file.name}:{i}: {stripped}")

    assert violations == [], (
        "UPDATE or DELETE found in db module:\n" + "\n".join(violations)
    )


def test_duplicate_petition_rejected(
    db: sqlite3.Connection, petition_01: Petition
) -> None:
    insert_petition(db, petition_01)
    with pytest.raises(sqlite3.IntegrityError):
        insert_petition(db, petition_01)


def test_duplicate_memo_rejected(
    db: sqlite3.Connection, completed_meeting: MeetingState, petition_01: Petition
) -> None:
    insert_petition(db, petition_01)
    memo = completed_meeting.memo
    assert memo is not None
    insert_memo(db, memo)
    with pytest.raises(sqlite3.IntegrityError):
        insert_memo(db, memo)


def test_get_nonexistent_returns_none(db: sqlite3.Connection) -> None:
    assert get_petition(db, "nonexistent") is None
    assert get_memo(db, "nonexistent") is None
    assert get_transcript(db, "nonexistent") is None
