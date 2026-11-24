# Processing today UI evidence — 2026-11-10 follow-up

Synthetic fixtures; no account data or remote backend was read. David approved
previous renders via relay 718fe8. All original renders were regenerated, 009/010 cover relay 66d9fd episode ownership before its fetch arrives, and 011–014 implement David's superseding failed-row ruling (relay 9e09f1).
The first four before/after pairs use placement off/on. The episode pair omits/
includes the formerly unparsed episode_id, keeping other fixture inputs identical.

Real ConversationsPage and ActivityPage: 393 × 852 logical pixels, 3× pixels,
light iOS theme, SF Pro fixtures, host Apple emoji font as render-only fallback.
No Apple system font is bundled. A fixed injected clock uses 2026-11-10 16:00.
Home fixtures include the unfinished row in both listed and local processing state.

See [prereview-dispositions.md](prereview-dispositions.md) for every review finding,
integration order, fixes and explicitly deferred discovery limits. The tests also
cover an expired today wait appearing only in Activity with retry, API episodeId
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
changes restore prior placement. David relay 9e09f1 supersedes #25013: projected terminal failures stay off Home and appear in Activity with retry; date-hidden processing also reaches Activity. The recorded start day is
used even when a capture crosses midnight. Every loaded Home row supplements the
pending window in Activity; historical episode-only/unstamped debt discovery and
all-history pagination remain deferred. Catch-up consumers retain their existing
through-notes-completion meaning. Physical-device behavior and live query latency
are unmeasured on this headless host. No merge/deploy or PCM CPU-guard changes.

Batched follow-up verification: 313 focused Flutter tests; 146 backend tests; 35 unit/widget tests in each of America/New_York, Pacific/Kiritimati and Pacific/Pago_Pago; analyzer ratchet and generated Dart wire-hardening check pass. Full preflight/hook results are recorded in the PR body.

Relay 9e09f1 adds render pairs 011/012 (failed Home before/after) and 013/014 (Activity retry before/after). Switch off uses #25013's previous Home failure row. Tests cover a successful retry, double-tap fencing, retry errors remaining actionable, ledger deduplication and a pending failed step outside loaded Home history. Relay 714b03 extends the change to the web conversation gallery and native macOS Conversations, each with Activity retry. No new query, stored job state or flag.

Latest relay 9e09f1 verification: 146 focused backend tests and 35 unit/widget tests in each of America/New_York, Pacific/Kiritimati and Pacific/Pago_Pago pass. Analyzer ratchet and generated Dart wire check pass. 313 expanded Flutter tests pass. Final repository-gate results are recorded in the PR body.

Activity also includes failures loaded only by Home search. Locked failed rows use a generic Processing Failed label; their private title stays redacted and existing server retry/entitlement checks remain authoritative. These paths have dedicated widget/unit coverage.


Relay 714b03 adds web renders 015/016 and native macOS renders 017/018. Web uses the actual FolderTabs, ConversationGallery and ConversationTile; native uses the actual HomeFailuresMovedState and FailedConversationsActivitySection mounted by ConversationsPage and ActivityHubTab. These are isolated production-component renders, not signed full-app sessions. Web screenshots use 1280×800 at 2×, local SF Pro, America/New_York and real Tailwind CSS. Native uses SwiftUI ImageRenderer, Aqua/SF system font, 720×420 at 2×. The native empty Home has only a failed fixture, while mobile/web also have a completed row. No network or credentials are used.

From web/app (Playwright 1.65.0 installed in a task-local directory, with `playwright install chromium --only-shell`):

```sh
bun run check
PLAYWRIGHT_MODULE=/path/to/task-local/node_modules/playwright/index.mjs PLAYWRIGHT_BROWSERS_PATH=/path/to/task-local/browsers bun scripts/ui-evidence/render-processingtoday.ts
```

The render script bundles only the real UI components, replaces API/analytics with explicit fixture functions, serves loopback only and blocks external browser requests. It asserts the failed row is absent from All, Activity exposes Retry, success removes the failed row, and rollback restores the failed Home tile. It closes the owned browser and server in finally.

From desktop/macos:

```sh
PROCESSING_TODAY_RENDER_OUTPUT="$PWD/../../.agent-artifacts/ui-evidence/processingtoday" xcrun swift test --package-path Desktop --filter 'HomeFailurePlacementTests|ConversationDisplayStateTests|ConversationRepositoryTests|ProcessingConversationWatcherTests|ServerConversationDecodingTests'
```

