# Capacity scaling prescription

Draft, 2026-09-10. No values in this plan have been applied. Numbers marked provisional are qualification targets, not certified capacity.

## Why scaling is a first-class implementation slice

The [production values](../../../charts/parakeet/prod_omi_parakeet_values.yaml) at the plan's source baseline declare one GPU/pod, HPA min 1/max 2, active-request target 20 and GPU target 70%, scale-up limited to one pod/300 seconds, scale-down stabilization 600 seconds, and rolling updates with one unavailable/zero surge. These are source declarations, not a live inventory. A larger node pool alone cannot overcome a two-pod HPA ceiling; increasing that ceiling alone cannot create GPU quota, ready nodes or warmed model replicas.

The [startup](../../../parakeet/main.py) initializes a batch GPU worker/engine and RNNT decoder together. Batch and stream admission are separate but share GPU resources. Stream admission is a process-local owner at the one-process, one-GPU pod boundary, not a listener-local limit. Preserve those assumptions; multiple Uvicorn workers could multiply the limit.

The [HPA template](../../../charts/parakeet/templates/hpa.yaml) supports a stream gauge, but production values currently use total active requests. Custom metric rules under the chart are not proof that the cluster-wide adapter serves them. Verify custom/external metrics and HPA conditions end to end before enabling scale-dependent traffic. A missing metric must not be treated as zero load.

## Chosen architecture

**Separate realtime and batch deployments/services, initially on separate labeled GPU capacity.** Reuse the current image/build lineage, with explicit serving modes that load only required models and expose only the matching endpoints. A realtime replica loads RNNT, VAD and speaker dependencies; a batch replica loads TDT and required batch diarization. Give each service independent readiness, admission/queue limits, HPA, dashboards and endpoint configuration. Retain the batch service and its validated capacity during migration.

This requires startup/endpoint-gating code, chart/release wiring and separate backend endpoint selection. It is not an existing env-only switch. Fail startup on contradictory mode/model configuration. Prove streaming readiness with decoder/diarizer warmup, not merely a batch GPU-worker-ready flag. Avoid duplicating unrelated business logic across services.

Reason: realtime peak latency should not depend on batch queue occupancy, large-file VRAM spikes or batch rollout. Splitting costs a warm redundant streaming floor; include that expense rather than promising that existing idle batch GPU is free. Revisit co-location only if a measured scheduler with enforceable reservations can preserve both SLOs and improve cost.

Start with one dedicated L4 and one process per `g2-standard-8` replica. Do not introduce time-slicing/MPS or Spot-only primary capacity in the first release. Batch opportunistic capacity is a later cost option, with tested retry and queue durability. A larger accelerator is not prescribed until L4 qualification identifies the actual bottleneck.

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

Recommended isolated qualification: two streaming replicas; one failure must leave capacity for the small test cohort. Recommended approved pilot: min 2/max 4 streaming replicas, no batch removal. Stage traffic by absolute concurrency as well as percentage. Exceeding the cohort budget routes new eligible sessions to vendors; it must not create an unbounded GPU waiting room.

Maintain `N_peak` warm for the peak interval. Off-peak downscaling is allowed only after verifying sufficient ready reserve throughout measured node/model startup time. Measure metric propagation + HPA reaction + node provisioning + image/model download + warmup as one distribution. Prewarm ahead of predictable peaks; cover unpredictable arrivals during that interval with ready spare capacity and vendor overflow. Do not count Pending/Starting pods as available.

Before fleet purchase/activation, collect a complete 28-day, at-most-one-minute-resolution eligible-demand series with coverage and scrape health. Export surface/language/feature/cohort dimensions with bounded labels. All-listener WebSocket count is only a rough envelope: it includes ineligible/custom paths, excludes some PTT work, and does not equal active voiced inference load. A sparse five-minute sampled maximum is a lower bound, not a peak capacity certificate. Do not extrapolate present Parakeet overflow traffic into primary demand.

## Autoscaling and infrastructure changes

