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
`completed` with a nonempty structured title, overview, or sections, excluding
`server_minimum` title provenance. This is a metadata proxy for enrichment, not
a count of model calls or a reconstruction of partially completed processing.
No ids or content enter the observations or metric labels.

Current default-on merge-before-processing policy preserves enriched donors;
pending-live resolution also refuses independently enriched donors. This
measurement observes existing policy (including its rollback path); it never
relaxes those fences. The scoping report predates these protections, so the
processed fraction may now be small or zero.

Labels are captured from stored donors inside the final assignment plan, after
encoding, and consumed only from the committed result before external effects.
Transaction replays discard their observations; later intake sees a tombstone.
No new reads, persisted receipts, environment switches, or processing gates are
added. All 20 series are primed at startup through `utils.metrics`. The existing
Cloud Run sync `sync_.*` keep rule and the general `omi_.*` profile retain them.

After one full week on deployed workers, the fraction of absorbed donors that
had already been processed is:

```promql
sum(increase(omi_sync_bridge_absorbed_total{processed="true"}[7d]))
/
sum(increase(omi_sync_bridge_absorbed_total[7d]))
```

For the actionable bridge-pending cohort, add `pending="true"` to both selectors.
Use `sum by (source_kind, pending)` in both sides to inspect cohorts. A zero
denominator means no observed absorptions, not zero waste. This denominator is
absorbed donors, **not all published standalone rows**; do not multiply this
fraction directly by published volume as a savings estimate.

The GLM scoping estimate of $15–125/day was a conditional ceiling: 10–20% of
about 12.5k published rows/day, with assumed per-row STT and LLM cost. It is not
measured savings. If the measured fraction is at least roughly 5–10%, evaluate
deferring enrichment for bridge-pending rows in a separate PR, preserving
durable enrichment debt, expiry, audio custody, and ordinary intake behavior.

Prometheus counters are process-local. Worker loss between commit and emission,
or before a scrape, can undercount; zero priming cannot recover lost workers.
This metric is an operational estimate and is not a durable accounting ledger.
