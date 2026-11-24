# Token lease: CI shard 7 verification

CI run `42760317887`, job `129644218884`, at `661fae06f9c6e12092483e0bffc88f96aecde525` had 14 failing cases across three files. Fix `b217c5c740d` adds the fixes on top; no production code or runtime configuration is changed. No assertion, timing guard or test selection is weakened. No skips, xfails or type ignores are added.

## Files and scope

| File | Change |
|---|---|
| `backend/tests/unit/test_sync_cloud_tasks.py:1345` | Install the async executor seam before importing router helpers; retain the same route assertions. |
| `backend/tests/unit/test_verify_pusher_config_references.py:198` | Assert all four declared token-lease defaults explicitly. |
| This report | Per-test causes, pinned-main comparisons and exact local verification. |

No product/design deviation, runtime configuration change, protected-owner edit or production access. No user audio changed or deleted. Source fix commit: `b217c5c740d3cd499c40d540d231e49578c0bade`; the following commit records this report only. No amend, rebase, push or PR mutation.

## Causes and main comparison

Fetched and independently checked `origin/main` / remote main at `eec13aa0cd29a20ab298bdaa75f71e767620fd42`. Created a detached scratch worktree and synced its separate virtualenv to the branch's installed package versions: all 273 package/version entries match, with Python 3.11.15. The initial six-file comparisons use the same canonical file-isolated `backend/test.sh`, offline environment and unchanged 1-second CPU guard. No changes were made to the baseline checkout.

The ten legacy-dark and three batch-admission failures share one cause: the legacy Cloud Tasks fixture installed `utils.executors.run_blocking` as an unspecified synchronous MagicMock, then replaced only the router's imported reference with its async passthrough. The new custody archive helper imported the synchronous mock and correctly awaited the executor API, causing TypeError; the route translated that into its existing HTTP 500. The fixture now installs the same async passthrough before importing the router and its helpers. All real archive and lease code remains exercised, and all route/admission assertions remain intact. This is a fixture contract correction, not a production exception fallback.

The dev pusher assertion omitted this branch's four intentionally declared dark defaults: `RECORD_TOKEN_LEASE_MODE=off`, `RECORD_TOKEN_LEASE_MODE_SERVE_PERCENT=0`, `RECORD_TOKEN_LEASE_SECONDS=3600`, `RECORD_TOKEN_LEASE_DEPLOYED_AT=0`. Its exact dictionary equality now includes those explicit values; it still rejects missing, extra or changed bindings. Generated manifests and the actual chart defaults already agree, so no configuration was changed or regenerated.

Per failing case:

| Node ID under `backend/` | Root cause |
|---|---|
| `tests/unit/test_verify_pusher_config_references.py::test_rendered_dev_pusher_direct_bindings_match_source_contract` | Exact dev environment assertion omitted the four declared token-lease defaults. |
| `tests/unit/test_legacy_dark_router.py::test_router_never_creates_a_legacy_job_outside_on[draining]` | Shared fixture supplied a synchronous executor mock to the awaited archive helper. |
| `tests/unit/test_legacy_dark_router.py::test_router_never_creates_a_legacy_job_outside_on[dark]` | Shared fixture supplied a synchronous executor mock to the awaited archive helper. |
| `tests/unit/test_legacy_dark_router.py::test_router_acknowledges_completed_legacy_content_in_dark` | Shared fixture supplied a synchronous executor mock to the awaited archive helper. |
| `tests/unit/test_legacy_dark_router.py::test_router_acknowledges_a_legacy_final_pass_owner_without_a_ledger_row[draining]` | Shared fixture supplied a synchronous executor mock to the awaited archive helper. |
| `tests/unit/test_legacy_dark_router.py::test_router_acknowledges_a_legacy_final_pass_owner_without_a_ledger_row[dark]` | Shared fixture supplied a synchronous executor mock to the awaited archive helper. |
| `tests/unit/test_legacy_dark_router.py::test_router_admits_a_rehomed_final_pass_owner_to_batch[draining]` | Shared fixture supplied a synchronous executor mock to the awaited archive helper. |
| `tests/unit/test_legacy_dark_router.py::test_router_admits_a_rehomed_final_pass_owner_to_batch[dark]` | Shared fixture supplied a synchronous executor mock to the awaited archive helper. |
| `tests/unit/test_legacy_dark_router.py::test_router_reads_the_legacy_mode_off_the_event_loop` | Shared fixture supplied a synchronous executor mock to the awaited archive helper. |
| `tests/unit/test_legacy_dark_router.py::test_router_is_unchanged_at_on` | Shared fixture supplied a synchronous executor mock to the awaited archive helper. |
| `tests/unit/test_legacy_dark_router.py::test_router_revalidates_a_stale_mode_read_before_creating_a_legacy_job` | Shared fixture supplied a synchronous executor mock to the awaited archive helper. |
| `tests/unit/test_batch_admission_language_router.py::test_actual_sync_router_excludes_before_claim_and_batch_intake[auto-on]` | Shared fixture supplied a synchronous executor mock to the awaited archive helper. |
| `tests/unit/test_batch_admission_language_router.py::test_actual_sync_router_excludes_before_claim_and_batch_intake[ja-on]` | Shared fixture supplied a synchronous executor mock to the awaited archive helper. |
| `tests/unit/test_batch_admission_language_router.py::test_negative_control_router_without_preclaim_gate_exposes_the_reviewed_bypass` | Shared fixture supplied a synchronous executor mock to the awaited archive helper. |

