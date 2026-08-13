# Account-deletion cleanup composite contract

Status: inert service-layer composition; no route, scheduler, credential, or
production activation

## Contract

The composite adapts independently injected cleanup participants to the
complete `runAccountDeletionCleanupCycle` coordinator. Construction succeeds
only when every deletion-inventory surface has one owner, no surface has two
owners, and the cyclic durable-work/staged-results disposal group has one
owner. Validation happens before any external dependency is called.

An injected terminal/eligibility-fence coordinator encloses every independently
held participant session. The composite scans every participant before
disposal, dispatches the core dependency groups to their sole owners, scans
every participant again, and requires an exact final eligibility-fence
revalidation before returning the coordinator's result. Provider exceptions
and malformed receipts become closed error codes and cannot leak content.

## Atomicity boundary

The outer fence proves that the terminal deletion coordinate and its complete
eligibility inputs remain current. Each participant supplies an honest fence
for its own store. This does **not** create an atomic transaction across
PostgreSQL, object storage, search, vector, or legacy systems. A later
participant can fail after an earlier participant committed disposal. Such an
attempt never reports completion; the operation is replayed until a complete
held-fence zero rescan and final exact revalidation succeed.

Production composition therefore owes concrete adapters whose fence semantics,
idempotent receipts, and replay behavior are qualified independently. This
contract does not select providers, credentials, retry schedules, retention
policy, approvals, or activation defaults.
