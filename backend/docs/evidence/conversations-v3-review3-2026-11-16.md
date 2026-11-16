# Conversations v3 final review round — 2026-11-16

Baseline: 05dd8844950, branch lane/conversations-v3. Local source, synthetic
fixtures and current-source decoder evidence only. No production/private-data
access, GCP credential tier, push/PR/merge/rebase/deploy or external runtime
configuration changes. No app UI, Q12 notes prompt or sync merge changes.

## Item decisions and discriminatory tests

All items are addressed locally; none is deferred in this round.

| Item | Final behavior and regression |
| --- | --- |
| R3-1 | /live always emits finished_at, nullable. LiveConversation requires the key. test_live_response_is_compact_and_never_a_recording compares against exported Conversation required keys; Dart compact-row decoder fixture passes. |
| R3-2 | Pending /urls returns alias entries with pending status, duration and no URL, plus polling delay. test_v3_urls_only_serves_conversation_artifact and actual Dart playbackReady/hasPending assertions keep play/export polling; no covering-file cache branch. |
| R3-3 | Matching permanent unavailable fingerprints suppress enqueue and produce unavailable aliases. test_v3_permanent_unavailable_stops_poll_enqueues_and_piece_change_heals proves repeated polls stop and changed pieces restart work. Existing merge_failed recovery remains bounded by its marker generation/backoff. |
| R3-4 | Shared pure playback_origin prefers normalized playback_start, retaining raw chunk keys for downloads. test_piece_trim_uses_playback_clock_for_171_second_capture_skew plus test_v3_artifact_wall_clock_uses_normalized_playback_start cover trim and wall spans. Manifest deletion subtraction uses the same clock. |
| R3-5 | Missing source metadata/chunks or truncated PCM fails before export; it never publishes a partial artifact. Temporary work uses bounded task retries and the existing default-on failed-merge recovery. Artifact format v2 invalidates old partial caches. test_v3_temporarily_missing_piece_never_exports_partial_artifact covers three readiness paths and eventual full assembly. Fully deleted intervals require no download; permanently absent pieces still skip as before. |
| R3-6 | Plugin backup preserves pending alias placeholders, so the existing worker reports not-ready/retry rather than no saved audio. test_backup_manifest_uses_exact_artifact_or_pending; cached backup still receives exactly one dense artifact. |
| R3-7 | Remove the fixed 20-minute anchor filter. test_hour_long_continuous_talk_crosses_anchor_and_pending_page covers 20 and 40 recordings spaced three minutes apart; one stable conversation survives the page. The existing 129-recording backlog regression remains. |
| R3-8 | Mark the time-latest kept recording from the next pending capture by started_at, not pending_since. Look ahead at most 33 rows and skip kept IDs, including equal-time captures. test_page_continuation_uses_capture_chronology_not_pending_order covers late earlier audio and equal timestamps. |
| R3-9 | Processing and purge sweeps cursor-page by document name. Purge errors retain pending, attempts and retry_after, and do not abort later rows. test_processing_and_purge_sweeps_cursor_past_errors_and_1000_rows exercises 1,001 of each obligation and an initial storage failure. Existing capture sweep age/cursor test stays green. |
| R3-10 | A permanently unreadable recording is marked as unreadable input and its obligation settles without creating a window. Missing documents are absent, not fabricated inputs. Transient pointer-fetch/infrastructure errors still retry. test_missing_transcript_blob_is_unreadable_and_settles_without_a_window uses the real missing-blob exception. |
| R3-11 | All reconcile exceptions fall through to the owner-checked stored detail and log only exception class. test_on_open_reconcile_errors_stream_stored_row covers source_changed, lease_lost and generic failure reasons. |
| R3-12 | The request waits eight seconds on a shielded tracked reconcile. Paid work and its renewal task remain owned until the worker exits, including direct cancellation. test_on_open_reconcile_timeout_streams_stored_row verifies the timeout does not cancel the holder; test_cancelled_builder_keeps_lease_until_paid_outline_exits blocks a real synthetic worker thread and verifies custody. |
| R3-13 | Renewal retries transient errors up to three times, refuses lost-token conflicts, and stops renewing after 900 seconds. Sync keepalive uses the same bounded duration and short transient retries. test_lease_renewal_retries_transient_failure_and_has_lifetime_cap plus existing renewal/thread-join tests cover the boundary. A cap does not kill a provider thread; token/expiry fences reject late writes. |
| R3-14 | Global open-ID validation now runs before codec/offload or any transaction batch. test_multiple_open_rows_are_rejected_before_any_batch_or_codec_write uses two large rows and rejects even codec side effects. Clarification: old code already iterated rows, not batch_rows, so its first transaction would abort atomically; the claimed successful two-row commit was not supported by that code. |
| R3-15 | omi_conversations_v3_terminal_failures_total counts committed transitions with static reason labels: processing/outline/transcription/attempts_exhausted. Processing transactions count after success; projection batches count after each committed batch. test_terminal_failure_counter_counts_committed_transitions_once proves repeated settlement is not another transition. Round-2 failed tiles/Retry remain covered. |
| R3-16 | A supplied summary token is released on fresh/ineligible stream exits. test_early_stream_exit_releases_preacquired_summary_token covers both branches. Clarification: prepare already returned None for an initially fresh/ineligible row; this closes the provided-token early-exit contract too. |
| R3-17 | Unfiltered layers use simple aggregates. Rare filtered layers inspect at most 10,001 metadata rows per layer, returning 503 above 10,000; predicates match list semantics, including explicit stored starred:false. No transcript decoding or optional-predicate composite power set. Filtered-scan, false-star and overflow tests in test_conversations_count.py cover the tradeoff. Generated manifest: 304 composites, versus 495 before this round; this is source count, not live schema access. |
| R3-18 | Episode MEMBER_FIELDS includes recording/home_hidden. test_member_read_mask_preserves_recording_guard_after_rollback hydrates through the real field mask and excludes the recording episode member. |
| R3-19 | Confirmed in _admitted: its later note_client_seen call was unconditional after channel admission despite the earlier beta gate in _v3_request_admission. Both paths are now beta-only. test_channel_admission_only_beta_refreshes_episode_client_marker covers beta/store/absent channel. |
| R3-20 | The rollout/deletion section explicitly requires V3-BACKFILL-30D-PARTITIONS and its full-window completion receipt before enabling backfill or claiming deletion readiness. PR-body metadata and preflight validate the draft; no runtime flag changed. |

