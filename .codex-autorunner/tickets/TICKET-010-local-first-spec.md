---
ticket_id: "tkt_local_emulator_spec"
agent: "codex"
done: false
title: "Finalize local emulator harness contract"
goal: "The repo has a durable, reviewed contract for the local emulator full-stack harness and its proof boundary."
context:
  - path: "docs/epics/local_first_full_stack_dev_harness_epic.md"
    required: true
    max_bytes: 20000
  - path: ".codex-autorunner/contextspace/spec.md"
    required: true
    max_bytes: 16000
---

## Tasks

- Review the epic and contextspace spec against existing repo scripts and docs.
- Lock the top-level `make` command names for local stack start, reset, credential check, scenario seed, status, and desktop launch.
- Decide backing script locations under `scripts/`.
- Update `docs/epics/local_first_full_stack_dev_harness_epic.md` and `.codex-autorunner/contextspace/spec.md` with any corrected command names or constraints.
- Record durable decisions in `.codex-autorunner/contextspace/decisions.md`.

## Acceptance criteria

- The spec clearly separates hermetic E2E, local emulator development, and V17 dev-cloud proof.
- The command surface is concrete enough for implementation tickets.
- The contract states that all harness-owned mutable state is local.
- The contract states that only stateless external dev-keyed provider calls are allowed.
- No production data, credentials, or GCP deploy dependency is required by the local harness contract.

## Tests

- `git diff --check`
- Manual doc review: all referenced paths exist and proof-boundary language is explicit.
