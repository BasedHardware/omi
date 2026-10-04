# Backfill memory-only rollout

Draft build, 2026-10-04. No production changes. Review and observability acceptance precede rollout through the existing backend deploy workflow. Only `.github/actions/sync-backfill-lifecycle/action.yml` changes the worker limit: **8 → 4 GiB**. Keep 2 vCPU, concurrency 3, revision min/max 3/18, service max 18 and request-based CPU. Queue settings stay 40 concurrent / 10 per second.

The coordinator's aggregate `cost-opps/evidence/backend-sync-backfill-container-memory-utilizations.json` records daily merged memory-utilization histograms at an 8-GiB allocation. Highest nonempty linear bucket upper bound = bucket index × 0.01 × 8 GiB. The source distribution is sampled; this is neither exact peak RSS nor proof against transient OOM.

| UTC day | Mean GiB | p99 bucket upper GiB | Highest bucket upper GiB |
| --- | ---: | ---: | ---: |
| Sep 24 | 0.726 | 0.88 | 1.20 |
| Sep 25 | 0.706 | 0.88 | 1.12 |
| Sep 26 | 0.674 | 0.88 | 1.36 |
| Sep 27 | 0.722 | 0.88 | 0.96 |
| Sep 28 | 0.708 | 0.88 | 0.96 |
| Sep 29 | 0.682 | 0.88 | 1.20 |
| Sep 30 | 0.741 | 0.96 | 1.04 |
| Oct 1 | 0.719 | 0.96 | **1.76** |
| Oct 2 | 0.732 | 0.96 | 1.12 |
| Oct 3 | 0.748 | 0.96 | 1.12 |

The full-range headroom calculation was run against every nonempty bucket in the supplied JSON. With the 1.76-GiB upper bucket, a 2-GiB allocation has **0.24 GiB / 12%** remaining; reject it because decode/PCM copies, downloads and memory-backed temp files can briefly exceed samples. 4 GiB leaves **2.24 GiB / 56%**. This is an evidence calculation, not a customer-audio replay or synthetic load-test result. No user content was read.

Gross active-memory saving: `4 GiB × $0.0000025/GiB-s × 3600 × (180.8–269.1 billed hours/day) × 30` = **$195–291/month**, plus possible idle saving. Credits/commitments reduce cash savings; concurrency/minimum changes overlap. [Cloud Run list rates](https://cloud.google.com/run/pricing).

After review, establish a day of phase/request/queue/memory baseline, deploy the memory-only setting through the normal path, and compare at least 24 hours. Reject any memory termination/restart or increased retries, and investigate persistent >10% p95 job-latency/queue-age regression. Aggregate metrics must cover the worker; absent metrics cannot count as a pass. Rollback to 8 GiB or previous serving revision through the normal deploy path.

A conservative concurrency-6 risk scenario doubles the complete 1.76-GiB footprint to **3.52 GiB**, leaving only 0.48 GiB under 4 GiB. That is not qualification: hold the concurrency draft until synthetic long-file/retry stress and a staged 8-GiB/concurrency-6 experiment establish adequate headroom. Merging both sizing drafts unconditionally produces 4 GiB/concurrency 6, which these samples do not justify. Fresh sync remains at 8 GiB because its sampled peaks reach 5.28 GiB.
