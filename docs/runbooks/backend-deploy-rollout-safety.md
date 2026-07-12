# Backend Deploy Rollout Safety

Use this runbook when a backend deploy may have produced stale runtime, partial traffic shifts, or GKE pods serving an old ReplicaSet. All commands below are read-only unless explicitly marked as a template for a future deploy workflow.

The `.70` incident-specific cause chain, rollback history, temporary-change
ledger, and follow-up ownership are preserved in
[backend-v0.12.70-production-after-action.md](backend-v0.12.70-production-after-action.md).

## Read GKE rollout state

```bash
python3 backend/scripts/deploy_status_report.py \
  --env prod \
  --include-gke \
  --gke-service backend-listen \
  --gke-service pusher \
  --gke-service llm-gateway \
  --gke-service parakeet \
  --gke-service diarizer \
  --gke-service vad
```

Interpretation:

- `desired`, `updated`, and `available` should match for every active deployment.
- `CrashLoopBackOff`, `ImagePullBackOff`, `ErrImagePull`, and `CreateContainerConfigError` are deploy blockers.
- An old ReplicaSet with replicas beyond the threshold means stale runtime may still be serving while the new rollout is unhealthy.
- Recent warning events are summaries only; inspect the named deployment/pod in an operator shell if the report flags a blocker.

## Read Cloud Run traffic state

```bash
python3 backend/scripts/deploy_status_report.py \
  --env prod \
  --project based-hardware \
  --include-cloud-run \
  --cloud-run-service backend \
  --cloud-run-service backend-sync \
  --cloud-run-service backend-integration
```

Interpretation:

- `latest created` must equal `latest ready` before a revision is safe to serve.
- The traffic column is the serving truth. A newly created ready revision with 0% traffic is not live.
- Image fields show the configured image/tag when Cloud Run exposes it through `services describe`; do not treat checked-in config as proof of a live deploy.

## Verify a planned Cloud Run traffic shift

Future deploy workflows should verify traffic immediately after `gcloud run services update-traffic`:

```bash
python3 backend/scripts/deploy_status_report.py \
  --env prod \
  --project based-hardware \
  --include-cloud-run \
  --cloud-run-service backend \
  --expect-cloud-run-traffic backend=backend-abcdef0-1
```

The command fails if the expected revision is not both latest ready and serving 100% traffic.

## Secret-first GKE rollout gate

Before restarting any GKE workload that consumes `backend-secrets`, workflows should apply/sync the ExternalSecret, wait for `Ready`, then verify key presence without printing values:

```bash
kubectl -n prod-omi-backend wait \
  externalsecret/prod-omi-backend-external-secret \
  --for=condition=Ready --timeout=120s

kubectl -n prod-omi-backend get secret prod-omi-backend-secrets -o json \
  | python3 backend/scripts/verify_k8s_secret_keys.py \
      ./backend/charts/backend-secrets/prod_omi_backend_secrets_values.yaml
```

This checks only key names. It must not decode, log, or store secret values.

## Deterministic production rollout checklist

This is the canonical checklist for `.github/workflows/gcp_backend.yml` and
`.github/workflows/gcp_backend_listen_helm.yml`. A deploy is not complete until
the live GKE, Cloud Run, load-balancer, and API evidence below agrees. Never use
a successful build, a ready zero-traffic revision, or a merged commit as proof
that production changed.

### 1. Pin identity and compare dev/prod configuration

Before dispatch, record the selected workflow ref, full source SHA, expected
seven-character image tag, and immutable Cloud Run child digest. The dispatch
ref and `branch` input must agree. Production resume also requires the exact
candidate suffix and the explicit confirmation string enforced by the workflow.

Compare the GitHub `development` and `prod` environment variable names against
`backend/deploy/runtime_env.yaml` and the rendered workflow outputs. These
identity values are fail-closed contracts:

| Setting | Development | Production |
| --- | --- | --- |
| `ENV` | `dev` | `prod` |
| `GCP_PROJECT_ID` | `based-hardware-dev` | `based-hardware` |
| `GKE_CLUSTER` | `dev-omi-gke` | `prod-omi-gke` |
| `RUNTIME_GCP_PROJECT_ID` | `based-hardware` | `based-hardware` |
| Cloud Run network/subnet | `omi-dev-vpc-1` / `omi-us-central1-dev-vpc-1-subnet-1` | `omi-prod-vpc-1` / `omi-us-central1-prod-vpc-1-subnet-1` |
| `CONTROL_PLANE_URL` | not used by prod resume | `https://api.omi.me` |

