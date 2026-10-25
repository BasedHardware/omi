# Physical-device performance runs

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

The runner enters an Aqua iTerm session for signing and VM discovery. iTerm
needs macOS Local Network permission, and the DEV app needs the phone's local
network permission. The caller waits for the owned worker and its terminal
result. Interrupting the caller cancels the worker's process group. A killed
headless caller is also observed by the Aqua worker. Only one benchmark may own
this worktree's build output at a time.

`omi-heavy` supplies the concurrency gate and `nice -n 19` priority. The GUI
waiter is the workspace's canonical `wait_for.sh`, resolved from
`OMI_ROLLOUT_BIN` or `OMI_WORKSPACE_ROOT/infra/rollout/bin`. On a relocated host,
set `OMI_HEAVY_BIN` and `OMI_PERF_WAITER` explicitly. If the GUI waiter is not
installed, run the command directly in Aqua iTerm. No signing identities, key
ACLs, production build settings, schedulers or permissions are changed by it.

## Receipts and comparison

Artifacts go to `OMI_PERF_ARTIFACT_ROOT`, or `mobile-heavy-profile` on the mounted
scratch volume. `--out <new-directory>` selects one batch. Existing nonempty
directories are refused. `--dry-run` prints the plan without building or
installing. Logs and failures remain alongside successful receipts.

Each frame receipt includes per-flow build/raster/total p50/p90/p99, counts over
16/32/100 ms, worst frame, nonempty-frame checks and exact measurement windows.
The gate requires three identical-binary runs and `(max p90 - min p90)/min p90`
at most 15% for **every** build/raster/total p90. A failed batch remains failed;
never discard one run, reduce the heavy fixture, or raise the limit to pass.

`--accept-baseline` updates `last-accepted-baseline.json` only for a qualifying
profile batch. Prior pointers are archived, and receipts are never removed.
Without that flag, a new run compares with the last accepted reference and
writes `comparison.json`; it never silently replaces it. `--baseline <dir>`
pins a particular reference. Comparison requires the same device, Flutter
revision, fixture, frame policy and harness hash. A changed measurement
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
| `errSecInternalComponent` from codesign | Check `launchctl managername`. A Background session cannot use the GUI keychain like Aqua. Launch through approved iTerm; allow an actual owner-approved signing prompt. Preserve the existing identity/team. Never switch to ad-hoc signing or alter key ACLs. |
| UDP 5353 `No route to host`, VM service not discovered | Check the launching app's Local Network permission. On the qualification host, Terminal was absent from the permission list while iTerm was granted. Use iTerm. USB log discovery sometimes recovers after 2–3 minutes; the warning itself is not a result. Each driver launch is capped at 14 minutes. |
| iTerm AppleScript times out before a worker PID appears | The runner opens an owned local `.command` file with iTerm as a fallback. An atomic claim prevents a delayed AppleEvent and fallback from starting two device jobs or overwriting each other's result. No TCC setting is changed. If neither launch acknowledges, stop and inspect the recorded launch rather than starting another unowned job. |
| iOS simulator profile build refused | Flutter 3.44.5 forbids AOT profile/release on iOS simulators. Use physical iOS for acceptance. The lower runner's `--simulator-qualification` is debug only, with invocation-only simulator overrides. |
| Heavy slot seems occupied forever | Inspect ownership and liveness with the workspace/host tools. An orphan Android emulator once retained a slot after its owner died. CPU/RSS alone is not permission to kill it. Ask its owner/lead before stopping it; never reset shared locks or kill another lane. |
| Home missing a provider / ServiceManager not initialized | Compose the existing production shell once, with real Conversation/Sync/LocalRecordings/People providers and the WAL ledger. Supply inert Device/PhoneCall/native boundaries explicitly. Do not initialize real hardware/account services to make a synthetic fixture pass. |
| Global navigator key already attached | Do not mount two production shells. Restore cache through the one Home mount. |
| Transcript finder has no scroll extent | Open the Transcript tab and wait for mounted content. `fadePointers` does not drive real-device frames reliably for this benchmark. Use `benchmarkLive`; `fullyLive` can include artificial pump frames. |
| Trace contains only the last flow | The VM ring buffer overwrote earlier events. Use streamed capture and require all task boundaries. Do not derive CPU bounds from the last remaining trace event or rank receipt serialization as app work. |
| Variance exceeds 15% | Preserve the whole failed batch. Check fixed pacing, fixture identity, device/refresh rate, thermal/power state, background activity, VM discovery, and tracing mode. `pumpAndSettle` can vary with endless production tickers; the harness uses fixed real-time pacing. Do not tune thresholds after seeing results. |
| Giant CPU receipt | The VM may return its entire AOT function table, including unused entries. Keep sampled stacks and their referenced functions; do not attribute unused functions or post-run serialization to the measured flows. |
| App says tests passed but transport failed | Require the driver receipt and the host variance result as well. Test output, artifact identity and acceptance are separate checks. |
| Scenario assertions pass but engine frame count is zero | One qualification run lost frame callbacks for three flows; native foreground loss was suspected, not proven. Reset only the exact DEV bundle before each attempt and activate it before the scenario handshake. Require resumed state and nonempty frames. Only tagged foreground/no-frame failures retry, at most twice. Every rejected attempt remains under `attempts/`; valid slow runs and variance failures never retry. |

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
