---
ticket_id: "tkt_local_runtime_safety"
agent: "codex"
done: false
title: "Add local runtime safety and isolation guards"
goal: "Harness scripts are mechanically prevented from reaching cloud state, deleting unrelated state, or killing unrelated processes."
context:
  - path: ".codex-autorunner/contextspace/spec.md"
    required: true
    max_bytes: 20000
  - path: "firebase.json"
    required: false
    max_bytes: 12000
  - path: "firestore.rules"
    required: false
    max_bytes: 12000
---

## Tasks

- Define the canonical local Firebase project ID `demo-omi-local` and Firestore database ID `(default)`.
- Add guards that reject non-`demo-` project IDs, unknown Firestore database IDs, non-loopback emulator hosts, ambient ADC, service-account files, production Firebase config, and inherited gcloud/Firebase project defaults.
- Define a harness state root like `${OMI_LOCAL_STATE_ROOT:-<repo>/.local/dev-harness}/<instance>`.
- Add ownership sentinel, process manifest, port manifest, config digest, logs, reports, and local service state directories under the state root.
- Ensure destructive commands resolve real paths and refuse empty paths, root, home, repository root, or paths without the ownership sentinel.
- Ensure process shutdown uses recorded PIDs after ownership verification; never broad `pkill`, never kill arbitrary port owners.
- Ensure port collisions fail with a foreign-process message instead of silently killing or hopping ports.
- Ensure Redis, if used, is dedicated to the harness instance and never reset with shared `FLUSHALL`.

## Acceptance criteria

- Safety guards fail closed before any seed/reset/mutation when project/database/emulator/state-root requirements are not met.
- `dev-reset` cannot delete outside the harness state root.
- `dev-down` cannot kill unrelated processes.
- Foreign port ownership produces an actionable error.
- The guard layer can be tested without starting the full desktop app.

## Tests

- Unit tests for state-root path validation and sentinel checks.
- Unit tests for project/database/loopback validation.
- Unit tests proving dangerous paths are rejected.
- Unit tests proving foreign PID/port ownership is rejected.
- `git diff --check`
