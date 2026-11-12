# Token lease: batched pre-review fixes

This is the local follow-up to #25018 at `5207fe3ebd3b`. Seven pre-review reports were read from the pipeline-refactor and Firestore-cost lead runs. Fresh main `8141729fccd928b90d16b34c13bcc162fef01fa5` was merged in `f408a309c2c6`; no rebase or force operation. Main's 223 alert payloads and the two token-lease payloads are an exact union of the split files, regenerated through `backend/scripts/provision_monitoring_alerts.py --regenerate`.

## Disposition ledger

| Finding | Disposition | Result / evidence |
|---|---|---|
| Fresh-main alert conflict (both merge reviews) | Fixed | Regenerated exact 225-rule union, including `omi-batch-staged-input-age`; alert/telemetry contracts cover the mirror. |
| #24866 adjacent-file dependency (both merge reviews) | Fixed sequencing | #24866 was confirmed open, head `ff7e36a2a168`; this branch merges main independently. Landing order is #25018 first, then #24866 merges the resulting main and preserves both transaction/scheduling intents. The actual PR body now states this explicitly; its code head remains unchanged until refactor-lead pushes. |
| Unfinished-row retention KeyError (both correctness/custody rounds) | Fixed | Retention requires closed/partial plus aware, ordered datetime bounds before any storage IO; unfinished uploads keep the original successful response. |
| Retain indexes unguarded timestamps | Fixed with same guard | Both timestamps are validated, including missing/null, malformed and naive values; no direct row indexing. |
| Recovery publication fence bypass under worker rollback | Fixed | Separate jobs enter `record_recovery_waiting`, invisible to old `record_pending` workers. Mode-independent transactional promotion waits for original publication. The active repair CronJob calls the same bounded promoter even with the seal worker idle; real emulator tests exercise that entrypoint against ledger and direct-job authorities. |
| Registration loses late observation after committed reply loss | Fixed | Persist `append_late` on the exact token and return it on idempotent re-registration. Unit and real committed-response-loss proofs retain one revision and one late event after storage. |
| Manifest renews frame producers / shadow can 503 | Fixed | Manifest renewal is serve-cohort only. Custody renewals target podless custody-source tokens, including protection against previously mislabeled pod-owned tokens; frame tokens are unchanged. Off/shadow/non-cohort perform no manifest token IO. |
| Partial selected archive becomes false 503 | Fixed | A nonempty selected subset is a durable append; deliberately unselected files preserve route semantics. Genuine partial storage failures remain refusals with no late counter. |
| Renewal error drops live audio | Fixed | Pusher renewal failures return to the storage lane without advancing the successful renewal clock. |
| Renewal error tears down live socket | Fixed with same guard | Every pusher caller uses the guarded method; cancellation still propagates normally. |
| Failed begin resurrected by next frame | Fixed | Track committed registrations separately from candidate tokens retained for abandonment. Failed or in-flight uncommitted candidates cannot renew. |
| fail_recording bookkeeping/gauge leak | Fixed | Retire local clocks, locks, late observations and registration ownership on failure, including an in-flight renewal completing afterward. |
| Custody receipts never expire | Fixed | Active repair deletes receipts after 24h using existing server `recorded_at`, including old receipt versions, under bounded pages/time. Audio and recovery jobs are untouched. No idle worker activation or out-of-band TTL policy. |
| Finish receipt can survive account erasure | Fixed | Enroll `assert_batch_write_allowed` in every new receipt-producing transaction before any write/early mutation. Read-only existing-receipt replay stays read-only. A real emulator test fences erasure before child enumeration and rejects a later finish before it can create an unseen child receipt. |
| Shadow lease_would_expire allegedly missing on active repair | Not a bug | Full planners already increment at `utils/batch_pipeline/record_seal_repair.py:251` and `utils/batch_pipeline/record_seal_nojob.py:190`; partial finish increments at `database/record_partial.py:161`, and `utils/observability/firestore_probe_export.py:21` exports the collector. The cluster wrapper copies the diagnostic. Incrementing there would double-count. Added active-path nojob/pending regressions with/without diagnostics, leaving production counting unchanged. |
| Custody emulator proof absent from CI | Fixed | Named run in the existing emulator proof runner and matching workflow triggers. |
| Nojob emulator proof skips unit shards | Fixed | The existing emulator CI lane now runs it with a real loopback emulator; no skip removed or weakened. |
| Lifecycle property proof absent from CI | Fixed | Invoke the existing hermetic lifecycle runner with the explicit property module; CI installs its Redis/FFmpeg/Opus leaves and triggers on both modules. |
| Real PromQL backtest manual-only | Fixed | New checksum-pinned promtool check in the checks manifest for both local and CI; actual split-file expression is evaluated. |
| 50ms Cloud Tasks deadline race | Fixed | Inject actual timeout expiry only once pipeline/enqueue have entered, with an unresolved event. Keep the exact one-marker-write assertion and assert exactly one enqueue call. No timeout-only increase. |
| Killed-child test still uses real 0.3s budget (nit) | Fixed | Keep the readiness pipe and advance the coordinator's injected clock; row expiry no longer depends on host scheduling. |
| Literal GKE lease env overrides shared rollout vector | Fixed | Explicit producer ConfigMap references replace literal overrides. Validated protected-environment inputs are bound in runner steps (rather than workflow scope) before ConfigMap writes and feed both runtime renderers; rendered off/shadow/serve tests compare sync, pusher, listen and the separately typed repair vector. |

