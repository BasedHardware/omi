# Parallel seal stock drain with fresh priority

The repair CronJob is the sole retained-audio proof path. Keep the continuous
`record-seal-worker` runtime disabled. Source/chart defaults remain one repair
shard; the production overlay selects five Indexed Job pods, eight isolated row
processes each. Set only `recordSealRepair.shards=1` to return to one pod.

Each pod takes `int(canonical_record_job_id, 16) % shards`. Job, urgent,
conversation and fresh discovery all use this same ownership predicate before
proof or audio reads. Frontiers are encrypted and independent for each lane,
shard count and index; changing shard count restarts a finite pass, not custody.
A maintenance lease suppresses duplicate pods for the same Indexed Job index:
1800s exceeds the Job's hard 1680s ceiling, and normal release follows child
reaping. An interrupted owner can delay that partition for at most 30 minutes.
Plan mode never writes this lease or a frontier.

The original urgent/ordinary allocation and checkpointed first worker group are
preserved in every shard. In parallel mode conversation discovery selects that
guaranteed initial group, then ordinary stock refills by enqueue time descending,
128 metadata rows/page, at most 1024 examined metadata rows/refill. The 1024
candidate **per-run** cap is removed; the 1500s run deadline remains. One shard
retains the original static conversation sweep, followed by refill if it finishes.
A frozen per-pass horizon reaches the tail; refusals are revisited on a later run.
Only shard zero performs custody maintenance and projection rebuild.

Each shard retains the fresh lane: age 60s–2h, newest first, polling every 15s,
maximum four of eight slots after the initial checkpointed group, 120s retry
spacing. Empty slots return to stock. Fresh attempts and ordinary loans are
bounded to 90s; protected initial pending-job attempts keep 270s. Privacy,
producer-token, retained-tail, partial, admission and provider-funding proofs
are unchanged. A proven seal wakes only a due job or an exactly certified retry,
using the current transaction snapshot; active claims and unmarked future clocks
remain untouched. Fresh wakes use available_at=0; older certified stock uses 1.

Native record admission classifies by the canonical barrier's `finished_at`:
FRESH through 600s, RECENT through seven days, DEEP thereafter. Invalid/unknown
end clocks use RECENT, and existing lower priority is never promoted. Both full
captures and partial pages share this intake function. This writes the existing
priority field before enqueue; it needs the Cloud Run/listen release, not a GPU
worker image roll. The existing scheduler checks FRESH before RECENT/DEEP,
including for the same owner. Already admitted units are not reclassified.
The stored `fresh_capture` merge cohort and its independent supervision/count
timer from #25292 retain their capture-age semantics. The ordering test also
checks that bulk admission does not label old captures fresh in that cohort.
`RECORD_INTAKE_AGE_PRIORITY_ENABLED=false` restores old classification for new
admissions; keep it on while bulk drain runs. It is bound on all five main.py
hosts in dev/prod overlays, the generated runtime manifest, listen charts,
classification and the explained pusher/listen difference. Sharding is expressed
as CronJob arguments plus a downward-API index file, not new serving env flags.

## Placement and estimates

2026-11-15 00:27Z ro-prod inventory: eight occupied GPU nodes each have only
1.302 requested CPU / 2.543 GiB free; a 4 GiB repair pod cannot fit. Production
repair therefore selects the existing untainted CPU-only api-pool, autoscaling
0–20 n2-standard-4 nodes, with hard repair-pod hostname anti-affinity. Each pod
requests 3 CPU / 4 GiB, limits 4 CPU / 8 GiB, and requests no GPU. Five pods need
five CPU nodes (15 requested CPU / 20 GiB); actual autoscale and image startup
must be verified by the release owner. Do not use the GPU nodes' spare CPU.

At 00:35Z the last hour counted 1658 sealed, 15 upload-failed-cleared, 78
partial-finished, 7 privacy-refused, 18 budget-exhausted; no upload-pending.
Seals/clears were 1673/1776 attempts (94.2%); sealed mean was 12.74s. Stock at
00:41Z was 31,319 record_pending, with 1108 ready / 219 leased. A sizing estimate
of 8–10k seals/h gives 2.7–3.6h for a hypothetical 27–29k sealable subset. The
actual remaining sealable share is unknown: partial/privacy rows must stay
unsealed. This estimate includes no guarantee of GPU completion or notes.

