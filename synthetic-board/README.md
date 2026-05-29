# sboard — Synthetic Advisory Board

A multi-agent LLM system that convenes a small board of persona-steered seats, runs them through a deterministic deliberation protocol, and produces a one-page signed memo with verdict, dissent, kill criteria, and next action.

This is the MVP. It does one meeting type (Idea Screen) with three seats. It is built to be killed by an A/B test against a single-LLM baseline. If it doesn't win that test, it dies.

## Why this exists

A single LLM averages. Asked for board feedback, it produces five hedges in one paragraph. A board with structurally diverse personas, anonymized peer review, confidence-weighted voting, and a forced devil's-advocate pass produces *the case for*, *the case against*, and *a decision*. That is the artifact a single agent cannot make.

The research backing this design is collected in `docs/02-architecture.md`. The short version: anonymization kills identity bias, confidence-weighted voting beats majority, and persona diversity is load-bearing.

## What is in this repo

```
.
├── HANDOFF.md              Read this first if you are building the system.
├── README.md               You are here.
├── docs/                   The full specification.
├── personas/               Steering files for each seat.
├── protocols/              Meeting-type definitions.
├── schemas/                JSON Schemas for every structured artifact.
├── src/                    Source (populated during build).
└── tests/                  Tests and the A/B eval harness.
```

## Quick start (once built)

```bash
uv sync
export ANTHROPIC_API_KEY=...
sboard convene tests/fixtures/petitions/example.json
sboard ab tests/fixtures/petitions/example.json
```

## Status

Pre-build. Specs frozen. Build instructions are in `HANDOFF.md`.

## License & IP note

Persona files reference real historical figures (Grove, Munger) as worldview anchors. The product surface uses role names only (Operator-CEO, Devil's Advocate). Internal use only until legal review of right-of-publicity clears the named approach.
