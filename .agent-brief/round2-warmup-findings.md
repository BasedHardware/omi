# Round 2 — Stage A warm-up instrumentation

Added only `app/integration_test/perf/perf_warmup_test.dart` plus this findings document. The existing scenarios, instrumentation helper, budgets, gate group and driver are unchanged. The new test imports `PerfWorld` and `PerfInstrumentation`, boots the same loopback fixture and real providers, taps the first Home row into detail, returns, opens Chat, and scrolls seeded history until 15 real seconds have elapsed. JSON schema: `omi-mobile-warmup/v1`. Missing engine samples remain null, with independently labeled host UI statistics; no synthetic timings or performance gate.

## Two passing proof runs

Run twice from `app/`, each in a fresh Flutter test process:

```sh
PERF_SCORECARD_DIR=/tmp/omi-round2-warmup-proof flutter test --no-pub -d flutter-tester \
  --dart-define=OMI_APP_PROFILE=local_dev integration_test/perf/perf_warmup_test.dart
```

Both runs: `All tests passed!`, `complete: true`; default dataset 80 Home items / 100 detail transcript segments / 60 memories / 40 chat messages. Base HEAD at measurement: `e52113704226457f55b72a10d20143182921f11c`. Shared worktree had concurrent app-init work, including an uncommitted `app/lib/providers/local_recordings_provider.dart` change; these measurements characterize the working tree, not an isolated baseline or an optimization comparison. Other agents' files are excluded from this commit.

| Cumulative wall-clock milestone (ms from before seed) | Run 1 | Run 2 |
| --- | ---: | ---: |
| `fixture_backend_up_ms` | 148.239 | 154.534 |
| `providers_first_ready_ms` | 193.493 | 204.145 |
| `first_home_frame_ms` | 1146.684 | 1333.169 |
| `first_detail_open_ms` | 1524.864 | 1729.942 |
| `first_chat_open_ms` | 4344.438 | 4676.706 |

| Interval delta (ms) | Run 1 | Run 2 |
| --- | ---: | ---: |
| Origin → loopback ready | 148.239 | 154.534 |
| Loopback ready → seed/provider first-ready | 45.254 | 49.611 |
| Providers ready → first Home frame (includes scaffolding boot) | 953.191 | 1129.024 |
| Home frame → tapped detail frame | 378.180 | 396.773 |
| Detail frame → Chat frame (includes 50 paced transition pumps) | 2819.574 | 2946.764 |

| Window / measurement | Run 1 frames | Run 1 p90 ms | Run 1 jank % | Run 2 frames | Run 2 p90 ms | Run 2 jank % |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 0–5s engine FrameTiming build + raster | 68 | 90.120 | 16.176 | 60 | 89.302 | 18.333 |
| 5–15s engine FrameTiming build + raster | 193 | 17.369 | 12.953 | 191 | 17.672 | 13.089 |
| 0–5s host active UI pipeline | 31 | 155.166 | 29.032 | 23 | 197.843 | 34.783 |
| 5–15s host active UI pipeline | 135 | 11.914 | 2.963 | 133 | 12.457 | 3.008 |

Jank threshold is 16.667 ms. Engine build p90 changes from 75.496/73.510 ms early to 9.740/9.543 ms later; raster p90 is 9.404/8.999 ms early and 8.068/8.233 ms later. Engine callbacks include idle frames; the imported host helper excludes idle frames, so their sample populations differ.

Artifacts (alongside the steady-state scorecard in the same directory):

- Run 1: `/tmp/omi-round2-warmup-proof/warmup-1791868637855763.json`; log `/tmp/omi-round2-warmup-proof1.log`.
- Run 2: `/tmp/omi-round2-warmup-proof/warmup-1791868684588118.json`; log `/tmp/omi-round2-warmup-proof2.log`.

## Interpretation and app-init investigation targets

The largest elapsed interval is detail-to-Chat (2.82–2.95s), but it deliberately contains 25 paced pumps before popping detail and 25 afterward to complete route transitions, so it cannot establish expensive Chat initialization. Excluding that controlled navigation interval, provider-ready to first Home dominates startup at 0.95–1.13s, versus only 0.19–0.20s to seed/load providers and 0.38–0.40s to open detail. The early engine build p90 is roughly 74–75ms while raster stays near 9ms; both runs show much lower later build/UI p90. This points toward first widget construction/layout, lazy provider initialization and post-frame work, with host debug/JIT contributing, rather than fixture HTTP as the main measured cost. It supports a measurable early-versus-later distinction but does not reproduce or explain a full installed-app 10–15s launch stall.

File-level suspects for the other agents (investigation leads, not causal attribution):

1. `app/lib/pages/conversations/conversations_page.dart`: first list construction and `initState` post-frame work, including deferred `LocalRecordingsProvider.refresh`; inspect `app/lib/providers/local_recordings_provider.dart` for scan/duration work. The fixture uses an empty native directory, so populated real recording scans remain outside this evidence.
2. `app/lib/pages/conversation_detail/page.dart`: playback/tab construction, cached-conversation provider notification and post-frame `initConversation`; also `app/lib/pages/conversation_detail/conversation_detail_provider.dart`. The ~380–400ms first-detail interval warrants measuring this path independently.
3. `app/lib/pages/chat/page.dart`: first seeded history layout and post-frame enabled-app fetch/health-sync hooks; also `app/lib/providers/message_provider.dart`. First Chat arrives during the expensive early-build window, but the navigation pacing means the cumulative Chat milestone alone cannot attribute its cost.

## Lane caveats and validation

The file header documents the real wall clock versus virtual test clock, 1ms readiness observation plus real loopback probe, fixed 16ms pumps paced by actual delays, navigation transition pumps, and separate engine/UI sources. Both windows start before `PerfWorld.seed()`; time without rendered frames is not invented as a zero-duration frame. Provider first-ready means the same fully seeded conversations/memories/messages readiness used by existing scenarios; it is not readiness of every lazy app provider. First destination frames are hit-testable production widgets, not fully hydrated/settled pages. The early window includes construction/navigation while the later window is chat scrolling, so their difference also reflects workload, not solely warming. Fixed seed dates, IDs, dataset sizes and scroll progression preserve the lane's deterministic inputs. This fixture-page boot omits `main()`, native startup/Firebase/hardware/real network, and host FrameTiming raster is not a phone-GPU measurement.

Validation:

- New test: two passing runs with the JSON artifacts above.
- `cd app && flutter analyze --no-pub integration_test/perf`: **clean**, no issues found.
- `make preflight`: **passed**, 23 checks (log `/tmp/omi-round2-warmup-preflight-final.log`).
- Existing gate: **not green in the shared working tree**. `PERF_SCORECARD_DIR=/tmp/omi-round2-warmup-proof bash app/tool/perf_harness.sh` passed Home/detail/memory but failed `chat_tap` p90 43.507ms > unchanged 35ms budget; log `/tmp/omi-round2-warmup-existing-gate.log`, scorecard `scorecard-1791868814173342.json`. A full rerun without this agent's analyze/preflight overlapping again passed the other three and failed chat p90 171.733ms (20 active samples); log `/tmp/omi-round2-warmup-existing-gate-retry.log`, scorecard `scorecard-1791868967298885.json`. The new entrypoint is never imported by `perf_main.dart`; all existing harness files and the driver have zero diff from HEAD. Shared-tree app edits and host timing noise remain uncontrolled; this evidence does not isolate the cause. No budgets/scenarios were changed to conceal the failure.
