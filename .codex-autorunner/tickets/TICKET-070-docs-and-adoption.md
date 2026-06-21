---
ticket_id: "tkt_docs_and_adoption"
agent: "codex"
done: false
title: "Document local emulator developer workflow"
goal: "Developers know when to use hermetic E2E, local emulator manual QA/product use, branch preview, and dev-cloud proof."
context:
  - path: "docs/epics/local_first_full_stack_dev_harness_epic.md"
    required: true
    max_bytes: 20000
  - path: "README.md"
    required: true
    max_bytes: 12000
  - path: "desktop/macos/README.md"
    required: true
    max_bytes: 12000
  - path: "backend/testing/e2e/README.md"
    required: true
    max_bytes: 16000
---

## Tasks

- Add docs for the local emulator workflow and command sequence.
- Document the decision tree: hermetic E2E for deterministic tests, local emulator harness for manual QA/product use, branch preview, dev-cloud proof.
- Document default real-provider mode and `PROVIDER_MODE=offline` fallback that reuses hermetic fake providers where possible.
- Add troubleshooting for missing dev credentials, provider mode prerequisites, emulator prerequisites, state-root ownership failures, and foreign-port errors.
- Document seeded Firebase Auth emulator users and multi-user profiles.
- Cross-link from desktop and backend development docs where appropriate.

## Acceptance criteria

- A developer can find the local emulator harness workflow from repo docs.
- Docs state exactly what each testing layer proves and does not prove.
- Docs state that the harness is local-development-only and does not run in CI initially.
- V17 dev-cloud proof remains clearly required for activation.

## Tests

- Follow the documented happy path from a clean shell.
- Confirm missing-credential troubleshooting matches actual `make dev-check` output.
- Run `git diff --check`.
