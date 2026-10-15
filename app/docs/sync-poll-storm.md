# Mobile sync polling storm: root cause and lane handoff

Evidence date: 2026-10-11. Repository: BasedHardware/omi. Lane base:
`3ff45c29874b`. No production calls, infrastructure edits, publication, or
release were performed. Production traffic figures below come from the task
brief; implementation conclusions come from current code and hermetic tests.

## Proven failure mechanism

`LocalWalSyncImpl.reconcileUploadedWals` originally fetched **every uploaded
job on every invocation**. Its limit of three was concurrency, not a request
budget. `SyncReconciler.poke` has no elapsed-time admission check: the 20–120s
timer schedules an additional wake but does not constrain other wakes.
`RecordingTransferCoordinator._runPassBody` calls reconcile before drain and
again when drain leaves uploaded jobs. Serial/coalesced wakes therefore still
multiply backlog size by pass count. The Transcribe Later provider also has a
15s periodic reconcile, originally without overlap or aggregate admission.

The regression `50 pending jobs and five serial wakes cannot produce 250
polls` uses the real coordinator, real WAL reconciler, a fake clock, and a
processing HTTP-result seam. Five serial socket-reconnected wakes at 10s
intervals produced **250 requests in 50s** against the original lane-base WAL
implementation. Output: `Expected: <=18; Actual: <250>`. The original file was
loaded with `git show HEAD:app/lib/services/wals/local_wal_sync.dart`
(`HEAD` was still the supplied `3ff45c29874b` base); an
unreachable `throttled` switch arm was added solely to compile against the new
enum. The fixed file was restored in `finally`. The same test passes with the
fix and is included in the ordinary test suite.

Poll 429s originally mapped to `transient` and kept WALs uploaded. Only the
upload gate applied the rate-limit cooldown. Consequently the next wake polled
the same jobs again despite an active upload cooldown. Unscoped 429s were
classified as backend capacity, which explains the misleading global busy
banner even when the throttle is at the edge.

A 404 immediately cleared the job ID, marked retained audio `miss`, and spent
a retry. The next drain uploaded the bytes again. A 409
`sync_content_in_progress` then became a generic `SyncUploadHttpException`,
counting as a failed upload and causing coordinator recovery retries. This
is not evidence that the original audio failed processing.

There is also a concrete lifetime gap: `database/sync_jobs.py:42` retains a
job result for **24h**, refreshed on mutation, while
`database/sync_ledger.py:17` admits a competing content owner only after
**48h**. The WAL has no maximum uploaded lifetime and can outlive the Redis
result. `test_expired_job_can_still_have_a_live_content_owner` proves that a
claim at 24h + 1s still returns busy without changing the owner. A missing GET
then a busy duplicate POST is therefore a valid protocol outcome. The status
route also returns 404 for absent or malformed Redis records. These sources
explain the possible paths; identifying which path produced the particular
production 618 missing responses requires job-level server evidence and was
not established here. The 409 route deletes its *new, rejected candidate* job;
the old app does not adopt that candidate, so that delete alone does not explain
its polled 404 IDs.

## Introducing changes and release evidence

- `5aa9460b7d11` (May 20): introduced unbudgeted reconcile fan-out and immediate
  404 recovery. `e222caa5099f` introduced the on-demand/timer scheduler.
- `2dfbb03a11a5` (July 14, centralize recording recovery): attached reconciliation
  to event-driven coordinator passes. The timer is not a gate on those passes.
- `0ad5c9b076d7` (July 10, isolate bounded historical recovery): introduced the
  48h content claim. `aa30548d9db0` set the 24h query window in May.
- `fe5d07056566`, **#20837** (Oct 6 19:49Z): expanded periodic and reconnect
  background recovery to discover/drain the whole backlog, adding an
  amplification path. Android foreground-task repeats send this wake every
  five minutes; it is not a seconds-frequency producer by itself.
