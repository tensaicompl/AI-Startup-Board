"""Task v2.4 — state machine wiring (v2 11-state graph, end to end).

Runs run_meeting_v2 on all three smoke petitions through the full 7-seat graph,
asserts a schema-valid MemoV2 with the five body sections (gtm present when not
kill, NULL when kill), checks the 7-seat anonymization has no peer-id leak in
pre-reveal prompts, and confirms the v1 CLI flow still works.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel
from typer.testing import CliRunner, Result

from sboard.chair.meeting_state import MeetingState
from sboard.chair.state_machine import run_meeting_v2
from sboard.cli import app
from sboard.schemas import MemoV2, Petition, Position
from sboard.seats.llm_client import AnthropicClient, LLMResponse, MockClient
from sboard.seats.persona_loader import Persona, load_all_personas

ROOT = Path(__file__).parent.parent.parent
PERSONAS_DIR = ROOT / "personas"
FIXTURES = ROOT / "tests" / "fixtures" / "petitions"
PETITION_01 = FIXTURES / "01-iso-compliance.json"
PETITION_02 = FIXTURES / "02-weak-petition.json"
PETITION_03 = FIXTURES / "03-ambiguous-petition.json"

V2_SEATS = (
    "operator-ceo",
    "devils-advocate",
    "outsider",
    "visionary",
    "technical",
    "growth-advisor",
    "marketing",
)
ELEVEN_STATES = {
    "CONVENE",
    "SEALED_OPENING",
    "ANONYMIZED_REVEAL",
    "IDENTIFIED_REBUTTAL",
    "IDEA_ANALYSIS",
    "DEVILS_ADVOCATE",
    "VISIONARY_PASS",
    "CONFIDENCE_VOTE",
    "FORCED_DISSENT_CHECK",
    "GTM_STAGE",
    "MEMO_SYNTHESIS",
}
PRE_REVEAL_STAGES = ("sealed_opening", "anonymized_review")

runner = CliRunner()


def _personas() -> dict[str, Persona]:
    return load_all_personas(PERSONAS_DIR, seat_ids=V2_SEATS)


def _petition(path: Path) -> Petition:
    return Petition.model_validate(json.loads(path.read_text()))


def _run_v2(path: Path, client: AnthropicClient) -> MeetingState:
    state = MeetingState(
        petition=_petition(path),
        personas=_personas(),
        seed=42,
        protocol_version="2.0.0",
    )
    return run_meeting_v2(state, client)


class KillVotingClient(MockClient):
    """A mock whose seats all vote kill — exercises the verdict==kill → no-GTM path."""

    def _generate_mock_output(self, stage: str, seat_id: str) -> dict[str, Any]:
        if stage == "vote":
            return {
                "seat_id": seat_id,
                "stage": "vote",
                "verdict": "kill",
                "confidence_raw": 0.8,
                "one_sentence_rationale": (
                    "This should not be funded; the risks dominate the upside decisively."
                ),
            }
        return super()._generate_mock_output(stage, seat_id)


@dataclass
class _Recorded:
    seat_id: str
    stage: str
    user_message: str


class SpyClient(AnthropicClient):
    """Records every call's user_message, then delegates to a real MockClient."""

    def __init__(self) -> None:
        self._delegate = MockClient()
        self.calls: list[_Recorded] = []

    def call(
        self,
        *,
        system_prompt: str,
        user_message: str,
        output_schema: type[BaseModel],
        seat_id: str,
        stage: str,
        model: str | None = None,
        max_tokens: int = 2000,
    ) -> LLMResponse:
        self.calls.append(_Recorded(seat_id=seat_id, stage=stage, user_message=user_message))
        return self._delegate.call(
            system_prompt=system_prompt,
            user_message=user_message,
            output_schema=output_schema,
            seat_id=seat_id,
            stage=stage,
            model=model,
            max_tokens=max_tokens,
        )

    def get_default_seat_model(self) -> str:
        return self._delegate.get_default_seat_model()

    def get_default_synthesis_model(self) -> str:
        return self._delegate.get_default_synthesis_model()


def _assert_full_v2_memo(memo: object) -> MemoV2:
    assert isinstance(memo, MemoV2)
    assert memo.schema_version == "2.0"
    for section in (memo.idea_analysis, memo.verdict_reasoning, memo.vision, memo.dissent_summary):
        assert len(section) >= 50
    assert len(memo.signatures) == 5  # five voting seats
    return memo


