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
