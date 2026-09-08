# Isolated JIT QA seed and ledger-drain proof

`backend/scripts/jit_qa_seed_and_verify.py` is the operator for the named JIT
QA data plane. It is intentionally separate from deployment and model
execution. The only account it may touch is
`vi7SA9ckQCe4ccobWNxlbdcNdC23` in project `based-hardware-dev`, Firestore
database `jit-qa`. It refuses a different project, database, UID, emulator, or
customer Firebase credential selector.

The deployment/database factory creates the named Firestore database. Before
seeding, run the explicit create-only bootstrap against that named database:

```bash
python3 backend/scripts/jit_qa_seed_and_verify.py bootstrap
```

Bootstrap fails unless the named database has an empty user plane. A backend
startup may have left the one known metadata-only
`conversation_recovery_state/byok_abandonment_sweep` cursor; bootstrap accepts
it only with the exact `generation`, `resume_after_path` (null), and
`updated_at` fields, and preserves it. Any other collection, document, field,
or malformed value fails closed. The receipt distinguishes this preserved
runtime metadata from the empty user plane. Bootstrap creates only the fixed
QA UID's minimal `users/{uid}` profile and `testers/{uid}` entitlement marker,
and calls `ensure_canonical_apply_control_state` to create the real
compatibility apply-control fence. It never creates a migration completion or
ledger cutover receipt; those remain owned by the drain job's canonical
`publish_ledger_migration_cutover` path. A durable
`jit_qa_bootstrap/{uid}` marker makes a retry idempotent while refusing any
unowned or malformed document. The default database and every other UID remain
out of scope.

The initial writer mode must be `compatibility`; all rows and evidence are
namespaced by the supplied run ID. Existing documents with a foreign marker
are a hard failure, and rerunning the same seed is a read-only no-op for rows
already owned by that run.

## Prepare and inspect

Use the existing dev-only credential loader or the workflow's workload
identity. Verify the shell is pointed at the development project before
running the script. No model call or Cloud Run execution is made by these
commands.

```bash
python3 backend/scripts/jit_qa_seed_and_verify.py bootstrap

python3 backend/scripts/jit_qa_seed_and_verify.py \
  --run-id qa-proof-20260905 prepare

python3 backend/scripts/jit_qa_seed_and_verify.py \
  --run-id qa-proof-20260905 inspect
```

`prepare` creates 101 canonical `memory_items` rows and their synthetic
evidence documents. The rows intentionally omit `ledger_schema_version`; they
are the same legacy-shaped canonical fixture used by the bounded drain
emulator proof. The printed result contains counts and the target identity,
never row content. `inspect` reads only metadata and reports the count of
legacy versus ledger rows, migration completion/projection presence, the
content-free metadata digest, and whether the global drain cursor exists.

## Execute and verify the two pages

The reviewed QA workflow owns Cloud Run execution. Run its explicit drain
execution twice, preserving the content-free summary for each execution. The
first summary must report 100 migrated rows and one remaining user; the second
must report one migrated row and one cutover user. A third allowlisted retry
must be a stable no-op. The workflow's execution summaries can be wrapped as
`{"execution": "...", "summary": {...}}` or supplied as the summary object
itself.

```bash
python3 backend/scripts/jit_qa_seed_and_verify.py \
  --run-id qa-proof-20260905 verify \
  --first-summary /path/to/drain-1-summary.json \
  --second-summary /path/to/drain-2-summary.json \
  --retry-summary /path/to/drain-retry-summary.json
```

Verification requires the fixed allowlisted identity, no errors, exact
`100 + 1` progress, 101 retained rows and evidence documents, a fenced ledger
completion and 101-row prompt projection, and no global cursor write. It does
not accept an injected rollout authorizer or an emulator result as cloud
evidence.

## Rollback and rollforward

Rollback is an explicit control-plane operation and requires a separate
confirmation. It does not rewrite the 101 canonical rows or evidence. After
the rollback receipt is captured, run one more reviewed QA drain execution;
the rollforward should migrate zero rows, cut over once, and restore the
ledger completion. Re-run `inspect` to confirm the metadata digest is unchanged
and all 101 rows remain present.

```bash
python3 backend/scripts/jit_qa_seed_and_verify.py \
  --run-id qa-proof-20260905 rollback \
  --confirmation ROLLBACK_QA
```

This command is intentionally not part of deployment and should only be run
after the first `verify` pass has been reviewed. The operator never deletes
fixture rows, evidence, or customer data.

## Receipt contract

The deployment producer and this consumer use the same cloud receipt contract:

* `schema_version`: `omi.jit.qa.cloud.v1`
* `project` and `data_plane_project`: `based-hardware-dev`
* `firestore_database_id`: `jit-qa`
* `auth_project`: `based-hardware`
* services: `backend-jit-qa`, `desktop-backend-jit-qa`,
  `llm-gateway-jit-qa`
* `exact_python_url`, `exact_desktop_url`, `exact_gateway_url`
* full 40-character `full_source_sha`
* ready revision and immutable image digest for Python and desktop services
* non-empty dependency vector naming the isolated Firestore, Redis, gateway,
  Firebase-auth verification, storage, Pub/Sub, and Scheduler bindings

The operator's drain proof is a separate data-plane receipt. A reviewed cloud
resource receipt proves the endpoint/dependency tuple; it does not prove the
101-row drain. Both must be retained together, with the exact Cloud Run
execution names joined to the three summary files.

## Emulator proof boundary

For local correctness, run the real Firestore emulator proof under
`firebase emulators:exec`:

```bash
firebase emulators:exec --only firestore --project demo-omi-jit-qa \
  'PYTHONPATH=backend python3 backend/scripts/jit_qa_seed_and_verify_emulator_test.py'
```

That test exercises bootstrap, 101-row seed, the actual migration helper's
100+1 progress, canonical publication, rollback, and roll-forward against a
real emulator. It injects only the rollout decision and labels that boundary
in its output. The named-cloud command still rejects emulators and requires
the deployed job's real rollout/admission path; an emulator pass is not a
cloud readiness result.
