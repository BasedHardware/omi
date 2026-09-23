# Physical devices — leased qualification lane (SCA-491 / C5)

The physical-device lane of the mobile foundation. Everything here is
**fail-closed**: a device that is not registered as a dedicated test device
cannot be leased, an unleased device cannot be driven, and OS-level actions a
CLI cannot perform are surfaced as explicit operator steps — never faked, and
never reported as physical acceptance.

Software portions (lease state machine, device-runner adapter, native
Swift/Kotlin lifecycle replay of the `phone-mic-native-events/v1` vectors)
are hermetically tested and run in CI; **actual device qualification requires
provisioned hardware and stays pending real evidence**.

## Commands

Everything hangs off the canonical mobile session command:

```bash
make mobile-session ARGS="device doctor"                      # read-only readiness (exact remedies)
make mobile-session ARGS="device list"                        # registry + lease status
make mobile-session ARGS="device register --platform android --device-id <serial> \
  --label 'Pixel 8 (test)' --os-version 15 --confirm-test-device"
make mobile-session ARGS="device acquire --platform android --device-id <serial> \
  --purpose sca-491-qualification --session oms-<id> --wait-timeout 30"
make mobile-session ARGS="device run --session oms-<id> --platform android \
  --device-id <serial> --artifact app/build/app/outputs/flutter-apk/app-dev-debug.apk"
make mobile-session ARGS="device release --platform android --device-id <serial>"
```

Direct form: `scripts/dev-harness/mobile-session.sh device <op> …` (add
`--json` after `device` or after the subcommand — `device --json doctor` and
`device doctor --json` are equivalent — for machine-readable output).
`device doctor` exits 2 while anything is `operator-action-needed` or
`agent-remediable` — the message names the exact smallest step.

## Ownership model

- **Qualification registry**: only a device registered with
  `--confirm-test-device` (the explicit operator assertion that it is a
  dedicated test device, never a personal phone/watch) can be leased.
  Unregistered devices are refused with the registration command to run.
- **Exclusive lease** (`device-lease/v1`): one lease per device, claimed
  atomically. Owner = host + user + pid; `generation` bumps on every recovery.
- **Never steal**: a live foreign lease is refused; bounded acquisition
  (`--wait-timeout`) polls and then fails with the holder's identity.
  Cross-host/cross-user leases are NEVER auto-recovered (operator matter).
- **Stale recovery**: same-host + same-user + provably dead pid is recovered
  under a guard directory (exactly one concurrent winner), generation bumps.
  `device recover` is the explicit form; `device heartbeat` refreshes liveness
  on long runs.
- **Release never touches device data**: no factory reset, wipe, or unenroll
  exists in this lane. The runner's only device-state mutations are permission
  toggles for the harness app id (`com.friend.ios.dev` /
  `com.friend-app-with-wearable.ios12.development.*`); foreign app ids are
  refused.

## Device-runner adapter

`device run` consumes the C1 session manifest (`mobile-sessions/<id>/lease.json`:
loopback ports, synthetic auth fixture, app identity) and drives the leased
device through narrow `adb` / `xcrun devicectl` shims:

- installs the built artifact (sha256 bound into the receipt),
- `adb reverse` each session port so the app's loopback endpoints reach the
  session's local services (Android),
- launch **untethered** (`am start` / `devicectl process launch` — never a
  `flutter run` debug session; debug Marionette does not survive backgrounding
  and proves nothing),
- permission deny→grant cycle (Android `pm revoke`/`pm grant`; iOS TCC is an
  operator step),
- records every step + operator steps into `device-run.json`
  (`device-run-evidence/v1`: source SHA, artifact hash, lease generation,
  device id, timestamps; credential-shaped keys are rejected).

Run evidence is per-session: `<state>/mobile-sessions/<oms-id>/device-run.json`.

## External physical-test handoff (for David's separate setup)

This is the complete template for running the physical qualification on a
provisioned host. Fill every field; attach the result to the SCA-491 issue.

### 1. Build the exact artifact

```bash
git fetch origin && git checkout <integrated-checkpoint-sha>
cd app && bash setup.sh android && bash setup.sh ios
# Android (untethered-capable, loopback-routed):
flutter build apk --debug --flavor dev --target-platform android-arm64
# iOS: profile/AOT opens untethered from the Home Screen (debug needs flutter run):
OMI_MOBILE_BUILD_MODE=profile bash setup.sh ios   # then Xcode > Runner > dev profile, your device
sha256sum build/app/outputs/flutter-apk/app-dev-debug.apk   # record in evidence
```

