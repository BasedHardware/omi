# App (Flutter) — Operational Playbook

Inherits all rules from the root [`../AGENTS.md`](../AGENTS.md). This file adds app-specific operational guidance.

## iOS Launch Safety — MANDATORY for every agent (Codex included)

Every launch-crash regression in this repo shipped with green tests and a successful build+install. **Build success, install success, and unit tests are NOT launch proof.** Before ending any session that touched app code, run the launch gate and paste its verdict:

```bash
cd app && ./scripts/verify_ios_launch.sh   # local contributor tooling (not in repo); must print: LAUNCH GATE: PASS
```

If the device is locked, ask the user to unlock it — do NOT claim the app works without the gate passing. `SKIP_DEVICE=1` runs static checks only and never counts as proof.

Hard rules (each one is a past real incident, not theory):

- **Never build with Xcode-beta / never export `DEVELOPER_DIR`.** Binaries linked against the iOS 27 SDK require UIScene; `flutter_contacts` (and other plugins) force-unwrap `delegate.window` at registration and SIGTRAP before Dart starts. Build with the default stable Xcode: `env -u DEVELOPER_DIR flutter build ios --profile --flavor dev --no-codesign`. Verify: `vtool -show-build build/ios/iphoneos/Runner.app/Runner | grep sdk` → must be < 27.
- **Never add `UIApplicationSceneManifest` to `ios/Runner/Info.plist`** until every registered plugin is scene-safe (pinned by test "Runner keeps the legacy UIKit lifecycle").
- **Never point `.dev.env` at a tunnel/local URL and leave it.** Envied bakes the URL into `dev_env.g.dart` at build time and does NOT track `.dev.env` changes — restoring the file requires `dart run build_runner clean` + delete `lib/env/dev_env.g.dart` + full rebuild. Ship builds only with `API_BASE_URL=https://api.omi.me/`.
- **Never invent backend endpoints.** api.omi.me is production and cannot be patched from this repo — a route added under `backend/` does not exist for the installed app. Verify with `curl -o /dev/null -w '%{http_code}' -X POST https://api.omi.me/<route>`: 401/405 = exists, 404 = does not. Glasses photos ingest ONLY via the transcription-socket `image_chunk` path (`ingestCapturedImage`).
- **Keep SwiftProtobuf statically linked** (`use_frameworks! :linkage => :static` in `ios/Podfile`); the dynamic-framework hack = dyld crash at launch. The duplicate-class objc warning is harmless.
- **After any `pub get`/clean, restore `ios/Flutter/Flutter.podspec` to `17.0`** (it silently resets to 13.0).
- **After `build_runner clean`, run a FULL `dart run build_runner build --delete-conflicting-outputs`** — a filtered build leaves `assets.gen.dart`/`*.g.dart` missing and nothing compiles.
- **Do not delete working subsystems to satisfy a constraint you inferred.** Removing the audio session also silently killed gestures (media-remote events need an active audio session) and photo history (socket carries the uploads). If a constraint seems to demand deleting a working path, stop and ask.
- **Do not rewrite tests to bless a regression.** If a contract test blocks your change, the test is evidence — investigate why it exists before touching it.
- **Never leave a `--terminate-existing` launch retry loop running** after your verification finishes — it kills the user's live session.
- Debugging on-device: `xcrun devicectl device process launch --console` captures real app output; `idevicecrashreport -u 00008130-000C04D81891401C -k <dir>` pulls `.ips` crash reports (parse `faultingThread`). Console.app and `devicectl device console` show nothing for this device.

## Build Bootstrap

### Flavors
- **dev**: `com.friend.ios.dev` — uses `.dev.env`, Firebase project `based-hardware-dev`
- **prod**: `com.friend.ios` — uses `.prod.env`, Firebase project `based-hardware-prod`

### Generated Files (never edit manually)
| Generator | Source | Output | Command |
|-----------|--------|--------|---------|
| envied | `lib/env/dev_env.dart`, `lib/env/prod_env.dart` | `*.g.dart` (obfuscated secrets) | `flutter pub run build_runner build` |
| json_serializable | `@JsonSerializable` models | `*.g.dart` (fromJson/toJson) | `flutter pub run build_runner build` |
| pigeon | `lib/watch_interface.dart` | `lib/gen/flutter_communicator.g.dart` + iOS/Android stubs | `flutter pub run build_runner build` |
| flutter_gen | `pubspec.yaml` assets/fonts | `lib/gen/assets.gen.dart`, `lib/gen/fonts.gen.dart` | `flutter pub run build_runner build` |
| flutter_localizations | `lib/l10n/*.arb` | `lib/gen_l10n/app_localizations*.dart` | `flutter gen-l10n` |

### Setup Sequence
```bash
bash setup.sh ios    # or: bash setup.sh android
```
This handles: pub get, build_runner, gen-l10n, and flavor configuration.

### Firebase Config
Never run `flutterfire configure` — it overwrites prod credentials. Config files:
- Dev: `ios/Config/Dev/`, `android/app/src/dev/`, `lib/firebase_options_dev.dart`
- Prod: `ios/Config/Prod/`, `android/app/src/prod/`, `lib/firebase_options_prod.dart`

## Native Bridge

### Pigeon Interface (bidirectional, iOS ↔ Dart)
- Contract: `lib/watch_interface.dart` — 13 methods (recording, audio, battery, permissions)
- Dart side: `lib/gen/flutter_communicator.g.dart`
- iOS side: `ios/Runner/FlutterCommunicator.g.swift`
- Implementation: `ios/Runner/RecorderHostApiImpl.swift`
- After editing `watch_interface.dart`, regenerate: `flutter pub run build_runner build`

