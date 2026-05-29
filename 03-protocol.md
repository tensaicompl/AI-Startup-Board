# 03 — Protocol: The Idea Screen State Machine

This is the spine. Implement it exactly. Every state has explicit entry conditions, transitions, and outputs. The chair owns all of this in code.

## 1. State diagram

```
   ┌─────────┐
   │ CONVENE │
   └────┬────┘
        │ valid_petition && quorum_met
        ▼
┌──────────────────┐
│ SEALED_OPENING   │  each seat drafts blind, in parallel
└────────┬─────────┘
         │ all seats responded || timeout
         ▼
┌────────────────────┐
│ ANONYMIZED_REVEAL  │  identities stripped, peers critiqued
└─────────┬──────────┘
          │ all critiques received
          ▼
┌────────────────────────┐
│ IDENTIFIED_REBUTTAL    │  identities revealed, revisions allowed
└─────────┬──────────────┘
          │ rebuttals received
          ▼
┌──────────────────────┐
│ DEVILS_ADVOCATE      │  DA produces steelman against majority
└─────────┬────────────┘
          │ DA case received
          ▼
┌────────────────────────┐
│ CONFIDENCE_VOTE        │  each voting seat emits (verdict, confidence)
└─────────┬──────────────┘
          │ vote tallied
          ▼
       ┌──── unanimous? ─── YES ──┐
       │                          ▼
       │                ┌──────────────────────────┐
       │                │ FORCED_DISSENT_CHECK     │
       │                └─────────┬────────────────┘
       │ NO                       │
       ▼                          ▼
┌────────────────────┐
│ MEMO_SYNTHESIS     │
└─────────┬──────────┘
          │
          ▼
       memo persisted, returned
```

## 2. State specifications

### S1 — CONVENE
**Inputs:** petition (validated), meeting_type config, seed.
**Actions:**
- Load the meeting protocol (`protocols/idea-screen.yaml`).
- Resolve quorum (3 seats for Idea Screen).
- Load persona files; hash them; record in `MeetingState`.
- Initialize transcript with petition, protocol version, persona hashes, model IDs, seed.
- Instantiate seat contexts (isolated, no shared state).

**Exit guard:** all seats instantiated, quorum met.
**Failure:** any persona file fails schema validation → abort with `error: persona_validation_failed`.

### S2 — SEALED_OPENING
**Inputs:** petition, per-seat persona.
**Memory access per seat:** persona file only. **No transcript. No peer outputs.**
**Prompt template:** see `src/sboard/prompts/sealed_opening.txt`.
**Required output schema** (`schemas/seat-output.schema.json`, variant `sealed_opening`):
```json
{
  "seat_id": "operator-ceo",
  "stage": "sealed_opening",
  "position": "proceed" | "kill" | "conditional",
  "one_paragraph_case": "string, 50-200 words",
  "top_three_reasons": ["string", "string", "string"],
  "kill_criteria": ["string", "string"],
  "confidence_raw": 0.0
}
```
**Parallelism:** all seats called concurrently.
**Timeout:** per-seat 60s default. On timeout: seat marked `abstain_timeout`, meeting continues if remaining seats ≥ quorum_floor (2).
**Malformed output:** one re-prompt with the validation error. If still malformed: seat marked `abstain_malformed`.

**Exit guard:** every seat has a status (responded | abstain_timeout | abstain_malformed). Quorum_floor satisfied.

### S3 — ANONYMIZED_REVEAL
**Actions:**
- Chair shuffles `sealed_opening` outputs.
- Chair re-labels them `Seat A`, `Seat B`, `Seat C` (random assignment, seed-recorded).
- Chair strips any persona-identifying language from the outputs using a deterministic redaction list per persona (defined in persona frontmatter — see `personas/_schema.yaml`).
- Identity map stored in `MeetingState.anonymization_map`, not exposed to any seat.

**Per-seat call:** each seat receives all peer outputs labeled A/B/C with its own output highlighted, asked to critique each peer (excluding self).
**Required output schema** (variant `anonymized_review`):
```json
{
  "seat_id": "operator-ceo",
  "stage": "anonymized_review",
  "reviews": [
    {"target_label": "Seat B", "agreement": "agree"|"disagree"|"undecided",
     "one_sentence_reason": "string"},
    {"target_label": "Seat C", "agreement": "...", "one_sentence_reason": "..."}
  ]
}
```
**Exit guard:** every responding seat from S2 has submitted reviews of every peer.

### S4 — IDENTIFIED_REBUTTAL
**Actions:**
- Chair reveals the anonymization map: each peer label is now associated with the actual seat ID.
- Seats may revise their position, but **must state why** if they move. Silent conformity is detectable in the transcript and flagged.

**Per-seat call:** each seat receives identified peer positions + the seat's own anonymized reviews of them.
**Required output schema** (variant `rebuttal`):
```json
{
  "seat_id": "operator-ceo",
  "stage": "rebuttal",
  "position": "proceed" | "kill" | "conditional",
  "position_changed": true|false,
  "change_reason": "string, required if position_changed=true, else null",
  "rebuttal_text": "string, 50-150 words"
}
```
**Exit guard:** all seats responded. Position changes logged. **Rounds capped at 1 in MVP** (ReConcile converges by round 3; we use one round, then DA, then vote — see §3 for the rationale).