The synthetic canonical privacy walk now uses **20 document reads** per
uncontended successful repair: the prior16 plus one committed-source revision
read and three deletion/source/ledger fence reads. The same shared post-seal
hook as the pusher runs after repair commits, fails open, and counts admission
only when record_admitted_at was first stamped in the real seal transaction.
The committed revision lets a proven repair supersede an earlier failed ledger
stage without treating an old admission as a new one. A reopened producer map
before the observation causes the closed-source observation to be skipped.

At10k seals/h, canonical reads are200k/h; fresh scans<=307200/h, initial scans
<=120000/h and one31319-row stock pass/shard/25min approximately376k/h. Nominal
sizing is about1.00M reads/h ($0.51/h at$0.51/million), approximately100reads/seal.
The conservative4M reads/h planning envelope remains$2.04/h (400reads/seal);
it is an estimate allowing retry/fence overhead, not a billing hard cap.
Canonical repair writes one conversation and, when claim-safe, one intake wake,
plus at most one ledger write:20–30k document writes/h at10k seals/h. The given
read price does not price writes. Normal admission, GCS, CPU nodes, index-entry
reads and vendor spend are separate; actual billing is unverified.

At 00:39Z the fleet completed about 588 audio-hours/hour. At the supplied ~20%
utilization, linear extrapolation is ~2940 audioh/h total, ~2350 spare, unverified.
Historical ~0.38 capture-span hours/record gives ~3800 span-hours/h at 10k rows/h;
this is an audio-demand proxy, not measured uploaded audio. RECENT/DEEP ready
can grow. Fresh stays in the existing higher class, subject to the unchanged
non-preemptible flight already running; observe fresh ready and wait metrics.

## Target-only prepare, server validation, apply and readback

Release Cloud Run/listen intake priority first; verify old native captures use
RECENT/DEEP. Smoke the approved CPU image repair entrypoint. The release owner
must set REPAIR_REPOSITORY/REPAIR_DIGEST to that approved immutable CPU artifact,
GPU_REPOSITORY/GPU_DIGEST to the current GPU pins (render input only), and
BEFORE_REPAIR_IMAGE to the independently approved current repair image. This
lane does not execute dry-run or writes; those commands belong to the release
owner's authorized operator tier. No full-chart Helm upgrade/apply is allowed.

The tool is offline. It rejects incompatible selectors, entrypoints, resource
budgets, existing index/failure policies and gates. It preserves every policy
map, cohort, secret ref and unrelated field. An absent fresh switch is added;
a present true switch is retained; an explicit false kill switch blocks this
expansion. Workers stay8. Prepare saves a mode0600 receipt containing the full
before/after specs, hashes, complete approved delta, and original image. It also
saves a private inverse template BEFORE apply; no reviewed field is omitted.
The partition volume explicitly includes Kubernetes v1.35 defaults
`downwardAPI.defaultMode: 420` and `fieldRef.apiVersion: v1` in both the chart
and the expected receipt. Rendered input may omit these defaults; conflicting
values are rejected. Existing container and PodSpec defaults come from the live
pre-read. New affinity, literal env, mounts and explicit Indexed failure fields
introduce no other defaults in the v1.35 CronJob defaulter. Job-only defaults
apply later to created Jobs, not this CronJob receipt.

