# Sync bridge absorption measurement

`omi_sync_bridge_absorbed_total{source_kind,pending,processed}` counts each
stored donor's first committed redirect in sync assignment. Pending-live
resolution uses that same assignment seam. Retraction attempts, cleanup retries,
and ancestor redirect repairs do not increment it. Both processed and
unprocessed donors belong to this one family; processing behavior is unchanged.

Labels are closed: `source_kind=omi|phone|desktop|sdcard|other`,
`pending=true|false`, `processed=true|false`. Other source values fold to `other`.
`pending` means the donor carried the intake `sync_bridge_pending` marker before
absorption, even if its deadline expired. `processed` means stored status is
`completed` and `config.merge_before_processing.already_processed(row)` is true.
That metadata predicate recognizes summary completion/output receipts, LLM input
or output hashes, structured action items/events, and legacy titles or summaries.
A server-minimum title alone is unprocessed; explicit completion evidence takes
precedence. This is a metadata proxy, not a count of model calls or partial work.
No ids or content enter the observations or metric labels.

Current default-on merge-before-processing policy preserves enriched donors;
pending-live resolution also refuses independently enriched donors. This
measurement observes existing policy (including its rollback path); it never
relaxes those fences. The scoping report predates these protections, so the
processed fraction may now be small or zero.

`omi_sync_published_rows_total{source_kind,pending}` counts every created row
across all accepted assignment plans, including each size rollover. It uses the
same bounded source/pending labels sampled from each created row. A primary
`merged` outcome may still publish rollover rows; `omi_sync_intake_total` counts
primary assignment outcomes and is not a row denominator. "Published" here means
created by sync assignment, including temporarily hidden bridge-pending rows.

Labels are captured from stored donors inside the final assignment plan, after
encoding, and consumed only from the committed result before external effects.
Both preparation and emission are best-effort, so malformed telemetry cannot
abort assignment or fail intake. Transaction replays discard their observations;
later intake sees donor tombstones and existing created rows. Deduplication
holds across retries and replicas while those durable records remain. Loss or
restoration of a redirect tombstone can permit a later absorption to count again.
No new reads, persisted receipts, environment switches, or processing gates are
added. All 20 absorption and 10 published-row series are primed at startup
through `utils.metrics`. The existing Cloud Run sync `sync_.*` keep rule and the general `omi_.*` profile retain them.

After one full week on deployed workers, the processed-absorptions /
published-rows ratio is:

```promql
sum(increase(omi_sync_bridge_absorbed_total{processed="true"}[7d]))
/
sum(increase(omi_sync_published_rows_total[7d]))
```

For the actionable bridge-pending cohort, add `pending="true"` to both selectors.
Use `sum by (source_kind, pending)` in both sides to inspect cohorts. A zero
denominator means no observed published rows, not zero waste. This is a
windowed event ratio, not a cohort survival probability: donors absorbed during
the week may have been published before it. Both counters cover committed row
events exactly in the successful result, but their process-local export can
undercount. It does not by itself establish actual vendor savings.

The GLM scoping estimate of $15–125/day was a conditional ceiling: 10–20% of
about 12.5k published rows/day, with assumed per-row STT and LLM cost. It is not
measured savings. If the measured fraction is at least roughly 5–10%, evaluate
deferring enrichment for bridge-pending rows in a separate PR, preserving
durable enrichment debt, expiry, audio custody, and ordinary intake behavior.

Prometheus counters are process-local. Worker loss between commit and emission,
or before a scrape, can undercount; zero priming cannot recover lost workers.
This metric is an operational estimate and is not a durable accounting ledger.
