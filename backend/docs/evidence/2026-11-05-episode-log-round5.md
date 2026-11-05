# Episode log round 5: projected-member proof and inert capture kill

Measured locally on m5-mbp, 2026-11-05 for BasedHardware/omi PR #24607,
`lane/epbatch2`, starting from `a9ebc518c61c9488cbeb290a877fd9fd86a6adbc`.
These are hermetic and synthetic loopback-emulator results. No GCP tier, human
cloud credentials, production reads/writes, merge, deployment or TTL apply.

## Repair proof

The exact Home member snapshots now contribute document paths and SDK
`update_time` to the repair proof. Missing, hidden and unreadable members remain
in the proof. The publication transaction reads those paths with `get_all`,
compares SDK versions, and only then stages checkpoint/views and clears dirty.
Conversation insertion at a missing path, deletion, recreation or any field
mutation rejects stale repair; later writers serialize against those reads.
No writer-specific watermark bump or timely capture delivery is required.

The [writer coverage inventory](../episode-repair-writers.md) names storage
entrypoints, including assignment canonical/donor/ancestor/replacement branches,
smart merge, lifecycle/finalization, user/privacy edits, batch/recovery,
maintenance and generic adapters. The full table is also copied into the PR
body for review. Projection targets remain epoch/lease-fenced by their single
publication writer.

Repair's conversation reads share the 128-source-document recheck budget with
episodes, links and receipt archives. Overflow is rejected before member reads.
The initial episode/source/old-projection scan stays bounded at 128; including
member reads the initial repair is bounded at 256 documents. Publication's
source recheck remains at most 128 document versions plus empty-query minimum
charges. Ordinary drains and customer serving transactions add no proof reads.

## Capture off

Global capture admission now precedes installing a commit observer, submitting
to the executor, executing an accepted callback, flushing an old intent (including
stage errors), and handling drops/cancellation. Off mode submits zero callbacks
and writes zero capture/invalidation markers, including under saturation or
submit failure. A policy release no longer invalidates in its disabled branch. A disabled SDK
retry clears the preceding aborted attempt's intent, preventing its dispatch if
capture returns before the winning commit.
Serving mutations still commit their original data/result.

`capture_possible()` can refresh the control-plane flag store, even while off.
This contains no customer data. Cached remote flag propagation and already
committing operations retain the runbook's stated limits.

## Qualification

Qualification test commands and final preflight use `/Users/dazheng/workspace/omi/bin/omi-heavy run --` with
`GOOGLE_APPLICATION_CREDENTIALS` and every `CLOUDSDK_*` variable removed.
Unit files run separately through `backend/test.sh` with its existing timing
limits and `BACKEND_PYTEST_WORKERS=1`.

- Focused selection: the same nine round-4 log suites plus
  `tests/unit/test_episode_log_round5.py`: **152 passed**, including round-2/3/4
  regressions and the policy-entry race.
- Acceptance: the exact selection recorded in the
  [round-4 evidence](2026-11-05-episode-log-round4.md), plus the new round-5 file.
  **2,978 passed** in the final post-sync run (13 round-5 cases total).
- Same 17 round-3/4 CI regression files: **127 passed**.
- `npx --no-install firebase emulators:exec --only firestore --project
  demo-omi-isolated-tests 'backend/.venv/bin/python -m pytest -q
  backend/tests/integration/test_episode_log_emulator.py'`: **25/25 passed**.
  Real assignment and smart-merge transactions commit between repair member read
  and publication while `member_refresh` stays queued and the owner is unchanged.
  Both reject publication, retain dirty/checkpoint state, and use the actual
  legacy Home route at 100% read admission. Delivery alone cannot clear dirty;
  fresh repair restores log routing. Four further cases cover uncaptured member
  edit/delete, missing-member creation and hidden-member policy changes.
- Combined log + `test_recorded_episode_timeline_emulator.py`: **52 passed,
  1 failed**. The unchanged legacy
  `test_concurrent_live_and_recorded_attachments_preserve_timeline` exhausted
  transaction attempts after `409 Transaction lock timeout`, as also observed
  in round 4. All 25 log proofs pass. Combined suite is not green. Retry budgets,
  proof concurrency and skips were unchanged; owned emulator processes stopped.
- Initial combined invocation used an incorrect timeline filename and collected
  no tests; the corrected invocation above is the measured combined result.
- Initial unit smoke found the round-4 fake client lacked collection support;
  proof prefix construction now uses the already-known UID namespace without a
  redundant client lookup. All retained round-4 cases pass in the focused suite.
- The initial PR-body validation discovered a synthetic merge conflict with
  current `origin/main` in the sync collector regex: main added the privacy
  memo-ineligible counter on the same line as this branch's episode metrics.
  The branch now retains both. That exploratory parallel run also detected
  ongoing edits; it is not counted as a successful preflight. Final preflight is serialized; the guarded push verifies committed source.
- Final `OMI_CHECKS_JOBS=1 BACKEND_PYTEST_WORKERS=1
  OMI_PR_BODY_FILE=<round-5-body> make preflight`: **70/70 checks passed**
  in 831.56 seconds. Normal guarded push uses the same serial checks without
  credential variables or hook bypasses; its completion is verified in the PR
  handoff. The final focused and emulator runs include the disabled-retry fix.

Current main (`e5f647a7f9c44459fae007835ec31abc499dad85`) was synced into the
feature branch to resolve the same-line collector conflict, retaining both metric
families. PR #24607 remains open. Writer coverage was re-audited afterward and
explicitly includes generic processing-recovery primitives plus main's new
`notes_identity.claim_late_evidence` writer. Final qualification follows that sync.

The first normal push also passed all 70 checks (793.61 seconds), then correctly
stopped on one canonical Pyright error: the repair-only conditional import of
`reconcile` was possibly unbound at the later member-read branch. The import is
now explicit at module scope. The full canonical `backend/scripts/typecheck.sh`
returns **zero errors**, and all **152 focused cases** pass again. The normal
push is retried with all hooks, selection, timeouts and credential removal intact.
