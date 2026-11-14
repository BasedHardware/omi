# Token lease round 5: late-append accounting and hook type checks

The two custody P2s and the hook-selected typing errors against `85812c4fb0131bcdcfc8cbe5658855e6f26296b5` were verified against the code and fixed on top. No rebase, push, PR, deployment or GCP tier.

## Behavior and scope

- Before adding a new pusher token, record registration observes whether any older token has lapsed, including on an open row. The existing barrier retains that observation until the first successful durable frame/window commit. Failed or refused commits leave the observation pending and do not count. Off mode retains its old payload and performs no new lease IO.
- Finish receipts store `late` and a unique `finish_attempt` created outside the transaction callback. Retries within that invocation return the stored late result and increment once after transaction success. Separate finish replays return the stored result, remain read-only and do not increment again. No second revision or continuation is created. Lost-fence recovery uses the same receipt accounting rule so its ambiguous commit cannot lose the counter either.
- The real Firestore-emulator matrix covers open, closed and partial rows, with/without a lost post-commit reply: exactly one late increment for closed/partial rows, retained bytes, revision 8 once, and one continuation where required. Independent finish/recovery replays add no writes or increments.
- Hook typing is fixed through a heterogeneous `dict[str, object]` update patch, explicit partial-run mapping validation, typed request state and a ParamSpec-preserving async decorator. Session/identity accesses use real narrowing. The shared WAL decode/PCM helpers are public and every in-tree caller is migrated. No ignores, typecheck config changes or waived diagnostics.

Contract: [producer custody leases](../../listen_pusher_pipeline.mdx). Flags/defaults, leases, heartbeat sources and rollout stay unchanged. No Part B work, discovery changes, raw-audio deletion or protected-owner edits. The only `record_audio.py` edit is adjacent to new-token lateness observation.

## Verification

Recorded at 2026-11-10T02:30:49+00:00. All commands used the current worktree and its Python 3.11 `.venv`, through `/Users/dazheng/workspace/omi/bin/omi-heavy run --wait 7200 --no-priority --`. The owned launcher unsets `GOOGLE_APPLICATION_CREDENTIALS`, all ambient `CLOUDSDK_*`, service-account/auth-file bindings and project bindings; uses private HOME/config/temp; caps numerical pools at one; and selects offline providers. Emulator SDK clients use demo projects and anonymous credentials. The canonical local-stack fixture can create an empty private CLOUDSDK_CONFIG; no ambient credentials are restored.

| Unit suite (`tests/unit/test_*.py`) | Passed | Pytest seconds |
|---|---:|---:|
| `test_record_token_lease` | 86 | 1.63 |
| `test_record_custody_append` | 39 | 3.33 |
| `test_pusher_storage_pcm_metrics` | 21 | 79.27 |
| `test_record_barrier_executor` | 15 | 45.44 |
| `test_record_drain_barrier_backoff` | 22 | 8.03 |
| `test_pusher_record_abandon` | 24 | 27.62 |
| `test_record_lease_append` | 1 | 8.83 |
| `test_record_gap_fill` | 52 | 9.21 |
| `test_record_audio_seal` | 57 | 41.14 |
| `test_record_partial` | 82 | 9.61 |
| `test_sync_v2` | 182 | 57.53 |
| `test_monitoring_telemetry_contract` | 54 | 3.96 |

**635 passes across 12 files**, canonical file isolation and **900s per-file budget**, unchanged call-CPU guard. The 12-file run exited 0 in 409.37s. After the last typing-only request-state narrowing, all three consumers were rerun: token lease **86**, custody **39**, sync v2 **182** (307 passes; 68.34s total). The table uses their final timings.

- Real-emulator receipt proof: **6 passed**, final rerun 4.42s pytest / 28.49s launcher wall, no skips.
- All-backend custody conformance: held **75 passed** (133.52s), recovery **39 passed** (77.06s), requiring memory, private Firestore and local PostgreSQL with `OMI_REQUIRE_STORE_BACKENDS=all`; no skips. The combined custody/emulator invocation exited 0 in 399.01s. Unique custody/receipt coverage: **120 passed**.
- Real PromQL backtests: **7 scenarios passed**, exit 0, 1.37s launcher wall.
- Changed-production-file pyright with repository config: **0 errors, 789 warnings**, exit 0, 2.92s.
- Exact enforced hook lane, `PYRIGHT_PYTHON=.venv/bin/python bash scripts/typecheck.sh` from backend: **0 errors, 78,181 warnings**, exit 0, 105.53s. Pyright 1.1.403, the hook pin; existing warning policy is unchanged. This runs the full repository include/exclude selection and the stricter `utils/sync` execution environment.
- Expanded preflight: **67 checks passed**, exit 0; 475.50s reported / **477.02s launcher wall**, on implementation commit `ff202e8cf36d221fa64e514392d9a62d4efbe47a`.

## Commands

The owned orchestration script is `/Volumes/Ephemeral/scratch/tokenlease-round5-validate.py`; its raw logs and JSON exit/timing records are `tokenlease-round5-<mode>.log` / `tokenlease-round5-<mode>-results.json` under that scratch root. Modes used: `--types`, `--units`, `--custody`, `--units-final`, `--receipt-final`, `--promql`, `--preflight`.

