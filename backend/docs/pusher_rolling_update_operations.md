# Pusher — Hardened native RollingUpdate (operator and developer operations)

This document is the operational contract for the hardened **native Kubernetes
`RollingUpdate`** of the **pusher** GKE workload. It is deliberately not a design
essay: it states what operators and developers can rely on, the exact termination
sequence the chart produces, the preflight gates that must pass before a rollout
is allowed, and the N/N-1 compatibility rules.

Scope and ownership:

- The **chart values** are the single source of truth for rollout inputs
  (`backend/charts/pusher/{dev,prod}_omi_pusher_values.yaml`). When the live
  cluster disagrees with the chart, the chart wins and the gap is a deploy
  problem to close, never a reason to weaken the chart.
- This hardening is **native `RollingUpdate` only**. No Argo Rollouts, Flagger,
  service mesh, Gateway API, or two-color experiment is in scope.
- **Production adoption is a LATER, explicit decision.** This PR lands the
  hardening and the operational contract on top of the existing pusher baseline.
  It is qualified **dev-first** (see [Dev qualification plan](#dev-qualification-plan)).
  Do not read this document as "pusher is production-ready for the new rollout"
  until SCA-40 lands and a healthy prod pusher baseline is confirmed.

> Related runbook: `backend/docs/runbooks/pusher-degraded.md` covers sustained
> degraded-session ratio. This document covers the rollout itself.

---

## Honest availability contract

State this plainly, because it governs every operator decision below: **no
approach preserves in-flight WebSocket sessions across a pusher cutover over the
proxied ALB + NEG path.** Pusher holds long-lived binary WebSocket sessions from
backend-listen. When a pod's endpoint leaves the NEG, the load balancer cuts the
existing connections on it.

What "graceful drain" actually means here:

- **Zero new-connection rejection during a healthy rollout.** The readiness gate
  flips a draining pod to `503` so the LB stops routing *new* sessions to it
  while other pods are still serving. New backend-listen connects go to healthy
  pods.
- **A bounded reconnect gap per affected session, roughly 1-60 seconds.**
  backend-listen owns the reconnect: when its pusher socket is cut it reconnects
  to a healthy pod. The gap is the time between the cut and the next successful
  reconnect, not a migration.
- **The LB cut is bounded by BackendConfig `connectionDraining`.** It sets how
  long the load balancer waits before hard-cutting in-flight connections on an
  endpoint that has left the NEG — here `drainingTimeoutSec: 60`. Without it the
  default is a hard cut on endpoint removal.
- **Background finalization is bounded by the pod grace period.** In-flight work
  (audio batched to GCS, transcripts routed to integrations, LLM analysis,
  speaker-sample extraction) is drained by the app within
  `terminationGracePeriodSeconds`; anything still running at the deadline is
  SIGKILLed. Durable finalization is reconciled by the conversation-finalization
  job lane, so a SIGKILLed session does not strand a conversation in `processing`.

Do **not** claim sub-second or zero-session-impact cutover. The contract is:
new connections keep flowing, existing sessions take a bounded reconnect gap,
and background work finishes or is durably reconciled.

---

## What changed in the hardening

The chart previously sent liveness, readiness, and startup probes all to
`/health`, had no app-level drain (`preStop` was only `sleep 15`), and the
BackendConfig had no `connectionDraining` (so the LB hard-cut in-flight WebSocket
on endpoint removal). The hardening splits serving readiness from liveness and
adds an app-level drain:

| Concern | Before | After (hardened) |
| --- | --- | --- |
| Readiness signal | `readinessProbe` -> `/health` | `readinessProbe` -> `/ready` (200 serving / 503 draining) |
| Liveness / startup | `/health` | unchanged, still `/health` |
| LB health check | BackendConfig `healthCheck.requestPath: /health` | unchanged, still `/health` |
| New-connection drain | none; `preStop` = `sleep 15` | `preStop`: `curl -sf -m 5 -X POST http://localhost:8080/__internal/drain \|\| true; sleep 15` — POST flips `/ready` to 503 (loopback), `\|\| true` never blocks termination, `sleep 15` covers NEG convergence |
| LB in-flight cut | none; `connectionDraining` absent (hard cut on endpoint removal) | BackendConfig `connectionDraining.drainingTimeoutSec: 60` bounds the LB wait (60 <= grace 120) |

Endpoints introduced by this hardening (on the pusher process, port 8080):

- `GET /ready` -> `200` while serving, `503` once the process is draining.
- `POST /__internal/drain` -> **loopback only**. Triggers the drain: flips
  `/ready` to `503` and lets background finalization run down within the grace
  period. `preStop` is the only intended caller.

Rollout inputs that are **already** correct in the chart and are reused, not
rebuilt (verified against `{dev,prod}_omi_pusher_values.yaml`):

- `progressDeadlineSeconds: 9600` in **both** charts. CI derives the healthy
  rollout budget from the chart (`backend/scripts/verify_pusher_rollout_budget.py`);
  prod at its 40-pod HPA ceiling is fourteen waves of ~640s availability = an
  8960s healthy budget, with 9600s as the committed deadline. The observed live
  value of 600 on an existing release is a **deploy drift gap**, not a chart gap
  — the chart value stays at 9600 and a real deploy must reconcile the cluster to
  it.
- prod `strategy: RollingUpdate { maxUnavailable: 1, maxSurge: 2 }`
  (dev is `{ maxUnavailable: 0, maxSurge: 1 }`).
- `terminationGracePeriodSeconds: 120` in both charts.
- prod autoscaling `minReplicas: 12`, `maxReplicas: 40`,
  `activeConnectionsPerPod: 30`; dev `minReplicas: 1`, `maxReplicas: 3`.
- `podDisruptionBudget.minAvailable: 80%` in both charts.

### Dedicated development Pusher capacity

Development Pusher alone tolerates `dedicated=pusher:NoSchedule`. Its existing
required node affinity still requires matching `service=pusher` and `env=dev`
labels, so that toleration does not admit LLM Gateway, Agent Proxy, or other
workloads to the pool. Production deliberately retains no corresponding
toleration; it is a separate configuration boundary.

Before a dev Pusher rollout, an external approved GKE operation must provide
**two Ready, schedulable Pusher-capable nodes** matching that affinity, each
tainted `dedicated=pusher:NoSchedule`. Two matching nodes leave room for the
single serving pod and its `maxSurge: 1` replacement during a rolling update.
Helm only renders the workload toleration: it does not create, label, taint, or
scale GKE node capacity. Dev HPA remains `minReplicas: 1`, `maxReplicas: 3`,
and its rolling-update settings remain `maxSurge: 1`, `maxUnavailable: 0`.

Fail-closed rollout gates (preflight scripts that must pass before a deploy) are
listed in [Operator runbook](#operator-runbook) and the blocking signals in
[Rollout quality gates (fail-closed)](#rollout-quality-gates-fail-closed).

---

## Termination sequence

For a single pod being replaced during a `RollingUpdate`, the chart produces this
sequence (accurate to `templates/deployment.yaml` and the values files):

1. **Pod enters `Terminating`.** Kubernetes starts the pod's
   `terminationGracePeriodSeconds: 120` clock.
2. **`preStop` hook runs in parallel with endpoint removal.** It runs
   `curl -sf -m 5 -X POST http://localhost:8080/__internal/drain || true; sleep 15`
   — the POST (loopback) flips `/ready` to `503`, `|| true` guarantees the hook
   never blocks termination if the drain call fails, and `sleep 15` gives the NEG
   time to converge before SIGTERM.
3. **Readiness starts failing; the endpoint leaves the NEG.** The readiness probe
   is `failureThreshold: 3` x `periodSeconds: 10`, so a draining pod is removed
   from the Service/NEG endpoints roughly **30 seconds** after `/ready` goes 503.
   From this point the LB sends no **new** connections to the pod.
4. **`SIGTERM` is delivered** (after `preStop` completes; the `sleep 15` bounds
   how long that takes). The pusher lifespan shutdown drains process-level
   background tasks (`drain_background_tasks`) and closes async HTTP client pools.
5. **Background finalization drains within the grace period.** Each active
   WebSocket session drains its background task queue (bounded by
   `BG_DRAIN_TIMEOUT` in the WS handler); audio/transcript/analysis work that can
   finish inside the remaining grace does so.
6. **`SIGKILL` at 120s.** Anything still running at the grace deadline is killed.
   A SIGKILLed session does not strand a conversation: durable finalization is
   reconciled by the conversation-finalization job lane.

Key timing knobs and what they bound:

- `preStop` `sleep 15` — NEG convergence window before SIGTERM.
- readiness `failureThreshold * periodSeconds` (~30s) — how long after `/ready`
  flips 503 before the endpoint is actually removed from the NEG.
- BackendConfig `connectionDraining.drainingTimeoutSec: 60` — how long the LB
  waits before hard-cutting the in-flight connections on the removed endpoint
  (deliberately <= the 120s pod grace).
- `terminationGracePeriodSeconds: 120` — the hard ceiling on background
  finalization before SIGKILL.

---

## Operator runbook

Small, hard-to-misuse steps. Run from the repository root of a checkout that
matches the image you intend to deploy.

### 1. Render the chart and confirm inputs

Render dev and prod and eyeball the values that drive availability:

```bash
helm template pusher backend/charts/pusher \
  -f backend/charts/pusher/dev_omi_pusher_values.yaml \
  --set-string image.digest=sha256:<64-lowercase-hex> \
  --set-string image.tag= \
  --set-string image.pullPolicy=IfNotPresent > /tmp/pusher-dev.yaml

helm template pusher backend/charts/pusher \
  -f backend/charts/pusher/prod_omi_pusher_values.yaml \
  --set-string image.digest=sha256:<64-lowercase-hex> \
  --set-string image.tag= \
  --set-string image.pullPolicy=IfNotPresent > /tmp/pusher-prod.yaml
```

Confirm in the rendered output: `readinessProbe.httpGet.path: /ready`,
`livenessProbe`/`startupProbe` on `/health`, the BackendConfig `healthCheck` on
`/health` plus `connectionDraining`, `preStop` calling `/__internal/drain`, and
`progressDeadlineSeconds: 9600`. Confirm the dev Deployment has the
`dedicated=pusher:NoSchedule` toleration and the prod Deployment does not.

### 2. Run the fail-closed preflight

The chart budget and the rollout gate must both pass. Both are dependency-free
static/contract checks (stdlib only, no cluster or registry reads):

```bash
# Derives the healthy rollout budget from the chart (waves x availability) and
# fails if progressDeadlineSeconds or the workflow rollout timeout undercut it.
python3 backend/scripts/verify_pusher_rollout_budget.py

# Static + contract preflight: capacity headroom, image/config identity, probe
# split, and that the rollout-blocking metrics are DEFINED in utils/metrics.py.
python3 backend/scripts/verify_pusher_rollout_gate.py preflight
```

`verify_pusher_rollout_budget.py` recomputes prod as fourteen waves x ~640s and
fails if `progressDeadlineSeconds` drops below the budget or a workflow's
`kubectl rollout status ... --timeout=` is too short.

`verify_pusher_rollout_gate.py preflight` (the default subcommand) fails closed
(non-zero exit) on any open gate. It checks, statically: capacity headroom
(`podDisruptionBudget.minAvailable`, HPA `minReplicas`, `maxSurge`/
`maxUnavailable`, and `terminationGracePeriodSeconds` >= the connectionDraining
timeout); image and config identity; the probe split
(`readinessProbe` -> `/ready`, liveness/startup -> `/health`,
`connectionDraining` present); and that the rollout-blocking metrics are defined
in `utils/metrics.py` — a missing metric *definition* is a failure, because a
rollout cannot be judged healthy against telemetry that does not exist. It does
not scrape live values; use `... rollback --env <env>` for the rollback-mode
contract check. Do not weaken the chart to make a check pass; fix the input.

### 3. Live production gate and development-qualified digest promotion

The automatic development Pusher workflow builds once, resolves the pushed
`sha256` digest, runs the ConfigMap reference and live capacity gates, waits for
the rollout, and only then uploads `pusher-dev-qualification`. Production remains
manual: it requires that digest plus the successful development run ID. The
production workflow downloads the attestation, verifies its exact GitHub run and
main source SHA, rejects Pusher source/chart drift since that bake, copies the
same digest into the production registry, and deploys `repository@sha256:...`.
It never rebuilds a production Pusher image.

Immediately before Helm, `verify_pusher_live_deployment_gate.py` renders that
exact digest and reads only Kubernetes metadata. It fails closed unless the next
`maxSurge` wave fits on a Ready, schedulable node matching Pusher's affinity and
tolerations. This is capacity evidence, not a claim that the rollout has product
traffic or user-success proof.

The dev Pusher dashboard is backed by the isolated dev Prometheus scrape. It
shows existing connection, readiness/drain, reconnect/recovery and
backend-listen circuit-breaker aggregates, plus target health, without creating
traffic. Pod health alone is not product-success evidence.

#### Read-only development evidence boundary

The development Prometheus jobs discover only `dev-omi-backend` pods carrying
the `env=dev` workload label. They retain the existing bearer-token file
reference; do not fetch `/metrics` directly, inspect the token, copy headers, or
weaken authentication. The dashboard contains only low-cardinality aggregates
and target labels (`job`, `namespace`, and `pod`), never connection IDs, user
data, or request payloads.

For a passive development-bake check in the permitted read-only operator plane,
use the Pusher dashboard or these equivalent PromQL expressions:

- active Pusher WebSockets: `sum(pusher_active_ws_connections{job="pusher-metrics"})`
- sessions currently reconnecting or degraded:
  `sum(pusher_sessions_degraded{job="backend-listen-metrics"})`
- reconnect circuit state and rejected attempts:
  `pusher_circuit_breaker_state{job="backend-listen-metrics"}` and
  `sum(rate(pusher_circuit_breaker_rejections_total{job="backend-listen-metrics"}[5m]))`
- authenticated scrape target health:
  `up{job=~"pusher-metrics|backend-listen-metrics"}`

`up == 1` proves only that Prometheus authenticated and scraped a target; it is
not connection, drain, or recovery proof. A recovery aggregate can move only
when a real client reconnects. If no real connection exists during the passive
window, record reconnect/recovery as **unproven**—do not generate synthetic
traffic to turn the signal non-zero.

### 4. Shared ConfigMap/Secret migration guard (required on key changes)

The 2026-07-22 production Pusher outage was a *non-atomic cross-resource
migration*: the shared key `REDIS_DB_HOST` stopped materializing in its source
while live pusher pods still referenced it. Pusher bulk-loads **all** of its
ConfigMap keys via `envFrom`, so a key removed from that object left pods
`CreateContainerConfigError` while `/health` stayed green — the fleet dropped to
zero healthy pods with no probe signal. `verify_shared_config_migration.py`
fails CLOSED before any mutation when a serving workload still references a
ConfigMap/Secret source or key the proposed state removes or reclassifies.

- **Preflight (CI / pre-push, stdlib-only).**
  `python3 backend/scripts/verify_shared_config_migration.py preflight` scans the
  pusher chart values and fails on a dual-source binding or a malformed
  `valueFrom`. Registered as `shared-config-migration-preflight` in
  `.github/checks-manifest.yaml`; it runs automatically. It has no inventory, so
  it cannot detect a key removed from a bulk-loaded object.

- **Guard mode (operator-invoked — the actual incident root-fix).** Run this
  before **any** change that adds, removes, or moves a ConfigMap/Secret **key**
  consumed by pusher or any serving workload (Deployment/StatefulSet/DaemonSet/
  Job/CronJob/ReplicaSet, incl. `initContainers`). It resolves every
  `env.valueFrom`, `envFrom`, and per-key reference against the proposed source
  inventory and fails closed on a removed/reclassified key. It reads object and
  key NAMES only — never ConfigMap/Secret values.

  ```bash
  # Render the proposed state (--rendered is repeatable across envs/workloads):
  helm template pusher backend/charts/pusher \
      -f backend/charts/pusher/prod_omi_pusher_values.yaml \
      --set-string image.digest=sha256:<64-lowercase-hex> \
      --set-string image.tag= \
      --set-string image.pullPolicy=IfNotPresent > /tmp/pusher-prod.yaml

  # Capture the CURRENT live key names in the guard's inventory format
  # ({configmaps: {<obj>: [key,...]}, secrets: {...}} — names only, never values):
  kubectl -n <env>-omi-backend get configmap <cfg> -o json \
      | jq '{configmaps: {(.metadata.name): (.data | keys)}}' > /tmp/live-keys.yaml

  # Write /tmp/proposed-keys.yaml in the same shape with the keys the object will
  # carry AFTER the change, then run the guard. --previous-inventory is what
  # catches a key removed from an envFrom bulk-loaded object (the outage class);
  # without it, envFrom removals are silent.
  python3 backend/scripts/verify_shared_config_migration.py guard \
      --rendered /tmp/pusher-prod.yaml \
      --source-inventory /tmp/proposed-keys.yaml \
      --previous-inventory /tmp/live-keys.yaml
  ```

  Non-zero exit = a serving workload still references a source/key the proposed
  state removes or reclassifies; do not apply. Needs PyYAML (the backend venv, or
  `pip install pyyaml`).

### 4. Deploy the immutable tag

Deploy the exact short-SHA image tag. Never deploy `latest`, and never let a
chart-only deploy reset the workload to `latest` (per `.github/AGENTS.md`). The
deploy workflow must wait for rollout completion with
`kubectl rollout status deploy/<env>-omi-pusher --timeout=...` and fail on
timeout.

### 5. Rollback

Roll back by re-running the Helm deploy against the **prior immutable image tag**
(not `latest`). Because traffic/runtime rollback to N-1 is always safe by design
(see [N/N-1 compatibility checklist](#nn-1-compatibility-checklist)), this is the
default rollback: point the chart at the previous tag and deploy it.

> Production adoption is a **separate, later** decision. Do not treat prod
> rollback of this hardening as available until SCA-40 (digest chart support,
> chart-only/reuse-image deploy mode, and rollback evidence) has landed and a
> healthy pusher prod baseline is confirmed. See
> [Relationship to SCA-40](#relationship-to-sca-40).

---

## Rollout quality gates (fail-closed)

There are two fail-closed layers, and both must hold:

1. **Static/contract preflight** (run before a deploy, see
   [Operator runbook](#operator-runbook)) — `verify_pusher_rollout_gate.py
   preflight` asserts the capacity, identity, probe-split, and
   metric-*definition* contract. It fails if a blocking metric is not even
   defined, because a rollout cannot be judged healthy against telemetry that
   does not exist. It does not scrape live values.
2. **Live rollout gate** (watched during the deploy) — the blocking signals must
   be green *and* sufficiently populated. The rule that overrides everything
   else: **missing telemetry = pause or fail, never green.** A silent or
   unscrapable dashboard is a failed gate, not a passed one.

Blocking signals (real metric names emitted by pusher / backend-listen):

- `pusher_active_ws_connections` — active pusher WebSocket sessions. The new pods
  must accept sessions and the count must recover to the pre-rollout baseline;
  a flatline means new pods are not accepting traffic.
- `backend_listen_active_ws_connections` — backend-listen side of the path; a
  sustained drop with no recovery indicates listeners are failing to reconnect.
- `pusher_circuit_breaker_state` (0 closed / 1 open / 2 half_open) and
  `pusher_circuit_breaker_rejections_total` — an opening breaker or rising
  rejections during a rollout means pusher is rejecting connections.
- `pusher_sessions_degraded` — sessions backend-listen routed away from pusher.
  Sustained elevation (see `backend/docs/runbooks/pusher-degraded.md`) is a
  user-impact signal.
- `omi_journey_terminal_total{journey="pusher_session"}` outcomes — terminal
  session outcomes; rising `failure` (close code 1011 / application failure) is a
  regression.
- `omi_journey_latency_seconds{journey="pusher_session"}` — end-to-end session
  latency; a rollout must not push this outside its bounded threshold.
- finalization health: `listen_finalization_jobs`, `listen_finalization_retries_total`,
  `listen_finalization_dead_letter_total`, and
  `listen_finalization_oldest_nonterminal_age_seconds`. A rollout that spikes
  retries, dead-letters, or oldest-nonterminal age is failing to drain cleanly.

The gate requires **minimum capability/session counts plus bounded error and
latency thresholds**, not only elapsed time. Time-only gates are forbidden: a
rollout that is merely "old enough" but has not served enough sessions, or is
over its error/latency bounds, is not green.

---

## N/N-1 compatibility checklist

Separate two kinds of rollback:

- **Traffic / runtime rollback to N-1 is always safe by design.** Re-pointing the
  chart at the previous immutable tag and redeploying never requires a data
  migration to undo. This is the only rollback an operator should ever need to
  perform under pressure.
- **Irreversible data changes are a different category** and must never be
  *required* by a rollout's rollback path. If a change is irreversible, the
  design obligation is to make N and N-1 coexist (additive, dual-read/dual-write,
  or feature-gated) so traffic can return to N-1 without a data rollback.

**Full N-1 drain first is required before introducing** any of the following
incompatibilities (these are the changes that break a safe traffic rollback to
N-1 and therefore cannot ride on a routine rolling update):

- **Envelope / key change:** `ENCRYPTION_SECRET` or the per-user envelope
  derivation (HKDF-SHA256 in `utils/encryption.py`). N-1 cannot decrypt
  N-written segments.
- **GCS audio-chunk envelope:** a change to how pusher batches/uploads audio
  chunks to GCS that N-1 cannot read back.
- **New `ConversationStatus`** (or any persisted processing-state enum) that N-1
  does not recognize and would mishandle.
- **Removed or renamed read fields** on persisted models that released
  app-clients or N-1 services still read.
- **Redis key or TTL change** that N-1 interprets differently (cache, rate-limit
  buckets, listen locks).
- **Finalization lease / fence protocol change:** the durable conversation-
  finalization lease and fence protocol (the `durable_job_required` / claim /
  lease-epoch contract pusher enforces) — a change here can let an N-1 session
  double-process or bypass a durable claim.

If a change touches any of the above, it is **not** a candidate for this
hardened rolling update without a documented N/N-1 coexistence plan and, where
relevant, a full N-1 drain. Routine pushes (probe/drain/availability hardening,
non-breaking additive fields) ride the rolling update and roll back to N-1 by
re-pointing the chart.

---

## Dev qualification plan

This hardening is qualified **dev-first**. Dev is the place to prove the
choreography (readiness flip, app drain, NEG convergence, reconnect gap,
finalization drain) end to end before any prod consideration.

How to qualify on dev (pusher dev: 1-3 pods, `maxUnavailable: 0 / maxSurge: 1`):

1. **Build once and render the digest** exactly as in the
   [Operator runbook](#operator-runbook). The automatic workflow records its
   digest only after the development rollout succeeds.
2. **Observe the passive bake.** Use the dev Pusher dashboard's connection,
   readiness/drain, and reconnect-circuit panels. Do not manufacture traffic or
   infer product success only from readiness.
3. **Use the resulting attestation for a manual production request.** Supply
   the exact digest and development qualification run ID; the production workflow
   validates the evidence, live ConfigMap references, exact digest render, and
   real next-wave capacity before Helm mutation.
4. **Record the evidence** (commands, output, gate result) in the PR, per the
   root `AGENTS.md` Definition of Done.

Acknowledge the limit of dev qualification explicitly: **dev proves the
choreography, not prod-scale NEG/ILB behavior.** Dev runs 1-3 pods with low
WebSocket traffic, so it exercises the readiness/drain/reconnect sequence but
does **not** prove prod-scale NEG propagation, the prod 40-pod / fourteen-wave
rollout, or prod ILB connection draining. Those require the separate, later prod
proof gated on SCA-40 and a healthy pusher prod baseline.

---

## Follow-up deployment controls

SCA-115 completes the bounded follow-up to the native RollingUpdate hardening:
digest identity is selected from a completed dev rollout, promotion preserves
that exact manifest digest, and the production workflow gates the live cluster's
next surge capacity before changing the Pusher release. The existing rollback
contract remains a separate operator action; this workflow does not auto-roll
back traffic or data.
