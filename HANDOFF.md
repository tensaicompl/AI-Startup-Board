# HANDOFF: Synthetic Advisory Board — MVP

**Read this first. Read it whole. Then read the docs in order.**

You are building the MVP of a synthetic startup advisory board: a multi-agent system where 3 persona-steered LLM seats deliberate on a founder's question under a deterministic protocol and produce a one-page signed memo.

This is the smallest version of the thesis. Do not build more than this is. The reason it is scoped this small is a single A/B test that must run before any expansion. The test is the gate.

---

## 1. The verdict you must hit

The MVP wins or loses on one measurement: in a blind paired-rating test against a well-prompted single-LLM baseline, does the board produce **sharper dissent** and **clearer kill criteria**? If yes, the concept proceeds. If no, the concept dies. Build for the test.

## 2. What you are building (MVP scope, frozen)

- One meeting type: **Idea Screen**. Founder submits a one-paragraph startup pitch. Board returns a one-page memo: verdict, dissent, kill criteria, next action.
- Three seats: **Operator-CEO** (Andy Grove), **Devil's Advocate** (Charlie Munger), **Outsider** (synthetic customer — no chart).
- One orchestrator: **deterministic Python state machine**. Not an agent. Never an agent.
- One memo schema. One transcript schema. One persona-file format (YAML frontmatter + Markdown body).
- One eval harness: blind A/B vs. a single-LLM baseline.

**What you are not building yet:** the full 7-seat cast, the other 5 meeting types, persistent web UI, multi-tenant, learning loops, calibration dashboard beyond a single CSV. All of that lives in `docs/08-roadmap.md`. Resist it.

## 3. Stack — already chosen

- **Python 3.11+**
- **LangGraph** for the state machine (graph nodes = protocol steps; deterministic edges).
- **Anthropic Python SDK** for seat calls. Default model: `claude-opus-4-7` for seats, `claude-sonnet-4-6` for memo synthesis. Both swappable via env.
- **pyswisseph** for natal chart computation (already used in the persona-build step).
- **Pydantic v2** for all schema validation.
- **SQLite** for memory and audit trail in MVP. Postgres is post-MVP and earns its place by data volume, not by aesthetics.
- **pytest** for tests.
- **uv** for env and packaging (fall back to pip if uv unavailable).

If you want to deviate from any of these, stop and write the case in `docs/decisions/` first. Don't silently swap libraries.

## 4. Read order

1. `docs/01-requirements.md` — what the system must do.
2. `docs/02-architecture.md` — layers, components, why each call was made.
3. `docs/03-protocol.md` — the state machine in full. This is the spine.
4. `docs/04-personas.md` — the steering file format and the chart pipeline.
5. `docs/06-memo.md` — the output artifact spec.
6. `docs/07-evaluation.md` — the A/B gate.
7. `personas/_schema.yaml` — the YAML schema. Validate every persona file against it.
8. `personas/operator-ceo.md`, `personas/devils-advocate.md`, `personas/outsider.md` — the three seats for the MVP.
9. `protocols/idea-screen.yaml` — the meeting protocol.
10. `schemas/*.json` — JSON Schemas for every structured artifact.

## 5. Task sequence

Work in this order. Do not skip ahead. Each task ends with a runnable test.

**Task 1 — Project scaffolding.** Create `pyproject.toml`, basic package layout under `src/sboard/`, install dependencies, get `pytest` running on a placeholder test. Pin versions.

**Task 2 — Schemas.** Implement Pydantic models matching `schemas/petition.schema.json`, `schemas/seat-output.schema.json`, `schemas/memo.schema.json`. Round-trip JSON tests for each.

**Task 3 — Persona loader.** Parse persona files (YAML frontmatter + Markdown body). Validate frontmatter against `personas/_schema.yaml`. Body becomes the system prompt verbatim. Unit-test against the three sample personas.

**Task 4 — Seat runner.** A single function that takes (persona, state, message) → structured output. Uses Anthropic SDK. Enforces JSON output via tool-use or structured output mode. Retries once on malformed output, then marks seat as `malformed` and returns abstain. Test with mocks.

