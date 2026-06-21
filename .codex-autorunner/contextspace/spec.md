# Local Emulator Full-Stack Dev Harness Spec

## Objective

Build a reusable local emulator full-stack harness for Omi development. V17 memory is the first customer, but the harness must be usable for future backend + desktop/app/web/hardware features.

This sits above the existing fully fake hermetic E2E harness and below dev-cloud proof. It is for local manual QA and product use, not deterministic pass/fail testing and not activation evidence.

## Required capabilities

- Start the local emulator/backend stack with one top-level `make` command.
- Reset all harness-owned local state with one top-level `make` command.
- Seed named synthetic product scenarios from Python-authored fixtures.
- Support a focused local V17 manual-QA flow without deploying to GCP.
- Launch a named desktop dev app profile against the local stack.
- Seed and select local Firebase Auth emulator users, including a default user and multi-user profiles.
- Fail fast with a checklist of missing required dev credentials/config values when default real-provider mode is selected and required keys are absent.
- Preserve the V17 proof boundary: local emulator evidence is not dev-cloud proof.

## Command surface

Top-level `make` commands are the stable developer interface. Heavy implementation must live under `scripts/dev-harness/`. The root `Makefile` is expected to be a thin dispatcher; this repository currently has no root `Makefile`, so implementation tickets may add one without changing the command contract.

Required initial commands:

```bash
make dev-up
make dev-check
make dev-reset
make seed-v17-scenario SCENARIO=happy_path
make list-v17-scenarios
make desktop-run-local USER=alice
make dev-status
make dev-down
make dev-logs
PROVIDER_MODE=offline make dev-up
```

Locked backing entrypoints:

| Command | Entrypoint |
|---|---|
| `make dev-up` | `scripts/dev-harness/dev-up.sh` |
| `make dev-check` | `scripts/dev-harness/dev-check.sh` |
| `make dev-reset` | `scripts/dev-harness/dev-reset.sh` |
| `make seed-v17-scenario SCENARIO=<name>` | `scripts/dev-harness/seed-v17-scenario.py` |
| `make list-v17-scenarios` | `scripts/dev-harness/list-v17-scenarios.py` |
| `make desktop-run-local USER=<name>` | `scripts/dev-harness/desktop-run-local.sh` |
| `make dev-status` | `scripts/dev-harness/dev-status.sh` |
| `make dev-down` | `scripts/dev-harness/dev-down.sh` |
| `make dev-logs` | `scripts/dev-harness/dev-logs.sh` |

Helper modules and scenario packages may live below `scripts/dev-harness/`, but the top-level command names and entrypoint paths are stable.

## Existing repo-native assets

The local emulator harness must reuse existing repo assets rather than creating parallel Firebase or fake-provider stacks:

- Firebase CLI config: `firebase.json` is authoritative and currently wires Firestore rules/indexes plus Firestore emulator port `8085`. Auth emulator support should be added by extending this file in implementation work.
- Firestore policy/index assets: `firestore.rules` and `firestore.indexes.json` are the rules and index files for the local harness and V17 emulator coverage.
- Existing V17 emulator npm scripts in `package.json` use short-lived `firebase emulators:exec --only firestore --project demo-v17-memory` commands. They are test assets/reference patterns, not the long-lived local manual-QA project.
- Existing emulator proof scripts under `backend/scripts/v17_*_emulator_test.*` demonstrate Firestore-emulator safety checks and may be reused or wrapped only where appropriate.
- The hermetic backend E2E runner `backend/testing/e2e/run.sh` and fakes under `backend/testing/e2e/fakes/` remain the deterministic fake/offline source of truth; `PROVIDER_MODE=offline` should reuse those implementations where possible.
- The desktop runner `desktop/macos/run.sh` is the existing build/launch primitive. `make desktop-run-local` should call it with a named local bundle/profile, explicit localhost service URLs, and local emulator Auth bootstrap.
- No root `Makefile` or README local-harness docs exist at this point; adding those is implementation/adoption work after this contract.

## Required local services

