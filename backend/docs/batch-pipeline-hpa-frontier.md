# Batch worker HPA retune frontier (2026-11-03)

The 40/0.6 retune in #24481 was reverted by #24493 before cluster apply: it
starved 35 minutes in the existing 24h max-of-two replay. This replacement uses
**41 ready units / 0.56 chain wall seconds per second**, preserving min 4/max 16,
1800s scale-down stabilization and one pod per 600s. Existing replay files and
assertions remain unchanged. Chart tests retain exact target assertions, updated
to 41/0.56 and the latent balanced-mode doubles 82/1.12.

## What the models establish

- **Current-volume fixture:** the 181-minute historical 25% aggregate window
  ending 2026-11-02 02:41Z. The adapter serves deduplicated fleet-summed 10m
  `worker_flight` rates; the fixture's `_per_pod` suffix does not mean an
  individual pod's demand. Hot means fleet 5m demand exceeds 0.85 times replicas.
- **Full-volume sensitivity:** multiply that fixture's fleet totals by 3.7,
  preserving epochs and missing samples. This is a linear model, not an
  observed full-volume run or a production latency measurement.
- **Older 24h fixture:** the separate measured window ending 2026-11-01 15:53Z,
  interpolated to 1436 controller minutes. Zero starvation means replicas times
  its measured 0.56 per-worker ceiling cover demand. Its traffic fraction is
  unspecified; it cannot be called measured full-volume qualification.

