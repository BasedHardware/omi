# Historical tier (T1+): old backfill gets its summary on open

Sync backfill, late-listen audio and batch audio whose trusted capture start
is past the [enrichment age gate](../../runbooks/enrichment-age-gate.md)
(`ENRICHMENT_MAX_AGE_HOURS`, the tier boundary itself; sync decides as of the
latest possible wake) is created with `processing_tier='historical'`. The row
keeps its transcript and speakers, and its deterministic title carries
`title_provenance='historical_minimum'`, a stand-in that summary debt ignores.
The row owes no `summary_due_at`, Home shows it ready instead of
"Writing notes" forever, and the summary repair refuses it. Both producers stamp
the row at create. Sync intake settles the row's hold with its content snapshot
(`historical_ingest.settle`) instead of an enrichment-outbox mark, including on
crash recovery and exact retries that still owe completion; a row that fails to
settle keeps its mark. The batch projection acknowledges a settled historical
part inside `mark_enrichment`'s transaction (`historical_settled`), so the privacy
guard and the record-notes dispatch still run; only the first-summary wake is
skipped, and an output that is not historical keeps its mark. An identical later append is then
`unchanged`, and new speech never buys an automatic run. A historical row's
summary is generated only by `POST /v1/conversations/{id}/summary/open`, by
Reprocess, by merge or by Process now, and every one of those runs is
summary-only. No memories, tasks, apps, folders, webhooks or notifications run.

A clamped, shifted or estimated clock (including a batch clock-run filename) proves no age, so those rows keep full
processing. Appends never change the marker. `SYNC_HISTORICAL_TIER_ENABLED=false`
gives new rows full processing again; it does not touch rows that are already
stamped. Contract: [historical tier](../../listen_pusher_pipeline.mdx#historical-processing-tier-t1).
Operations and the stuck-row conversion: [runbook](../../runbooks/historical-tier.md).
