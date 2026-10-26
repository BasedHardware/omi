# Physical-device performance runs

## Virtual qualification without a personal phone

Use a dedicated, synthetic Android emulator with an explicitly pinned system
image. iOS simulator profile/release is unsupported by Flutter3.44.5; its debug
path qualifies scenarios only. Neither path can replace physical-device release
acceptance. From the repository root, with the selected emulator already booted:

```bash
bin/omi-heavy run -- nice -n 19 bash app/tool/perf_sim_profile.sh \
  --platform android --device emulator-5580 --emulator-qualification \
  --runtime-build '<exact ro.build.fingerprint>' --warmup-runs 1 --runs 3 \
  --out /Volumes/Ephemeral/scratch/mobile-perf/baseline
```

Resolve `bin/omi-heavy` from the workspace when outside it. Admission verifies
the explicit emulator serial, native emulator property, runtime fingerprint,
display size/density and model before compilation and every launch. Virtual
identity also binds the host-name hash, host OS/architecture and logical CPU
count; reusing the same emulator serial/image on another host cannot qualify a
comparison. Host names themselves are not exported. For iOS,
use `--simulator-qualification --device <booted-simulator-UDID>` and pin the
runtime's `buildversion` with `--runtime-build`; it remains debug-only.

Every virtual batch requires 1–3 complete warmup launches retained as
`warmup-N.json`, followed by at least three measured launches of the same
binary. Warmup warms persistent shader/assets; it does not remove per-process
JIT costs from iOS debug. Measured cold Home still restores the full cache in
a fresh process. Cold here never means a fresh installation or native app boot.
The fixture, real-time action sequence and 30-second launch interval are fixed.
Keep the same emulator version, GPU backend, display/refresh rate and host
conditions for a pair; runtime/image pins cannot remove host scheduling noise.
Per-launch receipts record host load and CPU count separately from comparison
identity. The Android heavy target alone uses a devProfile manifest overlay to
remove native Firebase eager initialization; ordinary app targets retain it.
An APK inspection checks DEV identity and the initializer's absence before any
installation. This covers native startup that Dart's HTTP override cannot block
([Firebase initialization](https://firebase.google.com/docs/reference/android/com/google/firebase/FirebaseApp)).

Virtual launches require load1 no greater than the logical CPU count, fixed
before measurement. `host_load.py` retains samples before, every second during,
and after each launch. An overload before launch prevents it; an overload during
launch lets it complete and retains its output, then invalidates the entire
batch without retry. Every warmup and measured launch needs passing host-load
evidence before the report can qualify a virtual baseline.

All measured runs participate in the unchanged 15% p90 spread gate. Slow runs
and frames are retained, including first exposure in warmup. No statistical
outlier is silently dropped. A passing profile emulator batch is marked
`qualified_virtual_baseline`; `accepted_baseline` remains false, and the
physical baseline pointer cannot be updated from virtual results. The comparison
tool accepts an explicit qualified virtual reference only with matching runtime
and launch protocol. iOS debug cannot qualify a profile reference.

Frame percentiles use nearest rank (`ceil(n*p)-1`), retaining the worst frame
for both six and seven sparse cold samples. The earlier rounded `(n-1)*p`
method changed rank between those counts. This is a protocol change requiring
a new baseline; older failed batches remain failed. Sparse cold percentiles
still have low statistical power: inspect frame count, worst frame and cold
cache-ready operation time together. Each receipt now includes raw frame phase
times and monotonic action markers for detail pushes/pops, flings and tab taps.
Trace export remains a separate diagnostic with its overhead labeled.

**Rule 1: never uninstall.** Flutter3.44.5 `flutter drive` stops and uninstalls
the app by default. An earlier qualification attempt exposed the DEV sandbox
to that cleanup; pre-existing DEV data could not be ruled out. Every invocation
must use `--keep-app-running`. The command guard rejects missing/conflicting
flags, non-DEV flavors and uninstall-first before spawning. Do not bypass it.
Only the still-connected, VM-attested harness process may exit; keep its
app/data. After tests and teardown complete, an authenticated test-only RPC
asks that same PID/isolate to exit itself on every platform. No external
PID/package kill is issued. This also lets Android's next run pass idle
admission despite keep-app-running. The acknowledgement is separate from the
synthetic canary's evidence of installation/data retention.
Each completed physical iOS attempt must read back a unique synthetic preservation canary
written by this run. Never enumerate or read existing app data. Missing canary
proof stops the batch, including after failed attempts. Cancellation may stop
before that check; such an attempt is never a receipt and needs an explicit
owner-approved check later. Android retention still
needs qualification on the dedicated hardware.

Run from a prepared product task worktree on a fleet Mac:

```bash
bash app/tool/perf_device_run.sh --accept-baseline
```

This discovers exactly one connected supported physical iPhone, builds only the
DEV flavor, installs it, and performs three launches of one profile binary over
the same synthetic heavy fixture. Installation requires the device owner's
approval; device detection does not grant permission. Use `--device <UDID>` if
there are multiple phones. Keep the approved phone connected, unlocked and
awake; restore its Auto-Lock setting when releasing the device. Never use a
production account or the production app for this benchmark.

The runner enters an Aqua Terminal session for signing and VM discovery. The
launching app needs macOS Local Network permission or USB discovery fallback.
The caller waits for the owned worker and its terminal
result. Interrupting the caller cancels the worker's process group. A killed
headless caller is also observed by the Aqua worker. Only one benchmark may own
this worktree's build output at a time.

USB runs explicitly disable VM-port publication (`--no-publish-port`). The SDK documents this
as avoiding the iOS Local Network dialog. VM service authentication remains
enabled. This changes no TCC setting and does not dismiss a permission prompt.

Use `--aqua-app iTerm` when that route is approved and configured. iTerm needs Automation permission
for the controlling app; Terminal needs Local Network permission or accepts a
2–3 minute USB discovery fallback per launch. Choose only an owner-approved
route. The runner records the actual Aqua session and changes no permissions.

`omi-heavy` supplies the concurrency gate and `nice -n 19` priority. The GUI
waiter is the workspace's canonical `wait_for.sh`, resolved from
`OMI_ROLLOUT_BIN` or `OMI_WORKSPACE_ROOT/infra/rollout/bin`. On a relocated host,
set `OMI_HEAVY_BIN` and `OMI_PERF_WAITER` explicitly. If the GUI waiter is not
installed, run the command directly in the approved Aqua terminal. No signing identities, key
ACLs, production build settings, schedulers or permissions are changed by it.

## Receipts and comparison

Artifacts go to `OMI_PERF_ARTIFACT_ROOT`, or `mobile-heavy-profile` on the mounted
scratch volume. `--out <new-directory>` selects one batch. Existing nonempty
directories are refused. `--dry-run` prints the plan without building or
installing. Logs and failures remain alongside successful receipts.

Reserve an idle device with its owner. Before installation and each launch,
the physical iOS runner checks the exact DEV installation URL against native
process metadata; Android checks the DEV package PID. A running main process,
a failed query, or incomplete metadata blocks the operation. Known DEV
`PlugIns/<name>.appex/<name>` extension processes are recorded separately without blocking
admission or being terminated. Unclassified DEV executables still block. It never
force-stops an unowned app. These are point-in-time checks: the owner must keep
the device idle for the batch. Only the VM-attested harness PID may be stopped.

Fixtures use an owned `omi-heavy-perf-fixtures-v1` temporary namespace and an
append-only allocation ledger, capped at 24 allocations per installation/cache
namespace. A reservation remains consumed after a crash; the runner deletes no
WAL/audio. At the normal fixture shape, 24 allocations are roughly half a GB
plus indexes. On exhaustion or an unreadable ledger, stop and ask the owner;
never increase the cap to hide accumulation or delete files to make a run pass.
Earlier qualification directories predate this ledger and remain retained.

Each frame receipt includes per-flow build/raster/total p50/p90/p99, counts over
16/32/100 ms, worst frame, nonempty-frame checks and exact measurement windows.
The gate requires three identical-binary runs and `(max p90 - min p90)/min p90`
at most 15% for **every** build/raster/total p90. A failed batch remains failed;
never discard one run, reduce the heavy fixture, or raise the limit to pass.

`--accept-baseline` updates `last-accepted-baseline.json` only for a qualifying
profile batch. Prior pointers are archived, and receipts are never removed.
Without that flag, a new run compares with the last accepted reference and
writes `comparison.json`; it never silently replaces it. `--baseline <dir>`
pins a particular reference. Comparison requires the same device, runtime OS,
Flutter revision, fixture, frame policy and harness hash. A changed measurement
protocol needs an explicitly qualified new baseline. Deltas are median p90s
across runs, worst frame and total jank counts; a variance failure remains
visible even when a median improves. Review comparisons before accepting a
replacement reference. This tool does not merge or release anything.

Opt-in attribution CPU samples use monotonic scenario bounds, excluding seeding and
receipt export. Unreferenced entries in the VM's enormous AOT function table
are removed and sample stacks are reindexed without dropping samples. Samples
measure sampled CPU work, not wall duration. They are not a substitute for
frame timing or a causal before/after experiment. The trace-free baseline does
not export the enormous AOT CPU table; runs have a fixed 30-second interval.

For a separate Dart DevTools attribution trace:

```bash
bash app/tool/perf_device_run.sh --timeline --runs 1
```

Import `receipt-1-timeline.json` into DevTools Performance. `heavy.<scenario>`
tasks delimit the flows. Trace events stream to the host to preserve early
flows. The stream has a bounded event budget and fails on truncation. Tracing
has material overhead: these runs are explicitly ineligible for frame baseline
acceptance and must not be substituted into a trace-free comparison.

The exact fixture, production-provider boundaries and field telemetry design
are documented in [HEAVY_PROFILE.md](../../integration_test/perf/HEAVY_PROFILE.md).
Cold start covers Home shell/cache initialization, not native process/Firebase
startup. Background/foreground is a logical lifecycle replay, not actual OS
suspension. The simulator debug path qualifies scenarios only; it is never an
accepted profile baseline.

## Troubleshooting

| Symptom | Evidence and action |
| --- | --- |
| DEV app disappears / fixture directory disappears after a run | Stop. Default flutter drive cleanup uninstalls the app even after test failure. Enforce Rule1 and --keep-app-running; validate synthetic canary survival on every attempt. Never assume a DEV flavor is disposable or that an owner has no data in it. |
| `errSecInternalComponent` from codesign | Check `launchctl managername`. A Background session cannot use the GUI keychain like Aqua. Launch through approved iTerm; allow an actual owner-approved signing prompt. Preserve the existing identity/team. Never switch to ad-hoc signing or alter key ACLs. |
| UDP 5353 `No route to host`, VM service not discovered | Check the launching app's Local Network permission. On the qualification host, Terminal was absent from the permission list while iTerm was granted. Use iTerm. USB log discovery sometimes recovers after 2–3 minutes; the warning itself is not a result. Each driver launch is capped at 14 minutes. |
| iTerm AppleScript times out before a worker PID appears | The controlling app may need Automation permission. A command-file fallback was tried during qualification and stopped at an iTerm modal open-file warning, so unattended command-file fallback is not used. An atomic claim and caller identity/expiry checks reject duplicate or stale delayed launches. Use the approved `--aqua-app Terminal` route, or arrange permission/modal handling with the owner. Never alter TCC or blindly dismiss a warning. |
| iOS simulator profile build refused | Flutter 3.44.5 forbids AOT profile/release on iOS simulators. Use physical iOS for acceptance. The lower runner's `--simulator-qualification` is debug only, with invocation-only simulator overrides. |
| Heavy slot seems occupied forever | Inspect ownership and liveness with the workspace/host tools. An orphan Android emulator once retained a slot after its owner died. CPU/RSS alone is not permission to kill it. Ask its owner/lead before stopping it; never reset shared locks or kill another lane. |
| DEV is idle before install but admission reports BatteryWidget afterward | iOS may launch the DEV widget extension after an in-place install. Main Runner PIDs must block admission; direct `PlugIns/<name>.appex/<name>` executables are recorded as `extension_pids` without blocking or being terminated. Nested helpers or mismatched executable names remain unclassified and block admission. Never treat an extension PID as permission to terminate another app or weaken unknown-metadata checks. |
| Home missing a provider / ServiceManager not initialized | Compose the existing production shell once, with real Conversation/Sync/LocalRecordings/People providers and the WAL ledger. Supply inert Device/PhoneCall/native boundaries explicitly. Do not initialize real hardware/account services to make a synthetic fixture pass. |
| Global navigator key already attached | Do not mount two production shells. Restore cache through the one Home mount. |
| Transcript finder has no scroll extent | Open the Transcript tab and wait for mounted content. `fadePointers` does not drive real-device frames reliably. `fullyLive` adds pump frames; benchmarkLive still requests idle frames in Flutter3.44.5. HeavyProfileBinding suppresses that tail request while forwarding genuine app requests, and a quiet-widget probe rejects artificial idle rendering. |
| Trace contains only the last flow | The VM ring buffer overwrote earlier events. Use streamed capture and require all task boundaries. Do not derive CPU bounds from the last remaining trace event or rank receipt serialization as app work. |
| Variance exceeds 15% | Preserve the whole failed batch. Check fixed pacing, fixture identity, device/refresh rate, thermal/power state, background activity, VM discovery, and tracing mode. `pumpAndSettle` can vary with endless production tickers; the harness uses fixed real-time pacing. Do not tune thresholds after seeing results. |
| Giant CPU receipt | The VM may return its entire AOT function table, including unused entries. Keep sampled stacks and their referenced functions; do not attribute unused functions or post-run serialization to the measured flows. |
| App says tests passed but transport failed | Require the driver receipt and the host variance result as well. Test output, artifact identity and acceptance are separate checks. |
| Scenario assertions pass but engine frame count is zero | One qualification run lost frame callbacks for three flows; native foreground loss was suspected, not proven. Start only when the exact DEV app is idle; never terminate an unowned app to retry. Activate the connected harness before the scenario handshake. Require resumed state and nonempty frames. Only tagged foreground/no-frame failures retry, at most twice. Every rejected attempt remains under `attempts/`; valid slow runs and variance failures never retry. |
| Native app-active getter and Flutter lifecycle both stay inactive | Stop after the bounded retries. A system alert is one possible cause, not a diagnosis. Do not invent resumed events, capture a personal device's screen, tap dialogs or alter permissions. Ask the owner to clear the blocker, then requalify. The overnight device run was paused on this evidence. |
| Runner is cancelled during startup | The attempted measurement has no acceptance receipt. Retain all artifacts and `preservation-canary-name.txt`; a cancelled attempt may lack its post-run canary check. Later owner-approved checks may read only that exact synthetic file, never enumerate the app container. |
| Foreground guard rejects a phone that is unlocked | Flutter's TestPlatformDispatcher starts with an empty initial lifecycle value. The harness reads the actual native buffered state once when binding state is null, then retains live lifecycle events as authoritative. It never invents a resumed event. Receipts record both values. Profile failure formatting can lose exception text, so retry reasons travel as structured reportData. |

## Android and an always-on nightly host

Use a dedicated Android phone with no production Omi account. Install the
documented Flutter/JDK/Android SDK versions on m4-mini, prepare a pinned product
worktree on scratch, enable USB debugging and approve that Mac's RSA prompt.
Keep USB connected, the phone powered, awake and thermally stable. Confirm
`adb -s <serial> get-state` reports `device`, then run:

```bash
bash app/tool/perf_device_run.sh --platform android --accept-baseline
```

Auto-detection refuses emulators and ambiguous/unauthorized devices. This path
still requires manual qualification on the purchased hardware; iOS results do
not qualify Android.

After a successful three-run device qualification, the host's existing
scheduler can run:

```bash
OMI_PERF_DEVICE='<dedicated adb serial>' \
OMI_PERF_ARTIFACT_ROOT="$SCRATCH_ROOT/mobile-heavy-nightly" \
  bash app/tool/perf_nightly.sh
```

The script uses a lock and a clean pinned checkout. It runs serially, preserves
all evidence, compares with the accepted reference, and leaves notification and
cadence to that scheduler. It never pulls, merges, deploys, signs in, installs a
scheduler, creates a GitHub workflow or automatically rebaselines.

## Field signal

The [watch-only dashboard/gate design](../../integration_test/perf/HEAVY_PROFILE.md#field-signal-design-watch-only)
groups `mobile_lag_stall` by surface, build and device class, with foreground
exposure and unknown/insufficient cohorts explicit. Current main only has local
diagnostic logs; aggregate transport and an exposure denominator are separate
prerequisites. This harness adds no fleet telemetry transport or rollout action.