## Protocol and deployment notes

Each record-pending scan adds one waiting-state query and at most 100 transactional publication/privacy checks with a CAS write; a fresh 60s backoff prevents repeated writes by concurrent scanners. The active repair CronJob also performs one waiting query and at most 100 promotion checks per run under a separate 30s phase; receipt expiry gets its own 30s phase, so at most 60s of custody maintenance precedes the unchanged audio-repair budget. The checked-in idle worker remains disabled. Only current images can promote a parked recovery after original publication. Flag rollback still promotes; an old-image rollback safely retains the obligation until rollforward. Original jobs/units and raw audio remain immutable. New cleanup deletes metadata receipts only. Its 24h window exceeds the bounded request plus lease margin; it selects the existing `recorded_at` so no receipt backfill is required. The registry declares the collection-group `recorded_at` ascending index and regenerates `firestore.indexes.json`; schema readiness remains a release prerequisite, with no cloud changes performed here.

GitHub documents environment-level configuration availability after runner environment declaration ([contexts reference](https://docs.github.com/en/actions/reference/workflows-and-actions/contexts)). The rollout binding therefore runs as a job step and writes validated values to `GITHUB_ENV`; a regression rejects workflow-scope capture and requires this step before every standalone ConfigMap write.

Apply producer rollout inputs consistently through the protected environment and shared ConfigMap, roll every producer, and only then change the separately typed repair values to the same vector. Checked-in defaults remain off. Preserve the 48h shadow soak, fixed release epoch and approved ramp. #25018 lands first; refactor-lead then reconciles #24866 against that resulting main. The older opposite-order note is superseded by this documented sequence; both PRs remain under refactor-lead's control.

## Validation

Canonical unit runs use `bin/omi-heavy run --wait 7200 --no-priority -- python3 /Volumes/Ephemeral/scratch/tokenlease-batched-validate.py <label> <test stems...>`. The launcher runs `bash test.sh` from `backend/`, one file per subprocess, with `BACKEND_UNIT_TEST_FILE_LIST`, `BACKEND_PYTEST_WORKERS=1`, `BACKEND_UNIT_FILE_BUDGET_SECONDS=900`, CI defaults and no personal `.env`. It unsets `GOOGLE_APPLICATION_CREDENTIALS`, `SERVICE_ACCOUNT_JSON`, all `CLOUDSDK_*`, provider/stage overrides and ambient project settings; each run uses a private HOME/config/temp and bounded numerical pools. No GCP tier, production data or cloud credentials were used.

| Unit file (`backend/` prefix omitted) | Exact terminal result | Run |
|---|---|---|
| `tests/unit/test_record_token_lease.py` | 90 passed in 15.51s | `focused-token-final` |
| `tests/unit/test_record_custody_append.py` | 76 passed, 1 warning in 129.23s (0:02:09) | `focused-deploy-final` |
| `tests/unit/test_record_token_lease_prereview.py` | 39 passed, 1 warning in 65.19s (0:01:05) | `focused-deploy-final` |
| `tests/unit/test_record_token_lease_ci.py` | 11 passed in 1.88s | `focused-ci-final` |
| `tests/unit/test_record_lease_append.py` | 1 passed, 1 warning in 68.37s (0:01:08) | `focused-1` |
| `tests/unit/test_pusher_storage_pcm_metrics.py` | 21 passed, 9 warnings in 107.05s (0:01:47) | `focused-deploy-final` |
| `tests/unit/test_pusher_record_abandon.py` | 24 passed, 9 warnings in 60.76s (0:01:00) | `focused-1` |
| `tests/unit/test_record_barrier_executor.py` | 15 passed, 9 warnings in 41.20s | `focused-1` |
| `tests/unit/test_record_drain_barrier_backoff.py` | 22 passed, 1 warning in 8.14s | `focused-1` |
| `tests/unit/test_record_partial.py` | 82 passed, 1 warning in 52.36s | `focused-3` |
| `tests/unit/test_record_producer_proof.py` | 27 passed in 3.76s | `focused-1` |
| `tests/unit/test_record_seal_cluster_repair.py` | 154 passed, 1 warning in 51.31s | `focused-3` |
| `tests/unit/test_record_token_lease_deploy.py` | 15 passed in 155.26s (0:02:35) | `focused-deploy-final` |
| `tests/unit/test_monitoring_alert_rule_contract.py` | 75 passed in 49.44s | `focused-1` |
| `tests/unit/test_monitoring_telemetry_contract.py` | 54 passed in 10.50s | `focused-1` |
| `tests/unit/test_monitoring_alert_backtest.py` | 29 passed in 1.84s | `focused-1` |
| `tests/unit/test_oldest_age_flat_alerts.py` | 14 passed in 12.26s | `focused-1` |
| `tests/unit/test_legacy_dark_router.py` | 15 passed, 16 warnings in 55.44s | `focused-1` |
| `tests/unit/test_sync_cloud_tasks.py` | 208 passed, 143 warnings in 107.67s (0:01:47) | `focused-1` |
| `tests/unit/test_sync_v2.py` | 188 passed, 74 warnings in 386.58s (0:06:26) | `focused-1` |
| `tests/unit/test_verify_pusher_config_references.py` | 31 passed in 15.46s | `focused-1` |
| `tests/unit/test_record_gap_fill.py` | 87 passed, 1 warning in 16.84s | `focused-1` |
| `tests/unit/test_batch_pipeline_live.py` | 106 passed, 1 warning in 73.84s (0:01:13) | `focused-2` |
| `tests/unit/test_batch_pipeline_intake.py` | 85 passed, 1 warning in 3.56s | `focused-1` |
| `tests/unit/test_record_pending_repair.py` | 63 passed, 1 warning in 7.92s | `focused-1` |
| `tests/unit/test_lifecycle_sim_unit.py` | 50 passed, 9 warnings in 21.35s | `focused-1` |
| `tests/unit/test_lifecycle_invariants.py` | 248 passed, 86 xfailed in 21.60s | `focused-1` |
| `tests/unit/test_lifecycle_state_table_writers.py` | 1740 passed in 87.08s (0:01:27) | `focused-1` |
| `tests/unit/test_firestore_query_shapes.py` | TIMEOUT after 900s; no completed summary | `focused-1` |
| `tests/unit/test_firestore_outside_query_contract.py` | 31 passed, 10 warnings in 284.51s (0:04:44) | `focused-1` |
| `tests/unit/test_render_gke_backend_config.py` | 19 passed in 47.32s | `focused-1` |
| `tests/unit/test_backend_runtime_env_validator.py` | 206 passed in 786.02s (0:13:06) | `focused-1` |

The first broad run found stale fixture assumptions in partial renewal, due-page assertions and Helm image values. Those assertions now model podless custody identity, the additional publication-gate query and the required digest pull policy; corrected file results above supersede those first-run failures. The initial receipt-budget API error and emulator privacy/consent fixture defects were corrected in the preserved commits. No skip, xfail or assertion was weakened.

Additional terminal results, collected from the stopped run:

| Command / proof | Exact result | Evidence log under `/Volumes/Ephemeral/scratch/` |
|---|---|---|
| Native `tests/integration/test_record_custody_append_emulator.py`, real loopback Firestore | 24 passed, 12 warnings in 28.30s | `tokenlease-batched-preflight-final.log` |
| `tests/unit/test_record_seal_nojob_emulator.py`, same emulator | 4 passed, 1 warning in 5.01s | `tokenlease-batched-preflight-final.log` |
| `tests/integration/test_held_custody_conformance.py`, sim/emulator/Postgres required | 75 passed, 1 warning in 175.91s | `tokenlease-batched-types-2.log` |
| `tests/integration/test_recovery_custody_conformance.py`, sim/emulator/Postgres required | 39 passed, 40 warnings in 174.95s | `tokenlease-batched-types-2.log` |
| `bash scripts/typecheck.sh` from backend (repository hook selection) | 0 errors, 78927 warnings, 0 informations; command exit 0 | `tokenlease-batched-types-2.log`, final `QUALIFICATION_RESULT 0` |
| `bash backend/scripts/pre-deploy-check.sh` | 36 unittest tests plus 511 pytest tests passed; exit 0 | `tokenlease-batched-full-deploy.log` |
| `tests/promql/record_token_lease.py --promtool <verified promtool>` from backend | 7 scenarios passed; exit 0 | `tokenlease-batched-promql-1.log` |
| Full hermetic lifecycle scenarios plus properties | 3 failed, 31 passed, 3 existing xfailed in 2600.91s; all three named lease exits passed | `tokenlease-batched-preflight-1.log` |
| Expanded local preflight, base `8141729fccd9` | Exit 1 at the first manifest check: 26 disclosure regression tests passed, then missing `lease_would_expire` PR-body exit declaration | `tokenlease-batched-full-preflight-ci.log` |

The three terminal lifecycle failures are the existing projection-close-debt scenario's `exhaustion`, `eviction` and `late_tombstone` variants. The first lacks its durable marker after a logged marker-write timeout; the second exhausts `SweepBudget(30)`; the third retains its marker after reporting a changed row. They are unresolved validation failures, not declared flakes or proven token-lease defects. The three lease state-table exits (`seal`, `partial_finish`, `reactivated`) passed. An earlier interrupted replay lost its emulator and produced connection-refused cascades; that invalid run is not acceptance evidence.

The native session stopped before the final report/commit. No session failure trace is available in the worktree; validation receipts show both final orchestration chains terminated nonzero, rather than remaining in flight. The expanded preflight did not reach later checks. Its PR-body omission is corrected in the local handoff draft by naming `lease_would_expire` as a shadow diagnostic and its next-observation/finish/reactivation exits. The disclosure checker is rerun alone in the continuation, without repeating its already-passing 26-test regression suite. The generic query-shape file also still needs a completed run after its 900s timeout.

### Continuation-15 completion boundary

Preserved source head: `72bfce06fedfdfab7e997edf82cbe2c873f44d66`. This continuation changes this report only; it makes no source, `.github`, merge, credential, deployment or rollout change. A fresh `bin/omi-heavy` invocation of the canonical `backend/test.sh` for `test_record_token_lease_prereview.py` passed all 39 tests (2.65s pytest; command exit 0). The focused disclosure checker passed (0 knobs, 1 new diagnostic state); the exact offline alert-union proof passed (223 unchanged merged-main payloads plus both exact lease split-file payloads). Its first attempt still failed because inline code is stripped by the disclosure checker; the corrected plain-prose identifier passed on the next attempt. The full local gate is **not green**; m1 must resolve/reproduce the three projection lifecycle failures and complete the query-shape and expanded preflight gates before the one consolidated push and independent review. No new P1 was established by this inspection; no additional implementation batch was opened.

The recorded merge base is `8141729fccd928b90d16b34c13bcc162fef01fa5`. The shared `origin/main` ref had advanced to `986386ba0e480dd6963f0677a30cfbc7e5294580` at continuation inspection. This continuation deliberately performs no additional merge under its preserve-head instruction. Fresh-main integration/mergeability remains the push owner's responsibility; the previous 225-rule union is proven against the main commit actually merged, not asserted against later unseen changes.

## Batch commits and files

- `f408a309c2c6`: merge main `8141729fccd928b90d16b34c13bcc162fef01fa5`; regenerate the exact alert union.
- `c22390c168c1ac32098097329300fe187b5566a6`: custody, publication, retry, retention, CI, timing and rollout fixes.
- `b3d4fd8ea26d`: run the bounded recovery promoter from the active production repair CronJob, with its idle-worker configuration proof.
- `162c290a65b2`: preserve the synthetic erasure authority during emulator cleanup, asserting it remains blocked.
- `8a7da342ab63`: supply the existing digest-pinned Helm fixture with main's required `IfNotPresent` pull policy; retain all rollout-vector assertions.
- `4b9f5495bd3f`: require podless custody identity, including old mislabelled frame-token protection.
- `b061cc64933c`: bind protected rollout inputs after runner environment declaration and before standalone ConfigMap writes.
- `1e8a33c72c98`: update renewal fixtures to actual podless custody identity.
- `999f00ecff37`: prove the parked recovery privacy-blocked exit against Firestore.
- `38ef0980861f`, `f9daa9f607ba`: isolate emulator client project identity and preserve async parametrization.
- `6956b711d18a`: run the custody/nojob/lifecycle proofs first inside the existing emulator job and regenerate its inventory.
- `72bfce06fedf`: seed consent before the privacy-revocation proof.
- This validation-only report is the final local completion commit. No amend, rebase, push or new review.

The preserved batch commits change these 50 files (the merge separately incorporates main):

```text
.github/actions/deploy-backend-stack/action.yml
.github/checks-manifest.yaml
.github/ci-budget.yaml
.github/workflows/backend-emulator-proofs.yml
.github/workflows/gcp_backend_listen_helm.yml
.github/workflows/gcp_backend_pusher.yml
backend/charts/backend-listen/dev_omi_backend_listen_values.yaml
backend/charts/backend-listen/prod_omi_backend_listen_values.yaml
backend/charts/backend-listen/values.yaml
backend/charts/pusher/dev_omi_pusher_values.yaml
backend/charts/pusher/prod_omi_pusher_values.yaml
backend/charts/pusher/values.yaml
backend/database/batch_pipeline_record_lease_recovery.py
backend/database/batch_pipeline_store.py
backend/database/firestore_index_registry.py
backend/database/record_audio.py
backend/database/record_custody_append.py
backend/database/record_custody_receipts.py
backend/database/record_recovery_gate.py
backend/deploy/runtime_env.yaml
backend/deploy/runtime_env/_base.yaml
backend/docs/feature-flag-registry.md
backend/docs/listen_pusher_pipeline.mdx
backend/docs/listen_pusher_pipeline/changes/2026-11-09-record-token-lease.md
backend/docs/listen_pusher_pipeline/changes/2026-11-10-token-lease-batched-prereview.md
backend/routers/sync.py
backend/scripts/check_record_token_lease_promql.py
backend/scripts/run-emulator-proofs.sh
backend/testing/lifecycle_properties/test_properties.py
backend/tests/integration/test_record_custody_append_emulator.py
backend/tests/support/firestore_batch_pipeline_drivers.py
backend/tests/support/lifecycle_state_table.py
backend/tests/support/lifecycle_writer_inventory.py
backend/tests/unit/test_batch_pipeline_live.py
backend/tests/unit/test_pusher_storage_pcm_metrics.py
backend/tests/unit/test_record_custody_append.py
backend/tests/unit/test_record_partial.py
backend/tests/unit/test_record_seal_cluster_repair.py
backend/tests/unit/test_record_token_lease.py
backend/tests/unit/test_record_token_lease_ci.py
backend/tests/unit/test_record_token_lease_deploy.py
backend/tests/unit/test_record_token_lease_prereview.py
backend/tests/unit/test_sync_cloud_tasks.py
backend/tests/unit/test_sync_v2.py
backend/tests/unit/test_verify_pusher_config_references.py
backend/utils/batch_pipeline/record_lease_append.py
backend/utils/batch_pipeline/record_seal_cluster_repair.py
backend/utils/pusher_record_barrier.py
backend/utils/sync/record_token_lease.py
firestore.indexes.json
```