`RUNTIME_GCP_PROJECT_ID` is intentionally different from the dev deployment
project. A missing or different value must fail before Helm; after rendering,
the Deployment must contain `GOOGLE_CLOUD_PROJECT=based-hardware`. If the
topology changes, update the manifest, IaC, environment variables, exact guards,
and this table together.

`backend/deploy/runtime_env.yaml` explicitly owns
`GOOGLE_CLOUD_PROJECT=based-hardware` for all four Cloud Run surfaces. A fresh
candidate must receive that value from the rendered manifest; inherited service
state is not acceptable proof of runtime identity.

Verify required secret and notification-channel *names* exist without printing
values. `BACKEND_SECRETS_GSA` may use the checked-in deterministic default, but
the live Workload Identity annotation must match it. Production two-lane sync
also requires `SYNC_BACKFILL_ALERT_NOTIFICATION_CHANNELS`.

Run the non-mutating gates before creating another revision:

```bash
python3 backend/scripts/validate-backend-runtime-env.py \
  --env prod --check-workflows --check-rendered-cloud-run

python3 backend/scripts/preflight-cloud-run-deploy.py \
  --env prod --project based-hardware --region us-central1 \
  --check-secrets --check-traffic
```

Do not add `--repair-traffic` to an investigative or resume preflight.

### 2. Prove schedulable rollout capacity and load-balancer coverage

Capacity preflight must use the pod's required affinity labels, not total cluster
capacity. For every eligible node pool, record zone, machine type, allocatable
CPU/memory, current and maximum nodes, taints, quota/stockout events, and the
number of other scheduled pods. Compute per-node slots as the minimum of CPU,
memory, and pod-limit slots after existing reservations. Require enough slots
for the greater of the current HPA desire or its recent peak, plus
`maxSurge`. A configured autoscaler maximum is not evidence that the zone can
actually supply those nodes.

This is currently a mandatory operator gate; `prepare-cloud-run` does not yet
compute schedulable slots or prove provider stock. Alert with bounded labels and
use rates or dwell where applicable for: eligible-pool headroom, a pool held at
its configured maximum, pending or unschedulable backend-listen pods, fresh
`FailedScaleUp` or `GCE_STOCKOUT` events, HPA desired replicas above computed
schedulable slots, unhealthy NEG endpoints, and repeated GKE-dwell resets or
timeouts. A high configured maximum, such as 50 in a stock-constrained zone, is
not usable headroom until the provider actually creates the nodes.

Do not shrink requests as a first response to a blocked rollout. Request changes
create another ReplicaSet and must be justified by observed peak usage plus
headroom, exercised under representative load, and paired with an explicit
rollback. Prefer an eligible pool in another zone when the failure is a zonal
stockout.

Any new zone must be complete end to end before it counts as capacity:

1. The node pool labels satisfy the Deployment affinity and its autoscaler has
   sufficient headroom.
2. Kubernetes reports a same-named NEG for the zone and ready endpoints enter it.
3. The global backend service attaches that zonal NEG.
4. `gcloud compute backend-services get-health` reports every serving endpoint
   healthy.
5. The pool, autoscaler bounds, NEG attachment, and related quota are captured
   in IaC. An ad-hoc pool is an incident repair, not the durable final state.

### 3. Require a stable GKE dwell before Cloud Run mutation

The GKE gate must continuously observe all of the following for the configured
dwell window. A validation failure or any container restart-count increase
restarts the clock. A fully healthy HPA scale-up or scale-down does not restart
the clock merely because replica counts or pod membership changed:

- Deployment generation is observed; desired, current, updated, ready, and
  available match; unavailable is zero.
- The image is the approved short-SHA image and
  `GOOGLE_CLOUD_PROJECT` is the exact runtime project.
- Exactly one current ReplicaSet owns all desired replicas; every older
  ReplicaSet has desired and actual replicas at zero.
- Exactly the desired number of pods are Running and Ready, with no restarting
  containers, OOM kills, or unschedulable pods.
- HPA current and desired replicas equal the Deployment desire, and
  `AbleToScale=True` plus `ScalingActive=True`.

The automated `gke-gate` helper checks only Kubernetes Deployment, HPA,
ReplicaSet, pod, image, runtime-project, readiness, and restart state. It does
**not** currently inspect NEGs, load-balancer backend health, application logs,
502 rates, or websocket acceptance. Those remain separate mandatory operator
gates: verify every zonal NEG attachment and endpoint, query backend-service
health, smoke `/v1/health` through `https://api.omi.me`, and inspect the dwell
window for 502s, websocket-acceptance regressions, wrong-project/Firestore
errors, and tracebacks. Do not describe those checks as automated until a
separate fail-closed helper is implemented and exercised.

