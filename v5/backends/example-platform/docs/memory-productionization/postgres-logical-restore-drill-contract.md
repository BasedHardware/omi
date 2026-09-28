# Bounded local PostgreSQL logical restore drill

Status: local PostgreSQL 18.4 qualification only. This is not Cloud SQL PITR,
backup policy, an RPO/RTO claim, a production restore runner, or traffic release
authority.

`bun run test:postgres` runs one logical dump and restore after the real adapter
suite has committed representative migration, restore-admission, retained
tombstone, and stranded-rollback recovery rows. The drill:

1. refuses a source database larger than 512 MiB;
2. writes exactly one custom-format dump inside the labelled disposable
   PostgreSQL container, with a 64 MiB process file limit and a second exact
   post-write size check;
3. restores only into the fixed `omi_restore_drill` database in the same pinned
   PostgreSQL 18.4 container;
4. compares the server version, schema table count, complete migration-history
   coordinates, and exact row-set fingerprints for retained restore admission,
   restored terminal fences, and stranded-rollback recovery evidence;
5. proves the application role still cannot directly read a retained tombstone
   table after restore; and
6. drops the temporary database and deletes the dump in `finally`, failing the
   test closed if either cleanup operation fails.

The ordinary one-shot harness then performs its existing exact labelled
container-and-volume destruction. `test:postgres:preserve` remains an explicit
debug-only choice; even in that mode the restore database and dump are removed.
No dump is copied to the host, no password appears in a command argument, and
provider output is collapsed to closed error codes.

This drill establishes that a small logical PostgreSQL backup can reconstruct
the current schema and selected durable safety evidence. It does not establish
point-in-time recovery, WAL/archive continuity, encryption or retention policy,
cross-region recovery, Cloud SQL IAM, a production backup schedule, recovery
under live write load, or the program's RPO/RTO. Those remain separate P7/P8
operator and infrastructure gates.
