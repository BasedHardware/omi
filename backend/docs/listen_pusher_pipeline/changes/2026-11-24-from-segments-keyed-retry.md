# Keyed from-segments uploads can finish after the request deadline

The Firebase-authenticated `POST /v1/conversations/from-segments` route gives
keyed uploads up to 25 seconds of total request time. When the HTTP wait expires,
the existing retryable 503 carries `request_budget_exhausted`. An admitted
worker can finish the persisted claim with its own model budgets and owns
cleanup on processing failure.

A retry checks tombstones and the persisted conversation on the database pool
before requesting a processing slot. A completed claim returns its existing
conversation and applies late client metadata through the existing replay path.
An active claim returns `from_segments_processing_in_flight`. New and stale
claims remain subject to processing capacity. The existing atomic claim
creation resolves a concurrent insert after a lookup miss.

## Rollout

Pending review and backend deployment. This change requires no feature flag or
data migration.

## Verification

`tests/unit/test_developer_from_segments_idempotency.py` covers budget expiry
with a live claim, active and completed retries while processing admission is
full, and capacity rejection for a new key. After rollout, verify that a retry
after a budget cut returns the original conversation ID and track the route's
503 share of valid uploads under SCA-3846.
