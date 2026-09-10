# Capacity scaling prescription

Draft, 2026-09-10. No values in this plan have been applied. Numbers marked provisional are qualification targets, not certified capacity.

## Fleet ownership

The streaming release applies `prod_omi_parakeet_stream_values.yaml` after the
production base values (and the equivalent dev overlay). It uses a separate
service, internal load balancer and labeled GPU node pool. `serviceMode: stream`
loads one TDT v3 instance, VAD and speaker dependencies without a second batch model; the existing batch release
uses `serviceMode: batch`. One process owns one GPU and its admission limit.

Stream readiness includes actual model warmup, and draining removes readiness
and rejects new leases. The `parakeet_stream_demand` Pods metric combines active
streams with capacity-full admission pressure over one minute. It is exposed
through the existing cluster Prometheus adapter. HPA also observes active
streams. Missing series remain absent; never replace them with zero.

Use one dedicated L4 on `g2-standard-8` per replica. No GPU sharing or Spot-only
primary capacity is introduced. Batch and realtime use independent capacity,
so batch VRAM spikes cannot consume a streaming pod's resources. Revisit
co-location only with an enforceable reservation scheduler and measured benefit.

## Sizing contract and initial values

Let `c` be measured hard admissible live streams/pod while all benchmark gates pass, `q` the operating target below `c`, and `P` the peak eligible single-channel live concurrency for the approved cohort. PTT is sized separately if sharing the realtime pool; add its concurrent resource demand before using this formula.

Provisional `c=25`, `q=20`. Require `q <= 0.8c` and enough measured VRAM/CPU/latency headroom. Adopt lower values if needed; higher values require a new measured capacity report. Then:

`N_peak = max(2, ceil(1.30 × P / q) + 1)`

The extra replica covers one pod loss; the 30% factor covers demand uncertainty. They are intentionally separate. This assumes usable load distribution: per-pod skew must pass the admission/rebalance/fallback tests. With `N` warmed replicas, cohort peak must stay at or below `(N-1)×q/1.30`. Hard admission is still per pod; aggregate spare slots do not ensure a new connection lands on one.

| Illustrative eligible peak P | Warm streaming replicas at q=20 | Interpretation |
| --- | ---: | --- |
| 10 | 2 | Initial small pilot |
| 40 | 4 | Pilot ceiling supports about 46 peak streams with the stated reserve |
| 100 | 8 | Requires explicit fleet/quota increase |
| 300 | 21 | Material fleet and cost decision |
| 600 | 40 | Stress-sizing example, not an observed eligible workload |

The checked-in production floor is 40 and ceiling is 60. The development
floor/ceiling is 2/4. Streaming node-pool total capacity must reach 61/5,
respectively, to accommodate one rolling-update surge node. The 600-stream
production value is a conservative planning envelope, not a published live
customer measurement. Measure combined live and PTT pressure before promotion.
Excess per-pod admissions fall through to vendors instead of an unbounded queue.

Maintain `N_peak` warm for the peak interval. Off-peak downscaling is allowed only after verifying sufficient ready reserve throughout measured node/model startup time. Measure metric propagation + HPA reaction + node provisioning + image/model download + warmup as one distribution. Prewarm ahead of predictable peaks; cover unpredictable arrivals during that interval with ready spare capacity and vendor overflow. Do not count Pending/Starting pods as available.

Before fleet purchase/activation, collect a complete 28-day, at-most-one-minute-resolution eligible-demand series with coverage and scrape health. Export surface/language/feature/cohort dimensions with bounded labels. All-listener WebSocket count is only a rough envelope: it includes ineligible/custom paths, excludes some PTT work, and does not equal active voiced inference load. A sparse five-minute sampled maximum is a lower bound, not a peak capacity certificate. Do not extrapolate present Parakeet overflow traffic into primary demand.

## Autoscaling and infrastructure changes

