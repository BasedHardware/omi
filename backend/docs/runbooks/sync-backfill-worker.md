# Backfill pull workers (dark)

The owner/epoch registry chooses one execution drive. Cloud Tasks and pull
workers race the same owner transaction before either acquires the existing
Redis run lock. A pull winner has an unguessable worker token: task begin,
renewal and completion cannot mutate it. Expired workers cannot renew or
complete. Redrive advances the epoch and removes worker eligibility so the
Cloud Tasks fallback owns recovery. Redis's 1800-second token fence still
protects pipeline writes and slow executor leaves after cancellation.

`SYNC_BACKFILL_WORKER_PERCENT` defaults to `0`, and zero claims read no
persistence. Heartbeat/complete/fail remain available for accepted leases
after rollback. Claim also requires the sequencer enabled, active ledger
fencing, an explicitly worker-eligible backfill payload, and legacy dispatch
allowed for the account. Existing payloads are ineligible.

The private RPCs `/v2/sync-jobs/claim`, `/heartbeat`, `/complete`, `/fail`
use `SYNC_BACKFILL_WORKER_AUDIENCE` and
`SYNC_BACKFILL_WORKER_SERVICE_ACCOUNT`, with the existing OIDC verifier.
Completion rechecks terminal Redis state. Failure hands work to the sweep
only after the run lock is absent; uncertain cancellation retains the lock
and falls back after the unchanged silence TTL. A fail is never an audio
failure or permission to delete custody.

## Ramp and rollback

This PR ships dark. No production activation is part of it. After the idle
fleet and staging kit qualify, infracost owns expansion with lead approval:
synthetic/allowlisted accounts, then stable SHA-256 account cohorts at 5%,
25%, 50%, 100%. Soak at least 24h at 5% and 25%. Require zero lost speech,
zero `delivery/nonterminal_ack`, partial failure no worse than the flag-off
baseline (~5%), and no oldest-wait/depth regression at equal admission rate.
Measure node-hours versus displaced Cloud Run container-hours; savings are
estimates until that receipt exists. Review activation or continued darkness
by 2026-11-09; infracost reports any unexpanded flag as a blocker then.

Rollback: percent 0 closes intake; accepted workers finish under their
existing leases. Cloud Tasks enqueue and the sequencer sweep remain live.
Do not shorten either 1800s lease, mutate batch admission, or change ops pins.
Production and shared-data dev runtimes cannot be used as a staging sandbox:
the existing sequencer is production-stage only. A staging window must use
an isolated data plane and synthetic accounts before exercising this protocol.

## S2: idle fleet preparation

`backend/Dockerfile.roles --target sync-backfill-worker` shares the backend
runtime lock and source but runs only `python -m utils.sync.worker_runtime`.
It mounts health/readiness only and polls the OIDC claim RPC. It does not
import `main`, routers, startup reconcilers, or the batch serving pump. The
S2 image refuses unexpected leases; S3 adds the isolated job process described
below. One serial worker per pod; no new HPA until queue metrics qualify.

`backend/deploy/sync-backfill-worker.yaml` is the desired on-demand pool and
IAM plan, **not an installed resource receipt**. Infracost supplies actual
cluster/project identities, the existing node SA and approved buckets, gets
lead approval for those exact INV-AUTH/DATA bindings, then applies them from
m5 in the staging window. No command in this lane provisions resources.
Keep the one-zone pool at 1–2 nodes and replicas at 1–2; no Spot or preemptible
capacity. Both the dedicated GSA and KSA must be unique to this workload.

The K8s runtime secret must reproduce backend-sync-backfill's complete env
and secret-reference contract using the approved data-plane bindings. Do not
copy or print secret payloads in a terminal or put them in values/Git. Do not
mount an interactive gcloud config or export a service-account key. Match
`SYNC_BACKFILL_WORKER_SERVICE_ACCOUNT` on Tier A to the GSA; bind
`SYNC_BACKFILL_WORKER_AUDIENCE` to that Tier A service base. The worker's
Workload Identity token uses the same audience.

