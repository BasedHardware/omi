---
ticket_id: "tkt_local_first_spec"
agent: "codex"
done: false
title: "Finalize local-first harness contract"
goal: "The repo has a durable, reviewed contract for the local-first full-stack harness and its proof boundary."
context:
  - path: "docs/epics/local_first_full_stack_dev_harness_epic.md"
    required: true
    max_bytes: 16000
  - path: ".codex-autorunner/contextspace/spec.md"
    required: true
    max_bytes: 12000
---

## Tasks

- Review the epic and contextspace spec against existing repo scripts and docs.
- Decide final command names for local stack start, reset, seed, test, and desktop launch.
- Update `docs/epics/local_first_full_stack_dev_harness_epic.md` and `.codex-autorunner/contextspace/spec.md` with any corrected command names or constraints.
- Record durable decisions in `.codex-autorunner/contextspace/decisions.md`.

## Acceptance criteria

- The spec clearly separates local/emulator proof from V17 dev-cloud proof.
- The command surface is concrete enough for implementation tickets.
- No production data, credentials, or GCP dependency is required by the local harness contract.

## Tests

- `git diff --check`
- Manual doc review: all referenced paths exist and proof-boundary language is explicit.
