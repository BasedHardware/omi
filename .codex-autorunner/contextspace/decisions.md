# Local-First Harness Decisions

- This is a new infra epic, not V18 and not an extension of V17 product semantics.
- V17 is the first customer and provides the initial scenario set.
- Dev-cloud proof remains mandatory for V17 activation. Local/emulator evidence can supplement but never replace it.
- The harness should prefer deterministic local fakes/emulators over live provider calls.
- Scenario fixtures must use synthetic users and synthetic memory content only.
- Desktop testing should use a named local profile such as `Omi Dev Local` so it does not collide with production or existing dev installs.
- Commands should be repository-native and easy to discover, preferably through `make` wrappers or existing script conventions.
