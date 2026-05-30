"""Task v2.1 — v2 memo schema + protocol version bump.

Round-trips both memo versions through Pydantic, validates each against its JSON
Schema file, exercises the gtm/kill conditional, the version dispatcher, and the
new 11-state protocol YAML. v1 must stay green (see test_schemas.py).
"""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest
import yaml

from sboard.schemas import Memo, MemoV2, Position, parse_memo, parse_memo_json

ROOT = Path(__file__).parent.parent.parent
SCHEMAS_DIR = ROOT / "schemas"
PROTOCOLS_DIR = ROOT / "protocols"


# --- shared fixtures ---


def _kill_criteria() -> list[dict[str, str]]:
    return [
        {
            "criterion": "If no pilot converts to paid within ninety days of launch.",
            "owner_to_monitor": "Founder",
        }
    ]


def _next_action() -> dict[str, str]:
    return {
        "action": "Validate the top kill criterion within 30 days.",
        "owner": "Founder",
        "deadline": "2026-07-01",
    }


def _signatures() -> list[dict[str, object]]:
    return [
        {
            "seat_id": "operator-ceo",
            "verdict": "conditional",
            "confidence_raw": 0.7,
            "confidence_recalibrated": 0.6,
        }
    ]


def _metadata() -> dict[str, object]:
    return {
        "persona_hashes": {"operator-ceo": "abc123"},
        "model_ids": {"seats": "claude-opus-4-7", "synthesis": "claude-sonnet-4-6"},
        "seed": 42,
        "wall_clock_seconds": 1.0,
        "llm_cost_usd": 0.5,
        "unanimous": False,
        "forced_dissent_triggered": False,
    }


def _v2_memo_dict(verdict: str = "conditional", with_gtm: bool = True) -> dict[str, object]:
    d: dict[str, object] = {
        "schema_version": "2.0",
        "memo_id": "11111111-1111-4111-8111-111111111111",
        "petition_id": "00000000-0000-4000-8000-000000000001",
        "meeting_type": "idea_screen",
        "protocol_version": "2.0.0",
        "created_at": "2026-05-30T10:00:00Z",
        "source": "board",
        "verdict": verdict,
        "confidence_weighted": 3.2,
        "confidence_spread": 0.5,
        "idea_analysis": "I" * 120,
        "verdict_reasoning": "V" * 120,
        "vision": "S" * 120,
        "dissent_summary": "D" * 120,
        "dissent_source": "outsider",
        "kill_criteria": _kill_criteria(),
        "next_action": _next_action(),
        "signatures": _signatures(),
        "metadata": _metadata(),
    }
    if with_gtm:
        d["gtm_analysis"] = "G" * 120
    return d


def _v1_memo_dict() -> dict[str, object]:
    return {
        "memo_id": "22222222-2222-4222-8222-222222222222",
        "petition_id": "00000000-0000-4000-8000-000000000001",
        "meeting_type": "idea_screen",
        "protocol_version": "1.0.0",
        "created_at": "2026-05-30T10:00:00Z",
        "source": "board",
        "verdict": "conditional",
        "confidence_weighted": 1.6,
        "confidence_spread": 0.4,
        "verdict_reasoning": "V" * 120,
        "dissent_summary": "D" * 120,
        "dissent_source": "outsider",
        "kill_criteria": _kill_criteria(),
        "next_action": _next_action(),
        "signatures": _signatures(),
        "metadata": _metadata(),
    }


def _load_schema(name: str) -> dict[str, object]:
    return json.loads((SCHEMAS_DIR / name).read_text())  # type: ignore[no-any-return]


# --- Pydantic round-trips ---


def test_memo_v2_roundtrip() -> None:
    m = MemoV2.model_validate(_v2_memo_dict())
    assert m.schema_version == "2.0"
    assert m.gtm_analysis is not None
    dumped = json.loads(m.model_dump_json())
    assert MemoV2.model_validate(dumped) == m


