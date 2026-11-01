# Lane 1 notes

The collector and the warehouse fixtures are in this tree. Flags default off.
No PostHog schema, BigQuery job, IAM grant, or scheduled query was changed.

## Open integration

- `GET /v1/telemetry/client/aggregates` does not load the admin actor/channel
  map. Pass `channel_by_actor` into `query_is_stale` before voice coverage can
  be complete. Until then voice reads are `partial`.
- Client outbox, shadow send, and rendered panels belong to the other lanes.
  Fixtures they can read: `backend/tests/fixtures/client_telemetry/`.
- Live seven-day canary parity is not claimed.
