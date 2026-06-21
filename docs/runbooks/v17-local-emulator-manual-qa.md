# V17 local emulator manual QA runbook

This workflow is for local product-use/manual QA only. It emits `LOCAL_EMULATOR_DEV` metadata and is not V17 dev-cloud proof, production proof, IAM proof, deployed-index proof, telemetry proof, rollback proof, or activation evidence.

## Happy path

```bash
# Real providers are the default for interactive manual QA and require local dev credentials.
make dev-up
make seed-v17-scenario SCENARIO=happy_path
make desktop-run-local USER=alice
make dev-status
make dev-summary
```

Use offline providers for provider-independent debugging or missing-key demos:

```bash
PROVIDER_MODE=offline make dev-up
PROVIDER_MODE=offline make seed-v17-scenario SCENARIO=happy_path
PROVIDER_MODE=offline make dev-status
PROVIDER_MODE=offline make dev-summary
```

`make dev-status` prints the active instance, provider mode, local endpoints, state root, enabled external providers, seeded V17 scenario/users, and the local session-summary path. `make dev-summary` writes the optional session summary under the harness-owned `reports/` directory.

## Fail-closed scenario

```bash
make seed-v17-scenario SCENARIO=kill_switch
make dev-status
make desktop-run-local USER=alice
```

Other scenario names are listed with:

```bash
make list-v17-scenarios
```

## Desktop local profile handoff

`make desktop-run-local USER=<profile>` currently validates the harness sentinel and seeded synthetic Auth users, then prints the exact `desktop/macos/run.sh` environment expected once TICKET-050 adds the desktop auth/profile bootstrap. It intentionally does not embed provider credentials and does not touch production, beta, or default dev bundles.

## Reset

```bash
make dev-reset
```

Reset only clears sentinel-owned local harness state. It does not delete provider logs or provider-retained data from real external processors.

## Evidence and no-write framing

Session summaries are labelled:

- `evidence_class: LOCAL_EMULATOR_DEV`
- `activation_eligible: false`
- `watermark: NOT_ACTIVATION_EVIDENCE`

Where the summary references no-write/protected-state expectations, this slice includes explicit instrumentation placeholders plus protected collection `before_digest`/`after_digest` fields. Those fields remain `null` until live emulator readback/write-attempt instrumentation is wired; do not treat them as dev-cloud or production no-write proof.
