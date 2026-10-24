# In-cluster safety guards

This independent Helm release provides **Parakeet** and Cloud Run **batch**
rollback Jobs. See [BATCH.md](BATCH.md) for dedicated WIF, env-preserving rollback,
and the aggregate producer required before replacing the P90 laptop owner.
It does not modify the Parakeet serving pod template or deploy its chart.
The lead deploys after review; developing/testing this chart requires no cloud credentials.

## Deployment and kill switch

Dispatch `.github/workflows/gcp_incluster_guards.yml` on `main` after merge:

- `environment=prod` (or `development`)
- `source_sha=<full merged commit SHA reachable from main>`
- `enabled=true`
- `dry_run=false` (development always forces true)

The workflow uses the existing environment's deploy WIF identity, not the Job's
ServiceAccount, and serializes on `deploy-incluster-guards-<environment>`.
It upgrades only `<stage>-omi-incluster-guards` in `<stage>-omi-backend`.
Helm success proves installation, not a completed guard reading. Inspect the
first scheduled Job and state ConfigMap before retiring the existing Parakeet
laptop owner. A fresh install/identity starts a full 15-minute arming period.

`dry_run=true` suppresses HPA writes but retains state and decision evidence.
CronJob value changes apply to new Jobs; an already running Job retains its
startup settings for at most its 240s deadline. Verify active Job termination
when an immediate stop is required.
`enabled=false` removes the guard resources. Both use the same dispatch path.
Revert the PR or uninstall this independent release to remove it. Neither kill
switch undoes an already applied rollback; that requires a separately approved
HPA change. A Helm upgrade can retain the state data under Helm's three-way
merge; any spec/image/generation identity change still resets arming.

## Parakeet contract

Every five minutes, a bounded Job reads the exact HPA spec, deployment images,
readiness, recent Pod FailedScheduling events, and direct in-cluster Prometheus.
Only floor 5/8 without `parakeet_request_latency_p99` is armed. The state identity
includes the entire HPA spec, HPA generation and deployment images. Ordinary
autoscaling replica changes do not restart the clock. Configuration/image changes
reset the 15-minute clock. Readiness shortfall uses HPA desiredReplicas, not the
floor. ScalingActive must be true, as in the original P77 guard.

P77r refusal threshold: `max(.02, baseline * 1.25 + .005)`, inclusive. The
baseline is the admission-weighted refusal fraction over the same rolling UTC
hour ending exactly seven days earlier (`[1h] offset 7d`), using the same
accepted / overflow / batch_pressure outcomes as the current 15-minute reading.
It requires >=20 historical admissions and exactly 12 available Parakeet replicas
throughout that hour. Historical accepted-counter and replica freshness are
checked at one-minute checkpoints (<=120s); absent checkpoints fail qualification.
Each checkpoint also requires every listen scrape target to be up and have an
accepted counter, with no unmatched counter targets. The target count must match
the independent available-replica inventory for the listen deployments, including
canaries; fresh target and deployment telemetry is required. Partial target data
cannot inflate the baseline while the remaining admission series stay fresh.
Missing/nonfinite/low-sample/non-12-pod history is BLIND, never an implicit 2%
fallback. At a 6.3% baseline, the trip threshold is 8.375%. Values and the computed
`reading.refusal_threshold` are logged. This guard version restarts the arming clock.

Other P77 thresholds are unchanged: first-text p95 >= 30s, post/v2 p95 >=
3s, first-text >30s count >12, no-text deadline count >36 in 15m. Under 20
first-text/admission samples, latency/fraction thresholds are observations only;
absolute error counts, readiness and scheduling trips remain independent.
Missing/nonfinite data, stale counters (>120s), or absent GPU activity are blind,
never clean. Fresh low sample counts with successful NaN histogram/ratio arithmetic are
LOW_SAMPLE (never CLEAN); a missing series/query error is still blind. Zero GPU
activity during that quiet sample is not itself a trip. This prevents idle
night hours from becoming a rollback solely because quantiles are undefined. Three consecutive blind readings
trip after the full arming window. A fresh usable reading resets the counter.
Prometheus warnings and incomplete/old query results count as blind. The v2
counter also gets an explicit freshness check beyond the original script.

