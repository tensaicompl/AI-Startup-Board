# Decision 004: Use time.monotonic() for wall_clock_start, not time.time()

**Date:** 2026-05-29
**Status:** accepted
**Context:** `MeetingState.wall_clock_start` was initialized with `time.time()` (wall-clock epoch seconds), but the duration computation in `synthesize_memo` and state timing code used `time.monotonic()` (monotonic counter seconds). The two clocks have completely different baselines — subtracting a `time.time()` value from a `time.monotonic()` value produces a large negative number. This caused a Pydantic validation error (`wall_clock_seconds >= 0`) on every meeting that reached memo synthesis.
**Decision:** Changed `wall_clock_start` default factory from `time.time` to `time.monotonic`. All duration computations now use the same clock.
**Alternatives considered:** (1) Change the duration computations to use `time.time()` — rejected because `time.monotonic()` is the correct clock for measuring elapsed durations (immune to system clock adjustments). (2) Store both clocks — unnecessary complexity.
**Consequences:** `wall_clock_seconds` in the memo metadata is a duration measured by the monotonic clock, not a wall-clock timestamp. The `created_at` field (which uses `datetime.now(timezone.utc)`) provides the absolute timestamp.
