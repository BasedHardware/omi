# Recent conversation titles keep reserved enrichment capacity

Fresh titles were waiting behind the mixed enrichment backlog. The optional
fresh queue now admits only conversations within30 minutes of finished_at
(created_at fallback), including during idle-row promotion. A newly created
obligation for an old conversation retains the existing queue. Missing or
unavailable clocks retain that binding, with shared fallback telemetry on read
failure. Handler identity, token/lease fences and background custody are retained.

Production declares5 concurrent/2-per-second fresh dispatch through ops config;
staging mirrors that queue as `staging-enrichment-fresh` through its existing
provisioning helper. The lead owns review and deployment,
and must provision/reconcile before enabling the producer config. Targeted route,
coalescing and staging tests cover the change; extra E2E is waived for round2.
No deployed recovery is claimed by the lane.

Contract: [fresh enrichment queue capacity](../../listen_pusher_pipeline.mdx#fresh-enrichment-queue-capacity).
Runbook: [fresh enrichment priority](../../runbooks/enrichment-fresh-priority.md).
