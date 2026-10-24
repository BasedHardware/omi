# Mobile performance: keep the UI isolate free

The UI isolate builds, lays out and paints every frame; at 60 Hz it has 16 ms. Anything else it
does (JSON, hashing, file I/O, rebuilding widgets that did not change) is taken from that budget,
and the user feels it as a stuttering scroll, a slow page transition or a late tap.
Rule and guard: `INV-PERF-1` ([`product/invariants/mobile-ui-isolate.md`](../../product/invariants/mobile-ui-isolate.md)).

## What made the app lag (October 2026 audit)

The lag was intermittent because it scaled with what the app was doing in the background and
with how much history the user had, not with the screen in front of them.

| Cause | Where | Fix |
|---|---|---|
| The WAL index (one JSON file listing every recording chunk) was re-read, re-decoded and fully re-encoded on the UI isolate on every save, from dozens of call sites (several per upload batch) | `lib/utils/wal_file_manager.dart` | Queued saves collapse into the newest snapshot; the backup copy skips re-decoding a file this process wrote; large indexes encode via `offUiIsolate` |
| Proxy update hooks notified unconditionally, so every Conversation/Message/People/Usage notify re-notified Capture, and every Capture notify re-notified Device | `CaptureController.updateExternalActions`, `DeviceProvider.setProviders` | Return early when the injected references are unchanged |
| A listener on every capture notify joined the whole live transcript into a string; each new segment also hashed and JSON-encoded the whole session | `CaptureProvider._persistLiveSegments`, `LocalSegmentStore` | Cheap change key (list identity, length, `segmentsPhotosVersion`, owner token); no full-transcript fingerprint; writes coalesce so a burst of segments costs one snapshot per completed write; long sessions hash/encode via `offUiIsolate` |
| On resume, multi-megabyte conversation pages (with transcripts) were parsed and re-cached on the UI isolate | `getConversations`, `SharedPreferencesUtil.cacheConversations` | Large bodies parse via `offUiIsolate`; the cache encodes in the background behind a generation guard |
| `listSync` of the documents directory (which holds every WAL file) on every resume | `LocalRecordingsProvider.refresh` | Async `dir.list()`; when scans overlap, only the newest publishes or rewrites the owners file |
| The memories list re-filtered every memory for each row it built | `MemoriesPage` | Filter once per build |
| Voice dictation notified the provider at 60 Hz, rebuilding the whole chat composer | `VoiceRecorderProvider` | A dedicated `waveformTick` that only the waveform listens to |
| The iOS rage-click tracker held a `SemanticsHandle` for the app's lifetime, so every production iOS frame compiled the semantics tree (17–25% of UI pipeline time while scrolling a list); host harnesses never mounted it | `RageClickContextTracker` | Resolve the tapped control from the pointer's render hit-test path; semantics stays off unless an assistive technology turns it on |
| Background sync re-sorted the whole recording history on each progress refresh and published every inventory read and identical progress tick | `SyncProvider` | Reuse the sort order while membership and timestamps are unchanged; coalesce scalar progress to 100 ms (phase, file and terminal changes publish immediately); drop identical progress |
| The breathing live marker rebuilt and relaid out its surroundings every animation frame | `omi_live_indicators.dart` | A fixed-size painter repaints only itself |

Known remaining candidates (not yet changed): the chat sheet keeps a full-screen
`BackdropFilter` (sigma 18) over the live home page for as long as chat is open
(`lib/pages/chat/chat_route.dart`, a UX-contract D1 decision; measure raster on a device before
changing it), sync backlog and filter getters still scan the WAL list linearly (refreshes are now
coalesced to 100 ms and reuse the sort order), and the batch audio buffer fsyncs once per second from
the UI isolate (`MobileBatchBuffer`, a durability trade).

## Rules of thumb

- **Work that grows with history goes through `offUiIsolate`** (`lib/utils/off_ui_isolate.dart`).
  It runs inline below a size threshold and on a background isolate above it; the closure must be
  pure. Tests assert `offUiIsolateFallbacks == 0` so a payload that cannot cross isolates does not
  silently move back to the UI.
- **No synchronous `dart:io`** in `lib/`. `listSync`/`existsSync` on a directory with thousands of
  WAL files blocks the frame.
