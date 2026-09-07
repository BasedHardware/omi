# Provider-independent continuation state

Updated 2026-09-07. Production readiness remains open. The user authorizes parallel work, full hardware coverage, logical commits and pushes to v5, and deployment to BasedHardware DEV.

## Verified and pushed

Backend slices include authorized PostgreSQL tasks/audio (a64e477a56), transcription with durable paid-response recovery (f22f1d8572), conversation reads with revision-fenced cursors (8546a0e574), and current trusted chat context packets (01bdb648bb). Chat persistence and deployed gateway identity composition remain missing.

Native slices include capability-gated LED/microphone controls (9ea1065492), account-session device retirement (9af6d6c248), bounded reconnect plus truthful connecting UI (d2bd77e8b3), and acknowledged Find Device commands (5dd93b4ecd). Native retries use 1/2/4-second delays only after a previously ready connection; manual disconnect, account retirement and radio-off cancel them. Mind Map remains collapsed on Home under the existing design decision. Canonical capture ownership receipts are pushed in b4b989025e; the deletion inventory and real cleanup gate are repaired in 0748acd29b.

Storage status is pushed in f316e7ca5f, nullable unit-aware local Settings in 249feac743, and encrypted recording recovery with the coordinated batch wire in 1563013d22. The root check passed in /tmp/v5-final-journal-settings-check.log: 364 React Native tests, 247 Worker tests, 33 ratified contract tests, 46 PWA tests, native checks and 216 deployed-backend tests. Android, iOS and macOS builds passed in /tmp/v5-storage-*-build.log. PostgreSQL passed 28 tests and 1,029 assertions, restored 52 migrations across 119 tables, and passed pinned Linux Bun/Node parity (/tmp/v5-batch-wire-postgres.log). Independent review caught and verified fixes for packet fsync/acknowledgement ordering, retained-memory accounting and fractional transcription usage.

## Development infrastructure

Only based-hardware-dev was modified. Cloud SQL omi-platform-dev-pg18 runs PostgreSQL 18.4; database omi_platform has migrations 1–52 applied. Dedicated migrator and application-only runtime logins exist. Database URL, codec and cursor secrets have version 1. Secret payloads remain outside the repository and OpenTofu state. The Linux image omi-v5-portable:b4b98902 builds and rejects missing configuration; initialized service health remains unverified without runtime configuration.

The operator cannot create custom roles or change project/secret IAM. Eight IAM creates remain in the reviewed private plan at ~/.local/share/omi-v5-dev/operator/remaining-iam.tfplan, including access to the existing DEV transcription secret. The operator cannot read that secret, so live transcription-provider verification is blocked before the provider request. No Cloud Run service is deployed. The default gcloud project is production based-hardware; always specify based-hardware-dev.

Migrations 49 through 52 were applied after their verified commits. The dedicated migration credential and execution logs are private under ~/.local/share/omi-v5-dev/operator. The runtime login was not rotated. Activation still needs legitimate canonical release/account/grant authority; schema installation is not activation.

## Active work and verification limits

CI is confirmed green at 249feac743, run 34069451828; the newer journal commit is still running. It previously exposed two classic Docker image-store incompatibilities and Linux ICU's GMT representation for UTC. The fixes are pushed in ade381dab3, 34f7c2fd1d and 4ebe34e863. Exact pinned Linux formation tests reproduced the UTC failure before repair and passed afterward.

Physical phones were offline. Compilation and synthetic tests do not prove physical BLE writes, link-loss recovery, background capture or firmware operations. Full hardware scope is in hardware-device-parity.md. Background connection configuration is pushed in 62df56426e, but physical delivery and suspension behavior remain unverified. Encrypted recording recovery is implemented and tested, with physical recovery and Android Keystore instrumentation still open. Persistent pairing, storage transfer, buttons, firmware and supported camera/motion paths remain incomplete. Storage reads do not advance or erase audio; current firmware notification completion is not a durable app acknowledgement.

Provider-independent chat stores/gateway identity, Settings profile/entitlement producers, attachments, downstream formation workers and other gaps are in provider-agnostic-parity.md. Do not use QA seed identities, fabricated plans, UID-derived activation or empty successful projections to close them. Existing native cloud profile/subscription routes remain available; they do not prove a portable Settings implementation.

An isolated Linux Bun 1.3.14 run passed 2,387 backend tests with 39 explicit skips, zero failures and 16,541 assertions (/tmp/v5-backend-batch52-full.log). It includes the batch-52 cutover and runs with lsof, procps, Python and an init process. Real PostgreSQL qualification runs separately; live model-provider, deployed app and physical-device acceptance remain open.
