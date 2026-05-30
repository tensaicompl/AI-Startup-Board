# Decision 010: `advisor` / `gtm_only` default to false (schema accommodation)

**Date:** 2026-05-30
**Status:** accepted
**Context:** v2 introduces two non-voting seat roles distinguished by new
frontmatter booleans — `advisor` (broad non-voting advisor) and `gtm_only`
(participates only in the GTM stage). The three v1 persona files
(`operator-ceo`, `devils-advocate`, `outsider`) predate these fields and must
continue to validate and load **without modification**.

**The question (from the founder):** does `advisor`/`gtm_only` default to `false`
when absent via Pydantic defaults, or does it require schema accommodation?

**Answer: schema accommodation — not Pydantic.** `Persona` is a frozen
`@dataclass`, not a Pydantic model, and frontmatter validation is hand-rolled in
`persona_loader._validate_frontmatter`. The default-to-false is enforced by three
cooperating pieces:

1. **Loader default.** `load_persona` reads them with
   `advisor=bool(fm.get("advisor", False))` and
   `gtm_only=bool(fm.get("gtm_only", False))` — absent ⇒ `False`.
2. **Schema optionality.** `personas/_schema.yaml` lists `advisor` and `gtm_only`
   as **optional** properties (not in `required`), each documented `default: false`.
   So a file omitting them is still schema-valid.
3. **Validate-if-present.** `_validate_frontmatter` checks they are booleans only
   when present, so it never rejects a v1 file for their absence.

The `Persona` dataclass declares the two as non-default fields, but `load_persona`
is the sole construction site and always supplies them, so no dataclass default is
needed.

**Consequence:** the three v1 persona files validate and load unchanged, with
`advisor == False` and `gtm_only == False` (asserted by a test). v2 files set them
explicitly. Logged as Decision 010 per the founder's instruction that schema
accommodation (as opposed to a Pydantic default) be recorded.

**Alternative considered:** give the dataclass fields `= False` defaults and drop
the loader `.get` defaults — rejected as redundant (the loader is the only
constructor) and because the schema-level optionality is the piece that actually
lets unmodified v1 files validate.