### S5 — DEVILS_ADVOCATE
**Actions:**
- The seat marked `is_devils_advocate: true` in its frontmatter (Munger in MVP) is invoked.
- The DA receives all rebuttals and the current majority trend.
- The DA must produce a steelmanned case **against** the majority. The DA's own prior position is irrelevant in this state.

**Required output schema** (variant `devils_advocate`):
```json
{
  "seat_id": "devils-advocate",
  "stage": "devils_advocate",
  "majority_trend": "proceed" | "kill" | "conditional" | "split",
  "steelman_against_majority": "string, 100-200 words",
  "strongest_kill_condition": "string"
}
```
**Exit guard:** DA case received. If majority trend is "kill", the DA still produces a steelman for "proceed" (the DA's job is structural, not personal).

### S6 — CONFIDENCE_VOTE
**Actions:**
- Each voting seat (in MVP: all three seats vote) receives all rebuttals + the DA case + the chair's neutral summary of positions.
- Each seat emits a final verdict and a confidence value.

**Required output schema** (variant `vote`):
```json
{
  "seat_id": "operator-ceo",
  "stage": "vote",
  "verdict": "proceed" | "kill" | "conditional",
  "confidence_raw": 0.0,
  "one_sentence_rationale": "string"
}
```

**Recalibration function:**
```
confidence_recalibrated = confidence_raw * persona.recalibration_factor

where persona.recalibration_factor is in [0.6, 1.0] and defaults to 0.8
(LLMs systematically overconfidence; this discounts).
```

**Tally:**
```
For each verdict V in {proceed, kill, conditional}:
  score(V) = sum(seat.confidence_recalibrated for seat in seats if seat.verdict == V)
final_verdict = argmax(score)
confidence_spread = max(score) - second_max(score)
```

**Exit guard:** all voting seats voted. Tally computed.

### S7 — FORCED_DISSENT_CHECK (conditional)
**Entry condition:** all voting seats voted the same verdict (unanimous).
**Actions:** chair selects the lowest-confidence seat (deterministic — ties broken by seat_id alphabetical). That seat is asked to produce the strongest counter-case it can muster.

**Required output schema** (variant `forced_dissent`):
```json
{
  "seat_id": "operator-ceo",
  "stage": "forced_dissent",
  "counter_verdict": "proceed" | "kill" | "conditional",
  "counter_case": "string, 100-200 words",
  "would_change_mind_if": "string"
}
```
**Exit guard:** counter-case received. **The counter-case becomes the memo's dissent_summary** in unanimous cases.

### S8 — MEMO_SYNTHESIS
**Actions:**
- Code populates structural fields: verdict, confidence_spread, kill_criteria (deduplicated union from all seats), next_action, signatures.
- One LLM call (using `claude-sonnet-4-6` by default) writes the prose for `verdict_reasoning` (≤200 words) and `dissent_summary` (≤150 words).
- The synthesis prompt receives: final tally, all rebuttals, DA case, forced dissent (if any). It is constrained to the memo schema via tool-use / structured output.
- Memo validated against `schemas/memo.schema.json`. Word count enforced.

**Exit:** memo persisted, returned.

## 3. Design notes and tradeoffs

**One rebuttal round, not three.** ReConcile shows convergence by round 3 but also shows diminishing returns. With three seats and a DA pass, one rebuttal + DA + vote captures most of the value at a fraction of the cost. Post-MVP can experiment with more rounds.

**Confidence recalibration factor lives in persona, not in code.** Different personas have different overconfidence profiles. Munger is naturally cautious; default 0.95. Grove is operational and pattern-matches fast; 0.80. Outsider is uncalibrated; 0.70. These numbers are first guesses, to be tuned from A/B data.

**The DA is permanent in MVP.** Post-MVP it rotates. Permanent is simpler; rotation is fairer. Build simple first.

**Anonymization redaction list lives in persona frontmatter.** A seat's signature_phrases would otherwise leak identity. The chair redacts them when anonymizing. This is brittle; if a seat says "as I always say…" without using a redacted phrase, identity may leak. The mitigation is mostly structural (random shuffle, no positional cues) and partially trusted (the LLMs are not adversarial here).

**Position change must be explained.** This is the cheapest sycophancy detector. A seat that flips after reveal must say why; if "why" reads as "because Seat B said so", flag it. Manual review in MVP.

## 4. Runtime metrics to log

Every meeting writes these to the transcript:
- `position_changes_after_reveal`: count.
- `unanimous_vote`: boolean.
- `forced_dissent_triggered`: boolean.
- `da_case_majority`: which side the DA argued against.
- `wall_clock_seconds_per_state`: dict.
- `llm_cost_usd_total`: float.
- `confidence_spread_final`: float.
- `reasoning_overlap_score`: float, computed as Jaccard similarity over key terms from each seat's `top_three_reasons`. Flag if >0.6 (council-review's theatrical-consensus threshold).
