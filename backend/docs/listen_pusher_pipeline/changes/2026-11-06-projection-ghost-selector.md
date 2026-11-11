# Default-OFF ghost hint selector

A pre-fix sibling quarantine write could leave a `quarantine_held` discovery
hint on a completed `ready` receipt without any quarantined part. The real-held
release/expiry gates reject that shape, leaving it undiscoverable indefinitely.

The [held contract](../../../utils/batch_pipeline/CONTRACT.md#held--dead-letter-state-table)
now specifies a sibling branch in the existing release transaction. Fresh reads
must prove ready receipt, no quarantined part/privacy refusal, consistent
segment/binding/owner, committed job with recovery state other than held, and
at least 24h since finite `committed_at`. The only write is the existing sanctioned
`projection_state=ready` normalization. Ordinary discovery completes the ledger,
publishes and acknowledges with its own fences. No expiry or reassignment occurs.

`BATCH_PIPELINE_PROJECTION_GHOST_SETTLE_ENABLED` defaults OFF in every parser
mode; only `true` enables it. Off classifies the already-read documents without
extra queries/reads or ghost writes. Across both legs at most 16 ghosts settle
per pass. Existing summary logs gain aggregate `ghost_settled`, `classified`,
`skipped_by_class` and disjoint age buckets 1d/<7d, 7d/<30d, 30d+. No row IDs or
user data are added. Existing scan/cursor/real-hold behavior is preserved.

Ramp owner David: day 0 count-only; ONE train enable only after David approves;
24h review of classifications, settlements, skip classes, errors/conflicts and
age buckets plus existing quarantine_held_rows, assignment_held, held_expired_rows
stock legs. Kill by setting false; future repairs stop while valid repaired hints
and already published results remain. Production enable is outside this PR.

The four #24779 strict xfail cases (release/expiry × recovery none/recovered)
become flag-on regressions. Loopback proof drives actual selector → discovery →
ledger completion → captured publication → acknowledgement → replay without
reassignment/enrichment duplication. New transactional fence, count-only and
shared-cap tests retain real holds and privacy fences. No production stock,
read rate, scan-wrap time, throughput, publication volume or live acceptance was
measured. Tick/page/interval constants are unchanged. No reconcile CLI runs.