No bundle launch/signing/TCC changes. Native tests cover exclusive placement, missing/false/true wire fields, failed reads, double-tap/error retry, search-only reachability, completion and account clearing. Web typecheck/full suite pass; final counts and full hook are recorded in the PR body. Backend schema inventory regression: `backend/.venv/bin/python -m pytest backend/tests/unit/test_app_client_schema_inventory.py -q` passes all 14 tests after moving generated search decoding back to the API route (no test weakening).

Web retry results now replace known list/search rows and their list cache before refresh. A generation fence rejects a response started before that replacement, so failed refreshes and older reads cannot resurrect the completed Activity item. Tests cover failed refresh, cache remount and older list/search responses. The off path retains the previous status-only Home tile. Native Activity observes shared conversation updates and its spine receives the emitted confirmation value (Published emits before assignment), so placements update together.

Final local verification at head 9637bd3adbd280b7f8dfd952802a771bd286093c: all 88 repository preflight checks pass; web typecheck/smoke and 1,037 Vitest tests pass; 103 selected native tests pass. Flutter search/reconciliation subset rerun: 84 pass, plus analyzer ratchet. Final main-revert integration and the normal push hook are recorded in the PR body. The manual native mounted-destination flow is declared in e2e/flows/failed-conversations-activity.yaml and was not run as a signed app session on this headless host.

Web capture freezes CSS motion so the Activity selection is shown at rest; no product CSS is changed. The render script still verifies retry and rollback through the real component callbacks.

Web and native Activity retain account-scoped failures from loaded Home pages and search, so changing Home folders/dates cannot drop a row that was hidden. Completion and successful local deletion remove them; account reset clears both retained rows and deletion markers. No history scan is added. Web hook regressions cover filter changes, completion/deletion and reusing old source arrays across account changes. Native collection coverage uses the same remember/forget path as both mounted surfaces.

Final filter-supplement verification (2026-11-10 13:34Z, code checkpoint 7e9c6f6af99faae6f2445eeeee81e072a5931a8a): all 88 repository preflight checks pass; 1,039 web Vitest tests with typecheck/smoke and 103 selected native tests pass. The main revert required by relay 714b03 has not landed, so no follow-up push/full push hook has occurred. See handoff.md for exact remaining integration and publication steps. All local test/render/watcher processes have ended.

Post-revert integration: #25037 landed as d24d101cae0239838413bf537a80d5d68cf52018. Fresh main 35e63b5d701f94396cd166ef22db8df37aa947d4 was merged in 474edfb1b3efe9e6902e005c0699df9bee8627c1 with the adapted #25013 source/test/changelog files preserved exactly from the tested checkpoint. Old rejected Home screenshots remain deleted. This supersedes the earlier blocked status; post-integration test and normal push-hook results are recorded in the PR body. Anx is intentionally skipped at refactor-lead’s request.

## Luna retry-projection regression follow-up

Native authoritative replacements clear the old failed projection when retry
returns an active status without `home_step`; ordinary detail reads preserve it.
`ConversationRepositoryTests.testAuthoritativeReplacementClearsFailureWhenRetryOmitsHomeStep`
exercises stored/projected failures, active statuses and completion against the
real repository and Activity placement store. Explicit failed responses stay
failed. Approved PNGs are unchanged: this follow-up changes state reconciliation,
with no layout, copy or fixture edits.

Verification via `omi-heavy run --`:

- From desktop/macos: the five-suite Swift command above passed 104 tests with
  zero failures (105 executed, one opt-in PNG test skipped).
- From web/app: `bun run check` passed typechecking, six smoke tests and 1,041
  Vitest tests. Added list/cache/Activity and search-only/Activity retry cases
  using a processing response that omits `home_step`.
- From app: `flutter test --no-pub --reporter expanded
  test/providers/conversation_home_projection_replacement_test.dart
  test/providers/conversation_provider_processing_reconcile_test.dart
  test/widgets/conversation_summary_retry_row_test.dart
  test/widgets/conversation_detail_summary_retry_test.dart` passed all 148 tests.
  The new test checks failure clearing and Activity admission for in-progress,
  processing and merging without changing mobile's existing list ownership.

Full preflight and the one normal full-hook push are recorded in the PR body.
No production network, bundle launch, merge or deploy was performed.

