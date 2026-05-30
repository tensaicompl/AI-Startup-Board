"""Append-only SQLite persistence. No UPDATE. No DELETE. Ever."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from sboard.chair.meeting_state import TranscriptEntry
from sboard.schemas import Memo, MemoV2, Petition, parse_memo_json

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def _get_migration_sql() -> str:
    return (MIGRATIONS_DIR / "001_initial.sql").read_text()


def init_db(db_path: str | Path) -> sqlite3.Connection:
    """Create the database and run migrations."""
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(_get_migration_sql())
    return conn


def insert_petition(conn: sqlite3.Connection, petition: Petition) -> None:
    conn.execute(
        "INSERT INTO petitions (petition_id, submitted_at, meeting_type, data) "
        "VALUES (?, ?, ?, ?)",
        (
            str(petition.petition_id),
            petition.submitted_at.isoformat(),
            petition.meeting_type.value,
            petition.model_dump_json(),
        ),
    )
    conn.commit()


def insert_transcript(
    conn: sqlite3.Connection,
    petition_id: str,
    seed: int,
    transcript: list[TranscriptEntry],
) -> int:
    entries = [
        {
            "state": e.state,
            "seat_id": e.seat_id,
            "event": e.event,
            "data": e.data,
            "timestamp": e.timestamp,
        }
        for e in transcript
    ]
    cursor = conn.execute(
        "INSERT INTO transcripts (petition_id, meeting_seed, data) VALUES (?, ?, ?)",
        (petition_id, seed, json.dumps(entries)),
    )
    conn.commit()
    return cursor.lastrowid or 0


def insert_memo(conn: sqlite3.Connection, memo: Memo | MemoV2) -> None:
    conn.execute(
        "INSERT INTO memos (memo_id, petition_id, source, data) VALUES (?, ?, ?, ?)",
        (
            str(memo.memo_id),
            str(memo.petition_id),
            memo.source.value,
            memo.model_dump_json(),
        ),
    )
    conn.commit()


def get_petition(conn: sqlite3.Connection, petition_id: str) -> Petition | None:
    row = conn.execute(
        "SELECT data FROM petitions WHERE petition_id = ?", (petition_id,)
    ).fetchone()
    if row is None:
        return None
    return Petition.model_validate_json(row[0])


def get_transcript(
    conn: sqlite3.Connection, petition_id: str
) -> list[dict[str, Any]] | None:
    row = conn.execute(
        "SELECT data FROM transcripts WHERE petition_id = ? "
        "ORDER BY transcript_id DESC LIMIT 1",
        (petition_id,),
    ).fetchone()
    if row is None:
        return None
    return json.loads(row[0])  # type: ignore[no-any-return]


def get_memo(conn: sqlite3.Connection, memo_id: str) -> Memo | MemoV2 | None:
    row = conn.execute(
        "SELECT data FROM memos WHERE memo_id = ?", (memo_id,)
    ).fetchone()
    if row is None:
        return None
    return parse_memo_json(row[0])


def get_memo_by_petition(
    conn: sqlite3.Connection, petition_id: str
) -> Memo | MemoV2 | None:
    row = conn.execute(
        "SELECT data FROM memos WHERE petition_id = ? "
        "ORDER BY inserted_at DESC LIMIT 1",
        (petition_id,),
    ).fetchone()
    if row is None:
        return None
    return parse_memo_json(row[0])


def list_memos(conn: sqlite3.Connection) -> list[Memo | MemoV2]:
    rows = conn.execute("SELECT data FROM memos ORDER BY inserted_at").fetchall()
    return [parse_memo_json(r[0]) for r in rows]
