"""Render a Memo to Markdown for human reading.

Source-figure names never appear. Seats are referenced by role name only.
"""

from __future__ import annotations

from sboard.schemas import Memo

SEAT_ID_TO_ROLE: dict[str, str] = {
    "operator-ceo": "Operator-CEO",
    "devils-advocate": "Devil's Advocate",
    "outsider": "Outsider",
    "visionary": "Visionary",
    "cfo": "CFO",
    "cto": "CTO",
    "cmo": "CMO",
}


def _role_name(seat_id: str) -> str:
    return SEAT_ID_TO_ROLE.get(seat_id, seat_id)


def format_memo_markdown(memo: Memo) -> str:
    """Render memo to Markdown. Uses role names, never source-figure names."""
    lines: list[str] = []

    lines.append(f"# Board Memo — {memo.verdict.value.upper()}")
    lines.append("")
    lines.append(f"**Meeting type:** {memo.meeting_type.value}")
    lines.append(f"**Protocol version:** {memo.protocol_version}")
    lines.append(f"**Date:** {memo.created_at.strftime('%Y-%m-%d %H:%M UTC')}")
    lines.append(f"**Source:** {memo.source.value}")
    lines.append("")

    lines.append("---")
    lines.append("")

    lines.append(f"**Verdict: {memo.verdict.value.upper()}**")
    lines.append(f"Confidence (weighted): {memo.confidence_weighted:.2f}")
    lines.append(f"Confidence spread: {memo.confidence_spread:.2f}")
    lines.append("")

    lines.append("## Verdict Reasoning")
    lines.append("")
    lines.append(memo.verdict_reasoning)
    lines.append("")

    lines.append(f"## Dissent ({_role_name(memo.dissent_source)})")
    lines.append("")
    lines.append(memo.dissent_summary)
    lines.append("")

    lines.append("## Kill Criteria")
    lines.append("")
    for i, kc in enumerate(memo.kill_criteria, 1):
        lines.append(f"{i}. {kc.criterion}")
        lines.append(f"   *Owner:* {kc.owner_to_monitor}")
    lines.append("")

    lines.append("## Next Action")
    lines.append("")
    lines.append(f"**Action:** {memo.next_action.action}")
    lines.append(f"**Owner:** {memo.next_action.owner}")
    lines.append(f"**Deadline:** {memo.next_action.deadline.isoformat()}")
    lines.append("")

    lines.append("## Signatures")
    lines.append("")
    lines.append("| Role | Verdict | Confidence (raw) | Confidence (recalibrated) |")
    lines.append("|------|---------|-------------------|---------------------------|")
    for sig in memo.signatures:
        lines.append(
            f"| {_role_name(sig.seat_id)} | {sig.verdict.value} "
            f"| {sig.confidence_raw:.2f} | {sig.confidence_recalibrated:.4f} |"
        )
    lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("*Metadata*")
    lines.append(f"- Seed: {memo.metadata.seed}")
    lines.append(f"- Wall clock: {memo.metadata.wall_clock_seconds:.1f}s")
    lines.append(f"- LLM cost: ${memo.metadata.llm_cost_usd:.4f}")
    lines.append(f"- Unanimous: {memo.metadata.unanimous}")
    lines.append(f"- Forced dissent: {memo.metadata.forced_dissent_triggered}")
    if memo.metadata.reasoning_overlap_score is not None:
        lines.append(f"- Reasoning overlap: {memo.metadata.reasoning_overlap_score:.4f}")
    lines.append("")

    return "\n".join(lines)
