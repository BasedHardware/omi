# Oracle Review: Local Emulator Full-Stack Dev Harness

**Verdict:** LIMITED GO
**Review scope:** local emulator full-stack harness epic/spec/decisions/tickets after initial decision pass.
**Model caveat:** Oracle reported `requested=Pro; resolved=(unavailable); verified=no`; use as advisory feedback, not authoritative proof.

## Summary

Oracle agreed with the core direction:

- keep the three-layer model: hermetic E2E → local emulator full stack → dev-cloud proof;
- keep top-level `make` UX with implementation under `scripts/`;
- use Firestore and Firebase Auth emulators rather than a broad auth bypass;
- use Python-authored typed scenarios;
- target desktop macOS first;
- keep all harness-authoritative mutable state local;
- emit only `LOCAL_EMULATOR_DEV` evidence.

Oracle's main warning: the docs currently say “local” by intent, but should make it mechanically impossible to reach cloud state or delete unrelated state. It also warned that `test-v17-local` must not pass against contaminated long-lived developer state.

## Required amendments before implementation

1. **Real providers should be opt-in, not required for `dev-up`.**
   - `make dev-up` should require only local runtime prerequisites.
   - `make dev-check SCENARIO=...` should evaluate scenario-specific external provider credentials.
   - Real providers should require explicit `PROVIDER_MODE=real`.
   - Hosted vector/index services are stateful and must not be treated as stateless.

2. **Enforce a local Firebase demo-project boundary.**
   - Use fixed project ID `demo-omi-local`.
   - Use Firestore database `(default)` in v1.
   - Require loopback emulator hosts.
   - Construct a sanitized child-process environment.
   - Reject ambient ADC, service-account files, production Firebase config, and unknown project/database IDs.

3. **Define safe process/reset ownership.**
   - Use a state root like `${OMI_LOCAL_STATE_ROOT:-<repo>/.local/dev-harness}/<instance>`.
   - Require an ownership sentinel before destructive operations.
   - Never broad `pkill`, never kill arbitrary port owners, never unchecked `rm -rf`, never shared Redis `FLUSHALL`.

4. **Separate exploratory stack from isolated test stack.**
   - `make dev-up` is long-lived and exploratory.
   - `make seed-v17-scenario` mutates the exploratory instance.
   - `make test-v17-local` should create/reset/seed/run/report/clean an isolated test instance by default.
   - `REUSE_DEV_STACK=1` can exist as an explicit non-reproducible debug mode.

5. **Make Auth emulator fidelity explicit.**
   - Desktop should use real Firebase Auth emulator client behavior.
   - Use email/password synthetic users with deterministic UIDs.
   - Switching users signs out cached users first.
   - No trusted UID header, broad bypass, or hand-built bearer token counts as desktop auth acceptance.

6. **Harden scenario fixtures.**
   - Add schema version, deterministic clock/IDs, auth/profile/firestore/redis/file seeds, request cases, expected API results, expected protected collection changes.
   - Fixtures must not derive expected route decisions from the production decision function.
   - Fixtures must not choose their own evidence label; the report writer hard-codes `LOCAL_EMULATOR_DEV`.

7. **Strengthen no-write proof.**
   - Count attempted Firestore create/set/update/delete/batch/transaction writes at the adapter boundary.
   - Also compute protected collection before/after digest.

8. **Fully isolate desktop local identity.**
   - Unique bundle ID, keychain group, app support/cache directories, URL scheme, preferences domain, Firebase config, local Auth switch, local endpoints.
   - Do not copy credential-bearing `.env` into the bundle.
   - Provider keys stay backend-only.

9. **Clarify CI boundary.**
   - Long-lived full-stack orchestration and desktop launch are not mandatory CI gates in v1.
   - Fixture validation, safety guard tests, evidence-label tests, release-build emulator guards, and existing focused emulator/component tests may still run in CI.

## Recommended new tickets

- `TICKET-015-local-runtime-safety.md`: demo-project hard stop, environment allowlist, loopback enforcement, sentinel/destructive guards, PID/port ownership, safe reset tests.
- `TICKET-025-provider-capabilities.md`: provider modes, allowlists, synthetic-input rule, time/request/cost bounds, scenario-specific credential checks, external state prohibition.

## Recommended order

```text
010 → 015 → 020 → 025 → 030 → 040 → 050 → 070
```

Defer `TICKET-060` branch preview bridge from the local emulator MVP; treat it as separate cloud-promotion infrastructure.

## Decisions Oracle suggests escalating

| Decision | Recommended default |
|---|---|
| Docker/Colima required? | No for v1 unless already a normal Omi prerequisite. Use native Firebase CLI/Java and native Python/desktop loop; dedicated Redis process/container only if needed. |
| Real providers part of acceptance? | No. Default deterministic/off/local providers; real providers are explicit exploratory runs with synthetic data. |
| Local state persistence? | Disposable by default. Persistent named workspaces later. |
| Tests attach to manual stack? | Not by default. Isolated instance by default; `REUSE_DEV_STACK=1` debug only. |
| Desktop identity? | Lock unique bundle ID/keychain group now, e.g. `com.omi.desktop.local` / `group.com.omi.desktop.local`, adjusted for repo conventions. |
| What stays in CI? | Safety/fixture/evidence-label/release-guard tests and existing focused emulator tests; not full desktop orchestration. |
| Branch preview in this epic? | No; move to separate promotion/deployment epic or post-MVP handoff. |
