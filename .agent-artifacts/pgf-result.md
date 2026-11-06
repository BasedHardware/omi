# C2 implementation result — acceptance blocked

Updated: 2026-11-06T18:00:29.917916+00:00. Repository: BasedHardware/omi.
Worktree: `/Volumes/Ephemeral/scratch/worktrees/omi/omi-lane-pgf-c2-upstream-keep-clean`. Branch: `lane/pgf-c2`.
Implementation head when this receipt was written: `8d496d4813b49d1bdc4fe1a171edf2e1fad46963`. Implementation base / merge base:
`05dcd6065f9f396c5cb9f883868db72cb8bf908e`, which includes C1 #24795.
Shared `origin/main` advanced during this run; it is currently `4b1c40b5ef03242b82013a64c1dc941728715bab`.
No rebase, push, PR, merge, deployment, production-data access or flag expansion
was performed. GCP tier: **none**.

**This is not a completed C2 acceptance handoff.** The authorized implementation
is committed locally, but the brief's caller/file assumptions and one runtime
image dependency boundary block the remaining pointer-mode work. The consolidated
scope decision is [ANX ask](https://anx.scalingforever.com/o/david-zhang/w/omi/r/event:ev_b8e9305958bf7d71d1acdb0bdec6a6be).
Write admission remains default-off/0. O1 still requires C4 wipe coverage before
any production lake write admission.

## What was built

- A single pointer-or-inline transcript codec in `database/transcript_pointer.py`.
  The pointer is C1's exact dictionary inside `transcript_segments`, with the
  compressed marker true. Sibling JSON fields and the recurring-voice scrub stay inline.
- Typed fetch-failed, absent, shredded and corrupt decode outcomes; pointer
  failures never use the legacy decrypt fail-open path. Display/export/content
  gates use the brief's mappings at the common seam.
- Generic transaction-body context in `_client.py`, memo-only guarded transaction
  reads for migrated owners (the unwrapped owners below remain blockers), bounded preload/retry runners, and deferred upload followed by an
  update-time CAS. In-progress sessions are skipped by the deferred swap.
- Request/context-local plaintext memo with thread/task ownership, TTL 120 s,
  cap 32, copied segment lists, upload reuse, traceback-free cached failures, and atomic TTL-cache miss handling.
- Explicit conversation identity through write patches/callbacks, including
  callers whose payload does not include an `id` field. The internal codec
  argument does not add persisted fields.
- Consent stamping from the actual users schema: `training_data_opt_in` is a
  status/requested_at map. Approved/rejected/pending-review map to opt-in,
  opt-out/unknown; no policy version is invented.
- C1 review follow-ups: customer-plane key authority; durable content-free key
  tombstones; uncached account-deletion checks before key creation and after
  upload; cleanup of late fenced uploads; malformed key rows remain retryable;
  a transcript-specific 32 MiB plaintext/expansion limit; normal key-document
  read budgets of one per unwrap and two per put. Key-creation contention may
  additionally reread a winner. Puts also read deletion authority twice, and a
  new upload reads the consent document once.
- Pusher pins KMS/cachetools. Lock regeneration added only the KMS resolution;
  cachetools was already present transitively. The first-caller object-lake
  dead-code allowance was removed (the authorized data-file exception).
- Hermetic mechanics, reader/domain, memory and fencing tests; migrated retry
  and codec fixture seams; reviewed/re-pinned smart-merge query-body coverage.
  Extra pointer-state coverage drives processing, final-pass, smart-merge, privacy
  scrub and legacy undo transactions. No query filter, index, env binding or feature flag was added.

### Changed files

- `.github/scripts/dead_code/backend.allowlist.json`
- `backend/database/_client.py`
- `backend/database/conversation_terminal_title.py`
- `backend/database/conversations.py`
- `backend/database/episodes.py`
- `backend/database/owner_confirmation.py`
- `backend/database/recurring_voice_privacy.py`
- `backend/database/review_changes.py`
- `backend/database/review_overlay_merge.py`
- `backend/database/review_transcript_changes.py`
- `backend/database/smart_merge.py`
- `backend/database/speaker_assignment_effects.py`
- `backend/database/speaker_learning_jobs.py`
- `backend/database/speaker_resolution_updates.py`
- `backend/database/sync_assignment.py`
- `backend/database/transcript_pointer.py`
- `backend/docs/listen_pusher_pipeline/changes/2026-11-06-transcript-lake-offload.md`
- `backend/pusher/pylock.toml`
- `backend/pusher/requirements.txt`
- `backend/tests/integration/test_recurring_voice_privacy_firestore.py`
- `backend/tests/support/dream_firestore.py`
- `backend/tests/support/firestore_query_driver_registry.py`
- `backend/tests/unit/test_conversation_terminal_family.py`
- `backend/tests/unit/test_conversation_transcript_offload.py`
- `backend/tests/unit/test_live_transcript_merge.py`
- `backend/tests/unit/test_live_transcript_replay.py`
- `backend/tests/unit/test_object_lake.py`
- `backend/tests/unit/test_pusher_audio_projection.py`
- `backend/tests/unit/test_space_keys.py`
- `backend/tests/unit/test_transcript_pointer.py`
- `backend/utils/other/object_lake.py`
- `backend/utils/other/space_keys.py`
- `backend/utils/person_evidence_backfill.py`

This result file is the requested additional artifact. Unrelated pre-existing
`app/analysis_options.yaml` and `app/pubspec.lock` edits are preserved and are
not part of the commits. A temporary preflight stash was reapplied and its exact
patch hash verified; the task stash was dropped after successful restoration.

## Deviations from the original brief

- The task's explicit C1 review ownership supersedes the brief's C1-file freeze.
  The key destruction contract now retains a tombstone rather than deleting
  the authority row; the two old assertions and lake client fixture were migrated.
- The strict inline decoder and its error type were moved into the new module
  and imported at the existing conversation seam. There is one implementation,
  with no compatibility wrapper.
- Memo entries validate the full owner/reference (bucket, path, digest, byte
  count and key version), rather than digest alone. Upload reuse also includes
  entity identity, so equal content cannot silently mask an absent different
  blob or reuse another conversation's object path.
- Ledger-owned transactions use `run_preloaded_operation` around their actual
  owner operation; their runners are not the direct invocations assumed by the
  old line references. Ledger and queue state were not changed.
- Existing live retry mocks, the pusher codec mock, and the integration privacy
  fixture were migrated to the new seam. Their behavioral assertions remain.
  The smart-merge body digest was re-reviewed and re-pinned with unchanged
  serving query shapes, as required by the Firestore checklist.
- Current `run-unit-ci.sh` requires an explicit mode, so the command uses
  `--changed-files`. The selector requires the full backend suite for these
  database edits. A separate codec caller slice and Firestore guard selection
  run through the same `test.sh` executor.
- Initial static deadlines were too short for this shared host. Longer bounded
  reruns passed async/source closure; the old source-check child was stopped by
  its recorded PID. The initial preflight overlapped later authorized edits,
  so its tracked-file mutation diagnostic is not attributed to a check. A
  stable-source rerun is still required after the scope blocker is resolved.

## Verification

Every test payload is launched through `.agent-artifacts/pgf-c2-test-env.py`,
which unsets `GOOGLE_APPLICATION_CREDENTIALS`, all `CLOUDSDK_*`, service-account
and Firebase credential paths, and inherited project bindings, then supplies
only demo project hints and a closed loopback metadata endpoint. Heavy work
uses `/Users/dazheng/workspace/omi/bin/omi-heavy run --wait 3600 -- ...`.
Python is this worktree's `backend/.venv` (3.11.15).
`BACKEND_UNIT_FILE_BUDGET_SECONDS=900` and four file workers are used.
The full wrapper is:

```sh
python3 .agent-artifacts/pgf-c2-test-env.py \
  /Users/dazheng/workspace/omi/bin/omi-heavy run --wait 3600 -- <payload>
```

| Exact payload / command | State and counts |
| --- | --- |
| `backend/.venv/bin/python -m pytest backend/tests/unit/test_transcript_pointer.py backend/tests/unit/test_conversation_transcript_offload.py -q` | Latest two-file regression run: 112 passed; final expanded four-file run below supersedes this receipt. |
| Same two files plus `backend/tests/unit/test_object_lake.py backend/tests/unit/test_space_keys.py -q` | 147 passed before the last consent/identity/memo additions. |
| `bash backend/scripts/run-unit-ci.sh --changed-files "$PWD/.agent-artifacts/pgf-c2-changed-files.txt"` | First attempt: 7 new type errors; corrected. Second attempt: **0 type errors**, full 2674-file unit selection still in flight at this checkpoint. Three old-runner fixture failures found and corrected; affected-file rerun is green below. Seven native-audio failures also occurred because this process cannot locate the installed libopus; process-local library-path rerun is recorded below. This original run will remain nonzero even after the correction. |
| `BACKEND_UNIT_TEST_FILE_LIST="$PWD/.agent-artifacts/pgf-c2-legacy-codec-tests.txt" bash backend/test.sh` | 73 caller test files; 2870 passed, 2 failed. Only the pusher fixture file failed, due to the newly explicit codec keyword; fixture corrected, budgeted rerun below. |
| `BACKEND_UNIT_TEST_FILE_LIST="$PWD/.agent-artifacts/pgf-c2-firestore-guard-tests.txt" bash backend/test.sh` | Seven guard files: 840 passed, 1 deselected; no failures. |
| `BACKEND_UNIT_TEST_FILE_LIST="$PWD/.agent-artifacts/pgf-c2-single-test-list.txt" bash backend/test.sh` | Five focused/fixture files: 266 passed, exit 0. Final narrow reference/create regressions have an additional current-source run. |
| `python -m pytest tests/unit/test_transcript_pointer.py tests/unit/test_object_lake.py tests/unit/test_space_keys.py -q` (backend/) | 78 passed; current-source run. |
| `python -m pyright --pythonpath .venv/bin/python database/conversations.py database/transcript_pointer.py utils/other/object_lake.py utils/other/space_keys.py` (backend/) | **0 errors, 329 warnings** on the four codec/lake modules before the final identity/TTL changes; full-contract type check also passed before those narrow changes. |
| `backend/.venv/bin/python -m pytest backend/tests/unit/test_transcript_pointer.py backend/tests/unit/test_conversation_transcript_offload.py backend/tests/unit/test_object_lake.py backend/tests/unit/test_space_keys.py -q` | Final expanded codec/lake run: 184 passed. Previous expanded run: 183 passed. |
| `backend/.venv/bin/python -m pytest backend/tests/unit/test_conversation_terminal_family.py -q` | 81 passed, exit 0 after migrating the injected failed-commit/retry seam. |
| `backend/.venv/bin/python -m pytest backend/tests/unit/test_conversation_transcript_offload.py -q -k 'processing_owners or migration_keeps or final_pass_transaction or smart_merge_transaction or privacy_scrub_transaction or legacy_review_undo'` | First run: 14 failed, 11 passed, 79 deselected, caused by incomplete test-fake support / synthetic rows. Corrected matrix: 25 passed, 79 deselected, exit 0. |
| `backend/.venv/bin/python -m pytest backend/tests/unit/test_conversation_transcript_offload.py::test_explicit_document_identity_wins_over_payload_identity -q` | 1 passed, exit 0; single lightweight regression, outside the heavy gate. |
| `env DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib backend/.venv/bin/python -m pytest backend/tests/unit/test_empty_capture_recovery.py -q` | see log; no pytest summary; uses the heavy gate and installed native libopus, no host changes. Initial full-suite file: 61 passed, 7 failed (library not found). |
| `bash test-preflight.sh` (backend/) | Exit 0: 18 checks passed, 8 optional warnings, 0 failed. |
| `python scripts/scan_import_time_side_effects.py` (backend/) | Exit 0. |
| `python scripts/check_module_stub_pollution.py` (backend/) | Exit 0. |
| `python scripts/scan_async_blockers.py --dirs routers utils` (backend/) | First 180 s bound expired; bounded rerun exit 0, no selected blocking findings. |
| `make runtime-image-source-closure` | First bound expired; longer rerun exit 0 for all 19 registered images. |
| `make runtime-image-smoke SERVICE=pusher` | Blocked: Docker daemon/socket unavailable. Repeat used isolated empty Docker auth config. |
| `bash backend/scripts/update-python-lock.sh` | Exit 0; pusher lock-only KMS addition; other backend locks unchanged. |
| `OMI_PR_BODY_FILE="$PWD/.agent-artifacts/pgf-c2-pr-body.md" BACKEND_UNIT_FILE_BUDGET_SECONDS=900 make preflight` | Exit 2: third-party closure rejects batch-pipeline-worker's missing KMS dependency. Initial run also observed concurrent edits; not a green final-source receipt. |
| `scripts/pr-preflight --suggest` and `scripts/pr-preflight --lane local --suggest` | Executed; required invariant citation: none. |
| `scripts/pr-preflight --lane local --pr-body-file .agent-artifacts/pgf-c2-pr-body.md --metadata-only` | Final metadata-only selection passed again: four checks in 19.79 s, including the reviewed line-count exception. |
| `npm run test:listen-lifecycle:emulator -- --config .agent-artifacts/pgf-c2-firebase.json` | Firestore loopback assertion suite passed; no pytest count exposed. Emulator stopped. |
| `python -m pytest tests/integration/test_recurring_voice_privacy_firestore.py -q` (backend/) | Without emulator: 14 skipped. Isolated emulator rerun: 14 passed (see terminal receipt). |

Emulator commands use an empty task-specific `XDG_CONFIG_HOME`, usage telemetry
off, demo-only projects, isolated loopback ports, and absolute rules/index paths.
They run through `firebase emulators:exec`, which shuts down the owned processes.
The integration rerun's exact outer command is recorded in
`.agent-artifacts/pgf-c2-verification.jsonl`.

Formatting is the repository's pinned Black 26.5.1 pre-commit hook with
`--line-length 120 --skip-string-normalization`; a manual 27-file Black check passed. Subsequent changed Python files were checked by the pinned commit hook. `git diff --check` has passed.

The first Docker smoke attempted the host-configured registry credential helper
and failed to refresh its token before building. No cloud service read/write
was performed. Subsequent Docker commands use an empty task-only auth config;
no login, host-service installation/start, bucket/KMS provisioning or deployment
was attempted. Real image import acceptance and the HTTP offline harness remain
unverified because Docker is unavailable. The hermetic list/detail/MCP/export/
search/notification-path tests are local product-code tests, not deployed proof.

## Remaining scope and acceptance blockers

# C2 scope corrections needed for full acceptance

These changes are proposed, not applied. They are outside the brief's explicit
file/dependency boundaries. The implementation has kept writing default-off/0.

| Boundary | Current-code evidence | Proposed correction |
| --- | --- | --- |
| `backend/database/helpers.py` | `prepare_for_read` retains each `_process(item)` result in collections, including `None` returned for an absent transcript blob. List/MCP readers can therefore return `[None]`. | Filter deleted (`None`) decoder results from collection returns, preserving the scalar not-found result. Add pointer-absent list/MCP tests. |
| `backend/database/conversation_finalization_jobs.py` | Admission uses `run_with_transaction_contention_retry` around a direct SDK transaction. It does not pass through `_client.run_transactional`, contrary to brief §6a row 20. Admission calls `raw_conversation_has_content`. | Wrap the admission runner in `transcript_pointer.run_preloaded_operation`, keeping queue state unchanged. Audit all admission calls to the two raw-content predicates and add cold-pointer tests. |
| `backend/database/recording_sessions.py` | `tombstone_and_delete_empty_conversation._delete_empty` calls `raw_conversation_has_content` inside a direct SDK transaction. Brief §6b incorrectly classifies this reader as non-transactional. | Use the preload runner for `_delete_empty`; refuse deletion when pointer fetch fails and retain the existing absent/shredded empty-content policy. |
| `backend/utils/sync/assignment.py` | Candidate admission and canonical selection occur before the injected decode closure is called. Catching absent/shredded in the conversations decoder cannot safely skip a candidate at that late point. | At the transaction's `load(cid)` boundary, validate pointer availability through the injected decoder. Treat absent/shredded candidates like existing deleted candidates; let transport failures abort. Add canonical and candidate tests. |
| Retry policy in `backend/database/transcript_pointer.py` | The prescribed three total attempts can preload at most two cold references. A two-source review merge may read target plus two distinct sources; episode operations may read more. | Permit at most 32 distinct document preloads (the memo cap) plus three content-change retries, with a hard total bound and eviction of superseded versions. Preserve no-IO transaction bodies. This amends the brief rather than a file boundary. |
| `backend/diarizer/requirements-batch-pipeline.txt` and `backend/diarizer/pylock.batch-pipeline.toml` | The real third-party image closure guard fails: `batch-pipeline-worker` reaches `google.cloud.kms_v1` through the newly connected conversation codec, but its closed lock lacks KMS. | Pin `google-cloud-kms==3.6.0` in the worker input and regenerate its lock without upgrades. Check whether its existing cachetools resolution already satisfies the codec, then rerun image closure. No workflow changes. |
| `backend/database/speaker_profile_authority.py`, `speaker_auto_enroll.py`, and `users.py` | `current_source(transaction, ...)` decodes inside publication transactions and catches `Exception`. It is called by allowed learning jobs, auto-enrollment commit bodies, and the direct SDK `_replace_speech_profile_transaction` in users. Brief §6b incorrectly calls this non-transactional; pitfall 1 correctly says to narrow the catch. | Catch only corrupt/absent/shredded states, propagate preload misses and fetch failures, and switch only the actual publication runners to the preload boundary. Preserve all authorization and cleanup policy; add cold-pointer and refusal tests. |
| `backend/database/episode_attach_memo.py` and `episode_timeline.py` | `current_key` catches `Exception` and is called inside memo `check`/`finish` transactions and timeline `attach_recorded.attach`. The outer memo handlers also catch every exception. Brief §6b incorrectly calls this non-transactional; pitfall 1 requires narrowing. | Narrow the inner decode and outer operational handlers so pointer misses/fetch failures reach the preload owner, switch only the three affected runners, and add cold-pointer tests. Preserve memo eligibility and episode policy. |

The runtime-image smoke command also needs a working local Docker daemon. None
was started or installed. A repeat with an empty Docker auth configuration fails
on the missing `/var/run/docker.sock`, without invoking the host's GCP helper.

The scope above is necessary for R14/§12 acceptance; current default-off unit
results do not prove those pointer-mode paths. The result report will keep these
items explicit until approved, implemented and verified.


Additional original non-goals remain C3 backfill/janitor/registry and C4 account
wipe integration / quiescence / keys-last qualification. Deterministic unit race
hooks are not Firestore emulator contention proof for C4.

## Outcome record and in-flight work

[ANX C2 card](https://anx.scalingforever.com/o/david-zhang/w/omi/r/card:pg-foundation-c2-transcript-lake-codec),
using the authorized [anx-participant skill](/Users/dazheng/.agents/skills/anx-participant/SKILL.md).
The scope ask has a bounded ANX await subscription. The card is blocked on the scope decision. Local full CI remains in flight
at this checkpoint (PID/PGID 45361, command session 17604); its command session is watched and the 50-minute heartbeat is
armed and touched on wakes. Focused codec/transaction reruns are complete (see receipts above). The native-audio rerun is separately tracked in command session 94087 until terminal. The superseded scope waiter was stopped by its owned PID; the current eight-area scope ask is watched in session 38393 with a four-hour timeout. Heartbeat session 34503 wakes this thread after 50 minutes idle. No native/delegated agents were launched.

## Draft PR body (not submitted)

## What changed and why

Oversized transcript_segments can be stored as an encrypted object-lake pointer inside the existing field. The shared codec resolves pointers for backend, listen, pusher, MCP, export and search; migrated transaction owners use a content-addressed preload/retry boundary and revision-checked post-commit swaps. Deleted-owner key tombstones prevent rekeying, malformed key rows remain retryable, transcript decompression is bounded to 32 MiB, and key-document authority reads are budgeted (one per unwrap, two per put).

Writes remain default-off/0 admission. O1: OBJECT_LAKE_WRITE_ENABLED stays off in prod until C4's wipe-coverage test is green. Ramp is dev-first via OBJECT_LAKE_WRITE_PERCENT; C1's registry retains ramp metadata and ownership. No new env binding, dependency upgrade, schema migration or index is introduced; space_keys already exists and retains content-free destruction tombstones.

C3 reuses offload_inline_transcript for backfill and owns legacy re-encryption, orphan janitor and registry/receipt. C4 owns account-wipe integration, quiescing in-flight puts, prefix purge and key destruction last (preserving tombstones). B/W2 syncs pointer field changes as content-free doc changes. A6 ports the seam unchanged. Public-chat's bounded decoder excludes pointer docs; existing long shared conversations need a later product decision before backfill.

Acceptance remains incomplete: the caller-boundary corrections and worker dependency correction in the C2 result report still need authorization and implementation. This draft is not a ready-to-submit PR.

## Product invariants affected

none

## How it was verified

Hermetic local tests only. GCP tier: none. Credential scrubber removes GOOGLE_APPLICATION_CREDENTIALS and CLOUDSDK_* before each command. No production access, API calls or customer data. Focused codec and transaction-family verification is recorded with exact commands and counts in .agent-artifacts/pgf-result.md. Runtime source closure passed for 19 registered images; async blocker, import-purity and module-isolation scans passed. The Docker daemon is unavailable, so image smoke is blocked. The full unit contract is running; preflight failed the worker KMS dependency closure; final receipts will be in .agent-artifacts/pgf-result.md.

## Tests

backend/tests/unit/test_transcript_pointer.py: codec round trips, flag-off golden encodings, compressed-byte threshold, no-IO transaction guard, preload retries, decode taxonomy, memo hygiene, consent and deferred CAS.
backend/tests/unit/test_conversation_transcript_offload.py: pointer reader surfaces, domain refusals, oversized transcripts, tombstone races, malformed keys and authority read budgets.

## UI evidence

UI-Evidence: none -- backend only

## Failure class (fixes)

Failure-Class: none

## Scoped cleanups

Line-Count-Exception: backend/database/conversations.py | 4855 -> 4892 | Preserve domain transaction structure while adding pointer decoding and narrow unavailable-content refusals; codec mechanics live in transcript_pointer.py.
