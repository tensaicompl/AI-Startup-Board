"""Seat runner: takes (persona, stage, message) -> structured output."""

from __future__ import annotations

import json
import logging
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from sboard.seats.llm_client import AnthropicClient, LLMResponse
from sboard.seats.persona_loader import Persona

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class SeatStatus:
    RESPONDED = "responded"
    ABSTAIN_TIMEOUT = "abstain_timeout"
    ABSTAIN_MALFORMED = "abstain_malformed"


class SeatResult:
    """Result of a seat call."""

    __slots__ = ("output", "status", "response", "error")

    def __init__(
        self,
        output: BaseModel | None,
        status: str,
        response: LLMResponse | None = None,
        error: str | None = None,
    ) -> None:
        self.output = output
        self.status = status
        self.response = response
        self.error = error


def run_seat(
    client: AnthropicClient,
    persona: Persona,
    stage: str,
    user_message: str,
    output_schema: type[T],
    model: str | None = None,
) -> SeatResult:
    """Call the LLM for a seat and return validated structured output.

    Retries once on malformed output, then marks seat as abstain_malformed.
    """
    model_id = model or client.get_default_seat_model()
    current_message = user_message

    for attempt in range(2):
        try:
            response = client.call(
                system_prompt=persona.system_prompt,
                user_message=current_message,
                output_schema=output_schema,
                seat_id=persona.seat_id,
                stage=stage,
                model=model_id,
            )
        except TimeoutError:
            return SeatResult(
                output=None,
                status=SeatStatus.ABSTAIN_TIMEOUT,
                error="Seat call timed out",
            )

        try:
            data = json.loads(response.content)
            # seat_id is the chair's to assign, not the model's: a real model
            # invents values like "devils_advocate" instead of "devils-advocate".
            # Force the canonical id before validation.
            if isinstance(data, dict) and "seat_id" in output_schema.model_fields:
                data["seat_id"] = persona.seat_id
            parsed = output_schema.model_validate(data)
            return SeatResult(
                output=parsed,
                status=SeatStatus.RESPONDED,
                response=response,
            )
        except (json.JSONDecodeError, ValidationError) as exc:
            if attempt == 0:
                logger.warning(
                    "Seat %s returned malformed output (attempt 1), retrying: %s",
                    persona.seat_id,
                    str(exc)[:200],
                )
                # Feed the exact failure back so the model corrects its own
                # formatting. Live models routinely overrun max_length on terse
                # fields (a 320-char rationale against a 300 cap); a blind retry
                # repeats the mistake, an informed one fixes it.
                current_message = (
                    f"{user_message}\n\n"
                    "Your previous response failed schema validation:\n"
                    f"{str(exc)[:600]}\n"
                    "Return a corrected response that satisfies EVERY field "
                    "constraint — especially maximum string lengths. Keep each "
                    "field comfortably within its limit."
                )
                continue
            return SeatResult(
                output=None,
                status=SeatStatus.ABSTAIN_MALFORMED,
                response=response,
                error=f"Malformed after retry: {exc!s}"[:500],
            )

    return SeatResult(
        output=None,
        status=SeatStatus.ABSTAIN_MALFORMED,
        error="Unexpected: exhausted retries",
    )
