# B2-S3 (Sol) — `people_scan_dedupe`: task-scoped dedupe of People list scans

You are the Sol coding agent for slice B2-S3 of the Firestore-reads loop, batch 2. Read this whole
brief, then `data/run-2026-10-16-firestore-reads/briefs/SOL-COMMON.md` (shared rules: worktree,
lever contract, tests, report), then this slice. The COMMON brief governs everything it covers;
this file only adds slice specifics.

## Origin and target
- Ledger origin: `person_aliases:list_people` — ~1.27M reads/h on backend-sync-backfill + ~0.39M/h
  on backend-sync during the drain; steady ~12.7M/day (L4). Lever: `people_scan_dedupe`, default
  OFF, predicted ≤ 15M reads/day removed.
- Code: `backend/database/person_aliases.py::list_people` streams the user's whole `people`
  collection per call (no limit by default) and filters `is_dismissed` in Python.

## The S6 constraint (this slice's hard boundary)
SOL-S6-report.md §2 rejected a UID+TTL People cache: people are renamed/dismissed/created/deleted
and changed by speaker-learning/recovery OUTSIDE the alias module, so any cache lacking a mutation
generation covering the real writers can serve stale dismissed profiles or resurrect
privacy-sensitive context. Therefore:
- NO cross-task cache, NO TTL cache, NO Redis, NO persistent memo of any kind.
- The ONLY thing this slice may do is remove DUPLICATE `list_people` executions inside one
  task attempt: a task-scoped (ContextVar) raw-projection memo keyed
  `(uid, include_dismissed, limit)` that lives no longer than the sync-task attempt.
- Calls that feed entitlement/learning authority decisions, privacy/destructive scans, or anything
  mutation-adjacent must bypass the memo and read live. If call sites in files you don't own are
  the repeat offenders, do NOT edit them — report the top repeat sites (file:line + measured
  repeat rate) so the integrator can route a follow-up slice.

## What to build (lever `people_scan_dedupe`, default OFF)
1. In `database/person_aliases.py`: a task-attempt-scoped memo as above, hard-bounded (e.g. ≤ 256
   uids, ≤ 2 MiB per memo, or documented equivalent), cleared at task-attempt boundaries.
2. Gate with `config.firestore_read_levers.lever_enabled('people_scan_dedupe', uid)`. Lever OFF ⇒
   byte-for-byte current behavior.
3. Invalidate the whole uid's entries if any alias-module write happens in-task
   (`create/update/dismiss` paths in this same file).
4. New tunables env-configurable with CURRENT values as defaults.

## Files you own (edit ONLY these)
- `backend/database/person_aliases.py`
- New tests: `backend/tests/unit/test_fsr_people_scan_dedupe.py`

## Required tests
1. Behavior-preservation with lever off (existing person-alias tests + your new file only,
   `nice -n 19`).
2. Read-count proof: two identical `list_people` calls in one task attempt with lever off vs on;
   assert the stream count (e.g. "2 calls → 1 stream").
3. Freshness tests: (a) a `dismiss_person_soft` between two list calls invalidates the memo —
   second call re-reads; (b) a NEW task attempt (memo scope reset) re-reads; (c) differing
   `include_dismissed`/`limit` never share entries.
4. Off-path identity: lever off ⇒ same stream count as current main.

## Report
Per COMMON: write `data/run-2026-10-16-firestore-reads/SOL-B2S3-report.md`; include predicted
reads/day arithmetic, files changed, test command + results, the measured repeat-call sites (for
the follow-up slice), config for the integrator, and any outside-owned-file needs.
