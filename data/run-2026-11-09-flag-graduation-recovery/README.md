# Flag graduation recovery, 2026-11-09

Recovered `cb58353ace9fafc62da6e8ef89c6700bcde55d21`; comparison base is `82969e2b845b4f1c76d78f63272ad83b11cf9aa0`.

The supplied three input files were read from `/Users/dazheng/workspace/omi/data/run-2026-11-09-flag-decisions/`. Their hashes and every disposition are in [scope-audit.json](scope-audit.json). No production data or flags were read or written. No GCP credential tier was used. No push or PR is authorized for this lane.

## Scope audit

All 22 graduate keys are accounted for: 17 removed, five deferred with `review_by: 2026-11-23`. All 42 retirement registry rows and all 103 registry-only rows are structurally identical to the comparison base. Their serialized hashes are recorded in the audit. The 42 retirement-list key references in changed production Python modules remain present; references in superseded graduate tests and notes necessarily change. The extra `EPISODES_UID_ALLOWLIST` is outside the 42-key retirement docket and was redundant at 100 percent.

| Graduate key | Disposition |
| --- | --- |
| `AUDIO_ARCHIVE_COALESCE_ENABLED` | Removed; permanent production behavior |
| `CONVERSATION_NOTES_AGENT_PERCENT` | Removed; permanent production behavior |
| `EPISODES_CLIENT_CHANNELS` | Removed; permanent production behavior |
| `EPISODES_PERCENT` | Removed; permanent production behavior |
| `LIVE_CAPTURE_WINDOW_MERGE_UNION` | Deferred to 2026-11-23; conflicting reachable readers |
| `LIVE_CAPTURE_WINDOW_TRANSLATOR_SENDS` | Deferred to 2026-11-23; conflicting reachable readers |
| `REVIEW_SURFACE_MODE` | Removed; permanent production behavior |
| `SERVER_BATCH_ONLY_AUTO_LANGUAGE_PERCENT` | Removed; permanent production behavior |
| `SERVER_BATCH_ONLY_MOBILE_PERCENT` | Removed; permanent production behavior |
| `SERVER_BATCH_ONLY_VISIBLE_RESTORE_PERCENT` | Removed; permanent production behavior |
| `SONIOX_CAPTURE_AXIS_DIAGNOSTICS` | Deferred to 2026-11-23; conflicting reachable readers |
| `SONIOX_WIRE_LEDGER` | Deferred to 2026-11-23; conflicting reachable readers |
| `SPEAKER_MATCH_SCORES_ENABLED` | Removed; permanent production behavior |
| `STT_ROUTING_MODE` | Removed; permanent production behavior |
| `STT_ROUTING_ON_PERCENT` | Removed; permanent production behavior |
| `SYNC_DURABLE_STATUS_RECONCILIATION` | Removed; permanent production behavior |
| `CONVERSATION_REPROCESS_RESULT_CONTRACT_ENABLED` | Removed; permanent production behavior |
| `FIRST_SUMMARY_DEADLINE_ENABLED` | Removed; permanent production behavior |
| `FIRST_SUMMARY_DEADLINE_PERCENT` | Removed; permanent production behavior |
| `FIRST_SUMMARY_PRESERVE_ADMITTED_ENABLED` | Deferred to 2026-11-23; conflicting reachable readers |
| `SYNC_ASSIGNMENT_CONTENTION_RETRY_ENABLED` | Removed; permanent production behavior |
| `SYNC_LEGACY_COMPLETION_CONVERGENCE` | Removed; permanent production behavior |

The five deferrals and exact reader traces are documented in [the pipeline change note](../../backend/docs/listen_pusher_pipeline/changes/2026-11-09-flag-graduation.md). The lead must include these five exceptions in the combined PR body. `SERVER_BATCH_ONLY_VISIBLE_RESTORE_PERCENT` retains the zero behavior; its preview implementation and dead metering are removed. The router stays on at 100 percent, with independent product, health, withdrawal and capacity gates intact. Budget slots fall from 165 to 161.

## Recovery corrections

- Restored the independently owned first-summary allowlist and preservation readers in the shared stage resolver, including its existing empty-owner behavior.
- Kept completed-summary routing test coverage by using durable completion state, after removing the rollout flags.
- Pinned reconnect routing telemetry to current permanent admission, even when a persisted snapshot records an old off or shadow arm.
- Removed a stale short-circuited reference to the deleted summary gate; corrected the route-role reader trace.
- Removed dead paid-visible-preview counters and context, and report batch-only fallback accurately.
- Removed the unused contention-retry argument and migrated every in-tree caller; retries are permanent.

## Validation

All heavy commands use `/Users/dazheng/workspace/omi/bin/omi-heavy run -- ...`. Every test command unsets `GOOGLE_APPLICATION_CREDENTIALS` and all `CLOUDSDK_*` variables. Registry validation is reproducible with `run-validation.sh <Ephemeral-log-directory>`; append `all` to include backend test selection and execution.

| Command inside the heavy gate | Result |
| --- | --- |
| `backend/.venv/bin/python scripts/check_feature_flag_registry.py` | PASS; existing warnings remain |
| `backend/.venv/bin/python -m pytest -q scripts/test_check_feature_flag_registry.py` | PASS; 59 tests |
| `bash backend/scripts/pre-deploy-check.sh` with the worktree venv on PATH | PASS; source-only dev/prod contracts, 36 admission tests and 511 pytest tests |
| `BACKEND_UNIT_TEST_FILE_LIST=<selected-list> BACKEND_PYTEST_WORKERS=4 bash backend/test.sh` | RUNNING; automatic changed-file selection chose all 2,721 files |
| `make preflight` | First run timed out the Firestore query-shape guard at 300 seconds; retry queued with `OMI_CHECKS_JOBS=1` and `OMI_PR_BODY_FILE` pointing to the draft |
| `scripts/pr-preflight --pr-body-file <draft> --metadata-only` | Pending |
| `git diff --check` | PASS |

The first registry and registry-test attempts exhausted the heavy gate's 900-second admission limit without executing; the retry used a 3600-second admission limit and passed. Terminal backend and preflight results will replace the pending entries.

Rollback: revert the recovery and graduation commits. This lane makes no runtime change.
