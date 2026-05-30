# Decision 011: MemoV2 `confidence_weighted` ceiling is 7.5, not 5.0

**Date:** 2026-05-30
**Status:** accepted
**Context:** Task v2.4 asked to sanity-check whether the MemoV2
`confidence_weighted` cap of 5.0 is the correct ceiling for five voting seats.

**The math.** `tally_votes` accumulates, per seat voting the winning verdict:

```
score += recalibrate(confidence_raw, recalibration_factor) * voting_weight
```

with these bounds from the schemas:
- `confidence_raw ∈ [0, 1]` (Vote schema)
- `recalibration_factor ∈ [0.5, 1.0]` (persona schema) ⇒ `recal = raw × factor ≤ 1.0`
- `voting_weight ∈ [0.5, 1.5]` (persona schema)

So the **per-seat** contribution is `recal × weight ≤ 1.0 × 1.5 = 1.5`, and with
**five** voting seats all backing the winning verdict the ceiling is
`5 × 1.5 = 7.5`.

**Finding.** The "5.0" figure assumed `recalibration_factor` (max 1.0) was the
only multiplier and **omitted `voting_weight`**, whose schema maximum is 1.5. The
note that "recalibration factors can exceed 1.0" is also slightly off — the
persona schema caps `recalibration_factor` at 1.0, so `recal` itself never exceeds
1.0; the headroom above 5.0 comes entirely from `voting_weight`.

**Decision.** Set the MemoV2 `confidence_weighted` ceiling to **7.5** (Pydantic
`le=7.5` and JSON Schema `maximum: 7.5`). The current v2 personas all use
`voting_weight: 1.0`, so the practical maximum today is 5.0 — but the schema
permits 1.5, and a degenerate unanimous, max-confidence, max-weight vote would
otherwise fail memo validation. The cap should bound the architecture, not the
current persona file values.

**Alternatives considered:** (1) Keep 5.0 and additionally cap `voting_weight` at
1.0 in the persona schema — rejected; weight differentiation is a deliberate v1
design lever (`voting_weight ∈ [0.5, 1.5]`), not something to remove to make a memo
cap convenient. (2) Compute the cap dynamically from the seated roster's weights —
rejected as over-engineering for a static schema bound; the fixed architectural
maximum (7.5) is simpler and correct.
