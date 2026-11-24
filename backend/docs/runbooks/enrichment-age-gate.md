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

Run `backend/scripts/unpark_enrichment_age_gate.py` from the operator checkout.
Discovery requires the `enrichment_age_gate_unpark_newest` index to be ready.
Before planning and again before applying, confirm the effective age window of
the production workers that enforce the gate. Pass it as
`--serving-max-age-hours`, after the serving rollout has reached all relevant
workers. Use `0` only when the serving gate is disabled. The tool checks each
row against the supplied window and includes that window and its fixed
`based-hardware` project in the receipt. Apply sends Cloud Tasks in
`based-hardware/us-central1` using each row's persisted handler binding.

Dry-run accepts the `ro-prod` and `prod-operator` tiers. Pass `--next-file` in a
private directory under `/Volumes/Ephemeral/scratch`. For apply, use the
`prod-operator` tier and repeat the page inputs with
`--apply --approve-plan-sha256 <dry-run digest>`. A changed page or window returns
`plan_changed` with no row write, enqueue or checkpoint update. Run a fresh
dry-run on the same input before approving again. A concurrent token change
after apply has matched the digest is fenced inside the transaction. Keep the
input cursor until the page is settled, then use the output file as
`--after-file` with a different `--next-file`. An empty page resets the cursor.
