# Canonical Memory Firestore IAM and Service Account Deployment Gate

**Status:** local Firebase emulator gate now exists for vector repair outbox persistence and client-rule denial, but this is **not a cloud IAM validation** and does not claim that production IAM was inspected or changed. It makes the canonical-memory production write-gate assumptions explicit until they can be validated against the real Firebase project.

## Boundary

Canonical-memory Firestore state is server-owned. The backend uses the Firebase Admin SDK / Google Cloud Firestore Admin SDK with a backend service account to read and write the canonical memory collections. Mobile, desktop, web, third-party, and MCP clients must not use the Firebase client SDK to access these collections directly.

Checked-in `firestore.rules` is the client boundary: clients denied for direct read, create, update, and delete on protected memory paths. Product access must flow through backend APIs, which derive authenticated UID, rollout state, access policy, and archive/default visibility server-side. There must be **no client SDK writes** to canonical memory collections.

Protected paths:

```text
users/{uid}/memory_items/{memory_id}
users/{uid}/memory_operations/{operation_id}
users/{uid}/memory_outbox/{event_id}
users/{uid}/memory_control/{doc_id}
users/{uid}/memory_control/app_key_memory_grants
users/{uid}/memory_state/{doc_id}
users/{uid}/memory_commits/{commit_id}
users/{uid}/memory_evidence/{evidence_id}
mcp_api_keys/{key_id}
```

## Required service account

The deployed backend service account is the only principal expected to mutate canonical-memory Firestore state. Use least privilege for the service account:

- Grant Firestore document read/write through `roles/datastore.user` on the production project unless deployment evidence proves a narrower custom role is available and maintained.
- Do not grant broad owner/editor roles for the canonical-memory write gate.
- Do not distribute service account keys to clients. Production should use workload identity / platform-provided credentials where possible; local development may use `SERVICE_ACCOUNT_JSON` only on trusted developer/server machines.
- Keep vector/search/outbox consumer credentials separate when feasible so a compromised consumer cannot bypass the Long-term apply transaction.

## Dev-cloud before production IAM proof

For canonical `GET /v3/memories` activation, cloud IAM must now be proven first in a dedicated non-production Firebase/GCP project. See:

- `docs/rollout/memory-v3-proof-order.md`
- `docs/runbooks/memory-v3-dev-cloud-proof.md`
- `docs/runbooks/memory-v3-production-activation.md`

Dev-cloud proof must use a deployed branch backend revision with its actual runtime identity. A local backend using dev credentials is supplemental only and cannot satisfy the dev-cloud gate.

Dev-cloud IAM acceptance requires:

- explicit dev project ID, project number, database ID, and runtime service-account unique ID;
- hard-stop checks that abort on known production project IDs/numbers and reject implicit default projects;
- runtime identity read permissions sufficient for memory GET and no Firestore data-write permissions;
- a separate fixture-writer identity for synthetic control/head/projection docs;
- effective IAM evidence including inherited grants;
- denial evidence for unsafe/runtime write paths where feasible.

After dev-cloud GO, production IAM remains a production-only final activation blocker. Production activation must verify production runtime identity and effective IAM, but should not use production as the first enabled-path proof environment.

## Rollout/deployment checklist

Before enabling memory writes for any production user:

1. Confirm `firebase.json`, `firestore.rules`, and `firestore.indexes.json` are deployed for the target Firebase project.
2. Confirm the backend runs with the intended service account and has Firestore access no broader than required; record the IAM evidence in the rollout ticket or deployment change.
3. Confirm client direct access remains denied by Firestore Security Rules. Until real validation is available, the static guard is `pytest tests/unit/test_memory_firestore_security_rules.py -q`.
4. Confirm the backend write path still uses the atomic apply adapter and operation journal; do not introduce a direct product writer bypass.
5. Keep rollout external mode explicit:
   - `MEMORY_MODE=off`: legacy only.
   - `MEMORY_MODE=shadow`: no product-visible memory writes.
   - `MEMORY_MODE=write`: whitelisted server-side memory sidecar writes only after gates pass.
   - `MEMORY_MODE=read`: superset of write; memory read service authoritative for whitelisted users only after read/vector gates pass.
6. Confirm account deletion/source tombstone generation fences and rollback compatibility projection are healthy before widening the allowlist.

## Emulator validation gate

Local Firebase emulator validation is now wired for the memory vector repair/purge outbox writer, client-rule denial, and transactional lease contention:

```bash
npm run test:memory-vector-repair-outbox:emulator
npm run test:memory-vector-repair-outbox-rules:emulator
npm run test:memory-vector-repair-outbox-lease:emulator
```

Prerequisites:

- Firebase CLI (`firebase`) / `firebase-tools`
- Java runtime (`java`) for the Firebase emulator
- npm dependencies installed from the repository root (`npm install` when `node_modules` is absent)
- Python backend dependencies including `google-cloud-firestore`

What this gate proves locally:

- Backend/Admin-context writer path persists deterministic `vector_repair_purge` records at `users/{uid}/memory_outbox/{record_id}`.
- Repeating the same stale-vector observation performs an idempotent `.set(...)` to the same stable document with the same `record_id`/`idempotency_key`.
- New records retain the pending retry contract: `status=pending`, `attempt_count=0`, `last_error=null`.
- Write failures are not silently swallowed by `write_vector_repair_purge_outbox_records(...)`; exceptions propagate to the caller for route/worker telemetry and retry/dead-letter handling.
- Signed-in client SDK direct read/create/update/delete on `memory_outbox` and the other protected memory collections is denied by Firestore Security Rules; backend/Admin SDK access is required and bypasses client rules through IAM.
- `lease_vector_repair_purge_outbox_records(...)` claims due pending outbox records through Firestore transaction re-read/update semantics when the client supports transactions.
- Eight competing local emulator lease attempts against the same pending `users/{uid}/memory_outbox/{record_id}` document produce exactly one returned claim and one stored `in_progress` lease owner/timestamp set, proving the local transaction-contention contract for at-most-one worker action on that record.

What this gate does **not** prove:

- Production cloud IAM/service-account bindings or deployed Security Rules in any real Firebase project.
- Pinecone delete/repair behavior, tombstone precedence, duplicate stale-vector removal, retry/dead-letter workers, or central low-cardinality telemetry.
- Shared `ns2` isolation or vector benchmark/cutover readiness.

## memory vector repair outbox execution contract

The first explicit scheduler/lease-owner seam is `run_vector_repair_outbox_worker_tick(...)` in `backend/database/vector_repair_outbox_worker.py`. It is a bounded one-tick contract for Cloud Run Jobs, Cloud Scheduler → Cloud Run/Tasks, or another server-owned scheduler; it is **not** registered with any production scheduler in this repository.

Contract:

1. A server-owned caller constructs `VectorRepairOutboxWorkerTickConfig` from control-plane/env config. The default config is `enabled=false`, so the worker fails closed and does not lease records unless a deployer explicitly enables it.
2. The caller supplies the backend/Admin Firestore client, target `uid`, stable `worker_id`/lease owner identity, bounded `limit`, `lease_seconds`, and `max_attempts`.
3. The tick leases due pending `vector_repair_purge` records from `users/{uid}/memory_outbox/*` through `lease_vector_repair_purge_outbox_records(...)`, marking stored documents `in_progress` with `lease_owner`, `leased_at`, `locked_at`, and `lease_expires_at`.
4. Leased records are passed to `process_vector_repair_purge_outbox_records(...)` with injected dependencies only: authoritative item loader, Pinecone-shaped vector deleter, Pinecone-shaped vector repairer, and the Firestore ack writer.
5. Ack/retry/dead-letter patches are applied through `ack_vector_repair_purge_outbox_record(...)`. The returned summary is deterministic and low-cardinality-friendly: `enabled`, `worker_id`, `uid`, `leased_count`, `processed_count`, `skipped_count`, `failed_count`, `ack_failed_count`, `actions`, and `errors`.
6. Duplicate same-batch `idempotency_key` records remain at most one adapter side effect through the existing worker idempotency seam. Lease contention remains protected by the transaction re-read/update contract validated in the local emulator harness.

### Disabled-by-default Cloud Run/Tasks wrapper contract

`backend/scripts/vector_repair_outbox_worker_entrypoint.py` is the checked-in Cloud Run/Tasks wrapper contract for this tick. It now exposes both the CLI smoke path and a minimal ASGI HTTP shim at `POST /memory-vector-repair-outbox-worker/tick`. It is intentionally fake-injectable and does not create Cloud Tasks, Cloud Scheduler, Cloud Run Jobs, Firebase emulator processes, or Pinecone clients while disabled.

