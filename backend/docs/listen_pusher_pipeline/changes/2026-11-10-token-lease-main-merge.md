# Token lease: merge main for PR #25018

Merge `d43a6d78747e9bdcd9150d65f429730b2ff66d3a` joins pushed branch head `95464779c5eb5b3e30d8d583c5ecd97432e59173` and freshly fetched main `eec13aa0cd29a20ab298bdaa75f71e767620fd42`. This is a two-parent merge in the same `lane/tokenlease` worktree. No rebase, force update, push, PR mutation, deployment or GCP tier was used.

## Resolutions

- `backend/database/batch_pipeline_intake.py:63`: main's #24986 target/restore-admission fence runs before every existing-content return, including batch/completed ledger replay. Canonical record obligation and partial parent are checked before admission. `:173` retains token lease's `record_input_upload_revision` capture in non-off mode, after the normal immutable-binding checks; off adds no field.
- `backend/utils/batch_pipeline/record_gap_fill.py:219`: preserve token lease's public per-file `source_units` and `wav_pcm` APIs for late-WAL retention and interior-gap detection. Main's #24940 drain lease, bounded create-only writes, cancellation handling and post-write settle/ACK fence are kept (`:330`, `:364`, `:534`, `:543`). The write loop consumes main's predecoded `source`, and both new decoding callsites use the public helper. The auto-merged `live_upload.py:367` retains main's covered response only after the byte-exact retained ACK proof. Migrate the one new main test's helper patch to the public name.
- `config/feature-flags.yaml:2`: keep all three token-lease catalog entries and main's new orphan-repair/quiet-exit entries, retirements and registry changes. No activation changes.
- `backend/charts/backend-listen/values.yaml:9` and `backend/charts/pusher/values.yaml:9`: retain the four dark token-lease defaults (off, zero cohort, 3600 seconds, zero enable epoch), while keeping main's removal of retired retention/strict-projection switches.
- `backend/deploy/cloud_run_gmp_sync.yaml:48`: union token-lease/late-append families with main's runtime-percent families; retain every other allow/drop rule.
- Regenerate `backend/docs/feature-flag-registry.md` with `python3 scripts/render_feature_flag_registry.py`, preserving the committed as-of marker. Regenerate composed `backend/deploy/runtime_env.yaml` with `python3 backend/deploy/compose_runtime_env.py`; it matches the automatic merge. No generated output was hand-merged. The metric inventory is a captured snapshot plus reviewed declarations, and the lifecycle writer inventory explicitly requires review rather than regeneration; both merged automatically, preserve both sides, and are validated by their owning alert/source tests. No production inventory refresh.

The combined lifecycle invariant run exposed an integration gap: its derived-state checker accepted only conversation phases, so the two token views failed eight clauses. Follow-ups `1a1afce4230` and `4f6218c6a10` check the token views' actual source exits, nested-clock declaration, process-local gauge and custody-invariant page. They do not claim an independent persisted deadline or backlog dwell alarm. The source reader now follows control-flow blocks to find `apply_seals.commit` without crossing function scopes; a regression proves this. No xfail or timing exemption was added, and no production behavior was changed by these follow-ups.

## Validation

All heavy commands run through `/Users/dazheng/workspace/omi/bin/omi-heavy run --wait 7200 --no-priority -- ...` in this worktree with Python 3.11. Launchers unset `GOOGLE_APPLICATION_CREDENTIALS`, every ambient `CLOUDSDK_*`, auth-file/service-account and project bindings; use private HOME/config/temp; select offline providers; and cap numerical pools at one. Emulator SDKs use anonymous demo-project clients. Canonical fixtures may create an empty private CLOUDSDK_CONFIG. No GCP access or production credentials.

The unit contract is `BACKEND_UNIT_TEST_FILE_LIST=<files below> BACKEND_UNIT_FILE_BUDGET_SECONDS=900 BACKEND_PYTEST_FILE_ISOLATION=1 BACKEND_PYTEST_PARALLEL_SESSION=0 PYTHON=.venv/bin/python bash test.sh` from `backend/`, with the unchanged 1-second call-CPU failure guard. Files run serially; sync v2 and cluster repair both completed within 900 seconds. Final per-file results:

| File under `backend/tests/unit/` | Result |
|---|---|
| `test_record_token_lease.py` | 86 passed in 16.25s |
| `test_record_custody_append.py` | 39 passed, 1 warning in 25.21s |
| `test_record_producer_proof.py` | 27 passed in 4.13s |
| `test_record_partial.py` | 82 passed, 1 warning in 32.40s |
| `test_record_seal_repair.py` | 48 passed, 1 warning in 22.04s |
| `test_record_pending_repair.py` | 63 passed, 1 warning in 46.76s |
| `test_record_audio_seal.py` | 57 passed, 9 warnings in 101.61s (0:01:41) |
| `test_record_seal_nojob.py` | 44 passed, 1 warning in 17.70s |
| `test_record_seal_cluster_repair.py` | 148 passed, 1 warning in 60.55s (0:01:00) |
| `test_record_token_lease_deploy.py` | 12 passed in 8.99s |
| `test_record_seal_cluster_repair_deploy.py` | 10 passed in 7.54s |
| `test_record_seal_worker.py` | 25 passed, 1 warning in 7.19s |
| `test_record_lease_append.py` | 1 passed, 1 warning in 6.45s |
| `test_pusher_record_abandon.py` | 24 passed, 9 warnings in 27.00s |
| `test_pusher_storage_pcm_metrics.py` | 21 passed, 9 warnings in 26.34s |
| `test_record_barrier_executor.py` | 15 passed, 9 warnings in 61.41s (0:01:01) |
| `test_record_drain_barrier_backoff.py` | 22 passed, 1 warning in 12.60s |
| `test_record_gap_fill.py` | 87 passed, 1 warning in 10.82s |
| `test_batch_pipeline_intake.py` | 85 passed, 1 warning in 5.03s |
| `test_restore_recording_obligation.py` | 33 passed, 9 warnings in 34.82s |
| `test_batch_pipeline_live.py` | 105 passed, 1 warning in 29.05s |
| `test_sync_v2.py` | 182 passed, 68 warnings in 207.90s (0:03:27) |
| `test_lifecycle_state_table_writers.py` | 1737 passed in 200.82s (0:03:20) |
| `test_lifecycle_invariants.py` | 248 passed, 86 xfailed in 7.02s |
| `test_monitoring_alert_backtest.py` | 29 passed in 1.38s |
| `test_monitoring_notification_contract.py` | 8 passed in 18.07s |
| `test_monitoring_alert_rule_contract.py` | 75 passed in 24.27s |
| `test_monitoring_telemetry_contract.py` | 54 passed in 6.73s |
| `test_oldest_age_flat_alerts.py` | 14 passed in 4.53s |
| `test_backend_runtime_env_validator.py` | 206 passed in 53.82s |
| `test_render_backend_runtime_env.py` | 91 passed in 4.24s |
| `test_runtime_env_sources.py` | 5 passed in 1.00s |
| `test_runtime_percent.py` | 243 passed in 3.48s |
| `test_runtime_percent_export.py` | 21 passed, 1 warning in 2.93s |

The initial 32-file run exited 1 in 1314.98s solely on the eight derived-view assertions. The first follow-up narrowed this to one source-reader assertion; the final four-file follow-up passed in 22.80s. The initial four oldest-age skips were rerun with the real installed promtool on PATH; all 14 passed. The final table replaces failed/skipped attempts; no new xfails or skips.

Final focused total: **3,947 passes across 34 unique unit files**, **86 existing strict xfails**, zero final failures/skips. The named derived views now pass all four clauses. The final follow-up adds five rejection/source-reader cases, not a new expected-failure exemption.

Additional commands (same heavy wrapper and isolated environment):

