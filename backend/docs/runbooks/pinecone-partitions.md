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

What the 2026-11-02 rollout learned about building that inventory:

- A writer is any runtime that holds a Pinecone key **and** sets `PINECONE_INDEX_NAME`;
  `database/vector_db.py` builds no client without both. Cloud Run jobs count. Take a
  job's digest from its latest execution, because job specs often name a mutable tag.
  The rollout found `notifications-job` (scheduled every 15 minutes) and two dormant
  jobs still on pre-partition images, holding the key and the production index.
- For services, list every revision with traffic above 0% or a tag. For GKE, use the
  running pods' image IDs (scaled-to-zero deployments still count), plus pods that no
  Deployment, StatefulSet, DaemonSet or Job owns.
- Map each digest to a source commit through the registry tag of that exact digest.
  Promoted images (pusher) carry only `promotion-<digest>` in production; trace them
  through the development registry's SHA tag. Some development images are OCI indexes;
  the serving digest is the `linux/amd64` manifest inside the tagged index.
- Read the cluster with a private `KUBECONFIG` per identity. The shared `~/.kube` GKE
  token cache can serve another agent's identity.
- Any production train changes the fleet. Rescan, get a delta review, and run a
  drift check before every batch.
- Pass the real path of `fleet.json` to `--fleet-receipt`. Artifact paths resolve
  relative to its directory, so a symlink fails the gate.

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
Owners with 10,000 or more matches are supported: metadata fetch paginates their
records, then fresh complement queries prove no unknown identities remain and
bounded payload queries verify every known identity group. The query result cap
alone is not a reason to exclude an owner. The operator still rejects inventories
it cannot prove complete, including mixed identity schemas, unknown identities,
or stale replicas; record and resolve those failures before calling the rollout
complete. See `test_large_owner_qualifies_complete_inventory_and_every_payload_group`
in `backend/tests/unit/test_pinecone_partition_migration.py` for the 10,001-record
qualification case.

After the first full rollout and actual user-path/health verification, schedule a
monitored bounded sweep for later registered legacy owners. **Do not install that
schedule before the rollout owner verifies the release.** Each run needs current
reviewed fleet evidence, a single execution lock, private durable journals,
alerts on nonzero exit/blocked routes, and an owner for recovery. Monitor error
rates, search parity, provider units and bill changes; a migration count alone
does not prove savings.

### Cost and throughput (measured 2026-11-02)

- Query read units follow the scanned namespace's size, not the number of matches:
  a filtered top-1 query cost 69 RU on legacy `ns1`, 76 on `ns2` and 38 on `ns4`,
  but 1 RU on an owner's bucket. That drop is the saving. Measure it per family with
  one synthetic query after the first batch.
- Copy cost is mostly the source payload proof, one legacy-namespace query per proof
  group. The operator packs groups by response size, up to 100 records.
- The provider reports 0 write units for upserts. Estimate about 1 WU per KB of
  record (about 13 WU per 3072-d vector) and count it against the budget.
- One process moves about 4-10 records/s, plus about 13 s per family even when it
  is empty. A 19k-record family took about 55 minutes. Run several processes on
  disjoint owners, keeping the same output directory, rather than larger batches.
- Owners with unsettled serving operations report `blocked_unsettled_operations`.
  Skip them and leave the operations untouched until they are reconciled.

### Out-of-band legacy writers

Current code writes an owner's vectors only to the authoritative route, and its
deletes remove both copies. So after cutover, an owner's ID count in the legacy
namespace can stay flat or fall, never rise. Record that count right after each
batch (ID listing by the owner's ID prefix, 1 RU per 100 IDs) and re-count before
the next. Any increase means a pre-partition process, such as an old checkout's
script, wrote the legacy copy. Stop and resync that owner from its bucket. The
count cannot see an old-code update to an existing ID, so it detects inserts only.

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

**Never kill an operator process.** A kill that lands between a copy write's
admission and its settlement leaves a pending marker that blocks that owner until
it is reconciled. To stop a run, create the `--stop-file` path. The operator then
stops at its next provider read or before its next write admission, never inside
a write, exactly like a budget stop: the route stays `copying` under the owned
token with nothing pending, and the same output directory resumes with `--resume`.
A driver bounded by a session or job time limit should create the stop file
before that limit.

To show that another operator has stopped, use the newest `copy_*` operation's
creation time under the copying routes' `operations` subcollection. Route
`update_time` keeps moving, because serving writes to a copying owner also update
the route.

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
