# Desktop proactivity v2 consumers — retired

The macOS and Windows feed consumers documented here were deleted on
2026-10-26 together with the backend producers that fed them: the macOS
`ProactivityFeedConsumer`/`ProactivityNotificationAdapter`/`ProactivityReceiptStore`
and the Windows `src/main/proactivity` consumer. The server's
`GET /v1/proactivity/feed` and `POST /v1/proactivity/items/{id}/outcomes`
remain as one-release compatibility stubs (feed reports `enabled=false`,
outcomes are a recorded no-op) so already-shipped clients keep decoding
responses; they and the item ledger/budget are removed by the follow-up
retirement PR.

Still present on macOS, deliberately:

- `Rewind/Core/ProactivityRetirementMigration.swift` — forward-only GRDB
  migration dropping the older legacy proactivity tables; installed databases
  depend on its registered name, so it stays.
- The `proactivityV2` notification-kind and provenance cases — they decode
  historical journaled rows and notifications.
- The generated `OmiAPI` wire types — generated from the still-published
  OpenAPI schemas; `ProactivityWireTests` keeps decoding the shared
  `contracts/parity/proactivity_v2.json` fixture until the routes are removed.
