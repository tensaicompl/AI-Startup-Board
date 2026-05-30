"""LLM client interface and mock implementation."""

from __future__ import annotations

import json
import os
from abc import ABC, abstractmethod
from typing import Any, cast

import anthropic
from pydantic import BaseModel


class LLMResponse:
    """Wrapper around an LLM call result."""

    __slots__ = ("content", "model", "input_tokens", "output_tokens")

    def __init__(
        self,
        content: str,
        model: str,
        input_tokens: int = 0,
        output_tokens: int = 0,
    ) -> None:
        self.content = content
        self.model = model
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens

    @property
    def cost_usd(self) -> float:
        if "opus" in self.model:
            return (self.input_tokens * 15 + self.output_tokens * 75) / 1_000_000
        if "sonnet" in self.model:
            return (self.input_tokens * 3 + self.output_tokens * 15) / 1_000_000
        return (self.input_tokens * 1 + self.output_tokens * 5) / 1_000_000


class AnthropicClient(ABC):
    """Interface for LLM calls. Swap mock for real at Task 10."""

    @abstractmethod
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
        ...

    @abstractmethod
    def get_default_seat_model(self) -> str:
        ...

    @abstractmethod
    def get_default_synthesis_model(self) -> str:
        ...


class MockClient(AnthropicClient):
    """Deterministic mock that returns schema-valid outputs keyed by seat_id and stage."""

    _SEALED_OPENING_DEFAULTS: dict[str, dict[str, Any]] = {
        "operator-ceo": {
            "position": "proceed",
            "one_paragraph_case": (
                "This is a well-structured opportunity with clear operational metrics. "
                "The founding team has domain expertise, the market is quantifiable, and "
                "the NIS2 regulatory tailwind creates urgency. The unit economics at the "
                "stated price point are credible for the target segment. The risk is "
                "execution speed against well-funded US incumbents."
            ),
            "top_three_reasons": [
                "Regulatory tailwind from NIS2 creates mandatory demand in the target segment",
                "Founding team combines technical depth with audit domain expertise",
                "Localized CEE focus creates defensible niche against US-centric competitors",
            ],
            "kill_criteria": [
                "If paid customer count is zero after six months of sales effort",
                "If CAC exceeds twelve hundred EUR per customer by month nine",
            ],
            "confidence_raw": 0.75,
        },
        "devils-advocate": {
            "position": "conditional",
            "one_paragraph_case": (
                "The regulatory angle is real but the moat is thin. Compliance automation "
                "is a category where US players can localize faster than a CEE startup can "
                "scale. The three pilot customers are unpaid which means the willingness to "
                "pay is unproven. The pre-seed raise at one and a half million EUR is tight "
                "for an enterprise sales cycle that takes six to nine months."
            ),
            "top_three_reasons": [
                "Willingness to pay is unproven with zero paid customers to date",
                "Enterprise sales cycles will consume runway faster than projected",
                "US competitors could localize to CEE markets within eighteen months",
            ],
            "kill_criteria": [
                "If no pilot converts to paid within ninety days of product launch",
                "If Drata or Vanta announces a CEE localization initiative",
            ],
            "confidence_raw": 0.70,
        },
        "outsider": {
            "position": "conditional",
            "one_paragraph_case": (
                "As someone who would be the target buyer I see the pain but I have been "
                "burned before. The pitch says it connects to existing systems but the "
                "integration list matters enormously. If it does not support my specific "
                "ITSM tool the product is useless. I need to see a reference customer in "
                "my country and my industry before I would sign."
            ),
            "top_three_reasons": [
                "Integration coverage determines whether this replaces or adds to my workload",
                "No paid customer reference means I would be the guinea pig and that is career risk",
                "The price in local currency needs to fit my actual budget not a US benchmark",
            ],
            "kill_criteria": [
                "If integration with the top three ITSM tools in CEE is not available at launch",
            ],
            "confidence_raw": 0.60,
        },
    }

    _REVIEW_DEFAULTS: dict[str, list[dict[str, str]]] = {
        "operator-ceo": [
            {
                "target_label": "Seat B",
                "agreement": "disagree",
                "one_sentence_reason": (
                    "The competitive moat concern is valid but underweights "
                    "the regulatory timing advantage."
                ),
            },
            {
                "target_label": "Seat C",
                "agreement": "agree",
                "one_sentence_reason": (
                    "The integration coverage point is operationally critical "
                    "and must be addressed before launch."
                ),
            },
        ],
        "devils-advocate": [
            {
                "target_label": "Seat A",
                "agreement": "undecided",
                "one_sentence_reason": (
                    "The regulatory tailwind is real but does not prove "
                    "that this team captures it."
                ),
            },
            {
                "target_label": "Seat C",
                "agreement": "agree",
                "one_sentence_reason": (
                    "The reference customer requirement is exactly the kind "
                    "of ground truth that separates pitches from businesses."
                ),
            },
        ],
        "outsider": [
            {
                "target_label": "Seat A",
                "agreement": "undecided",
                "one_sentence_reason": (
                    "The operational metrics focus is appreciated but does not "
                    "address the integration question."
                ),
            },
            {
                "target_label": "Seat B",
                "agreement": "agree",
                "one_sentence_reason": (
                    "The willingness to pay concern matches my experience "
                    "with enterprise pilots that never convert."
                ),
            },
        ],
    }

    def __init__(self) -> None:
        self._call_count = 0

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
        self._call_count += 1
        model_id = model or self.get_default_seat_model()
        data = self._generate_mock_output(stage, seat_id)

        return LLMResponse(
            content=json.dumps(data),
            model=model_id,
            input_tokens=500,
            output_tokens=300,
        )

    def get_default_seat_model(self) -> str:
        return os.environ.get("SBOARD_SEAT_MODEL", "claude-opus-4-7")

    def get_default_synthesis_model(self) -> str:
        return os.environ.get("SBOARD_SYNTHESIS_MODEL", "claude-sonnet-4-6")

    def _generate_mock_output(
        self, stage: str, seat_id: str
    ) -> dict[str, Any]:
        if stage == "sealed_opening":
            defaults = self._SEALED_OPENING_DEFAULTS.get(
                seat_id, self._SEALED_OPENING_DEFAULTS["operator-ceo"]
            )
            return {"seat_id": seat_id, "stage": "sealed_opening", **defaults}

        if stage == "anonymized_review":
            reviews = self._REVIEW_DEFAULTS.get(
                seat_id, self._REVIEW_DEFAULTS["operator-ceo"]
            )
            return {
                "seat_id": seat_id,
                "stage": "anonymized_review",
                "reviews": reviews,
            }

        if stage == "rebuttal":
            return {
                "seat_id": seat_id,
                "stage": "rebuttal",
                "position": "conditional",
                "position_changed": seat_id == "operator-ceo",
                "change_reason": (
                    "After reviewing peer critiques the integration risk warrants a conditional stance."
                    if seat_id == "operator-ceo"
                    else None
                ),
                "rebuttal_text": (
                    "The peer review surfaced legitimate concerns about integration "
                    "coverage and unproven willingness to pay. While the regulatory "
                    "tailwind is real the execution risk is higher than initially assessed."
                ),
            }

        if stage == "devils_advocate":
            return {
                "seat_id": seat_id,
                "stage": "devils_advocate",
                "majority_trend": "conditional",
                "steelman_against_majority": (
                    "The conditional verdict assumes the founding team can execute "
                    "against well-funded US competitors while simultaneously building "
                    "enterprise integrations and closing their first paid customers. "
                    "History suggests this is the hardest kind of multi-front war for "
                    "a three-person team with eighteen months of runway. The compliance "
                    "automation category is consolidating globally and the window for "
                    "regional players is closing not opening."
                ),
                "strongest_kill_condition": (
                    "If no pilot converts to a paid annual contract within the "
                    "first six months of general availability the unit economics "
                    "cannot sustain the enterprise sales cycle."
                ),
            }

        if stage == "vote":
            verdicts = {
                "operator-ceo": ("conditional", 0.72),
                "devils-advocate": ("conditional", 0.68),
                "outsider": ("conditional", 0.55),
            }
            verdict, conf = verdicts.get(seat_id, ("conditional", 0.60))
            return {
                "seat_id": seat_id,
                "stage": "vote",
                "verdict": verdict,
                "confidence_raw": conf,
                "one_sentence_rationale": (
                    "The opportunity is real but unproven and the team needs "
                    "to demonstrate paid conversion before scaling."
                ),
            }

        if stage == "forced_dissent":
            return {
                "seat_id": seat_id,
                "stage": "forced_dissent",
                "counter_verdict": "kill",
                "counter_case": (
                    "If we are honest about the competitive dynamics a three-person "
                    "team with no paid customers and eighteen months of runway is "
                    "entering a category where Drata just raised two hundred million "
                    "dollars. The regulatory tailwind helps everyone not just this "
                    "team. Regional localization is a feature not a company. The "
                    "strongest kill case is that this becomes a nice consulting "
                    "business that never achieves software economics."
                ),
                "would_change_mind_if": (
                    "If they close three paid annual contracts at the stated price "
                    "within ninety days of launch that would prove the moat is real."
                ),
            }

        if stage == "memo_synthesis":
            return self._generate_mock_memo()

        if stage == "baseline":
            return self._generate_mock_baseline()

        raise ValueError(f"Unknown stage: {stage}")

    def _generate_mock_memo(self) -> dict[str, Any]:
        return {
            "verdict_reasoning": (
                "The regulatory tailwind from NIS2 creates genuine demand in the "
                "target segment. The founding team has the right domain expertise. "
                "However the absence of any paid customer and the tight runway "
                "against a consolidating competitive field warrant a conditional "
                "verdict pending proof of commercial traction."
            ),
            "dissent_summary": (
                "The strongest case against proceeding is that compliance automation "
                "is a feature not a company. US incumbents can localize faster than "
                "this team can scale. The regional moat argument assumes competitors "
                "will not invest in CEE which is an assumption that breaks when the "
                "market proves valuable."
            ),
        }

    def _generate_mock_baseline(self) -> dict[str, Any]:
        """A plausible single-LLM memo. Deliberately a fair competitor — the gate
        is only honest if the baseline can win, so this is not weakened."""
        return {
            "verdict": "conditional",
            "verdict_reasoning": (
                "There is a real regulatory driver here and a credible team, and the "
                "CEE localization angle is a reasonable wedge against US incumbents. "
                "But with zero paid customers the willingness to pay is unproven, and "
                "an enterprise sales motion on eighteen months of runway is tight. On "
                "balance this is worth continuing only if commercial traction appears "
                "quickly, so the verdict is conditional rather than a clear proceed."
            ),
            "dissent_summary": (
                "The case for a clean proceed is that the regulatory deadline is a hard "
                "forcing function and the founder pairing of auditor plus engineer is "
                "well matched to the problem; waiting for paid proof may simply cede "
                "the timing advantage to faster-moving competitors."
            ),
            "kill_criteria": [
                {
                    "criterion": "No pilot converts to a paid annual contract within six months of launch.",
                    "owner_to_monitor": "Founder",
                },
                {
                    "criterion": "Blended CAC exceeds 1500 EUR per customer by month nine.",
                    "owner_to_monitor": "Founder",
                },
            ],
            "next_action": {
                "action": "Convert at least one pilot to a paid contract within 60 days.",
                "owner": "Founder",
                "deadline": "2026-07-31",
            },
            "confidence": 0.62,
        }