The new targets produce current mean/max **4.343/5**, zero hot minutes, and the
floor appears. The synthetic full-volume result is **11.459/16**, six hot
minutes (within the lead's prior seven-minute budget). The older 24h result is
**6.371/15**, zero starvation, and backlog dominance holds. Current step wait is
3.355 minutes with catch-up in 10; synthetic full-volume step wait is 4.302
minutes with catch-up in 20. These model results do not predict that the
production 8.1-pod daily average will become 4.34.

## Bounded search and frontier

Reproduce from the repository root (offline numerical model evaluation):

```bash
backend/.venv/bin/python backend/scripts/batch_pipeline_hpa_frontier.py \
  --grid all --output /Volumes/Ephemeral/scratch/hpa-retune-v2-frontier.json
```

The coarse grid has ready targets 16..64 by 4, chain targets
0.45/0.48/0.50/0.52/0.54/0.55/0.56/0.57/0.58/0.60/0.65/0.70/0.80,
and stabilization 60/300/600/900/1200/1800/2400/3600 seconds. The refinement
has ready targets 36..44 by 1, chain targets
0.550/0.555/0.560/0.561/0.565/0.570, and stabilization 60..1800 by 60.
The union contains 2,918 distinct configurations. This is a bounded grid,
not a proof of a global optimum over continuous targets. The ranking minimizes
current mean, then synthetic full mean, then older 24h mean.

All rows use one pod per 600s unless specified. Mean/max pairs are replicas.

| Ready / chain / stabilization | Current mean/max; hot min | Synthetic full mean/max; hot min | Older 24h mean/max; starved min | Disposition |
|---|---|---|---|---|
| 32 / 0.5 / 1800 | 4.878/6; 0 | 11.790/16; 5 | 7.198/16; 0 | Reverted-main baseline |
| 40 / 0.6 / 1800 | 4.343/5; 0 | 10.994/16; 7 | 6.306/16; 35 | Rejected: unchanged starvation assertion |
| 41 / 0.56 / 60 | 4.050/5; 0 | 10.326/16; 9 | 5.552/15; 0 | Lowest current mean found; full hot budget exceeded; short window unqualified |
| 41 / 0.555 / 780 | 4.116/5; 0 | 10.829/16; 6 | 6.006/15; 0 | Lower-current-mean sensitivity; short window unqualified |
| 41 / 0.56 / 1320 | 4.166/5; 0 | 11.254/16; 6 | 6.211/15; 0 | Short window unqualified |
| **41 / 0.56 / 1800** | **4.343/5; 0** | **11.459/16; 6** | **6.371/15; 0** | **Chosen with stockout protection and full hot budget retained** |

At the chosen occupancy target, ready 41 is the last integer target passing the
unchanged sustained-step wait bound: ready 42 gives 3.914 minutes, exceeding
2.795 + 1. Occupancy 0.561 already produces starved minutes. Larger targets
cannot be justified by low ASR duty: `worker_flight` includes host serial work
and executor wait. The pump acquires its GPU slot before the timer, so its
second pipeline lane does not double-count slot wait. Worker processes remain
one pending the g2-standard-8 L4 throughput, cgroup-memory, and 24h soak gate.

### Why the numerical minimum is not the shipped setting

The older max replay has two downscale fidelity defects: its allowance permits
one pod down every 60s despite a 600s policy, and it omits recommendations equal
to the current count from stabilization history. It also omits controller
10% tolerance. The three-hour replay enforces the 600s period and tolerance,
but neither historical fixture establishes future L4 stockout recoverability.
Thus lower-window results are reported as candidates, not stockout qualification.
The existing 1800s chart assertion and policy are retained. No existing replay
engine or acceptance assertion was altered to make a candidate pass.

Policy sensitivity at ready41/chain0.56/window60 gives identical current
mean/max 4.050/5, with zero hot minutes. Synthetic full mean/hot results are:
1/60s = 8.552/11, 1/300s = 9.663/10, 1/600s = 10.326/9,
1/1200s = 10.475/8, 2/600s = 9.547/10. The 1/1200s case also fails
shed-from-12. Faster policies exceed the prior full hot budget and are not
qualified by the unchanged policy tests. None is shipped.

## Full-volume capacity limit and staged apply

Peak synthetic 5m demand is 14.998 chain seconds/second. Sixteen pods supply
13.6 at the 0.85 hot line; **18 are necessary** at that threshold, even before
provisioning delay. No target/window combination can give zero hot minutes at
that peak with max16. At the separate 0.93 measured ceiling even 17 are needed.
A capacity bound is not proof that raising the ceiling alone guarantees zero
hot minutes. The mathematical full-volume zero-hot goal is unresolved; do not
expand traffic based on this PR.

The lead applies at current volume only. First confirm pending timeliness
rules and both composite indexes are active/READY per
[the projection runbook](../charts/monitoring/batch-projection/README.md).
Capture private live values/manifest/image; reconcile any min6/max12 overrides
against the ruling min4/max16. Render the merged chart with production values,
keep the worker image, runtime bindings, profiling-on and 1500s drain intact,
and inspect the two targets, min/max, OD placement and downscale behavior before
Helm upgrade. The adapter is unchanged; compare privately captured live rules
using `backend/scripts/diff_prod_adapter.py` rather than redeploying it.

Watch one complete shed cycle plus 24h: useful completed audio per pod-hour,
throughput and admission-to-terminal timeliness, pending age, pull backoff,
and T3/hard-3 signals. Historical fresh-history shedding from 12 to 5 within
60 minutes is a test result; live retained recommendations can delay the cycle.
ADR-0001's T3 age floors are >900s obligation / >1800s job, with the cohort
freeze/rollback rules stated there. Its hard-3 backstops are p95 >30 minutes for
30 minutes, any admitted unit 2h without terminal state, and >5% wedged for 30
minutes with >=20 admitted. The in-cluster guard currently trips custody/proven
speech loss and treats wedges/latency as alert-only; the lead must confirm the
separate observer and response authority, not assume automatic hard-3 rollback.

Roll back on timeliness/throughput/T3 regression to targets 32/0.5, keeping
min4/max16, window1800 and 1/600s, e.g. on the same reviewed Helm upgrade command:
`--set autoscaling.targetQueuedUnitsPerWorker=32 --set-string autoscaling.targetChainBusyPerWorker=0.5`.
Alternatively restore the captured known-good release after inspecting its
values/image. The adapter need not change. Before streaming retirement doubles
batch volume, the lead decides whether to qualify maxReplicas above16; this PR
does not raise it. No cluster access or production changes were made here.
