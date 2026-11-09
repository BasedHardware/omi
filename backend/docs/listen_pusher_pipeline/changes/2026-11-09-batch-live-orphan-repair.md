# Dark bounded orphan repair

P0 freeze exemption: lead2 bus 8c0822. `BATCH_LIVE_ORPHAN_REPAIR_ENABLED`
defaults **off**, overriding the design's default-on proposal. The new
[operator runbook](../../../deploy/record-orphan-repair/README.md) describes
128-row plan/digest approval, private cursors, counts-only dry-run and retained
span audio seconds for STT sizing. No runtime config is activated.

The sealed+received path proves immutable retained audio, then one fenced
transaction stamps the missing window/content, completes the capture barrier and
creates the canonical batch job. The status transition is necessary: merely
registering an in-progress row fails the real `require_record_audio_barrier`.
The lifecycle owner supplies the normal relevance and Home-pending metadata;
the test exercises the real record barrier after registration. The normal batch pipeline
owns the remaining exit, retaining compute/funding/STT guards.

Delete-empty requires the closed-archive proven-empty shape, explicit received=false, empty
storage proof, no content/audio metadata or producer tokens/failure, and the
existing expired-lease quiet/identity fence. A narrow transaction guard joins
fresh owner consent, canonical privacy generation, row approval and job absence
to the existing lifecycle delete. Retained raw audio and GCS objects are never
removed. Received=true with no objects, unsealed captures and unknown leases are
parked, rather than weakening the proven-empty predicate. Every disposition
names its exit and refused private entries carry a closed last_failure_code;
privacy-skipped rows get no new persisted marker.

A lane-owned row with a missing server-only marker follows base quiet admission.
If that admission has no bounded exit, its quiet obligation is retired; repair
counts `barrier_mismatch` and `lease_unknown` as parked for **operator review**.