The other named files did not fail in CI: parallel console output interleaved their node IDs with failures from the legacy router. The final summaries show `test_stt_failover_recovery_flag.py` **45 passed**, `test_listen_ws_close_metric.py` **30 passed**, and `test_modulate_capacity_failover.py` **22 passed**, with no failure tracebacks for them. Their named delayed-build, baseline-metric replay, close classification and historical failover cases all passed locally on the original branch and main; no changes were made for those cases.

| Additional named node ID under `backend/tests/unit/` | Verification / disposition |
|---|---|
| `test_stt_failover_recovery_flag.py::test_runtime_pin_survives_delayed_build` | Passed on original and corrected branch and pinned main; CI status was interleaved with router failures. No change. |
| `test_stt_failover_recovery_flag.py::test_off_receiver_failover_replay_emits_only_baseline_metrics` | Passed on original and corrected branch and pinned main; CI status was interleaved with router failures. No change. |
| `test_listen_ws_close_metric.py::test_server_inactivity_close_counts_server_1001_and_held` | Passed on original and corrected branch and pinned main; CI status was interleaved with router failures. No change. |
| `test_listen_ws_close_metric.py::test_terminal_stt_close_failure_keeps_the_client_drop` | Passed on original and corrected branch and pinned main; CI status was interleaved with router failures. No change. |
| `test_listen_ws_close_metric.py::test_send_side_synthetic_1006_does_not_hide_the_clients_clean_close[3-ping]` | Passed on original and corrected branch and pinned main; CI status was interleaved with router failures. No change. |
| `test_listen_ws_close_metric.py::test_drain_timeout_falls_through_to_server_close` | Passed on original and corrected branch and pinned main; CI status was interleaved with router failures. No change. |
| `test_modulate_capacity_failover.py::test_historical_open_window_and_soniox_exhaust_with_failed_modulate[False-6a26acc]` | Passed on original and corrected branch and pinned main; CI status was interleaved with router failures. No change. |

Six-file initial branch reproduction: **160 passed, 14 failed**. Pinned-main comparison: **174 passed**, zero failures (72.90s). Corrected branch: **174 passed**, zero failures (66.35s). No failures were found in that six-file main comparison.

## Commands and final verification

All commands run via `/Users/dazheng/workspace/omi/bin/omi-heavy run --wait 7200 --no-priority -- ...`. The launcher removes `GOOGLE_APPLICATION_CREDENTIALS`, all ambient `CLOUDSDK_*`, service-account/auth-file and project bindings, and uses private HOME/config/temp and one-thread numerical pools. Focused and emulator suites use offline providers; the final unit profile clears both stage/provider overrides to match CI. GCP tier: **none**. Each unit file has a 900-second budget; the canonical 1-second CPU guard is unchanged. Unit files run in separate pytest processes, four workers for the complete shard and serially for focused comparisons.

