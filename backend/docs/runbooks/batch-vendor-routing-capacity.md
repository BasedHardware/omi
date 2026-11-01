# Batch vendor routing: GPU floor, provider capacity and drills

Capacity side of all-vendor batch routing (slice E). Selection, health and the
provider stage are in `utils/batch_pipeline/vendor_route_contracts.py` and its
slices. This page covers what keeps routing alive when a vendor or the L4 pool
fails: the standing GPU floor, the `provider-stt` queue, the staging rate-limit
ladder, the failover drills and the guard interlocks. Numbers marked
**estimate** are modelled, not measured.

## Ownership

| Setting | Where | Owner | Rollback |
| --- | --- | --- | --- |
| GPU floor (HPA min and baseline) | `charts/batch-pipeline-worker/prod_omi_batch-pipeline-worker_values.yaml` `replicaCount` + `autoscaling.minReplicas` | lead, at a worker Helm roll | 3 |
| L4 node pool minimum | GKE `batch-pipeline-pool` (operator-managed, not in this repo) | lead / op1 | previous minimum |
| GPU floor share of routed units | route table `gpu_floor_percent`, cohort `batch-vendor-gpu-floor` | lead, runtime config (slice B) | 0 |
| `provider-stt` queue size | `deploy/ops/prod.yaml` `cloud_tasks.provider-stt` | lead, config-train | previous size |
| Vendor caps, breaker thresholds | route table `RouteConfig`, `BATCH_VENDOR_HEALTH_THRESHOLDS` | lead, runtime config (slice C) | builtin table |

All of these are config, not code constants. Changing one is a values or
config-train change, never a code change.

## GPU floor

David's requirement (11-01): keep GPUs even when a vendor is cheaper, because
Modulate has outages. Modulate had six hard or degraded events in six weeks;
L4 stockouts in us-central1 come weekly to biweekly and eventually hit every
zone. A stockout fails scale-up, but on-demand nodes already running are not
taken back. So the floor has to be standing before an outage. A floor that
waits to scale up when the vendor dies fails in exactly the window it is for.

- **Value: 4 on-demand L4 workers** (`g2-standard-8`), HPA min 4 / max 16,
  pinned to `batch-pipeline-pool` (OD). Spot never holds the floor: L4 Spot
  has billed above on-demand (N6, 10-26) and disappears in stockouts.
- **Cost (list):** 4 × $0.8536/h ≈ $82/day, about $20.5/day above the old
  floor of 3. The premium over sending those hours to Modulate depends on
  yield: about $17.8/GPU-day at today's 2.65 audio-h/GPU-h, falling to about
  $8 at 12 audio-h/GPU-h (estimate; vendorscope-ops section 2).
- **What it covers (estimate):** about 10% of supported-language audio at
  today's starved yield, about 45% at the 11–13 audio-h/GPU-h target. Fresh
  and recent work is served during a full Modulate outage, and deep work waits
  with its audio retained. A 4h outage leaves about 232 audio-h of backlog,
  which drains in about 2h after the vendor recovers.
- **Node pool:** the GKE pool minimum must be at least the floor, with no
  zone policy that strands it (ANY across a/b/c). Before the first worker roll
  that carries floor 4, confirm at least 4 Ready on-demand nodes. On 11-01 the
  pool had 5 Ready nodes while a/b/c were stocked out, so floor 4 fits without
  any scale-up.
- **Changing it:** edit `replicaCount` and `autoscaling.minReplicas` together
  (a chart test pins them equal). The Helm lookup keeps the live replica count
  on upgrades, so the HPA minimum is the floor that binds. Options from the ops
  scope: 2 (fresh only, about $41/day), 4 (recommended), 9 (full supported
  coverage only after the yield fix, about $184/day).
- **Floor share:** the floor is warm only if traffic reaches it. The route
  table's `gpu_floor_percent` sends a stable owner-hash share (cohort
  `batch-vendor-gpu-floor`, its own salt) GPU-first wherever Parakeet can
  serve, whatever the price. Recommended 10–15% once vendor routing has
  any percent. With the builtin table every capable unit is GPU-first anyway.
