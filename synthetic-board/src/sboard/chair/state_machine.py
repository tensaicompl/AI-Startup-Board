"""LangGraph state machine: the eight-state Idea Screen protocol.

The graph nodes are deterministic Python functions, not agents.
Every edge is a code-level guard. No transition asks a model for judgment.
"""

from __future__ import annotations

import time
from typing import TypedDict, cast

from langgraph.graph import END, START, StateGraph

from sboard.chair.meeting_state import MeetingState, ProtocolState
from sboard.chair.states import (
    do_anonymized_reveal,
    do_confidence_vote,
    do_convene,
    do_devils_advocate,
    do_forced_dissent_check,
    do_gtm_stage,
    do_idea_analysis,
    do_identified_rebuttal,
    do_sealed_opening,
    do_visionary_pass,
)
from sboard.memo.synthesizer import synthesize_memo, synthesize_memo_v2
from sboard.schemas import Position
from sboard.seats.llm_client import AnthropicClient


class GraphState(TypedDict):
    meeting: MeetingState


# Declarative graph wiring: one closure per protocol node plus routing guards.
# The branch count is inherent to enumerating the state machine; splitting it
# would scatter the protocol spine across helpers and hurt readability.
def _build_graph(client: AnthropicClient) -> StateGraph[GraphState]:  # noqa: C901
    """Build the Idea Screen state machine graph."""

    def convene(state: GraphState) -> GraphState:
        do_convene(state["meeting"])
        return state

    def sealed_opening(state: GraphState) -> GraphState:
        do_sealed_opening(state["meeting"], client)
        return state

    def anonymized_reveal(state: GraphState) -> GraphState:
        do_anonymized_reveal(state["meeting"], client)
        return state

    def identified_rebuttal(state: GraphState) -> GraphState:
        do_identified_rebuttal(state["meeting"], client)
        return state

    def devils_advocate(state: GraphState) -> GraphState:
        do_devils_advocate(state["meeting"], client)
        return state

    def confidence_vote(state: GraphState) -> GraphState:
        do_confidence_vote(state["meeting"], client)
        return state

    def forced_dissent_check(state: GraphState) -> GraphState:
        do_forced_dissent_check(state["meeting"], client)
        return state

    def memo_synthesis(state: GraphState) -> GraphState:
        ms = state["meeting"]
        start = time.monotonic()
        ms.current_state = ProtocolState.MEMO_SYNTHESIS
        memo = synthesize_memo(ms, client)
        ms.memo = memo
        ms.current_state = ProtocolState.COMPLETE
        ms.log("memo_synthesized", {"memo_id": str(memo.memo_id)})
        ms.state_timings["MEMO_SYNTHESIS"] = time.monotonic() - start
        return state

    # --- Guards (deterministic routing) ---

    def after_convene(state: GraphState) -> str:
        ms = state["meeting"]
        if ms.current_state == ProtocolState.ABORTED:
            return "end"
        return "sealed_opening"

    def after_sealed_opening(state: GraphState) -> str:
        ms = state["meeting"]
        if ms.current_state == ProtocolState.ABORTED:
            return "end"
        return "anonymized_reveal"

    def after_vote(state: GraphState) -> str:
        ms = state["meeting"]
        if ms.unanimous:
            return "forced_dissent_check"
        return "memo_synthesis"

    graph = StateGraph(GraphState)

    graph.add_node("convene", convene)
    graph.add_node("sealed_opening", sealed_opening)
    graph.add_node("anonymized_reveal", anonymized_reveal)
    graph.add_node("identified_rebuttal", identified_rebuttal)
    graph.add_node("devils_advocate", devils_advocate)
    graph.add_node("confidence_vote", confidence_vote)
    graph.add_node("forced_dissent_check", forced_dissent_check)
    graph.add_node("memo_synthesis", memo_synthesis)

    graph.add_edge(START, "convene")
    graph.add_conditional_edges("convene", after_convene, {
        "sealed_opening": "sealed_opening",
        "end": END,
    })
    graph.add_conditional_edges("sealed_opening", after_sealed_opening, {
        "anonymized_reveal": "anonymized_reveal",
        "end": END,
    })
    graph.add_edge("anonymized_reveal", "identified_rebuttal")
    graph.add_edge("identified_rebuttal", "devils_advocate")
    graph.add_edge("devils_advocate", "confidence_vote")
    graph.add_conditional_edges("confidence_vote", after_vote, {
        "forced_dissent_check": "forced_dissent_check",
        "memo_synthesis": "memo_synthesis",
    })
    graph.add_edge("forced_dissent_check", "memo_synthesis")
    graph.add_edge("memo_synthesis", END)

    return graph


def run_meeting(
    meeting_state: MeetingState,
    client: AnthropicClient,
) -> MeetingState:
    """Execute the full v1 (8-state, 3-seat) Idea Screen protocol."""
    graph = _build_graph(client)
    compiled = graph.compile()

    initial: GraphState = {"meeting": meeting_state}
    result = compiled.invoke(initial)
    return cast(MeetingState, result["meeting"])


