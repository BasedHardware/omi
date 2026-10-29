# SOL-WQ13 — finalization candidate queries

## Result and scope

Branch: `lane/firestore-reads-wq13-candidates`.
Base at lane start: `origin/main` = `9fe2a38c6fb250b9840b8c6cc345d8c2e8c821c3` (fetched before branching).
Implementation commit: `580f7b2a00`.

Added the recognized `finjob_candidate_queries` lever. Missing or zero remains off;
no runtime/deploy/chart literal was edited. The loop owns adding the literal key
at zero. Enabled queries use the existing stable host cohort mechanism. This is
a partial reduction of candidate reads, not elimination of every reconciliation
scan: preserving legacy discovery prevents a safe age predicate on one path.
No PR was opened; nothing was pushed, merged, deployed, or enabled. GCP tier:
none (local code/tests and a saved measurement only).

## Verified caller inventory and changes

`backend/main.py` and `utils/other/fsr_leader_lease.py::_LOOPS` register five
finalization/queue-age loops below. The sixth loop is
`reconcile_pending_deletion_wipes`, unrelated to finalization and untouched.
The brief's `reconcile_in_progress_finalization_jobs` and
`reconcile_stale_processing_orphans` correspond to the actual service names
`reconcile_stale_in_progress_conversations` and
`reconcile_stale_processing_conversations`.

| Loop / database caller | Lever-on change | Expected document-read delta |
| --- | --- | --- |
| `reconcile_stale_in_progress_conversations` → `run_selfheal_tick` → `scan_in_progress_conversations` | Caller passes its exact existing two-hour admission cutoff; group query adds `finished_at <= cutoff`, ordered by `finished_at`. Existing Python and transactional admission checks remain. The optional self-heal job shares this caller and receives the same optimization. | Removes fresh and missing/non-timestamp finish rows before pagination. On an exhausted rotation, reads change from all in-progress rows to stale timestamped in-progress rows, plus existing cursor reads and query minimums. Per-tick savings may be zero when stale rows alone fill the scan cap. Absolute production reduction is unknown until enabled/read out. |
| `reconcile_abandoned_byok_finalization_jobs` → `get_abandoned_byok_job_candidates` | Keeps `requires_byok == True`; adds `status in [queued, leased, blocked_byok]` before pagination. Retains name order, page/scan caps, cursor CAS and all age/lease checks. | Removes completed/dead-letter BYOK history from each rotation; remaining reads scale with active BYOK rows, including fresh/live rows excluded later. Absolute production reduction is unknown; zero per-tick reduction is possible if active rows fill the cap. |
| `reconcile_listen_finalization_jobs` → `recover_stranded_byok_jobs` | Per-status age-ordered queries add `requires_byok == True` before the existing 50-row cap. | Removes non-BYOK queued/leased rows from the two rotating reclaim scans. Still up to 50 BYOK reads per status and the same cursor lookup/CAS work. Absolute reduction unknown. |
| `reconcile_listen_finalization_jobs` → `get_finalization_replay_candidates` | Unchanged: already queries `reconcile_after_at <= now`, capped at 100 rows. | Zero incremental reduction; already bounded by due jobs. |
| `reconcile_stale_processing_conversations` → `get_stale_processing_orphan_candidates` | Unchanged on and off: status-only processing group sweep. | Zero incremental reduction; legacy recovery remains complete. |
| `publish_all_queue_oldest_ready_ages` → finalization summary | Unchanged: finalization uses 16 fixed projection shard lookups and three indexed oldest-row queries, rather than a conversation scan. Other queue sampling remains owned by WQ3. | Zero incremental reduction for this lever. |

No lease code, transaction bodies, ownership fences, scheduler cadence, cursor
write helpers, or new work-queue writes were changed.

## Why two suggested blanket predicates are unsafe

