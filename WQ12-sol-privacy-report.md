# WQ12: batch privacy reads

Implemented on `lane/firestore-reads-wq12-privacy` in
`/Volumes/Ephemeral/scratch/worktrees/omi/omi-lane-fsr-wq12`, based on
`e8f6db2f2590` (`origin/main` at task start).

## Measurement and caller findings

Inventoried all Python references with
`rg -n 'assert_batch_write_allowed' backend --glob '*.py'`, then traced
`FirestoreTransaction.check_privacy` / `flush`, projection session preparation
and plan validation, admission, retention, recovery, enrichment, summary repair,
and completed-status reconciliation.

The triage hypothesis is only partly correct: there is no single control-doc
lookup per write. A successful assertion performs **3 + 2D document reads**,
where D is the number of distinct conversation documents visited, including
redirect targets. Missing documents are real point reads too.

| Document read, in order | Authority |
| --- | --- |
| `account_deletions/{uid}` | Account-deletion existence and `wipe_status`; only cancelled/billing_failed markers permit access |
| `users/{uid}` | Account existence, protection level, migration, recording cloud-sync setting |
| `batch_pipeline_privacy/{sha256(uid)}` | Durable generation, blocked and purging state |
| `users/{uid}/deleted_conversations/{conversation_id}` | User-deletion tombstone, checked before each conversation |
| `users/{uid}/conversations/{conversation_id}` | Deletion/redirect state and recording-specific privacy |

Failures stop at their original read and reason. An assertion without
conversations costs three reads; a single source without redirects costs five.
Converging redirect walks are already deduplicated within one assertion on main.

`flush()` already deduplicates job/result guards by
`(owner_id, conversation_id, privacy_generation)`. It does not call the assertion
once per physical write. Explicit body checks and flush checks can nevertheless
read the same authorities again. Projection's prepare and validate callbacks
also repeat owner/source reads in the same transaction.

These are **measured hermetic caller counts**, not new production telemetry.
The daily origin estimate in the brief was not remeasured; no GCP was used.

| Exercised path | Assertions / writes | Privacy reads OFF → ON | All document reads OFF → ON |
| --- | --- | --- | --- |
| Real `admit()` call, 20 segments, distinct sources, active scheduler shard | 20 / 24 = **0.8333 per write** | **100 → 43** | **124 → 67** |
| Transaction view: 20 body checks, 20 job + 20 result writes, distinct sources | 40 / 40 = **1 per write** | **200 → 43** | **220 → 63** |
| Same transaction-view batch, one shared source | 21 / 40 = **0.525 per write** | **105 → 5** | **125 → 25** |
| Singleton view: body check, job + result writes | 2 / 2 = **1 per write** | **10 → 5** | **11 → 6** |
| Projection prepare + plan validation + one receipt update | 2 / 1 in this fixture | **14 → 9** | **18 → 13** |

The real admission fixture executes `database.batch_pipeline_intake.admit`,
`Scheduler.enqueue_in_transaction`, `FirestoreStore.run` and `flush` using the
strict Firestore transaction fixture. Its 24 writes comprise 20 jobs plus queue,
control, owner and content. Its 24 non-privacy reads are unchanged. The shard is
seeded active so this document-only fixture does not need the unrelated
service-frontier query. Before/after stored payloads compare equal. A separate
fixture measures job/result flush deduplication and body rechecks explicitly.

Real admission saves 57% of privacy reads (46.0% of all reads) in this example.
Single-assertion transactions gain nothing. Separate transactions still reread
everything, so these percentages must not be applied to all 125–135M daily reads
without observing the production mix.

## Mechanism and default-off behavior

- Added only `batch_privacy_memoize` to `KNOWN_LEVERS`; absent key is 0. No runtime
  `FIRESTORE_READ_LEVERS` setting, deployment configuration or other lever changed.
- `BatchPrivacyMemo` stores successful document snapshots, including absence, by
  full path. It is explicitly bound to one client and transaction, and rejects
  mismatched clients/transactions and nontransactional construction. Read errors
  propagate without being cached.
- `FirestoreTransaction.check_privacy` creates its memo only for an enabled uid.
  Flush shares that memo; `FirestoreStore.run` creates a fresh transaction view
  on every callback attempt.
