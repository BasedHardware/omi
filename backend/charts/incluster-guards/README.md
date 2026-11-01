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
`enabled=false` removes the guards but retains their state ConfigMaps. Both use
the same dispatch path. Uninstalling this independent release also retains
state. Neither kill
switch undoes an already applied rollback; that requires a separately approved
HPA change. Helm manages only the state ConfigMap shells; each Job owns its
mutable data. A serving identity change still resets arming.
The state shells render even when `enabled=false`, so a first 0.3.2 upgrade
using the global kill switch applies retention rather than pruning old state
before that annotation exists. Optional batch state still requires
`batch.enabled=true` and `batch.cloudRunRollbackEnabled=true`; disabling the
global guard does not change those settings or create new batch object names.
When migrating a release that previously installed the batch writer, retain
both batch settings for the first 0.3.2 upgrade (the global kill switch can be
false). After that succeeds, either batch setting can be disabled safely.

## State ownership and recovery from a failed Helm upgrade

Chart 0.3.2 renders the existing `-state` and optional `-batch-state` ConfigMaps
with `helm.sh/resource-policy: keep` and **no data field** (not even `{}` or
`null`). Helm creates each shell on first install; the Job initializes data on
its first resourceVersion-guarded write. Names and get/patch-only Job RBAC stay
unchanged. The Parakeet Job preserves existing annotations when adding verdicts,
including the retention policy and Helm release identity.
It also restores the keep policy if an older in-flight Job erased it during
the upgrade; it never restores or changes the state data on Helm's behalf.

