# Historical tier (T1+): old backfill gets its summary on open

Sync backfill and batch audio whose trusted capture start is more than 72 hours
old (`SYNC_HISTORICAL_TIER_MIN_AGE_SECONDS`, the same boundary as the
[enrichment age gate](../../runbooks/enrichment-age-gate.md)) is created with
`processing_tier='historical'`. The row keeps its transcript and speakers, and
its deterministic title carries no `title_provenance`. Because the title is
final, the row owes no `summary_due_at`, Home shows it ready instead of
"Writing notes" forever, and the summary repair refuses it. Both producers stamp
the row at create. Sync intake settles the row's hold with its content snapshot
(`historical_ingest.settle`) instead of an enrichment-outbox mark. The batch
projection acknowledges the part (`store.ready`) instead of `mark_enrichment`,
after it prepares batch voice evidence. An identical later append is then
`unchanged`, and new speech never buys an automatic run. A historical row's
summary is generated only by `POST /v1/conversations/{id}/summary/open`, by
Reprocess, by merge or by Process now, and every one of those runs is
summary-only. No memories, tasks, apps, folders, webhooks or notifications run.

A clamped, shifted or estimated clock proves no age, so those rows keep full
processing. Appends never change the marker. `SYNC_HISTORICAL_TIER_ENABLED=false`
gives new rows full processing again; it does not touch rows that are already
stamped. Contract: [historical tier](../../listen_pusher_pipeline.mdx#historical-processing-tier-t1).
Operations and the stuck-row conversion: [runbook](../../runbooks/historical-tier.md).
