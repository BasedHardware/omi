# Home-overlap recovery evidence

Evidence timestamp: 2026-11-07T23:58:42.459597+00:00

PR: https://github.com/BasedHardware/omi/pull/24865

## Reconciliation

Initial local head `9cff8f2ab02` and published head
`4ebac52f436ea932a56bd31343a6a7205b81214a` contained 13 patch-identical Home
commit pairs, verified after fetch with `git log --left-right --cherry-mark`
and `git range-diff`. Rebasing onto the published head dropped only those
identical local copies. Main was then integrated while retaining published
ancestry, permitting a normal push without replacing any published commit.
The original local head remains at
`recovery/home-overlap-before-default-on-20261108`.
Both original dirty E2E edits were preserved and committed in `325109a045a`.
The extracted enrichment callback now mirrors explicit Process Now intent.

## Defaults and explicit detail intent

- `HOME_PROCESSING_OWNERSHIP_ENABLED` defaults to true; false disables ownership/dedupe.
- `HOME_LIVE_MEMBER_NOTES_DEFERRED_ENABLED` defaults to true; false disables notes deferral.
- These are independent permanent env kill switches, evaluated per call. The
  optional UID allowlist remains; empty admits all eligible accounts.
- The app rendering fix and ownership capability header are always on. The app
  does not read these backend env flags; no companion default-off app flag exists.
- Explicit detail reads send `X-Omi-Recording-Detail: 1`; Home lifecycle probes
  omit it. Cached detail entry refreshes quietly to carry explicit intent.
- Registry source, generated registry, pipeline contract and runbook agree.

## Successful local verification

Heavy runs used `/Users/dazheng/workspace/omi/bin/omi-heavy run --`.
Logs are in `/Volumes/Ephemeral/scratch/home-overlap-recovery-20261108/`.

1. Pinned Flutter 3.44.5, from app:
   `flutter test --no-pub --timeout 90s --reporter expanded`
   with `test/unit/home_rows_test.dart`, `test/unit/home_rows_state_space_test.dart`,
   `test/widgets/home_row_contract_render_test.dart`,
   `test/services/pending_work_store_test.dart`, `test/widgets/pending_work_test.dart`,
   and `test/providers/conversation_home_typed_fetch_test.dart`: **76 passed**.
   Includes 4352 state scenarios, actual Home widgets and detail HTTP intent.
2. Same Flutter command with `test/widgets/conversation_detail_status_test.dart`,
   `test/widgets/conversation_detail_summary_retry_test.dart`, and
   `test/providers/conversation_detail_reprocess_outcome_test.dart`: **44 passed**.
3. Backend isolated file runner:
   `BACKEND_PYTEST_WORKERS=1 BACKEND_UNIT_FILE_BUDGET_SECONDS=900
   BACKEND_UNIT_TEST_FILE_LIST=<selection> bash backend/test.sh`.
   Per-file results plus focused corrected-fixture retries total **2355 passed**:

   | File in backend/tests/unit | Passed |
   | --- | ---: |
   | test_pending_work.py | 46 |
   | test_sync_job_retention.py | 29 |
   | test_episodes_finalizer_hook.py | 23 |
   | test_homesettle.py | 48 |
   | test_phone_batch_process_now.py | 13 |
   | test_capture_group_notes_refresh.py | 20 |
   | test_conversation_finalizer_failure_logging.py | 3 |
   | test_conversation_smart_merge.py | 83 |
   | test_sync_v2.py | 176 |
   | test_conversation_finalization_jobs.py | 78 |
   | test_lifecycle_state_table_writers.py | 1712 |
   | test_enrichment_callback_parity.py | 3 |
   | test_enrichment_route.py | 105 |
   | test_enrichment_early_abort.py | 12 |
   | test_enrichment_callback_fence.py | 4 |

   The parity retry used the prescribed isolated runner and exited 0
   (`parity-combined.log`). Home-settling and failure-logging retries exited 0.
   The original aggregate runner timed out, so this is per-file evidence,
   not a claim of a clean aggregate exit.
4. `E2E_PYTEST_TIMEOUT=600s bash backend/testing/e2e/run.sh -q
   -k 'sync_lifecycle or watch_process_now'`: **9 passed**, exit 0,
   99.25s pytest time (`e2e-fixed.log`). Explicit intent, visibility, readable
   transcript, sync usage/erasure and target merge paths are covered.
5. `OMI_PR_BODY_FILE=<body> BACKEND_PYTEST_WORKERS=1
   BACKEND_UNIT_FILE_BUDGET_SECONDS=1800 make preflight`: **71 checks passed**,
   exit 0, 2332.04s (`preflight-retry.log`). Firestore index guard passed all
   seven files; no checks or CI settings were disabled.