The only serving write is P77 `step_fast.build(old, 12, rollback=True)`:
JSON Patch tests the **entire observed `/spec`**, sets minReplicas=12, and restores
the Value=3 latency metric. Metric/cap/downscale drift assertions are retained.
Scale-up must match either the legacy +1 pod/60s policy with zero stabilization,
or P77r's exact zero-stabilization, selectPolicy Max, +4 pods/15s policy.
Concurrent changes fail the test, with no retry against a newly read
spec. Failed drift checks fail the Job. Kubernetes read failures fail without
inventing an observed spec or bypassing the lookback. Missing HPA is therefore
safe in development and visible as a failed reading.

The production chart proposes floor 8, workload-only scaling and +4 pods/15s,
retaining max12, requests2/GPU35 and the 900s downscale window. That allows an
8->12 recommendation on the next controller sync (normally 15s), within a 60s
controller-response budget once metrics recommend scale-out. It cannot promise
GPU readiness within 60s; adapter lag, scheduling and model startup still apply.
See [Kubernetes scaling behavior](https://kubernetes.io/docs/concepts/workloads/autoscaling/horizontal-pod-autoscale/#configurable-scaling-behavior).
Install/verify the updated guard first; then the lead may activate the chart
retry and arm a fresh 15m lookback. Do not apply the chart with the old guard,
whose rollback drift check rejects the faster policy. For a retry halt, restore
floor12 and workloadOnly=false together; the fast scale-up policy can remain.
PR #23425's floor/workload-only changes are included in this proposal.

The mutable, nonsecret state ConfigMap is created by Helm. The Job may only
get/patch that exact ConfigMap, using a resourceVersion test. It records verdicts
in data and annotations, last observation time, and the blind/arming state.
The Parakeet Job has no cluster permissions, secrets, pod/exec, GCP identity
annotations, or cloud API calls. RBAC cannot constrain *fields* of an HPA patch; the patch
builder and its behavioral tests enforce that narrower application boundary.

## Batch queue observer coverage and blockers

Available worker metrics (`utils/batch_pipeline/metrics.py`, also allowed by
`deploy/cloud_run_gmp_sync.yaml`) are oldest admitted uncommitted age, retry age,
and the last successful refresh timestamp. A PodMonitor in this independent
release exposes existing batch worker metrics to local Prometheus (the worker's
existing PodMonitoring feeds GMP). It selects only batch-pipeline-worker pods
in the release namespace; it does not restart or modify workers. Queue metric namespace is the worker
Pod's Kubernetes namespace (`diarizer/batch_pipeline_runtime.py`). Both refresh
age and scrape age must be <=120s. Missing/stale/nonfinite samples are BLIND.

A fresh `omi_batch_pipeline_oldest_age_seconds > 1800` emits **TRIP**,
`uncommitted_job_age_over_30m`. This is a conservative stuck-job **proxy**:
`database/batch_pipeline_store.py:oldest()` queries `merge_pending=true` and
measures from enqueue. It includes historical obligations and legitimate deep
queues; it cannot identify new jobs or prove a projection wedge. Retry age is
logged, not another rollback condition. Usable readings without that trip are
**PARTIAL**, never a claim of complete batch safety.

There is no exported metric for **new projection obligations >15m**, pinned
object custody loss, or VAD-proven unrecovered speech. Those P90 signals require
Firestore/GCS metadata readers and serving-revision/ramp clocks. No such readers,
permissions or invented metrics are introduced here. **Keep the P90 safety owner
running** until those gaps have a verified aggregate producer. The separate
[batch rollback Job](BATCH.md) reads serving Cloud Run revisions and consumes
trusted P90 aggregates without customer metadata access.

Every reading emits JSON `batch_safety` / `parakeet_guard` records without IDs,
workload env, event messages, or HTTP bodies. A batch TRIP/BLIND or Parakeet
TRIP/BLIND exits nonzero; backoffLimit=0 prevents retries from accelerating the
blind counter. The state ConfigMap records `omi.me/batch-safety-verdict` and
`omi.me/parakeet-guard-verdict`. Kube-state-metrics exposes failed Jobs without
an exporter or new Job network listener.

**Alert routing needs lead verification:** the checked-in monitoring values say
Grafana owns notification routing and disable Alertmanager. This chart does not
claim a PrometheusRule will page. Wire/verify Grafana alerts for:

```promql
(kube_job_status_failed{namespace="prod-omi-backend",job_name=~"prod-omi-incluster-guards-.*"} > 0)
and on(namespace, job_name)
(time() - kube_job_status_start_time{namespace="prod-omi-backend",job_name=~"prod-omi-incluster-guards-.*"} < 600)
```

and absence of recent scheduled success/readings (account for expected WARMUP,
PARTIAL and deliberate dry run). Use the structured log/ConfigMap verdict to
distinguish safety trips from unavailable measurements. Verify actual delivery
before treating the batch observer as an unattended pager. This is an explicit
v1 activation blocker, not a claim that a nonzero exit alone delivers a page.

## Network and scheduling

The repository's only NetworkPolicy is in `listen-edge` and selects its own
pods; no committed policy selects this Job or denies monitoring ingress. Direct
backend -> monitoring TCP/9090 is permitted by those manifests. Live policy may
differ: the lead must verify it before deployment. If a default deny exists,
allow Job DNS UDP/TCP 53, Kubernetes API TCP 443 (and the GKE control-plane
endpoint/target port as appropriate for that CNI), and monitoring Prometheus
TCP 9090 in both egress and ingress. Do not add broad API proxy privileges.
A blocked scrape produces BLIND rather than clean data.

The image digest matches the existing Grafana stats-proxy Python image.
The ConfigMap also mounts a generated copy of the dependency-free
`backend/omi_logging.py`; the launch guard verifies source/mount wiring and byte
equality with that canonical module. Regenerate with
`cp backend/omi_logging.py backend/charts/incluster-guards/files/omi_logging.py`
when the canonical module changes. JSON safety fields are in the structured
log message, with ERROR severity for TRIP/BLIND.
No GPU requests/tolerations; required node affinity rejects GKE accelerator
nodes as well as named Parakeet/batch pools. Non-root, read-only filesystem,
dropped capabilities, and bounded CPU/memory keep the Job small.

## Cloud Run rollback: approved scoped identity

Production keeps `batch.enabled: false` (see `prod_omi_incluster_guards_values.yaml`)
until the deployer RBAC for the `-batch` objects is approved (access change,
David) and g2's trusted producer exists; `batch.cloudRunRollbackEnabled` stays
true there so re-enabling needs only the `batch.enabled` flip. Development
leaves the writer off entirely.
The dedicated KSA/GSA, four service-level `roles/run.developer` bindings,
runtime-SA actAs if required, and exact-KSA WIF binding are described in
[BATCH.md](BATCH.md). David approved that resource-scoped role on 2026-10-24.
No project-wide operations role is needed: the guard polls service readbacks.
The lead applies IAM and deploys; developing this chart applies neither.
Disabling removes the batch resources including its state ConfigMap, leaving the
Parakeet guard. Save state before removal; use dry run to stop writes while
retaining pending rollback intent. Retain P90 until the
trusted aggregate producer and real alert delivery have been verified.

## Local verification

Use `backend/.venv/bin/python -m pytest backend/tests/unit/test_incluster_guards.py -q`
and `make preflight` through `omi-heavy`. Tests use fake Kubernetes/Prometheus
clients and `helm template` only. `fixtures/incluster_guards/hpa_spec.json`
contains only the P77 HPA spec; `rollback_patch.json` freezes the original
`step_fast.build(spec, 12, True)` output. No inventory status/env/payload is copied.
