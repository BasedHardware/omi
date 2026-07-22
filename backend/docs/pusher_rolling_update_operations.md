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
  --set image.tag=<immutable-tag> > /tmp/pusher-dev.yaml

helm template pusher backend/charts/pusher \
  -f backend/charts/pusher/prod_omi_pusher_values.yaml \
  --set image.tag=<immutable-tag> > /tmp/pusher-prod.yaml
```

Confirm in the rendered output: `readinessProbe.httpGet.path: /ready`,
`livenessProbe`/`startupProbe` on `/health`, the BackendConfig `healthCheck` on
`/health` plus `connectionDraining`, `preStop` calling `/__internal/drain`, and
`progressDeadlineSeconds: 9600`.

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

### 3. Deploy the immutable tag

Deploy the exact short-SHA image tag. Never deploy `latest`, and never let a
chart-only deploy reset the workload to `latest` (per `.github/AGENTS.md`). The
deploy workflow must wait for rollout completion with
`kubectl rollout status deploy/<env>-omi-pusher --timeout=...` and fail on
timeout.

### 4. Rollback

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

1. **Render and preflight** exactly as in the
   [Operator runbook](#operator-runbook), against the dev values and the dev
   immutable tag.
2. **Exercise the choreography under synthetic load.** Use privacy-safe
   synthetic pusher capability checks that reuse the existing LLM-gateway smoke
   precedent (the family that validates a ready Kubernetes workload, its
   ingress/ILB attachment, and a Cloud Run VPC smoke route via
   `backend/scripts/verify-llm-gateway-serving.py` and
   `probe-llm-gateway-from-cloud-run.sh`). The pusher equivalents must open a
   WebSocket session, confirm `/ready` flips to 503 on drain, confirm new
   connections go to a healthy pod, and confirm background finalization
   completes inside the grace window — without using real user data.
3. **Hold the minimum capability/session counts and bounded error/latency
   thresholds** from [Rollout quality gates (fail-closed)](#rollout-quality-gates-fail-closed).
   Dev must serve the minimum session/capability counts, not just run for an
   elapsed time.
4. **Record the evidence** (commands, output, gate result) in the PR, per the
   root `AGENTS.md` Definition of Done.

Acknowledge the limit of dev qualification explicitly: **dev proves the
choreography, not prod-scale NEG/ILB behavior.** Dev runs 1-3 pods with low
WebSocket traffic, so it exercises the readiness/drain/reconnect sequence but
does **not** prove prod-scale NEG propagation, the prod 40-pod / fourteen-wave
rollout, or prod ILB connection draining. Those require the separate, later prod
proof gated on SCA-40 and a healthy pusher prod baseline.

---

## Relationship to SCA-40

This hardening is deliberately scoped to **native `RollingUpdate` availability**
and does not duplicate SCA-40's work. SCA-40 owns and is still building:

- **Digest chart support** (`image.digest` / `@sha256`) so a rollout pins an
  immutable image by content digest, not just a mutable tag.
- **Chart-only / reuse-image deploy mode** so a chart change can be applied
  without rebuilding or re-pushing the image.
- The immediate **`REDIS_DB_HOST` recovery preflight.**
- **Rollback evidence** recording.

Consequences for this document:

- This PR does **not** add an `image.digest` chart field, a digest-promotion
  pipeline, a chart-only deploy mode, or a rollback-evidence recorder.
- Build-once **digest promotion** (deploying the same built image across stages by
  digest) is deferred to stack on SCA-40; it is out of scope here.
- The rollback described in the [Operator runbook](#operator-runbook) is
  re-pointing the chart at the prior immutable **tag**, which is safe by the
  N/N-1 contract. Digest-pinned rollback and recorded rollback evidence arrive
  with SCA-40.

In short: this hardening makes the native rolling update honest and bounded;
SCA-40 makes image identity and rollback evidence durable.
