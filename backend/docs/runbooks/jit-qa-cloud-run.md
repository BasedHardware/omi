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
The desktop QA service also receives the development `GEMINI_API_KEY` binding
required by its batch OCR path; backend and gateway do not receive that
environment binding. All QA workloads share the runtime identity, so its
resource-level Secret Manager grants are accessible to every workload using
that identity. This is a shared QA trust boundary, not per-workload IAM
isolation; the desktop-only binding does not prevent another QA workload from
fetching the development key directly.

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

## Tombstoned sweep model invocations and the sweep-repair operator

The summary agent certifies failures before its first provider dispatch through
an invocation-scoped, irreversible dispatch latch. Such failures move `pending`
to `pre_dispatch_released` transactionally, retaining a content-free
`failure_reason` and incrementing `pre_dispatch_releases`. A later run can
claim the same identity without a repair receipt. Three releases are allowed;
the fourth failure moves to `pre_dispatch_exhausted` with
`blocked_reason=pre_dispatch_release_limit`. The source remains incomplete and
the cursor does not advance. Production operators can inspect those fields on
`daily_memory_sweep_model_invocation_fences/{invocation_id}`; this change does
not add a production repair CLI. Unknown failures and everything at or after
first dispatch remain `indeterminate`. Account deletion, generation changes,
foreign identities, and missing user payloads never release a claim.

The manual operator's `sweep-repair` operation
(`jit_qa_manual_operator.yml`, confirmation `SWEEP_REPAIR_QA`) remains QA-only.
`backend/scripts/jit_qa_sweep_repair.py` pages through accounting for diagnostics
and rejects failed streams, page-cap exhaustion, malformed matching timestamps,
and more than four matching attempts. These reads are **not an absence proof**:
`llm_gateway_attempts` is best-effort, asynchronous post-provider accounting,
and pagination has no shared snapshot. A dropped write or a late insertion
before the cursor can leave a scan empty after a provider call. An empty scan
is labeled `accounting_absence_unproven` and never authorizes a retry.

Recorded attempts require a real owning `jit_run_id` and remain an explicitly
authorized retry path, not a claim that the original provider never ran.
Without recorded attempts, the operator must independently establish that the
exact claim never dispatched **and its worker has terminated**. They must
supply both `--attestation-confirmation
ATTEST_NO_PROVIDER_DISPATCH_AND_WORKER_TERMINATED` and
`--attestation-reference <content-free-evidence-reference>`. The workflow exposes
the same pair as `repair_attestation_confirmation` and
`repair_attestation_reference`; neither is inferred or defaulted. A reference
identifies reviewed evidence, not raw logs or prompt content.

The receipt explicitly says `provider_outcome: operator_attested_no_dispatch`.
It binds the full invocation identity, claim token (null on legacy claims),
claim time, operator identity, attestation time, assertion, and evidence
reference. Both issuance and consumption validate that binding and require
`claimed_at + MODEL_INVOCATION_LEASE + 2 minutes < attested_at`. The tool
validates the assertion's structure and attribution; it cannot validate its
truth. It never calls this a reservation-absence proof or a no-spend result.
An incorrect human attestation can authorize duplicate dispatch. Without
independently sufficient evidence, leave the invocation indeterminate.

Why reservation absence is not implemented here:

- `llm_gateway/gateway/jit_budget.py` commits a reservation in
  `jit_cloud_qa_budgets_v1/{sha256(uid + NUL + run_id)}` before the JIT executor
  calls a provider. Unknown outcomes retain the reservation. It is per owner
  and run, not request id, and applies only to requests carrying the JIT contract.
- `gateway/request_context.py::validated_jit_budget_values` accepts entirely
  absent JIT headers as ordinary traffic. The QA manifest's gateway route and
  `OMI_LLM_GATEWAY_ALLOW_DIRECT_MODEL_EXCEPTION=false` do not make those headers
  mandatory at gateway ingress. Production sweeps do not use this QA contract.
- Existing fences do not persist a JIT run/request namespace before dispatch.
  `write_qa_sweep_run_receipt` writes the `jit_qa_sweep_runs` document after the
  scheduler returns, with neither claim ownership nor start/end timestamps.
  Temporal proximity cannot authoritatively join a legacy fence to a run.
- A future automatic protocol must persist the exact reservation namespace in
  the claim, enforce reservation-only dispatch end to end, verify the serving
  plane's configuration, and atomically close that namespace while proving it
  has never reserved. A strongly consistent absence read alone still races a
  delayed worker reserving after the read; lease expiry does not terminate it.

Legacy tombstones, including the QA claims beginning `518f8c2c` and
`8e479fc9`, are not repairable by accounting/reservation absence. Their honest
path is the independently evidenced operator attestation above, or remaining
blocked. No run id is synthesized. Previously issued `no_recorded_attempt`
receipts are rejected at consumption and by the workflow artifact validator;
do not delete receipts to bypass the single-repair rule.

Repair writes one receipt transactionally against the unchanged tombstoned
claim (`pending`, `indeterminate`, `payload_expired`, or
`pre_dispatch_exhausted`). The next claim consumes it exactly once. At most
one receipt may ever exist per invocation. Repair refuses an unexpired lease,
a `returned` fence, a changed claim, or an environment/UID outside the QA fence.
Repair performs no model calls and no scheduler mutation; `sweep-verify`
remains the execution path.

An incomplete sweep source is a named blocked outcome, not an opaque failure:
the scheduler records `uid=<uid>:source_incomplete:<local-date>:<reason>` and
leaves the cursor untouched, and the run receipt retains the dispatch evidence
of any admitted gateway request even when its output never staged. A day that
is merely over the conversation or character budget is truncated and processed;
only eligibility incompleteness (a still-processing or unfinished row) stalls.

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

The QA HTTP services advertise `jit-cloud-qa-v1`; the dedicated gateway enforces
that same provider-attempt budget. This capability is confined to these named
QA services. It does not alter rollout enrollment or open either maintenance job.

For an installed desktop startup observation, launch the exact QA bundle with
the one-off environment override (alongside the caller's usual QA environment
and automation setup as needed):

```bash
/usr/bin/open -n --env OMI_JIT_QA_DISABLE_REALTIME=1 /Applications/omi-jit-qa.app
```

The desktop applies this switch only when the bundle identifier is
`com.omi.omi-jit-qa` and the value is exactly `1`; it returns before `ensureWarm`
can mint a Live token or open a realtime socket. Stable, Beta, and other
development bundles retain their normal realtime warmup behavior, and any other
value leaves the QA bundle unchanged. This is a startup cost-isolation control
for QA observation, not a product rollout flag or evidence of a completed
realtime acceptance turn. Voice/PTT acceptance cannot be evaluated with this
override enabled.

The shared reserved QA target selector pins
`OMI_FORCE_BUCKET_CANDIDATES=0` and `OMI_FORCE_BUCKET_WORKSTREAMS=0`;
both wrapper and direct `run.sh` launches forward them through `open` and
persist them in the bundle environment for cold reopen. This isolates JIT qualification from
sibling candidate/workstream calls outside its budget. Ordinary named dev
bundles retain their defaults; use a separately named bundle for those experiments.
