# Synthetic Board v2 — Large Expansion Plan

**Frozen scope.** Seven seats (five voting, two advisory), five-stage memo body,
two new conditional protocol states, six persona files total. Backwards
compatibility preserved via protocol versioning — **v1 stays runnable, v2 becomes
default.**

## The seven seats

| Seat file | Role | Figure | Voting | Notes |
|---|---|---|---|---|
| operator-ceo | Operator-CEO | Jack Welch | yes | v1 |
| devils-advocate | Devil's Advocate | Warren Buffett | yes | v1 |
| outsider | Outsider | synthetic | yes | v1 |
| visionary | Visionary | Steve Jobs | yes | new |
| technical | CTO/Technical | Linus Torvalds | yes | new |
| growth-advisor | Growth advisor | Jeff Bezos | **no** (advisor) | new |
| marketing | Marketing/GTM | David Ogilvy | **no** (gtm_only) | new |

## New figures and birth data

- **Steve Jobs** — 1955-02-24, 19:15 PST, San Francisco CA (Rodden AA).
- **Linus Torvalds** — 1969-12-28, 14:30 EET, Helsinki, Finland (Rodden A — verify against astrodatabank).
- **Jeff Bezos** — 1964-01-12, time unknown, Albuquerque NM (Rodden DD/X — noon chart, `time_known: false`).
- **David Ogilvy** — 1911-06-23, time unknown, West Horsley UK (Rodden DD/X — noon chart, `time_known: false`).

For Bezos and Ogilvy the AA/A-only rule for chart-grounded seats is **relaxed in
v2 with explicit acknowledgment**: use noon charts, omit ascendant, lean on the
documented archetype in the body. Logged as **Decision 008**.

## Tasks (each ends with passing tests; one commit per task)

**v2.1 — Schema and protocol version bump**
- New memo body: `idea_analysis` (≤200w), `verdict_reasoning` (≤300w),
  `vision` (≤250w), `dissent_summary` (≤250w), `gtm_analysis` (≤200w, optional,
  present only if verdict != kill). Combined body limit 1,200 words.
- New protocol `protocols/idea-screen-v2.yaml` with 11 states.
- Pydantic models updated to v2 with a version discriminator.
- v1 schema preserved at `schemas/memo-v1.schema.json`; v2 at
  `schemas/memo.schema.json` (default). Round-trip tests for both. All prior green.

**v2.2 — Four new persona files**
- `personas/visionary.md` (Jobs), `personas/technical.md` (Torvalds),
  `personas/growth-advisor.md` (Bezos, voting:false, advisor:true),
  `personas/marketing.md` (Ogilvy, voting:false, gtm_only:true).
- Full frontmatter validated against `_schema.yaml`; full body with all 7
  mandatory sections. Add `advisor: bool` and `gtm_only: bool` to `_schema.yaml`.
- Diversity passes with all 7 seats (≥5 of 7 axes distinct). Per-persona load tests.

**v2.3 — Three new state functions**
- `do_idea_analysis` (all voting + Bezos), `do_visionary_pass` (Jobs + Bezos,
  always runs even on kill trend), `do_gtm_stage` (Ogilvy + Bezos, conditional on
  verdict != kill). Each: MeetingState + AnthropicClient → structured Pydantic
  output → transcript. Mock-tested on the three smoke petitions.

**v2.4 — State machine wiring**
- Insert new nodes. Edges:
  `IDENTIFIED_REBUTTAL → IDEA_ANALYSIS → DEVILS_ADVOCATE → VISIONARY_PASS →
  CONFIDENCE_VOTE → (FORCED_DISSENT_CHECK?) → (GTM_STAGE if verdict != kill) →
  MEMO_SYNTHESIS`. Conditional routing only on verdict.kill vs not-kill
  (arithmetic on the tally, not an LLM judgment). End-to-end mock test runs all
  11 states on petition 01. Cost cap raised: soft $12, hard $40 per meeting.

**v2.5 — Memo synthesis update**
- Synthesizer produces five body sections in one LLM call. Per-section + combined
  word budgets enforced. Forbidden-token list extended with the four new figures'
  tokens (plus the existing 11). Formatter renders the five sections in order.
  End-to-end test → schema-valid v2 memo with zero forbidden tokens.

## Discipline (unchanged)

- Chair is code. No state transition is an LLM judgment.
- Anonymization map stays in chair state; seats see Seat A/B/C until IDENTIFIED_REBUTTAL.
- Per-state memory access enforced by chair.
- Append-only persistence; no UPDATE, no DELETE.
- One commit per task. Decision records for every non-obvious choice.

## After all five tasks

Run `sboard ab --live --protocol idea_screen_v2` on the three smoke petitions;
produce paired memos against the unchanged single-LLM baseline. The comparator is
unchanged so v2-vs-baseline is comparable to v1-vs-baseline.
