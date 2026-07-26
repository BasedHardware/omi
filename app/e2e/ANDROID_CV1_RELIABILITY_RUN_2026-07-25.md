# Android CV1 BLE Reliability Run — 2026-07-25

This is the physical-device evidence record for the Android half of
[`BLE_RELIABILITY_ACCEPTANCE.md`](./BLE_RELIABILITY_ACCEPTANCE.md). It records
both passes and failures; it is not a claim that the full acceptance matrix
passes.

## Fixture

| Item | Value |
|---|---|
| Phone | Samsung SM-S936U, Android 16 (API 36) |
| App | Omi Dev `com.friend.ios.dev`, `1.0.543` (`992`) |
| Installed source revision at evidence capture | Exactly `9981ef2ccec1c8769f696d5611082604f06b5f36` |
| Pendant | Omi CV1; address masked as `**:**:**:**:0B:95` |
| Firmware before OTA | `3.0.28.1` |
| Firmware after OTA | `3.0.28.2`, confirmed and active |
| DFU artifact SHA-256 | `79ade33e69f3112e2dddee8a0876db68dfef11870f11111c94628d4d5efd2e90` |

The current uncommitted reliability changes—including DFU ownership/reclaim,
Android session-bound GATT/ready handling, reconnect stream lifecycle, and
per-GATT-ready time sync—were developed after this run. They were not installed
on the phone and none of the physical results below are evidence for them.

Do not publish full Bluetooth addresses, Firebase identities, email addresses,
bearer tokens, WebSocket URLs, or raw transcript content with this evidence.
All results below were extracted from redacted Flutter/Android logs.

## Safety and preflight

- Verified the exact paired pendant before any GATT management or DFU action.
- Captured the durable ring read/write cursors and dropped-record count before
  every destructive transfer.
- Used only the dev app. The production app was not stopped or replaced.
- Did not erase ring storage. `ADVANCE` was allowed only after `DONE`.
- Performed one OTA reboot. No later management reboot was run.
- Stopped intentional Bluetooth disruptions when live transcription became the
  user's priority. The last backlog was preserved for the post-fix run.

The firmware artifact's manifest advertised `3.0.28.2`. After activation, an
independent MCUboot image-list query returned slot 0 as active, confirmed,
bootable `3.0.28.2`.

## Historical pre-registry automated evidence

Before the current uncommitted session-bound completion-registry work began,
the Android BLE unit lane was run locally with the Homebrew JDK:

```bash
JAVA_HOME=/opt/homebrew/opt/openjdk@21 \
  ./gradlew :app:testDevDebugUnitTest --tests 'com.friend.ios.ble.*'
```

That pre-registry run reported `BUILD SUCCESSFUL` across 757 tasks. It is
hermetic native test evidence for the earlier source state only; it does not
cover the current uncommitted Kotlin registry work, change the installed-source
provenance, or repair the failed physical cases above.

## Final integrated local automated evidence

After the session-bound Android completion registry, exact-session delayed
MTU/ready guard, bounded exact-device DFU reclaim, reconnect stream lifecycle,
and per-ready-generation time sync were integrated, the current worktree
passed:

```bash
JAVA_HOME=/opt/homebrew/opt/openjdk@21 \
  ./gradlew :app:testDevDebugUnitTest --tests 'com.friend.ios.ble.*'

flutter test \
  test/unit/device_transport_exclusive_release_test.dart \
  test/unit/firmware_dfu_connection_handoff_test.dart \
  test/unit/native_ble_transport_exclusive_release_test.dart \
  test/unit/omi_mcu_dfu_policy_test.dart \
  test/unit/omi_ready_generation_time_sync_test.dart \
  test/providers/device_provider_test.dart

bash test.sh
scripts/analyze_ratchet.sh
git diff --check
```

The Gradle lane reported `BUILD SUCCESSFUL` across 757 actionable tasks
(14 executed, 743 up-to-date). The focused Flutter reliability set passed 35
tests, the full Flutter suite passed 1,008 tests, and the analyzer ratchet and
diff check passed.

This is hermetic source-level evidence only. These integrated changes were not
installed on either phone or exercised against the pendant, so none of these
results change the physical verdicts or installed-source revision recorded
above.

## Seams exercised

- Android native BLE connection ownership and automatic reconnect
- Flutter connection readiness after a new native connection generation
- CV1 ring protocol: `RingInfo`, `READ_BEGIN`, `DONE`, and `ADVANCE`
- Interrupted range transfer and retry from the durable cursor
- Screen-off/doze transfer behavior
- App process relaunch with persisted authentication and pairing
- MCUboot DFU handoff, activation, and post-reboot reclaim
- Firmware RTC timestamps across ordinary reconnect and OTA reboot

## Results

