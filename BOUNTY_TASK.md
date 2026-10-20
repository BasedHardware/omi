# Bounty Objective: [Bounty proposal] fix(mcp_oauth): coerce naive and ISO-8601 timestamps to UTC in grant and token paths ($50 proposed)
Target: BasedHardware/omi Issue #22660
URL: https://github.com/BasedHardware/omi/issues/22660

## Issue Description
## Problem

In `backend/database/mcp_oauth.py`, several OAuth grant, authorization code, access token, and refresh token operations compare or sort Firestore-stored timestamp fields directly against `datetime.now(timezone.utc)` or `datetime.min.replace(tzinfo=timezone.utc)`:

1. **`_grant_recency_key` / `list_user_grants`**:
   - `_grant_recency_key` returns `candidate` whenever `isinstance(candidate, datetime)` without checking `candidate.tzinfo`, and falls back to `datetime.min.replace(tzinfo=timezone.utc)` when neither `updated_at` nor `created_at` is a `datetime` (e.g. an ISO-8601 string or `None`).
   - When `list_user_grants` sorts grants (`grants.sort(key=_grant_recency_key, reverse=True)`) across records where one grant has an offset-naive `datetime` and another has an offset-aware `datetime` (or ISO-8601 string fallback), Python raises `TypeError: can't compare offset-naive and offset-aware datetimes`.
2. **`consume_authorization_code` & `exchange_authorization_code_for_tokens`**:
   - Both compare `expires_at <= now` after only checking `isinstance(expires_at, datetime)`. If `expires_at` is stored as a naive `datetime`, `expires_at <= now` raises `TypeError: can't compare offset-naive and offset-aware datetimes`. If `expires_at` is stored as an ISO-8601 string, valid authorization codes are falsely rejected as expired.
3. **`_is_unexpired`, `validate_access_token`, & `rotate_refresh_token`**:
   - `_is_unexpired` compares `expires_at > _utcnow()` without normalizing naive `datetime` objects or parsing ISO-8601 strings, crashing with `TypeError: can't compare offset-naive and offset-aware datetimes` on naive `expires_at`.
   - `validate_access_token` checks `isinstance(expires_at, datetime)` and returns `expires_at.astimezone(timezone.utc).isoformat()`, which omits ISO-8601 string timestamps.
   - `rotate_refresh_token` checks `isinstance(used_at, datetime)` and computes `(now - used_at).total_seconds()`, which raises `TypeError: can't subtract offset-naive and offset-aware datetimes` when `used_at` is a naive `datetime` and skips grace-window replay protection when `used_at` is an ISO-8601 string.

## Proposed Fix

- Introduce `_coerce_utc_datetime(value)` in `backend/database/mcp_oauth.py` to normalize naive `datetime` values (assuming UTC), non-UTC aware `datetime` values (`.astimezone(timezone.utc)`), and ISO-8601 timestamp strings (including `Z` suffixes) into timezone-aware UTC `datetime` objects.
- Use `_coerce_utc_datetime` in `_grant_recency_key`, `consume_authorization_code`, `exchange_authorization_code_for_tokens`, `_is_unexpired`, `validate_access_token`, and `rotate_refresh_token`.
- Add unit tests in `backend/tests/unit/test_mcp_oauth.py` covering mixed naive/aware/ISO-8601 timestamps across grant sorting, authorization code consumption/exchange, access token validation, and refresh token rotation.

Bounty settlement address (Base Mainnet USDC): `0xb9f3765aeb1974c27a193463f655a1a57b3aec94`


## Instructions for Kuro (Autonomous Solver):
1. Use skills: `systematic-debugging` and `code-review-and-quality`.
2. Inspect the repository structure, locate relevant files, and understand the bug/feature.
3. Apply the minimal, robust fix or implementation.
4. Run any existing test suites or linters in the workspace.
5. Ensure the fix adheres to the project's existing code style.
6. When done, output a summary of files modified and verification results.