- Python backend.
- Rust desktop backend when a desktop scenario requires it.
- Firestore emulator.
- Firebase Auth emulator.
- Local Redis or equivalent local-only state service.
- Local filesystem roots for any harness-owned file/blob state.

## External dependency policy

All harness-authoritative application state must live in harness-owned local services or directories.

In `PROVIDER_MODE=real`, prompts, media, responses, request metadata, and any explicitly enabled provider resources leave the machine, may incur cost, and may be retained under provider policy. `dev-reset` does not delete provider logs or provider-retained data.

External processors use real dev-keyed services by default for interactive local product use. Offline providers are available through `PROVIDER_MODE=offline` and should reuse the same fake-provider implementation used by the hermetic test environment wherever possible.

A real provider may be used only when all of the following are true:

- the provider is reached only through the local provider broker/governor;
- the provider is not authoritative for any harness state;
- inputs are entirely synthetic or developer-created local QA data;
- the call is bounded by explicit timeout, request-count, cost, token, upload-byte, and audio-duration limits;
- no callback, webhook, queue, index, vector write, or other durable external side effect is used;
- required credentials are checked before startup or before the dependent flow runs;
- credential/account fingerprints are approved for local dev and are not shared team keys or production provider projects.

Offline provider mode must remove provider credentials from child processes and deny outbound provider/network egress. Provider modes must fail closed: never infer mode from key presence, never silently fall back from real to offline or offline to real, and require automation/non-interactive invocations to specify provider mode explicitly.

Allowed:

- Firestore/Auth emulators, local Redis when needed, and local files for stateful dependencies.
- Real external processors using explicit dev API keys by default for manual QA.
- Hermetic-shared offline providers under `PROVIDER_MODE=offline` for missing-key, outage, demo, or provider-independent debugging flows.

Disallowed:

- production data, production credentials, production UIDs, or production tokens;
- production Firebase/Auth/Firestore/GCS projects;
- external stateful services or hosted indexes for harness-owned state;
- implicit ambient GCP defaults;
- hosted vector databases or other external indexes as local-harness dependencies.

`make dev-up` defaults to `PROVIDER_MODE=real` and requires/checks credentials for enabled real-provider flows. `PROVIDER_MODE=offline make dev-up` starts the same local stack with hermetic-shared offline providers and no external-provider credentials.

## Provider safety defaults

Real-provider mode requires a checked-in provider matrix covering provider/account/project, billing owner and quota, training/data-use setting, retention policy and region, allowed endpoints, and whether stateful resources/files/asynchronous jobs are permitted.

Initial local governor defaults:

- `$2` estimated cost per session;
- `$10` per day per developer;
- concurrency `2`;
- one retry only for idempotent calls;
- zero retries for non-idempotent calls;
- fail closed when pricing is unknown or usage cannot be bounded;
- no automatic replay of pending provider jobs after restart.

Default data policy is synthetic-or-local-QA-only. Production exports, customer data, secrets, and unreviewed personal recordings are prohibited. Sending non-synthetic content requires an explicit per-session override and visible acknowledgement that content is leaving the machine. Raw prompt/response logging is off by default; metadata logging may include request ID, resolved model, latency, usage, status, and estimated cost.

## Local isolation invariant

The v1 harness uses one fixed Firebase demo project ID and one Firestore database:

- project ID: `demo-omi-local`
- database ID: `(default)`

Every backend, seeder, test, desktop, and Firebase CLI process must use that same project ID and explicit loopback emulator endpoints.

Harness scripts must construct an allowlisted child-process environment and must not inherit ambient ADC, service-account credentials, gcloud/Firebase project defaults, or production Firebase configuration.

Any seed, reset, or mutation command must refuse to run unless:

- the configured project ID begins with `demo-`;
- required emulator host variables point to loopback;
- the database ID is exactly `(default)`;
- the target state directory contains the harness ownership sentinel.

Harness-owned state should live under a root such as `${OMI_LOCAL_STATE_ROOT:-<repo>/.local/dev-harness}/<instance>`. Destructive commands must resolve paths, verify the sentinel, refuse unsafe roots, and stop only recorded owned processes.

