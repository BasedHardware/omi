# Mobile interaction performance harness (Stage 1)

Run from any directory using the repository's driver path:

```bash
bash app/tool/perf_harness.sh
PERF_HOME_ITEMS=80 PERF_DETAIL_MESSAGES=100 PERF_MEMORY_ITEMS=60 PERF_CHAT_HISTORY=40 \
  PERF_SCORECARD_DIR=/tmp/omi-perf bash app/tool/perf_harness.sh
```

The driver uses host `flutter test --no-pub -d flutter-tester` with
`OMI_APP_PROFILE=local_dev`; no device, simulator, Firebase bootstrap, or
production backend is involved. Dataset size variables accept 1..2000; lists
must still contain enough content to scroll at the host viewport. Unprefixed
`HOME_ITEMS`, `DETAIL_MESSAGES`, `MEMORY_ITEMS`, and `CHAT_HISTORY` are also
accepted. `PERF_BUDGET_FILE` selects a JSON file (defaults to this lane's
`budgets.json`). Extra driver arguments are forwarded to Flutter.

The four hard gate tests each seed a fresh imported journey loopback backend,
load through real providers/HTTP clients, push a production page, interact,
and pop back. Home, transcript detail, and Memories fling to both endpoints.
Chat types a fixed message, taps the real send control, and requires the
fixture assistant reply to render through the real SSE path. Pages use the
imported journey app scaffolding rather than full `main()`/onboarding. Hardware
connectivity, phone-call events, and native directory lookup are stubbed at
platform channels; local recordings scan an isolated empty temp directory.
A loopback proxy supplies deterministic history and paginated datasets;
other requests go to the imported fixture.

The separate profile group always runs after the gates and writes
`$PERF_SCORECARD_DIR/scorecard-<timestamp>.json` (default `/tmp/omi-perf`).
`complete` requires all four measurements. Budget failures still leave their
measurements in the scorecard; a scenario failing before measurement may be
absent. The binding also records a `perf_trace` via `traceAction` and stores
the scorecard under `reportData.perf_scorecard` for integration-test retrieval.
The timestamp names the artifact only; seeded content has fixed dates and IDs.

## Reading the scorecard

Each scenario reports measured active UI frames, p50/p90/p95/p99 durations,
jank above 16.67 ms, rebuild counts (including initial builds), the top ten
rebuilders, and app widget source-file hints. `raw_ui_frame_ms` and
`janky_frames` associate slow frames with rebuilders and animation callbacks.
Frames with neither widget builds nor pending animation callbacks are excluded
and counted in `idle_frames_excluded`. Navigation and interaction are included;
provider seeding and app scaffolding setup are outside the measured window.

Under host `flutter test`, test time is controlled by fixed frame pumps.
`total_ms` and `build_ms` are wall-clock UI pipeline measurements from a frame
callback through the post-frame callback: animation callbacks, build, layout,
and paint. They are not device latency or pure widget build time. A stopwatch
keeps them code-change-sensitive rather than reporting virtual elapsed time.
The live integration binding also introduces host scheduling noise; this stage
proves execution, not cross-machine repeatability. Use the same machine, data,
viewport, warmup, and driver for comparisons, and compare repeated runs.

Host timing cannot measure GPU raster cost, shader-compilation jank, thread
priority, or real touch/network latency. Top-level `raster_ms` and raster-bound
jank are therefore null. `engine_frame_timing` separately contains genuine
FrameTiming samples when available, with build/raster quantiles and a
build-bound versus raster-bound split; these do not drive the host gate.
`ticker_census` counts scheduler transient callbacks as an animation proxy,
not actual Ticker objects: it cannot identify ticker owners or callbacks that
already finished during the sampled frame. Runtime-type source hints can be
ambiguous and rebuild counts include Flutter infrastructure. Attribution points
to investigation targets; it does not prove causation.

## Production conditions and phase split

Scenarios run with semantics off, as production does unless an assistive
technology is on (`testWidgets` defaults it on). `PERF_SEMANTICS=1` turns it
back on to measure VoiceOver-style conditions. Each scenario's scorecard
reports `semantics_enabled` and `ui_phase_ms`: UI-thread time per pipeline
phase (BUILD, LAYOUT, PAINT, COMPOSITING, SEMANTICS, FINALIZE TREE) from
`FlutterTimeline`. Host wall-clock swings between runs, but the split within
one run is stable, so a phase's share is comparable across arms.

## Device lag capture (what the host cannot see)

Host runs cannot raster, run AOT code, or reproduce a real phone's data and
thermal state, and an earlier round's host timings swung 5–10× between runs.
For lag a user feels, use the in-app recorder
(`lib/utils/analytics/lag_recorder.dart`). It runs in release and TestFlight
builds while Settings → Developer → Debug logs is on, and writes only to the
local debug log:

- for each surface (pushed page type or Home tab): frames, slow (>16.7 ms on
  either thread), severe (>33.3 ms) and freeze (>100 ms) counts, build-bound
  versus raster-bound, and whether the user was scrolling, had just tapped or
  was idle;
- the worst frames with wall-clock time, tap-to-frame latency (it includes the
  tap handler's own synchronous work), and UI-isolate stalls between frames
  (a 250 ms watchdog that runs only while capture is on).

To capture: turn on Debug logs, background and reopen the app, use it until it
lags, background it once (that writes `mobile_lag_report`), then use
Developer → Share logs. Then run
`python3 app/tool/lag_report.py omi_debug_YYYYMMDD.log` for a ranked table.

## Hill-climb contract

Keep scenario behavior, data sizes, sampling, and measurement definitions
fixed while optimizing production code in later stages. Compare all four
scenarios and their rebuild/animation evidence. Tighten budgets only after an
accepted optimization win demonstrated across repeated comparable runs; do
not raise budgets or weaken the interaction to hide a regression. The initial
100 ms p90 budgets are generous bootstrap gates, not a 60 fps quality claim.
Stage 1 neither changes production code nor publishes changes.
