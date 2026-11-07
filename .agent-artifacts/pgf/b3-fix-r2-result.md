# B3 review fixes, round 2

Status: code, the three named suites (136 tests), and preflight (44 checks) are complete; the required full selector and serialized retries are still in progress. Report checkpoint: 2026-11-07T20:44:02.214994+00:00.

Repository: BasedHardware/omi. Worktree: `/Volumes/Ephemeral/scratch/worktrees/omi/omi-lane-pgf-b3-upstream-keep-clean`. Branch: `lane/pgf-b3`. Started at `5d656b64eee`; no rebase, push, PR creation, production access, or GCP tier used. No messages or asks sent to David/ANX, per assignment.

## What was built

1. Commit-ordered datetime revisions: the space-head allocation lock assigns a monotonic server-clock microsecond timestamp, independently of caller `now`. `seq_as_of` uses the corresponding change-log stamp. Rows return this same timestamp as `updated_at`, making datetime tokens round-trip correctly even after clock regression. Event/retention timestamps remain separate. Pre-migration history is deliberately unstamped and requires integer rebase.
2. Cell-label admission: only the singleton serving store's explicit `cell1` label is accepted; unknown labels return retryable `directory_routing_unavailable` before any cell-store construction or IO.
3. Snapshot reconciliation: snapshots expose feed-shaped delete `entries` alongside current `rows`, using a shared address keyset/page budget. Tombstones are deduplicated, retained through compaction, and suppressed for recreated rows.
4. Receipt replay: `seq` and `rev` remain the original applied receipt sequence after a concurrent row advance or recreation.

Files changed:

- `backend/database/cells/store.py`
- `backend/database/cells/migrations/0003_revision_timestamps.sql`
- `backend/database/cells/serving.py`
- `backend/database/cells/feed.py`
- `backend/database/cells/mutations.py`
- `backend/models/space_sync.py`
- `backend/routers/spaces.py`
- `backend/tests/routers/test_spaces_sync.py`
- `backend/tests/unit/test_cell_store_conformance.py`

The requested external draft `/Volumes/Ephemeral/scratch/pgf-b3-pr-body-final.md` now includes “Review fixes (round 2)”. The tracked `.agent-artifacts/pgf-result.md` is untouched.

## Scope extensions taken

- Added the expand-only cell migration above. The original B3 brief forbade migrations, but round 2 requires an authoritative commit-order timestamp. Reusing caller event timestamps cannot satisfy that contract. The assignment explicitly permits correctness corrections outside the original list. Existing rows are left NULL rather than assigning invented historical commit times; integer revisions continue to work.
- Added `CELL_LABEL` in `backend/database/cells/serving.py`, outside B3's original list, to make the router validate the singleton serving identity without dialing its pool.
- No edits under `.github/`, `backend/database/jobstore/`, `backend/testing/store_fixtures.py`, production config, credentials, or spend.

## Commits

- `665a28ef7f9` — `fix(cells): resolve datetime revisions in commit order`
- `06d24bdd674` — `fix(spaces): reject unsupported cell labels before serving`
- `110978e901d` — `fix(spaces): retain snapshot deletes and original replay revisions`
- `d2d9fb83434` — `fix(cells): expose stable datetime revision timestamps on rows`

## Verification

All commands use worktree-local Python 3.11 (`backend/.venv/bin/python`) and private disposable PostgreSQL on `/Volumes/Ephemeral`. The evidence wrapper `.agent-artifacts/pgf/b3-fix-r2-verification/run-safe.py` removes `GOOGLE_APPLICATION_CREDENTIALS`, every `CLOUDSDK_*`, `SERVICE_ACCOUNT_JSON`, `FIREBASE_AUTH_CREDENTIALS_PATH`, and inherited remote/IAM PostgreSQL settings before invoking commands. It sets a synthetic 32-plus-character test `ENCRYPTION_SECRET`, a dummy OpenAI key, `OMI_REQUIRE_STORE_BACKENDS=postgres`, and an Ephemeral PG root. No real credentials or production data were used.

The following commands ran through the credential-scrubbing wrapper. Let `PY` be this worktree's absolute `backend/.venv/bin/python`, `SAFE` be `.agent-artifacts/pgf/b3-fix-r2-verification/run-safe.py` (absolute path), and `HEAVY` be `/Users/dazheng/workspace/omi/bin/omi-heavy`. Test, environment-preflight, backend type-check, async-scan, and make-preflight commands were invoked as `"$PY" "$SAFE" "$HEAVY" run -- <command>`; selector, formatter, and PR-metadata commands were invoked as `"$PY" "$SAFE" <command>`. The first retry added `--wait 3600` to heavy admission; it timed out acquiring a slot (exit 75, zero tests run). The requeued retry uses `--wait 21600`. The wrapper source is reproduced below for reproducibility.

