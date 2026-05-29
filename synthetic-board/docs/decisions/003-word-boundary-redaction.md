# Decision 003: Redaction uses word boundaries, not bare substring matching

**Date:** 2026-05-29
**Status:** accepted
**Context:** The operator-ceo persona has "GE" as a redaction alias (for General Electric). The original `redact_text()` used `re.sub(re.escape(term), "[REDACTED]", ...)` which is a bare substring match. This corrupted normal English words: "target" became "tar[REDACTED]t", "budget" became "bud[REDACTED]t", "urgency" became "ur[REDACTED]ncy". Beyond producing garbled text, the corruption pattern itself is an identity signal — seeing `tar[REDACTED]t` in an anonymized output reveals that a persona with "GE" on its redaction list authored it, partially defeating anonymization.
**Decision:** Changed `redact_text()` to use `\b` word boundaries: `r"\b" + re.escape(term) + r"\b"`. This matches standalone "GE" but not "ge" inside "target". Possessive forms like "Berkshire's" still match because `\b` falls between "Berkshire" and the apostrophe.
**Alternatives considered:** (1) Removing short aliases from redaction lists — rejected because "GE" is a legitimate identity marker when standalone. (2) Requiring aliases to be >=4 characters — too restrictive; "GE" and "IBM" are real identifiers.
**Consequences:** Redaction is less aggressive but more correct. A seat that writes "GE was my employer" gets redacted; a seat that writes "target market" does not. Signature phrases (which tend to be multi-word) are unaffected.