**Task 5 — State machine.** Implement the eight-state graph in LangGraph (see `docs/03-protocol.md`). Each state has explicit entry/exit guards. The chair is code, not an agent. Test with deterministic mock seats first, then with real seats.

**Task 6 — Anonymization.** Between SEALED_OPENING and ANONYMIZED_REVEAL, strip seat identity and shuffle. The mapping is held in chair state, not exposed to seats until REBUTTAL. Test that no seat ever sees identified peers in REVEAL.

**Task 7 — Memo synthesis.** Deterministic template fill from structured state. One LLM call to write prose for `verdict_reasoning` and `dissent_summary` only — every other field is filled by code. Hard one-page limit (≤500 words memo body, enforced at the schema level).

**Task 8 — Persistence.** SQLite tables for petitions, transcripts, memos. Immutable. Append-only. No updates. Test the audit trail.

**Task 9 — CLI.** `sboard convene <petition.json>` runs the protocol end-to-end and writes the memo to disk. `sboard inspect <memo_id>` shows the full transcript.

**Task 10 — The A/B harness.** `sboard ab <petition.json>` runs the board AND a single-LLM baseline on the same petition, writes both memos to disk anonymized. Blind-rater CSV template included. **This task is non-negotiable.** Without it the MVP is incomplete regardless of how good the rest looks.

## 6. Done means

- All ten tasks complete with passing tests.
- A working `sboard convene` on the three sample petitions in `tests/fixtures/petitions/`.
- A working `sboard ab` producing paired outputs for blind rating.
- `make test` green. `make lint` green. Type checks clean (`mypy --strict`).
- `docs/decisions/` contains a written record of every choice you made that wasn't already specified.

## 7. The discipline

Two rules you will be tempted to break. Don't.

**Rule one: the chair is code.** The first time something feels easier "if a model just decided this step" — stop. That instinct is the bug. The whole point of the architecture is to remove model judgment from procedural decisions. Hard-code the protocol.

**Rule two: don't expand the cast.** Three seats is enough to prove or kill the thesis. A fourth seat is research; finish the A/B first.

## 8. Resolved preconditions (do not re-litigate)

The founder has resolved the following. Build accordingly.

- **API key**: not required until the live A/B run. All build tasks (1–9) run against mocks. Task 10 (the A/B harness) is the first point where a real `ANTHROPIC_API_KEY` is needed. Until then, every test uses fakes that conform to the seat-output schema. The founder will provide the key at the Task 10 boundary. Implement an `AnthropicClient` interface and a `MockClient` that returns deterministic, schema-valid outputs keyed off the persona and stage; this is the contract the rest of the system codes against.
- **Personas**: the MVP cast uses figures with documented birth times. **Operator-CEO is Jack Welch** (Rodden AA — birth certificate confirmed; 19 Nov 1935, 10:30 EST, Peabody MA; Sun Scorpio, Moon Virgo, ASC Capricorn). **Devil's Advocate is Warren Buffett** (Rodden A — from-memory source rated reliable per Rodden system; 30 Aug 1930, 15:00 CST, Omaha NE; Sun Virgo, Moon Sagittarius, ASC Sagittarius). The Outsider remains synthetic and chart-free. Files are in `personas/`.
- **IP/parody stance**: internal use only for the foreseeable future. The product surface (CLI output, memo headers, any UI) refers to seats by role name (`operator-ceo`, `devils-advocate`, `outsider`) — never by source-figure name. Source-figure names appear only in `personas/*.md` frontmatter and in audit-trail metadata. Do not surface "Welch" or "Buffett" in any user-visible string. The memo formatter strips these from `metadata.persona_hashes` display output.

## 9. Things to ask only if encountered

- Petition pool for the A/B test (Task 10). Three sample petitions are in `tests/fixtures/petitions/`; the founder will supply or generate the other 17 before the gate runs.
- Anything that requires deviating from a frozen spec. Stop, ask, log a decision record under `docs/decisions/`.

## 10. After MVP — do not touch yet

`docs/08-roadmap.md` lists everything after the gate fires. If the A/B test wins, expand to 5 seats, add Pre-Mortem, build calibration tracking. If it loses, the project ends. Either way: not your call to make, and not during this build.

---

**Build the smallest thing that can be killed by evidence. Ship it. Read the result honestly.**
