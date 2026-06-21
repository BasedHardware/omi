---
ticket_id: "tkt_dev_up_foundation"
agent: "codex"
done: true
title: "Add local emulator stack start and reset commands"
goal: "Developers can start, check, stop, and reset the local emulator/backend stack with repo-native make commands."
context:
  - path: ".codex-autorunner/contextspace/spec.md"
    required: true
    max_bytes: 16000
  - path: "backend/testing/e2e/README.md"
    required: true
    max_bytes: 16000
  - path: "desktop/macos/run.sh"
    required: true
    max_bytes: 24000
---

## Tasks

- Add top-level `make` commands for `dev-check`, `dev-up`, `dev-status`, `dev-reset`, and any needed `dev-down` / `dev-logs` helpers.
- Put heavy implementation under `scripts/` rather than in the Makefile.
- Wire Python backend startup with a local-only environment profile.
- Start or validate Firestore emulator and Firebase Auth emulator.
- Start or validate local Redis or the selected local-only state service.
- Add a prerequisite checker that lists missing core local prerequisites and, in default real-provider mode, missing required provider credentials before startup.
- Ensure `PROVIDER_MODE=offline` skips external-provider credential requirements while preserving the same local stack shape.
- Ensure the checker rejects production Firebase/Firestore/GCS projects and implicit ambient GCP state as harness-owned dependencies.
- Ensure reset deletes only harness-owned local state and is idempotent.
- Add health checks that fail fast with actionable messages.

## Acceptance criteria

- `make dev-up` starts the required local emulator/backend services or reports missing prerequisites.
- `make dev-check` prints a clear missing-prerequisites checklist without starting services, including missing dev provider keys when provider mode is real.
- `make dev-reset` clears harness-owned local state without touching real user data.
- Commands do not use production credentials, production data, production projects, or ambient GCP defaults for mutable state.
- External provider usage is governed by `TICKET-025-provider-capabilities.md`; offline mode must not require external-provider credentials.

## Tests

- Run `make dev-check` with missing credentials and verify actionable output.
- Run the start command from a clean shell.
- Run the reset command twice and verify it is idempotent.
- Verify health checks fail clearly when a required dependency is missing.
- `git diff --check`

## Completion notes

- Added root make lifecycle commands backed by `scripts/dev-harness/` Python CLI and thin shell entrypoints.
- Added loopback Firestore/Auth emulator config for `demo-omi-local`, local Redis/backend process manifests, status/logs/down/reset, and prerequisite/provider-mode preflight.
- Verified offline mode skips provider credentials while keeping the local Firestore/Auth/Redis/backend stack shape; real mode reports missing core provider credentials pending TICKET-025 broker/governor details.
- In this environment `make dev-up` fails safely and actionably because `redis-server` and Python `uvicorn` are not installed.
