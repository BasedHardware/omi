# V17 Firestore IAM and Service Account Deployment Gate

**Status:** local Firebase emulator gate now exists for V17 vector repair outbox persistence and client-rule denial, but this is **not a cloud IAM validation** and does not claim that production IAM was inspected or changed. It makes the V17 production write-gate assumptions explicit until they can be validated against the real Firebase project.

## Boundary

V17 Firestore memory state is server-owned. The backend uses the Firebase Admin SDK / Google Cloud Firestore Admin SDK with a backend service account to read and write the canonical V17 collections. Mobile, desktop, web, third-party, and MCP clients must not use the Firebase client SDK to access these collections directly.

Checked-in `firestore.rules` is the client boundary: clients denied for direct read, create, update, and delete on protected V17 paths. Product access must flow through backend APIs, which derive authenticated UID, rollout state, access policy, and archive/default visibility server-side. There must be **no client SDK writes** to V17 memory collections.

Protected paths:

```text
users/{uid}/memory_items/{memory_id}
users/{uid}/memory_operations/{operation_id}
users/{uid}/memory_outbox/{event_id}
users/{uid}/memory_control/{doc_id}
users/{uid}/memory_state/{doc_id}
users/{uid}/memory_commits/{commit_id}
users/{uid}/memory_evidence/{evidence_id}
```

## Required service account

The deployed backend service account is the only principal expected to mutate V17 Firestore state. Use least privilege for the service account:

- Grant Firestore document read/write through `roles/datastore.user` on the production project unless deployment evidence proves a narrower custom role is available and maintained.
- Do not grant broad owner/editor roles for the V17 write gate.
- Do not distribute service account keys to clients. Production should use workload identity / platform-provided credentials where possible; local development may use `SERVICE_ACCOUNT_JSON` only on trusted developer/server machines.
- Keep vector/search/outbox consumer credentials separate when feasible so a compromised consumer cannot bypass the Long-term apply transaction.

## Rollout/deployment checklist

Before enabling V17 writes for any production user:

1. Confirm `firebase.json`, `firestore.rules`, and `firestore.indexes.json` are deployed for the target Firebase project.
2. Confirm the backend runs with the intended service account and has Firestore access no broader than required; record the IAM evidence in the rollout ticket or deployment change.
3. Confirm client direct access remains denied by Firestore Security Rules. Until real validation is available, the static guard is `pytest tests/unit/test_v17_firestore_security_rules.py -q`.
4. Confirm the backend write path still uses the atomic apply adapter and operation journal; do not introduce a direct product writer bypass.
5. Keep rollout external mode explicit:
   - `V17_MODE=off`: legacy only.
   - `V17_MODE=shadow`: no product-visible V17 writes.
   - `V17_MODE=write`: whitelisted server-side V17 sidecar writes only after gates pass.
   - `V17_MODE=read`: superset of write; V17 read service authoritative for whitelisted users only after read/vector gates pass.
6. Confirm account deletion/source tombstone generation fences and rollback compatibility projection are healthy before widening the allowlist.

## Emulator validation gate

Local Firebase emulator validation is now wired for the V17 vector repair/purge outbox writer, client-rule denial, and transactional lease contention:

