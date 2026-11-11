# Physical microphone and wearable traces → offline replay

Build a small, separately signed **Omi Mic Probe** app from the current
production `PhoneMicController`, engine, converter, permission gate, session
configurator, and interruption monitor. It runs optimized native code without
a debugger or Flutter. The replacement sink counts and immediately discards
PCM. It has no backend, account, network client, or audio-file writer.

This measures the **native streaming microphone layer**. It does not qualify
Flutter/Pigeon delivery, WAL, batch encoding, upload, BLE, battery life, or the
shipped app's interaction with other plugins. The probe wires production
streaming dependencies through the existing controller seams; it does not
compile the Flutter-dependent host adapter. OS notifications are real on the
phone; policy replay on a Mac substitutes OS I/O and synthetic silence.
The separate wearable test below measures CoreBluetooth packet delivery and
reconnection, with a replay into the production Dart transport seam.

Agents without a phone or signing credentials can compile the complete native
probe with the iPhone SDK using `python3 app/ios/test/phone_mic_probe/build.py --check`.
The macOS check manifest runs this compile check; it does not qualify runtime
startup or hardware behavior.

## Build and use an authorized phone

Prerequisites: Xcode/iPhone SDK, a paired unlocked iPhone with Developer Mode,
and an authorized development certificate/profile covering the probe bundle.
The build script checks that the supplied profile is a development profile and
covers the separate bundle ID. Device inclusion, certificate validity, and
installation are also enforced by code signing/iOS. It never provisions,
registers, leases, installs, or launches a device automatically.

For unattended qualification use the dedicated-device ownership rules in
[`PHYSICAL_DEVICES.md`](../../../../scripts/dev-harness/PHYSICAL_DEVICES.md).
An explicitly authorized, operator-assisted session on a borrowed personal
phone can use this separate probe without declaring the phone dedicated or
registering it for future agents. Authorization applies to the active session;
future agents must obtain access again. In an authorized active session, launch
arguments can start bounded runs automatically.
Do not register a borrowed phone with `--confirm-test-device`.

From the repository root, use a fresh output directory outside Git:

```bash
python3 app/ios/test/phone_mic_probe/build.py \
  --output /absolute/path/to/probe-build \
  --profile /absolute/path/to/authorized.mobileprovision \
  --identity '<authorized Apple Development identity>'

xcrun devicectl device install app --device '<authorized UDID>' \
  /absolute/path/to/probe-build/OmiMicProbe.app --timeout 30
xcrun devicectl device process launch --device '<authorized UDID>' \
  com.friend-app-with-wearable.ios12.development.micprobe --timeout 20
```

Before asking the operator to record, copy `Documents/startup.json` and check
that its build matches the selected artifact and its timestamp follows launch.
It is written after the probe's scene becomes active. Check that the process
remains alive and, when available, capture the probe screen. A successful
`devicectl process launch` alone is insufficient: the initial probe crashed
immediately on iOS 27 with
`UIApplicationEvaluateRuntimeIssueForNoSceneLifecycleAdoption`. The probe now
uses `UIWindowSceneDelegate` and declares its scene configuration.

Tap **Start 60-second run**, allow microphone access, wait for the frame count
to increase, lock for at least 15 seconds, then unlock and return to the app
before the 60-second automatic stop. Wait for **Run saved**. Stop now ends
capture early. A run under 10 seconds does not pass the start/stop check.
Each run saves a distinct `Documents/probe-<uuid>.json`. The two-second
post-stop observation checks for terminal-frame leakage. A killed/suspended
probe without completed evidence remains incomplete.

For a separate interruption experiment, start another run and use a real OS
audio interruption. The analyzer requires every observed begin to enter
`interrupted`, then observe an end, return to `running`, and deliver new frames
within five seconds. Require `interruption_recovery` explicitly. A competing
audio session that causes no interruption signal remains `not-observed`.
No interruption is synthesized inside this probe.

## Collect and check evidence

Create the host destination first: `devicectl copy from` requires an existing
destination directory on the Xcode version used for the first device run.
Copy only this probe's container, not whole-device logs or personal app data.

```bash
mkdir -p /absolute/path/to/probe-evidence
xcrun devicectl device copy from --device '<authorized UDID>' \
  --domain-type appDataContainer \
  --domain-identifier com.friend-app-with-wearable.ios12.development.micprobe \
  --source Documents --destination /absolute/path/to/probe-evidence --timeout 20

python3 app/ios/test/phone_mic_probe/analyze.py /absolute/path/to/probe-<uuid>.json \
  --build /absolute/path/to/probe-build/OmiMicProbe.app/build.json \
  --require start_stop --require background_capture --require foreground_recovery
```