```sh
set -e
umask 077
TASK_DIR=$(mktemp -d /Volumes/Ephemeral/scratch/seal-drain.XXXXXX)
CHART=backend/charts/batch-pipeline-worker
REPAIR_TOOL=backend/deploy/record-seal-repair/render_stock_drain_patch.py
REPAIR_PY=backend/.venv/bin/python
# Pre-read and record the pre-change fresh-ready age/count baseline.
kubectl -n prod-omi-backend get cronjob record-seal-repair -o json > "$TASK_DIR/before.json"
helm template prod-omi-batch-pipeline-worker "$CHART" -n prod-omi-backend \
  -f "$CHART/prod_omi_batch-pipeline-worker_values.yaml" \
  --set-string image.repository="$GPU_REPOSITORY" --set-string image.digest="$GPU_DIGEST" \
  --set-string recordSealRepair.imageRepository="$REPAIR_REPOSITORY" \
  --set-string recordSealRepair.imageDigest="$REPAIR_DIGEST" \
  --set recordSealRepair.shards=5 --show-only templates/record-seal-repair.yaml > "$TASK_DIR/rendered.yaml"
"$REPAIR_PY" "$REPAIR_TOOL" prepare --live-json "$TASK_DIR/before.json" \
  --rendered-yaml "$TASK_DIR/rendered.yaml" --expected-image "$BEFORE_REPAIR_IMAGE" --out "$TASK_DIR"
# Review approvedDelta privately; never print or commit policy/cohort packets.
kubectl -n prod-omi-backend patch cronjob record-seal-repair --type=json \
  --patch-file "$TASK_DIR/forward.json" --dry-run=server -o json > "$TASK_DIR/dry-run.json"
"$REPAIR_PY" "$REPAIR_TOOL" check-object --receipt "$TASK_DIR/receipt.json" \
  --object "$TASK_DIR/dry-run.json" --state after
# Generate the private inverse before applying. This binding is a dry-run RV;
# refresh it from a fresh readback before any real rollback.
"$REPAIR_PY" "$REPAIR_TOOL" rollback --receipt "$TASK_DIR/receipt.json" \
  --object "$TASK_DIR/dry-run.json" --output "$TASK_DIR/rollback.pending.json"
# Only after all commands above pass, apply the reviewed forward packet.
kubectl -n prod-omi-backend patch cronjob record-seal-repair --type=json \
  --patch-file "$TASK_DIR/forward.json" -o json > "$TASK_DIR/applied.json"
kubectl -n prod-omi-backend get cronjob record-seal-repair -o json > "$TASK_DIR/readback.json"
"$REPAIR_PY" "$REPAIR_TOOL" verify --receipt "$TASK_DIR/receipt.json" \
  --object "$TASK_DIR/readback.json" --state after
```

Every command is gated on the preceding command succeeding. Run with shell
`set -e` or stop at the first failure. A server-dry-run/defaulting difference,
object replacement, resourceVersion race, receipt mutation or unapproved spec
change is a HOLD: re-read and review a new packet; never weaken its checks.
The first real server dry-run belongs to the release owner and has not been
verified by this lane. If it reports any delta, STOP and send the diff back for
review; never hand-edit the receipt to make it pass.
Checks compare the entire spec, so every changed field and every unchanged
policy field must match. The tool never calls Kubernetes and never writes an
account or recording. No GPU Deployment, worker runtime, RBAC or monitoring
resource is applied.

## Full footprint rollback

Set shards=1 only to reduce future capacity; it is NOT a footprint rollback.
The inverse below restores the exact original image, schedule, resources,
placement, tolerations, index mode/fields, args, env, mounts and volumes. It is
UID/resourceVersion/spec guarded and emits only after the current after-spec
matches the approved receipt. Active Jobs finish under Forbid within1680s;
this CronJob rollback does not immediately terminate them.

```sh
kubectl -n prod-omi-backend get cronjob record-seal-repair -o json > "$TASK_DIR/current.json"
"$REPAIR_PY" "$REPAIR_TOOL" rollback --receipt "$TASK_DIR/receipt.json" \
  --object "$TASK_DIR/current.json" --output "$TASK_DIR/rollback.json"
kubectl -n prod-omi-backend patch cronjob record-seal-repair --type=json \
  --patch-file "$TASK_DIR/rollback.json" --dry-run=server -o json > "$TASK_DIR/rollback-dry-run.json"
"$REPAIR_PY" "$REPAIR_TOOL" check-object --receipt "$TASK_DIR/receipt.json" \
  --object "$TASK_DIR/rollback-dry-run.json" --state before
kubectl -n prod-omi-backend patch cronjob record-seal-repair --type=json \
  --patch-file "$TASK_DIR/rollback.json" -o json > "$TASK_DIR/rolled-back.json"
kubectl -n prod-omi-backend get cronjob record-seal-repair -o json > "$TASK_DIR/rollback-readback.json"
"$REPAIR_PY" "$REPAIR_TOOL" verify --receipt "$TASK_DIR/receipt.json" \
  --object "$TASK_DIR/rollback-readback.json" --state before
```

