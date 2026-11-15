# Speaker CI shard repairs — 2026-11-05

Starting branch head: `26226689febbe52e6f59f0e0d498726647c41978`.
CI evidence: [shard 3](https://github.com/BasedHardware/omi/actions/runs/42030341149/job/127254889458)
and [shard 8](https://github.com/BasedHardware/omi/actions/runs/42030341149/job/127254889431).
Job logs were fetched with `gh api repos/BasedHardware/omi/actions/jobs/JOB/logs --allow-escape-sequences`.

## Before/after and causality

| Cases | Before on branch | After |
| --- | --- | --- |
| Canary ConfigMap render | 1 failure | Passed by name |
| Recurring assignments | 7 failures, 50 passed | All 57 passed |
| Capture-loss extracted persistence hook | 2 NameErrors | Both passed by name |
| No requests imports in application utilities | 1 failure | Passed by name |

The canary CI log retains **all three** expected keys (`PROACTIVITY_REDIS_HOST`,
`REDIS_DB_HOST`, `TYPESENSE_HOST`). Its only extra key is
`BATCH_FINAL_PASS_ENABLED`; all four point at `prod-omi-backend-config-canary-987`.
The output is correct: the new speaker rollback binding must use the proposed
canary ConfigMap. The exact expected mapping adds that key and retains all old
entries and assertions.

The seven recurring failures are **caused by this branch**, not pre-existing on
`015fe4f23e027d5ff3ade56c8a18dc478c9c33ef`. A detached clean checkout of that exact
commit, with its own copy of the same installed Python dependencies, ran:

```sh
cd backend
.venv/bin/python -m pytest tests/unit/test_recurring_voice_assignments.py -q
```

Result: **57 passed, 9 warnings in 54.56 seconds**. Tracked sources were clean;
the test file and assignment implementation have no branch diff against that
commit. On the branch the same file fails seven cases. The changed
`final_pass_enabled_for` required an original unit scope, and
`recurring_enabled_for` reused it after the public scope had become
`final:batch:conversation:c1`. That suppressed binding, so later conflicting
assignments and person revocation could not retract the intended bound link.

The fix shares rollout admission while keeping the unit-scope requirement on
audio reconstruction only. Existing assignment/privacy assertions are unchanged.
A new regression keeps conversation scopes ineligible for the audio pass and
checks that existing kill switches and percentages still deny recurring binding.

The capture-loss test extracts a nested production hook using AST. Its namespace
needed the newly added `final_pass_settlements` closure. The fixture now supplies
it, and additional success/refusal tests exercise once-only settlement. The
production persistence hook is unchanged. SDK exception identities are isolated
at the database transport boundary; no HTTP calls were added, and the existing
retry/TLS and no-requests-in-utils assertions remain intact.

## Local validation

All tests ran via `omi-heavy`; no production access or GCP tier was used.
The eleven failing cases were each selected by their full pytest node ID after
the fix: **11 passed, 9 warnings in 38.96 seconds**.

The broader focused command, from `backend/`, was:

```sh
.venv/bin/python -m pytest \
  tests/unit/test_recurring_voice_assignments.py \
  tests/unit/test_recurring_voices.py \
  tests/unit/test_capture_loss_accounting.py \
  tests/unit/test_clean_sweep_migrations.py \
  tests/unit/test_verify_pusher_promotion_evidence.py \
  tests/unit/test_batch_final_pass_transient.py \
  tests/unit/test_batch_final_pass_outage.py -q
```

Result: **471 passed, 10 warnings in 98.66 seconds**. The repository's pinned
formatter leaves all changed Python files unchanged.

Detailed local logs are under `/Volumes/Ephemeral/scratch/spkfix/`:
`round14-before.log`, `round14-other-before.log`, `round14-main-recurring.log`,
`round14-named-after.log`, and `round14-focused-after.log`. This committed report
preserves their conclusions after the comparison checkout is removed. The full
installed pre-push gate runs on the resulting fix commit before publication;
its final result is recorded in the task handoff.
