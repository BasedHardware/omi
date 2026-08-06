# Android CV1 Storage-First Acceptance — 2026-07-28

This is the physical-device evidence record for the storage-authoritative CV1
path in [`BLE_RELIABILITY_ACCEPTANCE.md`](./BLE_RELIABILITY_ACCEPTANCE.md).
Failures and external-service interruptions are recorded alongside passes. This
run did not authorize a full historical-backlog drain and is not evidence for
the unrun iOS matrix.

## Fixture

| Item | Value |
|---|---|
| Phone | Samsung SM-S936U, Android 16 |
| App | Omi Dev `com.friend.ios.dev`, `1.0.543` (`992`) |
| Candidate source | `bd664d8fb2` (physically installed); rebased equivalent `64866c89ad` |
| APK SHA-256 | `42ba81588cee5572f8828e558243b83ac935c3a7631fb08b0bbb537a88242b1d` |
| Pendant | Omi CV1, identifying address redacted |
| Firmware | Storage-authoritative `3.0.29` candidate |
| App policy | automatic offline sync off; Remote VAD on; Android background mode off |
| Initial pendant state | battery 85%; read cursor 1,341,641; dropped records 0 |

The APK passed
`scripts/verify_android_physical_test_auth_config.sh` immediately before it
was installed. Installation used `adb install -r`, retaining the authenticated
dev account, exact pendant pairing, preferences, and local WAL manifest. The
production app was not stopped or replaced.

Do not publish the raw log or manifest. They contain device and account
identifiers even though this record does not.

## Automated evidence

The candidate passed:

```bash
flutter test test/unit/local_wal_sync_test.dart
flutter analyze \
  lib/services/wals/local_wal_sync.dart \
  test/unit/local_wal_sync_test.dart

cd android
./gradlew app:assembleDevDebug \
  -x app:uploadCrashlyticsMappingFileDevDebug \
  -Ptarget-platform=android-arm64 \
  -Ptarget=lib/main.dart
```

The WAL test file passed all 70 tests, the focused analyzer reported no issues,
and the authenticated Android build completed successfully.

New regression coverage proves:

- all transitive ring ranges separated by less than the configured 120-second
  conversation boundary are claimed before canonical publication;
- a range at exactly the boundary remains a separate conversation;
- a missing local archive is quarantined once instead of failing every
  compaction timer;
- truthful pendant recovery replaces an unavailable exact range and retires a
  stale covered alias.

## Physical results

| Case | Result | Evidence |
|---|---|---|
| Locked-screen cold start | Pass | The in-place dev build connected to the exact paired pendant, performed one time sync for the ready generation, started the storage-authoritative tail, and retained authentication. |
| Historical missing-file failure | Pass | The previously retryable missing archive moved to one `corrupted` manifest entry. No `historical archive group remains retryable` event recurred after the new build. The old pendant read cursor remained unchanged, so device recovery remains available. |
| Automatic deep backlog policy | Pass | The app logged that automatic sync was disabled. The historical read cursor remained 1,341,641; the run did not silently authorize or advance the old backlog. |
| Bluetooth off/on while locked | Pass | Bluetooth was disabled at 14:08:51, a deterministic offline marker played twice, and Bluetooth was enabled at 14:09:03. The exact pendant reported connected at 14:09:06.485 and time sync at 14:09:06.901. No force-stop, relaunch, or user reconnect was needed. |
| Offline range recovery | Pass | Recovery began at sequence 1,389,400 and durably completed two ranges: 96 records / 39,479 encoded bytes in 1.065 s, then 88 records / 36,077 encoded bytes in 0.775 s. The final write cursor was 1,389,584 and `dropped` remained 0. |
| Preview identity across outage | Pass after backend recovery | Reconnect explicitly preserved 48 visible preview segments. The transcription endpoint returned HTTP 503 during the outage, then became ready at 14:09:53.892. Pending durable ranges replayed idempotently, and the same preview advanced from 48 to 53 visible segments beginning 6.005 s after backend readiness. |
| Conversation assembly after the configured boundary | Pass | At 14:12:18 the app stamped 456 physical WALs from the continuous run. The manifest published one conversation-bound canonical replacement spanning 871 wall-clock seconds and 43,511 frames instead of exposing hundreds of short files. |
| Short-run battery observation | No regression observed | Pendant battery reported 85% throughout the measured reconnect/replay interval. This is not a substitute for the planned overnight battery comparison. |

The two recovery reads correspond to small interrupted-live ranges, not a clean
large-backlog benchmark. Their encoded throughputs were approximately 37.1 and
46.6 kB/s. They must not be compared to or folded into the existing 88.77 kB/s
large-range clean baseline.

## External-service interruption

The first reconnect attempts reached the pendant normally but the transcription
WebSocket received HTTP 503. Local durability therefore passed before live
transcription could pass. Once the service became ready, the app replayed the
already durable pending ranges, did not create duplicate WAL identities, and
continued the existing preview. This is the intended failure separation: a
backend outage can delay transcription, but it cannot erase the pendant or
phone copy.

## Remaining acceptance work

- Unlock the phone and authorize one immutable manual backlog snapshot. Interrupt
  BLE after `READ_BEGIN`, resume without another Sync tap, and prove completion
  through the original target without starving live audio.
- Measure at least three large clean ranges and keep interrupted retries out of
  the clean p50.
- Reconcile the uploaded canonical job to a terminal server result and inspect
  the final transcript chronology without publishing transcript content.
- Run the same marker, locked-screen reconnect, conversation-boundary, manual
  backlog, and DFU cases on the physical iPhone.
- Run a longer unplugged quiet/speech cycle to quantify the battery cost of the
  live tail and optional historical lane.

## Local evidence

- `/tmp/omi-acceptance-20260728.log`
- `/tmp/omi-acceptance-postfix-20260728.log`
- `/tmp/omi-acceptance-postfix-wals-initial.json`
- `/tmp/omi-acceptance-postfix-wals-final.json`
- `/tmp/omi-cv1-marker-online.aiff`
- `/tmp/omi-cv1-marker-offline.aiff`

## 2026-07-30 live-authority rerun

The authenticated Android dev build was rebuilt and installed in place after
removing charging from the deep-backlog authority path. Authentication,
preferences, the exact pendant pairing, and local recovery state were retained.
Automatic offline sync remained off.

The development transcription endpoint repeatedly closed with WebSocket code
1006 before reporting service readiness. The app therefore left the
storage-authoritative tail on the pendant: the run contained no ring
`READ_BEGIN`, `READ`, or `ADVANCE` command while transcription was unavailable.
This is the intended containment result and prevents an unavailable live
service from turning durable pendant history into an unbounded phone-side
queue. It is not live-preview evidence.

Android Bluetooth was then disabled and re-enabled. The exact pendant began
reconnecting about 5.2 seconds after radio shutdown, completed the physical
GATT connection about 2.2 seconds later, republished app readiness in another
0.3 seconds, and completed time sync in another 0.25 seconds. No ring read or
advance occurred during the service outage. This proves transport recovery and
live/deep authority containment; the live transcript still requires a healthy
development transcription endpoint.
