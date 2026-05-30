# Decision 012: v2 graph wiring choices

**Date:** 2026-05-30
**Status:** accepted
**Context:** Task v2.4 inserts three nodes (IDEA_ANALYSIS, VISIONARY_PASS,
GTM_STAGE) and two conditional edges, makes seating protocol-driven, and flips the
default to v2. Several non-obvious choices:

1. **Two graph builders, not one parameterized graph.** `run_meeting`
   (`_build_graph`, 8 states) is left byte-stable; v2 is a separate
   `run_meeting_v2` (`_build_v2_graph`, 11 states). The v1 graph and its tests are
   untouched. The entry points pick the builder from `ProtocolConfig.is_v2`.

2. **Conditional edges are arithmetic, never an LLM call.** `after_vote`:
   `unanimous → FORCED_DISSENT_CHECK`; else `verdict != kill → GTM_STAGE` else
   `MEMO_SYNTHESIS`. `after_forced_dissent`: `verdict != kill → GTM_STAGE` else
   `MEMO_SYNTHESIS`. Both read `MeetingState.unanimous` / `.final_verdict` set by
   the vote tally. `do_gtm_stage` also guards its own precondition
   (`GtmPreconditionError` if verdict is kill) as defense in depth.

3. **State labelling fixed for the reordered sequence.** The v1 `do_*` functions
   set the *next* state at their end and relied on the predecessor to label the
   current one. v2 reorders predecessors, so `do_devils_advocate`,
   `do_confidence_vote`, and `do_forced_dissent_check` now set their *own*
   `current_state` at entry (idempotent in v1; correct in v2). This is labelling,
   not routing — routing remains the graph's.

4. **v2 synthesis is a second function.** `synthesize_memo_v2` produces a
   schema-valid `MemoV2` (five body sections from one LLM call; `gtm_analysis`
   present iff verdict != kill). Per-section + combined **word-budget enforcement**
   and the **forbidden-token list** for the four new figures are explicitly v2.5;
   v2.4 only needs valid memos. The formatter renders both versions; `store`
   round-trips both via `parse_memo_json`.

5. **Default protocol = v2** (frozen scope: "v2 becomes default"). `sboard
   convene <p>` and `sboard ab <p>` seat all 7 and run the 11-state graph;
   `--protocol idea_screen_v1` runs the 3-seat 8-state v1 graph. The transitional
   `V1_SEATS` pin is removed; seating comes from the protocol roster.

6. **Anonymization leak test made sound for common-word seat ids.** v1 seat ids
   (`operator-ceo`, …) are compound and never collide with prose, so a bare
   substring check sufficed. v2 adds single-word ids (`technical`, `marketing`,
   `visionary`) that legitimately occur in petitions and opening content. The
   chair attributes peers only by `Seat X` label (never by seat_id), and
   `anonymize_opening` scrubs each peer's redaction_aliases + signature_phrases.
   So the sound 7-seat check asserts: peer **identity markers** absent, and peer
   **compound** seat ids absent — single-word ids are protected via their markers,
   with the shared petition text stripped first.

**Alternatives considered:** (1) One graph with a version flag — rejected; it
risked perturbing the frozen v1 path and its tests. (2) Make `confidence_vote`
re-derive its own label by reading the graph — rejected; setting state at entry is
simpler and local. (3) Keep the bare-seat_id leak assertion and rename the v2
seats to compound ids — rejected; the role-based ids (`technical`, `marketing`)
are correct and the marker-based check is the real anonymization contract.

**Consequences:** v1 and v2 both run end to end (v1 via `--protocol
idea_screen_v1`, v2 by default). The three smoke petitions produce schema-valid
MemoV2s (GTM present on 01/03, NULL on a kill). Cost caps remain declarative
config in the protocol YAMLs (no enforcement code; none hardcoded). v2.5 adds the
synthesis word-budget + forbidden-token enforcement and the formatter polish.
