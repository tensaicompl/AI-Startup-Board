# Decision 002: Seat identity flows explicitly through the LLMClient interface, not via prompt sniffing

**Date:** 2026-05-29
**Status:** accepted
**Context:** The initial MockClient tried to determine which seat was calling by pattern-matching keywords ("operator", "devil's advocate", etc.) against the system prompt text. This was fragile by construction — the keywords collide with prose in the persona Markdown bodies (e.g., "operator experience" appearing in the DA's system prompt matched "operator-ceo" first). Three attempts at fixing the keyword ordering all failed or would succeed by accident.

The seat runner already knows the seat_id and the stage at call time. Making the client guess this information from prose is an architectural error.

**Decision:** Extend the `AnthropicClient.call()` signature to accept `seat_id: str` and `stage: str` as keyword arguments. The real Anthropic client ignores these (they are metadata, not part of the API call). The MockClient uses them directly for routing. The `_extract_seat_id` method is deleted entirely. The seat runner passes both values on every call.

**Alternatives considered:** (1) Improving the keyword matching heuristic — rejected because any prose-based heuristic is fragile by construction and will break on new personas. (2) Passing seat_id as a separate init-time parameter on a per-seat client wrapper — rejected because it over-complicates the interface for no gain.

**Consequences:** The LLMClient interface now carries seat_id and stage as explicit context. This is also more honest about what the mock needs and will simplify integration tests that want different seats returning different verdicts on the same petition.
