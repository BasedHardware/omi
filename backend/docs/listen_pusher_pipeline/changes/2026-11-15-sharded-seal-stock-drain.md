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

The synthetic canonical privacy walk uses 16 document reads on an uncontended
successful seal. At 10k seals/h, canonical reads are about 160k/h before retries
and SDK fences. Five fresh scanners cost at most 307,200 metadata reads/h;
initial scans at most 120,000/h; one full 31,319-row stock scan per shard per
25m is about 376k/h. Total nominal sizing is about 0.97M/h before fence/retry
allowances. Use a conservative **4M reads/h planning envelope ($2.04/h at
$0.51/million)**, allowing up to 15x the 16-read canonical model plus metadata
and margin. This is a sizing upper estimate at the stated stock/rate, not a
hard billing cap or measured production read cost; remeasure terminal child
probe totals and retry rates after deployment. Normal traffic/admission reads,
GCS/network, CPU nodes and vendor spend are separate.

Main #25304 adds a separate, fail-open post-seal ledger transaction on
`database.record_audio.seal_record_audio`: three fenced document reads and at
most one ledger write per first admission. At 10k first admissions/h, allow
another 30k reads/h and 10k writes/h: nominal read sizing becomes about
0.99M/h ($0.51/h), still within the 4M/h planning envelope. Canonical repair
itself writes one conversation and, when claim-safe, one intake wake: 10–20k
document writes/h; including the ledger allowance gives 20–30k writes/h.
The supplied $0.51/million price is for reads only; ledger write charges are
additional and not priced here. The repair's existing direct
`apply_seals` transaction does not invoke that new pusher ledger writer, so its
ledger admission coverage remains a separate integration gap, not an asserted
effect or a dependency of this drain. Privacy/source deletion fences on the
new ledger writer are unchanged. Ledger retries are included only as a sizing
allowance; production billing is not verified.

At 00:39Z the fleet completed about 588 audio-hours/hour. At the supplied ~20%
utilization, linear extrapolation is ~2940 audioh/h total, ~2350 spare, unverified.
Historical ~0.38 capture-span hours/record gives ~3800 span-hours/h at 10k rows/h;
this is an audio-demand proxy, not measured uploaded audio. RECENT/DEEP ready
can grow. Fresh stays in the existing higher class, subject to the unchanged
non-preemptible flight already running; observe fresh ready and wait metrics.

## Target-only rollout and rollback

Use the approved second train's immutable repair-capable image. The backend CPU
image contains the repair script and ffmpeg; the release owner must smoke its
repair entrypoint. Pin it via recordSealRepair.imageRepository/imageDigest,
leaving image.repository/image.digest (the GPU artifact) unchanged. First deploy
intake priority to Cloud Run/listen and verify new old-capture units use
RECENT/DEEP. Then run these commands from the combined checkout, using a private
scratch directory and **no Helm upgrade/apply of the whole chart**:

```sh
umask 077
TASK_DIR=$(mktemp -d /Volumes/Ephemeral/scratch/seal-drain.XXXXXX)
CHART=backend/charts/batch-pipeline-worker
# REPAIR_REPOSITORY and REPAIR_DIGEST are the release owner's smoke-verified CPU image.
# GPU_REPOSITORY and GPU_DIGEST are the current pinned GPU image; render input only.
helm template prod-omi-batch-pipeline-worker "$CHART" -n prod-omi-backend \
  -f "$CHART/prod_omi_batch-pipeline-worker_values.yaml" \
  --set-string image.repository="$GPU_REPOSITORY" --set-string image.digest="$GPU_DIGEST" \
  --set-string recordSealRepair.imageRepository="$REPAIR_REPOSITORY" \
  --set-string recordSealRepair.imageDigest="$REPAIR_DIGEST" \
  --set recordSealRepair.shards=5 \
  --show-only templates/record-seal-repair.yaml > "$TASK_DIR/rendered.yaml"
kubectl -n prod-omi-backend get cronjob record-seal-repair -o json > "$TASK_DIR/live.json"
backend/.venv/bin/python backend/deploy/record-seal-repair/render_stock_drain_patch.py \
  --live-json "$TASK_DIR/live.json" --rendered-yaml "$TASK_DIR/rendered.yaml" \
  --output "$TASK_DIR/patch.json"
kubectl -n prod-omi-backend patch cronjob record-seal-repair --type=json \
  --patch-file "$TASK_DIR/patch.json"
```

The offline renderer only patches schedule/jobTemplate on this exact CronJob,
checks resourceVersion atomically and preserves live effective serving policy,
producer-lease gates, existing fresh kill setting, secret refs, KSA and other pod
fields. It changes repair image, shard count/index, placement/resources and the
per-pod worker count. Never print or commit its private input/output files.
A resourceVersion mismatch requires a fresh read/re-render; never bypass the CAS.
No GPU Deployment, continuous worker, RBAC or monitoring resource is applied.

Rollback: repeat the same render/get/patch sequence with
`--set recordSealRepair.shards=1`; keep intake age priority on. The existing Job
finishes under Forbid (at most 1680s), then future Jobs have one pod. This is not
an immediate stop of already running shards. For a complete source rollback,
use the release owner's approved prior repair digest and saved prior CronJob
shape; never restore the GPU image or alter producer/privacy proofs. After the
change, verify CronJob completion counts, all five pod indexes, CPU-only placement,
row dispositions, fresh ready/wait, intake claim refusals and serving identities.
