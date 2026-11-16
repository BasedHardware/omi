# Conversations v3 review round 1, 2026-11-16

Reviewed base: 852a2a5c861. Repair commits remain local on lane/conversations-v3.
No production/private-data access or GCP tier; no push, PR, merge, deploy or live
configuration change. No app pages, providers or widgets changed.

## Item disposition and discriminatory regressions

Audio fixes: b79fb522f80, 03367f2a2ab. Other fixes: 1a70d245e29. Verification: 47e0450a547.
The follow-on compatibility commit relocates additive declarations and applies
the durable title lock after cleanup; it also updates the outside-query witness
for the per-request admission argument.

| Item | Result | Regression / evidence |
| --- | --- | --- |
| A1 | Fixed, both audio commits | test_v3_dense_artifact_trims_pieces_and_neighbour_speech; test_v3_urls_only_serves_conversation_artifact; test_cached_backup_artifact_keeps_legacy_audio_files_protocol; test_v3_download_never_returns_covering_recording |
| A2 | Fixed | test_live_response_is_compact_and_never_a_recording |
| A3 | Confirmed, tests added | test_lapsed_beta_marker_restores_legacy_capture_and_episode_admission; legacy episode/client gate suites retained. Expiry returns new intake to ordinary capture; existing episode capability/admission gates still apply. |
| A4 | Mechanism fixed; release boundary pending lead | test_episode_build_bucket_uses_first_v3_build; test_episode_request_uses_build_header_not_marketing_version. Shared CONVERSATIONS_V3_FIRST_APP_BUILD is unset, hence unknown until lead supplies the first release build. Follow-up V3-FIRST-MOBILE-BUILD blocks deletion qualification, not beta capture. |
| B1 | Fixed | test_summary_route_returns_409_before_streaming_response; test_summary_holder_stores_before_releasing_lease_and_detail_sees_result |
| B2 | Fixed | test_backlog_over_128_advances_pages_and_extends_prior_window: 129 sources, oldest pages, stable window/id and all lines retained |
| B3 | Fixed | test_on_open_scopes_load_and_queues_processing; test_on_open_reconcile_timeout_streams_stored_row; test_on_open_projection_keeps_background_pending_obligation |
| B4 | Fixed, also entity-page mask | test_projected_product_surfaces_exclude_recordings (MCP, developer, by-id, entity); test_people_stats_projection_rejects_recording; test_prepare_excludes_recordings_and_home_hidden_rows |
| B5 | Fixed | test_terminal_processing_settles_pending (locked/deleted) |
| B6 | Fixed | test_preceding_outline_context_is_title_and_line |
| B7 | Fixed | test_rebuild_preserves_discard_lock_and_user_title. Preserve existing discard/lock/title unconditionally; only explicit restore/unlock paths change them. |
| B8 | Fixed | test_delete_during_capture_rearms_purge_at_settlement: release during live capture, settle, physical purge collaborator invoked |
| C1 | Fixed | test_sweeper_filters_age_in_query_and_cursors_past_1000: 1000 young plus 1001 old rows, two indexed cursor pages |
| C2 | Fixed | test_summary_renews_lease_until_model_finishes; test_synchronous_writer_owns_and_joins_lease_heartbeat; token/expiry persistence fences remain |
| C3 | Fixed | test_unreadable_markers_are_committed_instead_of_blocking; known private/clockless rows settle markers; decode failures still fail closed |
| C4 | Deferred, backfill OFF | V3-BACKFILL-30D-PARTITIONS must partition/resume the complete 30-day job before backfill enablement or deletion qualification. |
| C5 | Fixed | test_projection_partitions_bytes_and_keeps_pending_until_last_batch: 128 x 60 KB rows partition; claims/pending survive intermediate commits. test_projection_allows_transcript_offload |
| C6 | Fixed | test_malformed_outline_uses_cached_deterministic_fallback; test_paid_processing_and_outline_retries_are_content_bounded; exhausted-budget model meter test |
| C7 | Fixed | test_paid_processing_and_outline_retries_are_content_bounded; test_metadata_revision_change_does_not_rebill_unchanged_content |
| C8 | Fixed | test_short_threshold_and_covered_summary; test_short_on_open_does_not_store_empty_outline_as_fresh. Short means 20–299 words; media/background no processing. |
| C9 | Fixed | test_v3_short_path_obeys_content_minimum; existing quiet/content minima precede the short-task branch |
| C10 | Fixed | test_manual_end_after_last_speech_closes_preceding_stretch |
| C11 | Fixed | test_attribute_collection_constant_is_detected; dead get_visible entries removed; helper calls inventoried. Audit: 489 references. Per-call-site registry key strengthening remains optional, not needed for this fix. |
| C12 | Fixed | test_merge_rejects_recording_before_admission |
| C13 | Fixed | test_pending_bridge_preserves_user_curated_rows_and_layer_counts_use_aggregates; shared list-predicate count indexes declared |
| C14 | Fixed | test_reprocess_rejects_recording_before_processing; test_joan_rejects_recording_before_prompt. Joan product generation supersedes its earlier capture exception. |
| C15 | Fixed | test_episode_admission_is_cached_once_per_request; cached marker reader; existing admitted legacy calls still refresh capability |
| C16 | Fixed in source only | test_conversations_v3_stage_is_shared_across_creator_finalizer_readers; test_one_stage_source_moves_all_runtime_roles; prod runtime validator passes |
| C17 | Hardened | test_audio_alias_is_owner_checked: resolve and artifact snapshot re-read the conversation by uid, then recording claim ownership |
| C18 | Fixed | test_v3_missing_recording_piece_does_not_hide_playable_piece; test_manifest_skips_missing_piece_without_hiding_available_audio |
| D | Lead rejection retained | Planner creates derived in_progress rows; live endpoint filters recordings and uses a transcript-free compact model. |