Keep intake age priority enabled during a repair rollback. The packet preserves
policy; refreshing RECORD_SEAL_REPAIR_SERVER_FLAGS is a separate operation and
is not implemented by this stock-drain tool.

## Complete approved production delta

The before object must match the measured single-pod shape (or its first-shipment
image/minute-cadence/fresh=true update). The private receipt records every actual
changed path and its before/after values, not just this descriptive inventory:

- Schedule: */5 or already every minute -> every minute.
- completionMode: absent/NonIndexed or single Indexed -> Indexed;
  completions/parallelism absent or1 ->5.
- Global backoffLimit0 ->5; add backoffLimitPerIndex0 and maxFailedIndexes5.
  Thus a failed index cannot abort its four healthy siblings. ro-prod server
  v1.35.8-gke.1796000 exposes both fields (kubectl explain verified2026-11-15).
- Node-affinity pool batch-pipeline-pool -> api-pool; add required hostname
  anti-affinity matching repair pods; remove the two batch/GPU tolerations.
- Image: independently approved original pin -> smoke-verified CPU repair pin.
- CPU request4 ->3; limit4 unchanged; memory request4Gi/limit8Gi unchanged.
- Command unchanged; add args --shards5 --shard-index-file/etc/repair-partition/index.
- Workers stay8. Fresh env absent ->true, or already true ->unchanged.
  All other env, policy maps, cohorts and secret refs remain byte-identical.
- Add partition downward-API volume and read-only /etc/repair-partition mount.
  The tmp volume/mount, KSA, labels, security and all unrelated fields remain.
- Hard Job deadline1680 and Forbid remain unchanged. No Deployment is patched.

Do not apply if the dry-run changes anything beyond the receipt's exact delta.

## First ten minutes watch

Start this clock at creation of the first Indexed Job, not at patch time. Save
fresh-ready age/count before the patch, then sample at least once per minute.
The release owner holds further expansion and prepares the exact inverse on:

1. At+5min, fewer than five Running indexes on five distinct api-pool nodes,
   with persistent FailedScheduling, ImagePullBackOff or absent node scale-up.
2. Any coordinator OOMKilled, failed pod, BackoffLimitExceeded or DeadlineExceeded.
3. Fresh-ready age above300s on two consecutive samples, above its pre-change
   baseline, with fresh-ready count growing.

Also watch overlap_refused, missing/failed indexes and effective4/5 throughput;
record per-index dispositions and CPU usage. A green CronJob/Job status is not
evidence that every shard repaired work: overlap_refused exits0, so watch each
index's outcomes. A CronJob inverse controls future
Jobs; immediate termination of running Jobs is a separate release-owner action,
not part of this tool. Verify the unchanged GPU Deployment identities and the
new repair image identity, and retain the private before/after packet.

## Deadline and lease limits

The process records a monotonic clock before dependency imports. Its outer
IO budget ends by1560s after that clock, and earlier when necessary to leave60s
before scheduled-minute+1680s. The standard CronJob minute in the hostname
includes cold-node scheduling/image-pull waits. Accepted forms are the Indexed
hostname `record-seal-repair-<minute>-<index>`, the ordinary hostname
`record-seal-repair-<minute>-<random>`, and an Indexed pod's metadata name with
both index and random suffix. The existing downward API mounts only the index;
it does not expose the Job's scheduled timestamp. Unknown in-cluster identity
fails closed. Nested IO budgets cannot extend the outer deadline. Coordination
is shortened after projection/discovery/maintenance to reserve30s for final
checkpoint/reaping; the hard Kubernetes1680s ceiling is unchanged.

Projection rebuild now runs AFTER the per-index coordinator lease is acquired,
so a duplicate shard-zero pod does not rebuild before refusing overlap.
The1800s lease remains longer than the hard deadline. We deliberately do not
let a new Job identity steal an unexpired lease: a new name alone is not proof
that the prior pod/children are dead. A killed owner can therefore leave one
index idle for up to30min, yielding4/5 capacity until expiry; watch overlap and
missing indexes. The expiry protocol assumes synchronized node clocks; clock
skew above the120s lease/deadline margin can undermine exclusion. Immediate
safe takeover requires a server-fenced owner-death proof and is future work.
No privacy or producer-token proof is supplied by this maintenance lease.
