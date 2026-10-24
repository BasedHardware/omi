# Mobile UI performance admission (INV-PERF-1)

After preparing hermetic app inputs (`bash app/test.sh`), run from the repository root:

```bash
bash app/tool/perf_gate.sh
```

The command runs three fresh, serial Flutter processes under `nice -n 10` and
prints a scorecard with count ranges and timing variance. `PERF_SCORECARD_DIR`
selects an **empty** artifact directory; otherwise each invocation creates one.
`PERF_GATE_REPEATS=1` is useful while developing; acceptance needs three clean
consecutive runs. No device, credentials, Firebase service, or production data
is used. Pinned SDK: Flutter 3.44.5. Missing generated inputs are a setup error,
never a green result. The measured command duration excludes one-time setup.

`app/test/perf/production_shell_gate_test.dart` runs the same eight scenarios in
ordinary `test.sh`, with three independently seeded trials in one isolate to
amortize compilation. The local command uses three fresh processes instead.
Existing Mobile App Checks and Mobile Release Eligibility
therefore block admission of a regressed scenario; no workflow is added.
Shell fidelity and tool-contract checks also register in the existing local/CI
checks manifest. Existing release admission requires the canonical successful
Mobile Release Eligibility check on the exact release source.

## Production-shell fidelity

All Stage 1/2 scenarios use one `PerfProductionShell` through `PerfWorld.boot`.
`python3 app/tool/perf_shell.py` derives it from the actual `main.dart` builder
chain, including `WithForegroundTask`, production theme/localization,
`BluetoothGuidanceListener`, `RageClickContextTracker`, `TalkerWrapper`, and the
production `MobilePerformanceTelemetry` initializer/observer. Its frame callback
is attached. It forces the iOS + configured analytics predicate on a host, so
that platform's wrappers participate even without an analytics key. The page
is the inert fixture entry route; real production pages are then pushed by the
existing scenarios. Provider/native/backend bootstrap stays at the journey's
hermetic seams. This is shell fidelity, not full startup/onboarding coverage.

`perf_shell.py --check` rejects stale output. It fingerprints all of main.dart
and refuses unknown root wrapper shapes, so adding a wrapper outside the
extracted builder cannot silently evade the test. Regenerate after a deliberate
main change, review the new wrappers, and rerun the gate. The preferred future
seam is a shared production shell function called directly by main and tests;
this adapter avoids editing main while the parallel lag-fix lane owns it.

Each test uses `semanticsEnabled: false`, matching an app with no accessibility
client. A wrapper's held semantics handle still turns compilation on and fails.
This does not prohibit accessibility: assistive-technology sessions correctly
compile semantics and need separate device measurements.

## Measurements and budgets

The existing `budgets.json` owns all thresholds. Top-level numeric p90 budgets
are retained as historical diagnostic values; they no longer gate host runs.
`_gate` contains the blocking work-count caps for each scenario, zero semantics
compiles per sampled frame, and zero semantics share of measured pipeline work.
Initial rebuild/layout/paint caps are the unchanged-production baseline +10%
and 10 events, clip-layer maxima +2, nonzero opacity-layer maxima +1, and
painted image size at least 1,048,576 pixels. Semantics remains exactly zero.
Three independent holdouts passed with identical counts (26.6–28.3 seconds
each; 0/3 observed false failures). These initialize new count metrics, not
relaxations of existing timing caps.

Counts include route push/pop and interaction; seeding/warmup are outside the
measurement. Missing phases, samples, scenarios, repeated scorecards, framework failure
evidence or successful process exits fail. `run-status.json` preserves exit
codes independently of the measured counts; rendering errors cannot export
a successful admission card.

The scorecard records:

- `FlutterTimeline` build, layout, paint, compositing, compositing-bit updates,
  semantics, and tree-finalization counts, milliseconds and phase shares.
- Widget rebuilds including initial builds; actual render-object layout events
  nested inside the layout phase; debug paint callbacks; sampled frame count.
- Maximum retained layer census by type; clip total is the sum of per-type
  maxima. Opacity layers are candidates for compositing work, not GPU calls.
- Painted images' decoded and displayed dimensions. This is not a count of
  codec invocations and cannot see an image decoded but never painted.
- Real engine `FrameTiming` build/raster samples when the engine supplies them.
  Host raster is unavailable. `save_layer_count` is null: only a device GPU
  trace can measure actual `saveLayer` calls; no proxy is passed off as a count.

Host frames use an AutomatedTestWidgetsFlutterBinding with virtual time and
real loopback HTTP enabled; the real-time integration binding is reserved for
device capture. Host elapsed milliseconds are diagnostic. A shared Mac can pause mid-phase;
phase ratios can also vary. The exact zero semantics-share budget is robust to
that noise; other phase shares are reported with variance, not assumed stable.
Work counts are measured with debug instrumentation and cannot be compared to
uninstrumented device timing. Restore/debug-hook teardown is part of the
instrumentation contract. `variance.json` reports min/max/mean/standard deviation
of each count plus every repeated phase share and host p90.

Scenarios retain their fixed seeded datasets: Home history, transcript detail,
Memories, real chat send/SSE reply, live Home capture, episode, device sync, and
tab switches. Their providers/HTTP clients/pages remain production code; only
external services and hardware are faked. Existing dataset environment overrides
are for exploration and must not be used to produce an admission baseline.
Tighten budgets only with repeated measured optimization evidence; never raise
a cap or weaken data/interaction to conceal a regression.

## Mutation proof

```bash
PERF_GATE_REPEATS=1 PERF_GATE_MUTATION=held_semantics bash app/tool/perf_gate.sh
```

This mounts a test-only app-wide wrapper holding `ensureSemantics()` around the
same production shell. It must exit nonzero, with semantics state, compile-count
and phase-share violations. Production tracker files are never mutated. Unit
checks also exercise extra wrapper rebuilds, empty evidence, and arbitrary host
wall-clock inflation. A clean checkout must pass three consecutive full runs;
record observed false failures and denominator, not a claimed universal rate.

## Real-device profile route

A profile build on a physical device is required for wall-clock/raster truth.
The existing `test_driver/integration_test_driver.dart` preserves `reportData`
on failures, but the seeded host scenarios use debug-only fixture credential
trust and must not be advertised as profile-ready. The device prototype and
current access/credential asks are maintained in the dedicated device-route PR.
Never use iOS simulator timing as profile evidence.
