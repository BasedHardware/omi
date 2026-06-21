---
ticket_id: "tkt_local_emulator_spec"
agent: "codex"
done: true
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

- [x] Review the epic and contextspace spec against existing repo scripts and docs.
- [x] Lock the top-level `make` command names for local stack start, reset, credential check, scenario seed, status, and desktop launch.
- [x] Decide backing script locations under `scripts/dev-harness/`.
- [x] Update `docs/epics/local_first_full_stack_dev_harness_epic.md` and `.codex-autorunner/contextspace/spec.md` with corrected command names and constraints.
- [x] Record durable decisions in `.codex-autorunner/contextspace/decisions.md`.

## Completion inventory

- Root `Makefile`: not present yet; implementation tickets should add a thin dispatcher for the locked commands.
- Firebase emulator assets: `firebase.json` exists and points to `firestore.rules`, `firestore.indexes.json`, and Firestore emulator port `8085`; Auth emulator support should extend this file rather than create a parallel config.
- Firestore rules/indexes: `firestore.rules` and `firestore.indexes.json` are the repo-native assets to reuse for local emulator startup and V17 coverage.
- Existing emulator tests: `package.json` contains short-lived `firebase emulators:exec --only firestore --project demo-v17-memory` V17 scripts and `backend/scripts/v17_*_emulator_test.*` contains emulator proof scripts; these are reference/test assets, not the long-lived manual-QA harness project.
- Hermetic backend E2E: `backend/testing/e2e/run.sh` and `backend/testing/e2e/fakes/` remain the deterministic fake/offline layer; local emulator manual QA must stay separate.
- Desktop runner: `desktop/macos/run.sh` is the build/launch primitive that `make desktop-run-local` should wrap for a named local bundle/profile and localhost/emulator configuration.

## Acceptance criteria

- The spec clearly separates hermetic E2E, local emulator development, and V17 dev-cloud proof.
- The command surface is concrete enough for implementation tickets.
- The contract states that all harness-owned mutable state is local.
- The contract states that only stateless external dev-keyed provider calls are allowed.
- No production data, credentials, or GCP deploy dependency is required by the local harness contract.

## Tests

- `git diff --check`
- Manual doc review: all referenced paths exist and proof-boundary language is explicit.
