---
ticket_id: "tkt_v17_scenario_fixtures"
agent: "codex"
done: false
title: "Add synthetic V17 local scenario fixtures"
goal: "Developers can seed and reset named synthetic V17 memory scenarios locally."
context:
  - path: ".codex-autorunner/contextspace/spec.md"
    required: true
    max_bytes: 12000
  - path: "docs/runbooks/v17-v3-dev-cloud-proof.md"
    required: true
    max_bytes: 18000
---

## Tasks

- Define checked-in synthetic fixtures for V17 happy path, default-off, kill-switch, malformed cursor, and cross-user isolation.
- Add seed/reset tooling for named scenarios.
- Ensure all fixture content is synthetic and safe to commit.
- Include fixture metadata that records scenario name, users, expected route decision, and expected proof label.

## Acceptance criteria

- A developer can seed at least one happy path and one fail-closed scenario locally.
- Fixtures include at least two synthetic users for isolation checks.
- Fixture docs state that these are not dev-cloud proof artifacts.

## Tests

- Run seed for each scenario and inspect stored state.
- Run reset after each scenario and verify no residual scenario state remains.
- Run `git diff --check`.
