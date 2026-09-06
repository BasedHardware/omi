# PostgreSQL task adapter

The task adapter serves the existing `GET /v1/tasks` and `POST /v1/tasks/ops`
contracts. The original route modules still own envelope validation, response
bytes, field projection, opaque task handles, and write refusals. The PostgreSQL
adapter changes storage and authorization; it does not introduce another task
wire or issue grants.

Firebase identity must resolve to an exact existing `tasks.read` or `tasks.write`
application grant. A `memories.read` grant does not authorize either path. Each
request revalidates the issued context in the existing authorized serializable
transaction, holding account-control and credential/grant locks through response
construction and commit. Context expiry is checked against the database clock
again before commit; request cancellation rolls the transaction back.

Migration 0047 stores task field bags as JSON text to retain their canonical key
order and escaped Unicode. Revisions use the existing task hash-chain primitive.
Deletion leaves a tombstone, so recreating a record cannot revive an earlier
revision. Sequence allocation, the changed task row, and the write-ID receipt
commit together. Receipt reuse with different semantic content fails; an exact
retry returns the stored result. A caught route error cannot accidentally commit
an incomplete storage operation.

Task reads reuse the canonical projection and cursor implementation. Local QA
explicitly selects fixture authority. PostgreSQL supplies persisted authorization,
grant generation, and account epoch bindings, so regranting access invalidates a
continuation without changing stable reader-scoped task IDs. Reads declare the
applied frontier caught up because accepted writes commit directly into their
read store, without an asynchronous projection queue.

Stale-epoch edits are preserved as exact envelope bytes before the refusal
commits. Task records, sequences, receipts, and preserved edits participate in
the existing account deletion/export table inventory. This does not establish a
running ninety-day straggler export-and-delete scheduler; that producer and its
operational deployment remain required. The adapter follows the existing
entitlement fence's absent-projection behavior and does not fabricate a paid
plan or usage balance. A real entitlement producer remains separate work.

The current snapshot adapter loads at most 10,000 distinct task records,
including tombstones. It refuses a new record before exceeding that limit, and
refuses an imported oversized snapshot rather than silently dropping records.
Account-sized snapshots are a deliberate initial storage limit; larger accounts
need a SQL-backed cursor/read adapter before raising it.

`drivers/postgres/tasks.real.test.ts` exercises the real app-role database path
with isolated synthetic identity/authority fixtures. These fixtures are test-only;
the deployed command never seeds them. The existing PostgreSQL qualification
runner must discover this file alongside migrations, backup/restore, and role
checks. Hermetic route/store tests continue covering canonical behavior. A passing
local suite is not proof of live Firebase grants, deployment, or mobile device
behavior.
