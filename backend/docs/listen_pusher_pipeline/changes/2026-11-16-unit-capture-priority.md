# Per-unit sync admission priority (source only)

The request seed previously supplied every decoded unit's priority. With
`BATCH_PIPELINE_UNIT_CAPTURE_PRIORITY_ENABLED=true`, intake computes each unit's
age from its stored capture start (otherwise decoded capture start) plus duration,
then uses `min(seed.priority, priority_for(request_lane, unit_end_age))`.
Lower priorities are fresher: this can only promote, never demote. Recovery units
with untrusted clocks and malformed clocks retain the seed. The default is off;
unset, malformed, false, off and zero preserve seed priority.

The request lane, `unbound_capture_time` gate and 600-second boundary are unchanged.
Consequently unbound backfill units still cannot become FRESH. This fixes
sibling/start-versus-end priority dilution within the existing lane policy; it
cannot fix the dominant unbound sync admission path. A fresh-lane unit younger
than 600 seconds at capture end can become FRESH even with a RECENT request seed.

`omi_batch_pipeline_priority_demotions_total{lane,reason}` counts
`seed_effective_divergence` when the effective class differs from the seed,
and `fresh_capture_not_fresh` when a <=600-second end age retains a non-FRESH
class. Despite the requested metric name, divergence here means promotion.
The latter reason remains active with the flag off for a baseline. Counts are
unit classification attempts (before durable commit), not unique committed units.
They carry only bounded lane and reason labels, no account or content fields.

Release rollout: keep the flag off for source deployment. After a separate Release
activation decision, enable on one sync admission instance for one full hour;
verify both counter reasons are exported, FRESH latency does not regress, and
runnable RECENT/DEEP continue progressing. Release owns expansion to all sync
admission instances only after that clean window; review/expand or explicitly
extend by 2026-11-23. This change authorizes no deployment or activation.

Release rollback: set `BATCH_PIPELINE_UNIT_CAPTURE_PRIORITY_ENABLED=false` on all
sync admission instances. New admissions retain request seed priority; previously
admitted units keep their stored priority. No migration, requeue or index change.
