# Token lease: post-storage late-append observation

Review-desk #25018 P2 was verified against merged head `2921bbe3b9c1a24f6c0b43ebd52774bd57743906`. Fix `07628be860001d8c0f56fc23ed499e6bb2a01366` is an additional commit on that history; no amend, rebase, push, PR mutation or GCP access.

## Behavior

The pre-storage shadow snapshot and its unused database helper are removed. `utils/sync/record_token_lease.py:133` collects the late observation returned by each successful post-storage renewal. The request retains the OR of those observations, so a later file, refreshed lease or reopened row cannot erase the first durable file's late state. Shadow and non-cohort requests count once only after full durable storage and an accepted response. Serve passes the observation into its exact-token finish transaction (`:69`), which also reads current closure, partial and lapsed-token state.

`database/record_audio.py:226` computes custody late state before the lease/2 write throttle, publishes it for custody as well as frames, and retains post-storage observations across ambiguous commit-reply retries. Publication occurs only after the renewal call succeeds. Frame observation behavior and heartbeat write throttling are unchanged. `database/record_custody_append.py:119` combines the accepted post-storage observations with the current row/token state and the existing token hint. The finish receipt stores the result with its winning attempt; a receipt replay remains read-only, with no second metric increment, revision bump or recovery.

Off remains bit-exact with no new IO. Disabled archive, failed/partial commits, refused responses and memoized retries do not count. No raw audio is deleted, no rollout setting changes, and no protected-owner or discovery code is edited. Contract: [producer custody leases](../../listen_pusher_pipeline.mdx).

The race matrix exercises shadow, non-cohort and serve uploads with no transition, repair closure, partial finish and token lapse during storage, with/without renewal response loss. Two durable file operations count at most once for the accepted upload. The finish-reply-loss matrix covers both pre-existing and post-begin transitions; separate replay cannot upgrade a stored false result or count twice. Throttled closed/partial observations perform zero writes. A finish also observes its own lapsed fence.

## Verification

All heavy commands use `/Users/dazheng/workspace/omi/bin/omi-heavy run --wait 7200 --no-priority -- ...`, the worktree Python 3.11 environment, private HOME/config/temp, offline providers and one-thread numerical pools. Launchers remove `GOOGLE_APPLICATION_CREDENTIALS`, all ambient `CLOUDSDK_*`, service-account/auth-file and project bindings. Emulator clients are anonymous, using demo projects; the canonical fixtures may create an empty private CLOUDSDK_CONFIG. GCP tier: none.

Unit command, from backend: `BACKEND_UNIT_TEST_FILE_LIST=<files below> BACKEND_UNIT_FILE_BUDGET_SECONDS=900 BACKEND_PYTEST_FILE_ISOLATION=1 BACKEND_PYTEST_PARALLEL_SESSION=0 PYTHON=.venv/bin/python bash test.sh`. The unchanged 1-second call-CPU failure guard remains enforced. Final per-file results:

| File under `backend/tests/unit/` | Result |
|---|---|
| `test_record_token_lease.py` | 90 passed in 2.29s |
| `test_record_custody_append.py` | 76 passed, 1 warning in 13.22s |
| `test_pusher_storage_pcm_metrics.py` | 21 passed, 9 warnings in 11.08s |
| `test_pusher_record_abandon.py` | 24 passed, 9 warnings in 8.21s |
| `test_record_barrier_executor.py` | 15 passed, 9 warnings in 13.70s |
| `test_record_drain_barrier_backoff.py` | 22 passed, 1 warning in 4.26s |
| `test_sync_v2.py` | 182 passed, 68 warnings in 90.61s (0:01:30) |
| `test_monitoring_telemetry_contract.py` | 54 passed in 8.41s |

**484 passes across eight files**, no failures, skips or xfails. The first eight-file run passed in 165.83s; after extending finish-state coverage, token lease and custody were rerun together in 20.61s (final counts above).

All-backend custody conformance, each file in its own process with a 900s timeout under private `firebase emulators:exec --only firestore --project demo-omi-listen-stack --config <private-state>/firebase.json <child-command>`, with `OMI_REQUIRE_STORE_BACKENDS=all`:

| Command from backend | Result |
|---|---|
| `.venv/bin/python -m pytest -q --tb=short tests/integration/test_record_custody_append_emulator.py` | 12 passed, 2.92s (final rerun) |
| `.venv/bin/python -m pytest -q --tb=short tests/integration/test_held_custody_conformance.py` | 75 passed, 19.02s |
| `.venv/bin/python -m pytest -q --tb=short tests/integration/test_recovery_custody_conformance.py` | 39 passed, 4.75s |

**126 passes**, no skips; required memory, private Firestore and local PostgreSQL. The original three-file launcher exited 0 in 72.54s; after adding the real shadow race/renewal reply-loss cases, the 12-case emulator file was rerun in 25.96s launcher wall. Both runs shut down their owned services. The real emulator verifies unchanged uploads do not count, closure during storage counts once, and a committed lapsed-token renewal whose reply is lost still counts once after its refreshed lease is reread.

Changed-boundary pyright command: `.venv/bin/python -m pyright -p pyrightconfig.json --pythonpath <worktree>/backend/.venv/bin/python database/record_audio.py database/record_custody_append.py database/batch_pipeline_record_lease_recovery.py utils/sync/record_token_lease.py utils/batch_pipeline/record_gap_fill.py utils/batch_pipeline/record_lease_append.py database/batch_pipeline_intake.py`: **0 errors, 991 warnings**, exit 0, 2.12s. Exact hook command `bash scripts/typecheck.sh` from backend: **0 errors, 78,570 warnings**, exit 0, **96.87s**; pyright 1.1.403, no ignores or typecheck-policy changes.

Expanded preflight command: `bash scripts/dev-harness/run-python.sh .github/scripts/pr_preflight.py --lane local --base eec13aa0cd29a20ab298bdaa75f71e767620fd42`, with `OMI_PR_BODY_FILE=.agent-brief/tokenlease-pr-body.md`: **67 checks passed**, zero failures, exit 0; **874.19s** reported / **874.79s** launcher wall. The unit file budget remains 900s. It ran on the committed production fix `07628be860001d8c0f56fc23ed499e6bb2a01366`; the final commit adds the emulator regression and this evidence note. No check, timing threshold or policy was relaxed. The intentional mock GitHub HTTP 502 fixture warning is not a real API failure.

PromQL command from backend: `.venv/bin/python tests/promql/record_token_lease.py --promtool /Volumes/Ephemeral/scratch/tokenlease-promtool/promtool`: **7 scenarios passed**, exit 0, 0.41s.

No unresolved finding from this review. These are local checks, with no production acceptance or deployment claim. Verification completed at 2026-11-10T04:47:37+00:00.