No live.py changes; no due, timer or dispatch changes (#24866). Pending-job drain
#24953 is disjoint by transactional job absence. #24893 should absorb the
quiet-check's interim deferred-to-repair obligation into its standing state
machine. Rollback: set the repair switch false; committed jobs drain normally.

Synthetic strict-transaction tests and `orphan_sealed_registered.json` cover the
local contract. No cloud access, staging apply, production dry-run, recovered
transcript or Home acceptance is claimed by this implementation lane.

## Initial verification before review — 2026-11-09 06:46 UTC

All test and preflight commands ran through the workspace `bin/omi-heavy`, with
`BACKEND_PYTEST_WORKERS=4`. `GOOGLE_APPLICATION_CREDENTIALS`, `CLOUDSDK_*` and
other credential-file overrides were removed before verification. No GCP tier,
production reads, cloud writes, push or PR was used.

- The 23-file targeted selection passed, including seal/nojob, backlog, recording
  sessions and the trace corpus. Three emulator integration cases were skipped.
- Final focused runs: quiet finalization **111 passed**, recording sessions
  **37 passed**, orphan repair **45 passed**. They use `backend/test.sh` with
  backend-relative file lists and the normal CPU guards.
- `make backend-ratchet-preflight`: **7 files passed**.
- `backend/test-preflight.sh`: **17 passed, 9 optional warnings, 0 failed**.
- Full-tree `backend/scripts/typecheck.sh`: **0 errors**; configured warnings remain.
- `make preflight`: **44 checks passed** with `OMI_CHECKS_JOBS=1` and
  `BACKEND_UNIT_FILE_BUDGET_SECONDS=900`. Assertions and CPU guards were unchanged.
  The standard parallel run hit an OpenAPI scratch-directory removal/scanner
  race; the documented serial mode avoids that shared-tree race. The default
  300-second file budget also exhausted under host load before the Firestore
  shape suite finished; the longer wall budget completed the real guard.

For repository preflight, `OMI_ENV_STAGE` was unset: offline mode enables four
harness-only routes outside the normal route-policy catalog. The OpenAPI
inventory still used its hermetic fake-service bootstrap and blocked network.
This verification is local code/transaction evidence, not staging recovery,
production execution, recovered transcripts or Home acceptance.

## FIX-FIRST amendment

Both repair findings were verified against `5f0405b6b24d`: the CLI unconditionally
wrote its required cursor (`scripts/repair_record_orphans.py:43`), and
`read_candidate` read row/job before authority (`record_orphan_repair.py:125-135`).
`--next-file` is now optional and is the only opt-in filesystem write. Owner-only
consent/deletion/protection authority precedes every row/job read, including
registration planning, storage reauthorization and final delete guard. No
canonical privacy gate was removed; the missing-preference enabled default stays.

The fresh upstream flag policy classifies the per-invocation repair apply gate
as `config_switch`: it is an explicit operator opt-in with digest approval, not
a default-on fleet kill switch. Both source defaults remain OFF. Validation is
pinned to the rebased upstream SHA so a shared `origin/main` fetch cannot change
the synthetic merge target midway through preflight.

The registry's owning-area label is `batch-pipeline (dazheng)` for both keys.
Dazheng remains the responsible maintainer; the parenthetical annotation satisfies
the upstream rule that groups flag debt by owning area instead of account name.

## Verification after FIX-FIRST — 2026-11-09 12:49 UTC

Both Luna reviews were checked against the original code; all four findings were
confirmed and fixed. The final serial run used the workspace `bin/omi-heavy`
with credentials removed, metadata disabled and dotenv loading disabled:

- Quiet-check suite: **119 passed**.
- Orphan-repair suite: **66 passed**, including owner-refusal read poisons,
  final-delete consent races, optional cursor IO, approval/idempotency and trace.
- Recording-session suite: **37 passed**.
- Backend environment preflight: **17 passed, 9 optional warnings, 0 failed**.
- Pinned full-tree Pyright: **0 errors** (77,842 warnings).
- Repository preflight: **44 checks passed**, serial `OMI_CHECKS_JOBS=1`,
  `BACKEND_UNIT_FILE_BUDGET_SECONDS=900`; no assertions or CPU guards relaxed.

The repository preflight used the exact `make preflight` runner with immutable
`--base 634484b20ec642c08f09d93bad1f0a26c9c2f620` after rebasing onto that
upstream SHA. This avoids a shared-ref fetch changing its synthetic merge target.
The earlier run stopped on generated-registry merge conflicts after upstream
advanced; the final pinned run passed the real line-count and registry guards.
`OMI_ENV_STAGE` was unset only for the hermetic repository preflight.

Both switches remain default OFF. No GCP identity was loaded or used, no
production data was read, and no push, PR, deployment or operator apply ran.
No `live.py`, timer, due-time or dispatch change is included. This final
documentation amendment records results; the validated application code is
unchanged. Staging recovery, transcript/Home acceptance and activation remain
lead-owned; there are no open implementation questions.

## Round-2 custody amendment

The remaining P1 was confirmed against `60578cf2ecdc`: `read_candidate` loaded
the full capture and canonical job before `candidate_refusal` checked capture
privacy. Owner-level authority was already checked first. The lead narrowed the
read boundary to permit only a privacy-field projection after owner authorization.

Repair now reads only `uses_custom_stt`, `private_cloud_sync_enabled` and
`data_protection_level` through a Firestore field mask before any full capture or
job read. Refused captures return `privacy_skipped` without reading content, jobs
or storage. The same gate protects storage reauthorization and canonical
registration reads, including apply transactions. Canonical privacy-generation,
deletion and protection checks remain intact; dry-run still mints no cache token.
A missing capture remains an idempotent `not_candidate`.

Discovery already used `.select(())`; no query change was needed. Its path-only
projection is now documented in the runbook and asserted by a synthetic test.
New read-recording tests cover capture refusals during plan, registration apply
and empty-delete apply, plus later proof and registration authorization. The
owner-level poison-read tests remain intact. Only the second commit is amended;
the quiet-check implementation and both default-OFF switches are unchanged.

Round-2 local verification completed at 2026-11-09 13:56 UTC through `omi-heavy`,
serially with a 900-second per-file budget and cloud credentials removed:

- Quiet checks: **119 passed**; orphan repair: **87 passed**; recording sessions:
  **37 passed** (243 total). After replacing Mock attribute access in the new
  tests with typed local references, the repair suite again passed all 87 tests.
- Pinned Pyright 1.1.403 on the changed runtime module: **0 errors**, 376 warnings.
- Explicit Pyright on all three changed Python files also checks test files not
  included in the normal backend type-check scope. It reports **17 errors** and
  945 warnings. Checking the corresponding files from `60578cf2ecdc` reports the
  identical 17 test-only errors (private helper usage, existing Mock attribute
  access and optional import-loader typing), with 840 warnings. Diagnostic
  messages/rules/file names match exactly; **no error is introduced**. No checker
  setting or gate was relaxed. The four initial errors in the newly added tests
  were fixed before the final comparison.
- Formatting and `git diff --check` passed. The earlier full preflight results
  above predate this field-mask amendment; this round reran the requested suites
  and changed-file type checks.

No GCP tier was loaded, production data read, or push/PR/operator apply performed.
