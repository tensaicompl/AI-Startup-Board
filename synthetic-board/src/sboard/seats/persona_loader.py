"""Parse persona files: YAML frontmatter + Markdown body."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

import yaml


class GroundingType(str, Enum):
    NATAL_CHART = "natal_chart"
    SYNTHETIC = "synthetic"


class TimeHorizon(str, Enum):
    SHORT = "short"
    MEDIUM = "medium"
    LONG = "long"


class RiskAppetite(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class OptimizationTarget(str, Enum):
    GROWTH = "growth"
    MARGIN = "margin"
    DURABILITY = "durability"
    SPEED = "speed"
    LEARNING = "learning"
    QUALITY = "quality"


class EvidenceWeight(str, Enum):
    EMPIRICAL = "empirical"
    CONCEPTUAL = "conceptual"
    INTUITIVE = "intuitive"


class DecisionSpeed(str, Enum):
    SNAP = "snap"
    DELIBERATE = "deliberate"
    EXHAUSTIVE = "exhaustive"


class FailureResponse(str, Enum):
    PIVOT = "pivot"
    HARDEN = "harden"
    ESCALATE = "escalate"
    QUIT = "quit"


class PrimaryLens(str, Enum):
    OPERATIONS = "operations"
    STORY = "story"
    NUMBERS = "numbers"
    TECH = "tech"
    CUSTOMER = "customer"
    REGULATION = "regulation"


VALID_ROLES = frozenset({
    "Operator-CEO",
    "Visionary",
    "CFO",
    "CTO",
    "CMO",
    "Devil's Advocate",
    "Outsider",
})

VALID_SIGNS = frozenset({
    "aries", "taurus", "gemini", "cancer", "leo", "virgo",
    "libra", "scorpio", "sagittarius", "capricorn", "aquarius", "pisces",
})

VALID_MODALITIES = frozenset({"cardinal", "fixed", "mutable"})
VALID_RODDEN = frozenset({"AA", "A", "B", "C", "DD", "X"})

SEAT_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_-]{2,30}$")


@dataclass(frozen=True)
class Worldview:
    time_horizon: TimeHorizon
    risk_appetite: RiskAppetite
    optimization_target: OptimizationTarget
    evidence_weight: EvidenceWeight
    decision_speed: DecisionSpeed
    failure_response: FailureResponse
    primary_lens: PrimaryLens


@dataclass(frozen=True)
class Voice:
    sentence_length: str
    register: str
    forbidden_phrases: tuple[str, ...] = ()
    signature_phrases: tuple[str, ...] = ()
    redaction_aliases: tuple[str, ...] = ()


@dataclass(frozen=True)
class Protocol:
    recalibration_factor: float
    sealed_opening_max_words: int = 200
    rebuttal_max_words: int = 150


@dataclass(frozen=True)
class Provenance:
    built_by: str
    built_at: str
    reviewed_by: str
    reviewed_at: str
    file_version: str


@dataclass(frozen=True)
class Persona:
    seat_id: str
    role: str
    voting: bool
    voting_weight: float
    permanent: bool
    is_devils_advocate: bool
    grounding_type: GroundingType
    source_figure: str | None
    worldview: Worldview
    voice: Voice
    protocol: Protocol
    provenance: Provenance
    system_prompt: str
    file_hash: str
    must_produce: tuple[str, ...] = ()
    must_not: tuple[str, ...] = ()
    chart_signature: dict[str, Any] | None = None
    birth: dict[str, Any] | None = None


class PersonaValidationError(Exception):
    pass


def _split_frontmatter(raw: str) -> tuple[str, str]:
    """Split YAML frontmatter from Markdown body."""
    if not raw.startswith("---"):
        raise PersonaValidationError("Persona file must start with YAML frontmatter (---)")
    parts = raw.split("---", 2)
    if len(parts) < 3:
        raise PersonaValidationError("Persona file must have closing --- for frontmatter")
    yaml_str = parts[1]
    body = parts[2].strip()
    return yaml_str, body


def _validate_frontmatter(fm: dict[str, Any]) -> None:
    """Validate frontmatter against the persona schema."""
    required = [
        "seat_id", "role", "voting", "voting_weight", "permanent",
        "is_devils_advocate", "grounding", "worldview", "voice",
        "protocol", "provenance",
    ]
    for key in required:
        if key not in fm:
            raise PersonaValidationError(f"Missing required field: {key}")

    if not SEAT_ID_PATTERN.match(fm["seat_id"]):
        raise PersonaValidationError(
            f"seat_id '{fm['seat_id']}' must match pattern ^[a-z][a-z0-9_-]{{2,30}}$"
        )

    if fm["role"] not in VALID_ROLES:
        raise PersonaValidationError(f"Invalid role: {fm['role']}")

    if not isinstance(fm["voting"], bool):
        raise PersonaValidationError("voting must be boolean")

    vw = fm["voting_weight"]
    if not isinstance(vw, (int, float)) or vw < 0.5 or vw > 1.5:
        raise PersonaValidationError("voting_weight must be in [0.5, 1.5]")

    grounding = fm["grounding"]
    if grounding["type"] not in ("natal_chart", "synthetic"):
        raise PersonaValidationError(f"Invalid grounding type: {grounding['type']}")

    if grounding["type"] == "natal_chart":
        if "birth" not in grounding:
            raise PersonaValidationError("natal_chart grounding requires birth data")
        if "chart_signature" not in fm:
            raise PersonaValidationError("natal_chart grounding requires chart_signature")
        cs = fm["chart_signature"]
        for sign_field in ("sun", "moon"):
            if cs.get(sign_field) not in VALID_SIGNS:
                raise PersonaValidationError(f"Invalid {sign_field}: {cs.get(sign_field)}")
        if cs.get("ascendant") is not None and cs["ascendant"] not in VALID_SIGNS:
            raise PersonaValidationError(f"Invalid ascendant: {cs['ascendant']}")
        if cs.get("dominant_modality") not in VALID_MODALITIES:
            raise PersonaValidationError(
                f"Invalid dominant_modality: {cs.get('dominant_modality')}"
            )
        if cs.get("rodden_rating") is not None and cs["rodden_rating"] not in VALID_RODDEN:
            raise PersonaValidationError(f"Invalid rodden_rating: {cs['rodden_rating']}")

    wv = fm["worldview"]
    wv_required = [
        "time_horizon", "risk_appetite", "optimization_target",
        "evidence_weight", "decision_speed", "failure_response", "primary_lens",
    ]
    for key in wv_required:
        if key not in wv:
            raise PersonaValidationError(f"Missing worldview field: {key}")

    proto = fm["protocol"]
    if "recalibration_factor" not in proto:
        raise PersonaValidationError("protocol.recalibration_factor is required")
    rf = proto["recalibration_factor"]
    if not isinstance(rf, (int, float)) or rf < 0.5 or rf > 1.0:
        raise PersonaValidationError("recalibration_factor must be in [0.5, 1.0]")

    voice = fm["voice"]
    if "sentence_length" not in voice or "register" not in voice:
        raise PersonaValidationError("voice requires sentence_length and register")

    prov = fm["provenance"]
    prov_required = ["built_by", "built_at", "reviewed_by", "reviewed_at", "file_version"]
    for key in prov_required:
        if key not in prov:
            raise PersonaValidationError(f"Missing provenance field: {key}")


def load_persona(path: Path) -> Persona:
    """Load and validate a persona file."""
    raw = path.read_text(encoding="utf-8")
    file_hash = hashlib.sha256(raw.encode("utf-8")).hexdigest()

    yaml_str, body = _split_frontmatter(raw)
    fm = yaml.safe_load(yaml_str)
    if not isinstance(fm, dict):
        raise PersonaValidationError("Frontmatter must be a YAML mapping")

    _validate_frontmatter(fm)

    grounding = fm["grounding"]
    wv = fm["worldview"]
    voice = fm["voice"]
    proto = fm["protocol"]
    prov = fm["provenance"]

    return Persona(
        seat_id=fm["seat_id"],
        role=fm["role"],
        voting=fm["voting"],
        voting_weight=float(fm["voting_weight"]),
        permanent=fm["permanent"],
        is_devils_advocate=fm["is_devils_advocate"],
        grounding_type=GroundingType(grounding["type"]),
        source_figure=grounding.get("source_figure"),
        worldview=Worldview(
            time_horizon=TimeHorizon(wv["time_horizon"]),
            risk_appetite=RiskAppetite(wv["risk_appetite"]),
            optimization_target=OptimizationTarget(wv["optimization_target"]),
            evidence_weight=EvidenceWeight(wv["evidence_weight"]),
            decision_speed=DecisionSpeed(wv["decision_speed"]),
            failure_response=FailureResponse(wv["failure_response"]),
            primary_lens=PrimaryLens(wv["primary_lens"]),
        ),
        voice=Voice(
            sentence_length=voice["sentence_length"],
            register=voice["register"],
            forbidden_phrases=tuple(voice.get("forbidden_phrases", [])),
            signature_phrases=tuple(voice.get("signature_phrases", [])),
            redaction_aliases=tuple(voice.get("redaction_aliases", [])),
        ),
        protocol=Protocol(
            recalibration_factor=float(proto["recalibration_factor"]),
            sealed_opening_max_words=int(proto.get("sealed_opening_max_words", 200)),
            rebuttal_max_words=int(proto.get("rebuttal_max_words", 150)),
        ),
        provenance=Provenance(
            built_by=prov["built_by"],
            built_at=str(prov["built_at"]),
            reviewed_by=prov["reviewed_by"],
            reviewed_at=str(prov["reviewed_at"]),
            file_version=prov["file_version"],
        ),
        system_prompt=body,
        file_hash=file_hash,
        must_produce=tuple(fm.get("must_produce", [])),
        must_not=tuple(fm.get("must_not", [])),
        chart_signature=fm.get("chart_signature"),
        birth=grounding.get("birth"),
    )


def load_all_personas(directory: Path) -> dict[str, Persona]:
    """Load all persona .md files from a directory, keyed by seat_id."""
    personas: dict[str, Persona] = {}
    for path in sorted(directory.glob("*.md")):
        if path.name.startswith("_"):
            continue
        persona = load_persona(path)
        if persona.seat_id in personas:
            raise PersonaValidationError(f"Duplicate seat_id: {persona.seat_id}")
        personas[persona.seat_id] = persona
    return personas
