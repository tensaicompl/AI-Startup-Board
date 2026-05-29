# Decision Records

This directory holds the record of every meaningful choice made during build that was not pre-specified in `HANDOFF.md` or the docs. One file per decision.

## Format

```
NNN-short-name.md

# Decision NNN: Short name

**Date:** YYYY-MM-DD
**Status:** proposed | accepted | superseded
**Context:** why the choice came up
**Decision:** what was chosen
**Alternatives considered:** what else was on the table, why rejected
**Consequences:** what this commits us to
```

## When to write one

- A library was swapped (e.g., Typer → Click).
- A spec ambiguity was resolved (e.g., what to do if all seats abstain).
- A non-obvious implementation choice (e.g., how anonymization is seeded).
- A spec violation made knowingly with reason.

## When not to

- Routine implementation (test added, function refactored).
- Bug fixes.
- Cosmetic changes.

The bar is: would the next developer want to know why this is the way it is?
