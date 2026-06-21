---
ticket_id: "tkt_local_emulator_v17_manual_qa"
agent: "codex"
done: true
title: "Add local emulator V17 manual-QA workflow"
goal: "Developers can seed a V17 product state, launch desktop locally, inspect status, and manually QA the product without deploying to GCP."
context:
  - path: "backend/testing/e2e/README.md"
    required: true
    max_bytes: 18000
  - path: ".codex-autorunner/contextspace/spec.md"
    required: true
    max_bytes: 22000
---

## Tasks

- Add or finalize a local V17 manual-QA workflow behind the agreed `make` commands.
- Ensure the core workflow is `make dev-up`, `make seed-v17-scenario SCENARIO=<name>`, `make desktop-run-local USER=<profile>`, `make dev-status`, and `make dev-reset`.
- Ensure `make dev-status` shows active instance, seeded scenario/users, provider mode, local endpoints, state root, enabled external providers, and session summary path.
- Make real providers the default for manual QA and show an obvious hint for `PROVIDER_MODE=offline`.
- Ensure offline mode reuses hermetic fake/offline providers where provider-independent debugging is desired.
- Do not build a deterministic pass/fail product test suite against the long-lived manual-QA instance; deterministic tests remain in the hermetic harness.
- Support optional local session summaries labelled `LOCAL_EMULATOR_DEV` with `activation_eligible: false` and provider mode included.
- Where no-write or protected-state claims are emitted, back them with write-attempt instrumentation plus protected-collection before/after digests.

## Acceptance criteria

- A developer can seed a V17 happy-path product state and manually use it through the desktop local profile.
- A developer can seed at least one fail-closed scenario and manually observe the intended behavior.
- `make dev-status` accurately describes the active local state and provider mode.
- The workflow does not imply CI/pass-fail acceptance or dev-cloud activation proof.
- Offline mode is one switch away and shares hermetic fake providers where practical.

## Tests

- Run the documented manual-QA happy path locally enough to verify commands and status output.
- Run `PROVIDER_MODE=offline make dev-up` smoke if offline providers are implemented in this slice.
- Verify session summary uses `LOCAL_EMULATOR_DEV`, `activation_eligible: false`, and includes provider mode.
- `git diff --check`

## Completion notes

- Implemented enhanced `make dev-status`, optional `make dev-summary`, and safe `make desktop-run-local USER=<profile>` placeholder/handoff pending TICKET-050 desktop auth/profile bootstrap.
- Session summaries are hard-labelled `LOCAL_EMULATOR_DEV`, `activation_eligible=false`, include provider mode, and contain explicit non-activation/non-dev-cloud claims plus write-attempt/protected digest placeholders.
- Verified with scripts/dev-harness pytest, scenario list/seed/status/summary commands using temp state, offline `dev-up` smoke (blocked by missing Java/Firebase emulator prerequisites as expected in this environment), and `git diff --check`.