- Processing orphans deliberately include documents with missing or unparseable
  `processing_admitted_at`; their first recovery action stamps the admission
  fence rather than terminalizing them. The current reader also accepts ISO and
  numeric legacy timestamp representations. An inequality excludes missing
  fields and cannot represent this parsing contract. Checking `deferred == False`
  or `finalization_job_id == null` would similarly exclude missing legacy fields.
  A complete replacement needs a separately scoped migration/queue design.
- BYOK last activity is the first parseable value of `byok_last_activity_at`,
  `updated_at`, then `created_at`. Reclaim intentionally preserves old live
  activity while updating bookkeeping. An `updated_at` age predicate would miss
  old abandoned sessions after reclaim; requiring a dedicated activity field
  would miss legacy jobs. The safe pushed-down predicate is active status.
- In-progress recovery refuses rows whose staleness clock is fresh, and since
  upstream e756385d462 the admission fence clocks v2-serving uids by
  `speech_clock` (`last_speech_at or finished_at`), with v2 serving suppressing
  legacy `finished_at` writes. A raw `finished_at` pushdown is therefore
  admission-equivalent only while no uid can serve lifecycle v2. The candidate
  gate withholds the pushdown whenever a v2 serve cohort can exist
  (`LIFECYCLE_V2_MODE=serve` or a configured shadow cohort, via
  `cohort_configured`), keeping this status-only scan the
  `finished_at`-agnostic catch-all for those rows. Dormant shadow (the flag's
  documented default: percent 0, no digests) and explicit off keep the
  pushdown. Scan-window counters now describe the narrower candidate window
  when enabled.

Firestore's documented inequality/existence behavior:
https://firebase.google.com/docs/firestore/query-data/queries#orderBy_and_existence

## Cursor and index behavior

The in-progress query uses timestamp order with Firestore's document-name tie
break. Snapshot cursors retain all ordering values. A pre-rollout cursor missing
or carrying a non-datetime finish stamp wraps to the top instead of failing to
construct the new cursor. Deleted cursors also retain the existing wrap behavior.
A surviving old cursor with a fresh finish can produce an empty tail; exhaustion
then wraps the persisted cursor for the next tick. Switching between old name
order and new time order can revisit/skip part of one rotation; coverage resumes
once the query shape is stable. The lever should be held at a stable cohort
through a full rotation when assessing discovery/read reductions.

The repository has no backend index YAML. Its authority is
`backend/database/firestore_index_registry.py`, generating root
`firestore.indexes.json`. Added three composites, all ASCENDING:

1. Collection `conversation_finalization_jobs`: `requires_byok, status, __name__`.
2. Collection `conversation_finalization_jobs`: `requires_byok, status, created_at, __name__`.
3. Collection group `conversations`: `status, finished_at, __name__`.

Registry and generated manifest are committed together. Query drivers execute
both lever states; scanner profiles include absent/present cutoffs and cursors.
Indexes must be applied and READY through the owning pipeline before enabling
this lever. This lane did not apply indexes or query production Firestore.

## Requested snapshot re-check

Read locally:
`/Users/dazheng/.hermes/state/loops/firestore-reads/snapshots/2026-10-22T01:00:46Z.json`.
Its payload timestamp is `2026-10-22T01:01:02Z`, caller window is `1h`, coverage is
`0.792`, and `missing_services` is empty. The following sums combine retained
Cloud Run `top_1h` and GKE `gke_top_1h` rows, without treating absent top-list rows
as zero. They are attributable baseline exposure, not measured savings or a
whole-fleet billing total.

| Database caller | Observed reads / 1h | 1h × 24 exposure |
| --- | ---: | ---: |
| `scan_in_progress_conversations` | 1,792,760 | 43,026,240 |
| `get_abandoned_byok_job_candidates` | 2,519,680 | 60,472,320 |
| `get_stale_processing_orphan_candidates` | 1,732,730 | 41,585,520 |
| `recover_stranded_byok_jobs` | 11,325 | 271,800 |