Focused unit command, from backend: `BACKEND_UNIT_TEST_FILE_LIST=<focused-files.txt> BACKEND_UNIT_FILE_BUDGET_SECONDS=900 BACKEND_PYTEST_WORKERS=1 PYTHON=.venv/bin/python bash test.sh`: **692 passed**, no failures/skips/xfails, 232.09s.

| File under `backend/tests/unit/` | Passed | Pytest seconds |
|---|---:|---:|
| `test_record_token_lease.py` | 90 | 1.27 |
| `test_record_custody_append.py` | 76 | 9.06 |
| `test_pusher_storage_pcm_metrics.py` | 21 | 13.03 |
| `test_pusher_record_abandon.py` | 24 | 8.33 |
| `test_record_barrier_executor.py` | 15 | 8.70 |
| `test_record_drain_barrier_backoff.py` | 22 | 2.97 |
| `test_sync_v2.py` | 182 | 99.23 |
| `test_monitoring_telemetry_contract.py` | 54 | 4.50 |
| `test_sync_cloud_tasks.py` | 208 | 57.88 |

All-backend custody, under private `firebase emulators:exec --only firestore --project demo-omi-listen-stack --config <private>/firebase.json <child-command>`, each command from backend, `OMI_REQUIRE_STORE_BACKENDS=all`, 900s/file:

| Command | Result |
|---|---|
| `.venv/bin/python -m pytest -q --tb=short tests/integration/test_record_custody_append_emulator.py` | 12 passed, 5.47s |
| `.venv/bin/python -m pytest -q --tb=short tests/integration/test_held_custody_conformance.py` | 75 passed, 18.53s |
| `.venv/bin/python -m pytest -q --tb=short tests/integration/test_recovery_custody_conformance.py` | 39 passed, 18.04s |

**126 passed**, no failures or skips, including memory, private Firestore and local PostgreSQL. Launcher 89.94s, exit 0; owned emulators stopped.

Exact hook: `bash scripts/typecheck.sh` from backend, pyright 1.1.403: **0 errors, 78,570 warnings**, exit 0, 229.95s. The seven-file production boundary pyright check also passed with **0 errors, 991 warnings**, 5.13s. No typecheck policy or ignores changed. Boundary command from backend: `.venv/bin/python -m pyright -p pyrightconfig.json --pythonpath .venv/bin/python database/record_audio.py database/record_custody_append.py database/batch_pipeline_record_lease_recovery.py utils/sync/record_token_lease.py utils/batch_pipeline/record_gap_fill.py utils/batch_pipeline/record_lease_append.py database/batch_pipeline_intake.py`.

Shard manifest reproduction from the provided CI log, from the repository root:

```python
from pathlib import Path
import re
log = Path('.agent-brief/ci-shard7-661fae.log').read_text()
files = list(dict.fromkeys(re.findall(r'BACKEND-UNIT-FILE-WALL \d+s (tests/\S+\.py)', log)))
assert len(files) == 344
Path('/Volumes/Ephemeral/scratch/tokenlease-ci-shard7.txt').write_text('\n'.join(files) + '\n')
```

The manifest SHA-256 is `7b2c7689b16d165b9b09369f03a9746247f194d2c701676060dbe0df06f3feb1`. It contains every completed file from the original shard, including the additional batch-admission failures. Final full shard command from backend: `env -u PROVIDER_MODE -u OMI_ENV_STAGE BACKEND_UNIT_TEST_FILE_LIST=/Volumes/Ephemeral/scratch/tokenlease-ci-shard7.txt BACKEND_UNIT_FILE_BUDGET_SECONDS=900 BACKEND_PYTEST_WORKERS=4 PYTHON=.venv/bin/python bash test.sh`.

