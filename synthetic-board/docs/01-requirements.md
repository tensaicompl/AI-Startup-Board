# 01 — Requirements

## 1. Scope

The MVP runs **one** meeting type (Idea Screen) with **three** seats, accepts a petition, produces a memo, and emits an A/B-comparable artifact against a single-LLM baseline. Everything else is out of scope.

## 2. Functional requirements

### F1 — Petition intake
- The system accepts a petition in JSON conforming to `schemas/petition.schema.json`.
- A petition contains: `petition_id` (UUID v4), `submitted_at` (ISO-8601 UTC), `meeting_type` (one of: `idea_screen`), `pitch` (string, 50–1000 words), optional `context` (string, ≤2000 words), optional `attachments` (list of file URIs — ignored in MVP).
- Malformed petitions are rejected with a structured error, never silently coerced.

### F2 — Seat instantiation
- For each meeting, the system instantiates N isolated seat contexts. N is fixed by the meeting type (3 for Idea Screen).
- Each seat receives: its persona file (system prompt = Markdown body; structured config = YAML frontmatter), the petition, and only the memory permitted at the current protocol state.
- Seats never see each other's persona files. Seats never share context.

### F3 — Protocol execution
- The system executes the eight-state Idea Screen protocol exactly as defined in `docs/03-protocol.md`.
- Every state transition is governed by code-level guards. No state transition is conditional on an LLM judgment.
- Per-seat timeouts are configurable; default 60s. On timeout the seat is marked `abstain_timeout`.

### F4 — Anonymization
- Between `SEALED_OPENING` and `ANONYMIZED_REVEAL`, the chair shuffles seat outputs and re-labels them `Seat A / B / C` such that no recipient can infer the author from position or labeling.
- The identity map is held in chair state only. It is revealed to seats at `IDENTIFIED_REBUTTAL` and never before.

### F5 — Confidence-weighted voting
- Each voting seat returns a `confidence` value in `[0.0, 1.0]` at the vote step.
- The chair applies a recalibration function (specified in `docs/03-protocol.md`) to discount systemic overconfidence.
- The vote is tallied as a weighted sum. The verdict is the position with the highest weighted score.

### F6 — Forced dissent check
- If a vote is unanimous (all seats on the same verdict), the chair invokes the FORCED_DISSENT_CHECK state and selects one seat to produce a recorded minority position.
- The memo cannot be synthesized while `dissent_summary` is empty.

### F7 — Devil's Advocate role
- One seat per meeting holds the Devil's Advocate role (Munger in MVP — permanent).
- The DA must produce a steelmanned opposing case during `DEVILS_ADVOCATE` regardless of its own prior position.
- The DA holds a procedural veto on a "pass" verdict: a single forced extra rebuttal round. The DA cannot block a "kill" verdict.

### F8 — Memo synthesis
- The system produces a memo conforming to `schemas/memo.schema.json`.
- The memo body is ≤500 words. Fields outside the body (kill criteria, confidence spread, signatures) are structurally separate and not counted in the word limit.
- The memo is signed by every voting seat with that seat's individual confidence at vote time.
- The memo is immutable once written.

### F9 — Persistence and audit
- Every petition, full transcript, and memo is persisted to SQLite with append-only semantics.
- The transcript records every state transition, every seat input/output, the anonymization mapping, the vote tally, and timing.
- An auditor must be able to reconstruct any meeting in full from the database alone.

### F10 — CLI
- `sboard convene <petition.json>` runs a meeting end-to-end and writes the memo to disk.
- `sboard inspect <memo_id>` reads back the memo plus a human-readable transcript.
- `sboard ab <petition.json>` runs the board AND a single-LLM baseline, writes both memos with identity stripped, and emits a paired-rating CSV.

### F11 — Baseline comparator
- The baseline is a single Anthropic call to the seat default model with a fixed system prompt (provided in `tests/ab/baseline_prompt.txt`).
- The baseline receives the same petition. It is asked to produce a board-style memo in the same schema.
- The baseline output is stored in the same memo table, tagged `source: baseline`.

## 3. Non-functional requirements

### N1 — Determinism
- For a given petition + persona set + model version + protocol version, the *protocol path* must be deterministic. (LLM outputs themselves are stochastic; the framing, sequencing, anonymization, and voting math are not.)
- All randomness used by the chair (e.g., shuffling) must be seeded and the seed recorded in the transcript.

### N2 — Reproducibility
- Re-running a petition with the same inputs and same recorded seeds must produce the same protocol path and identical structural decisions, even if model outputs differ.

### N3 — Auditability
- Every artifact carries: protocol version, persona file hashes, model identifiers, seeds, timestamps.

### N4 — Cost guardrails
- Per-meeting LLM cost is logged. Default soft cap: 5 USD per meeting. Hard cap: 20 USD. Hard-cap excess aborts the meeting with a structured error.

### N5 — Latency
- Target wall-clock per Idea Screen meeting: under 90 seconds with default settings. This is a target, not a hard requirement.

### N6 — Privacy
- The MVP does not transmit data anywhere except the configured LLM provider. No telemetry. No analytics.
- API keys are read from environment variables, never written to disk.

### N7 — Code quality
- Python 3.11+. Strict typing (`mypy --strict`). `ruff` linting. ≥85% line coverage on the orchestrator and schemas. Seats may be lower since they're thin wrappers.

## 4. Out of scope for MVP

- Web UI. (CLI only.)
- Multi-user / multi-tenant.
- Persona learning from outcomes.
- Other meeting types.
- Other voting rules.
- Real-time streaming of seat outputs.
- Cross-meeting decision memory (the third memory store). Logged but not retrieved in MVP.
- Calibration dashboard beyond a CSV.

## 5. Acceptance criteria

The MVP is accepted when:

1. All ten tasks in `HANDOFF.md` complete with passing tests.
2. `sboard convene` runs end-to-end on the three sample petitions in `tests/fixtures/petitions/` and produces schema-valid memos.
3. `sboard ab` produces paired memos suitable for blind rating.
4. `mypy --strict` and `ruff` pass.
5. Coverage report shows ≥85% on orchestrator and schemas.
6. An auditor can reconstruct any test meeting from the SQLite DB.
