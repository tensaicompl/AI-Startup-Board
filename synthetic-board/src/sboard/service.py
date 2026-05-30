"""Orchestration layer behind the CLI.

`convene` runs the Idea Screen protocol end-to-end, persists the audit trail to
SQLite (append-only), and writes the memo to disk. `load_inspection` recovers a
memo plus its petition and full transcript from the DB given only a memo_id.

This module does the wiring and file/DB I/O but contains no Typer/presentation
logic, so it is unit-testable without invoking the CLI. `cli.py` stays thin.

The chair is code, not an agent — this module only sequences deterministic steps;
it never asks a model for a procedural decision.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sboard.chair.meeting_state import MeetingState, ProtocolState
from sboard.chair.state_machine import run_meeting, run_meeting_v2
from sboard.db.store import (
    get_memo,
    get_petition,
    get_transcript,
    init_db,
    insert_memo,
    insert_petition,
    insert_transcript,
)
from sboard.memo.formatter import format_memo_markdown
from sboard.protocol import DEFAULT_PROTOCOL_ID, DEFAULT_PROTOCOLS_DIR, load_protocol
from sboard.schemas import Memo, MemoV2, Petition
from sboard.seats.llm_client import AnthropicClient, LiveAnthropicClient, MockClient
from sboard.seats.persona_loader import load_all_personas

# Defaults are cwd-relative so the documented `sboard convene tests/...` usage
# (run from the repo root, as in the Makefile) works out of the box. All three
# live under paths that .gitignore already excludes (runs/, out/, *.db).
DEFAULT_DB_PATH = Path("runs/sboard.db")
DEFAULT_OUT_DIR = Path("out")
DEFAULT_PERSONAS_DIR = Path("personas")
DEFAULT_SEED = 42

# Seating is now protocol-driven (Task v2.4): the roster comes from the protocol
# YAML (idea-screen.yaml = 3 seats, idea-screen-v2.yaml = 7), and the protocol
# selects the v1 (8-state) or v2 (11-state) graph. The transitional V1_SEATS pin
# is gone.


class ConveneError(Exception):
    """A meeting could not produce a memo (no personas, or the protocol aborted)."""


@dataclass(frozen=True)
class ConveneResult:
    memo: Memo | MemoV2
    memo_markdown: str
    memo_md_path: Path
    memo_json_path: Path
    db_path: Path
    transcript_entries: int


@dataclass(frozen=True)
class Inspection:
    memo: Memo | MemoV2
    petition: Petition | None
    transcript: list[dict[str, Any]]


def make_client(*, live: bool = False) -> AnthropicClient:
    """Construct the LLM client. Mock by default (keyless); live needs a key.

    `LiveAnthropicClient()` raises if ANTHROPIC_API_KEY is unset, so it is only
    constructed when explicitly requested.
    """
    return LiveAnthropicClient() if live else MockClient()


def load_petition(path: Path) -> Petition:
    """Read and validate a petition JSON file."""
    data = json.loads(path.read_text(encoding="utf-8"))
    return Petition.model_validate(data)


def _persist_audit_trail(
    db_path: Path,
    petition: Petition,
    state: MeetingState,
    memo: Memo | MemoV2 | None,
) -> None:
    """Append the meeting's records to the audit DB.

    Petitions are immutable: a petition_id is inserted at most once. Transcripts
    and memos accumulate, so re-convening the same petition is safe and additive
    rather than an integrity error.
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = init_db(db_path)
    try:
        pid = str(petition.petition_id)
        if get_petition(conn, pid) is None:
            insert_petition(conn, petition)
        insert_transcript(conn, pid, state.seed, state.transcript)
        if memo is not None:
            insert_memo(conn, memo)
    finally:
        conn.close()