The selected build manifest must exactly match the trace. It embeds hashes of
all compiled production/probe source files, generated Pigeon input, build
script, source Git SHA, Xcode version, and **unsigned** executable hash. Code
signing subsequently changes executable bytes; that field is not a signed
artifact hash. Keep the signed `.app` and install/launch command results next
to the trace for physical provenance. The embedded manifest is attribution,
not independent proof that the submitted JSON came from a real phone.
New signed builds also write `signed-artifact.json` beside the app with hashes
of its signed files and the complete file tree.

The analyzer exits 0 only when every required check passes, 1 on a failed
required check, and 2 for missing/incomplete/invalid evidence. Background
acceptance requires a continuous segment of at least 10 seconds, increasing
frame/byte counts, and sample spacing no greater than 2.5 seconds. Returning
to the foreground must produce frames within 5 seconds of the last background
sample. This is sampled continuity, not proof of zero audio loss. Missing
scenarios remain `not-observed`. Keep traces/artifacts outside Git.

## Replay without an iPhone

First run the analyzer above against the retained build. Then:

```bash
OMI_PHONE_MIC_DEVICE_TRACE=/absolute/path/to/probe-<uuid>.json \
  ruby app/ios/test/phone_mic_lifecycle_replay_test.rb
```

The `ios-phone-mic-lifecycle-replay` manifest check selects this native suite
on macOS for microphone/probe changes. The native test command runs all eight
canonical vectors and
always exercises synthetic foreground-return, interruption (both resume flags),
and permission-denial/restoration sequences. The optional
trace adds the observed lifecycle input order to the same production
controller with fake OS I/O and synthetic PCM. It checks that returning to the
foreground preserves a healthy engine, frame delivery continues, observed
state ordering matches, and stale frames are dropped after stop. Time is
compressed; this is **controller policy regression coverage**, not another
physical test. It rejects unimplemented signal types instead of omitting them.

When a real trace reveals a new failure, add its minimal sanitized scenario
and a reviewed assertion to the existing replay harness. Make the regression
fail against the old production policy before fixing it. Do not automatically
bless observed output as correct or label synthetic traces device evidence.

Offline analyzer/discovery mutation tests are included in:

```bash
bash scripts/dev-harness/run-tests.sh
```

After the session, stop the probe. Its recordings contain only metadata;
remove the separately named app when the user is done with further runs.
Never uninstall/reset the user's Omi app as part of probe cleanup.

## Additional acoustic and wearable checks

New microphone runs include aggregate PCM sample count, square sum, and peak
amplitude, without retaining samples. Add `--require non_silent_pcm` to the
microphone analyzer after speaking during a run. It requires overall RMS above
-60 dBFS and peak above 100 PCM16 units. This distinguishes a working signal
from silent buffers; it does not prove speech intelligibility, codec accuracy,
or acoustic quality. Old traces lacking these measurements remain unqualified
for this check.

The **Start wearable reconnect test** button runs a separate CoreBluetooth
radio observer. Select only your own Omi from the discovered candidates. Its
service/characteristic UUIDs are extracted from the production Dart device
constants during build. It subscribes to the audio characteristic, counts and
discards notifications, and records callback order and connection generations.
It sends no firmware/storage commands, and records no peripheral names/IDs or
audio payloads. It does not use the shipping OmiBleManager, so it measures the
OS/radio callback contract rather than that manager's reconnect policy.

Once packets arrive, power the selected wearable off for about five seconds,
then on. Wait for packets to resume and stop the test. The probe requests a
new connection after an unexpected disconnect, rediscovers the audio service,
and resubscribes. Its own connection is canceled when the test ends. The run
automatically ends after 90 seconds, including discovery. Disconnecting a
wearable can also interrupt its connection to the user's ordinary Omi app;
do this only in an explicitly authorized active test session.

Collect `Documents/wearable-<uuid>.json` using the same scoped copy command.
Then run:

```bash
python3 app/ios/test/phone_mic_probe/analyze_wearable.py /absolute/path/to/wearable-<uuid>.json \
  --build /absolute/path/to/probe-build/OmiMicProbe.app/build.json

# From app/, after the radio analyzer passes:
OMI_BLE_RADIO_TRACE=/absolute/path/to/wearable-<uuid>.json \
  flutter test test/unit/wearable_radio_trace_replay_test.dart
```

The analyzer requires initial and reconnected links to deliver more than one
packet, with initial audio within ten seconds of connection. It permits the
first payload and notification-confirmation callback to arrive in either
order after the subscription request. Every observed unexpected disconnect
must recover; one early success cannot hide a final failed reconnect.
Background packet delivery is a separate optional result.

