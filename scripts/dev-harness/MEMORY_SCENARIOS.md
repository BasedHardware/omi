# Local memory scenario fixtures

The fixtures in `dev_harness.memory_scenarios` are synthetic, Python-authored, importable local emulator fixtures for the dev harness.

They are **LOCAL_EMULATOR_DEV** artifacts only:

- `evidence_class` is hard-coded by the tooling as `LOCAL_EMULATOR_DEV`.
- `activation_eligible` is hard-coded as `false`.
- `watermark` is hard-coded as `NOT_ACTIVATION_EVIDENCE`.
- Fixture definitions cannot choose evidence labels and must not be used as dev-cloud proof.
- Synthetic users include `local_default_user`, `alice`, and `bob`; no production UIDs, tokens, credentials, or copied user data are present.

Commands:

```bash
make list-memory-scenarios
make seed-memory-scenario SCENARIO=happy_path
make dev-status
make dev-summary
make desktop-run-local USER=alice
make reset-memory-scenario SCENARIO=happy_path
```

`make dev-summary` writes an optional `LOCAL_EMULATOR_DEV` session summary with `activation_eligible=false`, provider mode, local endpoints, no prod/dev-cloud activation implication, and placeholder fields for write-attempt instrumentation plus protected-collection before/after digests when live emulator instrumentation is not available.

If local Firestore/Auth emulators are not reachable, seed/reset commands still validate fixtures and emit a dry-run manifest under the sentinel-owned local harness state root. They do not fake live emulator writes.
