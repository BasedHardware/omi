# Record-seal repair: deadline priority, then newest first

This supersedes the ordering in [the November 9 change](2026-11-09-record-seal-age-order.md)
for Plan v3 L2 (David's newest-first / near-dead-letter-first ruling, reference
`6db8f2`). The urgency window is the final 24 hours before the **stored**
`record_dead_letter_deadline_at`; enqueue age never fabricates a deadline.
Pending jobs already past that deadline are included, while terminal jobs are
excluded by the existing state filter.

The jobs half of the existing first worker group scans ordinary pending jobs in
enqueue/name descending order every run, reserves their share, then scans urgent
jobs in deadline/name ascending order. Urgent jobs are attempted first.
Conversation discovery uses finish/name descending order.
Urgent jobs precede ordinary jobs and conversations, with duplicates removed.
The existing half-worker reservation for conversation discovery remains. This
does not increase the production worker count (16), row/run budgets, candidate
cap (1,024), or aggregate scan cap (10,000). The extra urgent page consumes up to
128 of that existing scan cap, rather than adding to it. All seal, privacy,
producer-proof and minimum-age eligibility checks remain unchanged.

The ordinary-job starvation bound is **one run between ordinary scans** when
jobs discovery is enabled and its existing shared discovery budget succeeds.
For job allocation `A = max(1, workers // 2)`, ordinary work reserves
`R = max(1, A // 4)` places when candidates are available. Urgent discovery is
capped at `A - min(R, ordinary candidates)`; unused ordinary reserve flows back
to urgency. At the production setting of 16 workers, that is 8 job places,
including at least 2 ordinary places despite a sustained urgent backlog, or
up to 8 urgent places when the ordinary pass is empty. Unused urgent capacity
is filled from the ordinary candidates already discovered. Duplicate paths
are attempted once. A single job place goes to ordinary work if available.

This fixes production-safety P2-1 and Luna's FIX-FIRST at `0711777f`.
Ordinary discovery precedes urgency so urgency cannot consume its query
opportunity. Candidates held beyond the selected ordinary share stay ahead of
the ordinary checkpoint, including when discovery reaches the end of a page.
The bound concerns discovery and reserved places in the first worker group;
proof refusal, discovery failure, budgets and run scheduling still prevent a
finite settlement or wall-clock guarantee. Conversation reservation remains.
Urgent discovery bounds the stored deadline to `> 0` and the final-day cutoff.
This uses the existing state/deadline/name ascending index; no new index is
required. Every examined row advances the encrypted scan position before
eligibility checks, including malformed rows. The urgent codec preserves raw
scalar query positions so a skipped clock cannot create an unreadable cursor;
ordinary enqueue cursors retain their existing numeric validation. Invalid
deadlines returned to the scanner increment the existing content-free
`invalid_clock_rows` aggregate and are never selected for urgent repair.
Values excluded by the query floor are not read or counted. A persistent full
malformed page cannot pin valid urgent jobs behind it: the floor reaches them
in one scan, and defensive cursor progress reaches them on the next scan even
when an adversarial projected page bypasses that floor.

Recency scans retain a frozen horizon and wrap so sustained new inflow cannot
strand the tail. The deadline scan can expand its upper boundary on resume:
newly urgent jobs have later deadlines and cannot prevent progress through the
earlier ones. All three encrypted frontiers checkpoint before proofs and after
actual attempts; preview writes none. New recency frontier names end in `v2`
so an old ascending cursor cannot skip newer work after the ordering change.
The old frontier documents remain available to an older binary on rollback.

The batch index registry and generated manifest add newest-job and deadline-job
indexes for both stages, plus a newest-completed conversation-group index.
The existing deployment readiness gate must confirm these indexes before
shipping the new image. No index apply or production deployment was performed.
Ordinary recency discovery retains its missing-index fallback to hash order;
an unavailable urgent index skips only the urgent leg, emits a content-free
`index_unavailable` event and shared degraded fallback telemetry, and allows
ordinary and conversation discovery to continue with a successful run. The
`gcp_diarizer.yml` batch-pipeline-worker path now enforces the shared readiness
gate against the selected source SHA before building or deploying the image.

Rollback the jobs priority with `RECORD_SEAL_REPAIR_AGE_ORDER=off`: this skips the
urgent scan and restores the original hash query. Code rollback restores the
previous conversation ordering and its untouched frontier. Neither rollback
changes custody or deletes recordings. The CPU, placement and bytecode changes
are independently reversible through the chart values or a code revert.


## CI import-order and workflow corrections

Evidence recorded 2026-11-10T19:28:30+00:00 on m1-mac-studio, after merging `origin/main`
`7ebd8450b6e023474cfe3275cf3446b28f3a710f` into the PR branch.
The complete logs from run `42879396660` showed PR-triggered regressions;
the earlier description of them as unrelated was incorrect.

- The workflow's service-only predicates were unsupported by the existing
  Firestore shipment policy. Both the sparse controls checkout and gate are
  now unconditional, and `_LANE_SOURCE_BINDINGS` registers the actual
  `${{ steps.vars.outputs.source_sha }}` expression. The policy is unchanged.
- `require_http_stage()` imports HTTPException only in its invalid-stage
  exception branch. Successful stage checks and the row entrypoint continue
  to exclude FastAPI/Pydantic/Starlette; five subprocess contracts verify this
  and the HTTP 503 path.