The Dart test projects service readiness, disconnects, and packet arrivals
onto the **production NativeBleTransport and BleBridge**, with a fake native
host API and synthetic payloads. It checks that the original stream listener
survives and each connection restores its subscription. It always runs a
synthetic reconnect scenario in the ordinary unit suite; the environment
variable adds the retained physical sequence. This does not replay
CoreBluetooth, OmiBleManager, Opus, storage/upload, or full-app behavior.

The ordinary suite also retains a reviewed, reduced callback sequence from the
2026-09-22 iOS 27 run: both links delivered their first payload before the
subscription confirmation, and the original Dart listener survived reconnect.
That scenario contains no device identity or audio and is regression input,
not independent physical acceptance evidence.

## Bounded automation, permission recovery, and resource baseline

After authorization, append these arguments to a device launch (after the
bundle identifier) to avoid a Start tap:

```text
--probe-mode mic --probe-duration 90
--probe-mode mic --probe-duration 300
--probe-mode wearable --probe-duration 15
--probe-open-settings
```

A 300-second mic run prevents automatic screen lock and restores the prior
idle-timer setting when stopped; the operator can still lock explicitly.
Durations must be 10–300 seconds; invalid arguments start no test. The settings
flag must appear alone and opens only this probe's iOS Settings page. It does
not toggle permissions. Each launch starts at most one run. Stop/relaunch the
probe between plans; foregrounding an already-running process is not a new
plan. Verify a fresh `startup.json` and matching build before relying on a run.
Wearable runs still require selecting the user's own device; no nearby device
is selected automatically. Their timer now includes discovery/permission wait.

For an authorized session, the separate [permission UI runner](../phone_probe_ui/README.md)
can open this probe's Settings page and verify its Microphone/Bluetooth toggles.
It targets only the probe. A passing switch assertion is not a capture result;
collect and analyze the denied and restored runs separately, and restore both
grants before ending the session. The remaining manual step for wearable runs
is selecting the user's own device.

A compact operator session can handle any OS actions automation cannot perform:

1. Disable Microphone and Bluetooth for **Omi Mic Probe** in its Settings page.
   Run the mic attempt, then a 15-second wearable attempt. Save both completed
   denied receipts before changing permissions. Mic denial completes after its
   two-second quiet observation; BLE denial records authorization `denied`.
2. Restore both permissions and relaunch the mic plan. Speak briefly, cause
   the authorized real audio interruption, and let capture recover. For a
   continuous baseline use a separate uninterrupted 300-second mic run.
3. Launch the restored wearable test, select the user's wearable once, and
   wait for ongoing audio packets. Allow the bounded run to finish.

Changing permissions in Settings may kill the app. Therefore restoration is
qualified using **two different, chronologically ordered receipts from exactly
the same build**, not by assuming an interrupted process remained alive:

```bash
python3 app/ios/test/phone_mic_probe/analyze.py /evidence/mic-granted.json \
  --build /artifact/OmiMicProbe.app/build.json \
  --permission-before /evidence/mic-denied.json --require permission_recovery
python3 app/ios/test/phone_mic_probe/analyze_wearable.py /evidence/ble-granted.json \
  --build /artifact/OmiMicProbe.app/build.json \
  --permission-before /evidence/ble-denied.json --require permission_recovery
OMI_PHONE_MIC_PERMISSION_BEFORE=/evidence/mic-denied.json \
OMI_PHONE_MIC_DEVICE_TRACE=/evidence/mic-granted.json \
  ruby app/ios/test/phone_mic_lifecycle_replay_test.rb
```

`permission_denial` is separately selectable on either analyzer. It requires
observed denied authorization, zero audio, and a completed attempt; missing
consent events never pass. Restoration requires actual granted permission and
continued successful delivery. This is probe permission behavior, not the
shipping app's permission UX. The native replay covers the production
controller's denied and restored start policy with synthetic audio; Settings
and CoreBluetooth permission changes are not replayed on the Mac.

Each one-second sample records resident bytes, cumulative process CPU seconds,
and maximum inter-callback gap during that interval. Microphone traces also
retain the all-run maximum frame gap; wearable traces retain the all-run
maximum packet gap. Audio remains aggregate-only and is discarded immediately.
For an uninterrupted five-minute mic run, add `--require sustained_capture`.
Acceptance requires at least 295 seconds from successful start to stop request,
at least 290 seconds of resource samples, increasing frames/bytes each sample,
and sample/callback gaps no greater than 2.5 seconds. Early stop, suspension,
missing resource samples, and missing final observation cannot pass.

The report gives sampled resident first/last/max bytes, average CPU as a percent
of one core, and maximum observed callback gap. These include probe measurement
and JSON-write overhead, and establish a hardware baseline without inventing
a shipping-app resource budget. Sampling does not prove zero audio loss or
measure OS scheduling exactly. USB-attached runs make **no battery-life claim**.
