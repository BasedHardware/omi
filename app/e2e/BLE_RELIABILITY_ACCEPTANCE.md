# Pendant BLE Reliability Acceptance

Use this playbook for changes to Omi pendant connection ownership, native
auto-reconnect, firmware update handoff, time sync, or offline-backlog recovery.
It complements hermetic Flutter/Kotlin tests; it is not a CI test because it
requires one physical pendant and phone.

Do not run two app clients against the pendant at once. Stop only the dev build
you launched. Never stop or replace a production desktop Omi app.

## Automated preflight

From `app/`, run the focused behavioral contracts before touching hardware:

```bash
flutter test \
  test/unit/device_transport_exclusive_release_test.dart \
  test/unit/firmware_dfu_connection_handoff_test.dart \
  test/unit/native_ble_transport_exclusive_release_test.dart \
  test/unit/omi_mcu_dfu_policy_test.dart \
  test/unit/omi_ready_generation_time_sync_test.dart \
  test/providers/device_provider_test.dart

scripts/analyze_ratchet.sh
```

If native Android BLE code changed, also run its focused Gradle test target
named in `app/AGENTS.md`. These tests must pass without a phone, network, sleep,
or plugin callbacks.

## Fixture and evidence

Record:

- app commit, flavor, phone model/OS, pendant ID suffix, and firmware version;
- whether Android background mode is enabled;
- wall-clock time from each disruption to `connected`, audio resumption, and
  backlog resumption;
- the app log spanning the disruption, including
  `OmiDeviceConnection: Time synced to device`;
- the backlog packet/byte count before and after the run.

Use `flutter run ... > /tmp/omi-flutter.log 2>&1` so the same log drives
`agent-flutter` and preserves evidence. On iOS, follow
[`IOS_DEVICE_TESTING.md`](./IOS_DEVICE_TESTING.md). On Android, use the setup in
[`SKILL.md`](./SKILL.md) and keep `adb logcat` as supplemental native evidence.

## Acceptance matrix

Run the matrix once on Android and once on iOS. Start each row with live audio
visible in the app and speak a unique marker phrase before and after the
disruption.

Before every intentional Bluetooth outage, show the tester a user-facing
`Offline test active — capture will reconnect and backfill` notice. As soon as
live audio and backlog processing are restored, show
`Connection restored — live capture and backfill resumed`. Do not begin the
next disruption until the tester has seen the restoration notice.

| Case | Action | Required result |
|---|---|---|
| Initial owner | Cold-launch the dev app with the paired pendant available | The exact paired pendant reaches ready, time sync is attempted once, and live audio starts without a second connect action |
| Bluetooth cycle | Turn phone Bluetooth off, speak a marker, turn it on, repeat five times | Every cycle reconnects without force-stop/relaunch; one time-sync attempt occurs per new ready generation; live audio resumes |
| Pendant absence | Take the pendant out of range or power-cycle it, speak while disconnected, then return it | Native reconnect restores live audio; stored audio drains afterward with its original chronology |
| Foreground/background | Background and foreground the app with the screen both unlocked and locked; on Android test background mode off and on | Reconnect does not create duplicate subscriptions or duplicate time-sync writes; capture/backfill resumes according to the platform mode |
| MCU DFU success | Complete one normal firmware update | The DFU updater releases BLE, one serialized bounded reclaim loop targets only the exact pre-DFU pendant (up to three attempts), normal audio/backlog sync resumes without app restart, and pendant application settings remain unchanged |
| DFU failure | Abort or use a controlled failing test image before activation | The app clears firmware-update state and runs one bounded reclaim loop for the same pendant; a plugin error plus thrown future must not start a second loop |
| Page disposal | Leave the firmware page while terminal cleanup is in flight | Disposal and the later terminal callback share one cleanup/reclaim future; neither strands nor duplicates the BLE owner |
| Backlog | Begin with a known non-empty pendant backlog, disrupt BLE during transfer, then restore it | Durable records are not acknowledged early; transfer resumes, finishes, and preserves timestamp order without duplicates |

## Repeatable backlog throughput

Use the same exact phone, pendant, app source, firmware artifact, distance, and
power conditions for candidate-versus-baseline comparisons. Where the backlog
permits, measure at least three large, clean ranges.

For every range, record:

- start/end durable cursors, record count, raw audio payload bytes, and
  `dropped` before and after;
- elapsed time from `READ_BEGIN` acceptance through `DONE`; exclude discovery,
  connection, service setup, and UI time;
- raw payload kB/s using decimal kB, plus the clean-run minimum and p50;
- negotiated MTU, PHY, and connection interval for that connection;
- whether the range was clean or an interrupted retry.

Interrupted retries are a separate population and must never be folded into the
clean p50. For this exact fixture, compare the clean p50 against the measured
88.77 kB/s clean baseline. A lower clean p50 is a regression until a
parameter-matched rerun explains it; this comparison gate is not an absolute
speed promise for every phone or radio environment. Keep the measured
74.10 kB/s retry result classified as an interrupted-retry regression
(approximately 16.5% below that clean baseline) until it is remeasured on the
same path.

## Timestamp-specific checks

Firmware reboot can reset its clock. For every initial connection and native
auto-reconnect:

1. Confirm exactly one `Time synced to device` log for that ready generation.
2. Confirm a failed GATT write is logged but does not suppress the next
   generation's attempt.
3. During rapid reconnects, confirm writes are serialized. A stale generation
   must never finish after a newer write.
4. Compare the marker phrases and stored-segment timestamps. Post-reconnect
   audio must not rewind into an earlier conversation.

## Known DFU telemetry limitation

DFU suspension currently traverses the normal disconnect path before the
exclusive transport-release seam. Native diagnostics can therefore record this
ownership handoff as a user-requested manual disconnect even though the user
did not choose “Disconnect.” Treat that event as DFU lifecycle noise when it
coincides with firmware update start. A dedicated native suspend reason would
remove the ambiguity, but is outside this narrowly scoped reliability fix.

## Pass and escalation

Pass only when all rows complete without force-stop/relaunch, manual reconnect,
wrong-device attachment, duplicate terminal cleanup, or chronological rewind.
Record measured reconnect and drain times rather than hiding slow runs behind a
large timeout.

If a row fails, retain the full Flutter/native log and the exact disruption
sequence. Re-run only once to classify reproducibility; repeated blind retries
erase the failure state that the reliability work needs.