## Verification

The 394-file broad selection (inventory beside this file) exercised episode,
conversation, sync, listen and playback suites. Initial run: 10,507 passed,
37 failed, 13 skipped, 7 deselected, 5 collection/setup errors; 12 files failed.
All failing files were repaired/rerun in a green 21-file run: 1,442 passed,
1 deselected. Import/field-mask/route seam assertions were updated where the
new product-read and per-request dependency seams changed; two host-sensitive
listen subprocess tests passed on rerun. This is composite coverage, not one
all-green invocation of the entire 394-file inventory at the final head.

Final touched/focused file run: 592 passed across 17 files. Follow-up audio and
heartbeat assertions initially brought JUnit coverage to 616 passed across 18 files
(including the 21 existing plugin transport tests); no test failure/skip/error.
The last isolated stream rerun moves a heavy router import to collection so its
call-phase CPU guard passes. The final single 19-file run at e1e57ff3a7d passes 649 tests with no errors,
failures or skips, including the outside-query witness and 133 focused v3 tests.
Current-source Dart fallback decoders: 3 passed. Slow Firestore digest: 1 passed,
606 deselected; fast query-shape guard: 606 passed, 1 deselected. Pyright: 0 errors.
App-client OpenAPI additive gate and all generated-client freshness checks pass.
Reader audit: 489 classified references. Prod runtime env validator passes.

All commands below run from the worktree root except the two noted directories.
`omi-heavy` means /Users/dazheng/workspace/omi/bin/omi-heavy. Logs and JUnit XML
are under the user-requested /Volumes/Ephemeral/scratch/episode-dayparts-brief/.

```sh
omi-heavy run -- env BACKEND_UNIT_TEST_FILE_LIST=/Volumes/Ephemeral/scratch/episode-dayparts-brief/review1-all-tests.txt BACKEND_PYTEST_WORKERS=3 bash backend/test.sh
omi-heavy run -- env BACKEND_UNIT_TEST_FILE_LIST=/Volumes/Ephemeral/scratch/episode-dayparts-brief/review1-rerun-tests.txt BACKEND_PYTEST_WORKERS=2 bash backend/test.sh
omi-heavy run -- env PYTHON=/Volumes/Ephemeral/scratch/episode-dayparts-brief/review1-pytest-xml BACKEND_UNIT_TEST_FILE_LIST=/Volumes/Ephemeral/scratch/episode-dayparts-brief/review1-final-touched-tests.txt BACKEND_PYTEST_WORKERS=2 bash backend/test.sh
omi-heavy run -- env PYTHON=/Volumes/Ephemeral/scratch/episode-dayparts-brief/review1-pytest-xml BACKEND_UNIT_TEST_FILE_LIST=/Volumes/Ephemeral/scratch/episode-dayparts-brief/review1-audio-final-tests.txt BACKEND_PYTEST_WORKERS=1 bash backend/test.sh
omi-heavy run -- env PYTHON=/Volumes/Ephemeral/scratch/episode-dayparts-brief/review1-pytest-xml BACKEND_UNIT_TEST_FILE_LIST=/Volumes/Ephemeral/scratch/episode-dayparts-brief/review1-small-tests.txt BACKEND_PYTEST_WORKERS=2 bash backend/test.sh
omi-heavy run -- env PYTHON=/Volumes/Ephemeral/scratch/episode-dayparts-brief/review1-pytest-xml BACKEND_UNIT_TEST_FILE_LIST=/Volumes/Ephemeral/scratch/episode-dayparts-brief/review1-stream-last-tests.txt BACKEND_PYTEST_WORKERS=1 bash backend/test.sh
omi-heavy run -- env PYTHON=/Volumes/Ephemeral/scratch/episode-dayparts-brief/review1-pytest-xml BACKEND_UNIT_TEST_FILE_LIST=/Volumes/Ephemeral/scratch/episode-dayparts-brief/review1-final-head-tests.txt BACKEND_PYTEST_WORKERS=2 bash backend/test.sh
omi-heavy run -- env BACKEND_PYTEST_MARK_EXPR=slow BACKEND_PYTEST_WORKERS=1 BACKEND_UNIT_TEST_FILE_LIST=/Volumes/Ephemeral/scratch/episode-dayparts-brief/TESTS-DIGEST-V3.txt bash backend/test.sh
backend/scripts/openapi_runner.sh scripts/export_openapi.py --surface app-client --check
backend/.venv/bin/python backend/scripts/generate_dart_models.py --all --check
backend/.venv/bin/python backend/scripts/generate_ts_openapi_types.py --check
backend/.venv/bin/python backend/scripts/generate_swift_openapi_types.py --check
backend/.venv/bin/python backend/scripts/check_app_client_openapi_compatibility.py --base-ref origin/main
backend/.venv/bin/python backend/scripts/check_conversation_readers.py --inventory
backend/.venv/bin/python backend/scripts/validate-backend-runtime-env.py --env prod --check-workflows
# from backend/
omi-heavy run -- env PYRIGHT_PYTHON_FORCE_VERSION=1.1.403 .venv/bin/python -m pyright -p pyrightconfig.json --pythonpath .venv/bin/python --level error
# from app/
omi-heavy run -- flutter test test/backend/conversations_v3_decoder_test.dart
# Required after committing this evidence; final result is in PR-BODY-V3.md and the ANX handoff.
omi-heavy run -- env OMI_PR_BODY_FILE=/Volumes/Ephemeral/scratch/episode-dayparts-brief/PR-BODY-V3.md make preflight
```

