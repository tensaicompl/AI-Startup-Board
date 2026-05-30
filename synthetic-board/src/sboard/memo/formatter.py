"""Render a memo (v1 or v2) to Markdown for human reading.

Source-figure names never appear. Seats are referenced by role name only.
"""

from __future__ import annotations

from sboard.schemas import Memo, MemoV2

SEAT_ID_TO_ROLE: dict[str, str] = {
    "operator-ceo": "Operator-CEO",
    "devils-advocate": "Devil's Advocate",
    "outsider": "Outsider",
    "visionary": "Visionary",
    "technical": "CTO",
    "growth-advisor": "Growth Advisor",
    "marketing": "CMO",
}


def _role_name(seat_id: str) -> str:
    return SEAT_ID_TO_ROLE.get(seat_id, seat_id)


def _header(memo: Memo | MemoV2) -> list[str]:
    return [
        f"# Board Memo — {memo.verdict.value.upper()}",
        "",
        f"**Meeting type:** {memo.meeting_type.value}",
        f"**Protocol version:** {memo.protocol_version}",
        f"**Date:** {memo.created_at.strftime('%Y-%m-%d %H:%M UTC')}",
        f"**Source:** {memo.source.value}",
        "",
        "---",
        "",
        f"**Verdict: {memo.verdict.value.upper()}**",
        f"Confidence (weighted): {memo.confidence_weighted:.2f}",
        f"Confidence spread: {memo.confidence_spread:.2f}",
        "",
    ]


def _kill_next_signatures_metadata(memo: Memo | MemoV2) -> list[str]:
    lines: list[str] = ["## Kill Criteria", ""]
    for i, kc in enumerate(memo.kill_criteria, 1):
        lines.append(f"{i}. {kc.criterion}")
        lines.append(f"   *Owner:* {kc.owner_to_monitor}")
    lines.extend(
        [
            "",
            "## Next Action",
            "",
            f"**Action:** {memo.next_action.action}",
            f"**Owner:** {memo.next_action.owner}",
            f"**Deadline:** {memo.next_action.deadline.isoformat()}",
            "",
            "## Signatures",
            "",
            "| Role | Verdict | Confidence (raw) | Confidence (recalibrated) |",
            "|------|---------|-------------------|---------------------------|",
        ]
    )
    for sig in memo.signatures:
        lines.append(
            f"| {_role_name(sig.seat_id)} | {sig.verdict.value} "
            f"| {sig.confidence_raw:.2f} | {sig.confidence_recalibrated:.4f} |"
        )
    lines.extend(
        [
            "",
            "---",
            "",
            "*Metadata*",
            f"- Seed: {memo.metadata.seed}",
            f"- Wall clock: {memo.metadata.wall_clock_seconds:.1f}s",
            f"- LLM cost: ${memo.metadata.llm_cost_usd:.4f}",
            f"- Unanimous: {memo.metadata.unanimous}",
            f"- Forced dissent: {memo.metadata.forced_dissent_triggered}",
        ]
    )
    if memo.metadata.reasoning_overlap_score is not None:
        lines.append(f"- Reasoning overlap: {memo.metadata.reasoning_overlap_score:.4f}")
    lines.append("")
    return lines


def _format_v1(memo: Memo) -> str:
    lines = _header(memo)
    lines.extend(["## Verdict Reasoning", "", memo.verdict_reasoning, ""])
    lines.extend([f"## Dissent ({_role_name(memo.dissent_source)})", "", memo.dissent_summary, ""])
    lines.extend(_kill_next_signatures_metadata(memo))
    return "\n".join(lines)


def _section(heading: str, gloss: str, body: str) -> list[str]:
    """A body section with a heading, a one-line italic gloss for at-a-glance
    orientation, then the prose."""
    return [f"## {heading}", f"*{gloss}*", "", body, ""]


def _format_v2(memo: MemoV2) -> str:
    """The five-stage v2 body, rendered in order (idea → verdict → vision →
    dissent → gtm). Each section carries a one-line italic gloss so the rater can
    see the structure at a glance, and the GTM section's presence is explicit: a
    full section when the verdict allows it, an "n/a — kill verdict" header when a
    kill drops it."""
    lines = _header(memo)
    lines.extend(_section("Idea Analysis", "What the business actually is, beneath the pitch.", memo.idea_analysis))
    lines.extend(_section("Verdict Reasoning", "Why the call lands where it does.", memo.verdict_reasoning))
    lines.extend(_section("Vision", "The upside if it works.", memo.vision))
    lines.extend(
        _section(
            f"Dissent ({_role_name(memo.dissent_source)})",
            "The strongest case against the verdict.",
            memo.dissent_summary,
        )
    )
    if memo.gtm_analysis is not None:
        lines.extend(_section("GTM Analysis", "How it reaches the market.", memo.gtm_analysis))
    else:
        lines.extend(["## GTM Analysis (n/a — kill verdict)", ""])
    lines.extend(_kill_next_signatures_metadata(memo))
    return "\n".join(lines)


def format_memo_markdown(memo: Memo | MemoV2) -> str:
    """Render a v1 or v2 memo to Markdown. Uses role names, never figure names."""
    if isinstance(memo, MemoV2):
        return _format_v2(memo)
    return _format_v1(memo)