The 0.3.1 deployment failed because server-side apply tried to set `data.state`
back to `'{}'`, after `Python-urllib` had taken ownership through the Job's
JSON Patch. Omitting that field lets Helm relinquish ownership while the
Job-owned live value remains unchanged, per the
[Kubernetes SSA conflict contract](https://kubernetes.io/docs/reference/using-api/server-side-apply/#conflicts).
Helm must never render the Job's state, verdicts, observation clocks or annotations
from a live `lookup`: those fields belong exclusively to the Job. Retention
protects both state objects when disabling/removing the guards, including batch
pending rollback intent. Re-enabling reuses the same objects and their state;
Helm's [keep policy](https://helm.sh/docs/howto/charts_tips_and_tricks/#tell-helm-not-to-uninstall-a-resource)
can leave them orphaned after release removal, so preserve their release metadata.

For the failed 2026-10-26 upgrade (run `40252836085`), the lead/op1 should:

1. Verify the release status is `failed` with `helm status prod-omi-incluster-guards
   -n prod-omi-backend`. A `pending-*` status indicates a different concurrency
   problem; stop and escalate rather than editing Helm storage.
2. Dispatch the existing workflow above from `main`, with `source_sha` set to
   the full merged 0.3.2 fix SHA and the same `environment=prod`, `enabled=true`,
   `dry_run=false` inputs. This runs the usual `helm upgrade --install ...
   --atomic --wait --timeout 180s`. A failed release is upgradeable:
   [Helm's upgrade preparation](https://github.com/helm/helm/blob/v4.2.4/pkg/action/upgrade.go#L218-L256)
   accepts it, using the deployed revision when available or the failed revision
   when none is deployed. No uninstall, pre-rollback, ConfigMap hand edit,
   release-secret edit, force replacement or `--force-conflicts` is required.
3. Verify Helm reports `deployed` at chart 0.3.2, the script ConfigMap matches
   the merged source, and the existing state ConfigMap UID is unchanged. Check
   that the prior rollback marker/streak survived installation and that the next
   scheduled Job retains the keep annotation while updating its normal state.
   The Job may legitimately advance state; compare at the upgrade boundary rather
   than requiring identical data after another reading.

The first recovery upgrade still has old successful revisions in its history:
an unrelated failure could trigger an atomic rollback to a pre-0.3.2 manifest
that templates state, reproducing the old conflict. If that occurs, diagnose the
other failure and retry a corrected **forward** upgrade. Do not roll back to a
pre-0.3.2 chart or restore its state template; keep the 0.3.2 ownership fix when
reverting other guard behavior. A successful recovery and subsequent scheduled
reading require operator verification; local template/unit checks do not prove
production recovery.

## Parakeet contract

Every five minutes, a bounded Job reads the exact HPA spec, deployment images,
readiness, recent Pod FailedScheduling events, and direct in-cluster Prometheus.
Any workload-only floor below the 12-replica rollback cap without
`parakeet_request_latency_p99` is armed; the floor is read from the HPA itself,
so operator floor changes cannot silently disarm the guard (the former 5/8
enumeration read NOOP at floor 10 on 2026-10-24/25). The state identity
includes the entire HPA spec except `minReplicas`, and deployment images. Ordinary
autoscaling replica changes do not restart the clock. Configuration/image changes
reset the 15-minute clock; scheduled floor writes do not (they also bump the HPA
generation, which is likewise excluded), or the guard could never arm under a
time-of-day floor. Readiness shortfall uses HPA desiredReplicas, not the
floor. ScalingActive must be true, as in the original P77 guard.

## Time-of-day floor schedule

`floorSchedule.enabled` renders a reviewed 24-entry UTC-hour floor table into
the guard's script ConfigMap as `floors.json`; the table's presence is the
schedule's only switch (development and non-opted releases never write the
floor from a schedule). On the first reading after each hour rollover the
guard patches `spec.minReplicas` to the hour's entry with the same atomic
test-the-whole-spec JSON patch as the rollback, under the same dry-run kill
switch and the same existing RBAC: **no new objects**, so the prod deployer's
name-scoped RBAC (which refuses new object names) accepts the upgrade. The
schedule defers, logging `deferred_guard_rollback`, whenever a guard rollback
is in force (the `parakeet_request_latency_p99` metric is present), and never
runs in the same reading as a rollback; the safety guard can still raise any
hour to 12. A scheduled **lower** additionally requires the guard to be armed
under the current spec identity: readings taken while the HPA is parked above
the cap still advance the arming clock (the floor is excluded from the
identity), so a drop lands on an armed guard - if the clock has not elapsed
(for example right after an operator clears a rollback), the lower defers
(`deferred_guard_not_armed`) until it has, and the higher floor holds in the
meantime. The 2026-10-25 table was derived from the 10-23..10-25 guard
trace with decisive samples only: floor 10 degraded across Sunday
12:05-13:50Z (measured p95 34.5-55.5s on >= 100-text windows) so 12-13Z
carries 12; Saturday 22:30Z ran 8 replicas at 701 first texts/h with p95
12.4s (8), and Saturday 14-15Z held 10 replicas at 521-692/h with p95 14-20s
(10-11). At the measured $0.583448/pod-hour the table projects ~$4.2k/mo
against ~$5.1k/mo for a flat 12, realized only when the parakeet-pool nodes
actually deschedule (p77 PLAN caveat).

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
3s, first-text >30s count >12, no-text deadline count >36 in 15m. The
first-text p95 trip additionally requires a decisive sample (2026-10-24 06:19Z
and 2026-10-25 05:40Z rolled floor 8 back on 26-37 first texts whose 95th
percentile saturated at the histogram's 60s top bucket): a measured value
strictly inside the histogram (the exported buckets end at 60s, and
`histogram_quantile` clamps to that boundary when the quantile lands beyond
it), at least 5 texts over 30s, and a 15-minute count of at least
`max(100, 0.5 * the weekly same-hour count's 15-minute equivalent)` (the
baseline counts one hour, so its window share is halved, never the raw hour
against the live window; 100 when that baseline is unavailable). A
regression-shaped reading below
that sample floor is **unmeasured**: it reads BLIND (ERROR log, nonzero exit,
alertable) and never rolls back; it also never counts toward the
three-consecutive-blind rollback, which missing/stale data still drives.
Under 20 first-text/admission samples, latency/fraction thresholds are observations only;
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
measures from enqueue, skipping durable allowance policy holds
(`compute_decision` outcome=held reason=allowance_exhausted; 131 such holds
kept this proxy tripped permanently on 2026-10-25) within a bounded 500-row
FIFO prefix; a prefix filled entirely by holds fails toward tripping on the
oldest hold's age rather than a fresh zero. It still includes legitimate deep
queues; it cannot identify new
jobs or prove a projection wedge. Retry age is
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
workload env, event messages, or HTTP bodies. The batch section is **isolated
evidence** (2026-10-25 21:06Z ruling): its trips and unknowns are logged and
recorded in the state ConfigMap but never fail the Job or block the Parakeet
schedule - only a Parakeet TRIP/BLIND exits nonzero.
backoffLimit=0 prevents retries from accelerating the
blind counter. The state ConfigMap records `omi.me/batch-safety-verdict` and
`omi.me/parakeet-guard-verdict`. Kube-state-metrics exposes failed Jobs without
an exporter or new Job network listener.

## Rollback expiry and the explicit clear

An applied rollback does not wait for a human forever: while rolled back, the
Job keeps evaluating readings, and after **one full 15-minute lookback window
of consecutive clean readings** (no trips, no blind, no unmeasured, not
low-sample) it clears itself - restoring workload-only metrics with the floor
still at 12, after which the arming/usable gates own any scheduled reduction.
Any unusable reading restarts the clean streak; a real regression keeps
re-tripping readings, so its rollback never expires. A rollback/expiry loop is
bounded and visible: each cycle holds the cap for at least the clean window
plus a fresh arming window before any lower applies. The explicit operator
clear remains: patch the HPA to remove the `parakeet_request_latency_p99`
metric (an approved HPA change); the guard reconciles on the next reading.

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
Disabling removes the batch resources while retaining its state ConfigMap, leaving
the Parakeet guard. Use dry run to stop writes while
retaining pending rollback intent. Retain P90 until the
trusted aggregate producer and real alert delivery have been verified.

## Local verification

Use `backend/.venv/bin/python -m pytest backend/tests/unit/test_incluster_guards.py -q`
and `make preflight` through `omi-heavy`. Tests use fake Kubernetes/Prometheus
clients and `helm template` only. `fixtures/incluster_guards/hpa_spec.json`
contains only the P77 HPA spec; `rollback_patch.json` freezes the original
`step_fast.build(spec, 12, True)` output. No inventory status/env/payload is copied.