Use at least a two-minute dwell before candidate work and reconfirm for at least
one minute immediately before traffic cutover.

The gate's timeout is a wall-clock budget, not a cumulative-health budget. Each
unhealthy sample discards the accumulated healthy interval while the outer
deadline continues. A cluster that recovers near the deadline therefore still
fails closed unless it can complete a fresh uninterrupted dwell. With the
current prepare settings, one attempt can spend 900 seconds in this gate, then
also pay Helm rollback/rollout time and the mandatory rollback dwell; a rerun
starts a new dwell from zero. Do not blindly extend the deadline. The helper
should emit every reset reason and timestamp, the longest healthy interval, HPA
current/desired state, pending-pod count, and remaining wall-clock budget so a
timeout is operationally diagnosable.

### 4. Reuse immutable candidates or start a fresh serialized deploy

Never blindly rerun after a partial deploy. First list each service's
latest-created, latest-ready, image digest, source label, and spec/status traffic.
For a bounded resume:

- Reuse only the exact `backend`, `backend-sync`, and
  `backend-sync-backfill` zero-percent candidates whose full source label and
  immutable child digest agree.
- Create only the missing `backend-integration` candidate from that pinned
  digest. Do not rebuild, reapply GKE, or reprovision queues/TTL/IAM/alerts.
- Require every candidate to be `Ready=True`, latest-created for its service,
  and still at zero percent. Until keyless IAM signing is implemented,
  all four production candidates must bind numeric-versioned
  `SERVICE_ACCOUNT_JSON` until keyless signing lands. Compute ADC alone cannot
  generate GCS signed URLs, causing authenticated `/v1/users/people` requests to
  return 500 and preventing backfill segment processing. Do not restore the
  retired `GOOGLE_APPLICATION_CREDENTIALS` filename secret: it resolves to
  `google-credentials.json`, which is absent from the b939 image and fails startup.
  The clone renderer drops inherited names before overlays, and the single
  shared Cloud Run flag removes the legacy binding remotely in both dev and
  prod. Do not add a second service-specific removal flag: gcloud rejects
  duplicate map-removal keys. Test the rendered flag count and clone ordering.
- Treat zero-traffic `Ready=True, reason=Retired` as identity readiness only,
  not proof that application startup ran. After applying a temporary tag,
  require every revision to reach `Ready=True` and `Active=True` before smoke.
  Capture its conditions and startup logs before tag cleanup: a failed revision
  can return to `Ready=True/Retired` afterward while retaining the useful first
  failure only in logs or an earlier condition snapshot.
- Before candidate creation, semantically validate the interim signing secret
  without printing it: the numeric version is enabled, the runtime identity has
  accessor IAM, JSON type is `service_account`, client email/private-key fields
  exist, and dummy V4 signing succeeds. After deploy, prove the candidate binds
  that exact numeric version and has no Cloud Run GAC binding. Startup consumes
  `SERVICE_ACCOUNT_JSON`, writes `/tmp/omi-google-credentials.json` mode 0600,
  and sets process-local GAC; that runtime-created path is distinct from the
  forbidden legacy Cloud Run filename binding.
- Add temporary per-revision tags and require the exact tag/revision mapping to
  converge in both `spec.traffic` and `status.traffic`. Remove every attempted
  tag, including after an ambiguous command result, and poll until it is absent
  from both spec and status.
- URL-enabled services must expose both their canonical `status.url` and the
  tagged target's reported output URL. Validate both as origin-only HTTPS Cloud
  Run URLs and require the reported tag host to match the exact tag plus the
  canonical host. Never synthesize or guess a tag URL.
- `backend` is the sole exception: production intentionally sets
  `run.googleapis.com/default-url-disabled=true` with
  `internal-and-cloud-load-balancing` ingress. Require that exact annotation,
  absent canonical/tag URLs, exact spec/status tag convergence, and a
  `Ready=True` and `Active=True` revision warmup; do not probe it directly. Run candidate
  `/v1/health`, OpenAPI POST-route, and safe GET=405 checks through the
  `backend-integration` tag, which is pinned to the same source and image digest.
- Health, OpenAPI, and offline signature checks do not prove the signed-URL user
  path. Before cutover, require a redacted authenticated candidate request that
  generates and fetches at least one real signed object URL, or a narrow
  service-owned probe exercising the same storage client and object permission.
  If no representative fixture exists, the gate is not passed.
- Re-run the stable GKE dwell before cutover.

