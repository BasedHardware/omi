# Recover implausible future-clock sync uploads

V2 admits well-formed capture stamps strictly more than 24 hours ahead of the
server receive clock with `SYNC_FUTURE_CAPTURE_CLAMP_ENABLED` on in code.
Dev and prod explicitly bind it **false** for the first roll. This margin is
144 times the normal 600-second skew allowance. That allowance is unchanged;
stamps between it and 24 hours still return HTTP 400 `invalid_capture_time`.
V1 keeps rejecting future clocks. The existing unconditional upload normalizer moves collision suffixes
(`_<timestamp>_uN.bin`) ahead of the timestamp before admission and hashing.
Future recovery preserves main's canonical name and ledger/content identity;
no new collision parser or switch is needed.

## Chronology and retained identity

The original early-clock helper packed each request's durations in raw source
order, ending at that request's frozen receive time. It had the same
cross-request reversal/overlap defect as the initial future-clock extension:
newest-first backlog requests were placed in request arrival order.

New identified-device admissions persist `capture_clock_policy=device_offset_v1`
in intake/Cloud Tasks context. Both early and future recovery share one affine
offset, transactionally created under
`users/{uid}/sync_assignment/capture-clock-<scope hash>`. The scope includes the
client device, explicit filename clock-run nonce (if present), and early/future
clock kind; owner isolation comes from the document path. An unmarked legacy
clock is one run per device and clock kind: an unmarked reset cannot be inferred
from out-of-order delivery. Explicit run tokens are read independently of the
clock-run partition switch, so toggling that switch cannot change placement.

The first successfully decoded request freezes
`offset = max(original start + decoded duration) - receive time` for each run.
Every stored span uses `raw start - offset`. This anchors the first decoded
batch's end on trusted receipt, preserves device-clock differences and gaps
across requests, and preserves nonoverlap of the device's source intervals in
any arrival order. VAD/coverage derivatives inherit the original file's scope
and offset; a trim cannot choose a new anchor. The anchor has no TTL and later
requests never rewrite it. A mapped span ahead of trusted server processing
time, or before epoch zero, waits with audio retained (`capture_clock_anchor_pending`), rather
than re-clamping or sliding earlier intervals. A discontinuous clock needs a
new explicit run nonce. Processing time may release an interval when due; it
never changes its offset, including on a retry with the original frozen receipt.
Offset storage failure likewise fails closed.

Future uploads without a stable client device return retryable 503
`capture_clock_identity_required`; an account-wide default would mix devices.
Early uploads without that identity, and already admitted contexts without the
new policy, retain their existing request-frozen behavior. Existing batch units
and cap-held units keep their already frozen stored capture times. The shared
fix applies to new identified early-clock admissions once the future switch is
enabled; phase one leaves this new policy off for both clock kinds.

Original files, filename timestamps, content identities, source-frame maps,
lineage proofs and custody checks remain intact. Receipt placement is an
untrusted ordering coordinate, never recovered absolute capture time. Normal
siblings retain their existing clock policy and historical lookback limits.
Untrusted spans use backfill pacing and omit client wall-clock lookup bounds.
`capture_time_trust=untrusted` remains on WorkItems and recovered conversations.
Temporal assignment/overlap cannot connect distinct identities when either
clock is untrusted. Explicit targets, committed source-frame ownership and
exact retry identity retain their independent checks. Energy/time coverage
skips recovered inputs; frame coverage may skip only positively proven
same-source samples. No receipt coordinate proves that other phone audio is
covered. Ordinary skewed suffixed filenames keep their existing behavior.

## Two-phase rollout and exact enablement

Phase one ships this code in any order with literal `'false'` bindings at all
five admission-capable scopes in **each** dev/prod overlay:

- `backend/deploy/runtime_env/dev.overlay.yaml` and `prod.overlay.yaml`:
  `overlay.gke.backend-listen.env.SYNC_FUTURE_CAPTURE_CLAMP_ENABLED.value`;
  `overlay.cloud_run.services.<service>.env.SYNC_FUTURE_CAPTURE_CLAMP_ENABLED.value`
  for `backend`, `backend-sync`, `backend-sync-backfill`, `backend-integration`.
- `backend/charts/backend-listen/dev_omi_backend_listen_values.yaml` and
  `prod_omi_backend_listen_values.yaml`: the `env` entry named
  `SYNC_FUTURE_CAPTURE_CLAMP_ENABLED`, `value: 'false'`.
- `backend/deploy/runtime_env.yaml` is generated from those overlays. Run
  `backend/.venv/bin/python backend/deploy/compose_runtime_env.py` after editing.

Before enabling, the release owner must record a serving release vector, not
just the new service spec or a ready candidate. From the release checkout,
using the approved read-only agent tier and the exact phase-one deploy receipt:

```bash
source ~/.local/bin/gcp-agent-env.sh ro-prod
backend/.venv/bin/python backend/scripts/verify_backend_release_vector.py \
  --environment prod --project based-hardware --region us-central1 \
  --commit-sha "$PHASE_ONE_SHA" --short-sha "$PHASE_ONE_SHORT_SHA" \
  --deploy-run-id "$PHASE_ONE_RUN_ID" --deploy-run-attempt "$PHASE_ONE_ATTEMPT" \
  --expected-image "$PHASE_ONE_IMAGE_DIGEST" \
  --latest-ready-wait-seconds 0 --evidence-path "$READBACK_DIR/release-vector.json"
backend/.venv/bin/python backend/scripts/validate-backend-runtime-env.py \
  --env prod --check-live-cloud-run
kubectl get deployments,cronjobs,jobs,pods -A -o json > "$READBACK_DIR/kubernetes-readers.json"
```

