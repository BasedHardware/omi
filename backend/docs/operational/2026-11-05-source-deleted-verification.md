# Source-deletion disposition verification — 2026-11-05

Repository: `BasedHardware/omi`. Branch: `cl2-cost/privacy-source-deleted`.
Initial base: `e2924da5a762dc446853e5f5914af660aaafa929`.
Round 2 base: `cc188f5369a22816eecf772b4914647bed504cff`.
Round 3 base: `112feeafc4bdfdee243c0d9f522b0c0b137f8663`.
Task owner: cl2-cost; scope/start rulings: lead2 534a5b / 437e92.
This record covers local hermetic verification. No production credentials,
production data, deployment, PR creation or merge were used. GCP tier: none.

## Current contract

An original source with `deleted=true`, no tombstone and no redirect may record
`disposition=source_deleted`. The source, account/privacy generation, immutable
binding, ledger ownership and predecessor remain transactionally fenced.

Completion aggregates every bound sibling and every part. If **any** receipt
has `source_deleted`, normal completion returns empty `new_memories` and
`updated_memories` and `reason_code=source_deleted`. The publisher is **not
called**, even with an empty result. Earlier persisted content parts cannot
escape this decision, regardless of which part contains the deletion receipt.
Partial results also withhold every ID, including when the deletion receipt
belongs to a held entry skipped for output. Existing partial custody semantics
remain intact. Replaying an older mixed completion removes its cached output
IDs without changing its recorded usage. Tombstone and redirect behavior is unchanged.

Kill switch: `BATCH_PIPELINE_PROJECTION_SOURCE_DELETED_ENABLED`, default **on**.
Set `false` to restore the missing-tombstone block. Counter:
`omi_batch_pipeline_projection_source_deleted_jobs_total`. It increments after
new job settlement commits, not when individual parts persist and not on replay
(including repair of an already completed legacy result).
Completion logs contain a fixed event/outcome, without user IDs or content.
See [the runbook](../runbooks/batch-projection-repair.md#deleted-source-without-a-tombstone).
Full and partial `source_deleted` completion skip `_commit_usage` entirely.
They also skip new usage attribution, the usage-cache writer fence, fair-use
dispatch and historical charge-step reissue. Transactional aggregation controls
the bypass, including markers inside held entries. Partial results carry
`reason_code=source_deleted` while preserving their partial custody status.
Earlier committed accounting is preserved; no refund or backfill occurs.
Deletion/tombstone writers, pricing, plans, limits and normal accounting
formulas and ordering are unchanged.

## Verification

`make setup` was completed in this worktree during Round 1; its own
`backend/.venv` uses Python 3.11.15. No shared venv was used.

Exact Round 3 command, from the worktree root:

```bash
printf '%s\n' tests/unit/test_batch_projection_source_deleted.py tests/unit/test_batch_pipeline_projection.py tests/unit/test_batch_pipeline_projection_followup.py tests/unit/test_batch_projection_privacy_hold.py tests/unit/test_batch_privacy_conversation_fence.py tests/unit/test_batch_pipeline_speech_redrive.py tests/unit/test_batch_pipeline_quarantine_recovery.py tests/unit/test_batch_pipeline_artifact_missing.py tests/unit/test_batch_artifact_missing_reupload.py tests/unit/test_batch_language_recovery.py > /Volumes/Ephemeral/scratch/planscost-handoff/tombstone/sol/round2-test-files.txt
BACKEND_UNIT_TEST_FILE_LIST=/Volumes/Ephemeral/scratch/planscost-handoff/tombstone/sol/round2-test-files.txt /Users/dazheng/workspace/omi/bin/omi-heavy run -- bash -c 'cd backend && bash test.sh'
```

Result: **572 passed across ten files**, including 40 source-deletion cases. `test.sh` used separate pytest
processes and its original CPU guard. Outbound network is blocked by the
backend test harness. No timing thresholds or allowlists were changed.

The source-deletion cases include single-part no-publish, mixed content/deletion
parts in both positions, strict kill-switch blocking, unchanged tombstone and
redirect publication, deferred once-only counting, replay, older mixed
completion suppression, partial-output suppression (including held-entry
deletions), and unchanged historical usage. Round 3 asserts no Firestore usage
commit, fair-use dispatch, charge-step reissue or usage-cache writer invocation
for single-part, mixed (both orders) and partial cases. Mixed and partial
regressions also cover an earlier charged partial ledger and replay. Supplied
positive seconds and prepared usage deltas must still produce no accounting
writes. Tombstone/redirect controls retain their normal accounting calls.

Validation uses the normal pre-push hook with local review metadata supplied
through `OMI_PR_BODY_FILE`. It opens no PR. The hook includes the shared
preflight, Pyright and guarded selected backend unit tests.

## Review and boundaries

Round 3 addresses the usage-accounting reachability BLOCK against `112feeaf`.
The completion helpers in `sync_ledger.py` were inspected: they write completion
status/result/expiry only; all accounting is isolated behind the skipped commit.
The partial and held-entry regressions now exercise `Projector.complete_held`
with publisher mocks and explicitly assert no callback. Luna independently
reviewed the Round 3 code and relevant completion/replay/accounting paths and
returned PASS with no actionable findings. The guarded suite passed all 572
tests after the final regression additions.

Round 2 addresses the mixed-part publication BLOCK against `cc188f5`.
A fresh Luna review found that a legacy completed-ledger repair was being
counted as a new termination. That repair now reports no new completion;
its regressions assert no counter increment. Luna confirmed the correction
and reported no directly related actionable issue. The guarded suite passed
again after this correction. An additional real partial-completion regression reproduced a leak when a held entry containing
a deletion receipt was skipped. The fix carries that marker separately into
the shared visibility fence, preserving held counts. Luna reviewed that
correction with no findings; all 566 Round 2 tests passed. Round 3 additionally
suppresses accounting for these jobs.

Local branch-review metadata includes the required narrow publisher-module
line-count allowance (no PR has been opened):

```text
Failure-Class: none
Line-Count-Exception: backend/utils/batch_pipeline/projection.py | 1698 -> 1702 | The job-wide privacy fence belongs at the central publish decision after aggregation; the same service paths must suppress fair-use dispatch for source-deleted full and partial completions.
```
Lead2 owns subsequent review; no PR, merge or deployment is authorized.

Already delivered content cannot be recalled by this publisher fence. This
change does not erase conversation documents or alter deletion/tombstone
writers. Older completed records are sanitized only when replayed; no backfill
is run. The Prometheus counter is process-local; a crash after settlement
commits but before increment can undercount. Runtime metrics and production
behavior have not been measured.
