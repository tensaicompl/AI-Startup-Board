# 04 — Personas: Steering Files & The Chart Pipeline

## 1. The format

A persona file is **YAML frontmatter + Markdown body**, one file per seat. The frontmatter is structured config that the chair reads. The body is the system prompt the seat reads. They are two languages serving two readers.

```
---
# YAML frontmatter (read by the chair)
seat_id: operator-ceo
role: Operator-CEO
voting: true
... (full schema in personas/_schema.yaml)
---

# Markdown body (read by the LLM as system prompt)
You are the Operator-CEO seat...
[the actual steering content — worldview, voice, failure modes, decision protocol]
```

The body is what makes the seat a character. The frontmatter is what makes the chair able to do its job (route, weight, anonymize, validate).

## 2. Why this split

Two readers, two needs.

- The **chair** needs typed, validated, parseable config. It doesn't read prose. It needs to know: who votes, what's the recalibration factor, what phrases to redact during anonymization.
- The **LLM** needs prose. Voice, examples, failure modes, decision heuristics — the kind of material in the Pisces/Virgo file. Structured fields don't steer behavior; written character does.

Splitting these is the difference between a system that validates and a system that performs.

## 3. The chart pipeline

The chart is a **diversity-forcing seed**. It does not predict behavior; it constrains the persona-build to produce a structurally distinct worldview from the other seats. Two seats grounded in different charts will have different priors by construction.

Pipeline:

```
Real figure
  └─> Birth data (date, time if known, place)
       └─> pyswisseph computes the natal chart
            └─> Chart features extracted to YAML
                 (sun sign, moon sign, ascendant if known,
                  dominant element, dominant modality, key aspects)
                 └─> Archetypal compression (manual or LLM-assisted)
                      └─> Steering file (YAML + Markdown body)
```

The compression step is currently manual. It can be LLM-assisted with the prompt in `tools/build_persona.py` (to be implemented). Every generated file is reviewed by hand before going live.

### 3.1 The Rodden Rating discipline

Every chart-grounded persona file records a Rodden Rating in its `chart_signature.rodden_rating` field. This is the astrological community's data-quality grading. Use it as a provenance flag, not as a truth claim:

- **AA** — from a birth certificate. Highest reliability.
- **A** — from family or friend memory. Generally reliable.
- **B** — from a biography. Acceptable but lower confidence.
- **C** — speculative, no documented source. Caution.
- **DD** — "dirty data" — contradictory or untrustworthy.
- **X** — no birth time available.

The MVP cast uses **AA** for Welch and **A** for Buffett. The chart-pipeline rule: only AA and A figures qualify for a chart-grounded seat. B-rated figures need explicit founder approval. C, DD, and X figures fall back to a synthetic (chart-free) persona.

### 3.2 When the chart time is unknown

This is the common case for historical figures. Public sources rarely record birth time. The pipeline handles this:

- **Time-unknown chart** uses noon as a stand-in.
- **Ascendant and MC are omitted** from the YAML (they require a known time).
- **The body emphasizes the documented archetype** of the figure rather than reaching for chart-specific traits.
- A `time_known: false` flag is set; the chair logs this so it's traceable.

### 3.3 When there is no figure (the Outsider)

The Outsider is not a famous person. It is a specific imagined customer — picked from the founder's actual market.

- `grounding.type: synthetic`
- No chart. No `chart_signature` block.
- The body is a full biographical sketch: name (invented), age, role, employer-type, three life facts, one quote.
- The role of this seat is to inject a non-elite, ground-truth voice. The all-genius cast otherwise becomes its own echo chamber.

## 4. What goes in the Markdown body

Same structure as the Pisces/Virgo file. Required sections:

1. **Operating identity** — one-paragraph distillation. Who is this character at the core?
2. **Operating principles** — 5–8 numbered decision heuristics with sources and failure modes.
3. **Intuitive faculty** (or analytical faculty, or whatever the dominant cognitive mode is) — how this character receives information.
4. **Voice and prose style** — sentence length, diction, hedging, lists, calibration phrases the character uses, phrases they never use.
5. **Decision protocol** — the step-by-step internal procedure for non-trivial decisions.
6. **Failure modes and guardrails** — predictable shadow patterns; what the character must monitor in itself.
7. **Behavioral defaults** — a quick-reference table mapping situations to defaults.

These sections are not optional. They are the load-bearing parts. The Markdown body that lacks them produces a generic agent in a costume.

## 5. The schema (summary; full at `personas/_schema.yaml`)

```yaml
# Identity
seat_id: string, snake_case, unique
role: string                          # "Operator-CEO", "Devil's Advocate", etc.
voting: bool                          # voting seat?
voting_weight: float [0.5, 1.5]       # multiplier on confidence in tally
permanent: bool                       # rotates between meetings or stays?
is_devils_advocate: bool

# Grounding
grounding:
  type: natal_chart | synthetic
  source_figure: string | null
  birth:                              # only if natal_chart
    date: YYYY-MM-DD
    time: HH:MM | "12:00"             # noon if unknown
    time_known: bool
    place: string
    coordinates: [lat, lon]

# Chart signature (computed, present if natal_chart)
chart_signature:
  sun: string
  moon: string
  ascendant: string | null
  dominant_element: string
  dominant_modality: string
  key_aspects: [string]
  archetype_summary: string

# Worldview vector (structurally typed for diversity scoring)
worldview:
  time_horizon: short | medium | long
  risk_appetite: low | medium | high
  optimization_target: growth | margin | durability | speed | learning | quality
  evidence_weight: empirical | conceptual | intuitive
  decision_speed: snap | deliberate | exhaustive
  failure_response: pivot | harden | escalate | quit
  primary_lens: operations | story | numbers | tech | customer | regulation

# Voice
voice:
  sentence_length: short | medium | long
  register: string                    # free-form descriptor
  forbidden_phrases: [string]         # phrases the seat must not use
  signature_phrases: [string]         # phrases that ID the seat — redacted when anonymizing
  redaction_aliases: [string]         # additional terms to redact in anonymization

# Protocol behavior
protocol:
  sealed_opening_max_words: int
  rebuttal_max_words: int
  recalibration_factor: float [0.5, 1.0]  # discount on confidence_raw

# Runtime guardrails
must_produce: [string]                # required structural outputs every turn
must_not: [string]                    # behaviors to avoid

# Provenance
provenance:
  built_by: string
  built_at: ISO-8601
  reviewed_by: string
  reviewed_at: ISO-8601
  file_version: string                # semver
```

## 6. The diversity check

Before a meeting runs, the chair computes a diversity score over the seated personas. The score is the count of distinct values across each worldview vector axis. The minimum acceptable score is `n_seats - 1` for at least 4 of the 7 axes. If the score is below threshold, the chair refuses to convene and emits a structured error.

This stops the obvious failure: three seats with the same worldview produce three near-identical openings.

## 7. Provenance and review

Every persona file carries a `provenance` block. Hash-pinned in the transcript. Hand-reviewed before going live. The reviewer signs the `reviewed_by` field. No persona file enters the active seat pool without review.

## 8. The compression discipline

When writing the Markdown body, the test is: would the source figure recognize themselves? The output should be sharp, opinionated, and recognizable, not a generic LinkedIn version of the role. If the body could be swapped between two persona files without anyone noticing, both files have failed.

Concretely, every body must contain:
- At least three specific, characteristic moves the figure was known for.
- At least three things the figure was known to refuse.
- A voice sample of ≥100 words that could not be mistaken for any other seat in the cast.

If any of these is missing, the file is not ready.