- `ProjectionSession.prepare` starts a fresh memo on every invocation, including
  retries on the same SDK transaction object. Subsequent guard/validate calls
  share it. The session can survive the precheck, but its memo cannot survive
  another prepare. Lever-off preparation removes any previous enabled memo.
- Assertions still run in full: expected-generation comparisons, owner policy,
  source/redirect checks, per-call cycle detection, the 256-document walk budget,
  exception reasons and snapshot outputs are preserved. Only repeat physical
  reads are eliminated. A newly introduced source always gets checked.
- With the lever absent/zero, original reads occur in their original order,
  including repeat and missing-document reads; no memo is allocated by callers.
  Explicitly supplied memos are also ignored when off. No middleware, request
  dependencies, executors, ContextVars or FastAPI teardown were added or changed.

No serving query shape was added: every optimized operation remains a
transaction-bound document-reference get. Inspected the current split registry
(`firestore_query_driver_registry.py` imports the batch/privacy driver modules);
no driver entry or index change is required.

## Staleness and deletion safety

**No TTL and no added cross-transaction staleness window.** Scope is narrower
than a job: the read phase of one transaction callback attempt. A job can span
many transactions, and each must read the privacy authorities afresh.

The first real get of every distinct authority still occurs in the same
Firestore transaction as the mutation. Reusing its snapshot does not remove
that document, or a missing document's absence, from transactional conflict
validation. A deletion/protection mutation during an attempt must serialize
with or invalidate that attempt; the optimization never authorizes a later
transaction using an earlier transaction's allow decision. Concurrent writes
retain the existing transaction ordering semantics.

Retry tests use the real Firestore SDK transactional decorator and inject
`Aborted` at commit. They deliberately reuse the same transaction object and
retry ID, mutate account-deletion/generation/conversation tombstone state, and
verify that both scheduler views and reused projection sessions reread and deny
on retry. These tests prove callback reset and denial behavior; the strict fake
does not simulate server contention/locking. No emulator or production canary
was run, and no deployment or runtime savings are claimed.

## Verification

All test commands ran via `/Users/dazheng/workspace/omi/bin/omi-heavy run --`,
using this worktree's `backend/.venv/bin/python`. Regression files were finally
run in separate pytest processes, as required by backend test-isolation guidance.

| `python -m pytest backend/tests/unit/<file> -q` | Result |
| --- | --- |
| `test_fsr_wq12_batch_privacy.py` | **43 passed** |
| `test_batch_privacy_conversation_fence.py` | **15 passed** |
| `test_firestore_read_levers.py` | **9 passed** |
| `test_batch_pipeline_scheduler.py` | **42 passed** |
| `test_batch_pipeline_projection.py` | **45 passed** |
| `test_batch_pipeline_intake.py` | **44 passed** |
| `test_batch_pipeline_shadow.py` | **26 passed** |
| Focused/regression total | **224 passed** |
| `test_firestore_query_shapes.py` | **495 passed**, 13 existing dependency deprecation warnings |

Additional validation: staged Python formatting and `git diff --check` passed.
`make preflight` is being completed before the local commit; its final outcome
will be recorded here. `scripts/pr-preflight --suggest --lane local` found no
required product invariant citation. The commit uses `perf:` for this read-cost
optimization. No PR is being opened.

## Files touched

- `backend/config/firestore_read_levers.py`: register the default-off lever.
- `backend/database/batch_pipeline_privacy.py`: scoped snapshot memo and optional
  read reuse while preserving the fence evaluation.
- `backend/database/batch_pipeline_store.py`: share memo across body and flush
  checks in one transaction view.
- `backend/database/batch_pipeline_projection_session.py`: share prepare/plan
  snapshots and reset them on every prepare attempt.
- `backend/tests/unit/test_fsr_wq12_batch_privacy.py`: read counts, real admission,
  output parity, denial parity, isolation, retry, walk-budget and failure tests.
- `WQ12-sol-privacy-report.md`: this report.

GCP tier: **none**. No push, PR, merge, deployment or lever activation performed.
The existing untracked `wq12-sol-prompt.md` and `wq12-sol-request.json` are left
untouched and excluded from the commit.
