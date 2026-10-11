# C025 — regionalize temporal sync storage

Last reviewed: 2026-10-12

Operator procedure only: merging this document does not provision buckets or
change serving configuration. Target: Standard, flat-namespace storage in
`us-central1`. Keep the current chart names until provisioning is verified.
Do not change `omi-private-cloud-sync`.

## Evidence and blast radius

Cost-ledger card **C025** reports production `syncing-local` as multi-region,
with the "Network Data Transfer GCP Replication within Northern America" line
up $46/day week over week. Live metadata was not inspected for this change.
Verify both production and development before executing; if development
`syncing-local-development` is already regional, do not recreate it needlessly.
There are no application storage-bucket resources in `infrastructure/`;
`infrastructure/opentofu/README.md` limits that foundation's storage ownership
to state metadata. This runbook owns the temporal bucket location/lifecycle.

`utils/other/storage.py` uploads WAV segments and returns V4 GET signed URLs
with a 15-minute expiry. `utils/sync/pipeline.py:process_segment` schedules
segment deletion after 480 seconds, calls prerecorded transcription (including
Deepgram), and fetches the same URL for speaker identification and optional
private-cloud processing. Signatures, checksums and endpoints have no
multi-region requirement; internet readers can fetch a regional signed URL.
The daemon janitor's in-memory schedule can be lost on restart; the GCS-side
one-day Delete lifecycle is the backstop, not a strict deletion deadline.

**Not all staged objects live eight minutes.** `routers/sync.py` also stages raw
`.bin` files before dispatching fresh/backfill jobs. Payloads contain
`raw_blob_paths`, not a bucket name. Workers resolve those paths against their
current environment and delete them on completion. Delayed/retry jobs can need
these blobs until the one-day lifecycle removes them; missing blobs finalize
with `sync_staged_audio_expired`. A rolling bucket flip without draining or
copying this material can break accepted jobs. No cross-region recovery
contract was found, but staging availability is still required during a job;
regionalization accepts correlated downtime with the us-central1 serving tier.
It does not promise that every client can recover every lost staging object.

## Provision and verify (operator shell; not executed by this PR)

Use the appropriate `gcp-agent-env.sh` read/operator tier for inspection and
provisioning; bucket IAM changes require the human tier. Record old location,
project, lifecycle, access policy, encryption, retention/holds, versioning and
soft-delete policy. Preserve required runtime/signer access, including any
project-level or conditional IAM grants; do not copy legacy bucket-owner
bindings blindly. Signed URLs require signer object-read access, while workers
need upload/read/delete access. Never make this audio public.

