# Episode detail redesign — approved implementation

David verdict relay-cl1 c3ee4c, 2026-11-10 08:31Z: full long summary expanded,
no Summary heading, one-tap linked task creation per follow-up. Prior ff0427 item 6
requires compact conversation rows, existing noise classification folded by default,
and no count badge on Home. PR #25022, lead refactor-lead. Synthetic data only.

These captures render the real EpisodePage on both sides: before has the operational
kill switch set true; after has it false. No test-only proposal widget remains.
The default is on. Set `mobile-episode-detail-redesign-disabled=true` through the
existing mobile flag service to restore the previous layout on next page open.
No remote flag row is created or changed by this PR.

Review boards: 025 typical day, 026 many noisy, 027 few members, 028 long summary.
Each shows at-open and at-end frames. Long summary is always expanded, including
all four moments and their details. Frames 018/019 show its middle and ending.
020 shows + ready; 021 shows the saved check. 009 reveals all eight short clips;
022 shows Home without a count; 023/024 show 320pt light mode at 1.3x text.

The + path is ActionItemsProvider.createActionItem -> existing POST /v1/action-items
with conversation_id and a stable Idempotency-Key. Composer follow-ups have no
individual source ids: the first retained non-noise conversation anchors the
follow-up (first retained member if none). This links to the episode's conversation
without asserting a source transcript span. In-flight and saved buttons disable;
retry/reopen uses the same server key. No separate todo store.

Reproduce on m1-mac-studio from app/ (through the managed omi-heavy runner):

```
flutter test --no-pub --timeout 90s \
  --dart-define=EPISODE_REDESIGN_RENDER_OUTPUT=$PWD/../.agent-artifacts/ui-evidence/episoderedesign \
  test/widgets/episode_redesign_render_test.dart
```

Then from repo root: `backend/.venv/bin/python app/test/widgets/episode_redesign/build_review_boards.py`.
The test loads real SF Pro/assets/emoji fonts with iOS metrics, captures a
RepaintBoundary at 3x, and asserts layout with and without output. Fixtures use a
loopback-only environment; they make no account, production or device reads.
These are widget renders, not device E2E. Inspect source PNGs for full resolution;
boards only resize and label the unmodified frames.
