# Released-memory change projection

`database.memory_change_head` adds one content-free random token per owner to
the **same Commit RPC** as every change to `memory_items`, historical
`memories`, or `memory_historical_overrides`. It covers set/create/update,
field transforms, hard deletes, batches, transactions and sync/async clients.
It preserves the source writes, preconditions, transaction identity and source
write-result cardinality. A failed commit changes neither source nor token.
The installer runs alongside the existing SDK read probe in `database._client`.

Non-atomic BatchWrite cannot publish a safe atomic token. Before any matching
bulk mutation, its owner head is permanently marked `blocked=true`; failure to
write that barrier stops the bulk request. Ordinary commits preserve the block.
Blocked owners always use the source paths. Do not clear a block while a bulk
writer might remain active. No automated unblock or backfill is provided.
Account erasure removes the head in its existing final metadata cleanup, after
all source deletes, so visiting `memory_state` first cannot leave a late head.

The token keys bounded, process-local **raw query snapshot projections**.
Canonical, historical, list-window and status-pair readers reuse only the exact
query, database, owner, client and rollout epoch. A hit reads the head before
and after lookup. A complete fill publishes only when both heads agree. Head
errors, missing heads, unsupported queries, churn and bulk blocks retain the
existing source queries and Firestore-read levers. Nothing caches authorization,
decrypted historical content, policy-filtered results or incomplete streams.
Policy, device/archive visibility, lineage, suppression, identity validation and
decryption still run in their original callers on every read.

Reuse expires after 60 seconds; eviction is lazy on the next projection read.
Storage is bounded to 128 entries / 16 MiB, with a 2 MiB per-entry ceiling.
Small queries with fewer than three returned rows
use the source path: two head reads would not save money. The small-query hint
only disables reuse and does not suppress any source query. No Redis dependency,
polling change, field/index migration or recurring scan is introduced.

MCP conversation cards reuse fs-p1's atomic
`users/{uid}/list_serving_versions/conversations.version`. They require its
`OMI_LIST_VERSION_EPOCH` and enabled `OMI_LIST_PROJECTION_WRITER_ENABLED`, in
addition to P2's gate. Missing P1 metadata falls back to the existing MCP path.
P2 adds no second conversation head. Offset skips are charged only on source
queries, while partial-stream prefixes keep their previous budget behavior.

## Rollout and rollback

The change-head writer is always on. `MEMORY_RELEASED_PROJECTION=off` is the
reader kill switch; the reader preference defaults on.
`MEMORY_RELEASED_WRITERS_COVERED=v1:<unique-rollout-epoch>` is a separate,
initially absent **fleet writer coverage attestation**, required before reuse.
An individual process installing the hook is insufficient evidence.

1. The rollout lead ships the writer to backend, sync/backfill/integration,
   listen, pusher, desktop-backend and any jobs/scripts that mutate these
   collections. Audit direct SDK, non-Python and raw-RPC writers too. A writer
   that does not import `database._client` is outside automatic coverage.
2. Before T3's cutoff (2026-10-24 07:30Z), the lead verifies source release
   identity on all writer runtimes and synthetic create/update/delete canaries.
   If coverage cannot be proved, report the blocker and leave reuse disabled.
3. Only after that proof, the lead sets a new unique coverage epoch across
   participating readers. MCP additionally waits for P1 coverage and its epoch.
   All eligible accounts participate; bulk-blocked/missing-head accounts retain
   source reads. No user-data backfill is required or authorized by this PR.
4. Compare exact output/order/access decisions and p95; on mismatch or latency
   regression, turn the reader kill switch off immediately. Clear coverage
   **before any writer rollback/gap**, and use a fresh epoch after coverage is
   restored. Never reuse an epoch across a writer gap. Writers remain installed
   during a reader-only rollback.

`omi_memory_released_projection_total` carries fixed `surface` and `outcome`
labels plus the existing bounded `origin`. Head reads use
`job:released_memory_projection`; source reads retain their original caller and
origin attribution. Measure both the avoided source reads and new head reads,
and the additional head writes/contention. A 100-document warm page uses two
head reads instead of 100 source reads; a cold page adds head checks. Repeat
share, eligible-account coverage and process locality determine net savings.
50M/day is the sprint's conditional full-P2 target, not a measured PR saving.
Use equal full-day windows and mature billing per the reads-loop runbook.

## Verification

Run the targeted unit files through `backend/test.sh` with
`BACKEND_UNIT_TEST_FILE_LIST`, under the workspace's `omi-heavy` gate and nice
19. The unit tests count billed documents, preserve raw identities/timestamps,
and cover mutations, deletion, negative results, coverage/epoch changes,
fallback, budget/deadline behavior and MCP's P1 dependency.

The real SDK/emulator script checks atomic failed batches, injected RPC-abort
transaction retry, source result cardinality, sync/async deletes and bulk
exclusion. It refuses to run without `FIRESTORE_EMULATOR_HOST`:

```sh
PYTHONPATH=backend firebase emulators:exec --only firestore \
  --project demo-fs-p2 \
  'backend/.venv/bin/python backend/scripts/released_memory_projection_emulator_test.py'
```

This verifies source contracts locally; it does not establish fleet coverage,
deployed p95, production parity, or realized billing savings.
