# Client telemetry fixtures

Lane 4 can read these files without importing the collector.

- `payloads.json` — `valid_mixed` is a schema-v1 batch: one synchronous upload
  (started + completed), one physical voice turn (started + successful terminal)
  and one floating voice terminal. Owner is not in the payload.
- `query_response.json` — durable aggregate read for that batch after the UTC
  day `2026-10-12` is sealed, queried at `2026-10-12T12:00:00Z` with
  `days=1`, `channel=production`, and actor `owner-a` classified as
  `production`.

The HTTP route does not yet receive the admin actor/channel map, so a live
read that includes voice rows stays `partial` until that classification is
passed into `query_is_stale`. The fixture shows the sealed, classified shape.
