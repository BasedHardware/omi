# Bounded enrichment retries for V3 custody conflicts

[Recording-derived conversations V3 contract](../../listen_pusher_pipeline.mdx#recording-derived-conversations-v3)

A rejected sync redirect can raise a typed V3 custody conflict during enrichment.
Previously, the exception escaped as HTTP 500 and left the outbox obligation
retrying. Enrichment now responds with HTTP 200 and defers the obligation twice
for 120 seconds each. A third conflict parks the row with the durable
`held_reason` of `v3_custody_conflict`.

Summary-debt repair respects deferred and parked rows. Lease and version fences
preserve concurrent producer work, and fresh producer work can reopen a parked
obligation with a new retry budget. The existing V3 custody transfer rules still
govern whether a redirect can proceed.

This change has no new flag and ships with backend-integration through normal
release admission. After rollout, check 30 minutes of live traffic for unhandled
custody-conflict 500s, compare enrichment 5xx with the pre-deploy baseline, and
confirm affected outbox rows are deferred or parked with the recorded reason.

Route and Firestore emulator regression evidence is recorded in
[PR #25917](https://github.com/BasedHardware/omi/pull/25917).
