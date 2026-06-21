# V17 local scenario fixtures

The fixtures in `dev_harness.v17_scenarios` are synthetic, Python-authored, importable local emulator fixtures for the dev harness.

They are **LOCAL_EMULATOR_DEV** artifacts only:

- `evidence_class` is hard-coded by the tooling as `LOCAL_EMULATOR_DEV`.
- `activation_eligible` is hard-coded as `false`.
- `watermark` is hard-coded as `NOT_ACTIVATION_EVIDENCE`.
- Fixture definitions cannot choose evidence labels and must not be used as V17 dev-cloud proof.
- Synthetic users include `local_default_user`, `alice`, and `bob`; no production UIDs, tokens, credentials, or copied user data are present.

Commands:

```bash
make list-v17-scenarios
make seed-v17-scenario SCENARIO=happy_path
make reset-v17-scenario SCENARIO=happy_path
```

If local Firestore/Auth emulators are not reachable, seed/reset commands still validate fixtures and emit a dry-run manifest under the sentinel-owned local harness state root. They do not fake live emulator writes.