- Streaming HPA primary: per-pod `parakeet_active_streams`, provisional target 20. Before capacity-dependent routing, require an implemented and verified offered-eligible-load/admission-rejection signal with bounded cardinality, a tested scale-up response, and explicit behavior on metric loss; these are mandatory acceptance criteria. Include this pressure as a separate bounded signal: admitted streams plateau at the cap and can hide demand. Keep GPU/VRAM and latency as guardrails; CPU alone is insufficient. Batch scales against its own queue age/active jobs and completion SLO.
- Propose scale-up of at most two pods/60 seconds for the pilot, no stabilization delay, max four; qualify that behavior against measured scheduling/warmup before using it. For larger fleets, review bounded percentage-based scaling from observed arrivals, not this pilot setting. Preserve at least 600-second scale-down stabilization and limit removal to one fully drained pod per interval.
- Existing HPA/metric plumbing should be extended through the cluster's owning adapter contract. Verify metric values match pod gauges, invalid/missing metrics surface as unhealthy, HPA conditions are healthy and desired replicas are schedulable. Do not deploy a competing cluster-wide adapter as a shortcut.
- Node-pool capacity must support streaming HPA maximum **plus one surge GPU**, independently of batch reservations. Check regional and per-zone L4 quota, actual stock/reservations, driver compatibility, node labels/taints, IP/CPU/RAM limits and cluster-autoscaler ceilings. Distinguish per-zone min/max settings from total fleet counts. A configured quota is not a promise of available hardware.
- Change rolling update to `maxUnavailable: 0`, `maxSurge: 1`, with surge node capacity already schedulable. For the two-replica pilot, use a PDB with `minAvailable: 2`; voluntary eviction therefore waits for a third ready replica or an explicitly reviewed maintenance plan. For larger stages, set `minAvailable: max(2, N_peak-1)` from the approved stage budget, and reconcile it with the HPA floor before reducing replicas. HPA scale-down and rollout strategy still need their own safety checks; a PDB does not govern every termination path.
- Require hostname anti-affinity (at most one streaming replica per node) for every approved replica count, including surge, after scheduling proof; otherwise one node loss can remove multiple replicas and invalidate the N+1 formula. Use preferred zone spreading initially, record its actual placement, and do not claim zone-failure tolerance. To require zone resilience, qualify cross-zone placement and replace the single-pod-loss sizing term with loss of the largest zone. Hard zone constraints without available GPUs can prevent scheduling.

Kubernetes describes [HPA behavior and missing metrics](https://kubernetes.io/docs/tasks/run-application/horizontal-pod-autoscale/) and [PDB limits](https://kubernetes.io/docs/concepts/workloads/pods/disruptions/). Google's [GPU autoscaling guidance](https://docs.cloud.google.com/kubernetes-engine/docs/best-practices/machine-learning/inference/autoscaling) supports workload-specific pressure metrics over CPU-only scaling; applying that principle to active STT streams is this plan's inference, not a published Parakeet capacity guarantee.

## Drain, recovery and acceptance

Current chart has no explicit stream-drain coordinator/preStop hook. BackendConfig source declares 130-second connection draining and pod termination 150 seconds; neither guarantees completion of arbitrarily long sessions. Implement an explicit draining state that refuses new sessions, removes readiness, allows a bounded finalization interval, and triggers tested listener fallback/reconnect for remaining streams. Synchronize readiness removal, load-balancer propagation, final-audio replay and process exit. Measure the real propagation delays before fixing a deadline; do not rely on a blind sleep.

Acceptance must include multi-listener sessions distributed across replicas; loss of one pod; full node failure; cold replacement; voluntary rollout; blocked GPU scheduling; metric-adapter failure; quota exhaustion; partial deploy recovery; leaked leases; vendor quota exhaustion; and batch/stream isolation. Assert transcript completeness, deduplication, speaker/timestamp continuity, fallback reason telemetry and sustainable latency through these failures. A PDB cannot prevent involuntary hardware loss.

Update implementation-owned contracts together: `backend/parakeet/` startup/drain; `backend/charts/parakeet/`; monitoring adapter values; `backend/deploy/runtime_env/_base.yaml` and generated `runtime_env.yaml`; `backend/scripts/runtime_env_parakeet_contract.py`; service-specific backend URLs; admission/Helm/runtime-env unit tests; existing GPU container tests; [capacity runbook](../../runbooks/parakeet-stream-capacity.md). No chart, node-pool or runtime value is changed in this design PR.

## Go/no-go prescription

Proceed to engineering qualification with the isolated architecture. Do not approve broad primary routing until eligible demand, warm capacity including failure reserve, provider fallback quota, tested drain/recovery and fully loaded unit economics are known. If the fleet needed at measured throughput is uneconomic, first improve the realtime model/runtime or narrow eligibility; retain vendor-primary rather than raising admission caps or spending on an unqualified fleet.
