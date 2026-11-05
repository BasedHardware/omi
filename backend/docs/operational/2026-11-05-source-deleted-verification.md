# Source-deletion disposition verification — 2026-11-05

Repository: `BasedHardware/omi`. Branch: `cl2-cost/privacy-source-deleted`.
Base fetched before worktree creation: `e2924da5a762dc446853e5f5914af660aaafa929`.
Task owner: cl2-cost; scope/start rulings: lead2 534a5b / 437e92.
This record covers local hermetic verification only. No production credentials,
production data, deployment, PR creation or merge were used.

The current guard matched the task: `conversation_deleted` without a tombstone
or redirect reached the missing-source-tombstone refusal in `_prepare_privacy`.
The fix permits an original, transactionally verified deleted source to settle
without content using `disposition=source_deleted`. Empty completion exposes
`reason_code=source_deleted`. Tombstone writers and usage/pricing logic were
not changed.

Kill switch: `BATCH_PIPELINE_PROJECTION_SOURCE_DELETED_ENABLED`, default on.
Set `false` to restore the previous block. Counter:
`omi_batch_pipeline_projection_source_deleted_jobs_total`, incremented after
a new terminal no-text receipt commits, once per job including multipart jobs.
See [the runbook](../runbooks/batch-projection-repair.md#deleted-source-without-a-tombstone)
for replay, counter and rollback semantics.

## Local verification

`make setup` passed in the fresh worktree. It created its own
`backend/.venv` with Python 3.11.15. The uv executable-install warning was
nonfatal; dependency synchronization and setup completed successfully.

Run from the worktree root:

```bash
/Users/dazheng/workspace/omi/bin/omi-heavy run -- bash -c 'cd backend && for test in tests/unit/test_batch_projection_source_deleted.py tests/unit/test_batch_pipeline_projection.py tests/unit/test_batch_pipeline_projection_followup.py tests/unit/test_batch_projection_privacy_hold.py tests/unit/test_batch_privacy_conversation_fence.py; do .venv/bin/python -m pytest "$test" -q || exit; done'
```

Results: source-deleted 18, projection 61, follow-up 36, privacy holds 20,
conversation fences 22: 157 passed. Each file ran in a separate pytest process.
Covered: default-on settlement through the real projector/completion path,
empty status publication, no content assignment/playback/enrichment, kill-switch
rollback, replay idempotency, the counter, multipart settlement, tombstones,
redirects, missing documents and account/binding/ledger/predecessor fences.
Outbound network is blocked by the backend hermetic test harness.

```bash
/Users/dazheng/workspace/omi/bin/omi-heavy run -- make preflight
```

Result: 41 checks passed. An earlier preflight run exited nonzero during
implementation; the subsequent run with the completed registry and code passed.

```bash
scripts/backend-python-format --check backend/config/batch_pipeline.py backend/database/batch_pipeline_projection.py backend/database/batch_pipeline_projection_session.py backend/utils/batch_pipeline/projection_disposition.py backend/utils/batch_pipeline/projection_followup.py backend/tests/unit/test_batch_projection_source_deleted.py backend/tests/unit/test_batch_pipeline_projection.py backend/tests/unit/test_batch_pipeline_projection_followup.py
git diff --check
```

Result: formatting and diff hygiene passed.

The first branch push passed all 41 preflight checks and Pyright with zero
errors, then stopped on the new end-to-end test's CPU-time guard (assertions
passed; 2.07 s against 1 s, reproduced at 2.63 s). Its unrelated fair-use
dispatch is now an asserted leaf mock and retention setup lives in the fixture;
the real privacy proof, receipt, accounting, completion and empty publication
remain tested. No timing limits or allowlists were changed. Exact guarded rerun:

```bash
# Run from backend/; the list contains tests/unit/test_batch_projection_source_deleted.py.
BACKEND_UNIT_TEST_FILE_LIST=/Volumes/Ephemeral/scratch/planscost-handoff/tombstone/sol/failed-test-files.txt /Users/dazheng/workspace/omi/bin/omi-heavy run -- bash test.sh
```

Result: 18 passed with the original CPU guard enabled.

## Changed files

- `backend/config/batch_pipeline.py`
- `backend/config/flag_budget.json`
- `backend/database/batch_pipeline_projection.py`
- `backend/database/batch_pipeline_projection_session.py`
- `backend/utils/batch_pipeline/projection_disposition.py`
- `backend/utils/batch_pipeline/projection_followup.py`
- `backend/tests/unit/test_batch_projection_source_deleted.py`
- `backend/tests/unit/test_batch_pipeline_projection.py`
- `backend/tests/unit/test_batch_pipeline_projection_followup.py`
- `config/feature-flags.yaml`
- `backend/docs/feature-flag-registry.md`
- `backend/docs/runbooks/batch-projection-repair.md`
- This dated verification record.

## Review and release boundary

Luna's bounded review found that destination IDs could impersonate the original
source. The proof was restricted to the computed original source ID and two
regression cases were added (binding target and job target, with a live source).
Luna rechecked the corrected condition and both regressions and reported the P2
resolved, with no additional findings in that focused correction.
Lead2 owns the subsequent review. No PR, merge or deployment is authorized.
Runtime counts and production behavior have not been measured.