The first full-shard invocation injected `OMI_ENV_STAGE=offline`, unlike CI, and completed all 344 files in 756.17s with **10,087 passed, 2 failed, 4 skipped, 86 xfailed, 35 deselected**. Both failures were unchanged `test_transcription_outcomes.py` cases (`test_live_failure_labels_are_bounded`, `test_record_live_stt_audio_seconds_uses_bounded_labels`) expecting the default environment label `unknown` rather than `offline`. On pinned main, the identical environment reproduced exactly **23 passed, 2 failed** (14.30s). No code/assertion change was made. A second diagnostic full run cleared only `OMI_ENV_STAGE`, but `utils/env_loader.py:90` also derives the stage directly from `PROVIDER_MODE=offline`. That run completed all 344 files in 1266.06s with **10,086 passed, 3 failed, 4 skipped, 86 xfailed, 35 deselected**: the same two labels plus the close-drain case below. This was a launcher mistake; the final CI profile clears both overrides, retains private HOME/config/temp and credential scrubbing, and first verifies the 25-case label file on both checkouts before running the complete shard. Both checkouts have no personal `backend/.env`, checked before launching this profile.

During the second diagnostic complete-shard run, `test_listen_ws_close_metric.py::test_send_side_synthetic_1006_does_not_hide_the_clients_clean_close[3-event]` observed server `1001` instead of client `1000`. The test (`:293-308`), listen runtime and close-metric implementation are unchanged from pinned main. `routers/listen/runtime.py:1325` sets a real monotonic deadline from `utils/observability/listen_close.py:27` (`CLOSE_FRAME_DRAIN_SECONDS=0.25`) and reads through queued audio until that deadline. Exceeding it before the close frame yields this server-close fallback; the observed symptom is consistent with a scheduling delay across that deadline. The earlier original-branch, corrected-branch and main runs each passed all 30 cases. A four-worker main comparison repeated the close file three times: **30 passed each (90 total)**, 51.99s / 52.09s / 52.06s. The unchanged deadline-sensitive close failure did not reproduce there, and no source change was made for it. The simultaneous transcription file still reproduced the two offline-provider label failures (**23 passed, 2 failed**, 4.62s); combined launcher **113 passed, 2 failed**, 60.85s. No clocks, deadlines or assertions were changed.

Expanded preflight from the repository root, `OMI_PR_BODY_FILE=.agent-brief/tokenlease-pr-body.md bash scripts/dev-harness/run-python.sh .github/scripts/pr_preflight.py --lane local --base eec13aa0cd29a20ab298bdaa75f71e767620fd42`: **67 checks passed**, zero failures, exit 0; 1978.38s reported / 1979.40s launcher wall. Source commit: `b217c5c740d3cd499c40d540d231e49578c0bade`. The final report commit changes documentation only. The internal preflight fixture's mock 3-check success is not counted as the final result.

Verified final CI environment: `PROVIDER_MODE` and `OMI_ENV_STAGE` both unset, with credential scrubbing/private HOME/config/temp unchanged and no personal `.env`. Before the full shard, the unchanged `test_transcription_outcomes.py` passed **25/25** on branch (4.15s pytest / 10.39s launcher) and **25/25** on pinned main (16.48s pytest / 26.20s launcher). These checks gate the final full-shard invocation.

Final full shard: **344 files, 10,089 passed, 0 failed, 4 skipped, 86 xfailed, 0 xpassed, 35 deselected**, exit 0, **1308.66s launcher wall**. Verified all 344 per-file summaries and exact set equality against the manifest extracted from the original CI job. The documented manifest reconstruction command was executed separately and produced the identical SHA-256. Every file retained its 900s budget and unchanged 1-second CPU guard. This is a local file-set reproduction, not a claim that GitHub's 900s shard-step budget was exercised on this shared macOS host.

## Remaining risks and delivery

No unresolved branch-caused failure. One earlier local close-drain timing failure remains a scheduling-sensitive test risk: the listen implementation and test are unchanged from main, three main repetitions passed, and the case passed in the final complete shard. No timing or assertion change was made for it. The four repository-declared skips (local libopus availability, two non-SSE matrix combinations and one irrelevant refund tuple) and 86 existing strict lifecycle xfails remain; no waiver was added by this change.

No design deviation or production behavior change. Tests used no GCP tier, credentials or production data. The temporary detached main checkout is removed after validation; all owned test services and heartbeat are stopped before handoff. Both commits are local, with no push, amend, rebase or PR mutation.


Verification completed at 2026-11-10T06:42:12.089613+00:00.