# The v2 graph adds three nodes and two conditional edges. Both conditionals are
# pure arithmetic on MeetingState (unanimity; verdict != kill) — never an LLM call.
def _build_v2_graph(client: AnthropicClient) -> StateGraph[GraphState]:  # noqa: C901
    """Build the v2 (11-state, 7-seat) Idea Screen graph."""

    def convene(state: GraphState) -> GraphState:
        do_convene(state["meeting"])
        return state

    def sealed_opening(state: GraphState) -> GraphState:
        do_sealed_opening(state["meeting"], client)
        return state

    def anonymized_reveal(state: GraphState) -> GraphState:
        do_anonymized_reveal(state["meeting"], client)
        return state

    def identified_rebuttal(state: GraphState) -> GraphState:
        do_identified_rebuttal(state["meeting"], client)
        return state

    def idea_analysis(state: GraphState) -> GraphState:
        do_idea_analysis(state["meeting"], client)
        return state

    def devils_advocate(state: GraphState) -> GraphState:
        do_devils_advocate(state["meeting"], client)
        return state

    def visionary_pass(state: GraphState) -> GraphState:
        do_visionary_pass(state["meeting"], client)
        return state

    def confidence_vote(state: GraphState) -> GraphState:
        do_confidence_vote(state["meeting"], client)
        return state

    def forced_dissent_check(state: GraphState) -> GraphState:
        do_forced_dissent_check(state["meeting"], client)
        return state

    def gtm_stage(state: GraphState) -> GraphState:
        do_gtm_stage(state["meeting"], client)
        return state

    def memo_synthesis(state: GraphState) -> GraphState:
        ms = state["meeting"]
        start = time.monotonic()
        ms.current_state = ProtocolState.MEMO_SYNTHESIS
        memo = synthesize_memo_v2(ms, client)
        ms.memo = memo
        ms.current_state = ProtocolState.COMPLETE
        ms.log("memo_synthesized", {"memo_id": str(memo.memo_id)})
        ms.state_timings["MEMO_SYNTHESIS"] = time.monotonic() - start
        return state

    # --- Guards (deterministic routing; arithmetic only) ---

    def after_convene(state: GraphState) -> str:
        return "end" if state["meeting"].current_state == ProtocolState.ABORTED else "sealed_opening"

    def after_sealed_opening(state: GraphState) -> str:
        return "end" if state["meeting"].current_state == ProtocolState.ABORTED else "anonymized_reveal"

    def after_vote(state: GraphState) -> str:
        ms = state["meeting"]
        if ms.unanimous:
            return "forced_dissent_check"
        return "gtm_stage" if ms.final_verdict != Position.KILL else "memo_synthesis"

    def after_forced_dissent(state: GraphState) -> str:
        ms = state["meeting"]
        return "gtm_stage" if ms.final_verdict != Position.KILL else "memo_synthesis"

    graph = StateGraph(GraphState)
    for name, fn in [
        ("convene", convene),
        ("sealed_opening", sealed_opening),
        ("anonymized_reveal", anonymized_reveal),
        ("identified_rebuttal", identified_rebuttal),
        ("idea_analysis", idea_analysis),
        ("devils_advocate", devils_advocate),
        ("visionary_pass", visionary_pass),
        ("confidence_vote", confidence_vote),
        ("forced_dissent_check", forced_dissent_check),
        ("gtm_stage", gtm_stage),
        ("memo_synthesis", memo_synthesis),
    ]:
        graph.add_node(name, fn)

    graph.add_edge(START, "convene")
    graph.add_conditional_edges("convene", after_convene, {
        "sealed_opening": "sealed_opening", "end": END,
    })
    graph.add_conditional_edges("sealed_opening", after_sealed_opening, {
        "anonymized_reveal": "anonymized_reveal", "end": END,
    })
    graph.add_edge("anonymized_reveal", "identified_rebuttal")
    graph.add_edge("identified_rebuttal", "idea_analysis")
    graph.add_edge("idea_analysis", "devils_advocate")
    graph.add_edge("devils_advocate", "visionary_pass")
    graph.add_edge("visionary_pass", "confidence_vote")
    graph.add_conditional_edges("confidence_vote", after_vote, {
        "forced_dissent_check": "forced_dissent_check",
        "gtm_stage": "gtm_stage",
        "memo_synthesis": "memo_synthesis",
    })
    graph.add_conditional_edges("forced_dissent_check", after_forced_dissent, {
        "gtm_stage": "gtm_stage",
        "memo_synthesis": "memo_synthesis",
    })
    graph.add_edge("gtm_stage", "memo_synthesis")
    graph.add_edge("memo_synthesis", END)

    return graph


def run_meeting_v2(
    meeting_state: MeetingState,
    client: AnthropicClient,
) -> MeetingState:
    """Execute the full v2 (11-state, 7-seat) Idea Screen protocol."""
    compiled = _build_v2_graph(client).compile()
    initial: GraphState = {"meeting": meeting_state}
    result = compiled.invoke(initial)
    return cast(MeetingState, result["meeting"])
