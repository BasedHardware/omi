# B2-S2 (Sol) — `ledger_purge_coalesce`: consolidate repeated privacy-history walks at the orchestrators

You are the Sol coding agent for slice B2-S2 of the Firestore-reads loop, batch 2. Read this whole
brief, then `data/run-2026-10-16-firestore-reads/briefs/SOL-COMMON.md` (shared rules: worktree,
lever contract, tests, report), then this slice. The COMMON brief governs everything it covers;
this file only adds slice specifics.

## Origin and target
- Ledger origin: `memory_ledger:_iter_collection_documents` — ~1.2M reads/h each on
  backend-sync-backfill (`other` + `users/memory_outbox`) and ~0.9M/h on backend-sync during the
  drain; steady ~12.8M/day (other) + ~12.1M/day (memory_outbox). Lever:
  `ledger_purge_coalesce`, default OFF, predicted ≤ 22M reads/day removed.
- Code: `backend/database/memory_ledger.py::_iter_collection_documents` feeds the privacy-purge
  walks. The repetition lives at the ORCHESTRATION layer:
  `backend/utils/memory/canonical_memory_adapter.py::purge_canonical_memory_projections` and
  `backend/utils/memory/memory_service.py::retract_conversation_memories`, which (per
  SOL-S6-report.md §"next amplifiers") trigger two/four overlapping history-walk groups for the
  same memory IDs in one task.

## What to build (lever `ledger_purge_coalesce`, default OFF)
1. At those two orchestrators, coalesce the purge work for a task's memory-ID set: batch the target
   IDs, remove redundant intermediate history scans, and preserve ALL of the following exactly as
   today:
   - the FINAL fresh history purge per user (never trust an earlier pass's result for the last
     verification),
   - provider-absence proofs, legal-hold takeover checks, retry receipts (S6 §1),
   - the destructive-gate revalidation behavior (`revalidate_gate`) semantics.
2. Mechanical rule (from S6): do NOT merely cache `_iter_collection_documents`, do NOT suppress the
   final verification, and keep privacy/destructive scans uncached. The savings must come from
   eliminating redundant *calls* to the purge machinery, not from reusing stale scan results.
3. Gate each coalesced path with
   `config.firestore_read_levers.lever_enabled('ledger_purge_coalesce', key)` (per-uid keying).
   Lever OFF ⇒ byte-for-byte current behavior: same purge calls in the same order, same reads,
   same deletes, same receipts.
4. New tunables (batch caps) env-configurable with CURRENT behavior as default.

## Files you own (edit ONLY these)
- `backend/utils/memory/canonical_memory_adapter.py`
- `backend/utils/memory/memory_service.py` (ONLY the `retract_conversation_memories` purge
  sequencing and any new private helper you add beside it; do not touch the historical-scan
  pagination code — that is slice B2-S1's caller area and must stay identical)
- New tests: `backend/tests/unit/test_fsr_ledger_purge_coalesce.py`

## Required tests
1. Behavior-preservation with lever off (existing canonical/retract tests for touched modules +
   your new file only, `nice -n 19`).
2. Read-count proof: a unit test driving a deletion of N memories through the orchestrator with
   lever off vs on, counting `_iter_collection_documents` walks / Firestore reads, asserting the
   reduction (e.g. "4 walks → 1 final walk").
3. Safety tests: final fresh purge still runs after coalescing (inject a mutation between the
   coalesced pass and the final pass, assert the final pass still sees and removes the new row);
   legal-hold takeover and provider-absence proof still executed; receipts still written.
4. Off-path identity: lever off ⇒ same purge-call sequence as current main.

## Report
Per COMMON: write `data/run-2026-10-16-firestore-reads/SOL-B2S2-report.md`; include predicted
reads/day arithmetic, files changed, test command + results, config for the integrator, and any
outside-owned-file needs.
