# Processing today UI evidence — 2026-11-10 follow-up

Synthetic fixtures; no account data or remote backend was read. David approved
previous renders via relay 718fe8. This batch regenerates all eight original
renders and adds 009/010 for relay 66d9fd episode ownership before its fetch arrives.
The first four before/after pairs use placement off/on. The episode pair omits/
includes the formerly unparsed episode_id, keeping other fixture inputs identical.

Real ConversationsPage and ActivityPage: 393 × 852 logical pixels, 3× pixels,
light iOS theme, SF Pro fixtures, host Apple emoji font as render-only fallback.
No Apple system font is bundled. A fixed injected clock uses 2026-11-10 16:00.
Home fixtures include the unfinished row in both listed and local processing state.

See [prereview-dispositions.md](prereview-dispositions.md) for every review finding,
integration order, fixes and explicitly deferred discovery limits. The tests also
cover an expired today wait remaining exactly one terminal Home row, API episodeId
parsing/copy/cache, delayed episode fetch, cold/failed rollback, account fencing,
100-item pending plus loaded supplement, DST and open-page midnight movement.

All heavy commands run via `/Users/david/workspace/omi-workspace/bin/omi-heavy`.
From repo root:

```sh
backend/.venv/bin/python -m pytest backend/tests/unit/test_pending_work.py backend/tests/unit/test_home_step.py backend/tests/unit/test_phase_shadow_readers.py -q
backend/.venv/bin/python backend/scripts/run_dart_wire_hardening_check.py
make preflight
```

From app/:

```sh
flutter test --no-pub --reporter expanded --dart-define=PROCESSING_TODAY_RENDER_OUTPUT=../.agent-artifacts/ui-evidence/processingtoday test/unit/processing_today_test.dart test/services/pending_work_store_test.dart test/widgets/processing_today_render_test.dart test/unit/home_rows_test.dart test/unit/home_rows_state_space_test.dart test/pages/activity/activity_test.dart test/widgets/home_row_contract_render_test.dart test/widgets/conversation_summary_retry_row_test.dart test/widgets/conversation_detail_summary_retry_test.dart test/unit/auth_service_token_result_test.dart test/unit/auth_session_snapshot_test.dart test/providers/conversation_home_projection_replacement_test.dart test/providers/conversation_provider_processing_reconcile_test.dart test/unit/conversation_search_projection_decode_test.dart
bash scripts/analyze_ratchet.sh
TZ=America/New_York flutter test --no-pub test/unit/processing_today_test.dart test/widgets/processing_today_render_test.dart
TZ=Pacific/Kiritimati flutter test --no-pub test/unit/processing_today_test.dart test/widgets/processing_today_render_test.dart
TZ=Pacific/Pago_Pago flutter test --no-pub test/unit/processing_today_test.dart test/widgets/processing_today_render_test.dart
```

The timezone commands now run in the ordinary PR Dart job. The complete far-zone
suite remains on main/nightly. Focused analyzer previously reported only existing
enum-name/style infos; the repository analyzer ratchet is the validation authority.
The PR body records the final command results and commit-pinned render URLs.

Classification/deadlines remain unchanged. The backend flag stays default-on;
new clients require explicit successful confirmation. Absent/error/404/account
changes restore prior placement. Projected terminal failures remain on Home via
#25013, while date-hidden processing reaches Activity. The recorded start day is
used even when a capture crosses midnight. Every loaded Home row supplements the
pending window in Activity; historical episode-only/unstamped debt discovery and
all-history pagination remain deferred. Catch-up consumers retain their existing
through-notes-completion meaning. Physical-device behavior and live query latency
are unmeasured on this headless host. No merge/deploy or PCM CPU-guard changes.

Batched follow-up verification: 296 focused Flutter tests; 146 backend tests; 26 unit/widget tests in each of America/New_York, Pacific/Kiritimati and Pacific/Pago_Pago; analyzer ratchet and generated Dart wire-hardening check pass. Full preflight/hook results are recorded in the PR body.
