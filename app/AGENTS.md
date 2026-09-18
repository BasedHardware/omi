# App (Flutter) — Operational Playbook

Inherits [`../AGENTS.md`](../AGENTS.md); adds app-specific operational guidance.

## Build Bootstrap

### Flavors
- **dev**: Android `com.friend.ios.dev`, iOS `com.friend-app-with-wearable.ios12.development` — uses `.dev.env`, Firebase project `based-hardware-dev`
- **prod**: Android `com.friend.ios`, iOS `com.friend-app-with-wearable.ios12` — uses `.env`, Firebase project `based-hardware-prod`
- **raybanDat**: camera-capable iOS target with the same iOS development identity; `scripts/rayban_dat.sh` excludes mcumgr only for that transaction, then restores the default graph.

### Version string
`pubspec.yaml` (`1.0.543+992`) is the local marketing+build placeholder. Store binaries ignore it: Codemagic sets `BUILD_NAME` from the latest TestFlight/App Store (or Play) version and `BUILD_NUMBER` to max(store)+1 (pubspec seeds only when stores have no history). Analytics/Crashlytics `build_number` is `OMI_BUILD_NUMBER` (Codemagic's `BUILD_NUMBER`, else `"local"`). Authoritative: stores = Codemagic; local/dev = pubspec; analytics = `OMI_BUILD_NUMBER`.

### Generated Files (never edit)
envied, json_serializable, pigeon (`lib/pigeon_interfaces.dart` → `lib/gen/` + iOS/Android stubs), and flutter_gen: `flutter pub run build_runner build`. ARB → `flutter gen-l10n` (`lib/l10n/app_localizations*.dart`). Never edit `*.g.dart` / `*.gen.dart`.

Never edit generated `.g.dart`/`.gen.dart` files. Regenerate using the commands above after source changes; resolve build_runner conflicts with `--delete-conflicting-outputs`.

### Setup Sequence
```bash
bash setup.sh ios    # or: bash setup.sh android
```
This handles: pub get, build_runner, gen-l10n, and flavor configuration.

For physical-device builds, use the wrapper: it owns `dev + local_dev` and `prod + mobile_beta` pairing plus auth env setup. Direct builds must first run
`scripts/validate_mobile_build_config.sh --flavor <dev|prod> --profile <profile>`
with the matching `OMI_APP_PROFILE`; release/profile helpers do this too.
`OMI_MOBILE_BUILD_MODE=profile` installs an AOT build that opens untethered
(debug builds need `flutter run` attached on a physical iPhone; see README).

### Firebase Config
Never run `flutterfire configure` — it overwrites prod credentials. Config files:
- Dev: `android/app/src/dev/`
- Prod: `android/app/src/prod/`
- Local emulator: `lib/firebase_options_local.dart`

## Native Bridge

### Pigeon Interface (bidirectional, iOS ↔ Dart)
- Contract: `lib/pigeon_interfaces.dart` — paired host/Flutter APIs for the watch recorder, BLE, and Ray-Ban Meta
- Dart side: `lib/gen/pigeon_communicator.g.dart`
- iOS side: `ios/Runner/PigeonCommunicator.g.swift`
- Android side: `android/app/src/main/kotlin/com/friend/ios/PigeonCommunicator.g.kt`
- Implementation: `ios/Runner/RecorderHostApiImpl.swift`
- After editing the contract, regenerate: `flutter pub run build_runner build`

### MethodChannel (Phone Calls)
- Channel: `com.omi/phone_calls` + EventChannel `com.omi/phone_calls/events`
- Dart: `lib/services/phone_call_service.dart`
- iOS: `ios/Runner/PhoneCalls/OmiPhoneCallsPlugin.swift`
- Android: `android/app/src/main/kotlin/com/friend/ios/phonecalls/PhoneCallsPlugin.kt`
- Methods: initialize, makeCall, endCall, toggleMute, toggleSpeaker

### Pigeon (Phone Mic — conversation capture)
- Contract: `lib/phone_mic_interface.dart` → `lib/gen/phone_mic_pigeon.g.dart` + `ios/Runner/PhoneMic/PhoneMicPigeon.g.swift` + `android/app/src/main/kotlin/com/friend/ios/phonemic/PhoneMicPigeon.g.kt`
- Regenerate: `dart run pigeon --input lib/phone_mic_interface.dart`
- iOS module: `ios/Runner/PhoneMic/` — self-healing AVAudioEngine capture (interruptions/route changes recover natively; Dart only mirrors state)
- Android module: `android/app/src/main/kotlin/com/friend/ios/phonemic/` — AudioRecord capture with a self-healing rebuild loop + silencing detection (calls/assistant recover natively; Dart only mirrors state); `PhoneMicForegroundService` (microphone FGS) keeps background capture alive; batch opus encode via a JNI shim over the plugin-shipped libopus
- Dart service: `lib/services/mic/native_mic_recorder_service.dart` behind `ServiceManager.phoneMic`; chat memos/speech profile stay on flutter_sound via `ServiceManager.mic`; `MicArbiter` prevents the two stacks contending
- Events carry a Dart-minted session id (`start(mode, sessionId)`); Dart drops events with a foreign id so a stale native event can't clobber a fresh session; `start()` onto a live native session adopts the new id and re-emits state so the caller converges; `stop()` always forwards to native (kills an orphaned session) and runs local teardown once
- Two capture modes, fixed per session at `start(mode)`: `stream` (realtime frames → Dart → socket/WAL) and `batch` (Transcribe Later — native opus encode (OpusKit iOS, libopus JNI shim Android) → WAL-compatible `audio_omibatchphone[auto]_…bin`; no frames cross to Dart; liveness = 1Hz `onBatchProgress`). Mode selection lives in `CaptureController.streamRecording` (explicit `batchModeEnabled` or auto offline fallback; iOS + Android); `omibatchphoneauto` recordings auto-upload on reconnect

On-device speech deadlines and cleanup: [contract](../.github/agent-docs/on-device-speech.md).

## Permission Matrix

| Permission | Android | iOS | Feature |
|-----------|---------|-----|---------|
| Microphone | RECORD_AUDIO | NSMicrophoneUsageDescription | Recording, speech profile |
| Bluetooth | BLUETOOTH_SCAN, BLUETOOTH_CONNECT | NSBluetoothAlwaysUsageDescription | Omi device connection |
| Location | ACCESS_FINE_LOCATION | NSLocationUsageDescription | Background features |
| Contacts | READ_CONTACTS | NSContactsUsageDescription | People recognition |
| Calendar | READ/WRITE_CALENDAR | NSCalendarsUsageDescription | Calendar integration |
| Camera | — | NSCameraUsageDescription | QR/photo features |
| Notifications | POST_NOTIFICATIONS | (automatic) | Push notifications |
| Background | FOREGROUND_SERVICE_* (4 types) | UIBackgroundModes (7 modes) | Continuous capture |

Android: 26 permissions in AndroidManifest.xml; iOS: 11 background modes + 10 consent strings.
Dev contracts: [B0 registration](lib/services/dev_controls/REGISTRATION.md), [B1 addressability](lib/services/dev_controls/ADDRESSABILITY.md).
## Test Strategy

### Test Structure
- `test/spine/` — [protected contracts](../scripts/dev-harness/PENDING_CONTRACTS.md); `test/unit/` — auth and utilities
- `test/widgets/` — UI components (shimmer, waveform, transcript)
- `test/providers/` — State management (capture_provider, device_provider)
- `test/utils/` — Utility functions (localization helpers)

### Running Tests
```bash
bash test.sh            # all unit/widget tests (hermetic)
flutter test test/unit/ # specific directory
make mobile-verify ARGS="fast --paths <changed-file>"  # focused product journeys
make mobile-verify ARGS="fast --all"                   # full hermetic journey suite
(cd android && ./gradlew :app:testDevDebugUnitTest)     # Android JVM: JDK 21, SDK 36
```

`test.sh` bootstraps missing inputs with empty `API_BASE_URL`. Journey selection/receipts/CI: `scripts/dev-harness/MOBILE_VERIFY.md`.

Native batch contracts: `ruby ios/test/batch_audio_energy_test.rb` (macOS manifest, local + CI).

CI runs `test.sh`, `analyze_ratchet.sh` (no new info/warnings), and `journeys-hermetic`.

### Test Patterns
- Capture seams/ownership: [C1 contract](lib/services/capture/OWNERSHIP.md); inject fakes.
- Typed analytics: [C7 registry contract](lib/utils/analytics/registry/REGISTRY.md); state machines use production seams.
- Everything under `test/` must be hermetic — no network, live backends, or real devices — because `bash test.sh` (the CI suite) runs all of it.
- Chat transcript layout: pumping only `AIMessage` in a `SingleChildScrollView` misses scroll-extent bugs; chat list changes must keep `test/widgets/chat_scroll_layout_test.dart` green (ListView drag + citation/markdown sizes) — it is the Mobile App Checks contract for this class.
- Tests needing a live service/device/real API go under `integration_test/` (plain `test.sh` skips them); the hermetic seeded journeys there run in CI via `mobile-verify fast --all` with loopback fixtures only. Local-backend tests set `OMI_APP_TEST_API_BASE_URL=http://127.0.0.1:<port>/`.
- Coverage: root `AGENTS.md` → Testing.

## Localization (l10n)

- All user-facing strings use `context.l10n.keyName`. Template: `lib/l10n/app_en.arb`. Never hardcode a locale count; `python3 scripts/l10n.py template` lists every locale the tree has.
- Add/change/remove a key with `scripts/l10n.py` (`add`/`set`/`remove`). Do not edit ARB files by hand or with `jq`. The caller supplies translations (no network); the tool writes every locale, runs `flutter gen-l10n`, formats generated Dart, and refuses a partial or placeholder-mismatched change.
- `python3 scripts/l10n.py check` is the fast consistency gate (parse, key-set, placeholders, generated freshness). Ready for a pre-push hook; not wired in this package.

## Auth & Security

### Token Lifecycle
1. `getAuthHeader()` in `lib/backend/http/shared.dart` checks token expiry (5-minute buffer)
2. If expired, calls `AuthService.instance.getIdToken()` for Firebase refresh
3. Token stored via SharedPreferencesUtil in flutter_secure_storage (Keychain / EncryptedSharedPreferences); expiration timestamp stays in SharedPreferences. One-time migrateAuthTokenFromPrefs() runs at SharedPreferencesUtil.init() so existing sessions keep their token.
4. 401 responses trigger automatic refresh + retry

### Auth Methods
- Google Sign In (`google_sign_in` package)
- Apple Sign In (`sign_in_with_apple` package, includes PKCE via nonce+sha256)
- Firebase Auth as the identity layer

### Request Headers
All API requests include: X-Request-Start-Time, X-App-Platform, X-Device-Id-Hash, X-App-Version, plus Bearer token.

### API Base URLs
- Dev: configured in `.dev.env` → `Env.apiBaseUrl`
- Prod: configured in `.prod.env` → `Env.apiBaseUrl`

## App Flows & E2E

- Flows: `e2e/SKILL.md`. Own-voice enrollment: [guide](../.github/agent-docs/mobile-voice-enrollment.md).
- See `e2e/flows/*.yaml` for individual flow definitions

## Verifying UI Changes (agent-flutter)

After any Flutter UI edit, verify with [agent-flutter](https://github.com/beastoin/agent-flutter) (Marionette is integrated in debug builds). Install once: `npm install -g agent-flutter-cli`.

Edit → Verify → Evidence loop:
1. Edit code, hot restart: `kill -SIGUSR2 $(pgrep -f "flutter run" | head -1)`
2. Connect: `AGENT_FLUTTER_LOG=/tmp/flutter-run.log agent-flutter connect`
3. Verify: `agent-flutter snapshot -i`
4. Interact: `agent-flutter press @e3` / `press 540 1200` / `find type button press` / `fill @e5 "text"` / `dismiss`
5. Evidence: `agent-flutter screenshot /tmp/evidence.png`

Key rules:
- Must reconnect after every hot restart (kills VM Service session).
- Refs go stale frequently — always re-snapshot before every interaction. Use `press x y` as fallback.
- `AGENT_FLUTTER_LOG` must point to flutter run stdout (not logcat).
- Prefer `find type X` / `find key "name"` over hardcoded `@ref`. Use catalog `omi.*` keys on new controls.
- Full command reference: `agent-flutter schema`.
