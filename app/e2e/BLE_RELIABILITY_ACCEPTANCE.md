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
  test/providers/capture_provider_test.dart \
  test/providers/device_provider_test.dart \
  test/providers/sync_provider_sync_wal_wake_test.dart \
  test/services/capture/conversation_session_window_test.dart \
  test/services/capture/device_audio_streaming_policy_test.dart \
  test/services/capture/live_transcript_preview_test.dart \
  test/services/wals/ring_storage_sync_test.dart \
  test/unit/conversation_audio_assembler_test.dart \
  test/unit/device_transport_exclusive_release_test.dart \
  test/unit/firmware_dfu_connection_handoff_test.dart \
  test/unit/local_wal_sync_test.dart \
  test/unit/native_ble_transport_exclusive_release_test.dart \
  test/unit/omi_mcu_dfu_policy_test.dart \
  test/unit/omi_ready_generation_time_sync_test.dart \
  test/widgets/transcription_paused_warning_test.dart

bash scripts/test_verify_android_physical_test_auth_config.sh
bash scripts/test_verify_ios_physical_test_auth_config.sh
scripts/analyze_ratchet.sh
```

## Storage-authoritative operating contract

The default connected mode is live capture. It may repair missing audio from
the still-open conversation, using the configured conversation-silence
boundary and durable sequence coverage, but it must not consume older pendant
history. A historical drain requires either one explicit Sync action or the
existing Auto Sync opt-in. Charging changes scheduling capacity, not user
authority, and therefore never starts a deep drain.

Automatic historical work remains subordinate to the live lane and runs only
in bounded slices. Explicit **Fast Sync** is a different, user-visible mode: it
latches one immutable ring write-sequence target, pauses preview delivery, and
uses larger sequential reads to move that fixed snapshot to durable phone
storage. Audio recorded after the target remains on the pendant and must not
expand the active snapshot. Completion, cancellation, or a recoverable transfer
failure must release BLE to live capture immediately. Being plugged in may
supply the power budget for requested work; it does not authorize Fast Sync or
an automatic deep drain.

The Sync page exposes determinate progress against that immutable target while
Fast Sync owns BLE. The used/free byte count is a cached device-status sample,
not a transfer counter: the app must not fabricate a decreasing value because
newer audio continues entering the ring after the target. A later status read
may refresh those bytes independently of the target-progress indicator.

This contract is shared Dart policy. Android and iOS provide transport
ownership but do not choose different backlog behavior. If the transcription
service is unavailable, storage-authoritative firmware keeps recording on the
pendant; the app must not move an unbounded queue of tiny ranges onto the
phone while no live transcript can accept them.

### Internal 3.0.30 black-box harness

Production routing remains exact to the 3.0.29 storage-authoritative test
line. A physical run against diagnostic firmware 3.0.30 build 110 is valid
only when the app was compiled and launched with
`--dart-define OMI_BLACKBOX_HARNESS=true`. Before collecting evidence, the
runtime log must show both `usesStorageAuthoritativeAudio=true` and an active
ring-audio owner. The define alone is not evidence: a build missing the
dev-only policy gate silently falls back to the legacy live characteristic and
invalidates Fast Sync and preview results.

Never widen production firmware routing to admit a diagnostic build. Keep the
harness artifact in the permanent CV1 evidence directory with its SHA-256,
bundle identifier, source commit, firmware build, and exact launch command.

### Authenticated Android physical-device builds

The hermetic `test.sh` bootstrap intentionally writes an empty `.dev.env` and
placeholder development Firebase files. Those inputs are valid for unit tests
only. Building an APK from them produces a sign-in screen whose OAuth URL is
relative and whose Firebase identity cannot authenticate the real test
account.

Before every authenticated Android CV1 run, seed these ignored files from the
primary maintainer checkout that already has the working prod-backed dev
configuration. Do not install the APK unless the mandatory preflight below
passes after generation:

```bash
M=/absolute/path/to/maintainer-checkout/app
W=/absolute/path/to/test-worktree/app

cp "$M/.dev.env" "$W/.dev.env"
cp "$M/lib/firebase_options_dev.dart" "$W/lib/firebase_options_dev.dart"
cp "$M/android/app/src/dev/google-services.json" \
  "$W/android/app/src/dev/google-services.json"
# main.dart imports both flavor option libraries at compile time. A dev build
# still needs the checked-in setup fixture at the unused prod import path.
cp "$W/setup/prebuilt/firebase_options.dart" \
  "$W/lib/firebase_options_prod.dart"
cp "$W/setup/prebuilt/key.properties" "$W/android/key.properties"

# The maintainer checkout may target the development API. Hardware acceptance
# must exercise the canonical customer data plane with the production Firebase
# project; set API_BASE_URL=https://api.omi.me/ in the copied .dev.env.

