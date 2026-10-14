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

Known remaining candidates (not yet changed): the chat sheet keeps a full-screen
`BackdropFilter` (sigma 18) over the live home page for as long as chat is open
(`lib/pages/chat/chat_route.dart`, a UX-contract D1 decision; measure raster on a device before
changing it), SD-card/flash-page sync refreshes the WAL list per downloaded chunk
(`SyncProvider.onWalUpdated`), and the batch audio buffer fsyncs once per second from the UI isolate
(`MobileBatchBuffer`, a durability trade).

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
- **Narrow listeners**: prefer `Selector`/`context.select` over `Consumer`/`watch` at page roots.
- **Paint cost**: no blur in lists or persistent surfaces, decode network images at display size
  (`memCacheWidth`), and use slivers instead of `shrinkWrap: true`.

## Guards that run in CI

| Guard | What it catches | Runs |
|---|---|---|
| `.github/scripts/check_mobile_ui_isolate.py` | New sync I/O, provider JSON, JSON outside `offUiIsolate` in the WAL index / live transcript / conversation list / preferences modules, fast timers, blur, unsized images, shrinkWrap lists in changed files (no-increase ratchet); any proxy hook that notifies without an `identical`/`==` early return, or whose declaration it cannot read | `mobile-ui-isolate` in `.github/checks-manifest.yaml` |
| `test/perf/notify_amplification_test.dart` | Proxy hooks re-notifying; capture notifies walking the transcript | `bash test.sh` |
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
