"""Anonymization: shuffle, relabel, redact."""

from __future__ import annotations

import random
import re
from typing import Any

from sboard.schemas import SealedOpening
from sboard.seats.persona_loader import Persona

LABELS = ["Seat A", "Seat B", "Seat C"]


def build_anonymization_map(
    seat_ids: list[str],
    seed: int,
) -> dict[str, str]:
    """Create a random mapping: seat_id -> anonymous label."""
    rng = random.Random(seed)
    labels = list(LABELS[: len(seat_ids)])
    rng.shuffle(labels)
    return dict(zip(seat_ids, labels, strict=True))


def reverse_map(anon_map: dict[str, str]) -> dict[str, str]:
    """label -> seat_id."""
    return {v: k for k, v in anon_map.items()}


def redact_text(text: str, redaction_terms: list[str]) -> str:
    """Replace redaction terms with [REDACTED] in text, using word boundaries."""
    result = text
    for term in sorted(redaction_terms, key=len, reverse=True):
        pattern = r"\b" + re.escape(term) + r"\b"
        result = re.sub(pattern, "[REDACTED]", result, flags=re.IGNORECASE)
    return result


def anonymize_opening(
    opening: SealedOpening,
    label: str,
    personas: dict[str, Persona],
) -> dict[str, Any]:
    """Produce an anonymized view of a sealed opening."""
    persona = personas[opening.seat_id]
    all_redaction_terms: list[str] = list(persona.voice.redaction_aliases)
    all_redaction_terms.extend(persona.voice.signature_phrases)

    return {
        "label": label,
        "position": opening.position.value,
        "one_paragraph_case": redact_text(opening.one_paragraph_case, all_redaction_terms),
        "top_three_reasons": [
            redact_text(r, all_redaction_terms) for r in opening.top_three_reasons
        ],
        "kill_criteria": [
            redact_text(k, all_redaction_terms) for k in opening.kill_criteria
        ],
    }