## Command lifecycle semantics

- `make dev-up` starts or validates a long-lived named exploratory manual-QA instance.
- `make dev-down` stops only processes owned by that instance.
- `make dev-reset` clears only state owned by that instance.
- `make seed-v17-scenario` mutates the exploratory instance.
- `make dev-status` shows active instance, seeded scenario/users, provider mode, local endpoints, state root, and enabled external providers.
- Local pass/fail tests are not run against the long-lived manual-QA instance; deterministic tests belong in the hermetic harness.
- Commands fail on foreign port ownership and never kill unrelated processes.

## Auth model

Local auth should be close to production while remaining fully synthetic:

- use Firebase Auth emulator by default;
- pre-populate a default local test user;
- provide named multi-user profiles such as `alice` and `bob`;
- support selecting the desktop user profile during launch;
- never use production users or production tokens.

## Scenario fixture model

Scenario fixtures should be Python-authored for type checking, authoring, and testing. Fixtures should be safe to commit.

At minimum, each fixture should define:

- schema version;
- scenario ID and description;
- deterministic clock, user IDs, document IDs, and cursor secrets;
- synthetic users;
- selected active user;
- Auth seed and profile seed;
- Firestore, Redis, and file seeds as needed;
- local feature flags/config;
- request cases;
- expected route decision;
- expected returned memory IDs/content summaries;
- expected protected collection changes;
- expected fail-closed behavior where applicable.

Fixture files cannot select an evidence class. The local harness report writer hard-codes `evidence_class: LOCAL_EMULATOR_DEV`, `activation_eligible: false`, and a `NOT_ACTIVATION_EVIDENCE` watermark. Fixture validation must happen before any service mutation, and expected decisions must not be computed by calling the production decision code under test.

## V17 scenario coverage

At minimum, local V17 emulator scenarios must cover:

- default-off legacy-safe behavior;
- enabled happy path with synthetic Short-term, Long-term, and Archive data;
- Archive excluded from default reads;
- stale Short-term excluded from default reads;
- kill switch fail-closed;
- malformed cursor fail-closed;
- cross-user isolation with at least two synthetic users;
- GET path performs no V17 writes in the harness.

## Desktop-first scope

Desktop macOS is the first surface target. Initial acceptance requires:

- a named local desktop bundle/profile that does not collide with production, beta, or existing dev bundles;
- bundled/local configuration pointing to localhost services;
- sign-in or bootstrapping as a seeded Firebase Auth emulator user;
- one V17-relevant local read path exercised through desktop against local emulator state.

Mobile, web, and hardware support are later surfaces.

## Non-goals

- No replacement for the existing hermetic E2E harness.
- Local manual-QA pass/fail automation belongs in hermetic E2E; this harness may include safety/fixture/command-contract checks but is not a deterministic product test suite.
- No claim that local emulator evidence satisfies V17 dev-cloud Gate 2.
- No broad refactor of V17 product semantics.
- No hidden dependency on a developer's ambient GCP project.

## Proof labels and report metadata

Every local session summary must state:

- `evidence_class: LOCAL_EMULATOR_DEV`
- `activation_eligible: false`
- `watermark: NOT_ACTIVATION_EVIDENCE`

Only `DEV_CLOUD_PROOF` may be used for V17 Gate 2 evidence, and this harness must not be able to emit that label. `LOCAL_EMULATOR_DEV` is for local full-stack development confidence only.

Every local session summary should include schema version, run ID, scenario ID, scenario digest, git commit and dirty-state marker, config digest, Firebase project ID, Firestore database ID, emulator/tool versions, provider mode, provider/model/profile, credential fingerprint, external provider call summary, sanitized service endpoints, external egress allowlist, data policy, raw-trace setting, session budget, estimated cost, timestamps, manual-QA notes/status, V17 write-attempt counters where instrumented, protected-state digest where computed, and explicit non-claims.

The no-write claim requires both attempted-write instrumentation at the Firestore adapter/client boundary and before/after protected-collection digests.
