"""Canonical source-figure token list and a word-boundary scanner (HANDOFF §8).

No source-figure name may surface in any user-visible string. This module is the
single source of truth for the forbidden tokens across every charted/aliased
figure, and the scanner the memo path uses to assert a rendered memo is clean.

Matching is word-boundary and case-sensitive — consistent with the existing IP
tests — so "GE" (General Electric) does not false-positive on a protocol state
like "GTM_STAGE", and "Git" does not match "digit".
"""

from __future__ import annotations

import re

# v1 figures (J.F. "Jack" Welch — General Electric; Warren Buffett — Berkshire
# Hathaway) plus the Outsider's synthetic alias. The original 11 — these stay.
_V1_TOKENS: tuple[str, ...] = (
    "Welch",
    "Buffett",
    "Jack",
    "Warren",
    "Marek",
    "Berkshire",
    "General Electric",
    "GE",
    "Peabody",
    "Omaha",
    "Hathaway",
)

# v2 figures added in Task v2.2 (Decision 008): Jobs, Torvalds, Bezos, Ogilvy.
# 36 tokens — names, companies, products, and birthplaces.
_V2_TOKENS: tuple[str, ...] = (
    # Jobs (12)
    "Jobs",
    "Steve",
    "Apple",
    "NeXT",
    "Pixar",
    "iPod",
    "iPhone",
    "Mac",
    "Wozniak",
    "Sculley",
    "Reed College",
    "Cupertino",
    # Torvalds (8)
    "Torvalds",
    "Linus",
    "Linux",
    "Git",
    "Helsinki",
    "Finland",
    "Transmeta",
    "kernel",
    # Bezos (10)
    "Bezos",
    "Jeff",
    "Amazon",
    "AWS",
    "Blue Origin",
    "Washington Post",
    "Princeton",
    "D.E. Shaw",
    "Seattle",
    "Albuquerque",
    # Ogilvy (6)
    "Ogilvy",
    "David",
    "Mather",
    "Aga Khan",
    "Touffou",
    "Confessions",
)

# The full guard: 11 (v1) + 36 (v2) = 47 tokens.
FORBIDDEN_TOKENS: tuple[str, ...] = _V1_TOKENS + _V2_TOKENS

# "David" and "Jeff" are bare first names — weak guards on their own, since the IP
# risk is the *association* with the figure, which needs the surname. The v2.5 spec
# anticipated narrowing them to "David Ogilvy" / "Jeff Bezos" IF they false-positive
# against real content. They do not against the (synthesized, IP-neutral) memo body
# the scanner runs on, so they stay as listed; narrowing would be Decision 013.
# See docs/decisions/013-v2-synthesis-budgets-and-ip.md.

_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (token, re.compile(rf"\b{re.escape(token)}\b")) for token in FORBIDDEN_TOKENS
)


def find_forbidden_tokens(text: str) -> list[str]:
    """Return every forbidden token that appears in `text` as a whole word.

    Order follows FORBIDDEN_TOKENS; a token is reported at most once.
    """
    return [token for token, pattern in _PATTERNS if pattern.search(text)]