cd "$W"
dart run build_runner clean
dart run build_runner build --delete-conflicting-outputs
bash scripts/verify_android_physical_test_auth_config.sh
flutter build apk --debug --flavor dev --target-platform android-arm64
```

The clean is required because build_runner's cached asset graph may not notice
an ignored `.dev.env` change and can report "wrote 0 outputs" while retaining
the empty test URL. The preflight decrypts the generated
`lib/env/dev_env.g.dart`; it must report the canonical production API + prod
Firebase with the dev package before the APK is installed. `api.omiapi.com` is
a development backend and is invalid acceptance evidence even when Firebase
authentication succeeds. Android and iOS preflights source the same executable
authority in `scripts/physical_test_customer_plane.sh`; do not duplicate or
override its endpoint in a platform-specific test workflow. Re-run the
preflight after every `test.sh`,
`flutter pub get`, setup script, branch switch, or rebase that may regenerate
ignored configuration.
An auth failure from an APK that did not pass this preflight is a build-fixture
failure, not BLE evidence.

#### Verified maintainer workstation toolchain

On the maintainer Mac used for CV1 acceptance, establish the toolchain before
regenerating or building. Do not replace `PATH` with a reduced list: Node lives
under `$HOME/.local/bin` on this machine and repository gates require it.

```bash
export JAVA_HOME=/opt/homebrew/opt/openjdk@21/libexec/openjdk.jdk/Contents/Home
export PATH="/opt/homebrew/bin:$HOME/.local/bin:$PATH"

java -version
flutter --version  # verified with Flutter 3.44.8
node --version     # verified with Node 22.23.1
```

If the local network blocks the debug Crashlytics mapping upload, exclude only
that upload task. Gradle still compiles and packages the complete dev APK:

```bash
cd android
"$JAVA_HOME/bin/java" \
  -classpath gradle/wrapper/gradle-wrapper.jar \
  org.gradle.wrapper.GradleWrapperMain \
  app:assembleDevDebug \
  -x app:uploadCrashlyticsMappingFileDevDebug \
  -Ptarget-platform=android-arm64 \
  -Ptarget=lib/main.dart
cd ..

