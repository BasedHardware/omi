# Episode page proposal — render review only

Authority: David ruling ff0427 item 6, relayed in the episoderedesign brief.
David reviews these renders before implementation. Lead: refactor-lead.
This commit changes only test fixtures, the review-only widget, and evidence.
There is no app/lib, server, flag, deployment, or classifier change.

## Before / after

Each board shows the page at open, then at the end of the scrollable list.
Before is the real EpisodePage at base `9c051da5be4b0ccb76994a6b434d0c2371701dcf`.
After is EpisodeRedesignProposal under app/test, unreachable in the app.
Both use exactly the same synthetic episode. All content is fictional.

| State | Comparison |
| --- | --- |
| Typical day: three useful recordings, two noise rows | [Before / after](023-mobile-ios-typical-day-comparison.png) |
| Many noisy rows: two useful recordings, eight noise rows | [Before / after](024-mobile-ios-many-noisy-comparison.png) |
| Few members: one recording, no noise toggle | [Before / after](025-mobile-ios-few-members-comparison.png) |
| Long summary: four composed moments, four useful recordings | [Before / after](026-mobile-ios-long-summary-comparison.png) |

Additional states: [noise revealed](009-mobile-ios-many-noisy-after-expanded.png),
[full summary expanded](018-mobile-ios-long-summary-after-expanded.png),
[full summary ending](019-mobile-ios-long-summary-after-ending.png),
[Home without a count badge](020-mobile-ios-home-episode-no-count.png),
[narrow light appearance with larger type](022-mobile-ios-narrow-light-after-rows.png).
The individual full-resolution captures are listed in evidence.json.

## Proposal

Use the existing composed lede, moment points, supporting details and follow-ups
in a Summary card. Show two moments initially for a long summary, with Read Full
Summary revealing the rest. Follow-ups stay visible. This is a proposed disclosure
choice for David to review, not an approved product rule.

Below the summary, show each conversation's time, single-line title and single-line
gist. Only existing `home_step == noise` rows enter Show N More Recordings.
Unknown classification remains visible; duration and text length never classify
a row here. Discarded, deleted and merged donors stay excluded from the proposal.
No member count is added to Home; its evidence uses the unchanged production row.

## Before implementation

Await David's OK through the brief's relay. Then implement in this same themed PR
behind a default-on operational kill switch using the existing client flag reader
(OmiFlags / AnalyticsManager), with remote rollback to today's episode page.
Register the switch and verify on/off behavior before shipping.

The episode-member wire adapter currently carries only id, dates, title, emoji
and status. It omits `home_step`, title provenance and overview. Home's history
provider can supply some of these, but that is insufficient for a reliable detail
page opened from a sparse payload. Carry the existing classification and gist
through the episode API and generated adapters; do not create another classifier
or hide unknown legacy rows based on missing text.

The proposal's row taps and menu are visual affordances. Shipping must preserve
the real conversation detail hydration, moment transcript seeks, tasks, locking,
accessibility, deletion/undo and live-to-composed update behavior, with localized
copy. These are not verified by a visual proposal. Moment seek affordances will
need integration into the approved layout.

## Reproduce

Repository: BasedHardware/omi, branch lane/episoderedesign.
Worktree: /Volumes/scratch/worktrees/omi/omi-lane-episoderedesign-upstream-keep-clean.
Captured on m1-mac-studio, 2026-11-10 UTC. Flutter 3.44.5 / Dart 3.12.2.

From app/, through omi-heavy:

```sh
flutter test --no-pub --timeout 90s \
  --dart-define=EPISODE_REDESIGN_RENDER_OUTPUT=../.agent-artifacts/ui-evidence/episoderedesign \
  test/widgets/episode_redesign_render_test.dart --reporter expanded
```

From the repository root:

```sh
backend/.venv/bin/python app/test/widgets/episode_redesign/build_review_boards.py
```

Ten focused widget tests passed. Captures are 393×852 logical points at 3×,
except the short Home fixture and the 320-point, 1.3× text-scale light fixture.
The board builder only labels and arranges resized copies of the PNGs; it does
not retouch their content. Tests load SF Pro fixtures even without the output define
so the larger-type check can detect real font wrapping. The macOS emoji font is
loaded when available. Without the output define the tests write no images.
There is no device or authenticated E2E claim.
