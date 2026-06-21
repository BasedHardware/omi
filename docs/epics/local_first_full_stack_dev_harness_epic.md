# Local Emulator Full-Stack Dev Harness Epic

**Status:** Proposed infra epic
**Primary customer:** V17 memory development and validation
**First surface target:** Desktop macOS app
**Long-term customer:** Any Omi feature that needs backend + desktop/app/web/hardware integration testing
**Related V17 docs:** `docs/rollout/v17-v3-proof-order.md`, `docs/runbooks/v17-v3-dev-cloud-proof.md`, `docs/epics/v17_memory_product_integration_epic.md`

## Problem

Omi has a fully fake hermetic E2E harness, but developers still need a deployed GCP/Firebase environment to honestly test local full-stack behavior. For V17 memory in particular, this slows iteration because:

- the desktop app can run locally, but normally points at cloud backends;
- hermetic E2E is intentionally fake and cannot catch emulator/runtime wiring issues;
- local live backend setup is credential-heavy and not scenario-driven;
- V17 dev-cloud proof is intentionally strict and should remain a promotion gate, not every developer's inner loop.

The result is a gap between fast hermetic tests and expensive dev-cloud proof.

## Goal

Create a local emulator full-stack development harness that lets developers run, seed, reset, and manually QA realistic Omi memory scenarios by actually using the product without waiting on GCP deploys, while preserving dev-cloud proof for the things only deployed GCP can prove.

The harness is general infrastructure. V17 memory is the first validation target because it needs high-confidence backend + desktop product behavior before cloud promotion. Deterministic pass/fail testing remains the job of the existing hermetic E2E harness.

## Non-goals

- Do not replace the existing hermetic test harness.
- Do not weaken V17 dev-cloud or production proof requirements.
- Do not use production data, production UIDs, production tokens, production Firebase projects, production Firestore projects, or production GCS buckets.
- Do not make local emulator evidence count as IAM, Cloud Run revision, deployed index, telemetry sink, or rollback proof.
- Do not make long-lived full-stack orchestration or desktop launch a mandatory CI gate in v1.
- Do not make V17 a dumping ground for general developer-infra work.

## Target developer experience

Top-level `make` commands are the stable user interface. Heavy implementation should live under `scripts/` so the command surface stays discoverable and maintainable.

```bash
make dev-up
make seed-v17-scenario SCENARIO=happy_path
make desktop-run-local USER=alice
make dev-status
make dev-reset
```

The exact backing script names may change to match repo conventions, but the top-level developer loop should remain one-command and scenario-driven.

## Architecture

The harness should provide:

- Python backend on localhost.
- Rust desktop backend when desktop flows need it.
- Firestore emulator.
- Firebase Auth emulator.
- pre-populated local test user by default.
- easy multi-user local test profiles for cross-user/isolation testing.
- local Redis or equivalent local-only state service.
- Python-authored synthetic scenario fixtures for V17 memory gates, projections, cursors, cross-user isolation, and rollback/kill-switch behavior.
- external processor integrations that use explicit dev API keys by default for realistic manual QA and can switch to offline providers with `PROVIDER_MODE=offline`.
- a prerequisite check that fails fast for core local prerequisites before startup and lists missing dev credentials when real-provider mode is selected.
- desktop local profile that points a named desktop bundle to localhost services.
- clear evidence labels that distinguish local emulator development from dev-cloud proof.

## Dependency boundary

All harness-authoritative application state must live in harness-owned local services or directories.

In `PROVIDER_MODE=real`, prompts, media, responses, request metadata, and any explicitly enabled provider resources leave the machine, may incur cost, and may be retained under provider policy. `dev-reset` does not delete provider logs or provider-retained data.

Allowed dependencies:

- local stateful services: Firestore emulator, Firebase Auth emulator, dedicated local Redis when needed, local files under harness-owned directories;
- local desktop/backend processes;
- allowlisted external processors only when explicitly selected for a scenario.

External processors use real dev-keyed services by default for interactive local product use. A developer can switch to offline deterministic providers with `PROVIDER_MODE=offline`; offline providers should reuse the same fake-provider implementation used by the hermetic test environment wherever possible to avoid maintaining two fake stacks.

A real provider may be used only when all of the following are true:

- the provider is reached only through the local provider broker/governor;
- the provider is not authoritative for any harness state;
- inputs are entirely synthetic or developer-created local QA data;
- the call is bounded by explicit timeout, request-count, cost, token, upload-byte, and audio-duration limits;
- no callback, webhook, queue, index, vector write, or other durable external side effect is used;
- required credentials are checked before startup or before the dependent flow runs;
- credential/account fingerprints are approved for local dev and are not shared team keys or production provider projects.

Offline provider mode should preserve the same app/backend interfaces but is a convenience mode for missing keys, outages, demos, and provider-independent debugging. It must remove provider credentials from child processes and deny outbound provider/network egress. Deterministic correctness tests remain in the hermetic harness.

Provider modes must fail closed: never infer mode from key presence, never silently fall back from real to offline or offline to real, and require automation/non-interactive invocations to specify provider mode explicitly.

Disallowed dependencies:

- production Firebase/Auth/Firestore/GCS projects;
- production UIDs, tokens, or user data;
- external stateful services or hosted indexes for harness-owned state;
- ambient GCP project/auth defaults as an implicit dependency;
- hosted vector databases or external indexes as local-harness dependencies.