def test_memo_v2_kill_omits_gtm() -> None:
    m = MemoV2.model_validate(_v2_memo_dict(verdict="kill", with_gtm=False))
    assert m.verdict == Position.KILL
    assert m.gtm_analysis is None
    # round-trips even though pydantic dumps gtm_analysis: null
    assert MemoV2.model_validate(json.loads(m.model_dump_json())) == m


def test_memo_v2_kill_with_gtm_rejected() -> None:
    with pytest.raises(ValueError):
        MemoV2.model_validate(_v2_memo_dict(verdict="kill", with_gtm=True))


def test_memo_v2_nonkill_requires_gtm() -> None:
    with pytest.raises(ValueError):
        MemoV2.model_validate(_v2_memo_dict(verdict="conditional", with_gtm=False))


# --- version dispatcher ---


def test_parse_memo_dispatches_by_version() -> None:
    assert isinstance(parse_memo(_v2_memo_dict()), MemoV2)
    assert isinstance(parse_memo(_v1_memo_dict()), Memo)
    # v2 detectable even without the explicit tag (idea_analysis is v2-only)
    v2_no_tag = _v2_memo_dict()
    del v2_no_tag["schema_version"]
    assert isinstance(parse_memo(v2_no_tag), MemoV2)
    # json entry point
    assert isinstance(parse_memo_json(json.dumps(_v2_memo_dict())), MemoV2)
    assert isinstance(parse_memo_json(json.dumps(_v1_memo_dict())), Memo)


# --- JSON Schema files ---


def test_default_schema_is_v2_and_v1_preserved() -> None:
    assert _load_schema("memo.schema.json")["title"] == "BoardMemoV2"
    assert _load_schema("memo-v1.schema.json")["title"] == "BoardMemo"


def test_v2_memo_validates_against_default_schema() -> None:
    jsonschema.validate(_v2_memo_dict(), _load_schema("memo.schema.json"))


def test_v1_memo_validates_against_v1_schema() -> None:
    jsonschema.validate(_v1_memo_dict(), _load_schema("memo-v1.schema.json"))


def test_pydantic_v2_dump_conforms_to_json_schema() -> None:
    schema = _load_schema("memo.schema.json")
    for verdict, gtm in (("conditional", True), ("kill", False)):
        m = MemoV2.model_validate(_v2_memo_dict(verdict=verdict, with_gtm=gtm))
        jsonschema.validate(json.loads(m.model_dump_json()), schema)


def test_v2_schema_rejects_kill_with_gtm() -> None:
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(
            _v2_memo_dict(verdict="kill", with_gtm=True), _load_schema("memo.schema.json")
        )


def test_v2_schema_requires_gtm_when_not_kill() -> None:
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(
            _v2_memo_dict(verdict="conditional", with_gtm=False),
            _load_schema("memo.schema.json"),
        )


def test_v1_memo_rejected_by_v2_schema() -> None:
    # A v1 memo lacks the v2 body fields → invalid under the v2 default schema.
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(_v1_memo_dict(), _load_schema("memo.schema.json"))


# --- v2 protocol YAML ---


def test_protocol_v2_has_eleven_states() -> None:
    proto = yaml.safe_load((PROTOCOLS_DIR / "idea-screen-v2.yaml").read_text())
    assert proto["protocol_id"] == "idea_screen_v2"
    assert proto["protocol_version"] == "2.0.0"
    assert len(proto["states"]) == 11
    assert len(proto["seats"]) == 7
    assert len(proto["voting_seats"]) == 5
    for new_state in ("IDEA_ANALYSIS", "VISIONARY_PASS", "GTM_STAGE"):
        assert new_state in proto["states"]
    assert proto["memo"]["body_max_words"] == 1200
    assert proto["cost"]["soft_cap_usd"] == 12.0
    assert proto["cost"]["hard_cap_usd"] == 40.0


def test_v1_protocol_still_present() -> None:
    proto = yaml.safe_load((PROTOCOLS_DIR / "idea-screen.yaml").read_text())
    assert proto["protocol_version"] == "1.0.0"
    assert len(proto["states"]) == 8