Measure candidate-tag creation through Uvicorn readiness. In the `.70` rollout,
the backend container became healthy in about 68 seconds, but its three minimum
instances took about 3 minutes 21 seconds to provision; startup logs also showed
sequential Stripe price API calls before Uvicorn became ready. Eliminate or cache
network-dependent startup work, define a measured cold-start SLO (including a
high-percentile target and hard maximum), and derive readiness/smoke retry
budgets from that SLO. Until that work lands, record each candidate's cold-start
duration and do not hide a regression by repeatedly extending timeouts.

The `.70` backfill cutover also proved 512 MiB insufficient under real work:
instances repeatedly used 517-561 MiB and were terminated. The worker contract
now requests 1 GiB at concurrency 1. Treat that as a bounded mitigation; capture
peak and high-percentile memory under representative backfill load before
shrinking it, and keep the change reversible.

For a fresh production image, do not use ordinary `mode=deploy` as a substitute
for the guarded rollout. Use the explicit two-phase path:

1. Dispatch `mode=prepare-cloud-run`, `environment=prod`,
   `deploy_targets=all`, the exact branch/ref pair, and
   `confirm=prepare-cloud-run-prod`. This mode performs a read-only traffic
   preflight, refuses missing or split serving services, pushes only the
   short-SHA image tag (not `latest`), creates all four revisions at zero
   percent with explicit source labels, and skips backend-secret and backfill
   platform reprovisioning.
2. The prepare job snapshots the prior Helm revision/image, rolls GKE with
   `--atomic`, requires a two-minute stable dwell, verifies Cloud Run traffic is
   byte-for-byte unchanged, and proves all four candidates are Ready,
   latest-created, same-digest, exact-source, and zero-percent. Any failure after
   GKE mutation rolls Helm back to the captured revision and rechecks the old
   image. Preserve the emitted source SHA, suffix, child digest, and prior
   serving snapshot.
3. Dispatch `mode=resume-cloud-run`, `environment=prod`,
   `deploy_targets=cloud-run-only`, `confirm=resume-cloud-run-prod`, and the
   exact handoff values. Never transcribe the digest or suffix from an earlier
   run. The resume lane owns candidate activation, temporary-tag smoke, ordered
   promotion, convergence, and all-service rollback.

The prepare suffix is
`<short-sha>-<GITHUB_RUN_ID>-<GITHUB_RUN_ATTEMPT>`. Re-running the same Actions
run creates a new candidate identity (`...-1` becomes `...-2`) even when source
and image contents are unchanged. Resume only the suffix emitted by the
successful attempt. Prove all earlier-attempt revisions remain zero traffic and
record them for explicit retention or cleanup; never substitute their suffix
into the successful handoff.

Candidate preparation intentionally leaves GKE on the new SHA after success so
the resume identity/dwell gate cannot mix two builds. Run the resume promptly.
If the operator chooses not to proceed, restore the captured Helm revision and
verify the old image rather than weakening the resume gate. Do not force-cancel
the prepare job after its GKE snapshot: GitHub cannot run the `failure()`
rollback step after a hard cancellation. If cancellation is unavoidable, treat
GKE state as unknown and perform the captured Helm/image reconciliation before
any new deploy.

Long term, give URL-disabled backend revisions a protected validation route:
attach the exact traffic tag to a dedicated serverless NEG and expose it only
through a restricted load-balancer host/path available to the deployment
identity. That path must preserve tag-to-revision attribution without enabling
the public default URL. Also configure an HTTP startup probe against
`/v1/health` so Cloud Run readiness represents application startup rather than
only process or TCP availability. Track both changes as durable infrastructure,
not incident-time ad-hoc mutations.

Only one backend deployment workflow may run per environment. Promote in
dependency order: `backend-integration`, `backend-sync-backfill`,
`backend-sync`, then `backend`. Before mutation, snapshot the single 100%
serving revision for every service. After each shift, require spec and status to
converge to the candidate at 100%. Smoke URL-enabled services through their
validated canonical service URLs. For `backend`, smoke `/v1/health` and the
OpenAPI/405 control-plane contract through the exact guarded
`https://api.omi.me` load-balancer URL. Before OpenAPI validation, append a
cryptographically random, URL-safe, non-secret probe token to `/v1/health`,
and reissue that same unique probe on every attribution poll. Every response
must be HTTP 200. Require an exact Cloud Logging request-log entry whose
`logName` is `projects/PROJECT/logs/run.googleapis.com%2Frequests`, whose
`resource.type=cloud_run_revision`, `service_name=backend`, and whose
`revision_name` equals the exact candidate. Missing evidence, evidence for a
different revision or log, or a logging command failure is a cutover failure;
do not use a partial traffic percentage as a substitute. Bounded-poll both spec
and status convergence after every forward or rollback traffic command. A
rollback command error is ambiguous: accept it only if the snapshot revision
still converges in both surfaces; otherwise report the verified reconciliation
failure and manual command. On any failure, reconcile **all four** services to
the snapshot in reverse order and verify the rollback.