The wrapper now includes a narrow production dependency resolver, but the resolver is invoked only after `MEMORY_VECTOR_REPAIR_OUTBOX_WORKER_ENABLED=true` and config validation. Disabled/default CLI smoke still does not initialize Pinecone, the embedding provider, or the Firestore client singleton.

Wrapper behavior:

1. Reads only explicit server-owned env/config.
2. Fails closed/no-ops when `MEMORY_VECTOR_REPAIR_OUTBOX_WORKER_ENABLED` is absent, empty, or `false`; a disabled invocation prints one deterministic JSON summary and does not lease records.
3. Treats malformed booleans, missing enabled `uid`, missing enabled `worker_id`, and non-positive numeric bounds as config denial; it prints a deterministic JSON summary with `config_valid=false` and exits nonzero before calling the tick.
4. When enabled and injected with production-safe dependencies, invokes exactly one `run_vector_repair_outbox_worker_tick(...)` for one explicit uid and stable lease owner. There is no unbounded production scan and no client-supplied arbitrary uid execution.
5. Prints/returns one JSON object suitable for Cloud Run/Tasks logs. Unit tests cover disabled no-op, malformed config denial, required uid/lease-owner denial, enabled fake tick summary, worker/action failure summary, dependency resolver invocation, missing dependency config denial before lease, HTTP shim disabled no-op, HTTP shim config/dependency denial, HTTP shim fake enabled tick, and no scheduler enqueue side effects.
6. Production dependency resolution requires `PINECONE_API_KEY`, `PINECONE_INDEX_NAME`, and `OPENAI_API_KEY`; constructs Admin Firestore from `database._client.db`; loads authoritative `users/{uid}/memory_items/{memory_id}` as `MemoryItem`; and wraps Pinecone `index.delete`/`index.upsert` plus `utils.llm.clients.embeddings.embed_query` through the explicit `ns2` adapter seam.

Disabled CLI smoke command shape:

```bash
python3 backend/scripts/vector_repair_outbox_worker_entrypoint.py
```

Proposed disabled Cloud Run service command shape (not yet applied):

```bash
uvicorn scripts.vector_repair_outbox_worker_entrypoint:app --host 0.0.0.0 --port 8080
```

Proposed env contract (not yet enabled):

```text
MEMORY_VECTOR_REPAIR_OUTBOX_WORKER_ENABLED=false        # default/fail-closed; only literal true enables
MEMORY_VECTOR_REPAIR_OUTBOX_UID=<server-owned uid shard> # required only when enabled; no unbounded scan
MEMORY_VECTOR_REPAIR_OUTBOX_WORKER_ID=<stable service/region/revision lease owner> # required only when enabled
MEMORY_VECTOR_REPAIR_OUTBOX_LIMIT=<small positive int, default 25>
MEMORY_VECTOR_REPAIR_OUTBOX_LEASE_SECONDS=<positive int, default 300>
MEMORY_VECTOR_REPAIR_OUTBOX_MAX_ATTEMPTS=<positive int, default 3>
PINECONE_API_KEY=<worker secret; required only when enabled>
PINECONE_INDEX_NAME=<worker index; required only when enabled>
OPENAI_API_KEY=<embedding provider key; required only when enabled>
VECTOR_REPAIR_PINECONE_NAMESPACE=ns2
```

Proposed Cloud Run/Tasks deployment shape (not yet applied):

```text
service: memory-vector-repair-outbox-worker
trigger: Cloud Scheduler or Cloud Tasks HTTP POST /memory-vector-repair-outbox-worker/tick, disabled by default; OIDC-authenticated at Cloud Run IAM/platform layer
identity: dedicated backend worker service account with Firestore Admin/Datastore User read-write on users/*/memory_outbox and read on authoritative memory memory item state; Pinecone credentials scoped to ns2-compatible vector delete/upsert only
config/env: wrapper env above, with MEMORY_VECTOR_REPAIR_OUTBOX_WORKER_ENABLED=false until production gates pass
input: explicit uid shard/list source must be server-owned; no client-supplied arbitrary uid execution
output/telemetry: monotonic counters for leased/processed/skipped/failed/ack_failed/action=delete|repair/retry/dead_letter/backlog_count/oldest_pending_age/duration with bounded labels only; alerts on dead_letter growth, ack failures, Pinecone/retry failure ratio, scheduler starvation, and stale-vector backlog age
auth: Cloud Run IAM (roles/run.invoker) plus Scheduler/Tasks OIDC serviceAccountEmail/audience; the app shim intentionally has no app-level bearer token
```