6. `scripts/pr-preflight --suggest` and
   `scripts/pr-preflight --metadata-only --pr-body-file <body>`:
   **5 metadata checks passed**, exit 0 (`metadata-final.log`).
7. Feature-flag registry generated with `python3 scripts/render_feature_flag_registry.py`;
   its check passed. Existing overdue-flag warnings are unrelated baseline debt.

## Failed attempts and their resolution

- Two old HTTP fake signatures failed after defaults became enabled; corrected
  the pending-sync keyword and reran all 46 pending-work cases successfully.
- Two cache rollback fixtures needed the ownership kill switch explicitly false;
  the capable-client rollback test now sends its real ownership and beta headers.
  All 48 cases passed on retry.
- Three logging fixtures needed to model the enabled notes-scheduling prelude;
  all 3 passed after correction.
- The first broad backend runner hit its 1800s outer deadline. The parity worker
  printed passing assertions but lacked a clean runner receipt; the isolated
  retry above produced exit 0. No aggregate green claim is made.
- First preflight timed out at the query-shape file's 900s wall limit at 95 percent,
  with no assertion failure. Full retry used an 1800s local per-file limit and
  passed all 71 checks. CPU/check policy and CI settings were retained.
- Initial E2E exceeded the harness-wide 120s limit without a verdict. The 600s
  retry had 8 passes and one Watch failure. The printed hermetic stack identified
  a test fake reading raw encrypted transcript/correction strings into a decoded
  `Conversation` model. It now uses the normal decoded database read/update
  boundary, preserving encrypted persistence; all 9 cases then passed with exit 0.
  No production change was needed for this fake error.
- Two diagnostic/parity admissions exhausted their 3600s queue limits without
  starting tests. They were combined in a single bounded heavy session, which
  completed and exited 0. Only our duplicate queued process was stopped.

## Render evidence

- `.agent-artifacts/ui-evidence/home-overlap/001-mobile-ios-home-overlap-before.png`
- `.agent-artifacts/ui-evidence/home-overlap/002-mobile-ios-home-overlap-after.png`
- `.agent-artifacts/ui-evidence/home-overlap/evidence.json`

Both committed renders were visually checked. The before image is the original
published fixture. The after was regenerated in the passing app run with
`--dart-define=HOME_ROW_RENDER_OUTPUT=<output-directory>` and is byte-identical
(SHA-256 `36b858994fbfd786b917a26e3ae043480d86f6ccf5a7ffdc1af0d3bf52638139`).
These are iOS-metric/font widget renders, not physical-device screenshots.
Before shows Listening plus Processing for three recordings; after shows only Listening.

## Scope, rollback and remaining coordination

Supplied live-WAL targets and recording IDs are persisted at job creation.
Session-only uploads have no reliable conversation target at admission and retain
null; no target inference, upload-contract change, backfill or migration was added.

Rollback: set either env switch false (both for complete backend rollback).
Durable obligations resume on their next wake. Revert the Flutter projection
changes for app rollback. Additive Redis metadata retains its existing TTL.

No PR merge or deployment is authorized. Merge-desk owns merge; the Infra Rollout
Coordinator owns production rollout. No runtime env changes were made. GCP tier:
none; no production access. Final GitHub head/CI state must be checked after push.
ANX ruling and progress are recorded on `card:episode-home-live-rows`.

## CI follow-up: smart-merge finalizer fixture

On 2026-11-08 at 01:33Z, the first published head's backend shard 7 failed
`test_conversation_smart_merge_finalizer.py`: 24 failures, 4 passes. Every
failure rejected the newly enabled `member_notes.waits` blocking call in the
strict fake executor. The fixture now explicitly exercises the unset (enabled)
default and models its recording as having no live owner, allowing that prelude
without changing smart-merge stage-order assertions. Production behavior and both
default-on switches are unchanged. The required pre-push selection includes this
whole 28-case file; its terminal result is recorded in the PR's verification
section after publication. Source job: https://github.com/BasedHardware/omi/actions/runs/42434242402/job/128589548246

The remaining shard failures exposed the same omitted scheduling seam in
`test_meeting_evidence_admission.py` (6 failures) and the photo-registration suite
(6 failures, using the already-corrected shared smart-merge harness). The action
item mirror's import-isolated router fixture also needed an explicit member-notes
module stub (3 setup errors), because the real module's outbox dependency is
intentionally absent in that unrelated endpoint fixture. The meeting fixture
retains the unset enabled default and models no live owner. No flags were
disabled and no production code changed for these fixture corrections.

The full app CI run also found two old cached-detail read-count assertions in
`conversation_detail_carried_transcript_test.dart`. The observed counts were
one read on cached entry and two after resume, matching the intentional quiet
explicit-detail refresh that grants the current open's notes lease. Expectations
now assert those counts; the carried-transcript refresh test is unchanged. The
second push gate was stopped before publication to include this correction in
the same follow-up. No production code changed for this test update.