# --- end-to-end runs ---


def test_v2_end_to_end_petition_01_not_kill() -> None:
    final = _run_v2(PETITION_01, MockClient())
    memo = _assert_full_v2_memo(final.memo)
    assert memo.verdict != Position.KILL
    assert memo.gtm_analysis is not None  # GTM ran (not a kill)
    assert set(final.state_timings) >= ELEVEN_STATES  # all 11 states executed


def test_v2_end_to_end_petition_02_kill_drops_gtm() -> None:
    final = _run_v2(PETITION_02, KillVotingClient())
    memo = _assert_full_v2_memo(final.memo)
    assert memo.verdict == Position.KILL
    assert memo.gtm_analysis is None  # GTM skipped on a kill verdict
    assert "GTM_STAGE" not in final.state_timings  # the conditional edge skipped it


def test_v2_end_to_end_petition_03_not_kill() -> None:
    final = _run_v2(PETITION_03, MockClient())
    memo = _assert_full_v2_memo(final.memo)
    assert memo.verdict != Position.KILL
    assert memo.gtm_analysis is not None
    assert set(final.state_timings) >= ELEVEN_STATES


# --- 7-seat anonymization leak (the Task-6 test, now across 7 seats) ---


def test_no_peer_identity_leak_in_pre_reveal_prompts_7_seats() -> None:
    petition = _petition(PETITION_01)
    personas = _personas()
    state = MeetingState(
        petition=petition, personas=personas, seed=42, protocol_version="2.0.0"
    )
    spy = SpyClient()
    run_meeting_v2(state, spy)

    # The anonymization contract: pre-reveal, a seat learns no peer IDENTITY. The
    # chair attributes peers only by "Seat X" label (never by seat_id), and
    # anonymize_opening scrubs each peer's identity markers (redaction_aliases +
    # signature_phrases). So the sound checks are: (1) peer identity markers absent,
    # (2) peer COMPOUND seat_ids absent. Single-word seat_ids ("technical",
    # "marketing") are common words that legitimately occur in petition prose and
    # in opening content, so a bare-substring check on them is meaningless — their
    # identity is protected by their markers, which are checked. The petition (the
    # shared subject) is stripped before checking.
    shared = (petition.pitch, petition.context or "")

    for seat_id in personas:
        peer_compound_ids = {sid for sid in personas if sid != seat_id and "-" in sid}
        peer_markers: set[str] = set()
        for sid, p in personas.items():
            if sid != seat_id:
                peer_markers.update(p.voice.redaction_aliases)
                peer_markers.update(p.voice.signature_phrases)
        for call in spy.calls:
            if call.seat_id != seat_id or call.stage not in PRE_REVEAL_STAGES:
                continue
            cleaned = call.user_message
            for text in shared:
                cleaned = cleaned.replace(text, "")
            for peer in peer_compound_ids:
                assert peer not in cleaned, (
                    f"peer seat_id {peer!r} leaked into {call.stage} prompt for {seat_id}"
                )
            for marker in peer_markers:
                assert not re.search(rf"\b{re.escape(marker)}\b", cleaned, re.IGNORECASE), (
                    f"peer identity marker {marker!r} leaked into {call.stage} for {seat_id}"
                )


# --- v1 flow still works via the CLI ---


def test_v1_cli_flow_still_works(tmp_path: Path) -> None:
    out = tmp_path / "out"
    db = tmp_path / "sboard.db"
    result: Result = runner.invoke(
        app,
        [
            "convene",
            str(PETITION_01),
            "--protocol",
            "idea_screen_v1",
            "--personas",
            str(PERSONAS_DIR),
            "--db",
            str(db),
            "--out",
            str(out),
            "--no-show-memo",
        ],
    )
    assert result.exit_code == 0, result.output
    memo_path = next(out.glob("*.json"))
    data = json.loads(memo_path.read_text())
    # A v1 memo: no v2 discriminator, no v2 body, exactly 3 signatures, protocol 1.0.0.
    assert "schema_version" not in data
    assert "idea_analysis" not in data
    assert data["protocol_version"] == "1.0.0"
    assert len(data["signatures"]) == 3
