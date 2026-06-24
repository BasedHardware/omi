# Memory `/v3` archive + short-term default visibility readiness

Status: **BLOCKED** (pre-runtime proof only).

This slice defines a local, read-only readiness contract for the future `GET /v3/memories` default visibility path. It does not wire runtime behavior and does not edit `backend/routers/memories.py`.

## Contract proven locally

- Archive/L1 evidence is unavailable by default.
- Archive or historical context requires explicit query opt-in.
- Stale Short-term/Working memory is not default-visible.
- Fresh Short-term memory is default-visible only when it is source-backed projection output.
- Long-term active stable synthesis remains default-visible as a stable profile fact.
- Unknown visibility, unknown lifecycle, unknown source freshness, hidden/rejected records, and unbacked Short-term records fail closed.
- Enrolled canonical-memory failures must not use legacy fallback or merge.

## Non-claims preserved

- No `/v3` route wiring.
- No runtime behavior change.
- No production rollout approval.
- No production Firestore reads/writes, network, cloud, provider, vector, or telemetry sink calls.
- No secret material, cursor token, or user content logging in readiness output.
- No Archive default visibility.
- No stale Short-term default visibility.

## Local proof

Run:

```bash
cd backend
PYTHONPATH=. python3 scripts/p1_3_v3_archive_short_term_visibility_readiness.py --execute
```

Expected summary remains `status=BLOCKED`, `read_only=true`, `route_wiring=false`, and all production/mutating call counts are zero.
