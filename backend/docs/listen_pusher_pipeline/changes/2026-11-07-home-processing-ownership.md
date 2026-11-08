# One Home row per live episode

Hide all members before skipping an episode owned by active Listening. When
capture stops, its server snapshot retains one episode row. The local processing
insertion path uses the same complete membership. Render evidence is in
`.agent-artifacts/ui-evidence/home-overlap/` at the repository root.

The backend ownership/dedupe and live-member notes switches default on, with independent false env kill switches.
Admission metadata is additive Redis JSON with unchanged TTL. Session-only
uploads without a target remain a reported upload-contract limitation.

[Contract](../../listen_pusher_pipeline.mdx#home-processing-ownership-default-on) and
[runbook](../../runbooks/home-processing-ownership.md) describe the capability
header, flags, telemetry, durable waits, default-on verification and rollback. This PR changes code defaults;
it does not change runtime env, merge or deploy. See focused Home, pending-work, sync-admission,
finalizer and Process Now regression suites in this PR.

Review fixes require the client to echo the live episode ID in its existing
held-member pairs; missing, malformed or mismatched echoes keep recordings visible.
The app acknowledges fetched live members as well as composed closed episodes.
The recording detail lease covers the maximum hold plus a quiet-window delivery
margin (4,200 seconds). Expiry restores deferral. Empty-transcript processing
passes the notes gate; retained batch registration precedes early and late notes
waits, and donor completion propagates scheduling deferral without wrapping it
as a retryable processing failure. Clock-driven admission tests, raw legacy Redis
payload tests and finalizer regressions cover these boundaries.

Live list omissions require exact client-held episode/member pairs, including
for current live membership and time-overlap ownership. Newly attached or
unacknowledged members remain visible until fetched. All acknowledged omissions
are named in `X-Omi-Home-Suppressed-Ids` for local source restoration. The early
finalizer notes gate also bypasses empty transcripts, including photo-only rows.
