# V17 Firestore IAM and Service Account Deployment Gate

**Status:** documentation/static guard only. This is **not a cloud IAM validation** and does not claim that production IAM was inspected or changed. It makes the V17 production write-gate assumptions explicit until they can be validated against the real Firebase project and emulator.

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

## Emulator validation prerequisites

Real Security Rules validation must be added once the local/CI environment has:

- Firebase CLI (`firebase`)
- Java runtime (`java`) for the Firebase emulator
- npm is not sufficient by itself

Target emulator coverage: signed-in client reads/writes to every protected V17 collection are denied, while backend/Admin SDK access is exercised outside client rules. Record exact emulator commands and outputs in `v17_memory_implementation_tickets.md` when this becomes available.

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

Cloud IAM, deployed Security Rules, and Firebase emulator validation remain future gates until the required tools and production/project access are available.
