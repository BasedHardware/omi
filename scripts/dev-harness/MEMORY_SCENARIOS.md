# Local memory scenario fixtures

The fixtures in `dev_harness.memory_scenarios` are synthetic, Python-authored, importable local emulator fixtures for the dev harness.

They are **LOCAL_EMULATOR_DEV** artifacts only:

- `evidence_class` is hard-coded by the tooling as `LOCAL_EMULATOR_DEV`.
- `activation_eligible` is hard-coded as `false`.
- `watermark` is hard-coded as `NOT_ACTIVATION_EVIDENCE`.
- Fixture definitions cannot choose evidence labels and must not be used as dev-cloud proof.
- Synthetic users include `local_default_user`, `alice`, `bob`, and two Chat-first E2E-only principals; no production UIDs, tokens, credentials, or copied user data are present.

Commands:

```bash
make list-memory-scenarios
make seed-memory-scenario SCENARIO=happy_path
make dev-status
make dev-summary
make desktop-run-local DESKTOP_USER=alice
make reset-memory-scenario SCENARIO=happy_path
```

Before `make desktop-run-local` signs into the Auth emulator, it resets only the selected synthetic `omi-*` bundle's team-and-bundle-scoped auth, local-agent, and device Keychain items. This keeps repeated ad-hoc builds hermetic; the reset helper rejects Prod, Beta, Omi Dev, and any app-path identity mismatch.

`make dev-summary` writes an optional `LOCAL_EMULATOR_DEV` session summary with `activation_eligible=false`, provider mode, local endpoints, no prod/dev-cloud activation implication, and placeholder fields for write-attempt instrumentation plus protected-collection before/after digests when live emulator instrumentation is not available.

If local Firestore/Auth emulators are not reachable, seed/reset commands still validate fixtures and emit a dry-run manifest under the sentinel-owned local harness state root. They do not fake live emulator writes.

## Chat-first E2E fixture

The named Chat-first bundle is exercised through real Firebase Auth emulator
credentials. The local harness resolves the emulator-assigned `localId` from
`canonical-auth-uids.json`; it never uses a fixed UID or a production auth
bypass. Start the local backend and live emulators, seed the scenario, prepare
the fixture using its logical principal, then launch the named bundle:

```bash
PROVIDER_MODE=offline make dev-up
make seed-memory-scenario SCENARIO=happy_path
make chat-first-e2e-fixture CHAT_FIRST_E2E_ACTION=prepare CHAT_FIRST_E2E_CASE=enabled
make desktop-run-local DESKTOP_APP_NAME=omi-chat-first-e2e DESKTOP_USER=omi-chat-first-e2e-enabled
```

The same local-only command snapshots or advances an existing fixture while
preserving the authenticated principal boundary:

```bash
make chat-first-e2e-fixture CHAT_FIRST_E2E_ACTION=snapshot CHAT_FIRST_E2E_CASE=enabled
make chat-first-e2e-fixture CHAT_FIRST_E2E_ACTION=advance CHAT_FIRST_E2E_CASE=enabled CHAT_FIRST_E2E_SECONDS=86400
```
