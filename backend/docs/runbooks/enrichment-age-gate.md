# Historical enrichment parking

David's 2026-11-04 ruling limits enrichment to the past three days.
`ENRICHMENT_MAX_AGE_HOURS` defaults to `72`; invalid or negative values retain
72 and `0` disables new parking. A conversation's `created_at` OR its obligation's
`first_pending_at` older than that window is enough to park it. Missing timestamps
are unknown and do not prove age.

The enrichment endpoint checks age on the database executor before borrowing a
callback slot. The Firestore outbox claim, sweep and summary-debt repair enforce
the same rule. Parking is a CAS on an unleased row: retain identity, version,
policy and custody metadata, mark `age_gate_parked=true` and
`deferred_reason=age_gate_72h`, clear the due time, set dormant, and rotate the
task token. The task answers HTTP 200 and old deliveries become stale. Nothing
is deleted and no LLM call is made. Existing active leases finish under their
existing fences; the age gate does not cancel a running worker.

Marks, sweeps and debt repair never reopen parked rows. A new append to an old
conversation therefore cannot repeatedly recreate its wake. First-summary
deadlines remain retained as debt, but this explicit historical-work ruling
suspends their processing while parked.

Rollback stops new parking by setting the value to `0`. It does not automatically
resume the parked population: the lead must separately unpark bounded batches
after the serving configuration permits their age. Increasing the window admits
older work; decreasing a nonzero value parks more work, not less.

An unpark operation must re-read the row under CAS, verify the exact parked
token and absence of an active lease, honor privacy fences, then clear the age
marker/defer reason, set dormant=false and due_at/task_due_at=now, rotate the
token and enqueue the persisted handler binding. A failed enqueue leaves durable
due debt for the normal sweep. Keep both the original first_pending_at and the
custody/policy fields. No deletion, generation reset or synthetic completion is
part of unpark. The operator must keep a private checkpoint and counts-only
receipt; never print identities.