def _extract_tool_payload(raw: object, output_schema: type[BaseModel]) -> dict[str, Any]:
    """Recover the real tool arguments from `tool_use.input`.

    Models intermittently nest the arguments under a generic wrapper key
    (observed: 'parameter', '$PARAMETER_NAME') or add stray meta keys (observed:
    '$FUNCTION_NAME'), even under forced tool_choice. Match the schema's own
    field names to find the payload, then keep only schema fields (the models use
    extra='forbid', so dropping anything else is exactly right).
    """
    expected = set(output_schema.model_fields.keys())
    if not isinstance(raw, dict):
        return {}
    raw_dict = cast("dict[str, Any]", raw)

    if expected & raw_dict.keys():
        return {k: v for k, v in raw_dict.items() if k in expected}

    # No schema fields at the top level — look one level down for a wrapper.
    for value in raw_dict.values():
        if isinstance(value, dict) and expected & value.keys():
            return {k: v for k, v in value.items() if k in expected}
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
            except (json.JSONDecodeError, ValueError):
                continue
            if isinstance(parsed, dict) and expected & parsed.keys():
                return {k: v for k, v in parsed.items() if k in expected}

    return raw_dict  # give up; let downstream validation raise a clear error


class LiveAnthropicClient(AnthropicClient):
    """Real Anthropic client. Forces schema-valid structured output via tool-use.

    This is the first component that needs a live ANTHROPIC_API_KEY (Task 10).
    It is never exercised by the mock-based build tests; its control flow is
    covered by a test that patches `messages.create`.
    """

    def __init__(
        self,
        api_key: str | None = None,
        *,
        seat_model: str | None = None,
        synthesis_model: str | None = None,
    ) -> None:
        key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY is not set; it is required for live runs. "
                "Set it in the environment or pass api_key explicitly."
            )
        self._client = anthropic.Anthropic(api_key=key)
        self._seat_model = seat_model or os.environ.get("SBOARD_SEAT_MODEL", "claude-opus-4-7")
        self._synthesis_model = synthesis_model or os.environ.get(
            "SBOARD_SYNTHESIS_MODEL", "claude-sonnet-4-6"
        )

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
        model_id = model or self._seat_model
        tool = {
            "name": "emit_structured_output",
            "description": (
                "Return the result as a single structured object conforming exactly "
                "to the provided JSON schema. Put every field at the TOP LEVEL of the "
                "tool input — do not nest the fields under any wrapper key. Populate "
                "every required field."
            ),
            "input_schema": output_schema.model_json_schema(),
        }
        response = self._client.messages.create(
            model=model_id,
            max_tokens=max_tokens,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
            tools=[cast("Any", tool)],
            tool_choice={"type": "tool", "name": "emit_structured_output"},
        )

        raw_input: object = None
        found = False
        for block in response.content:
            if block.type == "tool_use":
                raw_input = block.input
                found = True
                break
        if not found:
            raise ValueError(
                f"No tool_use block in response (seat={seat_id}, stage={stage})"
            )

        payload = _extract_tool_payload(raw_input, output_schema)
        return LLMResponse(
            content=json.dumps(payload),
            model=response.model,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
        )

    def get_default_seat_model(self) -> str:
        return self._seat_model

    def get_default_synthesis_model(self) -> str:
        return self._synthesis_model
