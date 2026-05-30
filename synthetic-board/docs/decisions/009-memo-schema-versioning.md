# Decision 009: Memo schema versioning (v1/v2)

**Date:** 2026-05-30
**Status:** accepted
**Context:** Task v2.1 introduces a five-stage v2 memo body while v1 must stay
runnable (frozen scope: "v1 stays runnable, v2 becomes default"). Persisted v1
memos already exist in audit DBs (from the live A/B runs) and have neither a
`schema_version` field nor the v2 body. (Decision 008 is reserved for the v2
chart-grounding relaxation in Task v2.2.)

**Decision:**

1. **v1 `Memo` is left byte-for-byte unchanged.** No field added, no constraint
   touched — every existing v1 memo, test, and persisted row keeps validating.
   The v1 JSON Schema is copied verbatim to `schemas/memo-v1.schema.json`.

2. **`MemoV2` is a separate model** carrying the discriminator `schema_version:
   Literal["2.0"]` (default `"2.0"`) plus the five body fields (`idea_analysis`,
   `verdict_reasoning`, `vision`, `dissent_summary`, and optional `gtm_analysis`).
   `confidence_weighted` cap is raised 3.0 → 5.0 (five voting seats). Body word
   budgets are enforced by the synthesizer (Task v2.5); the Pydantic char caps are
   generous guards sized to the word targets.

3. **Manual version dispatch, not a Pydantic discriminated union.** `parse_memo`
   routes by `schema_version == "2.0"` OR presence of the v2-only `idea_analysis`
   field; anything else is v1. A built-in `Field(discriminator=...)` union was
   rejected because it requires the discriminator key present in the raw input —
   which the already-persisted, field-less v1 memos lack. The manual dispatcher
   loads old v1 data, tagged v2 data, and untagged-but-v2-shaped data correctly.

4. **`gtm_analysis` is present iff verdict != kill**, enforced in two places that
   must agree:
   - Pydantic `model_post_init`: kill ⟹ `gtm_analysis is None`; non-kill ⟹ not None.
   - JSON Schema `if/then/else`: kill ⟹ `gtm_analysis` is `null`/absent; non-kill ⟹
     required string. The schema accepts **null** (not just absence) on kill
     because Pydantic's `model_dump_json` emits `"gtm_analysis": null` for kill
     memos — the two representations must validate identically.

5. **`schemas/memo.schema.json` is now the v2 schema (default)**; v1 lives at
   `schemas/memo-v1.schema.json`. The v2 protocol config is
   `protocols/idea-screen-v2.yaml` (11 states); v1's `idea-screen.yaml` is
   untouched. Neither YAML is loaded by code yet (reference config); the state
   machine consumes the v2 flow in Task v2.4.

**Alternatives considered:** (1) Add a defaulted `schema_version` to v1 `Memo` and
use a real discriminated union — rejected: it still can't validate field-less
persisted v1 data, and it perturbs the frozen v1 surface. (2) Express the gtm/kill
rule only in Pydantic — rejected: the JSON Schema is a published contract and must
encode the same invariant. (3) Exclude `None` on dump to avoid the null case —
rejected: changing global dump behavior is invasive; accepting null in the schema
is local and explicit.

**Consequences:** v1 and v2 memos coexist in one append-only store; `parse_memo`
is the single load path callers will adopt as v2 memos start being written
(Task v2.4/2.5). Round-trip + JSON-Schema-conformance tests cover both versions
and the gtm/kill conditional in both representations.
