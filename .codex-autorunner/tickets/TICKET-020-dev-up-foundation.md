---
ticket_id: "tkt_dev_up_foundation"
agent: "codex"
done: false
title: "Add local dev stack start and reset commands"
goal: "Developers can start and reset the local backend stack with repo-native commands."
context:
  - path: ".codex-autorunner/contextspace/spec.md"
    required: true
    max_bytes: 12000
  - path: "backend/testing/e2e/README.md"
    required: true
    max_bytes: 16000
  - path: "desktop/macos/run.sh"
    required: true
    max_bytes: 20000
---

## Tasks

- Add repo-native commands for starting and resetting the local stack.
- Wire Python backend startup with a local-only environment profile.
- Add local Redis/fakeredis and Firestore/Auth emulator or documented strict fake startup.
- Ensure reset deletes only harness-owned state.
- Add health checks that fail fast with actionable messages.

## Acceptance criteria

- `dev-up` equivalent starts the required local services or reports missing prerequisites.
- `dev-reset` equivalent clears harness-owned state without touching real user data.
- Commands do not use production credentials or ambient GCP defaults.

## Tests

- Run the start command from a clean shell.
- Run the reset command twice and verify it is idempotent.
- Verify health checks fail clearly when a required dependency is missing.