After the existing role-image train produces and smokes a release digest,
infracost can render the chart for review (substitute approved values):

```bash
helm template sync-backfill-worker backend/charts/sync-backfill-worker \
  --namespace prod-omi-backend \
  --set image.repository=REGISTRY/backend-sync-backfill-worker \
  --set image.digest=sha256:QUALIFIED_DIGEST \
  --set runtimeSecret=APPROVED_RUNTIME_SECRET \
  --set serviceAccount.gcpEmail=APPROVED_GSA \
  --set worker.apiUrl=https://APPROVED_SERVICE.run.app \
  --set worker.audience=https://APPROVED_SERVICE.run.app
```

Applying this rendered configuration requires the lead's window and approval;
keep Tier A `SYNC_BACKFILL_WORKER_PERCENT=0`. Prove healthy pulls with empty
leases before considering S3. Measure idle node-hours; +$3–8/day is only the
reviewed scope estimate and may understate a dedicated node's actual idle
cost. Rollback: scale the deployment to 0 (or uninstall this release), then
set the dedicated pool minimum to 0 after its pods have drained. This lane
does not execute either direction. Infracost reviews idle qualification by
2026-11-09 under the same clean metrics and ramp ownership above.

## S3: fallback-preserving cohort execution

Registration stamps `worker_eligible` only on newly accepted active-fenced
backfill jobs selected by `SYNC_BACKFILL_WORKER_PERCENT` while the sequencer
and legacy registration are on. Caller markers are discarded. Fresh and
legacy-fenced jobs remain ineligible; draining/dark never creates new worker
eligibility. Existing batch admission is untouched. Turning percent to zero
closes claims before persistence reads, even for previously eligible jobs.

Head reservation still enqueues the same named Cloud Task, scheduled five
minutes from reservation. No worker claim means that task begins the normal
handler. Task begin and worker claim race the same transaction, so only one
can choose the drive. Uncertain enqueue retries and failed/expired workers
redrive directly to Cloud Tasks; they do not start another five-minute hold.

Each claimed job runs `utils.sync.worker_job` in a fresh process group. The
child takes the existing Redis token, rechecks the sequencer heartbeat after
acquisition, and uses the existing ledger binding, bounded download and async
pipeline. There is no HTTP budget or replacement-enqueue wrapper. Parent
sequencer heartbeat is 120s; the child renews Redis every 300s. TTLs remain
1800s. A failed renewal cancels execution and exits the entire job process.
The supervisor kills remaining group members even if the root child already
crashed, so detached executor/decoder work cannot outlive the local job.

Ordinary retry preserves staged custody, resets the nonterminal job under its
Redis token, then hands it back through `/fail`. Cancellation or unknown leaf
state preserves Redis until TTL; `/fail` refuses early release while that lock
exists. Completion verifies terminal state after the normal custody/slot
cleanup and immediately kicks the next queued UID head, just like Cloud Tasks;
duplicate completion cannot enqueue it again. The parent stops intake at
shutdown, drains for 1450s within the
1500s pod grace, then kills its owned group. No global pattern-based kill.

Google identity is attached Workload Identity only; the chart masks legacy
key variables from the full runtime secret. `OMI_CUSTOMER_DATA_PROJECT` must
explicitly pin the approved data plane. Staging already has a guarded route:
`OMI_DEPLOYMENT=staging`, production stage semantics, the named `staging`
database in `based-hardware-dev`, private Redis and staging buckets. Both
supervisor and child check `utils.staging_fence` before network/data access.
Do not use shared-data dev as a substitute. Runtime image build/import, live
identity and staging speech/custody outcomes are separate qualification gates.

Run the [staging proof kit](syncsplit-staging.md) in infracost's authorized
window before proposing activation or S6 audio work.