- Cold-import tracing of the merge test found `database.conversations` →
  `utils.other.storage` → `utils.cloud_tasks` → FastAPI inside the test body.
  Earlier framework warming had hidden that load. The real visibility
  dependency is now a module-scoped fixture, so setup owns its import and the
  unchanged 1.00-second call-phase guard measures rollback/visibility work.
- The multipart failure reproduces with the sync-preferences file alone. Its
  own scoped fixture installed a plain `ModuleType('python_multipart')`,
  hiding the installed exceptions submodule after the import-order change.
  The unnecessary multipart fake is removed; the existing isolation context
  still restores the other fakes. CI runs each file in its own Python process.
  The action-items fallback mentioned during diagnosis already cleans up in
  `finally` and skips installation when the real package is available.
- The apparent Gacrux-desktop failure was interleaved workflow-test output.
  The voice file's own old CI summary is 119 passed, and its isolated baseline
  and corrected runs each pass all 119 tests. Voice code is untouched.

Repo-runner verification (Python 3.11.15):

| Measurement | Before correction | After correction |
| --- | --- | --- |
| Workflow contracts | 2 failed / 95 passed | 98 passed |
| Sync preferences | 59 setup errors | 59 passed |
| Merge rollback filler-only call CPU | 0.575309 s | 0.000652 s |
| Focused regression selection | mixed failures above | 344 passed |
| Original CI shard 3 | timing failure in CI | 345 files, exit 0 locally |
| Original CI shard 8 | workflow and multipart failures in CI | 345 files, exit 0 locally |

The CPU samples come from the existing repo guard's `_test_item_cpu` values,
read by a temporary reporting plugin; fixture/setup still pays the dependency
import. No timing threshold or allowlist changed.

Both complete local shard manifests exactly match the file sets extracted
from the old job logs (jobs `130051305085` and `130051305033`). Their launch
order is the unchanged `run-unit-ci.sh` LPT schedule over the original
2,741-file changed-path selection, including its workflow-contract extra and
shard-1 typecheck reservation. Plain `--all` selects 2,740 files and therefore
produces a different deal; it was not used for the final reproduction.
Manifest SHA-256:

- Shard 3: `bd8d7ef206c78476156f4143282cc75c72c66155e949cb761e6926a90029a74f`.
- Shard 8: `8557c8854d15d4fd9bcf615bc4839b76b3081f3f82fbe900f03b5ff4eafc7ea8`.

Each complete shard used `backend/test.sh` with its explicit
`BACKEND_UNIT_TEST_FILE_LIST`, `BACKEND_PYTEST_WORKERS=4`,
`BACKEND_PYTEST_FILE_ISOLATION=1`, warning/failure CPU limits 0.1/1.0 seconds,
and `BACKEND_UNIT_FILE_BUDGET_SECONDS=3600`, under `omi-heavy`, with
`GOOGLE_APPLICATION_CREDENTIALS`, `CLOUDSDK_CONFIG` and
`CLOUDSDK_CORE_ACCOUNT` unset. `actionlint gcp_diarizer.yml` and
`git diff --check` also pass. This is hermetic local evidence; no deployment,
index apply or production data access was performed.


## Ordinary reserve verification

The Luna follow-up merges main without rebasing; L1 #25018 was still open at
that fetch. Regression tests use the real bounded query and encrypted cursors
across three runs with an urgent backlog larger than the job allocation.
They assert the ordinary reserve each run, deadline-first urgent attempts,
conversation capacity, and the pre-attempt checkpoint retaining deferred
ordinary candidates. An exhausted ordinary pass returns its whole allocation
to urgency. Coverage includes 2, 4 and 16 workers, including a one-place job
allocation. The shared scan cap still accounts for one page per job leg.

Verification recorded 2026-11-10T20:21:16+00:00 on m1-mac-studio after merging main
`85de1985f0fb4fddd05e0de4b36c1ac68108d81e`: all 15 record-seal unit files
ran through `backend/test.sh` under `omi-heavy`, with credential variables
unset, file isolation, four file workers, a 3,600-second per-file budget and
the unchanged 0.1/1.0-second CPU warning/failure guards. Result: **436 passed,
3 skipped** (Firestore emulator tests without an emulator). This includes all
35 priority tests, 136 coordinator tests and five row import-graph contracts.
No production or emulator service was started.


## Malformed urgent-prefix follow-up

Luna's FIX-FIRST on earlier head `7c214814` identified that the previous
all-malformed test replaced the bad rows before its next scan. That test is
retained with readable advancing cursor assertions for all malformed scalar
cases. A new persistent-prefix regression keeps 128 zero/negative deadlines
in place with valid urgent work behind them. It checks the real query floor
and, separately, an adversarial projected page to verify two-run encrypted
cursor progress and invalid-clock counts. Coordinator tests also verify those
counts are added to the existing summary metric without selecting bad rows.

Verification recorded 2026-11-11T00:26:25+00:00 on m1:
`backend/test.sh` under `omi-heavy` passed **1,310 tests** across all 15
record-seal files, the canonical seven Firestore query guards and flag budget.
Three emulator tests skipped without an emulator, and the standard runner
deselected one slow-marked query guard. The priority file passed all 39 cases,
including the four persistent-prefix cases and retained saturated-page cases.
The earlier reserve batch's priority-file subtotal is corrected to 35;
its recorded total of 436 is unchanged. The Firestore manifest generation
check also passes without registry or manifest changes. Credential variables
were unset; file isolation, four file workers, the 3,600-second per-file budget
and unchanged 0.1/1.0-second CPU warning/failure guards were used.