## Notes failures with kept outputs (relay-cl1 94a9ed / David 4ddd04)

Cases 010/011/012 now have Activity captures on every client:

| Case | Mobile | Web | macOS |
| --- | --- | --- | --- |
| 010: failed Home projection with kept outputs | 019-mobile-ios-notes-case-010.png | 022-web-notes-case-010.png | 025-desktop-macos-notes-case-010.png |
| 011: action items kept, notes absent | 020-mobile-ios-notes-case-011.png | 023-web-notes-case-011.png | 026-desktop-macos-notes-case-011.png |
| 012: events kept, notes absent | 021-mobile-ios-notes-case-012.png | 024-web-notes-case-012.png | 027-desktop-macos-notes-case-012.png |

All nine use the server `conversation_notes_failed_with_outputs` attention kind;
clients never infer it from noise or local summary metadata. Real Activity widgets
show Needs attention and Re-run notes. Each conversation appears once. The mobile
and browser fixtures retain task/event arrays across retry; native uses the real
ledger model/store and SwiftUI section with injected server responses. No task or
event store is mutated. These fixtures verify client behavior; backend discovery
and the notes-only side-effect boundary belong to pipeline-driver's separate PR.

The existing default-on Home placement confirmation gates the new notes section.
Unknown kinds remain display-only, including mobile bulk retry. Accepted notes
retries suppress stale ledger/projected duplicates; rejection/failure retains an
error. Older reads and account changes are fenced; a genuinely new notes ledger
generation can surface after recovery. Missing optional display metadata decodes
through the existing generated mobile DTO with adapter defaults.

Additional verification commands (through `omi-heavy run --`):

```sh
# repo root, credentials unset:
backend/.venv/bin/python -m pytest backend/tests/unit/test_home_step.py backend/tests/unit/test_pending_work.py backend/tests/unit/test_flag_budget.py -q
backend/.venv/bin/python -m pytest backend/tests/unit/test_app_client_schema_inventory.py -q
# app/:
flutter test --no-pub --timeout 90s --reporter expanded --dart-define=PROCESSING_TODAY_RENDER_OUTPUT=../.agent-artifacts/ui-evidence/processingtoday test/services/notes_attention_test.dart test/services/pending_work_store_test.dart test/widgets/pending_work_test.dart test/widgets/processing_today_render_test.dart test/unit/processing_today_test.dart test/unit/home_rows_test.dart test/pages/activity/activity_test.dart test/providers/conversation_home_projection_replacement_test.dart
bash scripts/analyze_ratchet.sh
```

The web/native commands above now also capture cases 010/011/012. New native
sources are covered by the existing failed-conversations-activity manual flow,
extended with the notes-only ledger, unknown-kind, retry/error and account cases.
The PNGs were inspected for real fonts, legibility, single placement and clipping.
Final counts, preflight/full-hook result and non-test line delta are in the PR body.

Fresh-main completion: after the addition commit 44d470e980f19fee32992a9a31e3539b2454cf14,
merged main 8a9f00b975f3828134bb63a3952e4afb9affb0cd as
c6013b4b597faed1dc7e1500aaed5cbe8cb5719f, normally and without conflicts.
The separate #25034 registry conflict had already been resolved in 0bb9d47e42.
Addition-only non-test delta: +954/-81 (1,035 changed lines), excluding upstream
merges, tests/e2e and UI evidence/render harness; includes source, config, docs
and localization/generated files (+205 localization lines). The immutable
measurement and reproduction method are in notes-addition-line-delta.json.


### Off-page retry follow-up (Luna 6206927c)

The web cache correction changes retry reconciliation, with no layout or fixture change.
The existing PNG bytes and their published commit pins are retained. The new regression
cases exercise search-only remembered failures retried outside both loaded lists,
processing/completed and terminal-conflict acknowledgments, failed retry retention,
and notes-only ledger reconciliation. Cross-client regressions confirm shared-provider
replacement on mobile and explicit remembered-result reconciliation on macOS.

Validation: `cd web/app && bun run check` (type checking, 6 Bun smoke tests, 1,071
Vitest tests); Flutter notes/pending/provider tests (69 passed); native
`AttentionLedgerRetryTests|HomeFailurePlacementTests|ConversationRepositoryTests`
(70 passed, two opt-in PNG skips). The full hook and CI status are recorded in the
PR body. No production endpoint, signed app session, merge or deploy was used.