The JUnit launcher only delegates to the worktree's pinned Python and adds a
unique `--junitxml` file per test file; it changes no test selection or guards.
Final preflight receipt is attached to the existing ANX local handoff card:
https://anx.scalingforever.com/o/david-zhang/w/omi/r/card:conversations-v3-backend-local-handoff

## Unverified boundaries

No live model call, emulator contention, named-account dev E2E, production access,
image build or distributed released-app playback/WAL/capture test was run.
The released-client catalog has no captured historical bundle. Source decoder
fixtures and Python fallback tests are not released-device acceptance.
Audio now has a backend-only exact-window path; no alternative audio design is
pending David. The first v3 mobile release build still requires the lead's value.
Backfill remains off and cannot qualify the 30-day deletion criterion yet.


## Advanced-main scope and integration

Target observed during metadata validation: 1ed16cae960589255dfc70f63db31e95cc587a4c.
No Git merge or history rewrite was performed. Candidate field declarations and
flag records were relocated away from same-line upstream insertions. The v3
locked-title guard now runs after salience/cleanup, so the upstream title block
can apply unchanged before it. A parameterized regression checks both locked
and unlocked titles when cleanup returns a replacement structured value.

Scope panel: scope-20261116t105125-2ca9, candidate 47e0450a547. The primary agent
supplied an invalid duration (`--timeout 240`, rather than `4m`); the collector
marked errors and deleted its isolated checkout while members were still active.
Existing Luna and DeepSeek runs were collected with `agentctl await ... --timeout
4m --content`. Both reported their reduced inspection coverage. The third member
was cancelled via agentctl after its deadline; no member remains running.
This is a limited scope, not an independent full-feature approval. No PR exists,
so `omi-panel review --pr` was not run. Scope dossiers have risks, no F-numbered
findings; the tool's finding-triage command does not accept scope risks.

Disposition of the returned scope risks: accept preservation of the upstream
membership serializer, title-quality state, identity observation, word units and
profile scheduling by avoiding wholesale file replacement; accept title-lock
ordering and its regression; retain short/media/minimum guards and existing
model routing; preserve all flag values/dates and validate the registry. A
suggestion to create an integration branch/merge was rejected because the user
requires new commits on this branch and prohibits merging. Suggestions that a
missing Section type or content-word write allowlist might fail were questions,
not verified defects, and no speculative production changes were made.

Synthetic integration and branch execution are separate evidence: metadata
preflight tests whether the candidate combines with current origin/main; the
component tests execute this branch. The lead still owns combined Q12/mobile
runtime qualification and exact-head PR CI.


The first full preflight at e1e57ff3a7d passed the index guard (607 query-shape
tests), reader classification and synthetic-integration size gate, then found
two unclassified public runtime bindings. The follow-on declaration classifies
CONVERSATIONS_V3_STAGE and CONVERSATIONS_V3_FIRST_APP_BUILD as config in
config/deployment-setting-classification.json. Two parameterized source tests
pin config classification and regular environment placement for every service.
No deployment or external configuration was changed.
