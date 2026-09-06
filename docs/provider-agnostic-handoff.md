# Provider-independent continuation state

Updated 2026-09-07. Production readiness remains open. The user authorizes parallel work, full hardware coverage, logical commits and pushes to v5, and deployment to BasedHardware DEV.

## Verified and pushed

Backend slices include authorized PostgreSQL tasks/audio (a64e477a56), transcription with durable paid-response recovery (f22f1d8572), conversation reads with revision-fenced cursors (8546a0e574), and current trusted chat context packets (01bdb648bb). Chat persistence and deployed gateway identity composition remain missing.

Native slices include capability-gated LED/microphone controls (9ea1065492), account-session device retirement (9af6d6c248), and bounded reconnect plus truthful connecting UI (d2bd77e8b3). Native retries use 1/2/4-second delays only after a previously ready connection; manual disconnect, account retirement and radio-off cancel them. Mind Map remains collapsed on Home under the existing design decision.

The final root check passed in /tmp/v5-reconnect-final-check.log: 330 React Native tests, Worker/D1, ratified contract, PWA, native and deployed-backend gates. Android, iOS and macOS builds passed in /tmp/omi-reconnect-*-build.log. The latest PostgreSQL context run passed 23 tests and 940 assertions, restored 50 migrations across 119 tables, and passed pinned Linux Bun/Node driver parity (/tmp/v5-chat-context-postgres.log).

## Development infrastructure

Only based-hardware-dev was modified. Cloud SQL omi-platform-dev-pg18 runs PostgreSQL 18.4; database omi_platform has migrations 1–50 applied. Dedicated migrator and application-only runtime logins exist. Database URL, codec and cursor secrets have version 1. Secret payloads remain outside the repository and OpenTofu state. The latest tested Linux image builds; rebuild after subsequent deployed-entry changes.

The operator cannot create custom roles or change project/secret IAM. Eight IAM creates remain in the reviewed private plan at ~/.local/share/omi-v5-dev/operator/remaining-iam.tfplan, including access to the existing DEV transcription secret. The operator cannot read that secret, so live transcription-provider verification is blocked before the provider request. No Cloud Run service is deployed. The default gcloud project is production based-hardware; always specify based-hardware-dev.

Migrations 49 and 50 were applied after their verified commits. The dedicated migration credential and execution logs are private under ~/.local/share/omi-v5-dev/operator. The runtime login was not rotated. Activation still needs legitimate canonical release/account/grant authority; schema installation is not activation.

## Active work and verification limits

CI now passes the 23 PostgreSQL tests and restoration. It exposed two classic Docker image-store incompatibilities and Linux ICU's GMT representation for UTC. The fixes are pushed in ade381dab3, 34f7c2fd1d and 4ebe34e863. Final live CI confirmation remains pending. Exact pinned Linux formation tests reproduced the UTC failure before repair and passed afterward.

Physical phones were offline. Compilation and synthetic tests do not prove physical BLE writes, link-loss recovery, background capture or firmware operations. Full hardware scope is in hardware-device-parity.md. Durable encrypted recording recovery, persistent pairing, background services, device storage, buttons, firmware and supported camera/motion paths remain incomplete.

Provider-independent chat stores/gateway identity, Settings profile/entitlement producers, attachments, downstream formation workers and other gaps are in provider-agnostic-parity.md. Do not use QA seed identities, fabricated plans, UID-derived activation or empty successful projections to close them. Existing native cloud profile/subscription routes remain available; they do not prove a portable Settings implementation.

Broad backend tests remain unverified because macOS lsof calls hang in kernel state. Focused suites do not certify the broad suite. Real deployed app, live model-provider and physical-device acceptance remain open.