Run once per environment, dev first (confirm the owning project rather than
assuming the compute project is also the storage project). Proposed new names
must be globally available; if occupied, pick a unique name and use it in all
subsequent configuration. The commands create an empty replacement, not an
in-place location update. See [create](https://docs.cloud.google.com/sdk/gcloud/reference/storage/buckets/create)
and [update](https://docs.cloud.google.com/sdk/gcloud/reference/storage/buckets/update).

```bash
set -euo pipefail
# Production; for dev use syncing-local-development and
# syncing-local-development-us-central1 instead.
C025_OLD=syncing-local
C025_NEW=syncing-local-us-central1
C025_PROJECT=REPLACE_WITH_VERIFIED_STORAGE_PROJECT
C025_DIR=$(mktemp -d)
chmod 700 "$C025_DIR"
gcloud storage buckets describe "gs://${C025_OLD}" --format=json > "$C025_DIR/old.json"
gcloud storage buckets get-iam-policy "gs://${C025_OLD}" --format=json > "$C025_DIR/old-iam.json"
cat > "$C025_DIR/lifecycle.json" <<'JSON'
{"rule":[{"action":{"type":"Delete"},"condition":{"age":1}}]}
JSON
gcloud storage buckets create "gs://${C025_NEW}" \
  --project="$C025_PROJECT" --location=us-central1 \
  --default-storage-class=STANDARD --uniform-bucket-level-access \
  --public-access-prevention --soft-delete-duration=0
# Dedicated disposable staging: no versioning or retained deleted copies.
gcloud storage buckets update "gs://${C025_NEW}" \
  --lifecycle-file="$C025_DIR/lifecycle.json" --no-versioning
# Operator prepares new-iam.json from reviewed old/project bindings;
# retain required principals/roles and adjust bucket-name conditions.
gcloud storage buckets set-iam-policy "gs://${C025_NEW}" "$C025_DIR/new-iam.json"
gcloud storage buckets describe "gs://${C025_NEW}" --format=json
gcloud storage buckets get-iam-policy "gs://${C025_NEW}" --format=json
```

If the source requires CMEK or additional access constraints, apply equivalent
settings before admitting uploads. Soft delete is explicitly disabled on the
new disposable bucket to avoid the creation default retaining deleted audio;
confirm this retention decision with the bucket owner. Do not alter the old
bucket's retention policy as part of provisioning. Verify `REGIONAL` /
`US-CENTRAL1`, Standard class, age-1 Delete, no versions/soft delete, and private
access. With each serving identity, smoke-test upload, V4 signed-URL fetch,
worker download and delete of a synthetic object before switching traffic.

## Deploy order and rollback

1. Create and qualify the dev replacement, then prod replacement. Leave both
   old buckets accessible for rollback. No bulk copy is needed for consumed
   eight-minute WAV segments: already issued URLs keep naming the old bucket.
2. Before a **no-copy** cutover, pause new sync intake through an operator-owned
   admission/traffic control that preserves client retry behavior; keep old
   workers running. Drain fresh/backfill Cloud Tasks, Redis per-UID sequencing,
   retries and in-flight jobs. Require no nonterminal job referencing old raw
   paths. A paused queue is not a drained queue. If no safe intake control or
   drain evidence is available, hold the cutover. An alternative migration must
   preserve pending raw objects (for example `gcloud storage rsync --recursive
   "gs://${C025_OLD}" "gs://${C025_NEW}"` with writers stopped), verify them, and
   qualify mixed-worker/account-deletion behavior separately; copying is not
   the default procedure here.
3. Wait at least 15 minutes after the last old signed URL was generated and
   ensure consumers finished. Redis signed-URL cache keys use only `blob.name`
   (`database/redis_db.py`), so reusing paths before cached URLs expire could
   return an old-bucket URL. Keep old serving processes alive for at least
   480 seconds after their last segment schedule if relying on their janitor.
4. Change `BUCKET_TEMPORAL_SYNC_LOCAL` in **both** prod charts:
   `backend/charts/backend-listen/prod_omi_backend_listen_values.yaml` and
   `backend/charts/pusher/prod_omi_pusher_values.yaml` to
   `syncing-local-us-central1`. For dev, change both corresponding `dev_` files
   to `syncing-local-development-us-central1` after dev provisioning.
   Inventory Cloud Run `backend`, `backend-sync`, `backend-sync-backfill` and
   other hosts importing storage: this variable is absent from the checked-in
   runtime-env manifest, so their live/inherited configuration is not proven
   by changing Helm. Declare the new literal in each applicable service's env
   in `backend/deploy/runtime_env/{prod,dev}.overlay.yaml`, compose with
   `python3 backend/deploy/compose_runtime_env.py`, and review rendered values.
   Backfill deployment clones backend-sync's runtime; verify it explicitly.
5. With intake still paused and old jobs drained, deploy all producers/workers
   through the normal GitHub release workflows, verifying the effective env
   on every serving revision/pod before resuming intake. Run a synthetic fresh
   sync and backfill sync, signed fetch and speaker-ID check; confirm cleanup
   and no new permission/404/`sync_staged_audio_expired` failures. This is a
   coordinated change, not an independent two-chart rolling flip.
6. Old segment blobs drain via surviving 480-second janitors; restart leftovers
   and unused raw blobs drain via the one-day lifecycle. Account-deletion
   cleanup resolves only the currently configured temporal bucket: ensure old
   processes/URLs are drained and the old bucket expires leftovers; do not
   preserve old raw data beyond the existing lifecycle for migration.
7. After **at least 48 hours since the final old write**, verify no old writers,
   references or rollback need, and that the bucket has no live/noncurrent
   objects. Lifecycle is asynchronous: postpone deletion if not empty. Check
   soft-deleted objects/holds too; do not force recursive deletion. Only then:

   ```bash
   gcloud storage buckets delete "gs://${C025_OLD}"
   ```

Rollback before deletion: pause intake, drain jobs using the new bucket, wait
out its 15-minute URL cache, flip the same charts and all Cloud Run env values
back to the old name, redeploy/verify, then resume. Retain the new bucket until
its consumers/jobs have drained too. Simply flipping back while queued new
raw paths still exist is unsafe. After deleting the old bucket, this rollback
path is no longer available.

## Cost qualification

C025's current-volume estimate is **$40–60/day** (~$1,200–1,800 per 30 days),
not measured post-change savings. The $46/day WoW replication increase is a
ledger observation, not the full replication baseline. For Standard flat
namespace, [published pricing](https://cloud.google.com/storage/pricing) gives
US replication $0.02/GiB written, Class A $0.010 → $0.005 per 1,000 operations,
and Class B $0.0004 → $0.0004 (no Class B saving). Thus daily gross savings:

```text
0.02 * replicated_GiB_per_day
+ 0.005 * Class_A_operations_per_day / 1000
+ 0 * Class_B_operations_per_day / 1000
```

For illustration only, 2,000 GiB/day and 1 million Class A operations/day yield
$40 + $5 = $45/day. Internet egress remains; exclude durable sync costs and
avoid attributing a soft-delete retention change to regionalization. Compare
bucket-attributed billing before/after at matched upload volume: replication
should stop for new regional writes, Class A price should halve, and sync job
success/latency should remain stable. Dev savings depend on its verified
location and volume. `gcp_component_classifier.sql` already matches the
`syncing-local` prefix, including the proposed replacement names.
