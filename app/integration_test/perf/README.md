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

## Hill-climb contract

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