Supply repeated `--service-image SERVICE=...@sha256:...` if the receipt uses
role images. Run the corresponding dev readback with its project/environment
and prescribed read-only tier. The verifier checks 100% revision-pinned traffic
for all four Cloud Run services and converged listener endpoints. Also inspect
the traffic-target revision documents: each must have the phase-one source SHA
(or a build-proven digest from that source) and the explicit false binding.
Resolve task OIDC/handler URLs to these exact serving revisions: sync tasks,
provider-STT, projection/follow-up, quarantine recovery, and delayed/redrive
handlers must not point to old tagged revisions or separate old workers.

The Kubernetes inventory must cover every running batch scheduler/pump,
projection/recovery controller, optional sync-backfill pilot, and active Jobs,
including old pods still terminating and CronJob templates for future runs.
Compare each running container `imageID` and future template digest with the
source-proven release receipt containing the new WorkItem field and recovery
readers. A tag, chart release name (`BATCH_PIPELINE_WORKER_RELEASE`), or source
label by itself is insufficient. Operator redrive tools must run from the same
new checkout. Any unaccounted or older reader means **keep admissions false**.
The following is the source-declared reader/image matrix (`runtime_images.json`,
Dockerfiles and chart values), **not a measurement of serving images**. In the
current deployment declarations, dev uses project `based-hardware-dev` and prod
uses `based-hardware`:

| Process / deployment | Reads and trust-sensitive behavior | Current image repository; role-image alternative |
| --- | --- | --- |
| `uvicorn main:app` on Cloud Run `backend`, `backend-sync`, `backend-sync-backfill`, `backend-integration` | `Serving` projection pump, worker RPC, `Projector`, context/prefetch/follow-up, provider STT/quarantine/shadow recovery, restored-upload and speech-redrive readers; router mounting and switches determine active paths. `context.py` and `projection.py` explicitly inspect the marker before nearest/overlap conversation lookup and persist it. | `gcr.io/<project>/backend`; role split declares `backend-api` for `backend`, `backend-workers` for the other three. Read the actual traffic revision digest. |
| `uvicorn main:app` on GKE `backend-listen` | Same startup/serving code and admission/inline sync pipeline where mounted/enabled. | `gcr.io/<project>/backend`; role alternative `backend-realtime`. |
| Optional GKE `utils.sync.worker_runtime:app` children `python -m utils.sync.worker_job` | Persisted sync policy/trust payload into legacy pipeline, assignment/index/overlap/coverage. No `Projector` in this process. Pilot declaration is not evidence it is installed. | `backend-sync-backfill-worker`, digest supplied by the role-image train; actual repository comes from the installed chart. |
| GPU `python -m diarizer.batch_pipeline_runtime` and its child processes | `Scheduler.pull` deserializes `WorkItem`; `Pump`/GPU compute consumes it. This runtime supplies neither a projector nor `project_pending`. It does not inspect `capture_time_trust` for a conversation decision. `Scheduler.complete` and `OrderedMerge` update the original full job map, preserving unknown fields; the CPU projector re-reads that job. An old dataclass can omit the marker in memory. | `gcr.io/<project>/batch-pipeline-worker`, `backend/diarizer/Dockerfile.batch-pipeline`. **Unchanged by this lane.** |
| `scripts/record_seal_{sweep,repair_job,worker}.py` CronJobs/Deployment | Record repair/intake controllers share the GPU image, rather than a separate backend image; inventory their templates and any active Jobs too. They do not run the trust-sensitive projector. | Same `batch-pipeline-worker` repository and chart `image.digest`. |
| Operator `batch_pipeline_{artifact_missing,held_disposition,terminal_empty,speech_redrive}.py` and `recover_dev_failed_sync_backfill.py` | Reconstruct WorkItems or replay trust/policy contexts. Database voice-evidence/final-pass and shadow readers also deserialize WorkItems inside their invoking CPU process. | Local approved checkout/interpreter, or the explicitly selected operator container digest. No fixed deployed image is implied. |

The GPU scheduler is a reader, so it must be included in the release inventory.
Its raw-job-preserving write path explains why its transient WorkItem is not the
old-projector binding hazard. It does **not** prove compatibility of an unknown
deployed GPU digest. The strict second-roll gate remains a verified new-reader
image across the inventory; accepting an older GPU image requires a separate,
exact-digest compatibility proof and lead ruling. This lane neither changes the
GPU image nor grants that exception. If that gate requires a GPU upgrade, the
standing brief requires separate authorization before enabling admissions.
These live readbacks have not been executed by this implementation lane.

Phase two is a separate config-only commit: change exactly those ten overlay
values and two chart entries from `'false'` to `'true'`, regenerate
`backend/deploy/runtime_env.yaml`, and update the staged registry note with the
readback evidence. Run `backend/scripts/pre-deploy-check.sh` through `omi-heavy`,
then use the normal authorized deployment path. Repeat the serving revision/env
readback and require true on all intended admission scopes. The registry's
staged-off test intentionally changes to true with this enablement commit.
Observe `omi_sync_capture_time_total{outcome="accepted_future_clamped"}` and the
content-free `event=sync_capture_time` log, with no time-only bindings/coverage.

There is no new-reader-only claim fence in this change. Old WorkItem readers
silently omit unknown fields; adding another job field does not stop their
claims. A reliable fence needs a versioned queue/claim protocol and changes to
all claimers, so it is not a cheap safe addition to this patch.

Rollback new admissions by restoring these same bindings to false. Persisted
policy contexts, anchors, trust markers, tasks and holds continue independently
of the switch and current worker time. Never roll processors back to readers
that discard the trust marker while admitted work remains. Client retries
retain their existing schedule; no immediate phone resend is claimed.

Contract: [sync admission](../../listen_pusher_pipeline.mdx).
