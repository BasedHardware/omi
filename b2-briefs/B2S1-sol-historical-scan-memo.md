# B2-S1 (Sol) — `historical_scan_memo`: task-attempt memo for historical memory scan pages

You are the Sol coding agent for slice B2-S1 of the Firestore-reads loop, batch 2. Read this whole
brief, then `data/run-2026-10-16-firestore-reads/briefs/SOL-COMMON.md` (shared rules: worktree,
lever contract, tests, report), then this slice. The COMMON brief governs everything it covers;
this file only adds slice specifics.

## Origin and target
- Ledger origin: `memories:_historical_scan_page` — currently ~3.4M reads/hour on
  backend-sync-backfill + ~1.9M/h on backend-sync during the #21883 drain (steady pre-drain:
  ~14M/day). Lever: `historical_scan_memo`, default OFF, predicted ≤ 32M reads/day removed.
- Code: `backend/database/memories.py` — `_historical_scan_page()` (shared bounded keyset scan,
  updated_at/created_at order fields) and its public wrappers `scan_memories_updated_at_page` /
  `scan_memories_created_at_page`. Callers live in `backend/utils/memory/memory_service.py`
  (`_next_historical_scan_limit`, ~2602–2761).

## What we believe is happening
Sync and backfill tasks re-scan the same user's historical memory pages repeatedly within a single
task attempt (same `(uid, order_field, query_spec, start_after)` requested again after mutation
fences or across pipeline stages), each repeat billing a full page of document reads. This matches
the L4 triage's cheapest-safe candidate: "count exact repeated `_historical_scan_page` requests
within one task attempt and reuse only identical `(uid, filter, cursor)` pages before any
mutation. Do not lower page limits."

## What to build (lever `historical_scan_memo`, default OFF)
1. A task-attempt-scoped memo inside `database/memories.py` (ContextVar or request/task-scoped
   dict; no cross-process or cross-task cache, no Redis):
   - Key: `(uid, order_field, query-spec-identity, start_after-cursor, limit)`.
   - Value: the exact `(payloads, cursors, exhausted)` triple returned.
   - Scope: initialized/cleared per sync-task attempt; hard bound (e.g. 64 entries, 8 MiB of
     payload bytes, or a documented equivalent); evict-oldest; never persists across tasks.
2. Gate every read-through with `config.firestore_read_levers.lever_enabled('historical_scan_memo', key)`
   — per-user keying (uid). Lever OFF ⇒ the function must be byte-for-byte current behavior (same
   queries, same reads, same return values, no extra allocations of note).
3. Mutation fence: any write path in `database/memories.py` that mutates a user's memories rows
   within the same task (create/update/delete/visibility) must invalidate that uid's memo entries
   before the mutation commits (or clear the whole uid scope). Never serve a memo across a
   mutation. If a mutating call happens from outside this module, note it in your report — do not
   edit files you don't own.
4. Memo identity includes the `budget` mode: only calls passing an equivalent budget mode share an
   entry. Keep `budget` accounting truthful (a memo hit must not double-charge or
   un-charge the probe counters).
5. New tunables (memo size, entry cap) are env-configurable with the CURRENT values as defaults.

## Files you own (edit ONLY these)
- `backend/database/memories.py`
- New tests: `backend/tests/unit/test_fsr_historical_scan_memo.py`

## Required tests
1. Behavior-preservation: existing memories tests pass with the lever off (run the touched
   modules' existing tests + your new file only, `nice -n 19`, per COMMON).
2. Read-count proof: count Firestore reads (probe counters from
   `database/firestore_document_probe.py` or patched client) for N repeated identical scans with
   lever off vs on; assert the reduction (e.g. "10 identical pages: 10 scans → 1").
3. Fence test: mutate a memory mid-task, assert the next scan re-reads (no stale memo).
4. Off-path test: lever off ⇒ identical query call counts to current main.

## Report
Per COMMON: write `data/run-2026-10-16-firestore-reads/SOL-B2S1-report.md`; include predicted
reads/day arithmetic, files changed, test command + results, config for the integrator, and any
outside-owned-file needs.
