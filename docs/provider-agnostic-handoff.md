# Provider-independent continuation state

Updated 2026-09-07. Production readiness remains open. The user authorizes parallel work, full hardware coverage, logical commits and pushes to v5, and deployment to BasedHardware DEV.

## Verified and pushed

Remote v5 is f22f1d8572; that commit adds durable authorized transcription and app retry. Hardware controls and desktop device Settings are included in 9ea1065492; ade381dab3 repairs Docker image-store compatibility in the PostgreSQL CI setup. It includes BLE setup deadlines, retired callback fencing and the CI dependency installation correction. Commit 83ee6fadc9 adds the deployed PostgreSQL memory runtime, persistent render cache, Firebase binding operator and GCP development foundation. Commit e917bbd1d2 adds actual Device Information Service reads and connection retry error recovery. Earlier mobile task mutations, Conversations and Settings navigation are included.

The full root check before transcription commit f22f1d8572 passed: 324 React Native tests, 246 Worker tests, 50 D1 tests, 33 ratified contract tests, 46 PWA tests, 96 deployed backend tests and native checks. Android, iOS and macOS compiled for the native controls and transport changes. Physical hardware and deployed app acceptance remain separate.

CI exposed a dependency installation ordering defect: Worker task tests imported portable schema code before Ajv was installed. The pushed workflow fix moves the existing portable install ahead of Worker tests; CI passed that stage and exposed a separate chat provider-fixture race. The provider-fixture repair passed locally and is pushed. CI subsequently reached the PostgreSQL image-store check; its compatibility repair passed that CI boundary. CI now exposes a formation runtime test returning model_response_invalid before its injected persistence failure; investigation remains open.

## Development infrastructure

Only based-hardware-dev was modified. Cloud SQL omi-platform-dev-pg18 runs PostgreSQL 18.4; database omi_platform has verified migrations 1–49. Dedicated migrator and application-only runtime logins exist. Database URL, codec and cursor secrets each have version 1. Secret payloads remain outside the repository and OpenTofu state.

The current operator cannot create custom roles or change project/secret IAM. Eight IAM creates remain in the reviewed private plan at ~/.local/share/omi-v5-dev/operator/remaining-iam.tfplan, including access to the existing DEV transcription secret. The current operator also cannot read that secret, so a live transcription-provider probe is blocked before any provider request. No Cloud Run service has been deployed. The default gcloud project is production based-hardware, so every command must explicitly specify based-hardware-dev. Runtime activation also requires genuine canonical release and account authority; schema installation alone is insufficient.

## Active work and verification limits

PostgreSQL tasks migration 47 and durable audio upload migration 48 passed 22 real database tests and 890 assertions, including expiry rollback, plus restoration of 48 migrations across 117 tables and Linux Bun/Node parity. Routes are connected inside the existing readiness and shutdown boundary. The updated Linux image builds. Backend changes passed the full local gate and are pushed. Migrations 47–48 are applied to DEV; the service is not deployed. Native capability-gated controls and transcription integration are committed and pushed. Conversation reads and account-session device cleanup are the current code lanes.

The image tagged omi-platform-dev-review:local includes the final upload expiry guard; rebuild after subsequent code changes. Migrations 47–48 were applied successfully to DEV after commit a64e477a56. The missing temporary migrator credential was rotated for the dedicated migration login and stored privately under ~/.local/share/omi-v5-dev/operator; the runtime login was not changed. Broad backend tests remain unverified because macOS lsof calls hang in kernel state; focused suites do not establish that the broad suite passes.

Physical phones were offline during discovery. Device builds and synthetic fault tests do not prove physical BLE capture, reconnection or firmware operations. Full hardware scope is recorded in hardware-device-parity.md. Provider-independent chat, conversation listing, settings and other parity gaps remain open. Transcription has database and app contract evidence but no live provider/deployed acceptance. Mind Map remains collapsed on Home under the existing design decision.

Transcription migration 49 passed 22 real PostgreSQL tests with 923 assertions, restoration of 49 migrations across 118 tables, and pinned Linux Bun/Node parity. Peer review found and fixed the UTF-8 publication ceiling and paid-response cancellation window. A completed response can be saved under a separate ten-second deadline only after fresh authorization; cancellation prevents canonical publication. Migration 49 was applied successfully to DEV after commit f22f1d8572. The final combined root check and Linux image build passed; evidence is /tmp/v5-transcription-final-check.log and /tmp/v5-transcription-final-image.log. Live provider and deployed app verification remain pending.

Conversation migration 50 passed the combined pinned-host Bun 1.3.14 PostgreSQL suite: 23 tests and 943 assertions, restoration of 50 migrations across 119 tables, and Linux Bun/Node driver parity. Independent review approved revision-fenced cursors after a delayed-visibility omission was fixed. Full root check passed in /tmp/v5-conversations-temporal-final-check.log. Migration 50 is not yet applied to DEV. Native account-session retirement is pushed in 9af6d6c248; bounded reconnect remains under implementation.
