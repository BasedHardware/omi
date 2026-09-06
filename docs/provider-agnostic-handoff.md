# Provider-independent continuation state

Updated 2026-09-07. Production readiness remains open. The user authorizes parallel work, full hardware coverage, logical commits and pushes to v5, and deployment to BasedHardware DEV.

## Verified and pushed

Remote v5 is 35cf1a4ab4a98acb3ee5b58b38a7508250fe0a68. It includes BLE setup deadlines, retired callback fencing and the CI dependency installation correction. Commit 83ee6fadc9 adds the deployed PostgreSQL memory runtime, persistent render cache, Firebase binding operator and GCP development foundation. Commit e917bbd1d2 adds actual Device Information Service reads and connection retry error recovery. Earlier mobile task mutations, Conversations and Settings navigation are included.

The complete local check passed before both commits. The latest run included 313 React Native tests, 245 Worker tests, 50 D1 tests, 33 ratified contract tests, 46 PWA tests, 64 deployed backend tests and native checks. Android, iOS and macOS compiled. Real PostgreSQL passed 21 tests and 827 assertions, restoration of 46 migrations across 111 tables, and pinned Linux Bun and Node parity.

CI exposed a dependency installation ordering defect: Worker task tests imported portable schema code before Ajv was installed. The pushed workflow fix moves the existing portable install ahead of Worker tests; CI passed that stage and exposed a separate chat provider-fixture race. Its regression repair is under final local validation, with CI verification still required.

## Development infrastructure

Only based-hardware-dev was modified. Cloud SQL omi-platform-dev-pg18 runs PostgreSQL 18.4; database omi_platform has verified migrations 1–46. Dedicated migrator and application-only runtime logins exist. Database URL, codec and cursor secrets each have version 1. Secret payloads remain outside the repository and OpenTofu state.

The current operator cannot create custom roles or change project/secret IAM. Seven IAM creates remain in /tmp/omi-platform-dev-remaining-iam.tfplan. No Cloud Run service has been deployed. The default gcloud project is production based-hardware, so every command must explicitly specify based-hardware-dev. Runtime activation also requires genuine canonical release and account authority; schema installation alone is insufficient.

## Active work and verification limits

PostgreSQL tasks migration 47 and durable audio upload migration 48 passed 22 real database tests and 890 assertions, including expiry rollback, plus restoration of 48 migrations across 117 tables and Linux Bun/Node parity. Routes are connected inside the existing readiness and shutdown boundary. The updated Linux image builds. Backend changes await the final full local gate and commit; they are not deployed. Native capability-gated controls and transcription integration remain in progress.

The image tagged omi-platform-dev-review:local includes the final upload expiry guard; rebuild after subsequent code changes. Migrations 47–48 are tested but remain unapplied to DEV pending the final commit. Broad backend tests remain unverified because macOS lsof calls hang in kernel state; focused suites do not establish that the broad suite passes.

Physical phones were offline during discovery. Device builds and synthetic fault tests do not prove physical BLE capture, reconnection or firmware operations. Full hardware scope is recorded in hardware-device-parity.md. Provider-independent chat, transcription, conversations, settings and other parity gaps remain open. Mind Map remains collapsed on Home under the existing design decision.