```sh
# Every mode is invoked through this same heavy gate.
/Users/dazheng/workspace/omi/bin/omi-heavy run --wait 7200 --no-priority -- python3 /Volumes/Ephemeral/scratch/tokenlease-round5-validate.py --types
# cwd backend; exact hook child command
PYRIGHT_PYTHON=.venv/bin/python bash scripts/typecheck.sh
# cwd backend; changed-production-file child command, same repository config
.venv/bin/python -m pyright -p pyrightconfig.json --pythonpath .venv/bin/python database/record_audio.py database/record_custody_append.py database/batch_pipeline_record_lease_recovery.py utils/sync/record_token_lease.py utils/batch_pipeline/record_gap_fill.py utils/batch_pipeline/record_lease_append.py
# cwd backend; canonical selected-file executor, table above is the file list
PYTHON=.venv/bin/python BACKEND_PYTEST_FILE_ISOLATION=1 BACKEND_PYTEST_PARALLEL_SESSION=0 BACKEND_PYTEST_WORKERS=1 BACKEND_UNIT_FILE_BUDGET_SECONDS=900 BACKEND_UNIT_TEST_FILE_LIST=<owned-state>/unit-files.txt bash test.sh
# cwd backend; each conformance file is a fresh process, timeout 900s
.venv/bin/python -m pytest -q --tb=short tests/integration/test_record_custody_append_emulator.py
.venv/bin/python -m pytest -q --tb=short tests/integration/test_held_custody_conformance.py
.venv/bin/python -m pytest -q --tb=short tests/integration/test_recovery_custody_conformance.py
.venv/bin/python tests/promql/record_token_lease.py --promtool /Volumes/Ephemeral/scratch/tokenlease-promtool/promtool
# cwd root; required local preflight against the branch's immutable main base
bash scripts/dev-harness/run-python.sh .github/scripts/pr_preflight.py --lane local --base 2fd0a9d94f238b6c338d6c67aec1e77f783159d9
```

The custody command runs inside `firebase emulators:exec --only firestore --project demo-omi-listen-stack` with an owned loopback endpoint and private config; only exact synthetic owner/doc IDs are cleaned. Canonical fixture cleanup stopped the emulators/PostgreSQL. Preflight uses `CI=true OMI_CHECKS_JOBS=1`, the existing local PR body and its three exact line-count disclosures; its local file-wall guard is 1800s, while all requested unit/integration runs retain 900s. The runner seeds a private copy of the completed, exact-pin Swift helper cache (source commit `62eaad2822b865407b8cde56c36386c00800f7ec`, clean tracked source, version 602.0.0, matching source/copy SHA-256) to avoid another cold build. The full typecheck has an 1800s outer orchestration deadline; its final run completed in 105.53s without changing the hook.

## Failures corrected and limits

The first unit attempt reported four failures in the new late-row/recovery fixtures (35 custody cases passed): their synthetic user account was missing, so the existing privacy guard correctly rejected recovery with `account_missing`. The fixtures now seed their own account. No production privacy check was relaxed. Only that owned failing unit runner and its descendants were stopped; `tokenlease-round5-units-initial.log` and `tokenlease-round5-unit-stop.json` retain the diagnostics/audit. The complete rerun and final consumer rerun are green above.

The first full hook run after the initial fixes exited 1 in 908.10s with two new TypedDict optional-session access errors (and the same 78,181 warnings). Session and resolved identities are now narrowed explicitly; the final full hook run and changed-file check both exit 0. `tokenlease-round5-types-initial.log` and its JSON timing record retain that result. No failed or skipped file is counted as passing.

No production implementation deviation from the R5 rulings. The same ambiguous-commit counter fix was also applied to lost-fence recovery, with two additional regressions, to close the identical path. Counter delivery still requires the completing process to survive through metric emission; the durable receipt, revision and continuation are independent of that process-local emission. Production/CI identity, rollout and the 48h soak remain unverified. No push, PR, production access or GCP tier.

## Files and commits

R5 changes these paths (including this note):

- `backend/database/batch_pipeline_record_lease_recovery.py`
- `backend/database/record_audio.py`
- `backend/database/record_custody_append.py`
- `backend/docs/listen_pusher_pipeline.mdx`
- `backend/tests/integration/test_record_custody_append_emulator.py`
- `backend/tests/unit/test_pusher_storage_pcm_metrics.py`
- `backend/tests/unit/test_record_custody_append.py`
- `backend/tests/unit/test_record_gap_fill.py`
- `backend/tests/unit/test_record_token_lease.py`
- `backend/utils/batch_pipeline/record_gap_fill.py`
- `backend/utils/batch_pipeline/record_lease_append.py`
- `backend/utils/sync/record_token_lease.py`
- `backend/docs/listen_pusher_pipeline/changes/2026-11-10-token-lease-round5.md`

Implementation commit: `ff202e8cf36d221fa64e514392d9a62d4efbe47a` — `fix: count late producer appends and type custody paths`. Final receipt commit is reported in the handoff; it contains documentation only.

Final verification receipt recorded 2026-11-10T02:41:24+00:00. The final commit changes this receipt only; all production and test source remains identical to the verified implementation commit.