- `17682e2b` (#20882) changes capture pause/encoding; `f3f67b41` adds stale-WAL
  telemetry and phone capture recovery; `636651f8` (#20638) flushes custody test
  writes; `b92a4d2a` changes calendar gap filtering. None adds the all-job GET
  loop. These changes do not independently prove the measured onset.

The fetched Android tag `v1.0.558+1400-android-cm` at `a7127cc56483`
(Oct 8 18:13Z) contains #20837 and the other October candidates. The Oct 6
`v1.0.555+1374-android-cm` tag does not contain #20837. The available iOS tag
`v1.0.560+12392-ios-cm` points to Sept 25. Tags prove build source contents,
not store rollout or which binary was installed on the affected phones.
Codemagic resolves build name/number from the release plan, not the pubspec
placeholder. There is insufficient fetched release evidence to assign the
Oct 7 12–18Z incident onset to one shipped build with certainty.

## Fix

- One shared `SyncJobPoller` for WAL and Transcribe Later: one pass in flight,
  at most **18 GET attempts per rolling minute**, reserved before await; one
  request per job in flight; at least **20s** between requests for a job.
  Oldest due jobs go first so a large backlog progresses. Stale scheduler
  entries are pruned after a day.
- Preserve and honor upload/status `poll_after_ms` hints above that minimum.
  Transient responses and thrown fetches back off per job for at least 60s.
- Serialize a WAL pass's requests so a poll 429 installs the account cooldown
  before another request starts. Both polling owners and the upload gate honor
  that cooldown. Retry-After and the existing 30-minute absent-header default
  remain. A concurrent successful upload cannot clear an edge cooldown.
- Require two missing reads separated by five minutes before returning retained
  audio to `miss`; expiry spends no processing retries and never deletes audio.
- Add `job_id` and `poll_after_ms` to the existing 409 body, preserving status,
  code, detail and Retry-After for shipped clients. New clients adopt that
  existing content owner and remain uploaded rather than resending bytes. With
  an old server that omits the ID, pause at least 60s without spending retries or
  emitting a processing-failure event.
- Explicit fair use and capacity remain distinct. Unclassified edge throttles
  use `syncCardThrottlePaused`: “Syncing paused briefly — it will resume automatically”.
  Added through `scripts/l10n.py` across all 49 locales; generated Dart refreshed.

Changed implementation: `app/lib/backend/http/api/conversations.dart`,
`app/lib/backend/schema/conversation.dart`,
`app/lib/providers/local_recordings_provider.dart`,
`app/lib/pages/conversations/sync_cooldown_copy.dart`,
`app/lib/services/wals/{local_wal_sync,sync_job_poller,sync_job_policy,sync_rate_limiter,sync_upload_gate}.dart`,
`backend/database/sync_ledger.py`, `backend/routers/sync.py`,
`backend/utils/sync/admission_responses.py`. Existing terminal policy and busy
response construction are extracted to their owning small modules so oversized
product files shrink rather than requiring a line-count exception.
Tests: `app/test/unit/{sync_poll_storm,sync_rate_limit_response}_test.dart`,
`backend/tests/unit/{test_sync_two_lane,test_sync_cloud_tasks}.py`,
`app/test/unit/sync_job_terminal_policy_test.dart` (migrated import), and
`app/test/widgets/sync_edge_throttle_render_test.dart`.
Metadata: mobile changelog fragment and the failure-class definition
`FC-event-wakes-bypass-request-cadence` with the regression as its guard artifact.

## Verification of initial commit

Run from `app/`:

```sh
bash test.sh test/unit/sync_poll_storm_test.dart test/unit/sync_rate_limit_response_test.dart test/unit/sync_upload_gate_test.dart test/unit/wal_unsupported_audio_terminal_test.dart test/unit/sync_paced_backfill_backoff_test.dart test/unit/sync_cooldown_copy_test.dart test/unit/local_recordings_owner_test.dart test/unit/local_recordings_auto_upload_test.dart test/unit/sync_job_terminal_policy_test.dart test/widgets/sync_edge_throttle_render_test.dart test/services/wals/recording_transfer_coordinator_test.dart
bash scripts/analyze_ratchet.sh
```

Direct focused `flutter test --no-pub ... --reporter expanded` output:
`00:02 +106: All tests passed!`. Analyzer: `Analyzer ratchet passed.`
Initial setup failed because build_runner captured an intermediate constructor
syntax error; after correction `flutter pub run build_runner build` completed.
Initial test fixture compilation/assertions were corrected and rerun. No failed
attempt is counted as a passing verification.

Run from repository root:

```sh
printf '%s\n' tests/unit/test_sync_two_lane.py tests/unit/test_sync_cloud_tasks.py > /tmp/omi-sync-backend-tests.txt
BACKEND_UNIT_TEST_FILE_LIST=/tmp/omi-sync-backend-tests.txt BACKEND_PYTEST_XDIST=0 bash backend/test.sh
backend/.venv/bin/python backend/scripts/scan_async_blockers.py --dirs backend/routers backend/utils
make mobile-verify ARGS='fast --paths app/lib/services/wals/local_wal_sync.dart app/lib/providers/local_recordings_provider.dart'
OMI_PR_BODY_FILE=/tmp/omi-sync-pr-body.md make preflight
```

Backend output after extraction: `39 passed in 0.62s`;
`108 passed, 52 warnings in 2.98s`.
Warnings include existing deprecated FastAPI regex and mock coroutine warnings.
Async scan: `Selected blocking findings: 0`.
App wrapper result: protected spine `+138: All tests passed!`; focused suite
`+105: All tests passed!`; the final direct focused run adds the concurrent
cooldown regression and passes 106 tests. Selected mobile journeys: `executed: 23, passed: 23,
failed: 0, skipped: 0`. Draft metadata validation: `PR preflight passed: 5 checks in 2.71s`. Full local
preflight: `PR preflight passed: 41 checks in 167.67s` (exit 0). UI screenshot,
file-size, invariant, failure-class, backend compatibility/isolation/source
closure and the other selected repository checks passed without exceptions.
The actual Offline Sync page is also rendered with hermetic provider fixtures
and bundled fonts by `sync_edge_throttle_render_test.dart`. Its screenshot lives
at `.agent-artifacts/ui-evidence/sync-poll-storm/001-mobile-ios-sync-edge-paused.png`
and was visually inspected. Screenshot command from `app/`:

```sh
flutter test --no-pub --dart-define=OMI_SYNC_UI_EVIDENCE_DIR=../.agent-artifacts/ui-evidence/sync-poll-storm test/widgets/sync_edge_throttle_render_test.dart --reporter expanded
```

Output: `+1: All tests passed!`. These are hermetic checks and widget-render
acceptance, not an installed phone, agent-flutter session, live-server smoke,
CI or production acceptance.

## Independent review follow-up

The review of `943f8c13b1ff` returned SHIP-WITH-FIXES. All four requested
findings are addressed in a separate commit:

- Replace recording-status `paused` copy with the localized sync-specific key.
- On a busy ledger claim, read the owning Redis job. If absent, re-read the
  ledger in a transaction and take over only that same missing owner. Preserve
  completed results and concurrent new owners, clear stale run bindings, and
  retain processing checkpoints. Redis errors propagate rather than authorize
  takeover. The unchanged HTTP route now admits recovered claims normally;
  live-owner 409 status/code/Retry-After and additive fields remain compatible
  with shipped apps. Client session tombstones prevent adopting a confirmed
  missing owner returned by older servers; this pauses without spending retries.
- After confirmed 404, Transcribe Later saves its cleared sidecar, refreshes
  retained files, and runs the ordinary sequential auto-upload selector. Manual
  Transcribe Later files remain manual. Auto-fallback files are re-queued.
- Regression coverage runs the provider's actual 15s periodic timer and WAL
  event passes against `SyncJobPoller.instance`, checks the combined rolling
  18/min bound, advances the actual limiter's injected clock through the 120s
  throttle expiry, verifies retained auto files are uploaded again after 404,
  rejects dead 409 owners, and verifies adopted WALs stay uploaded through
  processing and become synced only on completed. Server tests cover missing
  owner takeover before 48h, live-owner preservation, concurrent ownership and
  completion, Redis failure, and unchanged live-owner 409 responses.

Follow-up verification (from `app/`, same focused file list shown above):

```sh
bash test.sh test/unit/sync_poll_storm_test.dart test/unit/sync_rate_limit_response_test.dart test/unit/sync_upload_gate_test.dart test/unit/wal_unsupported_audio_terminal_test.dart test/unit/sync_paced_backfill_backoff_test.dart test/unit/sync_cooldown_copy_test.dart test/unit/local_recordings_owner_test.dart test/unit/local_recordings_auto_upload_test.dart test/unit/sync_job_terminal_policy_test.dart test/widgets/sync_edge_throttle_render_test.dart test/services/wals/recording_transfer_coordinator_test.dart
bash scripts/analyze_ratchet.sh
python3 scripts/l10n.py check
flutter test --no-pub --dart-define=OMI_SYNC_UI_EVIDENCE_DIR=../.agent-artifacts/ui-evidence/sync-poll-storm test/widgets/sync_edge_throttle_render_test.dart --reporter expanded
```

Results: protected spine `+138: All tests passed!`; focused suite
`+109: All tests passed!`; `Analyzer ratchet passed.`;
`ok: 49 locales, 3825 keys`; screenshot `+1: All tests passed!` and visually
inspected with the sync-specific two-line title. Localization was added with
`python3 scripts/l10n.py add syncCardThrottlePaused --before syncCardBackendBusy --en 'Syncing paused briefly — it will resume automatically' --description 'Offline Sync cooldown after a temporary request throttle; syncing resumes automatically, recording is unaffected.' --translations /tmp/omi-sync-throttle-translations.json`;
output `added syncCardThrottlePaused to 49 locales`.

From repository root:

```sh
printf '%s\n' tests/unit/test_sync_two_lane.py tests/unit/test_sync_cloud_tasks.py tests/unit/test_sync_repeat_failure_cap.py tests/unit/test_sync_assignment_recovery.py tests/unit/test_sync_v2.py tests/unit/test_recover_dev_failed_sync_backfill.py > /tmp/omi-sync-followup-backend-tests.txt
BACKEND_UNIT_TEST_FILE_LIST=/tmp/omi-sync-followup-backend-tests.txt BACKEND_PYTEST_XDIST=0 BACKEND_PYTEST_WORKERS=1 bash backend/test.sh
backend/.venv/bin/python backend/scripts/scan_async_blockers.py --dirs backend/routers backend/utils
OMI_PR_BODY_FILE=/tmp/omi-sync-pr-body.md make preflight
```

Backend serial result: **422 passed** across six isolated files:
`43 passed in 0.50s`, `108 passed, 52 warnings in 2.68s`,
`20 passed, 14 warnings in 2.93s`, `59 passed, 14 warnings in 3.16s`,
`182 passed, 60 warnings in 3.30s`, `10 passed in 0.53s`. Existing regex and
mock coroutine warnings remain. The preceding parallel run passed all
assertions but failed the existing CPU guard on a v2 test at 0.31s versus the
unchanged 0.30s limit. The serial rerun passed without allowlist or limit changes.
Async blocker scan: `Selected blocking findings: 0`.

The first stricter timer fixture failed to advance the timer created after
real directory IO; a subsequent join across virtual/IO zones stalled. The
corrected fixture puts the actual periodic Timer in the widget clock's zone,
flushes IO/microtasks, and never invokes the provider reconciler to drive ticks.
Its isolated final run passed 13 tests, followed by the passing full focused
run above. No failed or stalled attempt is counted as passing verification.
The first committed-head preflight failed its synthetic-merge check because
upstream had concurrently appended localization keys at the same end-of-catalog
location. A tested `--before` option was added to the official localization tool, and
the key was removed/re-added through `scripts/l10n.py` beside
`syncCardBackendBusy`, regenerating Dart. No generated Dart was hand-edited.
`bash test/shell/l10n_tool_test.sh` passed, including positioned insertion,
English metadata placement, byte-identical repeat, and refusal without writes
when the insertion anchor is absent.
This keeps the feature diff independent of unrelated upstream work. The reordered-source preflight passed `42 checks in 207.67s`. Preflight is
rerun after committing the tool/fixture follow-up; the final lane report records
that final SHA and outcome.

## Generated response contract follow-up

The full backend suite exposed two raw 409 response decoders added by this
branch. `SyncContentInProgressResponse` now declares `code`, optional `job_id`
and optional `poll_after_ms` in the v2 upload's OpenAPI 409 response. The job
status response also declares its optional poll hint. The repository generators
produce the Dart and TypeScript wire types; both 409 helpers decode through
`GeneratedSyncContentInProgressResponse`, and the job status adapter projects
all cadence/throttle metadata through `GeneratedSyncJobStatusResponse`.
Legacy responses without owner/hints retain their paced-conflict behavior.
No schema inventory exemption or allowlist was added.

Verification from repository root:

```sh
printf '%s\n' tests/unit/test_app_client_schema_inventory.py > /tmp/omi-sync-schema-tests.txt
BACKEND_UNIT_TEST_FILE_LIST=/tmp/omi-sync-schema-tests.txt bash backend/test.sh
backend/.venv/bin/python backend/scripts/generate_dart_models.py --group conversation --check
backend/.venv/bin/python backend/scripts/check_app_client_openapi_compatibility.py --base-ref origin/main
bash backend/test.sh
OMI_PR_BODY_FILE=/tmp/omi-sync-pr-body.md make preflight
```

The inventory reproduction failed with **1 failed, 12 passed** before the fix,
then passed **13 tests** after regeneration. Generated Dart freshness and
released app-client OpenAPI compatibility checks passed. The focused Dart
command above passed the **138-test protected spine and 112 sync tests**, including
409 owner/hint decoding, omitted-field compatibility and metadata projection;
the analyzer ratchet passed. The final lane report records the full backend
suite and committed-head preflight results, including comparison of any backend
failures against a detached origin/main worktree with its own locked venv.

## Full-app CI replay timing follow-up

The CI merge checkout added main's empty-completion diagnostic test. Current
main was merged into the lane before reproducing the four failures, so local
verification includes that test and the full merged app suite.

All four failures are timing artifacts, not stranded production terminal jobs:

- The persisted/enqueued/acknowledged replay attempted both its processing poll
  and completed poll at the upload's original timestamp. A queued upload
  explicitly defers its first poll by its hint (20 seconds by default), and a
  processing response starts another minimum interval. Advancing the replay
  clock at both boundaries reaches `synced` without another upload.
- The invalid-input replay attempted its terminal poll at the upload timestamp.
  Advancing the upload deadline earns `unsupportedAudio`; every wake remains
  unable to re-upload it, and deliberate retry still earns the same verdict
  after that retry's deadline. All original retained-byte assertions remain.
- The transient-failure replay attempted both failed-job verdicts before their
  upload deadlines. It now observes each eligible verdict before the next
  coordinator drain: retry count remains exactly one, then two, for two uploads.
- The empty-completion diagnostic test had no upload deadline: its first poll
  is immediate, but its second same-time pass cannot repoll. The injected clock
  advances exactly 20 seconds for completion, preserving its original ACK
  timestamp, file persistence, retry accounting and diagnostic assertions.

All four use an injected job-status fetcher, which gives each WAL owner a
private poller; global request-budget leakage did not cause these failures.
Replay fixtures now clear the shared limiter, align its clock, reset singleton
poller state on first boot, and restore both on teardown. Local-WAL fixtures
also reset these shared test dependencies. Additional regression tests prove
that restored jobs poll immediately, explicit upload hints defer first polls
without being extended by skipped wakes, and the singleton reset clears
budget, deadlines and confirmed-missing owner tombstones. Production admission
and terminal handling are unchanged.

The local CI command is taken from
`.github/workflows/mobile-app-checks.yml` (`Dart Analyze & Tests`): Flutter
3.44.5, `flutter pub get`, hermetic compile inputs, `dart run build_runner build
--delete-conflicting-outputs`, `bash scripts/analyze_ratchet.sh`, then the full
`bash test.sh --reporter expanded --file-reporter json:<results-file>` with
pipefail and output capture. Plain `flutter analyze` is also run as requested.
The final report records exact commands, analyzer diagnostics, full-suite totals,
committed-head preflight and pushed-ref verification.

## Residual risk and production acceptance

Budgets and transient cooldowns are process-local, as before; relaunch gets a
fresh budget. Very large backlogs now take longer to reconcile (roughly three
minutes for 50 unique jobs before timer/backoff/HTTP latency); expired jobs add
at least five minutes to recovery. A lost Redis owner still requires paced
recovery from local bytes. The exact production missing-job cause and the
mobile version associated with onset remain unverified. The backend additive
owner response and mobile handling both need coordinator-led releases.

For the upgraded build, check GET requests per auth/device cohort at
`/v2/sync-local-files/ID`: <=18/min during steady process lifetime, with no
additional polls during a returned throttle cooldown. Compare LB
`denied_by_security_policy` for these GETs and collateral conversations /
action-item / fair-use requests. Track duplicate POST `sync_content_in_progress`
share, pending uploaded age, completed-job/conversation surfacing and sync
latency together; lower requests alone must not hide stranded recordings.

An upgraded active phone should improve in its first session; allow up to the
existing 30-minute throttle plus several minutes to drain typical backlogs.
Fleet totals should improve with adoption, provisionally over 24–72h after
mobile rollout, not merely backend deployment. Compare like-for-like cohorts
and UTC windows over 24–48h before declaring the incident resolved.
