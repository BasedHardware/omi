# Mobile UI performance admission (INV-PERF-1)

For the synthetic 6,500-WAL / 2,000-conversation integration benchmark and its
physical-profile versus simulator-debug limits, see [HEAVY_PROFILE.md](HEAVY_PROFILE.md).

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

`perf_shell.py --check` rejects stale output. It fingerprints only the
extracted shell — the copied imports, the telemetry field, and the builder
chain — and refuses unknown root wrapper shapes, so a wrapper added anywhere
around the builder cannot silently evade the test while unrelated main.dart
edits stay green. Regenerate after a deliberate shell change, review the new
wrappers, and rerun the gate. The preferred future
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
relaxations of existing timing caps. After merging main, device_page was
re-baselined on the same formula: #23494's never-set-clock catch-up rendering
is what the fixture's `timerStart: 1` WALs legitimately exercise (3869
rebuilds / 2405 layouts, deterministic), so its caps follow that baseline.

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

## Legacy budget provenance

The following original Stage 1 contract explains the historical numeric time
budgets retained in budgets.json; current host admission is defined above.

Keep scenario behavior, data sizes, sampling, and measurement definitions
fixed while optimizing production code in later stages. Compare all four
scenarios and their rebuild/animation evidence. Tighten budgets only after an
accepted optimization win demonstrated across repeated comparable runs; do
not raise budgets or weaken the interaction to hide a regression. The initial
100 ms p90 budgets are generous bootstrap gates, not a 60 fps quality claim.
Stage 1 neither changes production code nor publishes changes.

## Physical-device profile prototype (2026-10-23)

