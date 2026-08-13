# Account deletion cleanup cycle contract

Status: implemented service orchestration; persistence adapters remain inert.

One cleanup cycle runs under a single adapter-owned deletion fence. It scans
all thirteen v4 surfaces, verifies the complete source inventory, applies the
deletion-dominance planner, disposes only surfaces the plan reports remaining,
then scans and verifies all thirteen surfaces again before returning `complete`.
Disposal follows closed dependency groups: externally derived/indexed and
product surfaces precede durable work and authoritative memory; account access
is last. `durable_work` and `staged_results` are one atomic group because their
immediate PostgreSQL foreign keys cross in both directions. Their inventory
counts stay distinct, but no adapter may delete one while leaving the other.
Inventory presentation order is never used as SQL deletion order.

An unverified or active legal hold, missing policy/export/restore coordinate,
or any planner blocker performs no disposal. Scanner failures, malformed or
incomplete receipts, disposition failures, and nonzero post-scan state produce
closed retryable outcomes, never success. An already-empty account is
idempotently complete without disposal.

The adapter receives only exact terminal account/control/deletion coordinates,
an opaque operation reference, an eligibility digest binding the exact terminal
export, restore, legal-hold, retention, and recovery coordinates, and closed
surface codes. It must reload and compare those sources while acquiring its
fence. The public result
contains closed modes/codes, surface names, counts/digests, and no account id,
content, SQL, object path, provider error, or free-form reason.

The service input boundary rejects proxies, accessors, decorated records,
extras, and malformed nested planner input before the adapter is invoked.

This unit does not mint cleanup authority, choose a role/lease duration, scan
PostgreSQL or legacy/object storage, place or release a legal hold, delete
bytes, persist a receipt, restore traffic, or activate a worker/route. Those
operations require named adapters and real transaction/race qualification.