### memory vector repair outbox central telemetry/alert seam

`backend/database/memory_vector_repair_outbox_telemetry.py` defines the central fake-injectable telemetry seam for the outbox worker. It converts one deterministic worker tick summary plus optional backlog/duration inputs into low-cardinality metric/event payloads for an injected emitter. This is a code seam and alert contract only; it is **not** wired to Prometheus/OpenTelemetry/Cloud Monitoring in production by this repository slice.

Telemetry contract before enablement:

```text
metrics:
  vector_repair_outbox_worker_records_total{worker_component,status=leased|processed|skipped|failed}
  vector_repair_outbox_worker_action_total{worker_component,action=delete|repair}
  vector_repair_outbox_worker_retry_total{worker_component,reason}
  vector_repair_outbox_worker_dead_letter_total{worker_component,reason}
  vector_repair_outbox_worker_ack_failure_total{worker_component,reason}
  vector_repair_outbox_worker_backlog_count{worker_component,status=pending|dead_letter}
  vector_repair_outbox_worker_oldest_pending_age_seconds{worker_component,status=pending}
  vector_repair_outbox_worker_duration_ms{worker_component,status=tick}
events:
  vector_repair_outbox_worker_dead_letter
  vector_repair_outbox_worker_ack_failure
allowed labels only:
  worker_component, status, action, reason, event_type
forbidden labels/fields:
  uid, worker_id, vector_id, memory_id, record_id, idempotency_key, raw error text
```

Proposed alert gates that must be implemented in the real metrics backend before enablement:

- `dead_letter_count > 0` for any uid shard over 15 minutes: page and pause enablement/expansion.
- `ack_failed_count > 0` over 5 minutes: page because Pinecone may have mutated while Firestore ack state is ambiguous.
- `failed_count / leased_count >= 0.10` for 15 minutes: warn; `>= 0.25` for 15 minutes: page and disable worker expansion.
- `oldest_pending_age_seconds > 3600`: warn; `> 21600`: page and block cutover.
- `leased_count == 0` while `pending backlog_count > 0` for 30 minutes: warn for scheduler/IAM/lease starvation.

Pass/fail criteria:

- Pass: central sink receives monotonic counters/events with only allowed labels; alert policies exist for dead letters, ack failures, retry spike ratio, scheduler starvation, and oldest pending backlog; telemetry emitter failures are recorded as telemetry failures and never mask worker cleanup/ack results.
- Fail: any metric/event label includes uid/worker_id/vector_id/memory_id/record_id/idempotency_key/raw error text; worker can be enabled before dashboards and alert policies exist; telemetry exceptions change delete/repair/ack outcome.

### Cloud Run/Tasks/Scheduler static deployment contract and OIDC/IAM proof artifact

`docs/epics/memory_vector_repair_outbox_cloud_deployment_contract.yaml` is now the checked-in disabled-by-default Cloud Run/Tasks/Scheduler contract artifact for this worker. It is a static readiness/proof artifact, not an applied deployment. It deliberately keeps:

- Cloud Run `MEMORY_VECTOR_REPAIR_OUTBOX_WORKER_ENABLED` at `"false"` by default.
- Cloud Scheduler `state: PAUSED` by default.
- Cloud Run invoker IAM required (`run.googleapis.com/invoker-iam-disabled: "false"`) and ingress restricted.
- OIDC `serviceAccountEmail` plus `audience` matching the intended worker tick URI.
- Explicit service-account/IAM proof targets for `roles/run.invoker`, `roles/cloudtasks.enqueuer`, `roles/iam.serviceAccountTokenCreator`, and `roles/datastore.user` (or a narrower maintained Firestore custom role).
- One-at-a-time Cloud Tasks dispatch with bounded `maxAttempts`, `maxRetryDuration`, and dead-letter routing placeholders.
- Server-owned uid-shard placeholders only; clients must not select arbitrary uid execution.
- Explicit proof commands and pass/fail criteria to run later with `gcloud`/Firebase against the target project.

