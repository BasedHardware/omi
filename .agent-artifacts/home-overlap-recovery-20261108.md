# Home-overlap recovery verification

Updated at: 2026-11-07T22:00:37.548577+00:00

Status: validation in progress; no push, merge or deployment in this recovery yet.

## Reconciliation

The initial local head was `9cff8f2ab02`; the published head was
`4ebac52f436ea932a56bd31343a6a7205b81214a`. After fetching the published branch,
`git log --left-right --cherry-mark` and `git range-diff` showed all 13 Home
commit pairs were patch-identical. The local copies were dropped when rebasing
onto the published head; main was then integrated while retaining that published
ancestry. This permits a normal push without overwriting any published commit.
The original local head remains at
`recovery/home-overlap-before-default-on-20261108`.

Both original dirty E2E edits were preserved and committed in `325109a045a`.
The extracted enrichment callback now mirrors explicit Process Now intent.

## Defaults and detail intent

- `HOME_PROCESSING_OWNERSHIP_ENABLED`: true when unset; false disables ownership/dedupe.
- `HOME_LIVE_MEMBER_NOTES_DEFERRED_ENABLED`: true when unset; false disables notes deferral.
- Both are permanent env kill switches, evaluated per call. The optional UID
  allowlist remains; empty admits all eligible accounts.
- The app rendering fix and ownership capability header are always on. The app
  does not read these backend env flags.
- Explicit detail reads send `X-Omi-Recording-Detail: 1`; Home lifecycle probes
  omit it. Cached detail entry refreshes quietly to carry explicit intent.
- Registry source, generated registry, pipeline contract and runbook match.

## Validation so far

Heavy commands use `/Users/dazheng/workspace/omi/bin/omi-heavy run --`.
Logs and the exact backend file selection are under
`/Volumes/Ephemeral/scratch/home-overlap-recovery-20261108/`.

- Pinned Flutter 3.44.5: 76 passed across `home_rows_test.dart`,
  `home_rows_state_space_test.dart`, `home_row_contract_render_test.dart`,
  `pending_work_store_test.dart`, `pending_work_test.dart` and
  `conversation_home_typed_fetch_test.dart` (`flutter test --no-pub --timeout 90s`).
- The regenerated after render is byte-identical to the committed after PNG:
  SHA-256 `36b858994fbfd786b917a26e3ae043480d86f6ccf5a7ffdc1af0d3bf52638139`.
  Both committed before/after iOS renders were visually checked.
- Core backend files now pass in isolation: pending work 46, sync-job retention 29,
  finalizer hooks 23. The first core attempt had two stale HTTP fake signatures;
  both were corrected and the pending-work file rerun passed.
- The broader isolated run found two cache-rollback fixture failures and three
  finalizer logging fixture failures. Corrected their setup for enabled defaults;
  focused retries are queued. Other file results are still arriving.
- Initial sync lifecycle E2E attempt exceeded the harness-wide 120s limit without
  a verdict. Retry uses documented `E2E_PYTEST_TIMEOUT=600s`.
- PR metadata check passed all five checks after adding exact line-count exceptions.
- `make preflight` is running; async-blocking check passed. Full result pending.

## In flight / resume

Do not push until remaining verification and PR body results are complete.
The existing guarded runners are observable through these log files:

- `backend-suite.log`: 15-file isolated backend selection in `backend-files.txt`.
- `preflight.log`: full `make preflight`, local wall budget 900s per backend file.
- `detail-tests.log`: three focused detail widget/provider files.
- `e2e-retry.log`: sync lifecycle and Watch Process Now with 600s harness budget.
- `homesettle-retry.log` and `finalizer-logging-retry.log`: corrected fixtures.
- `pr-body.md`: draft preserving the required attribution and footer.

A host heartbeat is armed. Inspect ownership/liveness before stopping a runner;
never kill another lane or kill by process-name pattern.

## Publication and boundaries

Fetch both main and the lane again before normal
`git push -u origin lane/home-overlap`. Remove `GOOGLE_APPLICATION_CREDENTIALS`
and every `CLOUDSDK_*` variable from the push environment; retain the pinned
Flutter SDK for hooks. Update only PR #24865 with current validation results.
Record the final outcome in ANX (the ruling is already recorded on
`card:episode-home-live-rows`). No merge or deployment is authorized.

GCP tier: none. No production reads or writes.
Session-only uploads still have no reliable conversation target at admission;
keep their target null. Supplied targets/recording IDs are persisted before results.
