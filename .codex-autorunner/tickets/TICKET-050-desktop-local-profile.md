---
ticket_id: "tkt_desktop_local_profile"
agent: "codex"
done: false
title: "Add desktop local emulator profile for Omi Dev Local"
goal: "Developers can launch a named desktop app profile against the local emulator/backend harness as a seeded local test user."
context:
  - path: "desktop/macos/run.sh"
    required: true
    max_bytes: 24000
  - path: "desktop/macos/.env.example"
    required: true
    max_bytes: 12000
  - path: ".codex-autorunner/contextspace/spec.md"
    required: true
    max_bytes: 16000
---

## Tasks

- Add a documented local desktop profile that points the Swift app to localhost Python and desktop backends.
- Ensure the profile uses a named bundle such as `Omi Dev Local` and does not collide with production, beta, or the existing `Omi Dev` profile.
- Lock unique local identity values for bundle identifier, keychain access group, Application Support/cache directories, URL scheme, preferences domain, Firebase config, local Auth switch, and local backend endpoints.
- Wire the desktop launch command through `make desktop-run-local USER=<profile>` or the agreed equivalent.
- Make Firebase Auth emulator behavior explicit for desktop: default local user, named users, and how the selected user is bootstrapped.
- Add a launch command wrapper or documented command that assumes `make dev-up` has already started the local stack.

## Acceptance criteria

- The desktop app can be launched against the local harness with one command after `make dev-up`.
- The generated app bundle/config contains localhost backend URLs and no provider credentials.
- The selected local Firebase Auth emulator user is available to the desktop flow.
- The profile does not remove or mutate existing production, beta, or existing dev app bundles.
- At least one V17-relevant local read path can be manually exercised through desktop against local emulator state.

## Tests

- Build and launch the local desktop profile.
- Statically scan the resolved build configuration and bundle for prohibited production endpoints, Firebase project IDs, and credential patterns; do not copy credential-bearing `.env` files into the app bundle.
- Verify the selected local auth user is present/usable.
- Run a manual V17 memory scenario through the desktop path if the relevant UI/API path exists.
- `git diff --check`
