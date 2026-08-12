# Local PostgreSQL qualification

This workflow provides a repeatable PostgreSQL 18.4 environment for memory-system
development. It uses synthetic data only. Docker CLI and Colima are managed by
`machine-config`; this repository owns the digest-pinned database and runtime controls.

## One-time Mac prerequisite

From `/Users/dazheng/machine-config`:

```sh
./macctl plan
./macctl apply
./macctl doctor
```

Review the plan before applying it. Apply installs and pins Docker CLI 29.7.2 and
Colima 0.10.3 but does not start a VM. The dedicated profile stores rebuildable state
under `/Volumes/Ephemeral` and never changes the global Docker context.

Linux and CI developers supply their existing Docker daemon; the platform script never
invokes Colima there.

## Daily workflow

From the platform repository root:

```sh
bun run test:postgres:setup
bun run test:postgres:status
bun run test:postgres
bun run test:postgres:teardown
```

`setup` is idempotent. On a Mac without a running managed daemon it starts only the
`omi-memory` profile. It creates an exactly labelled database volume and container,
binds PostgreSQL to an OS-assigned `127.0.0.1` port, verifies the pinned amd64 image,
PostgreSQL 18 data path, labels, mount, and loopback binding, and prints no credential or
connection URL.

`test` reapplies checksummed migrations, exercises the real Postgres.js transaction
adapter, and runs the same client corpus in pinned Bun 1.3.14 and Node 24.19.0 amd64
containers. It refuses ambient `DATABASE_URL` and `PG*` selectors.

`teardown` removes only the owned container, stops the managed profile only when this
workflow started it, and preserves the labelled volume. A later setup reuses that data.

## Destructive reset

After resolving the status output and confirming that the synthetic local database may
be discarded:

```sh
bun run test:postgres:destroy
```

This command carries the required `--yes`, verifies exact resource labels, removes only
the owned container and volume, and leaves unrelated Docker/Colima state untouched.
The data is unrecoverable. To remove the rebuildable VM itself as a separate operation:

```sh
cd /Users/dazheng/machine-config
./macctl container reset --yes
```

Never use Docker prune, a mutable PostgreSQL tag, production credentials, or production
data with this workflow.

## Current qualification boundary

Passing this entrypoint proves the pinned server/client/runtime scaffold, migration
reapply, callback-scoped serializable transaction behavior, rollback-local cleanup,
application-role graph/formation/identity/liveness append and reconstruction, shared
SQLite/PostgreSQL snapshot parity, one-head race behavior, and Bun/Node client parity.
The real corpus also kills a size-one pool backend at a query-quiescent pre-commit
checkpoint after its first write, proves observer-visible rollback, and proves the next
transaction reconnects with cleared local state. It does not by itself activate
PostgreSQL for production. Arbitrary in-flight cancellation, product-projection rebuild,
load/recovery, and the remaining gates in the PostgreSQL authority contract still apply.