- **Scale-in:** HPA floor 4, max 16, scale-down 1 pod / 120s after a 300s
  window. Lease fences make scale-in safe mid-queue; never drain the floor by
  hand during an outage.

## provider-stt queue

The C3/C8 transport PR (#24222) creates `provider-stt` at 48 concurrent / 10
per second. Today the handler is synchronous: one dispatch holds one
backend-integration request for the whole vendor call (Modulate client
timeout 300s, `attempts=2`).

Throughput is `min(max_dispatches_per_second, max_concurrent_dispatches / L)`,
where L is the vendor call latency per unit. **L is unmeasured.** Size from
the staging ladder below, then set:

- `max_dispatches_per_second` ≥ 2 × peak unit rate, and no higher than the
  measured vendor rate limit. The queue rate is also what throttles a redrive
  burst after an outage, when every `vendor_held` unit becomes due at once.
- `max_concurrent_dispatches` ≈ 2 × peak unit rate × L p95.

Peak rate by step (estimate: about 205k builtin provider units/day at 100%
batch, plus the vendor-routed share of about 672k supported units/day, less a
15% GPU floor share at 100%; peak = 2 × mean). The ops scope's 12–16/s counted
supported units only.

| Vendor routing | Units/day | Peak/s | Dispatch/s | Concurrency at L = 3 / 5 / 10 / 20 s |
| --- | ---: | ---: | ---: | --- |
| 0–1% (builtin, draining) | ~212k | ~5 | 10 (as created) | 30 / 50 / 100 / 200 |
| 5% | ~239k | ~5.5 | 12 | 33 / 55 / 110 / 220 |
| 25% | ~373k | ~8.6 | 18 | 52 / 86 / 172 / 344 |
| 100% | ~776k | ~18 | 36 | 108 / 180 / 360 / 720 |

48/10 holds through 1% if L ≤ about 5s. Resize before 25% using the measured
L. The handler runs the delivery on the shared `sync` executor (16 threads per
instance), so one backend-integration instance holds at most 16 vendor calls
at once. Its cap of 50 instances (concurrency 40) gives 800 threads, shared
with other integration work. At 100% and L = 10s, 360 held calls need about
23 instances, roughly 45 vCPU or $100/day of Cloud Run time (estimate). That
is about the size of the vendor bill for the same traffic. If the measured L
p95 is above about 5s, the stage needs async submit-and-poll before 25%. That
is slice D's change, not a bigger queue. Alarm on queue age p95 over 15 min,
never on depth; depth is unbounded by design.

Staging mirrors prod's queue (the mirror test enforces it), so every resize
lands in both files.

## Staging rate-limit ladder (vendor limits are unknown)

Neither vendor's rate limit is in our records. Find them on staging only,
never with a burst in prod.

1. Preconditions: staging `staging-provider-stt` queue exists; slice C's
   breaker is on in staging; synthetic 30s units (non-speech and speech
   fixtures, no user audio); a daily audio-hour cap on the staging route table
   sized to the ladder (about 2 audio-h per rung).
2. Rungs: 5 → 10 → 25 → 50 concurrent, each held 10 min, Modulate first, then
   Soniox (failover-only, $0.10/h list, so keep its rungs short).
3. Record per rung: 429 count and share, 5xx share, timeout share, L p50/p95,
   integration CPU s/unit, and vendor audio-seconds billed (from
   `omi_batch_pipeline_vendor_attempt_audio_seconds_total`).
4. Stop at the first rung with 429 ≥ 1% or 5xx ≥ 5% sustained 5 min, or when
   L p95 doubles from rung 1. The last clean rung is the measured ceiling.
5. Set the prod queue from section "provider-stt queue" at no more than 50% of
   the measured ceiling, and record the receipt beside the change.

Budget the window from the real ceiling of the staging tools (queue drain
rate, Job timeouts) before scheduling it.

## Failover drills

**Staging/sim (step 0, before any prod percent).** The pipeline sim runs
each case, and each must show zero 5xx, zero custody events, zero
paid-intent violations and no `failed_held` with a vendor cause:

| Case | Expect |
| --- | --- |
| Modulate down (5xx / timeout) | breaker opens; new units go to GPU where capable, Soniox once otherwise, else `vendor_held` |
| Modulate funds refusal (402) | route unhealthy on first refusal, page; no retries fan out |
| Soniox down while Modulate down | GPU-capable units take the ring; the rest are `vendor_held` with audio retained |
| All vendors down | only `vendor_held` and the GPU ring; nothing terminal |
| Recovery | half-open probe, close, auto-redrive drains holds at the queue rate |
| Late result after failover | merges once; the late token settles as superseded |
| L4 stockout (no scale-up) | floor of 4 keeps serving; HPA does not hammer scale-up |

**Prod drill (step 2, 1% cohort, lead-run, low peak).** Force the Modulate
breaker open for the cohort through slice C's thresholds config, hold for 30
min, then restore. Pass: shed to GPU/Soniox/`vendor_held` as above, zero
intake 5xx, zero T1 events, holds drained within 1h of close. A receipted real
outage counts as the drill for its step. Repeat at 25% at low peak.

## Guard interlocks (must hold before any provider traffic)

Lead ruling `d914f8` (11-01): **no legacy draining cohort and no provider
traffic in prod until F1 and F2 are fixed and adopted** in the observer. These
findings come from offline tests at 150k units against the observer's own
predicates:

- **F1 (T4, hard):** route proof is read only from GPU-worker logs
  (`event=batch_language_route surface=worker`). Provider units complete on
  Cloud Run and leave none, so each completed provider unit counts as
  `T4_completed_without_route_proof`. Fix: the provider stage emits a route
  proof at settle, and the observer reads it with the same scrutiny as worker
  proof.
- **F2 (T2, blind):** a provider-cause `failed_held` unit has no VAD receipt,
  so T2 can never be CLEAN. Fix: the provider stage logs its CPU Silero
  receipt, and the observer reads it.
- **F3 (T3 and the 2h backstop):** `vendor_held` units count as wedges and
  against ADR-0001's 2h backstop. Exclude them only while
  `is_vendor_policy_hold` holds (redrive due plus the stale grace), so a dead
  redrive still alerts.
- **F4 (in-cluster batch verdict):** `batch_pipeline_store.oldest()` skips
  only allowance holds and fails toward the oldest hold past 500 holds, so a
  large `vendor_held` population drives `uncommitted_job_age_over_30m`.

Provider units never enter `ready_for_capacity`, so they cannot buy GPUs
through the HPA. `vendor_held` units that reroute to the ring do.

## Rollout order

Follows vendorscope-ops section 5. Each step is one write to roll back.

0. Preconditions: #24222 queues live; slices A–D merged dormant; F1/F2
   adopted (above); staging drill table green; staging ladder receipt; floor 4
   live with at least 4 Ready OD nodes.
1. Shadow at the current batch percent: decisions counted, routing unchanged.
2. 1% vendor routing with floor share on, plus the prod drill.
3. 5% → 25% in lockstep with the batch and draining-cohort steps (vendor
   percent ≤ batch percent). Resize `provider-stt` from the measured L before
   25%.
4. 100%: daily caps armed, floor standing.

Rollback at any step: vendor routing percent → 0 (or the kill switch), which
serves the builtin table, today's routing. Units in flight finish on their
stamped route, and held units keep their audio.

## Plays

**Vendor outage.** Confirm the breaker state
(`omi_batch_pipeline_vendor_breaker_state`). Confirm no intake 5xx and no T1
events. On a funds refusal, page David (only he can top up; auto-reload is on).
Leave the floor alone. On close, watch `vendor_held` drain at the queue rate.

**L4 stockout.** The floor holds and scale-up fails. Do not delete or recreate
pool nodes, and do not lower the floor to free quota. Deep backlog is
tolerated; audio is durable while it waits. If the floor itself drops below 4
Ready (a node lost to maintenance), vendors carry the overflow; check that no
vendor is also unhealthy before expanding any percent.