**Status: dry-run prototype; no physical run or product performance acceptance.**
Use a real Android/iOS phone in profile mode for device measurements. Flutter
explains why debug/host/simulator timing differs from release behavior in its
[profiling guide](https://docs.flutter.dev/perf/ui-performance) and documents
[`flutter drive --profile`](https://docs.flutter.dev/cookbook/testing/integration/profiling).
This device section is independent of the host harness above.

### What can actually run in profile

`perf_main.dart` remains the host/debug seeded scenario entry. It imports
`journeys/support/hermetic_boot.dart`, which installs a synthetic singleton
token gateway and arms debug-only credential trust. The gateway installation's
assertions disappear in profile, but `Env.debugTrustedFixtureAuthority` still
requires `kDebugMode`, so profile never arms that trust. Do not remove those
security guards to make a benchmark pass. The harness also indexes source files
and reads its budgets from checkout paths, which a device app cannot assume.
Changing `--profile` alone does not make the seeded scenarios supported.

`device_smoke_main.dart` is a separate profile-safe shell smoke: a standalone
MaterialApp scrolls deterministic rows, captures engine `FrameTiming` build,
raster and total durations, and returns them through the existing
`test_driver/integration_test_driver.dart`. It imports no Omi app bootstrap,
production shell, auth, network client, providers or fixture backend. It does not
write host paths from the device. This proves only engine sampling and driver
transport once run. It does **not** measure Home/detail/Memories/chat, production
builder overhead, or satisfy a product performance gate. No budget is inferred
from this synthetic list.

To port the full scenarios later: provide a reviewed profile-safe fixture/auth
boundary without weakening production trust, package budgets without host file
reads, replace source indexing with bundled/static hints, and wire the parent's
source-derived production shell after it lands. Those changes are prerequisites,
not implemented or claimed by this prototype.

### Plan now; execute only on a specifically approved device

Inventory is read-only. Keep local inventories, plans, reports and logs outside
Git, preferably on the scratch volume. From `app/`, on the device's host:

```bash
flutter devices --machine > /Volumes/Ephemeral/scratch/perf-devices.json
python3 tool/perf_device.py plan \
  --inventory /Volumes/Ephemeral/scratch/perf-devices.json \
  --device-id '<exact physical ID from inventory>' \
  --output-dir /Volumes/Ephemeral/scratch/perf-device-run-001 \
  --plan-file /Volumes/Ephemeral/scratch/perf-device-plan-001.json
```

`plan` never starts a subprocess or accesses a device. It requires one exact
supported physical mobile entry (`emulator: false`), profile mode and the
`dev/local_dev` pair, refuses seeded mode and existing output directories, and
prints the exact validator + Flutter command with a unique run ID. The printed
validator checks the prepared `.dev.env` before any future build. Prepare this
lane's dependencies and supported dev environment through the documented setup
first; iOS needs the existing development signing/provisioning for this phone.
Native project/plugin build feasibility has not been tested here.

**Stop before copying the printed command into a shell.** David must name the
host and device and approve installing/replacing the dev app and launching this
smoke. Refresh inventory immediately before that approved run. No access is
implied by an inventory entry or a saved plan. The script intentionally has no
`run` action. Run IDs and hashes detect accidental stale/mismatched artifacts;
they are not device attestations or proof of approval.

After a separately approved execution, preserve its log and actual exit code.
The driver writes `integration_response_data.json` into the unique output
directory via `OMI_PERF_DEVICE_OUTPUT_DIR` (otherwise its normal default applies).
Collect offline; pass the actual Flutter exit code, including failures:

```bash
python3 tool/perf_device.py collect \
  --plan-file /Volumes/Ephemeral/scratch/perf-device-plan-001.json \
  --drive-exit-code '<actual flutter drive exit code>' \
  --output /Volumes/Ephemeral/scratch/perf-device-collected-001.json
nice -n 10 python3 -m unittest discover -s tool -p test_perf_device.py -v
```

Collection requires exit 0, the matching run ID/platform, profile metadata,
completion, and at least ten finite engine samples with nonzero raster work.
Host scorecards, debug results and failed/incomplete runs cannot become successful
device smoke evidence. Failed driver responses remain available for diagnosis.
The tool creates output files exclusively, preserving earlier evidence.

### Availability and cheapest route

Read-only observation on **2026-10-23, 14:40–14:49 UTC**; availability can change:

| Route | Observed availability / prerequisite | Estimated incremental vendor cost |
| --- | --- | --- |
| USB fleet phone (preferred) | m5 Xcode lists David's iPhone 15 Pro Max / iOS 27.0.1 unavailable, deviceprep -27 (browsing; unlock/cable required). m1 Studio and m4 mini Xcode inventories contain only their Macs. Local ADB lists no device. m4 Air is offline; its USB inventory is unknown. | $0 for existing hardware and local builds, excluding electricity/operator time. |
| Firebase Test Lab physical Android/iOS | Both platforms supported. `ro-dev` catalog read returned 403 `Not authorized for project based-hardware-dev`; no current model/capacity is claimed. Native instrumentation/XCTest packaging and report export need qualification; this local VM-service driver cannot simply attach to a cloud device. | Spark: 5 physical runs/day. Blaze: first 30 physical minutes/day free, then $5/device-hour rounded up per minute. Example: 5 billable device-minutes ≈ $0.42, 10 ≈ $0.83, before any storage/build costs. Remaining project allowance unknown. |
| Codemagic + Test Lab | Build runner plus external device service; no independent physical-phone availability verified. Needs approved existing project/auth and the same native test packaging. No workflow was changed or submitted. | Listed M2 $0.095/min, M4 $0.114/min, Linux X2 $0.045/min, plus Test Lab. Example: 10 M2 build minutes + 5 billable physical minutes ≈ $1.37; Android Linux equivalent ≈ $0.87. Existing plan allowance unknown. |

Pricing and support sources checked 2026-10-23:
[Test Lab pricing](https://firebase.google.com/docs/test-lab/usage-quotas-pricing),
[iOS catalog](https://firebase.google.com/docs/test-lab/ios/available-testing-devices),
[Android catalog](https://firebase.google.com/docs/test-lab/android/available-testing-devices),
[Flutter Test Lab packaging](https://docs.flutter.dev/testing/integration-tests),
[Codemagic pricing](https://codemagic.io/pricing/), and
[Codemagic Test Lab integration](https://docs.codemagic.io/yaml-testing/firebase-test-lab/).
The documented Android cloud example uses debug APKs; it establishes test
packaging, not profile performance support. A profile/native-runner export path
must be qualified separately before paying for a cloud profile run. Catalog
capacity is an aggregate, not a reservation or immediate queue guarantee.

**Ask for David:** nominate a dedicated USB test phone and its fleet host, connect
and unlock/trust it, enable Developer Mode where needed, and specifically approve
the dev-app install/launch for this standalone probe. Recommend a dedicated test
role rather than silently treating his personal phone as a test fixture. If USB
is unavailable, name the approved Test Lab project, approved agent authentication
route and spending cap before a submission; credential/IAM changes each need
their own approval. Do not paste credentials into chat. This lane used only
GCP `ro-dev` for a catalog request; no production data/API calls, cloud test
submissions, device installs, builds or launches occurred.
