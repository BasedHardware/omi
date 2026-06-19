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

Local Firebase emulator validation is now wired for the V17 vector repair/purge outbox writer:

```bash
npm run test:v17-vector-repair-outbox:emulator
npm run test:v17-vector-repair-outbox-rules:emulator
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

What this gate does **not** prove:

- Production cloud IAM/service-account bindings or deployed Security Rules in any real Firebase project.
- Pinecone delete/repair behavior, tombstone precedence, duplicate stale-vector removal, retry/dead-letter workers, or central low-cardinality telemetry.
- Shared `ns2` isolation or vector benchmark/cutover readiness.

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
cd backend && pytest tests/unit/test_v17_firestore_security_rules.py tests/unit/test_v17_firestore_iam_deployment_doc.py tests/unit/test_v17_vector_repair_outbox_emulator_harness.py -q
```
