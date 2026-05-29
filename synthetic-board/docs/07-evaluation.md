# 07 — Evaluation: The A/B Gate

This is the gate. The MVP either passes this test or it dies. The point of the architecture is to win this comparison; if it doesn't, the multi-agent overhead isn't justified and the project ends.

## 1. The test

**Hypothesis:** A 3-seat synthetic board produces sharper dissent and clearer kill criteria than a single well-prompted LLM, on the same petitions, blind-rated.

**Null hypothesis:** It does not. The single-LLM baseline is as good or better. (This must be a real possibility. If it cannot lose, it is not a real test.)

## 2. The setup

1. Assemble a test set of 20 petitions covering a range of startup ideas: 5 obviously good, 5 obviously bad, 10 ambiguous. Source: real founder pitches (anonymized), historical pitch decks, and synthetic variations. Petitions are stored in `tests/ab/petitions/`.
2. Run each petition through both pipelines:
   - **Board:** `sboard convene <petition.json>` — full 3-seat Idea Screen.
   - **Baseline:** `sboard baseline <petition.json>` — single Anthropic call to `claude-opus-4-7` with the prompt in `tests/ab/baseline_prompt.txt`, asked to produce a memo in the same schema.
3. Both memos are saved to disk with all source-identifying metadata stripped (`source` field removed, persona hashes removed, model IDs masked).
4. The blind-rater receives the petition + two memos labeled `A` and `B`. The A/B assignment is randomized per petition (recorded in the master file, not visible to the rater).

## 3. The rating

The rater scores each memo independently on three axes (1–5 scale):

**Sharpness of dissent (1–5):**
- 5 — Names a specific, non-obvious objection that materially affects the verdict.
- 3 — Names a generic objection.
- 1 — No real dissent; agrees with itself.

**Clarity of kill criteria (1–5):**
- 5 — All kill criteria are measurable, time-bounded, and tied to specific metrics.
- 3 — Mix of measurable and vague.
- 1 — Aspirational, untestable, or absent.

**Decisiveness (1–5):**
- 5 — A clear verdict that the rater could act on in 60 seconds.
- 3 — A verdict, but hedged.
- 1 — Five hedges in one paragraph; no clear call.

The rater also picks a forced choice: "If you were the founder, which memo would you act on?" (A | B | neither).

## 4. The raters

Minimum three raters per petition. Independent. They do not see each other's scores until after submission. Raters are:

- The founder (Przemyslaw).
- One technical raters (Claude — when run as evaluator with cleared context).
- One non-technical rater (recommended: someone with operator experience who is not in the project).

Rater identity is not blinded to themselves but their scores are pooled.

## 5. The success criterion

The board wins the gate if **all** of the following hold across the 20 petitions:

1. **Mean sharpness-of-dissent score for board > baseline**, with the difference ≥ 0.5 on the 5-point scale.
2. **Mean kill-criteria clarity score for board > baseline**, with the difference ≥ 0.5.
3. **Forced-choice preference for board ≥ 60%** of petitions (i.e., raters pick board ≥ 12 of 20 times).

Decisiveness is monitored but not gating — the board can lose on decisiveness as long as it wins on dissent and kill criteria, because that tradeoff is acceptable.

## 6. The exit criteria

- **Pass:** all three conditions hit. Proceed to expand the cast and add Pre-Mortem (`docs/08-roadmap.md`).
- **Marginal:** two of three conditions hit. Diagnose the failing axis; one iteration cycle (≤4 weeks) to improve, then re-test. Hard limit: one re-test only.
- **Fail:** zero or one of three conditions hit. Project ends. Write the post-mortem. Document what was learned.

## 7. What "honest" means here

The temptation to game this test is severe. Guardrails:

- The rater cannot see which memo came from which pipeline. Enforced by the harness, not by trust.
- Petitions are written *before* the seats are tuned. Petitions are not adjusted to flatter the board.
- The baseline prompt is written *before* the board's outputs are reviewed. It is not weakened to make the board look good.
- Marginal results are reported as marginal. The temptation to round up to "pass" is the worst form of theater.

## 8. The harness

`sboard ab` does the following:

1. Reads a petition.
2. Runs the board and the baseline in parallel.
3. Strips identifying metadata from both memos.
4. Randomizes A/B label per petition.
5. Writes both anonymized memos and the rating template to `tests/ab/runs/<petition_id>/`.
6. Records the master file mapping (locked, only visible to the test administrator).

Rating sheets are CSV: petition_id, rater_id, axis, score, forced_choice. Tally script in `tests/ab/score.py`.

## 9. Sample size note

20 petitions is the minimum. It is statistically thin. Treat the result as directional, not definitive. If the result is borderline, run another 20 before declaring pass/fail. If the result is clear (5/5/5 vs 2/2/2), 20 is enough to act on.

## 10. The cost

20 petitions × 2 pipelines × ~15 LLM calls (board) or 1 call (baseline) ≈ 320 LLM calls total. At Opus pricing this is in the tens of USD. Cheap. Run the test.
