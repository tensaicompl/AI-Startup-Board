# 02 — Architecture

## 1. Layers

Five layers, strict separation. Each is replaceable without touching the others.

```
┌─────────────────────────────────────────────────────────┐
│  PRESENTATION                                            │
│  CLI: sboard convene | inspect | ab                      │
└─────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────┐
│  ORCHESTRATION  (deterministic, no LLM judgment)         │
│  LangGraph state machine = the Chair                     │
│  States: CONVENE → SEALED_OPENING → ANONYMIZED_REVEAL →  │
│          IDENTIFIED_REBUTTAL → DEVILS_ADVOCATE →         │
│          CONFIDENCE_VOTE → FORCED_DISSENT_CHECK →        │
│          MEMO_SYNTHESIS                                  │
└─────────────────────────────────────────────────────────┘
                          │
        ┌─────────────────┼─────────────────┐
        ▼                 ▼                 ▼
┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│  SEATS       │  │  SCHEMAS     │  │  PROTOCOLS   │
│  (LLM agents)│  │  (Pydantic + │  │  (YAML defs) │
│  Isolated    │  │  JSON Schema)│  │              │
└──────────────┘  └──────────────┘  └──────────────┘
        │
        ▼
┌─────────────────────────────────────────────────────────┐
│  MEMORY  (three stores)                                  │
│  persona (per-seat, immutable)                           │
│  episodic (per-meeting transcript)                       │
│  semantic (cross-meeting decisions — logged not used MVP)│
└─────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────┐
│  PERSISTENCE  (SQLite, append-only)                      │
│  petitions | transcripts | memos                         │
└─────────────────────────────────────────────────────────┘
```

## 2. The core design decision: the chair is code

The single most important architectural decision is that the orchestrator — the chair — is a deterministic state machine, not an LLM agent. Every state transition is a code-level guard. No state transition asks a model for judgment.

This is non-obvious and tempting to violate. The pull will be: "the synthesis step would be cleaner if a chair-agent decided what's important." That is exactly the failure mode the research warns about. An LLM chair inherits the same sycophancy and identity bias it is supposed to police. See Choi et al. 2025 on identity bias and CONSENSAGENT 2025 on consensus drift.

The chair's job is **procedural**: route, anonymize, time-box, tally, enforce dissent rules, assemble. The seats' job is **substantive**: take positions, argue, vote. Confusing these is the bug.

## 3. Components

### 3.1 Chair (`src/sboard/chair/`)
- `state_machine.py` — LangGraph definition of the eight-state graph.
- `states.py` — one function per state. Pure-ish: takes a `MeetingState`, returns the next state and updated context.
- `anonymizer.py` — shuffles + relabels seat outputs; holds the identity map.
- `voting.py` — confidence recalibration and weighted tally math.
- `dissent_guard.py` — detects unanimity, triggers FORCED_DISSENT_CHECK.

### 3.2 Seats (`src/sboard/seats/`)
- `seat.py` — generic Seat class. Stateless. Takes (persona, state, prompt) and returns structured output.
- `persona_loader.py` — parses YAML frontmatter + Markdown body, validates against schema.
- `output_schema.py` — Pydantic models for every output shape (opening, rebuttal, vote, etc.).
- `llm_client.py` — thin wrapper over Anthropic SDK with retry and JSON-mode enforcement.

### 3.3 Memo (`src/sboard/memo/`)
- `synthesizer.py` — deterministic template fill + one constrained LLM call for prose fields.
- `schema.py` — Pydantic model for the memo.
- `formatter.py` — renders memo to Markdown for human reading.

### 3.4 Memory (`src/sboard/memory/`)
- `persona_store.py` — read-only access to persona files; cached and content-hashed.
- `episodic_store.py` — SQLite-backed transcript log.
- `semantic_store.py` — placeholder in MVP (logs only, no retrieval).

### 3.5 Persistence (`src/sboard/db/`)
- `models.py` — SQLAlchemy models (or raw SQLite — either works).
- `migrations/` — schema versions.
- All inserts are append-only. No updates, no deletes, ever.

### 3.6 CLI (`src/sboard/cli.py`)
- Typer-based. Three commands: `convene`, `inspect`, `ab`.

## 4. Data flow (single meeting)

1. CLI reads a petition file. Validates against `petition.schema.json`.
2. Chair creates a `MeetingState`. Records protocol version, persona file hashes, model identifiers, seed.
3. Chair runs the state machine. Each state writes to the transcript.
4. After `MEMO_SYNTHESIS`, the memo is validated against `memo.schema.json`, persisted, and returned.
5. CLI writes the memo to disk in Markdown form and prints the path.

## 5. Memory architecture (and why three stores)

A single flat store is the canonical mistake. It produces echo chambers when seats retrieve their own past positions and anchor on them. CoALA (Sumers et al., Princeton) and MIRIX both argue for compositional memory. We follow that pattern.

- **Persona memory** is the steering file. Stable. Read at seat instantiation only. Hash-pinned.
- **Episodic memory** is the transcript of the current meeting. Each seat sees only the slice the protocol permits at the current state.
- **Semantic memory** is the cross-meeting decision ledger. MVP logs but does not retrieve. Post-MVP it surfaces base rates and prior verdicts on related petitions — but never during `SEALED_OPENING`. The fresh-eyes draft is the structural antidote to drift, and it must precede any retrieval.

## 6. Anti-sycophancy: layered, structural

Every defense is structural, not prompt-based. Prompt-based "be critical" fails under load. Structural defenses do not.

1. **Anonymization between rounds** — Choi et al. 2025: this single intervention "eliminates identity bias almost entirely."
2. **Confidence-weighted voting with recalibration** — ReConcile (ACL 2024): weighted beats majority; recalibration counters overconfidence.
3. **Permanent Devil's Advocate seat with veto-on-pass** — DEBATE; council-review.
4. **Forced dissent check on unanimity** — unanimous outputs are bugs, not features.
5. **Persona diversity by construction** — chart-grounded steering files produce structurally different priors. ChatEval (ICLR 2024): identical role descriptions degrade output.
6. **Runtime metrics** — log Identity Bias Coefficient (IBC), position-change rate after reveal, reasoning-footprint overlap, disagreement rate over rounds. These are the sycophancy meters.

## 7. Cost and latency

LLM calls per Idea Screen meeting (3 seats):
- SEALED_OPENING: 3 calls
- ANONYMIZED_REVEAL: 3 calls (each seat critiques peers)
- IDENTIFIED_REBUTTAL: ≤3 calls (only seats who changed position speak)
- DEVILS_ADVOCATE: 1 call
- CONFIDENCE_VOTE: 3 calls
- FORCED_DISSENT_CHECK: 0–1 calls (only on unanimity)
- MEMO_SYNTHESIS: 1 call

Total: 14–15 LLM calls per meeting. With `claude-opus-4-7` at typical pricing, well under the 5 USD soft cap.

## 8. What this architecture does not include and why

- **No agentic chair.** See §2.
- **No retrieval at SEALED_OPENING.** Anti-echo.
- **No seat-to-seat direct messaging.** All inter-seat communication flows through the chair, anonymized when required.
- **No streaming.** Adds complexity, slows synthesis, no MVP value.
- **No multi-provider routing.** Anthropic only for MVP. Diversity is bought via persona, not model. (Post-MVP can add model diversity.)
- **No web UI.** CLI is sufficient to run the A/B test.
