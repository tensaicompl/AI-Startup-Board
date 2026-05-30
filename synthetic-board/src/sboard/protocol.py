"""Protocol config loader — the single source of truth for seating and which graph.

A protocol YAML names its seats and version; the entry points read it to decide
who sits and whether to run the v1 (8-state) or v2 (11-state) graph. This replaces
the transitional V1_SEATS pin (removed at Task v2.4).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

DEFAULT_PROTOCOLS_DIR = Path("protocols")
DEFAULT_PROTOCOL_ID = "idea_screen_v2"  # v2 is the default cast (frozen scope)

# Accepted --protocol values mapped to their YAML file. "idea_screen_v1" is an
# alias for the v1 file (whose own protocol_id field is "idea_screen").
_PROTOCOL_FILES = {
    "idea_screen": "idea-screen.yaml",
    "idea_screen_v1": "idea-screen.yaml",
    "idea_screen_v2": "idea-screen-v2.yaml",
}


class ProtocolError(Exception):
    """Unknown protocol id or unreadable/invalid protocol file."""


@dataclass(frozen=True)
class ProtocolConfig:
    protocol_id: str            # the file's own protocol_id ("idea_screen" | "idea_screen_v2")
    protocol_version: str       # semver string, e.g. "2.0.0"
    seats: tuple[str, ...]      # the roster, in file order
    is_v2: bool                 # run the 11-state v2 graph + v2 memo if True


def load_protocol(
    protocol_id: str = DEFAULT_PROTOCOL_ID,
    protocols_dir: Path = DEFAULT_PROTOCOLS_DIR,
) -> ProtocolConfig:
    """Load a protocol's seating + version from its YAML file."""
    filename = _PROTOCOL_FILES.get(protocol_id)
    if filename is None:
        raise ProtocolError(
            f"Unknown protocol '{protocol_id}'. Known: {sorted(_PROTOCOL_FILES)}"
        )
    path = protocols_dir / filename
    if not path.exists():
        raise ProtocolError(f"Protocol file not found: {path}")

    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    file_id = str(data["protocol_id"])
    return ProtocolConfig(
        protocol_id=file_id,
        protocol_version=str(data["protocol_version"]),
        seats=tuple(data["seats"]),
        is_v2=file_id == "idea_screen_v2",
    )
