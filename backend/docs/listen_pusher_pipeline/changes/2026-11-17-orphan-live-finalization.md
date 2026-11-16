# Missing-marker batch-live finalization recovery

`BATCH_FINALIZE_ORPHANED_LIVE_CAPTURES_ENABLED` defaults off using `default_off`:
unset, false and malformed values preserve the existing content-due query.
When explicitly enabled, that query uses the existing collection-group
`status + finished_at` index and retains the original `has_content == True`
population plus `batch_live_v1` rows whose `has_content` field is absent.
Explicit false markers and other missing-marker lanes are excluded locally.
No index or deployment change is included.

The same persisted cursor bounds this scan to 2,000 examined rows per tick,
100 per page, 25 eligible candidates and 10 successful admissions. Missing
`finished_at` rows cannot enter the ordered due query. Normal recovery checks
still require stale content, no existing job, and all deletion/protection fences.

The diagnosed rows expose an additional admission constraint: the fast path
requires a proven expired recording-session lease, and missing session identity
previously counted as unknown. Inside the admission transaction, this change
allows only closed (`record_audio_closed is True`) batch-live captures with a
missing content marker, a datetime `finished_at`, and no session reference to
pass that unknown-lease check while the new flag is on. Referenced but absent,
malformed, mismatched or active sessions retain the original refusal. An open
capture without a session identity remains refused. The existing predicate
alone was therefore not sufficient for the fast path.

No composer, vendor gate, SLO or `BATCH_LIVE_ORPHAN_REPAIR_ENABLED` behavior changes.
This is a source-only change; no production access or enablement was performed.

## Release and rollback

Release owns enablement after exact-head review/CI and verification that the
existing status/finished-at index is serving. Start with one self-heal runner
for a full observation window; compare aggregate self-heal enqueue/refusal/error
counts and finalization outcomes, and watch episode waiting/composed outcomes.
Expand to remaining runners only if lease/deletion refusals remain enforced and
errors and duplicate jobs do not increase. Release must expand or disable by
24 hours after initial enablement; this branch does not authorize that action.
Rollback: set the new flag false (or unset) on every runner, restoring the old
query and lease rule. Already admitted durable jobs remain owned by the normal
finalization pipeline; rollback does not cancel them.

## Local verification

The candidate-query, self-heal sweep/recovery and finalization-job modules passed
220 tests; the combined seven-module run including quiet-finalization, operator
orphan-repair and refactor-mode coverage passed 444 tests at the implementation
commit. Regression coverage drives the real scan and transactional admission
with synthetic records, including default/false/malformed flags, closed unleased
capture enqueue, no-finish/live/unknown leases, non-target lanes, explicit false
markers, cursor continuation, and the shared per-tick bounds. This proves local
behavior, not deployed throughput or episode recovery.