- **Proxy update hooks return early when nothing changed.** They run on every upstream notify.
  If a downstream page genuinely derives from upstream state (the conversation detail page), say
  so with `// omi-perf-allow: proxy-hook-notify -- <reason>` above the declaration.
- **Listeners that run on every notify must be O(1) when nothing relevant changed.** Key them on
  list identity, length or a version counter (`segmentsPhotosVersion`) before walking anything.
- **Frame-rate visuals tick their own listenable.** Never `notifyListeners()` a shared provider at
  60 Hz; use an `AnimationController` or a `ValueNotifier` the painter listens to.
- **No `SchedulerBinding.scheduleTask` below `Priority.animation` from a surface that can
  animate.** The default strategy declines the task while any ticker runs, and the scheduler
  re-arms a zero-delay timer every event-loop turn until it can run: a pulsing dot or an
  indeterminate bar turns one queued idle task into a busy-looping UI isolate. Defer with
  `Timer.run`, a `Future` or a post-frame callback instead.
- **Narrow listeners**: prefer `Selector`/`context.select` over `Consumer`/`watch` at page roots.
- **Paint cost**: no blur in lists or persistent surfaces, decode network images at display size
  (`memCacheWidth`), and use slivers instead of `shrinkWrap: true`.

## Guards that run in CI

| Guard | What it catches | Runs |
|---|---|---|
| `.github/scripts/check_mobile_ui_isolate.py` | New sync I/O, provider JSON, JSON outside `offUiIsolate` in the WAL index / live transcript / conversation list / preferences modules, fast timers, blur, unsized images, shrinkWrap lists in changed files (no-increase ratchet); any proxy hook that notifies without an `identical`/`==` early return, or whose declaration it cannot read | `mobile-ui-isolate` in `.github/checks-manifest.yaml` |
| `test/perf/notify_amplification_test.dart` | Proxy hooks re-notifying; capture notifies walking the transcript | `bash test.sh` |
| `test/perf/home_after_detail_perf_test.dart` | An idle-priority scheduler task behind Home's live dot; the 1-second tick leaving its leaf; tickers or rebuilds left behind by a detail visit; list updates rebuilding more than one shell per mounted row | `bash test.sh` |
| `test/perf/conversation_list_off_ui_test.dart` | Off-isolate parse/encode drift, stale cache writes, non-sendable payloads | `bash test.sh` |
| `test/unit/wal_file_manager_save_cost_test.dart` | Save coalescing, off-isolate index encode, backup validation | `bash test.sh` |
| `test/unit/voice_recorder_mic_contention_test.dart` (waveform case) | 60 Hz provider notifies while dictating | `bash test.sh` |
| `test/unit/local_segment_store_test.dart` (digest case) | Off-isolate transcript digest drifting from the inline one | `bash test.sh` |

The ratchet compares each changed file with its merge-base version, so a renamed or moved file
starts at zero and its existing hits read as new; carry them over with allow comments. The
host perf harness below is deliberately not a CI gate: its frame times depend on the machine and
its rebuild counts vary a few percent between runs (live binding, real loopback I/O).

Run the ratchet on your files before pushing:

```bash
python3 .github/scripts/check_mobile_ui_isolate.py --report app/lib/pages/foo.dart
python3 .github/scripts/check_mobile_ui_isolate.py --graph
```

## Measuring

- **Interaction harness** (`integration_test/perf/`, `bash tool/perf_harness.sh`): real pages over
  a loopback fixture backend; reports frame-time percentiles, jank counts and per-widget rebuild
  counts in a JSON scorecard. Host `flutter test` cannot measure raster cost, and its wall-clock
  numbers vary by machine; compare runs on one machine, and treat rebuild counts as the portable
  signal. See its README.
- **In-app telemetry** (`lib/utils/analytics/mobile_performance_telemetry.dart`): per-route frame
  counts, frames over 32 ms and max frame time, written to the debug log when developer logs are
  enabled. Turn it on, reproduce the lag, and read which route and background activity coincided.
- **A device trace** is the ground truth: `flutter run --profile` on a phone, then DevTools'
  Performance view during a sync or a long recording.