- Streaming HPA primary: per-pod `parakeet_active_streams`, provisional target 20. Before capacity-dependent routing, require an implemented and verified offered-eligible-load/admission-rejection signal with bounded cardinality, a tested scale-up response, and explicit behavior on metric loss; these are mandatory acceptance criteria. Include this pressure as a separate bounded signal: admitted streams plateau at the cap and can hide demand. Keep GPU/VRAM and latency as guardrails; CPU alone is insufficient. Batch scales against its own queue age/active jobs and completion SLO.
- The stream overlays allow two additional pods per 60 seconds with no scale-up stabilization delay; the warm floor covers the planning peak while nodes start. Qualify that rate against measured provisioning and arrival bursts. Preserve at least 600-second scale-down stabilization and limit removal to one fully drained pod per interval.
- Existing HPA/metric plumbing should be extended through the cluster's owning adapter contract. Verify metric values match pod gauges, invalid/missing metrics surface as unhealthy, HPA conditions are healthy and desired replicas are schedulable. Do not deploy a competing cluster-wide adapter as a shortcut.
- Node-pool capacity must support streaming HPA maximum **plus one surge GPU**, independently of batch reservations. Check regional and per-zone L4 quota, actual stock/reservations, driver compatibility, node labels/taints, IP/CPU/RAM limits and cluster-autoscaler ceilings. Distinguish per-zone min/max settings from total fleet counts. A configured quota is not a promise of available hardware.
- Change rolling update to `maxUnavailable: 0`, `maxSurge: 1`, with surge node capacity already schedulable. For the two-replica pilot, use a PDB with `minAvailable: 2`; voluntary eviction therefore waits for a third ready replica or an explicitly reviewed maintenance plan. For larger stages, set `minAvailable: max(2, N_peak-1)` from the approved stage budget, and reconcile it with the HPA floor before reducing replicas. HPA scale-down and rollout strategy still need their own safety checks; a PDB does not govern every termination path.
- Require hostname anti-affinity (at most one streaming replica per node) for every approved replica count, including surge, after scheduling proof; otherwise one node loss can remove multiple replicas and invalidate the N+1 formula. Use preferred zone spreading initially, record its actual placement, and do not claim zone-failure tolerance. To require zone resilience, qualify cross-zone placement and replace the single-pod-loss sizing term with loss of the largest zone. Hard zone constraints without available GPUs can prevent scheduling.

Kubernetes describes [HPA behavior and missing metrics](https://kubernetes.io/docs/tasks/run-application/horizontal-pod-autoscale/) and [PDB limits](https://kubernetes.io/docs/concepts/workloads/pods/disruptions/). Google's [GPU autoscaling guidance](https://docs.cloud.google.com/kubernetes-engine/docs/best-practices/machine-learning/inference/autoscaling) supports workload-specific pressure metrics over CPU-only scaling; applying that principle to active STT streams is this plan's inference, not a published Parakeet capacity guarantee.

## Drain, recovery and acceptance

The stream chart invokes the loopback-only drain endpoint, waits 30 seconds,
and allows 105 seconds total termination grace. New sessions are refused while
existing leases drain; Uvicorn graceful shutdown is bounded to 30 seconds and final flush to five seconds. The total grace includes the preStop request/wait, server handler shutdown, admission drain and a margin. Arbitrarily long
sessions cannot finish naturally inside this interval and must exercise the
listener's vendor failover path. Measure readiness/LB propagation and transcript
continuity during real rolling termination; a preStop delay alone is not proof.

Acceptance must include multi-listener sessions distributed across replicas; loss of one pod; full node failure; cold replacement; voluntary rollout; blocked GPU scheduling; metric-adapter failure; quota exhaustion; partial deploy recovery; leaked leases; vendor quota exhaustion; and batch/stream isolation. Assert transcript completeness, deduplication, speaker/timestamp continuity, fallback reason telemetry and sustainable latency through these failures. A PDB cannot prevent involuntary hardware loss.

Update implementation-owned contracts together: `backend/parakeet/` startup/drain; `backend/charts/parakeet/`; monitoring adapter values; `backend/deploy/runtime_env/_base.yaml` and generated `runtime_env.yaml`; `backend/scripts/deploy_parakeet_stream.py` and `backend/scripts/parakeet_stream_contract.py`; service-specific backend URLs; admission/Helm/runtime-env unit tests; existing GPU container tests; [capacity runbook](../../runbooks/parakeet-stream-capacity.md). These contracts are changed together in this implementation PR. No production rollout has been executed by the preparation task.

## Go/no-go prescription

Proceed to engineering qualification with the isolated architecture. Do not approve broad primary routing until eligible demand, warm capacity including failure reserve, provider fallback quota, tested drain/recovery and fully loaded unit economics are known. If the fleet needed at measured throughput is uneconomic, first improve the realtime model/runtime or narrow eligibility; retain vendor-primary rather than raising admission caps or spending on an unqualified fleet.