`backend/scripts/vector_repair_outbox_oidc_iam_proof.py` is the safe read-only proof runner for the Cloud Run/Tasks/Scheduler OIDC/IAM slice. Without `--execute`, it prints a `NOT_RUN` JSON readiness inventory containing the exact `gcloud run services describe`, `gcloud run services get-iam-policy`, `gcloud scheduler jobs describe`, `gcloud tasks queues describe`, `gcloud projects get-iam-policy`, and `gcloud iam service-accounts get-iam-policy` commands. With `--execute`, it only runs those allowlisted read-only describe/get-iam-policy commands, then checks that the worker env remains disabled, Scheduler is paused, OIDC `serviceAccountEmail`/`audience` match the contract, public Run invoker bindings are absent, and required worker/scheduler IAM bindings exist. It fails honestly when `gcloud`, project, region, service, job, queue, auth, or IAM resources are missing.

Important readiness caveat: the executable trigger surface now matches the intended HTTP/OIDC Cloud Run/Tasks shape through `POST /memory-vector-repair-outbox-worker/tick`, but OIDC is still enforced by Cloud Run IAM/platform configuration rather than local test credentials. In this local slice, `gcloud` was not installed/on PATH and no target project/region was configured, so the proof runner was run only in `NOT_RUN`/prerequisite-failure mode. No Cloud Run service, Cloud Tasks queue, Cloud Scheduler job, IAM binding, deployed rules validation, production Firestore IAM proof, or Pinecone operation was created or claimed.

### Production Firestore IAM and deployed Security Rules proof runner

`backend/scripts/firestore_rules_iam_proof.py` is the safe read-only readiness/proof runner for production Firestore IAM and deployed Security Rules on the memory vector repair outbox paths. It inventories the exact production validation commands by default and only runs read-only commands when `--execute` is explicitly passed:

```bash
python3 backend/scripts/firestore_rules_iam_proof.py
python3 backend/scripts/firestore_rules_iam_proof.py --project PROJECT_ID --execute
```

Read-only inventory commands:

```text
gcloud firestore databases describe (default) --project PROJECT_ID --format=json
gcloud projects get-iam-policy PROJECT_ID --format=json
gcloud iam service-accounts get-iam-policy WORKER_SA --project PROJECT_ID --format=json
gcloud iam service-accounts get-iam-policy BACKEND_SA --project PROJECT_ID --format=json
firebase firestore:rules:get --project PROJECT_ID
```

Prerequisites for a real PASS/FAIL proof are an authenticated `gcloud` CLI, authenticated Firebase CLI, a target Firebase/GCP project, the deployed Firestore database, the deployed Security Rules release, and the intended Admin worker/backend service-account names. Without those prerequisites the runner emits `status=NOT_RUN` with explicit missing prerequisites; that is a readiness artifact, not production evidence.

Pass/fail criteria for the runner (including explicit client denial checks):

- `client_denial.memory_outbox`: deployed Security Rules deny client read/create/update/delete on `users/{uid}/memory_outbox/{record_id}`.
- `client_denial.app_key_memory_grants`: deployed Security Rules deny client read/create/update/delete on `users/{uid}/memory_control/app_key_memory_grants`; memory app/key memory grant assignment remains server-owned/Admin-only.
- `mcp_api_key_inventory`: deployed Security Rules/IAM proof includes `mcp_api_keys/{key_id}` as Admin-only MCP API-key inventory; clients cannot self-read or mutate MCP key `app_id`/`scopes`.
- `worker_firestore_iam`: Admin worker service account has Firestore read/write IAM (`roles/datastore.user` or narrower custom role) and no owner/editor role.
- `memory_control.server_owned`: `users/{uid}/memory_control/state` remains server-owned/Admin-only, including the `vector_repair_outbox_enabled` gate.
- `app_key_grants.server_owned`: `users/{uid}/memory_control/app_key_memory_grants` remains server-owned/Admin-only and cannot be self-granted by app/key clients.
- `no_client_vector_repair_enablement`: no client enablement of `vector_repair_outbox_enabled` is possible through deployed rules.
- `no_broad_public_access`: project and service-account IAM have no broad public access (`allUsers` / `allAuthenticatedUsers`).

The runner is guarded against mutating commands: no `firebase deploy`, no `gcloud firestore databases update`, no IAM `set-iam-policy`, and no IAM binding mutations. It does not deploy rules, change IAM, mutate databases, write outbox documents, or call Pinecone. A PASS is still only Firestore IAM/deployed-rules evidence for these paths; it is not production approval and does not close Pinecone duplicate stale physical-ID cleanup, shared `ns2` isolation, retry/dead-letter telemetry, or benchmark gates.

### Pinecone repair/shared-ns2 validation readiness runner

