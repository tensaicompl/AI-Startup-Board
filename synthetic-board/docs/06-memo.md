# 06 — The Memo

The memo is the product. The transcript is exhaust. Build for the memo.

## 1. Why one page

A board memo that runs past one page is a report, not a decision. Reports are read at leisure; decisions are read in three minutes and acted on. Every constraint in the memo schema serves the three-minute read.

Concretely:
- Body ≤500 words.
- Verdict in the first line.
- Dissent in a named paragraph, not buried.
- Kill criteria are falsifiable, not aspirational.
- Next action has one owner and one deadline.

## 2. The schema

Full JSON Schema in `schemas/memo.schema.json`. Summary:

```json
{
  "memo_id": "uuid",
  "petition_id": "uuid",
  "meeting_type": "idea_screen",
  "protocol_version": "1.0.0",
  "created_at": "ISO-8601",
  "source": "board" | "baseline",

  "verdict": "proceed" | "kill" | "conditional",
  "confidence_weighted": 0.0,
  "confidence_spread": 0.0,

  "verdict_reasoning": "string, ≤200 words",
  "dissent_summary": "string, ≤150 words",
  "dissent_source": "seat_id of the dissenting (or forced-dissenting) seat",

  "kill_criteria": [
    {"criterion": "string, falsifiable", "owner_to_monitor": "string"}
  ],

  "next_action": {
    "action": "string, ≤100 chars, imperative voice",
    "owner": "string",
    "deadline": "YYYY-MM-DD"
  },

  "signatures": [
    {
      "seat_id": "string",
      "verdict": "proceed" | "kill" | "conditional",
      "confidence_raw": 0.0,
      "confidence_recalibrated": 0.0
    }
  ],

  "metadata": {
    "persona_hashes": {"seat_id": "hash"},
    "model_ids": {"seats": "string", "synthesis": "string"},
    "seed": "int",
    "wall_clock_seconds": 0.0,
    "llm_cost_usd": 0.0,
    "unanimous": true|false,
    "forced_dissent_triggered": true|false
  }
}
```

## 3. Field discipline

- **verdict_reasoning** synthesizes *the case for the winning verdict*. It is not a summary of the deliberation. It is the argument as it stands at the end of the meeting. Past disagreements are referenced only where they materially affect the standing argument.
- **dissent_summary** is the minority's strongest case, stated charitably. It is never a strawman. If there is no real dissent (rare), the forced-dissent step produces it.
- **kill_criteria** are conditions that, if observed, would flip the verdict. They are *measurable* and *time-bounded*. "Customer acquisition cost exceeds 1200 USD by month 6" is a kill criterion. "Things go badly" is not.
- **next_action** is exactly one. Not a list. The board does not produce roadmaps; it produces the next step.

## 4. Rendering

The memo persists as JSON. For human consumption it renders to Markdown via `src/sboard/memo/formatter.py`. The Markdown form is what the founder reads. Example layout in `tests/fixtures/golden-memos/example-memo.md`.

## 5. Immutability

Once a memo is written, it cannot be edited. Period. If new information arrives, a new meeting is convened that references the prior memo. The audit trail is the value; mutability destroys it.

## 6. Chaining (post-MVP, but design for it now)

A future Post-Mortem memo will reference an earlier Idea Screen memo and score whether the kill criteria fired as predicted. The schema accommodates this via `metadata.references_memo_id`. MVP does not use it, but the field exists so the migration is trivial.

## 7. What the memo deliberately does not include

- Vote counts. (Confidence-weighted score is the only number.)
- Per-seat reasoning. (In the transcript, not the memo.)
- The full deliberation history. (Audit trail; not a decision artifact.)
- Recommendations beyond the next action. (One step, not a plan.)
- Hedges and qualifiers. (The board has a verdict. Hedging is for the transcript.)

## 8. The one-page test

Print the memo. If it does not fit on one US-letter page at 11pt, the synthesizer failed. Reject and resynthesize. Hard rule.