The first row includes backend-sync 906,551, backfill 690,000 and backend
196,209. BYOK includes backend-sync 880,060, backfill 680,134, backend 194,960,
integration 89,280 and backend-listen 675,246. Orphans include backend-sync
654,600, backfill 463,700, backend 152,100, integration 54,200 and backend-listen
408,130. Reclaim's retained row is backend-listen only.

No rollout readout is possible from this default-off local implementation.
After the owner applies indexes/deploys/enables the lever, compare these exact
callers over matched windows and inspect candidate/terminal discovery and error
metrics. Do not credit the unchanged orphan, replay, or queue-age paths with
savings from this change.

## Test evidence

Focused query tests: **21 passed** using `backend/.venv`.
The 19-file isolated backend run: **1,067 passed, 1 deselected**, exit 0.
It includes the new query tests, finalization/resilience/BYOK/orphan suites,
self-heal/recovery suites, lever registry, singleton and WQ1 lease recovery tests,
manifest tests, and all seven repository Firestore guards.

Commands (from the worktree root):

```sh
/Users/dazheng/workspace/omi/bin/omi-heavy run -- backend/.venv/bin/python -m pytest backend/tests/unit/test_finjob_candidate_queries.py -q
/Users/dazheng/workspace/omi/bin/omi-heavy run -- env BACKEND_UNIT_TEST_FILE_LIST=/Volumes/Ephemeral/scratch/wq13-unit-files.txt BACKEND_PYTEST_WORKERS=2 bash backend/test.sh
backend/.venv/bin/python backend/scripts/generate_firestore_indexes.py --write
```

The new tests prove inclusive staleness, lever-off query/order identity, cutoff
propagation, old/deleted/mutated cursors, timestamp ties and exhaustion, terminal
history exclusion, BYOK activity fallback/live-lease protection, reclaim past a
non-BYOK prefix, and retained legacy orphan discovery. The semantic query fake
applies filters before the limit and compares cursor values even when the cursor
row no longer matches. Controlled examples read 1 candidate rather than a
100-row excluded prefix; these are unit-test document counts, not production
billing estimates.

Logs: `/Volumes/Ephemeral/scratch/wq13-unit.log` and
`/Volumes/Ephemeral/scratch/wq13-preflight.log`.

Full preflight: **34 checks passed**, exit 0, in 210.73 seconds, using:

```sh
/Users/dazheng/workspace/omi/bin/omi-heavy run -- env OMI_PR_BODY_FILE=/Volumes/Ephemeral/scratch/wq13-pr-body.md make preflight
scripts/pr-preflight --lane local --pr-body-file /Volumes/Ephemeral/scratch/wq13-pr-body.md --metadata-only
```

The full run started against the working tree. After committing the implementation,
metadata validation passed all **4 checks**, including the exact line-count growth
declarations below. Existing warnings are advisory (deprecated dependencies,
legacy architecture budgets, and grandfathered policy/flag declarations).
The backend async-blocker check selected zero blocking findings, import purity
reported zero violations, and the generated manifest matched its registry.
No endpoint, live Firestore oracle, or production acceptance test was run: the
changed surface is background query discovery, verified hermetically here.
Rollback is the unchanged absent/zero lever state; no data rollback is needed.

## PR metadata handoff (no PR opened)

Suggested declaration: `Failure-Class: none` (cost/query optimization).
The oversized-file ratchet requires these exact growth declarations for the
query owner and index authority; draft metadata is validated locally:

```text
Line-Count-Exception: backend/database/conversation_finalization_jobs.py | 2728 -> 2772 | Keep the gated read-query variants with their existing caller and index ownership; transactional and lease behavior is unchanged.
Line-Count-Exception: backend/database/firestore_index_registry.py | 2206 -> 2243 | Keep the gated read-query variants with their existing caller and index ownership; transactional and lease behavior is unchanged.
```
