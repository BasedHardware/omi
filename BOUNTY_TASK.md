# Bounty Objective: [Bounty Proposal] Normalize datetime and ISO-8601 string timestamps across episode selection, writer, and conversation duration
Target: BasedHardware/omi Issue #22942
URL: https://github.com/BasedHardware/omi/issues/22942

## Issue Description
## Scope & Problem Statement

Several backend conversation and episode-note helpers make contradictory assumptions about whether `started_at`, `finished_at`, and `item.time` are `datetime` objects or ISO-8601 `str` values, and whether timestamps are timezone-aware or naive:

1. **`backend/utils/conversations/episode_selection.py` vs. `backend/utils/llm/episode_writer.py`:**
   - `_datetime()` in `episode_selection.py` calls `datetime.fromisoformat(value or '')`, raising `TypeError: fromisoformat: argument must be str` when `finished_at` or `item.time` is a `datetime` object.
   - Conversely, `episode_finish_local_iso(finished_at, user_tz)` in `episode_writer.py` accesses `finished_at.tzinfo` directly, raising `AttributeError: 'str' object has no attribute 'tzinfo'` when passed an ISO-8601 `str` (such as `EpisodeEvidence.finished_at` or raw Firestore dict payloads).
2. **`backend/testing/episode_notes/policy_replay.py`:**
   - `episode_route_signals` subtracts `datetime.fromisoformat(...)` values without normalizing naive vs. aware timestamps to UTC, raising `TypeError` when evidence items mix naive and offset-aware strings.
3. **`backend/utils/conversations/duration.py`:**
   - Although `duration.py` supports plain `dict` conversations via `_value()`, `_wall_duration_seconds` rejects ISO-8601 string `started_at`/`finished_at` fields (`if not isinstance(started_at, datetime)`) and `_as_utc` only checks `value.tzinfo is None` rather than `value.tzinfo is None or value.tzinfo.utcoffset(value) is None`.

## Deliverables & Verification
- Unify UTC-aware `datetime | str | None` coercion in `episode_selection._datetime`, `episode_writer.episode_finish_local_iso`, `episode_evidence.evidence_time`, `policy_replay.episode_route_signals`, and `duration._as_utc` / `_wall_duration_seconds`.
- Add unit tests in `backend/tests/unit/test_episode_writer.py` and `backend/tests/unit/test_conversation_duration.py`.
- **Implementation PR:** #22941

---
**Designated Payout Rail — EVM (Base / Arbitrum / Polygon USDC):** `0x484eD370DEd0D36e36AAD469a2AFE5D69B1A005D`


## Instructions for Kuro (Autonomous Solver):
1. Use skills: `systematic-debugging` and `code-review-and-quality`.
2. Inspect the repository structure, locate relevant files, and understand the bug/feature.
3. Apply the minimal, robust fix or implementation.
4. Run any existing test suites or linters in the workspace.
5. Ensure the fix adheres to the project's existing code style.
6. When done, output a summary of files modified and verification results.
