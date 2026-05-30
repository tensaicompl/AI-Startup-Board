# Decision 007: A/B harness — anonymization, rating schema, gate tally

**Date:** 2026-05-29
**Status:** accepted
**Context:** Task 10 builds the gate the MVP exists to pass (docs/07-evaluation.md):
`sboard ab` runs the board and a single-LLM baseline on one petition, writes a
blind rater bundle, and `tests/ab/score.py` tallies the three pass criteria. The
spec fixes the intent but leaves several mechanics open. They are recorded here.

**Decision:**

1. **Anonymization is structural, not just metadata-stripping.** The spec says to
   strip the `source` field, persona hashes, and model IDs. That is necessary but
   not sufficient: the board memo carries three signatures and the baseline one,
   so a signature block (or any confidence/seed/cost metadata) would reveal the
   pipeline immediately. The rater-facing artifact (`A.md` / `B.md`) therefore
   renders only the pipeline-neutral decision surface — verdict, verdict
   reasoning, dissent, kill criteria, next action — via `render_anonymized_memo`.
   Both pipelines produce an identically-sectioned document.

2. **Neutralized one board-referential template string.** The synthesizer's
   conditional `next_action` previously read "…report back to the board." The
   founder is an explicit rater (07-evaluation §4) and knows the architecture is
   called "the board," so that phrase is a tell. Changed to "…report back at the
   next review." This is the only board-self-reference in deterministic output.
   Live free-text prose cannot be guaranteed neutral by the harness; the board
   synthesis and baseline prompts are responsible for not naming the mechanism.
   The harness guarantees structural + metadata blindness, enforced by a test.

3. **Rating CSV adds a `memo` column.** The doc sketches columns
   `petition_id, rater_id, axis, score, forced_choice`. Those cannot express
   *which* memo a score belongs to, yet criteria 1 and 2 require per-pipeline
   means. Added a `memo` (A|B) column. Final schema:
   `petition_id, rater_id, memo, axis, score, forced_choice`. `axis` is one of
   `dissent_sharpness | kill_criteria_clarity | decisiveness`; `forced_choice` is
   `A | B | neither`. The template ships 6 skeleton rows (2 memos × 3 axes) for a
   placeholder `RATER_ID`, plus `HOW_TO_RATE.md` with the 1–5 scale.

4. **forced_choice is per (petition, rater).** Recorded once on any of a rater's
   rows; the tally takes the first non-empty value. A petition counts as
   board-preferred when board forced-choices outnumber baseline among its raters
   (majority). Criterion 3 = (board-preferred petitions / petitions) ≥ 0.60.

5. **Master mapping held in a separate directory.** `tests/ab/master/<pid>.json`
   holds the A/B→pipeline mapping, memo ids, and seeds — never inside the rater
   bundle `tests/ab/runs/<pid>/`. Both paths are git-ignored.

6. **Baseline memo construction.** The single LLM call fills `BaselineMemoOutput`
   (the rater-relevant content subset); code assembles a full schema-valid `Memo`
   with `source=baseline`, `persona_hashes={}`, one `baseline` signature, and
   `confidence_spread=0.0`. The baseline prompt is a fair competitor, not
   weakened (07-evaluation §7).

7. **Real client via tool-use forcing.** `LiveAnthropicClient` (the first
   component needing `ANTHROPIC_API_KEY`) forces schema-valid output by exposing
   the Pydantic `model_json_schema()` as a single tool and reading the tool input
   back as JSON. Selected with `--live` (default `--mock`); its control flow is
   tested with `messages.create` patched, so the build stays keyless.

8. **Pipelines run concurrently** via a `ThreadPoolExecutor` (independent work;
   real wall-clock win on live runs). A/B labels are assigned with a seeded RNG
   (`--ab-seed`, default 1) so runs are reproducible; the mapping lives in master.

9. **Gate verdict mapping.** PASS = all 3 gating criteria; MARGINAL = 2 of 3;
   FAIL = ≤1 (per 07-evaluation §6). Decisiveness is computed and reported but not
   gating. Tally logic lives in `sboard.ab_score` (typed, unit-tested);
   `tests/ab/score.py` is the thin runnable entry point the spec names.

10. **`ab` persists to the audit DB** (append-only): petition (once), board
    transcript, and both memos. Consistent with the Task 8 audit discipline and
    Decision 006's re-run behaviour.

**Alternatives considered:** (1) Strip only `source`/hashes/model-ids and reuse
the full memo formatter — rejected; the signature block leaks the pipeline.
(2) Keep the doc's 5-column CSV — rejected; it cannot compute per-pipeline means.
(3) Regex-scrub "board" from prose in the renderer — rejected as fragile; fixed
the one deterministic source instead and left live-prose neutrality to the
prompts. (4) Run the pipelines sequentially — rejected; the spec says parallel
and the live gate benefits.

**Consequences:** `sboard ab` runs end-to-end on mocks (keyless) and the live
gate needs only `--live` + the key. The two memos are structurally
indistinguishable and a test asserts no pipeline tells (incl. source-figure
names and the word "board") in the rater bundle. The 20-petition test set itself
is the founder's to assemble (HANDOFF §9); the harness is complete.

---

## Addendum — live-run hardening (first real `--live` run)

The first live A/B run surfaced four failure modes that mocks cannot, all fixed
without altering argument quality (so §7 integrity holds — these are reliability
and blindness fixes, not tuning to flatter the test):

1. **Tool-payload wrapping.** Under forced `tool_choice`, models intermittently
   nest the arguments under a generic wrapper key (observed: `parameter`,
   `$PARAMETER_NAME`) or add a stray `$FUNCTION_NAME` key. `LiveAnthropicClient`
   now runs `_extract_tool_payload`, which matches the schema's own field names to
   recover the real object and drops anything else (the schemas are
   `extra="forbid"`, so this is exactly right). Tool description also asks for
   top-level fields.

2. **Invented `seat_id`.** A real model fills the `seat_id` field with its own
   value (`devils_advocate` vs the canonical `devils-advocate`), breaking persona
   lookups and signatures. `run_seat` now overwrites `seat_id` with the canonical
   persona id before validation — identity is the chair's to assign, not the
   model's.

3. **Verbose seats overrunning `max_length`.** Live models routinely exceed terse
   field caps (e.g. a 320-char vote rationale against a 300 cap), and a blind
   retry repeats the mistake. The single retry is now **informed**: the exact
   validation error is fed back so the model corrects its own formatting. (Still
   one retry, so the call-count tests hold.) `ab._run_board` also wraps the board
   run so any residual pipeline failure surfaces as a clean `ABError` instead of a
   traceback.

4. **Prose leak.** The synthesis model wrote "the board votes kill (2.09/5.0)…",
   naming the mechanism and citing internal scores — a fatal tell for the
   founder-rater. The synthesis prompt + system prompt were rewritten to forbid
   any reference to a board, seats, voting, dissent mechanics, or internal scores;
   it must write as a single standalone advisor. A leak scan confirmed clean
   output on the re-run. Note the residual confound this exposed: board memo prose
   is written by **Sonnet** (synthesis) while the baseline is **Opus** — so
   blind-rated "language" differences may be model-tier, not architecture; a fair
   comparison should set `SBOARD_SYNTHESIS_MODEL` to the baseline's tier.
