# Stranded rollback recovery manifest

Status: route-free P7 recovery contract and retained PostgreSQL evidence;
production composition inactive.

ADR-014 defines `rolled_back_stranded` data as new-generation data in
PostgreSQL. It is not a second datastore and does not need a second deletion
surface. Deletion inventory v5 therefore covers those bytes once through the
existing authoritative-memory, work, projection, index, migration, access, and
external-object surfaces. The stranded recovery manifest answers a different
question: exactly what destination state remains recoverable after legacy
authority resumes?

## Exact 30-day window

One legacy-authority rollback coordinate binds account, control revision,
account epoch, database generation, cutover frontier, rollback frontier,
cutover time, rollback time, and a deadline exactly 30 days after rollback.
Callers cannot choose a shorter or longer window. The verifier returns only:

- `blocked` when control is not the exact active `rolled_back_stranded` head or
  any source is missing/released;
- `recoverable` before the deadline; or
- `disposition_due` at and after the deadline.

`disposition_due` is not disposal authority. It means the ratified recovery
window elapsed and the separately authorized disposition decision is now due.
Account deletion remains a different lifecycle path and disposes the same
underlying physical surfaces through the deletion cleanup coordinator.

## Complete destination manifest

The manifest requires one held source receipt for every deletion-inventory v5
surface except `legacy_generation_data`, because legacy has resumed as product
authority. Each receipt is bound to the exact account/control/epoch/database
generation, scanner contract, source frontier, held fence, record count, and
record-set digest. Explicit zero receipts are required. A missing scanner never
becomes empty.

The output contains counts, closed surface codes, times, and digests only. It
contains no memory, evidence, prompt, model output, object path, provider error,
credential, Firebase uid, or SQL. The process-local verified manifest cannot be
forged by JSON round-trip.

## PostgreSQL evidence

Migration 41 retains the manifest and eleven content-free source receipts.
Only the existing GCP-IAM-backed restore/operator role can call the fixed record
and load functions. Each call locks and revalidates the exact current active
`rolled_back_stranded` control head; stale epoch, control change, lifecycle
change, destination activation, or conflict denies. Exact replay returns the
same receipt and changed bytes conflict. Application and public roles have no
table or function access.

The retained rows are recovery/non-resurrection evidence and are not product
data. They are not a route, credential, release, grant, re-cutover decision,
support export, provider fence, or automatic deletion schedule.

## Remaining production gates

Production composition still owes the actual cutover/rollback coordinator that
holds every source fence, provides the complete receipts, and invokes this
repository after the legacy CAS. Recovery/export tooling, operator runbook,
post-deadline disposition action, live-provider qualification, and cohort
activation remain separate gates. This unit never makes stranded data visible
to ordinary clients.