shasum -a 256 build/app/outputs/flutter-apk/app-dev-debug.apk
```

Git hooks export the Omi worktree's `GIT_DIR`. Raw Flutter commands inside a
hook can then inspect Omi instead of the Flutter SDK and report
`0.0.0-unknown`. Hook-owned Flutter commands must use the checked-in
`scripts/flutter-with-clean-git-env` wrapper. Its behavioral regression is part
of the existing `setup-pre-push-prerequisites` gate.

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
| Pendant absence | Take the pendant out of range or power-cycle it, speak while disconnected, then return it | Native reconnect restores live audio; the still-open conversation gap is repaired in its original chronology without authorizing older history |
| Foreground/background | Background and foreground the app with the screen both unlocked and locked; on Android test background mode off and on | Reconnect does not create duplicate subscriptions or duplicate time-sync writes; capture/backfill resumes according to the platform mode |
| MCU DFU success | Complete one normal firmware update | The DFU updater releases BLE, one serialized bounded reclaim loop targets only the exact pre-DFU pendant (up to three attempts), normal audio/backlog sync resumes without app restart, and pendant application settings remain unchanged |
| DFU failure | Abort or use a controlled failing test image before activation | The app clears firmware-update state and runs one bounded reclaim loop for the same pendant; a plugin error plus thrown future must not start a second loop |
| Page disposal | Leave the firmware page while terminal cleanup is in flight | Disposal and the later terminal callback share one cleanup/reclaim future; neither strands nor duplicates the BLE owner |
| Fast Sync | Begin with a known non-empty pendant backlog, start Fast Sync, disrupt BLE during transfer, then restore it | The fixed snapshot resumes without a second tap; durable records are not acknowledged early; newer capture does not expand the target; transfer finishes in timestamp order without duplicates; live preview resumes immediately |
| Fast Sync cancel | Start Fast Sync, wait for one bounded range to begin, then cancel | At most the in-flight bounded range finishes and is durably acknowledged; no further historical range begins; live preview resumes without reconnect or app restart |

## Cross-host ownership handoff

CV1 firmware exposes one BLE connection. An installed iOS app may be relaunched
by CoreBluetooth restoration even when it is not the companion the user is
actively using. With iOS Background Mode disabled:

1. Connect iOS, terminate the dev app, and confirm iOS performs a restoration
   launch.
2. Leave that restored iOS process running and enable Bluetooth on the paired
   Android phone.
3. Android must acquire the pendant without terminating iOS again. The
   background-launched Flutter engine must not reclaim the link.
4. Disable Android Bluetooth and foreground iOS. iOS must then reconnect and
   republish GATT readiness.

Repeat with iOS Background Mode enabled. In that opt-in mode, restoration owns
the background capture link until the user explicitly releases or switches the
device; this is expected rather than a handoff failure.

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

## Storage-authoritative logical backlog

Remote VAD and backlog grouping are independent contracts. Remote VAD adds a
voice gate to the live transcription socket; it does not merge Sync-screen
rows or change the local-files upload boundary. It is valid to retain multiple
bounded ring/archive artifacts internally, but adjacent artifacts inside the
configured conversation-silence boundary must appear as one logical recording
and upload as one ordered multipart job.

Run this case with `autoSyncOfflineRecordings=false`. Charging never authorizes
a deep drain; only a Sync tap or explicit automatic offline-sync opt-in may
consume historical backlog.

1. Record the configured conversation-silence duration, Remote VAD state,
   initial battery, and initial ring `read`, `write`, and `dropped` counters.
   Preserve the WAL manifest and a SHA-256 inventory of audio artifacts.
2. Cold-launch the authenticated dev app and establish live transcription.
   Wait 60–90 seconds without tapping Sync. Recent live/recovery reads are
   allowed, but old backlog must neither drain nor upload automatically.
3. Confirm adjacent physical archives render as one pending row whose duration
   spans their wall-clock capture interval. A five-minute storage boundary is
   never, by itself, a conversation boundary.
4. Tap Fast Sync once while continuing to produce audio. Capture the
   `manual backlog snapshot latched` log and its immutable
   `target_write_seq=T`. Preview is intentionally paused while the fixed
   snapshot drains. Historical ranges authorized by this tap must end at or
   before `T`; newer records stay in the ring and must not expand the target.
   Require the Sync page to show determinate progress toward `T`; do not treat
   its separately cached storage byte count as live transfer progress.
5. Disable Bluetooth after `NOTIFY_READ_BEGIN` and before `NOTIFY_DONE`, play a
   unique offline marker, then re-enable Bluetooth. Do not tap Fast Sync again.
   The same pendant must reconnect, retry from durable coverage, and emit
   `manual backlog snapshot completed` for the original `T`. The existing live
   preview then resumes and includes capture produced after `T`.
6. After the configured conversation boundary closes, require one logical row
   and one upload job for the continuous run. Every physical member must share
   the terminal job result; sequence coverage through `T` must have no holes or
   duplicate source identities. The offline marker must occur once in
   timestamp order.
7. Repeat with a second fixed snapshot and cancel during one bounded range.
   Preserve the cancellation time and the first post-cancel live frame time.
   Already durable coverage may advance, but no subsequent historical READ may
   begin and the user must not need to reconnect or reopen the capture screen.

A `429` or server `5xx` is not an end-to-end pass. Confirm bounded retry with
local data retained, then verify the final transcript when the backend is
available. Report record throughput (`count * 444 / elapsed`) and encoded-audio
throughput (`count * 440 / elapsed`) separately, and keep interrupted retries
out of the clean p50. Do not publish raw manifests, preferences, account IDs,
or full Bluetooth addresses.

## Deterministic voice-gate fixture

Use recorded or synthesized speech instead of tester speech when comparing
firmware voice-gate candidates. Keep the pendant position, phone position,
speaker, macOS output level, and pendant microphone gain unchanged for the
entire comparison.

Create one reusable marker:

```bash
say -v Samantha -r 165 \
  -o /tmp/omi-cv1-marker.aiff \
  "Omi marker seven. The blue train reaches the station at nine forty."
```

For each firmware artifact:

1. Record the artifact SHA-256 and the initial ring `read`, `write`, and
   `dropped` counters.
2. Leave the fixture silent for 60 seconds. After the configured audio
   hangover, `write` must remain stable; hardware-AAD wakeups alone are not
   stored speech.
3. Play the marker five times at the fixed normal level, separated by
   one-second pauses:

   ```bash
   for run in 1 2 3 4 5; do
     afplay -v 0.50 /tmp/omi-cv1-marker.aiff
     sleep 1
   done
   ```

4. Repeat once at the fixed quiet level with `afplay -v 0.25`.
5. Leave the fixture silent again. The ring must stop growing within the
   encoded-audio hangover even if the low-power conversation window remains
   armed.
6. Cycle phone Bluetooth off, play one marker while disconnected, then turn
   Bluetooth on. The app must resume live audio first and durably recover the
   missing marker with its capture timestamp.

Pass only when all normal-level markers and the quiet marker are durably
present, the two silence windows do not create audio records, `dropped` does
not increase, and the reconnect produces neither a duplicate marker nor a
chronological rewind. Preserve the generated audio file, artifact hash, ring
snapshots, and Flutter/native log with the run evidence.

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
5. Inject adjacent, contiguous source ranges whose embedded RTC timestamps jump
   forward beyond the configured conversation boundary. They must never be
   assembled into one silence-padded canonical file or reported as one long
   conversation. Preserve both source sequence and embedded timestamp in the
   diagnostic evidence; sequence establishes identity, while wall clock owns
   the conversation boundary.

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