```bash
npm run test:v17-vector-repair-outbox:emulator
npm run test:v17-vector-repair-outbox-rules:emulator
npm run test:v17-vector-repair-outbox-lease:emulator
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
- Write failures are not silently swallowed by `write_v17_vector_repair_purge_outbox_records(...)`; exceptions propagate to the caller for route/worker telemetry and retry/dead-letter handling.
- Signed-in client SDK direct read/create/update/delete on `memory_outbox` and the other protected V17 collections is denied by Firestore Security Rules; backend/Admin SDK access is required and bypasses client rules through IAM.
- `lease_v17_vector_repair_purge_outbox_records(...)` claims due pending outbox records through Firestore transaction re-read/update semantics when the client supports transactions.
- Eight competing local emulator lease attempts against the same pending `users/{uid}/memory_outbox/{record_id}` document produce exactly one returned claim and one stored `in_progress` lease owner/timestamp set, proving the local transaction-contention contract for at-most-one worker action on that record.

What this gate does **not** prove:

- Production cloud IAM/service-account bindings or deployed Security Rules in any real Firebase project.
- Pinecone delete/repair behavior, tombstone precedence, duplicate stale-vector removal, retry/dead-letter workers, or central low-cardinality telemetry.
- Shared `ns2` isolation or vector benchmark/cutover readiness.

## V17 vector repair outbox execution contract

The first explicit scheduler/lease-owner seam is `run_v17_vector_repair_outbox_worker_tick(...)` in `backend/database/v17_vector_repair_outbox_worker.py`. It is a bounded one-tick contract for Cloud Run Jobs, Cloud Scheduler → Cloud Run/Tasks, or another server-owned scheduler; it is **not** registered with any production scheduler in this repository.

Contract:

1. A server-owned caller constructs `V17VectorRepairOutboxWorkerTickConfig` from control-plane/env config. The default config is `enabled=false`, so the worker fails closed and does not lease records unless a deployer explicitly enables it.
2. The caller supplies the backend/Admin Firestore client, target `uid`, stable `worker_id`/lease owner identity, bounded `limit`, `lease_seconds`, and `max_attempts`.
3. The tick leases due pending `vector_repair_purge` records from `users/{uid}/memory_outbox/*` through `lease_v17_vector_repair_purge_outbox_records(...)`, marking stored documents `in_progress` with `lease_owner`, `leased_at`, `locked_at`, and `lease_expires_at`.
4. Leased records are passed to `process_v17_vector_repair_purge_outbox_records(...)` with injected dependencies only: authoritative item loader, Pinecone-shaped vector deleter, Pinecone-shaped vector repairer, and the Firestore ack writer.
5. Ack/retry/dead-letter patches are applied through `ack_v17_vector_repair_purge_outbox_record(...)`. The returned summary is deterministic and low-cardinality-friendly: `enabled`, `worker_id`, `uid`, `leased_count`, `processed_count`, `skipped_count`, `failed_count`, `ack_failed_count`, `actions`, and `errors`.
6. Duplicate same-batch `idempotency_key` records remain at most one adapter side effect through the existing worker idempotency seam. Lease contention remains protected by the transaction re-read/update contract validated in the local emulator harness.

### Disabled-by-default Cloud Run/Tasks wrapper contract

`backend/scripts/v17_vector_repair_outbox_worker_entrypoint.py` is the checked-in Cloud Run/Tasks wrapper contract for this tick. It is intentionally fake-injectable and does not create Cloud Tasks, Cloud Scheduler, Cloud Run Jobs, Firebase emulator processes, or Pinecone clients while disabled.

The wrapper now includes a narrow production dependency resolver, but the resolver is invoked only after `V17_VECTOR_REPAIR_OUTBOX_WORKER_ENABLED=true` and config validation. Disabled/default CLI smoke still does not initialize Pinecone, the embedding provider, or the Firestore client singleton.

Wrapper behavior:

1. Reads only explicit server-owned env/config.
2. Fails closed/no-ops when `V17_VECTOR_REPAIR_OUTBOX_WORKER_ENABLED` is absent, empty, or `false`; a disabled invocation prints one deterministic JSON summary and does not lease records.
3. Treats malformed booleans, missing enabled `uid`, missing enabled `worker_id`, and non-positive numeric bounds as config denial; it prints a deterministic JSON summary with `config_valid=false` and exits nonzero before calling the tick.
4. When enabled and injected with production-safe dependencies, invokes exactly one `run_v17_vector_repair_outbox_worker_tick(...)` for one explicit uid and stable lease owner. There is no unbounded production scan and no client-supplied arbitrary uid execution.
5. Prints one JSON object suitable for Cloud Run/Tasks logs. Unit tests cover disabled no-op, malformed config denial, required uid/lease-owner denial, enabled fake tick summary, worker/action failure summary, dependency resolver invocation, missing dependency config denial before lease, and no scheduler enqueue side effects.
6. Production dependency resolution requires `PINECONE_API_KEY`, `PINECONE_INDEX_NAME`, and `OPENAI_API_KEY`; constructs Admin Firestore from `database._client.db`; loads authoritative `users/{uid}/memory_items/{memory_id}` as `V17MemoryItem`; and wraps Pinecone `index.delete`/`index.upsert` plus `utils.llm.clients.embeddings.embed_query` through the explicit `ns2` adapter seam.

Proposed disabled command shape (not yet applied):

```bash
python3 backend/scripts/v17_vector_repair_outbox_worker_entrypoint.py
```

Proposed env contract (not yet enabled):

```text
V17_VECTOR_REPAIR_OUTBOX_WORKER_ENABLED=false        # default/fail-closed; only literal true enables
V17_VECTOR_REPAIR_OUTBOX_UID=<server-owned uid shard> # required only when enabled; no unbounded scan
V17_VECTOR_REPAIR_OUTBOX_WORKER_ID=<stable service/region/revision lease owner> # required only when enabled
V17_VECTOR_REPAIR_OUTBOX_LIMIT=<small positive int, default 25>
V17_VECTOR_REPAIR_OUTBOX_LEASE_SECONDS=<positive int, default 300>
V17_VECTOR_REPAIR_OUTBOX_MAX_ATTEMPTS=<positive int, default 3>
PINECONE_API_KEY=<worker secret; required only when enabled>
PINECONE_INDEX_NAME=<worker index; required only when enabled>
OPENAI_API_KEY=<embedding provider key; required only when enabled>
V17_VECTOR_REPAIR_PINECONE_NAMESPACE=ns2
```

Proposed Cloud Run/Tasks deployment shape (not yet applied):

```text
service/job: v17-vector-repair-outbox-worker
trigger: Cloud Scheduler or Cloud Tasks HTTP/job tick, disabled by default; OIDC-authenticated if HTTP-triggered
identity: dedicated backend worker service account with Firestore Admin/Datastore User read-write on users/*/memory_outbox and read on authoritative V17 memory item state; Pinecone credentials scoped to ns2-compatible vector delete/upsert only
config/env: wrapper env above, with V17_VECTOR_REPAIR_OUTBOX_WORKER_ENABLED=false until production gates pass
input: explicit uid shard/list source must be server-owned; no client-supplied arbitrary uid execution
output/telemetry: monotonic counters for leased/processed/skipped/failed/ack_failed/action=delete|repair/dead_letter plus bounded error classes; alerts on dead_letter growth, ack failures, Pinecone failures, and stale-vector backlog age
```

Remaining deployment gates before enabling this contract in production:

- Real Cloud Run/Tasks or Scheduler wiring and OIDC/IAM proof for the worker identity and trigger principal.
- Production Firestore IAM and deployed Security Rules validation in the target Firebase project.
- Production-safe uid sharding/backlog discovery and worker identity ownership model.
- Real Pinecone delete/upsert validation with duplicate stale physical IDs and tombstone precedence in namespace `ns2`.
- Retry/backoff/dead-letter central telemetry and alerts.
- Shared `ns2` isolation evidence proving legacy queries exclude V17 schema records or a separate namespace/filter decision.

## Rollback notes

- `read → write` should be a config rollback using the reconciled V17-derived compatibility projection; it must not expose stale vectors or resurrect deleted memories.
- `write → off` after persistent V17 writes is not a blind flag flip. It requires decommission reconciliation so V17-created memories do not disappear from the user experience.
- If IAM or Security Rules are found wrong, set `V17_MODE=off` or remove affected users from the allowlist first, stop V17 workers, then fix and redeploy rules/IAM before retrying writes.

## Verification currently available

Static checks only:

```bash
cd backend
pytest tests/unit/test_v17_firestore_security_rules.py tests/unit/test_v17_firestore_iam_deployment_doc.py -q
```

Cloud IAM and deployed Security Rules remain future gates until production project access is available. Local Firebase emulator validation is available through:

```bash
npm run test:v17-vector-repair-outbox:emulator
npm run test:v17-vector-repair-outbox-rules:emulator
npm run test:v17-vector-repair-outbox-lease:emulator
cd backend && pytest tests/unit/test_v17_firestore_security_rules.py tests/unit/test_v17_firestore_iam_deployment_doc.py tests/unit/test_v17_vector_repair_outbox_emulator_harness.py -q
```
