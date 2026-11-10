# Verification receipt — 2026-11-10T09:30:21+00:00

Source verified: `6c8d2d59cef91c9f7cac7d31a03d82670fedf20b`. All data synthetic.
Host: m1-mac-studio. Heavy commands use omi-heavy.

- Flutter: 95 tests passed across episode detail read/gate, follow-up creation,
  render/layout, composed processing transition, delete/undo, existing row actions,
  row work checks and EpisodeProvider. The + test asserts one linked task on two
  taps before rebuild, disabled pending/saved controls, and stable retry/reopen keys.
- Backend: 92 tests passed in five isolated files: test_episode_member_presentation.py,
  test_episode_home_read.py, test_episodes_router.py, test_action_item_idempotency.py,
  and test_feedback_task_provenance.py. The changed detail endpoint is exercised
  through FastAPI TestClient with local fixtures and normal response validation.
- Focused Flutter analysis: no issues (14 path groups). Final lock-bit adapter is
  additionally compiled and exercised by the detail-read test above.
- Render capture: 28 PNGs and manifest; before/after four states, + ready/saved,
  noise expanded, Home no count and narrow light mode at larger type. Inspected
  real-font source frames and comparison boards. The final lock bit defaults false
  for these fixtures. Captures wait for a paint after scrolling; the supplementary
  long-summary middle frame is distinct from the ending.
- First-party TypeScript DTOs regenerated with backend/scripts/generate_ts_openapi_types.py
  after the first push hook detected stale clients; its --check now passes.
- Repository checks before the additive lock-bit follow-up: make preflight passed
  51 checks; PR preflight --all passed 52 gates, zero failed/skipped for time.
  Normal pre-push checks validate the publishing head; final result is in PR #25022.

Reproduction:

```sh
# app/, each through omi-heavy
flutter test --no-pub --timeout 90s test/unit/episode_detail_read_test.dart test/widgets/episode_follow_up_test.dart test/unit/episode_detail_gate_test.dart test/widgets/episode_redesign_render_test.dart test/widgets/episode_page_delete_test.dart test/widgets/episode_composed_render_test.dart test/widgets/conversation_hub_actions_test.dart test/perf/home_row_work_perf_test.dart test/perf/home_remaining_work_perf_test.dart test/unit/episode_provider_test.dart
# Add EPISODE_REDESIGN_RENDER_OUTPUT to capture; see README.md.
# repo root
make preflight
scripts/pr-preflight --all --pr-body-file <PR-body.md>
```

No live flag service, customer API, account data, device, deploy or merge used.
The composer supplies episode-level follow-up text without per-item source ids;
the task links to the first retained non-noise conversation (first retained fallback).
