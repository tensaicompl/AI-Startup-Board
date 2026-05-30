"""Task v2.5 — v2 memo synthesis (five-section body), IP guard, formatter polish.

Covers, end to end on the three smoke petitions with the deterministic MockClient:
  - the five-section body is produced and each section is within its word budget,
  - the combined body is within the 1,200-word cap,
  - the retry-once-then-fail discipline (patch the validator, not the prose —
    Decision 005) with the synthesis LLM call count staying at 1 on the happy path,
  - the rendered Markdown carries no source-figure token (the full 47-token guard),
  - the formatter renders five distinguishable sections and makes the GTM section's
    presence explicit ("## GTM Analysis" vs "## GTM Analysis (n/a — kill verdict)").
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel

from sboard.chair.meeting_state import MeetingState
from sboard.chair.state_machine import run_meeting_v2
from sboard.memo.formatter import format_memo_markdown
from sboard.memo.ip_safety import FORBIDDEN_TOKENS, find_forbidden_tokens
from sboard.memo.synthesizer import (
    MEMO_V2_COMBINED_WORD_LIMIT,
    MEMO_V2_SECTION_WORD_LIMITS,
    MemoSynthesisError,
    _count_words,
)
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


def _personas() -> dict[str, Persona]:
    return load_all_personas(PERSONAS_DIR, seat_ids=V2_SEATS)


def _petition(path: Path) -> Petition:
    return Petition.model_validate(json.loads(path.read_text()))


def _run_v2(path: Path, client: AnthropicClient) -> MeetingState:
    state = MeetingState(
        petition=_petition(path), personas=_personas(), seed=42, protocol_version="2.0.0"
    )
    return run_meeting_v2(state, client)


class _SynthesisCountingClient(AnthropicClient):
    """Wraps MockClient and counts calls by stage (to assert call discipline)."""

    def __init__(self, delegate: AnthropicClient | None = None) -> None:
        self._delegate = delegate or MockClient()
        self.stage_counts: dict[str, int] = {}

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
        self.stage_counts[stage] = self.stage_counts.get(stage, 0) + 1
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


class _KillVotingClient(MockClient):
    """A mock whose seats all vote kill — drives the verdict==kill → no-GTM path."""

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


# --- the 47-token guard -----------------------------------------------------


def test_forbidden_list_is_the_full_47() -> None:
    assert len(FORBIDDEN_TOKENS) == 47
    assert len(set(FORBIDDEN_TOKENS)) == 47  # no duplicates
    # v1's 11 stay in the list.
    for v1_token in ("Welch", "Buffett", "General Electric", "GE", "Hathaway"):
        assert v1_token in FORBIDDEN_TOKENS
    # the four new figures are represented.
    for v2_token in ("Jobs", "Torvalds", "Bezos", "Ogilvy"):
        assert v2_token in FORBIDDEN_TOKENS


def test_scanner_is_word_boundary_and_does_not_repeat_the_ge_mistake() -> None:
    # "GE" must not match inside "GTM_STAGE"; "Git" must not match "digit".
    assert find_forbidden_tokens("The GTM_STAGE ran; a 12-digit code.") == []
    # whole-word hits are caught, in list order.
    hits = find_forbidden_tokens("A memo about Bezos and Welch and Linux.")
    assert hits == ["Welch", "Linux", "Bezos"]


# --- word budgets (against real mock output) --------------------------------


@pytest.mark.parametrize("path", [PETITION_01, PETITION_03])
def test_v2_sections_within_per_section_and_combined_budgets(path: Path) -> None:
    memo = _run_v2(path, MockClient()).memo
    assert isinstance(memo, MemoV2)

    counts = {
        field: _count_words(getattr(memo, field))
        for field in MEMO_V2_SECTION_WORD_LIMITS
        if getattr(memo, field) is not None
    }
    for field, wc in counts.items():
        assert wc <= MEMO_V2_SECTION_WORD_LIMITS[field], (
            f"{field} is {wc} words, exceeds {MEMO_V2_SECTION_WORD_LIMITS[field]}"
        )
    assert sum(counts.values()) <= MEMO_V2_COMBINED_WORD_LIMIT


def test_v2_synthesis_call_count_is_one_on_happy_path() -> None:
    client = _SynthesisCountingClient()
    _run_v2(PETITION_01, client)
    assert client.stage_counts.get("memo_synthesis_v2", 0) == 1


# --- retry path (patch the validator, not the prose — Decision 005) ---------
# The five present sections each route through _count_words once per attempt, so a
# non-kill petition makes 5 calls per attempt.


def test_v2_synthesis_retries_once_then_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    original = _count_words
    n = 0

    def _rigged(text: str) -> int:
        nonlocal n
        n += 1
        return 999 if n <= 5 else original(text)  # over-budget for the first attempt only

    monkeypatch.setattr("sboard.memo.synthesizer._count_words", _rigged)
    client = _SynthesisCountingClient()
    result = _run_v2(PETITION_01, client)
    assert isinstance(result.memo, MemoV2)
    assert client.stage_counts.get("memo_synthesis_v2") == 2


def test_v2_synthesis_hard_fails_after_two_over_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sboard.memo.synthesizer._count_words", lambda text: 999)
    client = _SynthesisCountingClient()
    with pytest.raises(MemoSynthesisError, match="1200"):
        _run_v2(PETITION_01, client)
    assert client.stage_counts.get("memo_synthesis_v2") == 2


# --- end-to-end: five sections, IP-clean Markdown, GTM presence -------------


@pytest.mark.parametrize("path", [PETITION_01, PETITION_03])
def test_v2_end_to_end_full_memo_markdown_is_ip_clean(path: Path) -> None:
    memo = _run_v2(path, MockClient()).memo
    assert isinstance(memo, MemoV2)
    assert memo.verdict != Position.KILL
    assert memo.gtm_analysis is not None

    md = format_memo_markdown(memo)
    # All five sections present and in order.
    for heading in ("## Idea Analysis", "## Verdict Reasoning", "## Vision", "## Dissent", "## GTM Analysis"):
        assert heading in md
    assert "(n/a — kill verdict)" not in md
    # The full 47-token guard finds nothing in the rendered Markdown.
    assert find_forbidden_tokens(md) == []


def test_v2_kill_drops_gtm_and_markdown_marks_it_na() -> None:
    final = _run_v2(PETITION_02, _KillVotingClient())
    memo = final.memo
    assert isinstance(memo, MemoV2)
    assert memo.verdict == Position.KILL
    assert memo.gtm_analysis is None

    md = format_memo_markdown(memo)
    assert "## GTM Analysis (n/a — kill verdict)" in md
    assert "## How it reaches the market." not in md  # the present-GTM gloss is absent
    assert find_forbidden_tokens(md) == []


def test_v2_section_glosses_orient_the_reader() -> None:
    """Each body section carries a one-line italic gloss (visual hierarchy)."""
    memo = _run_v2(PETITION_01, MockClient()).memo
    assert isinstance(memo, MemoV2)
    md = format_memo_markdown(memo)
    for gloss in (
        "*What the business actually is, beneath the pitch.*",
        "*Why the call lands where it does.*",
        "*The upside if it works.*",
        "*The strongest case against the verdict.*",
        "*How it reaches the market.*",
    ):
        assert gloss in md
