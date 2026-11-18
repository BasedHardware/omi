# Measure duplicate follow-up discovery before electing a sweeper

This diagnostic observes IDs already returned by periodic follow-up discovery,
BEFORE process-local backoff. It adds no Firestore queries/writes and changes no
cursor, ownership, claim, receipt, privacy or scheduling decision. Targeted/owed
repairs and the direct initial desync seed query are excluded. Direct Firestore
and the mirror-only `DualStore` primary are included; Postgres/index and simulated
adapters are excluded. These are selected-row observations, not SDK retries,
physical billed reads or a fleet census.

## Bounded signals

`omi_batch_pipeline_projection_overlap_visits_total` counts row visits, including
repeats; `pages_total` counts successful pages, including empty pages. Labels are
only `data_namespace` (`batch_pipeline_dev`, `batch_pipeline_prod`) and `mode`
(`legacy`, `due`). `skipped_total{reason}` reports invalid/regressing clocks and
observer errors; missing observer coverage must never be treated as zero work.

`omi_batch_pipeline_projection_overlap_register` exports a64-register HLL sketch
for each scope in two alternating fixed600-second windows. Extra labels are
`slot` (`0`, `1`) and `register` (`0` through `63`). No row identifier, row hash,
owner, user, PID or unbounded epoch label is exported or retained. Only a hash's
leading-zero rank is retained. Hashing uses a fixed namespace domain so registers
can be unioned across targets. This is identifier-free aggregation, not a claim
of differential privacy or a telemetry data-access grant.

Values encode `epoch*64+rank`, where `epoch=floor(unix_time/600)`. Decode all64
values with `utils.batch_pipeline.projection_overlap.decode(values, epoch)`.
Reject a partial, mixed or stale epoch. Multiprocess `max` exposition unions
registers within a scrape target; a new epoch's zero registers supersede old
ranks. A partial rotation is invalid, never a plausible smaller population.

For a COMPLETED epoch, estimate each target's distinct rows with `estimate`.
Take the componentwise maximum of decoded ranks across targets, then estimate
the distinct fleet union. `sum(target distinct estimates)/fleet union estimate`
is approximate average scrape targets touching each observed row. Equal sets
on4 targets yield about4; disjoint sets about1. Repeated visits on one target
increase visits without increasing distinct-target overlap. A scrape target may
contain several worker processes: this is not an exact process count. HLL64's
nominal relative standard error is13% per distinct estimate; the ratio has
additional correlated estimation error. Do not advertise a hard confidence bound
or infer savings simply by multiplying the observed ratio by a bill.

## Coverage and cost acceptance

`BATCH_PIPELINE_PROJECTION_OVERLAP_DIAGNOSTICS` defaults on; `0`, `off`, `false`
or `no` disable observer wiring when the follow-up drain is constructed. If
headroom is not qualified, Release can set it off on the ordinary candidate
before startup, without changing discovery. To remove already-registered series,
replace the affected processes/revisions with the same artifact and this switch
off, and verify the new receiving targets: changing an env value cannot erase
old multiprocess metric files or historical ingested samples. Do not call that
historical metric disappearance instantaneous. Inverse: restore the prior switch
value only after target sample-cap and telemetry-budget qualification.

Use existing scrape infrastructure. The API Cloud Run keep rule already admits
`omi_batch_pipeline_*`; no keep-list or production mutation is added here.
Dedicated pump/private endpoints still need independent export/identity proof.
A root ro-prod metadata-only probe on2026-11-17 found11 distinct `instance`/`pod`
labels for the existing pump tick family on GKE; that does NOT establish the
new family's coverage or API target identity. Prove both on the actual carrier.

One active scope has128 register series after two windows, plus4 counter/time
series. Worst case, all4 scopes use512 registers plus16 counter/time series,
with up to3 skipped-reason counter/time pairs. At a15-second scrape, register
samples alone are737,280/day/target for one scope,2,949,120/day/target for all4.
Budget against the ACTUAL target count, scrape interval and existing sample cap;
Release must confirm headroom and the telemetry cost before admitting a carrier.
No new scrape target, rate, service, timer or paid capacity is authorized here.

After actual serving, verify nonempty new families from every eligible source,
closed adapter/target coverage and no sample-cap drops. Capture all64 registers
for the completed epoch after the last relevant scrape+ingestion delay but before
the same slot is reused ten minutes later. Record gaps, restarts, scale-down and
clock skew. Unscraped or departed instances cannot be reconstructed; if any
participating target is missing, report partial coverage, never whole-fleet
zero duplication. Scrape timestamps alone do not establish an epoch match.

Reserve24h of qualified serving coverage before sizing the leader. Compare
same-window physical read-origin counters and completed/admitted work/age;
visit-counter deltas need matched epoch boundaries and scrape-edge uncertainty.
Root then proposes one fenced discovery lease per namespace/task with bounded
renewal/takeover, fairness and retained targeted/owed repair. This PR does NOT
elect a sweeper. Rollback is the previous ordinary artifact; no data migration or
receipt change needs reversal. Any telemetry error leaves discovery unchanged.