def convene(
    petition_path: Path,
    *,
    protocol_id: str = DEFAULT_PROTOCOL_ID,
    personas_dir: Path = DEFAULT_PERSONAS_DIR,
    protocols_dir: Path = DEFAULT_PROTOCOLS_DIR,
    db_path: Path = DEFAULT_DB_PATH,
    out_dir: Path = DEFAULT_OUT_DIR,
    seed: int = DEFAULT_SEED,
    client: AnthropicClient | None = None,
) -> ConveneResult:
    """Run the protocol end-to-end, persist the audit trail, write the memo.

    Seating and graph come from the protocol (default v2). Defaults to the
    deterministic `MockClient`; `--live` injects the real client.
    """
    client = client or MockClient()

    config = load_protocol(protocol_id, protocols_dir)
    petition = load_petition(petition_path)
    all_personas = load_all_personas(personas_dir)
    if not all_personas:
        raise ConveneError(f"No persona files found in {personas_dir}")
    missing = [s for s in config.seats if s not in all_personas]
    if missing:
        raise ConveneError(
            f"Protocol {config.protocol_id} requires seats {missing} "
            f"not found in {personas_dir}"
        )
    # Seat the protocol roster, preserving directory order (keeps the seed stable).
    personas = {sid: p for sid, p in all_personas.items() if sid in config.seats}

    state = MeetingState(
        petition=petition,
        personas=personas,
        seed=seed,
        protocol_version=config.protocol_version,
    )
    final = run_meeting_v2(state, client) if config.is_v2 else run_meeting(state, client)

    if final.current_state == ProtocolState.ABORTED or final.memo is None:
        # Still persist petition + transcript: an aborted meeting is part of the
        # audit trail. There is no memo to write or inspect.
        _persist_audit_trail(db_path, petition, final, memo=None)
        raise ConveneError(final.error or "Meeting aborted before producing a memo")

    memo = final.memo
    _persist_audit_trail(db_path, petition, final, memo)

    out_dir.mkdir(parents=True, exist_ok=True)
    markdown = format_memo_markdown(memo)
    md_path = out_dir / f"{memo.memo_id}.md"
    json_path = out_dir / f"{memo.memo_id}.json"
    md_path.write_text(markdown, encoding="utf-8")
    json_path.write_text(memo.model_dump_json(indent=2), encoding="utf-8")

    return ConveneResult(
        memo=memo,
        memo_markdown=markdown,
        memo_md_path=md_path,
        memo_json_path=json_path,
        db_path=db_path,
        transcript_entries=len(final.transcript),
    )


def load_inspection(memo_id: str, *, db_path: Path = DEFAULT_DB_PATH) -> Inspection | None:
    """Recover a memo + its petition + full transcript from the audit DB.

    Returns None if the DB does not exist or the memo_id is unknown.
    """
    if not db_path.exists():
        return None
    conn = init_db(db_path)
    try:
        memo = get_memo(conn, memo_id)
        if memo is None:
            return None
        pid = str(memo.petition_id)
        petition = get_petition(conn, pid)
        transcript = get_transcript(conn, pid) or []
        return Inspection(memo=memo, petition=petition, transcript=transcript)
    finally:
        conn.close()


def render_transcript(transcript: list[dict[str, Any]]) -> str:
    """Render the full transcript as plain text. Role-keyed seat ids only —
    source-figure names never enter the transcript, so none leak here."""
    lines: list[str] = [f"## Transcript ({len(transcript)} entries)", ""]
    for i, entry in enumerate(transcript, 1):
        state = entry.get("state", "?")
        seat = entry.get("seat_id") or "—"
        event = entry.get("event", "?")
        lines.append(f"{i:>3}. [{state}] {event}  (seat: {seat})")
        data = entry.get("data") or {}
        if data:
            rendered = json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True)
            lines.extend(f"      {dl}" for dl in rendered.splitlines())
        lines.append("")
    return "\n".join(lines)


def render_memo(memo: Memo | MemoV2) -> str:
    """Render a memo to Markdown (role names only, never source-figure names)."""
    return format_memo_markdown(memo)


def render_inspection(inspection: Inspection) -> str:
    """Render a memo followed by its full transcript."""
    return "\n".join(
        [render_memo(inspection.memo), "", render_transcript(inspection.transcript)]
    )
