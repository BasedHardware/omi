# Pinecone owner partition rollout

The operator copies one owner's vectors into a bounded hash bucket, verifies
payloads and search freshness, then atomically changes that owner's route. UID
filters remain mandatory because different owners share buckets. There is no
customer-visible search setting.

**This runbook is a procedure, not evidence of deployment or savings.** Complete
provider and user-path qualification for the exact implementation before issuing
GO. Do not manufacture receipts to bypass an unfinished check.

## Preconditions and fleet evidence

1. Deploy the same routing implementation to every process that can read or write
   this Pinecone index. Use immutable image digests and record their source SHAs.
   Include the four Cloud Run backend services, GKE listener and pusher, scheduled
   jobs, repair/backfill scripts, and any development service with production
   credentials. A scaled-to-zero old writer must not later restart unchanged.
2. Follow `.github/AGENTS.md` and the backend release workflow. Run
   `backend/scripts/verify_backend_release_vector.py` for its documented surfaces;
   it does **not** prove pusher, every job, or independently launched scripts.
   Record separate runtime evidence for those writers and the serving Firestore
   data-plane database identity. The operator must use that same database.
3. Qualify all seven vector families, with the real user-facing path repeated
   three times, update/delete, collision isolation and account cleanup. Run a
   production pilot only for the explicitly authorized test accounts. General
   rollout requires a successful production pilot on the same implementation.
4. Have a reviewer check the complete writer inventory and evidence within 24
   hours of each production apply. Changing the fleet invalidates the review.

Use the deployed backend environment and Google ADC. `PINECONE_INDEX_NAME` selects
its index and `PINECONE_API_KEY` comes from the existing secret environment; never
put credentials in receipts or command arguments. Only the exact dev index
`memories-backend-dev` is exempt from the production evidence gate. Emulator mode
requires `--emulator-project demo-...`, `FIRESTORE_EMULATOR_HOST`, and the dev index;
a production index rejects an emulator even for inventory.

## Inventory and explicit test users

Run from `backend/`. `rollout_dir` is a private durable directory outside the
repository. Keep the same directory when resuming a migration.

```sh
rollout_dir="$HOME/mobile-ux-agent/metrics/pinecone-partition-rollout"
.venv/bin/python scripts/migrate_pinecone_partitions.py \
  --uid "$test_uid" --output-dir "$rollout_dir"
```

Without `--apply`, this reads route documents only, including virtual legacy
routes for owners without a document. It neither creates route rows nor calls
Pinecone. Repeat `--uid` or use a private `--uids-file` containing one UID per line.
All seven families are selected unless `--family` is explicitly provided.

After reviewing the actual evidence, run the production test-user pilot:

```sh
.venv/bin/python scripts/migrate_pinecone_partitions.py \
  --uid "$test_uid" --apply --pilot \
  --fleet-receipt "$rollout_dir/fleet.json" \
  --test-user-proof "$rollout_dir/dev-go.json" \
  --output-dir "$rollout_dir/pilot"
```

`dev-go.json` must explicitly list the authorized production test UIDs. The pilot
command performs provider qualification and cutover; it does not itself exercise
the app UI. After it finishes, exercise the actual test-user searches, updates,
deletes and adjacent flows, repeat three times, and record the production pilot
GO proof. Do not proceed on provider checks alone.

## Production evidence format

All artifact references have `path` (relative to the referring receipt) and
`sha256` (SHA-256 of the exact bytes). Artifacts must be JSON. Paths, identities
and hashes below describe the required schema; these are not ready-made GO files.

`fleet.json` requires:

| Field | Requirement |
|---|---|
| `schema_version` | Integer `1` |
| `index_name` | Exact target index |
| `implementation_commit` | Full 40-character source commit |
| `reviewed_by`, `reviewed_at` | Reviewer identity and UTC/offset timestamp within 24 hours |
| `writer_inventory_complete` | Boolean `true`, asserted only after the inventory review |
| `writer_inventory_artifact` | Hashed JSON containing the complete `writer_names` list |
| `writers` | One entry for every name in that inventory, no duplicates |

Each writer entry requires `name`, full `source_sha`, immutable
`image` ending in `@sha256:<64 hex characters>`, `implementation_present: true`,
`runtime_verified: true`, and a hashed `evidence` JSON artifact. Writer source
commits can differ if the reviewer verifies each contains the implementation.
The minimum named entries are `backend`, `backend-sync`, `backend-sync-backfill`,
`backend-integration`, `backend-listen`, and `pusher`. This minimum is **not** an
exhaustive fleet inventory. Record independently executed writers too, using
the immutable image in which they run; do not omit an uncontainerized writer to
make the gate pass. Bring it under a verified immutable runtime first.