## Verification commands and selection

The final selection is conversations-v3-review3-tests.txt: focused v3, every
touched backend test file, episode and audio/sync regressions, the lifecycle
writer inventory and all seven Firestore guard files. backend/test.sh keeps
one process per file and its normal timing guards. The launcher only adds
per-file JUnit receipts with the pinned worktree Python 3.11.

```sh
/Users/dazheng/workspace/omi/bin/omi-heavy run -- env \
  PYTHON=/Volumes/Ephemeral/scratch/episode-dayparts-brief/review3-pytest-xml \
  BACKEND_UNIT_TEST_FILE_LIST=/Volumes/Ephemeral/scratch/episode-dayparts-brief/review3-tests.txt \
  BACKEND_PYTEST_WORKERS=2 bash backend/test.sh
```

Generation and freshness/additive checks:

```sh
backend/scripts/openapi_runner.sh scripts/export_openapi.py --surface app-client --write
backend/.venv/bin/python backend/scripts/generate_dart_models.py --all
backend/.venv/bin/python backend/scripts/generate_ts_openapi_types.py
backend/.venv/bin/python backend/scripts/generate_swift_openapi_types.py
backend/scripts/openapi_runner.sh scripts/export_openapi.py --surface app-client --check
backend/.venv/bin/python backend/scripts/generate_dart_models.py --all --check
backend/.venv/bin/python backend/scripts/generate_ts_openapi_types.py --check
backend/.venv/bin/python backend/scripts/generate_swift_openapi_types.py --check
backend/.venv/bin/python backend/scripts/check_app_client_openapi_compatibility.py --base-ref origin/main
backend/.venv/bin/python backend/scripts/generate_firestore_indexes.py --write
backend/.venv/bin/python backend/scripts/check_conversation_readers.py --inventory
```

Backend selection: 3,479 passed across 29 files, including 178 focused v3 tests; zero failures, errors or skips.
All schema/generation checks passed. Swift regeneration was byte-identical.
Current-source Dart (from app/): omi-heavy run -- flutter test
 test/backend/conversations_v3_decoder_test.dart: 5 passed. Reader audit: 490
classified references. Standalone async-blocker gate: zero findings.
Pyright (from backend/): omi-heavy run -- env
 PYRIGHT_PYTHON_FORCE_VERSION=1.1.403 .venv/bin/python -m pyright -p
 pyrightconfig.json --pythonpath .venv/bin/python --level error.

Required final committed, frozen-head gate:

```sh
/Users/dazheng/workspace/omi/bin/omi-heavy run -- env \
  OMI_PR_BODY_FILE=/Volumes/Ephemeral/scratch/episode-dayparts-brief/PR-BODY-V3.md \
  make preflight
```

Exact final head, pass counts and receipts are appended to the requested PR body
and durable ANX outcome after the runner exits. No tracked report or PR-body
mutation during preflight. Early fixture mistakes, type/unused-import cleanup,
and the reviewed alias status inventory addition were corrected; they are not
counted as successful verification runs.

## Boundaries and scope evidence

The prescribed scope command initially needed an explicit local --git-dir to
resolve this unpushed branch. Panel scope-20261116t123652-3a7d then launched;
no completed answer was returned within bounded collection. All three executions
were cancelled and exited. No independent review is claimed. Supplied reviewer
findings were checked against current source and discriminatory regressions.
No PR exists or was opened, so no PR panel was run. The scope checkout is removed
after terminal collection.

No live model call, image build, real-Firestore emulator contention, named-account
dev E2E, distributed released-build/WAL/playback/export/share/delete acceptance,
or combined lead/Q12 runtime qualification was run. Synthetic decoder tests do
not certify a distributed released binary. Lead2 still sets FIRST_APP_BUILD at
rollout; it remains deliberately unset in source. Backfill remains OFF until
V3-BACKFILL-30D-PARTITIONS. No alternative audio design decision is pending.


Pinned mobile receipt: the commit hook refused the host-default Flutter 3.47.9.
An isolated Flutter 3.44.5 / Dart 3.12.2 SDK was fetched from the official release
manifest into /Volumes/Ephemeral/scratch/conversations-v3-flutter-3.44.5; its
SHA256 is 442aece6674c4334d46a4f110008a44e835ff53979a8f317333c5e71ccc065b4.
The pinned formatter made no changes and all 5 decoder tests passed with:
omi-heavy run -- /Volumes/Ephemeral/scratch/conversations-v3-flutter-3.44.5/flutter/bin/flutter
 test test/backend/conversations_v3_decoder_test.dart (from app/).
No formatting/commit guard was bypassed and no host-default SDK was changed.
Final preflight prepends this isolated SDK bin directory to PATH.