The prepare-plus-resume path implements this ordering and rollback today. The
normal `deploy` lane still uses its legacy backend-first sequential traffic
commands without the same per-service smoke and rollback wrapper. Generalize the
verified promotion helper into one atomic fresh-deploy workflow before calling
the ordinary path deterministic; until then, production must use the explicit
two-phase path above.

Status reporting must be phase-aware. After a pre-cutover candidate failure,
zero-percent/not-promoted findings are expected secondary diagnostics; the first
failed activation, condition, or smoke is the root-cause signal. Preserve it and
do not let an unconditional post-promotion expectation obscure the actual gate.

### 5. Keep a temporary-change rollback ledger

Before changing HPA bounds, node-pool bounds, resources, affinity, or capacity,
record:

| Field | Required evidence |
| --- | --- |
| Before state | Exact `kubectl`/`gcloud` output or IaC revision |
| Change | Command or IaC diff, operator, UTC timestamp, and reason |
| Classification | Temporary mitigation or intended durable topology |
| Revert | Exact revert command/change and safe trigger |
| Expiry | Deadline or owner for conversion to IaC |
| After state | Rollout, HPA, node, NEG, endpoint-health, and user-impact proof |

Apply one reversible change at a time. Restore temporary HPA or autoscaler caps
after the stable dwell. A capacity repair intended to remain must be represented
in IaC before the incident is considered fully closed.

### 6. Preserve after-action evidence

Attach this evidence to the deployment summary or PR:

- workflow URL/run ID, exact ref, full source SHA, image tag, and immutable child
  digest;
- GKE Deployment/HPA/ReplicaSet/pod snapshot, rendered runtime project, dwell
  timestamps, and restart/OOM/event summary;
- eligible node-pool zones and bounds, NEG sizes/attachments, and backend-service
  health;
- all four Cloud Run latest-created/latest-ready revisions, source labels,
  images, traffic before/after, default-URL policy, first-failure conditions and
  startup logs, and any rollback result;
- queue, IAM, TTL, log-metric, and alert-policy checks for two-lane sync;
- `/v1/health`, desktop OpenAPI/405 probes, websocket/session acceptance, 5xx/502
  checks, and sanitized logs for the observation window;
- every temporary-change ledger entry and any durable IaC follow-up.

Only then report the Python backend as deployed. Desktop channel registration or
promotion remains a separate explicitly authorized operation.

### 7. Known hardening backlog

Track these as follow-up work rather than rediscovering them during the next
incident:

- Pin the GKE Deployment to an immutable image digest and verify each pod's
  `imageID`; the short-SHA container tag is still mutable.
- Remove or cache the Stripe/network-dependent startup path and enforce the
  measured cold-start SLO in candidate warmup.
- Represent the zone-B pool, autoscaler bounds, NEG attachment, and load-balancer
  settings in IaC; add topology-spread policy and alternate-zone headroom.
- Automate fail-closed NEG/backend-health, 502, websocket-acceptance,
  wrong-project, traceback, and reconnect-anomaly gates.
- Build a restricted pre-cutover probe path for the default-URL-disabled backend,
  or keep the integration-smoke/post-cutover-rollback limitation explicit.
- Replace private-key GCS URL signing with refreshed ADC plus IAM `signBlob`,
  grant the runtime service account the narrow self-signing permission, and only
  then remove `SERVICE_ACCOUNT_JSON`. Add an authenticated candidate
  smoke that exercises at least one real signed-URL response; health/OpenAPI
  checks did not catch the `.70` signing regression.
- Generalize the resume lane's dependency ordering, smokes, and rollback to fresh
  deploys; add verified Helm rollback rather than relying on rollout timeout alone.
- Add one verifier for the sync queues, IAM bindings, Firestore TTL, log metrics,
  alert policies, and notification channels.
- Retry bounded Firestore `ABORTED`/409 transaction-contention failures at both
  the `/v3/memories/batch` and `/v1/action-items` create/update/batch ownership
  boundaries, with jitter and idempotency guards. Exhaustion must return a
  generic retryable 503; add concurrency regression tests and denominator-based
  route error alerts. During the `.70` soak, memory and action-item requests
  failed while adjacent requests succeeded, so deploy health alone cannot close
  this failure class.
- Gate anomalous reconnect/request amplification independently from raw HPA
  demand so a correctness loop cannot consume the whole capacity envelope.