`backend/scripts/pinecone_repair_validation_readiness.py` is the safe-by-default readiness artifact for the real Pinecone validation still required by Oracle P0-4. Default mode is inventory only and prints `status=NOT_RUN`; it never deletes, upserts, queries, or mutates Pinecone in default mode:

```bash
python3 backend/scripts/pinecone_repair_validation_readiness.py
```

A future real throwaway validation run must be explicitly gated with credentials and safety flags. The runner requires `PINECONE_API_KEY`, `PINECONE_INDEX_NAME`, `PINECONE_INDEX_HOST`, a non-`ns2` throwaway namespace, a long `memory-proof-...` throwaway vector id prefix, exact prefix confirmation, and explicit mutation acknowledgement before any future execute-mode mutation can be considered:

```bash
python3 backend/scripts/pinecone_repair_validation_readiness.py \
  --execute \
  --allow-throwaway-mutation \
  --test-namespace memory-proof-throwaway-namespace \
  --throwaway-prefix memory-proof-ticket- \
  --confirm-throwaway-prefix memory-proof-ticket- \
  --shared-ns2-readonly
```

Pass/fail criteria for a later real Pinecone proof:

- `duplicate_stale_physical_ids`: duplicate stale physical IDs under the confirmed throwaway prefix are all deleted or repaired, with no stale duplicate remaining after validation.
- `tombstone_precedence_delete`: missing/deleted/tombstoned/purged authoritative items choose delete over repair for every matching throwaway vector.
- `live_stale_item_repair_upsert`: a live stale item produces exactly one repair/upsert with current projection/account-generation metadata.
- `retry_dead_letter_behavior`: injected or observed Pinecone delete/upsert failures produce retry patches, then `dead_letter` at max attempts, with ack failures counted separately.
- `shared_ns2_isolation`: shared `ns2` isolation is read-only inventory only in this runner; evidence must prove legacy vectors not touched, legacy queries exclude memory schema records, and baseline legacy recall is retained before any production memory `ns2` inserts.
- `legacy_vectors_not_touched`: no broad delete/update is allowed; mutating validation must be constrained to the confirmed throwaway test namespace and throwaway prefix, never shared `ns2`.

Current local output is an honest readiness/non-claim artifact only. The local environment has no Pinecone target configuration recorded here, so no real duplicate stale physical-ID delete/repair, tombstone precedence, retry/dead-letter behavior, or shared `ns2` isolation proof is claimed. This is not production approval.

Remaining deployment gates before enabling this contract in production:

- Run `python3 backend/scripts/vector_repair_outbox_oidc_iam_proof.py --project PROJECT_ID --region REGION --execute` against the target project and attach exact JSON output before unpausing Scheduler or enabling the worker.
- Run `python3 backend/scripts/firestore_rules_iam_proof.py --project PROJECT_ID --execute` against the target Firebase project and attach exact JSON output before enabling `vector_repair_outbox_enabled` or the worker.
- Production-safe uid sharding/backlog discovery and worker identity ownership model.
- Real Pinecone delete/upsert validation with duplicate stale physical IDs and tombstone precedence in namespace `ns2`.
- Retry/backoff/dead-letter central telemetry and alerts.
- Shared `ns2` isolation evidence proving legacy queries exclude memory schema records or a separate namespace/filter decision.

## Rollback notes

- `read → write` should be a config rollback using the reconciled memory-derived compatibility projection; it must not expose stale vectors or resurrect deleted memories.
- `write → off` after persistent memory writes is not a blind flag flip. It requires decommission reconciliation so memory-created memories do not disappear from the user experience.
- If IAM or Security Rules are found wrong, set `MEMORY_MODE=off` or remove affected users from the allowlist first, stop memory workers, then fix and redeploy rules/IAM before retrying writes.

## Verification currently available

Static checks only:

```bash
cd backend
pytest tests/unit/test_memory_firestore_security_rules.py tests/unit/test_memory_firestore_iam_deployment_doc.py -q
```

Cloud IAM and deployed Security Rules remain future gates until production project access is available. Local Firebase emulator validation is available through:

```bash
npm run test:memory-vector-repair-outbox:emulator
npm run test:memory-vector-repair-outbox-rules:emulator
npm run test:memory-vector-repair-outbox-lease:emulator
cd backend && pytest tests/unit/test_memory_firestore_security_rules.py tests/unit/test_memory_firestore_iam_deployment_doc.py tests/unit/test_memory_vector_repair_outbox_emulator_harness.py -q
```
