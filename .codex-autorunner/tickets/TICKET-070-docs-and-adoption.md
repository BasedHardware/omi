---
ticket_id: "tkt_docs_and_adoption"
agent: "codex"
done: false
title: "Document local-first developer workflow"
goal: "Developers know when to use local harness, hermetic E2E, live local backend, and dev-cloud proof."
context:
  - path: "docs/epics/local_first_full_stack_dev_harness_epic.md"
    required: true
    max_bytes: 16000
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

- Add docs for the local-first workflow and command sequence.
- Document the decision tree: hermetic local, emulator local, live local backend, branch preview, dev-cloud proof.
- Add troubleshooting for common missing prerequisites.
- Cross-link from desktop and backend development docs where appropriate.

## Acceptance criteria

- A developer can find the local harness workflow from repo docs.
- Docs state exactly what each testing layer proves and does not prove.
- V17 dev-cloud proof remains clearly required for activation.

## Tests

- Follow the documented happy path from a clean shell.
- Run `git diff --check`.