## Sync ring and Device page regression (October 21, 2026)

`OmiActivityRing` used a `RotationTransition` without a repaint boundary. In a
60-frame window the real Home battery header had 60 rotation-widget builds and
60 surrounding display-list repaints while syncing (both zero while idle).
It did not rebuild Home's page root or notify a provider at frame rate. The arc
now listens to its controller directly in a `CustomPainter` inside its own
`RepaintBoundary`; its static glyph and the header stay out of those repaints.
The controller stops when inactive, under Reduce Motion, or outside `TickerMode`.

Separately, Device settings listened to all Capture, Sync, Conversation and
Episode notifications at the page root. Metric samples and progress updates
rebuilt every section and recalculated the WAL totals and today's conversation
durations. Capture metrics sample every five seconds; episodes poll and tick
every 30 seconds. Neither is a frame-rate timer. Device settings now selects
its visible capture state and sync badge, with separate subscriptions for stats,
Right now and the diagnostic rates. Ten irrelevant Capture/Sync notification
pairs per simulated second used to cause ten whole-page builds, both idle and
syncing; now they cause zero. Visible pause and sync-amount updates remain tested.

Reproduce the counters with `flutter test test/perf/sync_indicator_isolation_test.dart`
from `app/`. For the same workload with an explicit live frame policy, run
`flutter test --no-pub -d flutter-tester integration_test/perf/sync_indicator_perf.dart`.
It pumps 60 frames at 16,667 microseconds each, after warmup, and logs rebuilds,
surrounding paints and host UI pipeline p50/p95. The page input stress rate is
10 notification pairs per second, not a claim about the production notification
rate. Optional `SYNC_INDICATOR_EVIDENCE_DIR` writes synthetic screenshots.
These host timings do not measure phone latency or GPU raster; use rebuild and
paint counts as the portable regression signal and a phone profile for device jank.

## Home scroll after opening a conversation (October 21, 2026)

Opening a conversation from Home queued its analytics through
`SchedulerBinding.scheduleTask(…, Priority.idle)`. The default scheduling
strategy declines an idle task while `transientCallbackCount > 0`, and
`SchedulerBinding._runTasks` then re-arms `Timer.run` every event-loop turn
until the task can run. With a capture live, Home's episode row pulses its dot
indefinitely, so the UI isolate busy-looped from the tap onward: through the
push, through a processing conversation's indeterminate bar on the detail
page, and on Home again after the pop. In a widget test the same shape never
returns from `pump` and the tester grows to 34 GB. The call now defers with
`Timer.run`. The capture card's own 1-second `setState` also stops while the
episode row draws the capture, since the card renders nothing then.

`flutter test test/perf/home_after_detail_perf_test.dart` from `app/` pumps the
real Home with the pulsing live row and a pushed detail page: the scheduling
strategy is consulted zero times on open (the old code trips the spy at 51),
the open still reaches analytics, five ticks rebuild only `LiveEpisodeClock`,
three visits leave `transientCallbackCount` at baseline, and ten list identity
replacements cost one shell build per mounted row each (20 here; row content
stays behind its `Selector`). That last number is the current cost of a
completion landing on Home, not a floor.

## Device lag capture (October 23, 2026)

Host runs cannot raster, run AOT code, or reproduce a phone's data and thermal state. For lag a
user feels, use the local recorder in `lib/utils/analytics/lag_recorder.dart`. It runs in release
and TestFlight builds while Settings → Developer → Debug logs is on, and writes only to the local
debug log. Per surface (the pushed page type or the Home tab) it records:

- frames over 16.7, 33.3 and 100 ms on either thread, split into build-bound and raster-bound;
- whether each slow frame came while scrolling, just after a tap, or idle;
- the worst frames, with wall-clock time;
- tap-to-frame latency, which includes the tap handler's own synchronous work;
- UI-isolate stalls between frames, from a 250 ms watchdog that runs only while capture is on.

To capture:

1. Turn on Debug logs, then background and reopen the app.
2. Use the app until it lags, then background it once. This writes `mobile_lag_report`.
3. Share the log from Developer → Share logs.
4. Run `python3 app/tool/lag_report.py omi_debug_YYYYMMDD.log`.