`make dev-up` should default to `PROVIDER_MODE=real` and require/check credentials for the enabled real-provider flows. `PROVIDER_MODE=offline make dev-up` should start the same local stack with hermetic-shared offline providers and no external-provider credentials.

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

Local auth should be close to production by default:

- use Firebase Auth emulator rather than a broad auth bypass;
- seed a default local test user automatically;
- support named local test users such as `alice` and `bob` for cross-user scenarios;
- make desktop launch able to target a selected local user profile;
- keep local auth identities synthetic and clearly non-production.

## Scenario fixtures

Scenario fixtures should be Python-authored for easy type checking, authoring, and test reuse. They should be safe to commit and should include synthetic memory/user content only.

Each scenario should define, at minimum:

- scenario name;
- schema version and scenario ID;
- deterministic clock, user IDs, document IDs, and cursor secrets;
- synthetic users and selected active user;
- Auth seed, profile seed, Firestore seed, Redis seed, and file seed as needed;
- local feature flags/config state;
- request cases;
- expected route decision;
- expected default reads;
- expected explicit Archive reads where applicable;
- expected fail-closed behavior where applicable;
- expected protected collection changes.

Fixture files cannot select an evidence class. The local harness report writer must hard-code `evidence_class: LOCAL_EMULATOR_DEV`, `activation_eligible: false`, and a `NOT_ACTIVATION_EVIDENCE` watermark. Fixture validation must happen before any service mutation, and expected decisions must not be computed by calling the same production route-decision code being tested.

## Desktop-first target

Desktop macOS is the first surface target. Mobile, web, and hardware should be added later after the desktop path is useful.

The first desktop acceptance bar is:

- launch a named local desktop bundle/profile without mutating production, beta, or existing dev bundles;
- point the desktop app at localhost backend services;
- authenticate as a seeded local Firebase Auth emulator user;
- exercise at least one V17-relevant read path against local emulator state;
- keep all mutable state local.

## Local vs dev-cloud boundary

Local emulator development can support manual QA of:

- full-stack local wiring behavior;
- route-selection logic;
- fail-closed semantics;
- no legacy fallback after V17 selection;
- no V17 writes in GET paths under the harness;
- desktop request/response shape compatibility;
- Firebase/Auth emulator behavior for synthetic users;
- deterministic scenario behavior with local mutable state.

Local emulator development must not claim:

- real Cloud Run runtime identity;
- real Firestore IAM or least privilege;
- real deployed Firestore index readiness;
- real Firebase Auth issuer/audience behavior in a deployed project;
- real telemetry sinks or rollback propagation;
- production or dev-cloud activation readiness.

Evidence generated by this harness should be labelled `LOCAL_EMULATOR_DEV`. Only dev-cloud proof can produce `DEV_CLOUD_PROOF` evidence for V17 activation.

## Evidence report metadata

Every local session summary should include:

- `schema_version`
- `evidence_class: LOCAL_EMULATOR_DEV`
- `activation_eligible: false`
- `watermark: NOT_ACTIVATION_EVIDENCE`
- `run_id`
- `scenario_id`
- `scenario_digest`
- git commit and dirty-state marker
- config digest
- Firebase project ID and Firestore database ID
- emulator/tool versions
- provider mode and external provider call summary
- provider/model/profile, credential fingerprint, data policy, raw-trace setting, session budget, and estimated cost
- sanitized service endpoints
- start/end timestamps
- test results
- V17 write-attempt counters
- protected-state digest
- explicit non-claims

The no-write claim requires both attempted-write instrumentation at the Firestore adapter/client boundary and before/after protected-collection digests.

## Ticket pack

Executable tickets live under `.codex-autorunner/tickets/`.

| Ticket | Outcome |
|---|---|
| `TICKET-010-local-first-spec.md` | Establish the local emulator harness contract and `make` command surface. |
| `TICKET-015-local-runtime-safety.md` | Add demo-project, environment, process, port, and destructive-operation safety guards. |
| `TICKET-020-dev-up-foundation.md` | Add `dev-up` / `dev-reset` foundation for backend-local emulator services. |
| `TICKET-025-provider-capabilities.md` | Define real-default provider mode, offline hermetic-shared provider mode, credential checks, and external side-effect guardrails. |
| `TICKET-030-v17-scenario-fixtures.md` | Add Python-authored synthetic V17 product-state scenarios and seed/reset tooling. |
| `TICKET-040-local-emulator-v17-manual-qa.md` | Add V17 local manual-QA workflow/status/session summaries outside mandatory CI. |
| `TICKET-050-desktop-local-profile.md` | Add a desktop local profile for "Omi Dev Local". |
| `TICKET-060-dev-cloud-preview-bridge.md` | Post-MVP handoff: define optional branch preview deploy/proof bridge without weakening gates. |
| `TICKET-070-docs-and-adoption.md` | Document the developer loop and proof boundary. |

## Acceptance

- A developer can run at least one V17 memory happy-path and one fail-closed scenario locally against emulators without GCP deploy access.
- The desktop app can be launched against the local stack with a named dev profile and seeded local Firebase Auth emulator user.
- The harness fails fast with a clear missing-dev-credential checklist when default real-provider mode is selected and required dev keys are absent.
- All harness-owned mutable state is local and resettable.
- The docs explicitly state that local emulator development supplements, but does not replace, V17 dev-cloud proof.