A test-user GO proof requires `schema_version: 1`, `status: "GO"`, matching
`implementation_commit`, all seven names in `families_verified`,
`real_user_path_verified: true`, `cleanup_verified: true`, integer `repeats >= 3`,
and nonempty hashed `artifacts`. For `--pilot`, include
`allowed_production_test_uids`. For general rollout, require
`stage: "production_pilot"` and the exact production `index_name`.

The CLI validates structure and artifact hashes; it cannot independently infer
that a screenshot, runtime inspection or a reviewer's assertion is truthful.
The reviewed artifacts must substantiate those assertions. Never use a generated
fixture proof as production user-path evidence.

## Bounded rollout and subsequent discovery

```sh
.venv/bin/python scripts/migrate_pinecone_partitions.py \
  --sweep --max-owners 10 --max-route-docs 10000 \
  --output-dir "$rollout_dir/all"

.venv/bin/python scripts/migrate_pinecone_partitions.py \
  --sweep --resume --apply --max-owners 10 --max-route-docs 10000 \
  --max-provider-requests 1000 --max-read-units 10000 \
  --max-write-units 10000 --max-upload-bytes 100000000 \
  --fleet-receipt "$rollout_dir/fleet.json" \
  --test-user-proof "$rollout_dir/production-pilot-go.json" \
  --output-dir "$rollout_dir/all"
```

Sweep uses a single-field `mode == legacy` Firestore query, then filters the index
locally. With `--resume`, it first queries `mode == copying` under the same shared
document budget and reports unowned copying routes as blocked. It avoids adding a composite index. The owner and route-document caps
are real bounds; receipts report deferred owners and incomplete scans. An empty
bounded scan is not proof every historical owner was migrated. Dormant owners
without registered route rows are invisible to sweep until a routed read/write
registers them. Explicit trusted owner lists can seed their migration directly.
A scan dominated by another index or repeatedly blocked owners needs an explicit
reviewed UID list or a larger bounded scan; do not claim global completion.

A process runs sequentially with at most three qualification attempts (default
two). Only a known qualification/revision race retries automatically. Unknown
provider outcomes stop that owner. Provider request and upload-byte limits are
checked before calls; read/write units are measured after responses, so one RPC
can exceed its unit threshold. Counters include only units the provider returns;
a zero write-unit counter does not mean writes are free. Request/upload-byte
bounds still apply when a provider response omits usage. Firestore reads are separately bounded by route
scan size and selected owners/families, not included in Pinecone usage counters.
A budget stop leaves the source authoritative and an owned resumable journal.
The qualified implementation rejects owners whose inventory cannot be proven
complete (including 10,000-or-more matches); record and resolve that cohort
before calling the rollout complete.

After the first full rollout and actual user-path/health verification, schedule a
monitored bounded sweep for later registered legacy owners. **Do not install that
schedule before the rollout owner verifies the release.** Each run needs current
reviewed fleet evidence, a single execution lock, private durable journals,
alerts on nonzero exit/blocked routes, and an owner for recovery. Monitor error
rates, search parity, provider units and bill changes; a migration count alone
does not prove savings.

## Receipts, interruption and recovery

Each run atomically writes `run-<UTC>-<id>.json`; per-family owner journals live
under `owners/<hashed-key>.json`. Directories are mode `0700` and files `0600`.
They contain routing identities, migration coordination tokens and counters, not
API credentials, record payloads or customer conversation text. Treat them as
private. Exit `0`/`GO` means the selected bounded batch passed its checks, never
that the entire fleet or product is verified. Exit `2`/`PARTIAL` or `STOPPED`
requires inspecting the receipt; error messages from providers are omitted to
avoid leaking payloads or credentials.

An interrupted `copying` route resumes only with `--resume`, the original output
directory, the matching local migration token, and the same direction. Use
`--sweep --resume` to revisit owned copying routes, or resume owners explicitly with `--uid` or `--uids-file`. Another operator's copying route is refused. Do not steal a token,
reset a revision, clear pending operations, or assume an old request has settled.
For uncertain operations, obtain evidence of the original provider request's
settled outcome and scope before using the state reconciliation protocol. Keep
serving from the authoritative route while investigating.

Rollback uses the same explicit owner selection plus `--apply --rollback` and
current production evidence. It copies the **current** authoritative bucket back
into the legacy namespace, reconciles deletions, verifies freshness and parity,
and only then switches the route. Never toggle an environment flag, restore an
old binary, or switch to a retained stale copy. A failed rollback leaves the
current route authoritative. Account deletion must finish its all-copy purge;
never clear a tombstone or route journal to bypass that check.

Old copies are deliberately retained after cutover and still incur storage cost.
This command does not purge namespaces. Any later cleanup needs a separate
owner-scoped retention/rollback policy and proof. Tiny internal barrier records
have no UID, are excluded by every customer owner filter, and are not customer
records. They provide freshness evidence because a successful no-op delete can
return an LSN that never appears in the indexed-LSN header.
