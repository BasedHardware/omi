# Isolated JIT QA Cloud Run plane

`.github/workflows/jit_qa_cloud_run.yml` is the only entrypoint for the
isolated cloud proof. It is manual, accepts a dispatch from `main` only, and
requires the exact current `main` SHA to have a successful first-attempt
`Release Eligibility` run. It uses `based-hardware-dev` in `us-central1` and
creates or updates only these named resources:

- `backend-jit-qa` — the main API service;
- `desktop-backend-jit-qa` — the desktop companion API;
- `llm-gateway-jit-qa` — the isolated, service-token-authenticated gateway;
- `knowledge-ledger-drain-qa-job` — the ledger migration job; and
- `daily-memory-sweep-qa-job` — the bounded daily sweep job.

The API services use bare development ADC and the dedicated
`jit-qa-runtime@based-hardware-dev.iam.gserviceaccount.com` runtime identity.
They use the named `jit-qa` Firestore database in `based-hardware-dev`, while
Firebase token verification is explicitly addressed to `based-hardware`.
The workflow creates that native Firestore database in `us-central1` if it is
missing. `FIRESTORE_DATABASE_ID=jit-qa` is mechanically accepted only with
the dev project, dev stage, and QA auth fence, so an accidental production
process cannot fall back into this database.
`OMI_JIT_QA_AUTH_ONLY=true` enables the narrow application fence: after token
verification, every HTTP/WebSocket route rejects a UID other than
`vi7SA9ckQCe4ccobWNxlbdcNdC23`, before account, Redis, or model work. The
Firebase Admin client uses verify-only credentials and its mutation methods are
blocked; Firestore ADC remains available for the isolated data plane.
The backend, desktop, drain, and sweep profiles bind the development
`POSTHOG_PROJECT_API_KEY` individually. This is required for the JIT rollout
authority to observe the `jit-processing-v1` control-plane decision; an
unconfigured PostHog client is not a rollout proof.

The API and gateway use a dedicated Basic-tier 1 GiB Memorystore instance named
`jit-qa-redis`; its AUTH value and gateway service token live in the dedicated
`jit-qa-redis-password` and `jit-qa-gateway-token` secrets. The services use
private-range VPC egress for Redis and the exact gateway URL returned by the
deployment. Gateway-only routing is required (`gateway` route and feature mode,
direct-model exception `false`); a missing or unhealthy gateway cannot be
reported as QA ready. The gateway's public Cloud Run transport is still
application-authenticated with the scoped token and caller allowlist
`backend,desktop`; `/health` is the only unauthenticated probe. Readiness
requires pre-existing development-project `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`,
and `PERPLEXITY_API_KEY` secrets because the checked-in gateway route catalog
contains those managed lanes; the workflow only grants the QA runtime access
and never creates, exports, or prints their values. No shared
Redis/cache, Typesense, Pinecone, queue, connector, notification, or customer
credential binding is copied into the plane.

Memorystore Basic M1 pricing is approximately `$0.049/GiB-hour` in Iowa, or
about `$35.77` for 730 hours for the 1 GiB instance, before other dev costs.
See [Memorystore Redis pricing](https://cloud.google.com/memorystore/docs/redis/pricing).
The workflow does not create a Scheduler trigger. To clean up the owned QA
resources, first disable or cancel any run, then delete the three services, two
jobs, the named `jit-qa` database, Redis/token resources, and the dedicated
runtime identity in `based-hardware-dev`; redeployment is idempotent and
recreates the same fixed names and minimum bindings. Never run cleanup against
`based-hardware`.

The drain and sweep jobs deploy with gates closed and the explicit QA UID in
their environment. QA sweep executions use a direct allowlist inventory and
never read or advance the global daily-sweep cursors. `run_once=true` requires
`RUN_ONCE`, checks `run.jobs.runWithOverrides`, executes the drain first, and
polls the exact returned execution through `status.conditions[type=Completed]`,
then reads the QA database's apply-control, migration-completion, and bounded
projection documents and requires matching writer/head/epoch fences, stable
ledger mode, zero live legacy rows, and a nonempty completed scan. Only that
durable proof makes a sweep eligible. This closed deployment workflow has no
paid-model execution stage: the sweep model gate and kill switch remain false,
and `run_once` only admits the bounded ledger drain. Model qualification
requires a separately reviewed workflow and budget receipt. A deployment-only
dispatch performs no model work. Execution artifacts contain resource and
execution identities only, never customer content.

Verification reads each deployed Cloud Run resource and checks the immutable
image digest, exact environment and secret bindings, runtime identity, fixed
QA names, and the actual v1/v2 container paths. It probes the gateway and both
HTTP services without customer data, then writes an activation-shaped
`omi.jit.qa.cloud.v1` readiness candidate containing exact URLs, revisions,
image digests, source SHA, and the full dependency vector. The candidate has
`reviewed: false`; a root operator must independently inspect the live
resources and promote it to a reviewed activation receipt.

The local functional fallback is
`scripts/dev-harness/jit_qa_local_stack.py`. It is useful for emulator contract
proofs but is not evidence that the isolated cloud companion, gateway, Redis,
or real Firebase identity path is serving.