| Command | Result |
|---|---|
| `.venv/bin/python -m pytest -q --tb=short tests/integration/test_record_custody_append_emulator.py` under private Firestore emulator | 6 passed, no skips |
| `.venv/bin/python -m pytest -q --tb=short tests/integration/test_held_custody_conformance.py` with `OMI_REQUIRE_STORE_BACKENDS=all` | 75 passed, no skips; memory, private Firestore and local PostgreSQL |
| `.venv/bin/python -m pytest -q --tb=short tests/integration/test_recovery_custody_conformance.py` with the same requirement | 39 passed, no skips; all three backends |
| `.venv/bin/python -m testing.lifecycle_sim.run --keep --state-dir <private-state>/lifecycle --extra-test-module testing/lifecycle_properties/test_properties.py` | 34 passed, 3 existing strict xfails in 79.70s; launcher 115.05s |
| `.venv/bin/python -m pyright -p pyrightconfig.json --pythonpath <worktree>/backend/.venv/bin/python database/record_audio.py database/record_custody_append.py database/batch_pipeline_record_lease_recovery.py utils/sync/record_token_lease.py utils/batch_pipeline/record_gap_fill.py utils/batch_pipeline/record_lease_append.py database/batch_pipeline_intake.py` | 0 errors, 1,012 warnings, 3.31s |
| `bash backend/scripts/typecheck.sh` from repository root (launcher runs `bash scripts/typecheck.sh` from backend) | 0 errors, 78,591 warnings, 290.08s; exact enforced hook lane, pyright 1.1.403 |
| `.venv/bin/python tests/promql/record_token_lease.py --promtool /Volumes/Ephemeral/scratch/tokenlease-promtool/promtool` from backend | 7 scenarios passed, 0.99s |
| `bash backend/scripts/pre-deploy-check.sh` | 511 pytest passes + 36 script self-tests; exit 0, 60.13s |

Custody launcher: `firebase emulators:exec --only firestore --project demo-omi-listen-stack --config <private-state>/firebase.json <child-command>`; each file runs in its own process with a 900s timeout. The local PostgreSQL backend is fixture-owned. All services shut down after their commands. Lifecycle named exits **seal**, **partial_finish**, **reactivated** passed. Its pre-existing strict xfails remain sealed-no-job recovery, upload-failure retry, and closed-before-completed ordering; the invariant suite's 86 strict xfails are its checked-in reviewed gap table. These results are local verification, not production acceptance.

Expanded preflight: `bash scripts/dev-harness/run-python.sh .github/scripts/pr_preflight.py --lane local --base eec13aa0cd29a20ab298bdaa75f71e767620fd42`, with `OMI_PR_BODY_FILE=.agent-brief/tokenlease-pr-body.md`, **67 checks passed**, zero failures, **1205.64s** reported (**1206.25s** launcher wall), exit 0. The source head is `4f6218c6a1015b09bb3f5765c65dc534ead56bb2`; the final commit adds this evidence note only. `BACKEND_UNIT_FILE_BUDGET_SECONDS=900` remains set throughout. The committed, clean Swift-format source at `62eaad2822b865407b8cde56c36386c00800f7ec` supplied a hash-verified copy of its version 602.0.0 binary into the isolated helper cache; no source or check was bypassed. The fixture's intentional mock GitHub HTTP 502 warning did not indicate a real API failure.

The local preflight PR-body draft carries the current sync line counts (`3820 -> 3842`, growth 22); the open PR still carries the pre-merge counts (`3819 -> 3841`, also growth 22). No remote PR metadata was changed. For an exact-count handoff the lead can copy:

```text
Line-Count-Exception: backend/routers/sync.py | 3820 -> 3842 | Minimal adjacent lease/custody hooks; shared transaction and recovery logic lives in component helpers.
```

No design or runtime deviation in the resolutions. The only extra source change after the merge is test-contract integration for the derived token views. Default-off deployment and all original privacy, custody, immutable-binding and raw-audio retention rules remain. Existing strict xfail gaps above remain open; no production access was needed.

Verification completed at 2026-11-10T04:16:20+00:00.
