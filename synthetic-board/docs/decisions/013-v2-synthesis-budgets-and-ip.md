# Decision 013: v2 synthesis word budgets, the 47-token IP guard, and GTM rendering

**Date:** 2026-05-30
**Status:** accepted
**Context:** Task v2.5 finishes the v2 memo path: per-section + combined word
budgets on the five-section body, the forbidden-token guard extended for the four
new figures, and the formatter polish. Several non-obvious choices:

1. **Word budgets enforced in the synthesizer, not as Pydantic validators.** The
   per-section budgets (idea_analysis ≤200, verdict_reasoning ≤300, vision ≤250,
   dissent_summary ≤250, gtm_analysis ≤200) and the combined cap (≤1200) are checked
   in `synthesize_memo_v2` right after the structured output validates — the "schema
   boundary" — exactly as v1's 500-word cap is. They are deliberately *not* hard
   `Field`/validator constraints on `SynthesisV2Output`, because the discipline is
   retry-once-then-fail: an over-budget result must trigger a re-call, not raise at
   validation time. The `MemoV2` character caps remain as generous structural guards
   sized to the word targets. Word counting routes through the module-level
   `_count_words` so the retry-path tests can rig the budget signal (Decision 005).

2. **Per-section is the schema-boundary check; combined is separate.** `_v2_within_budget`
   computes each present section's word count once, then asserts (a) every section is
   within its own budget and (b) the sum is within 1200. These are two distinct
   conditions over one set of counts (no double counting, so the retry tests' call
   arithmetic stays clean: one `_count_words` call per present section per attempt).

3. **Combined cap covers the five body sections only — not the kill criteria.** This
   differs from v1, whose 500-word combined count folds in the kill-criteria text. v2's
   body *is* the five sections, and the five per-section budgets sum to exactly 1200, so
   the combined cap is the natural envelope of the body: 1000 words on a kill (no GTM),
   1200 on a full memo. Kill criteria are bounded by their own schema field limits.

4. **The 47-token guard lives in one source module.** `memo/ip_safety.py` holds the
   canonical list — v1's 11 (Welch/Buffett + the Outsider alias) plus 36 for Jobs,
   Torvalds, Bezos, Ogilvy — and `find_forbidden_tokens`, which matches each token on a
   word boundary, case-sensitive (so "GE" does not fire inside "GTM_STAGE" and "Git" does
   not fire inside "digit"). The scanner is asserted against the *rendered* memo Markdown
   (which contains the five body sections), per the v2.5 done-means.

5. **"David" and "Jeff" are kept, not narrowed.** The v2.5 spec offered narrowing them to
   "David Ogilvy" / "Jeff Bezos" *if* they false-positive against real content. They do
   not against the synthesized, IP-neutral memo body the scanner runs on (and the three
   smoke petitions contain neither as whole words), so the full 47-token list stands as
   written. Narrowing was the trigger for this decision number; since we did not narrow,
   this records the call to keep them and where to revisit it if a live run ever surfaces
   a legitimate "David"/"Jeff" in memo prose.

6. **GTM header names the section and makes absence explicit.** The formatter renders
   "## GTM Analysis" when present and "## GTM Analysis (n/a — kill verdict)" when a kill
   drops it — so a rater sees the section either way and never wonders whether it is
   missing or merely empty. Each of the five sections also carries a one-line italic gloss
   for at-a-glance orientation (visual hierarchy without reading every word). The earlier
   "## Go-to-Market" heading from the v2.4 stub is replaced by "## GTM Analysis" per spec.

**Alternatives considered:** (1) Pydantic word-count validators — rejected; they would
raise at validation and defeat the retry-then-fail control flow. (2) Folding kill criteria
into the v2 combined count like v1 — rejected; the v2 body is defined as the five sections
and the budgets already sum to the cap. (3) Narrowing David/Jeff pre-emptively — rejected
for now per the spec's "only if it false-positives" condition.

**Consequences:** The happy path is a single synthesis LLM call (the v1 call-count test is
unaffected; the v2 equivalent is asserted). Over-budget output retries once then raises
`MemoSynthesisError`. Rendered v2 memos for the three smoke petitions are word-bounded and
carry zero source-figure tokens; a kill memo drops GTM and says so. The IP guard is now a
reusable source function rather than a list duplicated across tests.
