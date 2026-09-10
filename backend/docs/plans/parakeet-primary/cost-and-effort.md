# Economics and engineering estimate

Action class: read-only public pricing research and local arithmetic; no spend or paid benchmark incurred.
Evidence cutoff: 2026-09-10. USD; public list prices are not Omi contract prices.

## Public price snapshot

| Provider / mode | Price per audio hour | Qualification |
| --- | ---: | --- |
| Modulate English fast, batch / streaming | $0.025 / $0.050 | Match actual endpoint and features before using |
| Modulate multilingual, batch / streaming | $0.030 / $0.060 | Diarization listed as included; optional signals cost extra |
| Deepgram Nova-3 monolingual, batch / streaming | $0.258 / $0.288 | Streaming is promotional; published regular rate $0.462 |
| Deepgram Nova-3 multilingual, batch / streaming | $0.312 / $0.348 | Streaming is promotional; published regular rate $0.552 |
| Deepgram streaming diarization add-on | +$0.120 | Added where enabled; other add-ons separate |
| Self-hosted Parakeet | Not yet measured | No hosted per-minute model rate; include all serving and operating costs |

Sources fetched September 10: [Modulate pricing](https://www.modulate.ai/api-pricing) and [Deepgram pricing](https://deepgram.com/pricing). These are first-party rates; no competitor comparison claims used. Verify billing units, silence/channel charging, rounding, add-ons, minimum commitments and negotiated discounts against actual Omi invoices. Promotional rates have no established expiry in this snapshot; model both promotional and regular prices.

## Reproducible model

Use incoming unique audio hours H, Parakeet-eligible fraction e, attempted eligible fraction a, and fallback fractions fM/fD of attempted Parakeet hours. Track actual billed fallback hours, including retries and overlap, separately; they may exceed failed unique hours. Let vendor rate rV be the measured current mix, and rM/rD the feature-matched fallback rates. Compute each term by surface/language/feature stratum, then sum; rV is shorthand for that stratum-specific rate, not one global blended rate applied to ineligible traffic.

Monthly proposed cost = fleet fixed cost F + Parakeet variable cost v × H×e×a + Modulate billed hours × rM + Deepgram billed hours × rD + unattempted/ineligible vendor hours × rV + recurring incremental operations O.

Baseline = observed provider billed hours × actual rates + existing attributable ASR infrastructure/operations. Compare incremental cash cost as well as fully allocated total cost: the current Parakeet fleet already serves batch, so neither charging all its cost twice nor declaring shared GPU capacity free is valid. Include displaced batch capacity, minimum replicas, N+1 redundancy, CPU/RAM, GPU idle time, diarization, load balancing, network, storage, monitoring, duplicate shadow traffic and fallback quota reservation.

For a simplified all-eligible workload, one fallback at rate r, failure fraction f, no duplicate billing and total fixed cost F+O:

`break-even H = (F+O) / ((1-f)×r - v)`

Only valid when the denominator is positive and fleet size/capacity remain valid at H. Add backoff/retry overlap using measured billed hours, not a guessed percentage.

## Sensitivity calculation — assumptions, not measured savings

Assume F=$730/month (a hypothetical $1 per fleet-hour ×730, not a GPU quote), O=$0, v=$0.005/audio-hour, e=a=1, 5% Modulate overflow at $0.06/audio-hour, no duplicates, and baseline entirely Modulate multilingual streaming at $0.06. Then candidate cost is `730 + 0.008H`; baseline is `0.06H`.

| Unique audio hours/month | Vendor baseline | Parakeet + overflow | Difference (baseline minus candidate) |
| --- | ---: | ---: | ---: |
| 10,000 | $600 | $810 | −$210 |
| 50,000 | $3,000 | $1,130 | $1,870 |
| 100,000 | $6,000 | $1,530 | $4,470 |

Break-even is 14,038.46 hours/month. Doubling fixed cost to $1,460 raises it to 28,076.92 hours. Adding an illustrative $2,000/month operations allocation to the original case raises it to 52,500 hours. These are optimistic arithmetic scenarios, not claims that one fleet serves 100,000 hours: that volume averages 137 concurrent streams before peaks and redundancy. Fleet cost must be resized using the measured capacity curve; recompute every row after sizing.

For orientation, 10,000 hours at Deepgram's promotional monolingual base rate cost $2,880 before diarization. Comparing only to that rate would exaggerate savings if Omi already sends most hours to cheaper Modulate. Replacing Modulate is a harder cost gate than replacing Deepgram.

## Evidence needed for an investment decision

Collect a trailing 28-day finalized baseline by surface/language/provider: unique accepted audio, billed audio, fallback/retry overlap, concurrency p50/p95/p99/peak, session lengths, paid tier and explicit-provider exclusions. Join vendor invoices and GCP attributable costs over the same window; report missing attribution. Use no raw customer content.

Obtain a region/SKU-specific infrastructure quote and actual committed rates. Model any infrastructure commitment/true-up and credits separately from resource savings; privately refresh applicable contracts before claiming cash savings. Do not annualize a short promotional or partial billing window.

Proposed financial gate: ≥20% reduction in fully loaded cost for migrated hours at expected demand, with a non-negative incremental cash case and a downside case for 20% overflow plus N+1 capacity. If a resilience/quality benefit justifies higher cost, The approving owner must record that explicit tradeoff instead of calling it savings. Qualification spend proposal: ≤$500 external compute/API costs, no automatic purchases; revise from actual rate and runtime inputs before provisioning.

## Capacity-priced scenarios

Use the [capacity prescription](capacity-plan.md), not the earlier hypothetical $730 fleet, for capacity approval. Google's [accelerator-optimized price page](https://cloud.google.com/products/compute/pricing/accelerator-optimized) lists an on-demand `g2-standard-8` with one L4 at **$0.853624312/hour** in its default displayed pricing context (checked 2026-09-10). Confirm the intended region/currency/SKU in a saved quote before purchase; this is a public reference rate, not a negotiated or region-locked quote. The G2 VM price includes the accelerator; do not add a second GPU charge. At 730 hours, one node is **$623.15/month** before disks, network, management, observability, fallback and operations.

| Warm streaming fleet, held for 730 hours | Compute-only monthly reference | Boundary |
| --- | ---: | --- |
| 2 replicas | $1,246.29 | Proposed pilot floor; existing batch capacity is additional |
| 4 replicas | $2,492.58 | Proposed pilot ceiling; transient fifth surge node is additional |
| 8 replicas | $4,985.17 | Illustrative 100-peak cohort sizing |
| 21 replicas | $13,086.06 | Illustrative 300-peak cohort sizing |
| 40 replicas | $24,925.83 | Illustrative 600-peak cohort sizing |

These are constant-fleet references, not HPA forecasts. Recompute from actual hourly replica counts and incremental batch capacity. At 20 simultaneously productive streams per node, compute alone is $0.04268/audio-hour; at 10 it is $0.08536. Modulate multilingual streaming is $0.06 before optional extras, so low occupancy can erase savings even before redundancy and operating costs. At 25 streams, the compute-only break-even occupancy against $0.06 is 56.9%; relative to a planning target of 20 it is 71.1%. Reserve replicas and idle connected audio alter effective utilization. Billable audio must be reconciled to the invoice's silence/channel rules.

For a deliberately conservative example, a 600-peak/300-average workload with 40 nodes kept warm all month consumes 219,000 unique audio hours. At $0.06 the vendor baseline is $13,140; streaming compute alone is $24,925.83, already $11,785.83 higher. This does not rule out a cheaper demand-following fleet or better measured throughput; it rules out claiming savings from a raw per-GPU throughput figure. The prescribed ≥20% fully loaded savings gate must hold after failure reserve, batch separation, fallback and operations, or be replaced by an explicitly approved reliability/control premium.

## Capacity-inclusive effort prescription

Person-days; estimates, not commitments. Assumes experienced backend/ML/SRE support and available test hardware/data. Includes the split-service and scaling work absent from a provider-order-only estimate.

| Work package | Person-days | Deliverable |
| --- | ---: | --- |
| Serving/workload/billing baseline | 2–3 | Eligible demand with coverage, negotiated rate inputs kept private |
| Corpus and quality baseline | 4–6 | Held-out paired quality/latency/diarization report |
| Realtime/batch separation, GPU capacity and drain | 8–12 | Independent serving modes, readiness, node plan, N+1 and scheduling proof |
| Policy, Deepgram live callback and continuity | 5–8 | Both vendors reachable from Parakeet-primary, bounded replay and no duplicates |
| HPA/metric plumbing, release controls and observability | 4–7 | Offered/admitted pressure, budgeted cohorts, tested recovery |
| Integrated qualification and review | 3–6 | Quality + failure + cost packet |
| **Core total** | **26–42** | Approximately 6–9 working weeks for one effective engineer |

With two effective engineers and overlapping corpus/infrastructure work, budget 4–6 calendar weeks plus external data/quota/approval waits. Add 20–30% contingency (roughly 32–55 person-days total). Critical path is corpus/model viability → safe per-pod capacity → infrastructure/unit economics → integrated failover/drain qualification → explicit rollout decision.

Optional scope: 2–4 person-days to policy-admit/integrate existing Deepgram batch helpers; 3–6 for a new Deepgram PTT adapter; 5–10 for a multilingual/punctuated realtime feasibility spike, with implementation re-estimated afterward. Multi-channel failover remains a separate unsized design until its contract is agreed. Production observation time is additional.