| Cwd | Command after the safety/heavy prefix | Result |
| --- | --- | --- |
| backend | `.venv/bin/python -m pytest tests/routers/test_spaces_sync.py tests/unit/test_cell_store_conformance.py -q` | Initial timestamp run: 118 passed, 0 failed. |
| backend | `.venv/bin/python -m pytest tests/routers/test_spaces_sync.py -q` | Intermediate 87 passed; final `d2d9fb83434` run: **88 passed, 0 failed, 0 skipped**. |
| backend | `.venv/bin/python -m pytest tests/unit/test_cell_store_conformance.py -q` | Intermediate and final: **36 passed, 0 failed, 0 skipped**. |
| backend | `.venv/bin/python -m pytest tests/unit/test_directory_store.py -q` | Intermediate and final: **12 passed, 0 failed, 0 skipped**. |
| backend | `env PYTHON=.venv/bin/python bash test-preflight.sh` | **18 passed, 0 failed, 8 optional warnings** (26 checks). |
| backend | `env PYRIGHT_PYTHON=.venv/bin/python bash scripts/typecheck.sh` | **0 errors**, 75,439 warnings; exit 0. |
| repo | `backend/.venv/bin/python backend/scripts/scan_async_blockers.py --dirs backend/routers backend/utils` | **0 selected blocking findings**, exit 0. |
| repo | `make preflight` | First attempt: one reported failing check; Firestore guard timed out on `test_firestore_query_shapes.py` at 300 seconds (status 124); exit 2. |
| repo | `env OMI_PR_BODY_FILE=/Volumes/Ephemeral/scratch/pgf-b3-pr-body-final.md OMI_CHECKS_JOBS=1 BACKEND_PYTEST_WORKERS=1 BACKEND_UNIT_FILE_BUDGET_SECONDS=900 make preflight` | **44 checks passed**, 0 failed; exit 0 (3640.41 seconds). This resolves the earlier guard timeout. |
| repo | `scripts/pr-preflight --suggest` | Exit 0. |
| repo | `scripts/pr-preflight --pr-body-file /Volumes/Ephemeral/scratch/pgf-b3-pr-body-final.md --metadata-only` | Initial and final: **4 checks passed**, 0 failed; exit 0. Final metadata run: 14.47 seconds. |
| repo | `backend/.venv/bin/python backend/scripts/select_backend_unit_tests.py --changed-files .agent-artifacts/pgf/b3-fix-r2-verification/changed-files.txt --output .agent-artifacts/pgf/b3-fix-r2-verification/selected-tests.txt --reason-output .agent-artifacts/pgf/b3-fix-r2-verification/selector-reason.txt` | Selected **2,687 files**; reason: `backend/database/cells/store.py requires the full backend unit suite`. Exit 0. |
| backend | `env BACKEND_PYTEST_WORKERS=4 BACKEND_UNIT_FILE_BUDGET_SECONDS=900 BACKEND_UNIT_TEST_FILE_LIST=/Volumes/Ephemeral/scratch/worktrees/omi/omi-lane-pgf-b3-upstream-keep-clean/.agent-artifacts/pgf/b3-fix-r2-verification/selected-tests.txt bash test.sh` | **Original phase intentionally drained/stopped to correct the native Opus loader environment: 916 files completed, 911 passed, 5 nonzero.** Two reported wall timeouts: `test_batch_vendor_outage_drills.py` and `test_cross_service_deploy_contract.py`, each at 900 seconds (status 124); no failed assertion reported before termination. Two other files passed all assertions but exceeded the CPU guard (`duplicate_capture_policy`: 1.12s; `enrichment_route`: 1.01s, each versus 1.00s). `empty_capture_recovery` had 7 failures because native Opus could not be found; 61 other assertions passed. Continuation below covers that file and every remaining selected file. |
| backend | `env BACKEND_PYTEST_WORKERS=1 BACKEND_UNIT_FILE_BUDGET_SECONDS=900 BACKEND_UNIT_TEST_FILE_LIST=/Volumes/Ephemeral/scratch/worktrees/omi/omi-lane-pgf-b3-upstream-keep-clean/.agent-artifacts/pgf/b3-fix-r2-verification/retry-tests.txt bash test.sh` | Retry manifest contains both timed-out files, `test_duplicate_capture_policy.py`, and `test_enrichment_route.py`. CPU/wall guards remain unchanged. First retry: admission timeout after 3,600 seconds, exit 75, **zero tests run**. Requeued through `omi-heavy run --wait 21600`; in flight. |

Additional continuation command (backend cwd, safety/heavy prefix, `--wait 21600`):