| Case | Result | Evidence |
|---|---|---|
| Large pre-OTA backlog | Pass | 46,800 records advanced from cursor 880,869 to 927,669 at 88.77 kB/s, followed by 2,383 records to cursor 930,052. Firmware reported `dropped=0`. |
| OTA and activation | Pass | `3.0.28.2` uploaded, activated, confirmed, and independently observed active after reboot. |
| Cursor integrity across OTA | Pass | Pre-OTA durable cursor was 930,052. First post-OTA `RingInfo` read cursor was exactly 930,052; 714 newly captured records were pending and `dropped=0`. |
| Small post-OTA drain | Pass | 714 records, 317,016 raw bytes, 3.946 s, 80.34 kB/s. `DONE` preceded successful `ADVANCE`; postcondition `read == write == 930,766`, `dropped=0`. |
| Passive recovery after OTA reboot | **Fail** | App remained Offline for more than 60 s. A Bluetooth off/on cycle did not reclaim it within 15 s. Force-stop/relaunch was required; authentication was retained and connection then completed in 1.087 s, ring-ready in about 2.5 s. |
| Ordinary reconnect after app restart | Pass with latency | Four measured connects were 3.13, 3.76, 3.62, and 2.67 s; ring-ready was 5.36, 5.71, 5.62, and 4.73 s respectively. No spontaneous radio disconnect occurred during these cycles. |
| Mid-range interruption safety | Pass | Transfer began at cursor 930,766 for 1,800 records. Bluetooth was disabled 2.17 s after `READ_BEGIN`, after 306 records plus 406 pending bytes. The app logged incomplete transfer and skipped `ADVANCE`. After reconnect, firmware still reported read cursor 930,766 and `dropped=0`. |
| Interrupted range retry | Pass | Retry drained 930,766–932,566, then 932,566–933,461. Both ranges reached `DONE` before `ADVANCE`; final `read == write == 933,461`, `dropped=0`. |
| Retry throughput | **Regression** | 1,196,580 raw bytes in 16.148 s = 74.10 kB/s (72.36 KiB/s), about 16.5% slower than the 88.77 kB/s large-backlog baseline. |
| Timestamp order on ordinary outage/retry | Pass | Controlled outage segments were monotonic and their starts were within about one second of the corresponding disruption start. |
| Timestamp order across OTA reboot | **Fail** | Post-OTA segments moved from epoch 1,785,022,655 back to 1,785,018,726 (about 65 minutes), then forward again. Sequence cursors remained contiguous, but cursor order alone cannot reconstruct conversation chronology after this RTC migration. |
| Screen-off transfer | Partial | A 268-record range (933,461–933,729) completed with `DONE` then `ADVANCE` while the phone initially reported Dozing. The phone woke within about 10 s, so sustained screen-off transfer remains unproven. |
| Process relaunch | Pass | Before relaunch `read == write == 933,729`, `dropped=0`. Force-stop/relaunch retained auth and pairing; exact-device connection completed in about 1.1 s and ring status followed. |
| Sustained doze reconnect | Partial | After roughly 100 s of screen-off capture, automatic reconnect completed in about 2.3 s and ring status followed about 1.8 s later. The reported 2,159-record backlog also included an earlier management-client disconnect, so it is not a pure doze capture-volume measurement. |
| Final 2,159-record drain | Held | The user resumed live Listening/transcription. No further disconnect, reboot, foreground navigation, or drain was performed. Preserve this backlog for the post-fix acceptance run. |

## Findings

1. The durable cursor contract is working: incomplete BLE reads did not advance
   firmware state, and reconnect retried the exact range without a gap.
2. DFU activation and cursor preservation worked, but automatic ownership
   recovery after the firmware reboot did not. Requiring an app process restart
   is an acceptance failure.
3. Ordinary reconnect timestamps were accurate, while the OTA reboot produced
   a large timestamp rewind. RTC/time-sync ordering around DFU reboot is a
   separate correctness defect from BLE transport reliability.
4. Transfer speed varies materially. The interrupted-retry path was slower than
   the large-backlog baseline and should be measured separately from initial
   bulk drain.
5. An independent MCU management client can cause the app to forget/unmanage
   the pendant. Future test tooling must treat management ownership as
   exclusive and verify the persisted exact-device identity afterward.
6. A UI duration label can remain stale or represent the phone-side WAL rather
   than the current pendant backlog. Protocol cursors are the acceptance source
   of truth.

## Required post-fix rerun

Resume with the preserved 2,159-record backlog while live capture is active.
The run passes only if the app drains it without an early `ADVANCE`, keeps
subsequent live audio connected, reports `dropped=0`, and reconstructs monotonic
conversation time. Show the Offline-test and Connection-restored notices
required by the acceptance playbook around every intentional disruption. Then
repeat:

1. DFU activation followed by passive exact-device reclaim, with no app restart.
2. A sustained locked-screen/background drain long enough to prove the phone
   remains asleep.
3. At least three large clean throughput ranges where the backlog permits,
   measured separately from interrupted retries against the 88.77 kB/s clean
   baseline.
4. The same artifact and cases on a physical iPhone.
5. Five reconnect cycles on each platform only after notifying the tester that
   live capture will be intentionally interrupted.

## Local evidence index

The raw evidence remains local because it contains device and account data.
Redact it before attaching excerpts to a PR.

- `/tmp/omi-android-plus2-dfu-live.log`
- `/tmp/omi-active-imagelist-excerpt.log`
- `/tmp/omi-android-714-drain-excerpt.log`
- `/tmp/omi-android-midrange-cut-excerpt.log`
- `/tmp/omi-android-midrange-resume-reconnect.log`
- `/tmp/omi-android-resume-drain-excerpt.log`
- `/tmp/omi-android-bg-sync-excerpt.log`
- `/tmp/omi-android-relaunch-excerpt.log`
- `/tmp/omi-android-sustained-doze-reconnect.log`
