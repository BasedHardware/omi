# Processing today UI evidence — 2026-11-10

Synthetic account fixtures; no account data or remote backend was read. The before
state uses the existing HOME_STEP_PROJECTION rollback behavior. The after state
uses local-day placement. Today, yesterday, Activity with an older pending item,
and empty Activity each have a before/after PNG in evidence.json.

Renders use the real ConversationsPage and ActivityPage at 393 × 852 logical pixels,
3× pixel ratio, light iOS theme, SF Pro fixtures, and the host Apple emoji font as
a render-only fallback. No Apple system font is bundled or committed. The Home
fixtures also put their unfinished row in the provider's local processing list,
covering the second insertion path.

## Verification

At production-code commit 31f88231e79687a382701cb9151978ff0b5ea536:

- Backend focused suite: 134 passed.
- Flutter focused suite: 91 passed.
- Changed-file Flutter analyzer: no issues.
- Midnight unit suite under TZ=Pacific/Kiritimati: 5 passed.
- make preflight with the PR body: 52 checks passed.

Final font-corrected render test: 10 passed. The evidence-only follow-up changes
font loading and the images; it changes no production code.

All heavy commands ran through /Users/david/workspace/omi-workspace/bin/omi-heavy.
From repo root:

```sh
backend/.venv/bin/python -m pytest backend/tests/unit/test_pending_work.py backend/tests/unit/test_home_step.py -q
```

From app/:

```sh
flutter test --no-pub --reporter expanded --dart-define=PROCESSING_TODAY_RENDER_OUTPUT=../.agent-artifacts/ui-evidence/processingtoday test/widgets/processing_today_render_test.dart test/unit/processing_today_test.dart test/unit/home_rows_test.dart test/unit/home_rows_state_space_test.dart test/pages/activity/activity_test.dart test/widgets/home_row_contract_render_test.dart
TZ=Pacific/Kiritimati flutter test --no-pub test/unit/processing_today_test.dart
```

## Boundaries

Classification and processing deadlines are unchanged. Home and Activity own only
presentation. HOME_STEP_PROJECTION=off in the backend restores prior placement via
the additive home_processing_today response field. Pending response limit remains
100; loaded Home rows supplement it in Activity. Live-account query latency and
physical-device behavior were not measured on this headless host. No merge or deploy.

Compatibility follow-up (2026-11-10): 135 focused backend tests and 91 focused
Flutter tests pass. An unfinished stored job remains in pending work after its
Home presentation deadline. Stale supplemental candidates do not trigger history
pagination; pagination remains only for the existing live-owner exclusion.
The four TypeScript clients were regenerated for the additive optional field.
