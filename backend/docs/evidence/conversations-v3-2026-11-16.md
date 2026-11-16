# Conversations v3 local verification, 2026-11-16

Base: `92b697098eb6ff200165cf005577c916aeab189f`. Local branch:
`lane/conversations-v3`. Synthetic fixtures only; no production access or GCP tier.
No push, PR creation, merge, deploy, or runtime stage/config changes.

## Backend tests

Commands from the worktree root (the `omi-heavy` executable is
`/Users/dazheng/workspace/omi/bin/omi-heavy`):

```sh
omi-heavy run -- env BACKEND_UNIT_TEST_FILE_LIST=/Volumes/Ephemeral/scratch/episode-dayparts-brief/TESTS-FINAL-V3.txt bash backend/test.sh
omi-heavy run -- env BACKEND_PYTEST_WORKERS=2 BACKEND_UNIT_TEST_FILE_LIST=/Volumes/Ephemeral/scratch/episode-dayparts-brief/TESTS-FINAL-RETRY-V3.txt bash backend/test.sh
omi-heavy run -- env BACKEND_PYTEST_WORKERS=1 BACKEND_UNIT_TEST_FILE_LIST=/Volumes/Ephemeral/scratch/episode-dayparts-brief/TESTS-STREAM-V3.txt bash backend/test.sh
```

The first run covered 383 files: 9,695 passed, 9 failed, 13 skipped,
6 deselected. Five failed files: deletion/revision fixtures lacked assignable
snapshot IDs; the Flex defaults assertion needed the new lane; two listen
subprocess checks failed under host contention (permission/ps timeout). After
fixes, all five passed in the second run, alongside the new and expanded v3
contracts: 464 passed across 11 files. Its stream file had four passing assertions
but failed the CPU guard due to a heavy import inside the test; moving that
import to collection fixed it: the third run passed all 4 with the timing guard.

Combined latest results for the 384-file inventory above: **9,718 passed,
13 skipped, 6 deselected, no remaining failed file**. This is a composite of
file-isolated runs, not a single clean run of all files on the final commit.
The 80 v3-specific tests include transaction leases, concurrent reconcile,
source revisions, ownership/claims, overlap-preserving deletion, merge retries,
placement/dedup/cuts/resume/cap, switch behavior, reader guards, short paths,
summary streaming and title stability. Two completed-recording finalizer replay
regressions also pass in the 222-test finalization file.

Logs are in the user-requested brief directory under TEST-FINAL-V3.log,
TEST-FINAL-RETRY-V3.log and TEST-STREAM-FINAL2-V3.log. A final 59-test run of the contract/stream/transaction files also passes,
including three released-capture poll binding tests and three cursor-refill
visibility contracts (TEST-LAST2-V3.log).
The inventory is copied
here so the file selection remains reviewable after scratch cleanup.

## Contracts and readers

```sh
backend/scripts/openapi_runner.sh scripts/export_openapi.py --surface public --check
backend/scripts/openapi_runner.sh scripts/export_openapi.py --surface app-client --check
backend/scripts/openapi_runner.sh scripts/export_openapi.py --surface integration-public --check
backend/.venv/bin/python backend/scripts/generate_dart_models.py --all --check
backend/.venv/bin/python backend/scripts/generate_ts_openapi_types.py --check
backend/.venv/bin/python backend/scripts/generate_swift_openapi_types.py --check
backend/.venv/bin/python backend/scripts/check_app_client_openapi_compatibility.py --base-ref origin/main
backend/.venv/bin/python backend/scripts/check_conversation_readers.py --inventory
python3 scripts/check_client_compat.py --base origin/main
cd app && /Users/dazheng/workspace/omi/bin/omi-heavy run -- flutter test test/backend/conversations_v3_decoder_test.dart
```

All three OpenAPI surfaces and generated clients are current; additive gate PASS
against merge-base 92b697098eb6. Reader audit PASS: 479 classified references.
Current-source Dart fallback decoder tests: 3 passed. Released catalog: 0 captured,
0 supported; C10 capture/replay PENDING. This is no proof of released-device
WAL/capture/audio behavior. Existing audio APIs resolve aliases in the backend;
actual released playback remains a lead acceptance gate.

## Preflight and limits

Final `make preflight` result is recorded in PR-BODY-V3.md. Earlier failures
identified worker-image import closure and async I/O; those were corrected.
A subsequent async finding was a conservative false positive on a database-module
exception constructor; the shared exception now lives in a pure errors module.
Third-party closure independently passed all 19 runtime images.

No Firestore emulator, live model calls, named-account dev E2E, distributed
released builds or web/desktop device acceptance was run. Backfill remains OFF
and refuses histories over 128 source documents until operator partitioning is
implemented. Newer shared origin/main commits were not rebased into this lane;
the lead must integrate Q12-AU/Q12-AV and rerun exact-head CI before rollout.

## Additional verification

The Firestore serving/index profiles, caller witnesses, field-index declarations
and outside-query contract pass **719 tests** (606 + 41 + 41 + 31; 1 deselected):

```sh
omi-heavy run -- env BACKEND_PYTEST_WORKERS=2 BACKEND_UNIT_TEST_FILE_LIST=/Volumes/Ephemeral/scratch/episode-dayparts-brief/TESTS-FIRESTORE-V3.txt bash backend/test.sh
```

The focused v3/gateway/finalization rerun passes **315 tests**; the subsequent
59-test contract/stream/transaction run adds three capture-poll assertions, all
passing. Exact final typecheck and preflight receipts are in PR-BODY-V3.md:

```sh
cd backend
omi-heavy run -- env PYRIGHT_PYTHON_FORCE_VERSION=1.1.403 .venv/bin/python -m pyright -p pyrightconfig.json --pythonpath .venv/bin/python --level error
cd ..
omi-heavy run -- env OMI_PR_BODY_FILE=/Volumes/Ephemeral/scratch/episode-dayparts-brief/PR-BODY-V3.md make preflight
```

Pinned Dart formatting was not run: the available Flutter is 3.47.9 while this
repo pins 3.44.5. The commit uses the hook's documented OMI_SKIP_DART_FORMAT=1
escape only for the new synthetic test. Generated outputs are generator-owned.

The final full guard also runs the digest-pinned slow query review test. The
reviewed cursor collector change threads three post-read visibility options;
query/cursor/limit construction is unchanged. New synthetic tests execute page
refill past recording and home-hidden documents, with and without opt-ins.
Only that helper's reviewed AST digest was refreshed.
