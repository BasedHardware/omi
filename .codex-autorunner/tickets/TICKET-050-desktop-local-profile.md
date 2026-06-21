---
ticket_id: "tkt_desktop_local_profile"
agent: "codex"
done: false
title: "Add desktop local profile for Omi Dev Local"
goal: "Developers can launch a named desktop app profile against the local harness."
context:
  - path: "desktop/macos/run.sh"
    required: true
    max_bytes: 24000
  - path: "desktop/macos/.env.example"
    required: true
    max_bytes: 12000
  - path: ".codex-autorunner/contextspace/spec.md"
    required: true
    max_bytes: 12000
---

## Tasks

- Add a documented local desktop profile that points the Swift app to localhost Python and desktop backends.
- Ensure the profile uses a named bundle such as `Omi Dev Local` and does not collide with production or the existing `Omi Dev` profile.
- Keep Firebase/Auth local behavior explicit: emulator, test-token shim, or clear unsupported state.
- Add a launch command wrapper or documented command that uses the local stack.

## Acceptance criteria

- The desktop app can be launched against the local harness with one command after `dev-up`.
- The generated app bundle contains localhost backend URLs.
- The profile does not remove or mutate existing production/beta app bundles.

## Tests

- Build and launch the local desktop profile.
- Inspect bundled `.env` to confirm local URLs.
- Run a manual V17 memory scenario through the UI if the relevant UI path exists.