```bash
env DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib BACKEND_PYTEST_WORKERS=4 BACKEND_UNIT_FILE_BUDGET_SECONDS=900 BACKEND_UNIT_TEST_FILE_LIST=/Volumes/Ephemeral/scratch/worktrees/omi/omi-lane-pgf-b3-upstream-keep-clean/.agent-artifacts/pgf/b3-fix-r2-verification/continuation-tests.txt bash test.sh
```

Continuation is **in flight**, 1,772 files (the native Opus retry first, then all 1,771 remaining files). Together, 911 previously passing files + 4 serialized retries + 1,772 continuation files exactly cover the 2,687-file selector. The installed `/opt/homebrew/lib/libopus.dylib` loads successfully with the explicit fallback path; neither a package install nor a host/venv configuration change was made. New safety-wrapper invocations also set this fallback path; the three named suites ran before that verification-only addition.

The old scheduler's TERM trap only logs cancellation, so an initial TERM/CONT resumed scheduling. It was paused again; after confirming zero live descendants, only owned scheduler PID 39763 (parent 39674, `bash test.sh`) was stopped with SIGKILL. All workers drained normally; no worker or other lane's process was signaled. The intentionally stopped original wrapper exited 247.

Formatting: `"$PY" -m black --line-length 120 --skip-string-normalization` ran over all eight changed Python files, then over `store.py` and `test_spaces_sync.py` after the timestamp follow-up. All commits also passed the installed staged formatter. `git diff --check 5d656b64eee..HEAD` passed.

Final required suites total **136 passed, 0 failed, 0 skipped**. Intermediate required suites totaled 135 passed; initial timestamp-focused run totaled 118 passed. Per-file logs, selection manifests, `completed-tests.txt`, `remaining-tests.txt`, and `failed-tests.txt` live under `.agent-artifacts/pgf/b3-fix-r2-verification/`. `state.json` records the active execution sessions for continuation. These are live partial-run records until the selector terminates.

The full selector began at `110978e901d`, before the row timestamp round-trip follow-up. The affected required suites reran on final code `d2d9fb83434`; preflight/type checking/metadata completed after that change. This is local verification, not remote CI or deployment evidence, and does not claim a single clean all-files final-SHA run.

Safety wrapper source:

```python
import os
import subprocess
import sys

clean = dict(os.environ)
for name in list(clean):
    if name.startswith('CLOUDSDK_') or name in {
        'GOOGLE_APPLICATION_CREDENTIALS', 'SERVICE_ACCOUNT_JSON',
        'FIREBASE_AUTH_CREDENTIALS_PATH', 'OMI_TEST_POSTGRES_DSN',
        'OMI_TEST_POSTGRES_IAM', 'OMI_TEST_POSTGRES_ALLOW_REMOTE',
    }:
        clean.pop(name, None)
clean.update(
    DYLD_FALLBACK_LIBRARY_PATH='/opt/homebrew/lib',
    ENCRYPTION_SECRET='pgf-b3-round-two-hermetic-test-secret-2026',
    OPENAI_API_KEY='test-openai-key-not-real',
    OMI_TEST_PG_ROOT='/Volumes/Ephemeral/scratch',
    OMI_REQUIRE_STORE_BACKENDS='postgres',
)
raise SystemExit(subprocess.call(sys.argv[1:], env=clean))
```

## Known gaps

- Broad verification is still in progress. At 2026-11-07 19:54:46 UTC, host load averages were 114.04 / 87.65 / 70.04, and this run's four pytest workers received roughly 1.5-3.9 percent CPU each. No other lane's processes were signaled. This is a verification scheduling limitation, not a failing product assertion.
- Migration `0003_revision_timestamps.sql` must be applied before the new writer runs. No database deployment performed.
- Pre-migration datetime history cannot be reconstructed safely; clients must rebase using integer revisions for unstamped history.
- No live/production canary and no client acceptance test; the API remains default-off.

## Draft PR body

### What changed and why

Add the default-off spaces sync protocol and address round-two review findings: commit-ordered datetime revisions, supported-cell admission, snapshot tombstones, and stable original replay revisions.

### Product invariants affected

No additional invariant-globbed paths. Existing B2 `INV-CUTOVER-1` and `INV-MEM-3` fences remain authoritative.

### How it was verified

Required suites: 136 passed, 0 failed/skipped. Final preflight: 44 checks passed. Type check: 0 errors. Async scan: 0 findings. The 2,687-file selector and isolated vendor-drill wall-timeout retry remain in progress. Credential-scrubbed local Python 3.11 and disposable PostgreSQL; no GCP tier, production data, push, or deployment.

### Tests

Regression tests cover confirmed PostgreSQL row-lock contention with reversed caller times; NULL legacy stamps; datetime round trips during logical clock advances; unknown cell labels on every route; snapshot delete shape, pagination, compaction and recreation; and patch/delete replay after concurrent advancement.

### UI evidence

UI-Evidence: none -- backend only

### Failure class (fixes)

Failure-Class: none