### MethodChannel (Phone Calls)
- Channel: `com.omi/phone_calls` + EventChannel `com.omi/phone_calls/events`
- Dart: `lib/services/phone_call_service.dart`
- iOS: `ios/Runner/PhoneCallsPlugin.swift`
- Methods: initialize, makeCall, endCall, toggleMute, toggleSpeaker

### Meta Wearables (DAT) — vendored & locally patched
- Plugin lives at `third_party/meta_wearables_dat_flutter` (path dep) and IS locally modified; don't `pub upgrade` it away.
- Only expose real DAT SDK APIs. Verify a method exists before wrapping it: `grep 'func <name>' <SDK>.xcframework/**/*.swiftinterface` (checkout under `SourcePackages/checkouts/meta-wearables-dat-ios`). No invented methods.
- Adding a plugin method = all 4 layers in sync: facade (`lib/meta_wearables_dat_flutter.dart`) → platform interface → method channel → native Swift handler. A Dart-only add throws `MissingPluginException` at runtime.
- App layering: `MetaWearablesService` (SDK wrapper) → `MetaWearablesProvider` (state, registered in `main.dart` via ProxyProvider on `CaptureProvider`) → pages. Keep session calls targeting only link-connected uuids (see `_sessionTargetUuid`).
- DAT needs iOS 17. `ios/Flutter/Flutter.podspec` `deployment_target` resets to 13.0 on `pub get`/clean — restore to `17.0`. Guarded by contract test "declares iOS DAT runtime requirements".
- Android DAT Maven needs GitHub Packages auth: set `GITHUB_TOKEN` or `android/local.properties` `github_token=...` with `read:packages`; never commit tokens.
- Mock Device Kit test harness: `flutter test integration_test/meta_glasses_mock_test.dart --flavor dev --dart-define=OMI_META_MOCK=true` (add `-d <ios-simulator-id>` when multiple devices are attached).

### Meta Wearables — addon backlog
- Nine ready-to-execute plans live in `docs/meta-glasses-plans/` (start at `README.md` for shared constraints + order). One plan per branch/PR.

### Coding Practices
- Debug-only/proof screens must gate on `kDebugMode`, never `!kReleaseMode` (that includes Profile installs and boots the app into the debug screen). Example: `lib/debug/meta_wearables_ui_proof.dart`.
- After a `--dart-define`-flagged verification build, always reinstall a normal build — never leave a flagged build on a device.
- Meta/DAT changes must keep `test/unit/omi4meta_reconstruction_contract_test.dart` green and `flutter gen-l10n` at zero untranslated.

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

Android has 26 total permissions in AndroidManifest.xml. iOS has 11 background modes + 10 consent strings.

## Test Strategy

### Test Structure
- `test/unit/` — Auth, tokens, preferences, audio utils
- `test/widgets/` — UI components (shimmer, waveform, transcript)
- `test/providers/` — State management (capture_provider, device_provider)
- `test/utils/` — Utility functions (localization helpers)

### Running Tests
```bash
bash test.sh           # runs all tests
flutter test           # same thing
flutter test test/unit/  # specific directory
```

### Test Patterns
- Mock singletons (SharedPreferencesUtil, AuthService, FirebaseAuth) since they aren't injectable
- Test state machine logic via minimal abstractions mirroring production flow
- Meta glasses mock coverage lives in `integration_test/meta_glasses_mock_test.dart` and is gated by `kDebugMode && OMI_META_MOCK`.

## Localization (l10n)

- All user-facing strings must use `context.l10n.keyName`
- 49 locales: English (template) + 48 translations in `lib/l10n/`. Don't trust this count from memory — enumerate with `ls lib/l10n/app_*.arb`.
- Template: `lib/l10n/app_en.arb`
- Add keys via `jq` (never read full ARB — they're large). Use skill `add-a-new-localization-key-l10n-arb`
- Translate all locales — use skill `omi-add-missing-language-keys-l10n` for real translations
- Regenerate after changes: `flutter gen-l10n`. Task is only complete when this command emits zero "untranslated message(s)" warnings. To get the exact missing-key list, temporarily add `untranslated-messages-file: /tmp/untranslated.json` to `l10n.yaml` and re-run.

## Auth & Security

### Token Lifecycle
1. `getAuthHeader()` in `lib/backend/http/shared.dart` checks token expiry (5-minute buffer)
2. If expired, calls `AuthService.instance.getIdToken()` for Firebase refresh
3. Token stored in SharedPreferencesUtil with expiration timestamp
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
- Agent proxy WS: derived from apiBaseUrl (api.omi.me → agent.omi.me)

## Codegen Rules

- Run `flutter pub run build_runner build` after changing: env files, model annotations, pigeon contracts, or pubspec assets
- Run `flutter gen-l10n` after changing ARB files
- Never edit files ending in `.g.dart` or `.gen.dart`
- If build_runner fails with conflicts: `flutter pub run build_runner build --delete-conflicting-outputs`

## App Flows & E2E

- See `e2e/SKILL.md` for navigation architecture, screen map, widget patterns, and 34 reference flows
- See `e2e/flows/*.yaml` for individual flow definitions
- agent-flutter (Marionette) for programmatic UI interaction — see root AGENTS.md for setup
