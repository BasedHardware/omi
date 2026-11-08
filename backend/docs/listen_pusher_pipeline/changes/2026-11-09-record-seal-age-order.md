# Oldest-first record-pending repair discovery

`discover_jobs` previously visited `record_pending` jobs in document-name (hash)
order. It now visits `enqueued_at ASC, __name__ ASC`, with a frozen enqueue-time
horizon for each pass and a wrap back to the oldest row after exhaustion. This
prioritizes older retained recordings without changing seal proof, producer
liveness, custody, privacy, `JOBS_MIN_AGE_SECONDS`, or the 128-row page and
`MAX_SCAN` bounds. The query and projection still read only job metadata.

Before this change, missing, nonnumeric, boolean, NaN, and infinite `enqueued_at`
values were scanned by name and skipped by the local numeric-age filter. After
this change those jobs remain ineligible: the numeric range query excludes
missing/nonnumeric values, and the unchanged local filter still skips any
boolean/nonfinite clocks returned by Firestore. No previously eligible job
silently disappears. A missing or malformed clock is not interpreted as age zero
and no stored jobs are rewritten or deleted. Young finite jobs remain subject to
the same local minimum-age check; a job newer than the frozen horizon becomes
visible in a later pass.

`RECORD_SEAL_REPAIR_AGE_ORDER` is a default-on ops kill switch through
`config/refactor_modes.py`. Setting it to `off` restores the original hash query,
age filtering, and legacy cursor format. Switching orders restarts at that
order's head, preserving coverage. The encrypted frontier carries the exact
numeric enqueue value and frozen horizon; it retains the legacy timestamp
envelope so older binaries can still decode it on a code rollback.

Missing/building-index errors fall back to the original hash query within the
same bounded discovery call. The shared fallback helper and the coordinator's
explicit aggregate diagnostic report that transition once per process, without
including the SDK error text. Later fallback calls resume the saved hash cursor
rather than repeatedly revisiting its first page. Other read failures still
propagate.

Both `(state ASC, enqueued_at ASC, __name__ ASC)` index definitions already existed
in `sync_pipeline_indexes.py` as `batch_pipeline_{prod,dev}_result_ready`, contrary
to the brief's inventory. They move to `batch_pipeline_indexes.py` under the same
registry IDs and identical definitions; the generated manifest is reordered,
with no added or removed index signatures. The existing registry deployment and
readiness gates remain authoritative. No index provisioning or rollout is part
of this local implementation.

Part A token leases and #24893-owned files are untouched. Extra scope beyond the
brief's short file list is limited to the encrypted cursor codec, registry
relocation/source and generated artifacts, query-driver coverage, and preserving
the original hash-mode regression suite.

Failure-Class: none

Validation and the local commit are reported in the implementation handoff. This
note can be used as the lead's draft PR body; no PR is opened by this lane.

## Local validation

Repository: `BasedHardware/omi`, branch `lane/sealorder`, base
`c2c07908de2ebfa52cb12cd074771d4833bc0559`. These commands ran in this worktree;
no GCP agent tier or cloud credentials were used. The wrapper removes
`GOOGLE_APPLICATION_CREDENTIALS` and every `CLOUDSDK_*` variable before tests:

```bash
env -u GOOGLE_APPLICATION_CREDENTIALS /Users/dazheng/workspace/omi/bin/omi-heavy run -- bash -c '
for key in ${!CLOUDSDK_@}; do unset "$key"; done
cd backend && .venv/bin/python -m pytest -q \
  tests/unit/test_record_seal_cluster_repair.py \
  tests/unit/test_record_pending_repair.py \
  tests/unit/test_refactor_modes.py'
```

Result: **198 passed, 1 warning in 133.57s** (the existing Python `audioop`
deprecation warning).

```bash
env -u GOOGLE_APPLICATION_CREDENTIALS /Users/dazheng/workspace/omi/bin/omi-heavy run -- bash -c '
for key in ${!CLOUDSDK_@}; do unset "$key"; done
firebase emulators:exec --only firestore --project demo-seal-age-order \
  "cd backend && .venv/bin/python -m pytest -q tests/unit/test_record_seal_nojob_emulator.py"'
```

Result: **3 passed, 1 warning in 15.87s**; emulator shutdown completed normally.
The emulator validates query and cursor semantics, not production index readiness.

`scripts/pr-preflight --lane local --suggest` identified no required invariant
citations. `scripts/pr-preflight --lane local --pr-body-file
backend/docs/listen_pusher_pipeline/changes/2026-11-09-record-seal-age-order.md
--metadata-only` passed **4 checks in 17.66s**.

```bash
env -u GOOGLE_APPLICATION_CREDENTIALS /Users/dazheng/workspace/omi/bin/omi-heavy run -- bash -c '
for key in ${!CLOUDSDK_@}; do unset "$key"; done
cd backend && .venv/bin/python -m pytest -q \
  tests/unit/test_firestore_query_shapes.py \
  tests/unit/test_firestore_outside_query_contract.py \
  tests/unit/test_firestore_caller_witnesses.py \
  tests/unit/test_firestore_runtime_witnesses.py \
  tests/unit/test_firestore_index_rules.py \
  tests/unit/test_firestore_query_contract.py \
  tests/unit/test_firestore_field_indexes.py'
```

Result: **842 passed, 10 warnings in 787.11s**; exit code 0. Warnings are existing
Python/Pydantic/FastAPI deprecations. Both age-order and hash-order query-driver
profiles are exercised against the generated manifest.

Full preflight command:

```bash
env -u GOOGLE_APPLICATION_CREDENTIALS /Users/dazheng/workspace/omi/bin/omi-heavy run --wait 3600 -- bash -c '
for key in ${!CLOUDSDK_@}; do unset "$key"; done
BACKEND_UNIT_FILE_BUDGET_SECONDS=900 make preflight \
  OMI_PR_BODY_FILE=backend/docs/listen_pusher_pipeline/changes/2026-11-09-record-seal-age-order.md'
```

The first attempt used the default 300-second per-file budget and exited 2:
`test_firestore_query_shapes.py` timed out (status 124), while the other six
isolated guard files passed. It also detected that the implementer had appended
validation results to this note during the run. The rerun freezes all inputs and
uses the existing 900-second budget override; it skips no checks. Terminal
preflight results are in the final implementation handoff.

## Terminal preflight result

The 900-second-budget rerun on implementation commit
`ca484a9540f2bacfef446346ddd47a0f6ba2ecd7` exited **2 after 849.27s**. The
canonical Firestore index guard passed all **7 isolated files** (729.17s including
setup). The async-blocking, runtime image third-party closure, dead-code,
batch-policy, notification-dispatch, and speaker-label checks also passed.

The sole reported failure was `feature-flag-registry`:
`review overdue beyond the 7-day grace: ACTION_ITEM_REFRESH_PRESERVE_ENABLED
(review_by 2026-11-01)`. Its complete registry row is unchanged between the
starting base `c2c07908de2ebfa52cb12cd074771d4833bc0559` and the implementation
commit; only the new `RECORD_SEAL_REPAIR_AGE_ORDER` row was added. No error was
reported for the new flag. Other repository checks were cancelled after this
failure, so this is **not a fully green preflight**. The unrelated review date
and ruling were left untouched to preserve Part B scope.

The implementation remains locally committed only; no push, PR, index apply,
cloud read, deploy, or token-lease change was performed. A subsequent local
commit records only this terminal validation result; production code and tests
are unchanged from the tested implementation commit.
