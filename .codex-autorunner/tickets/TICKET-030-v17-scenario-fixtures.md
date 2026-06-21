---
ticket_id: "tkt_v17_scenario_fixtures"
agent: "codex"
done: true
title: "Add Python-authored synthetic V17 local product scenarios"
goal: "Developers can seed and reset named synthetic V17 memory product states in local emulator state."
context:
  - path: ".codex-autorunner/contextspace/spec.md"
    required: true
    max_bytes: 16000
  - path: "docs/runbooks/v17-v3-dev-cloud-proof.md"
    required: true
    max_bytes: 18000
---

## Tasks

- Define Python-authored scenario fixtures for V17 happy path, default-off, kill-switch, malformed cursor, stale Short exclusion, Archive default exclusion, and cross-user isolation.
- Include typed scenario metadata: schema version, scenario ID, description, deterministic clock/IDs/cursors, users, selected user, local flags/config, auth/profile/firestore/redis/file seed data, request cases, expected route decision, expected reads, expected protected collection changes, and expected fail-closed behavior.
- Ensure fixtures cannot choose evidence labels; the report writer hard-codes `LOCAL_EMULATOR_DEV`.
- Add seed/reset tooling for named scenarios against local emulator/local state.
- Add a scenario listing command for discoverability.
- Ensure all fixture content is synthetic and safe to commit.
- Include at least a default local user plus named users such as `alice` and `bob` for multi-user testing.

## Acceptance criteria

- A developer can seed at least one happy path and one fail-closed scenario locally.
- Fixtures include at least two synthetic users for isolation checks.
- Fixtures are Python-authored and importable/type-checkable by the seed/test tooling.
- Fixture docs state that these are `LOCAL_EMULATOR_DEV` artifacts, not dev-cloud proof artifacts.

## Tests

- Run scenario listing.
- Run seed for each initial scenario and inspect local emulator state.
- Run reset after each scenario and verify no residual scenario state remains.
- Run the Python unit tests/type checks added for fixture validation.
- Run `git diff --check`.

## Completion notes

- Added Python-authored, importable local V17 scenarios for `happy_path`, `default_off`, `kill_switch`, `malformed_cursor`, `stale_short_exclusion`, `archive_default_exclusion`, and `cross_user_isolation`.
- Added local-only list/seed/reset commands. When emulators are absent, seed/reset validate fixtures and emit dry-run manifests without pretending to write live emulator state.
- Local metadata is hard-coded as `LOCAL_EMULATOR_DEV`, `activation_eligible=false`, and `NOT_ACTIVATION_EVIDENCE`; fixtures cannot select evidence labels.