Record: source SHA + dirty state, artifact path + sha256, flavor/profile.

### 2. Bring up a synthetic session and lease the device

```bash
make mobile-session ARGS="doctor"                       # everything ready before continuing
make mobile-session ARGS="acquire --name c5-phys --platform android"  # session lease (id: oms-c5-phys)
make mobile-session ARGS="start oms-c5-phys --no-device" # local services only
make mobile-session ARGS="seed oms-c5-phys"             # synthetic Auth-emulator user (fixture v1)
make mobile-session ARGS="device doctor"                # device visible + registration state
make mobile-session ARGS="device register --platform android --device-id <serial> \
  --label '<what it is>' --os-version <os> --confirm-test-device"
make mobile-session ARGS="device acquire --platform android --device-id <serial> \
  --purpose c5-physical --session oms-c5-phys"
```

iOS additionally: trust the Mac, enable Developer Mode, and have a valid
development signing identity/team for the profile build.

### 3. Run the qualification

```bash
make mobile-session ARGS="device run --session oms-c5-phys --platform android \
  --device-id <serial> --artifact app/build/app/outputs/flutter-apk/app-dev-debug.apk"
```

Then work the checklist (the runner prints the operator steps it cannot do):

| # | Case | Automatable? | Pass evidence |
|---|------|--------------|---------------|
| 1 | Clean untethered launch (Home Screen → app, no `flutter run`) | runner + operator tap | `device-run.json` launch step + screenshot |
| 2 | Mic permission deny → grant → capture runs | Android: runner (`pm revoke/grant`); iOS: operator (TCC) | transcript/PCM evidence + logs |
| 3 | Bluetooth permission deny → grant → wearable reconnect | operator (BLE is real-radio) | reconnect log lines + screenshot |
| 4 | Interruption/recovery: phone call in/out during capture | operator | state log shows interrupted → running |
| 5 | Foreground/background transitions during capture | operator (adb can't drive app switching) | background modes keep capture alive |
| 6 | Wearable disconnect/reconnect during capture | operator | reconnect + capture continuity |
| 7 | Offline persistence → recovery/upload vs the session's synthetic services | operator toggles airplane mode | WAL drain + upload counts in logs |

A simulator/emulator pass, or a debug-Marionette pass, does NOT satisfy any
real-radio/background row — those stay operator-assisted on hardware.

### 4. Capture evidence

Per case record: exact build (SHA + artifact sha256), device model + OS,
lease id/generation, profile/endpoints (loopback only), real start/end times,
native logs (`adb logcat -d` / Console.app for `[PhoneMic]` lines) + Dart
logs, expected vs observed lifecycle transitions, and the `device-run.json`
receipt. Redact personal identifiers. Keep diagnostics that show failure
modes; prefer turning each device-discovered failure into a synthetic
regression vector before closing it.

### 5. Report back

Attach to SCA-491: the completed table, `device-run.json`, and log excerpts.
Physical acceptance flips only on this real-device evidence.

## m1-mac-studio readiness inventory (2026-09-16, read-only probes)

| Area | Observed | Classification |
|------|----------|----------------|
| iOS physical | `xcrun devicectl list devices` → "No devices found."; `xcrun xctrace list devices` → only this Mac | operator-action-needed: connect + unlock a dedicated test iPhone over USB, trust this Mac, enable Developer Mode (Settings > Privacy & Security > Developer Mode) |
| iOS signing | `security find-identity -v -p codesigning` → 0 valid identities (this SSH context) | operator-action-needed: provide an authorized development team/identity for profile builds (simulator-only work needs none) |
| Android physical | `adb devices` → none attached (platform-tools 37.0.1 present at `/Volumes/scratch/android-sdk`) | operator-action-needed: connect + unlock a dedicated test phone, enable Developer options > USB debugging, authorize this host |
| Wearable | No phone paired ⇒ no wearable path on this host | operator-action-needed (pairs to the phone, not the Mac) |
| Simulators | iOS 26.5 + watchOS 26.5 runtimes installed | ready (not hardware evidence) |
| Android SDK | platform 36, build-tools 36.0.0, NDK 28.2.13676358, platform-tools verified | ready for builds/JVM tests; emulator images intentionally absent (capacity) |

No hardware was purchased, enrolled, reset, or reconfigured. The smallest
operator steps are exactly the commands above once devices are attached.
