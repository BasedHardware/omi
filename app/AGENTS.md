# App (Flutter) — Operational Playbook

Inherits all rules from the root `../AGENTS.md`. This file adds app-specific operational guidance.

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
- No integration tests currently (integration_test dependency exists but unused)

## Localization (l10n)

- All user-facing strings must use `context.l10n.keyName`
- 34 locales: English (template) + 33 translations in `lib/l10n/`
- Template: `lib/l10n/app_en.arb`
- Add keys via `jq` (never read full ARB — they're large). Use skill `add-a-new-localization-key-l10n-arb`
- Translate all locales — use skill `omi-add-missing-language-keys-l10n` for real translations
- Regenerate after changes: `flutter gen-l10n`

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
- agent-flutter (Marionette) for programmatic UI interaction — see root CLAUDE.md for setup

### iOS Simulator Known Limitations

| Issue | Workaround |
|-------|-----------|
| ASWebAuthenticationSession blocks Google Sign-In (system dialog, not automatable) | Use `FirebaseAuth.instance.signInWithCustomToken(token)` via VM Service evaluate |
| `agent-flutter scroll` fails (uses ADB/transport.swipe, Simulator window disconnected) | Scroll via VM Service Dart evaluation: `pos.jumpTo()` on Scrollable widgets |
| Simulator.app window shows Home Screen (not app) when booted via SSH user | Use `simctl screenshot` for true device state; use Marionette/VM Service for interaction |
| No `simctl` touch/swipe API | VM Service evaluate for Flutter-level interaction; cliclick only works if Simulator window is synced |
| iOS keychain persists through app uninstall | `xcrun simctl erase <UDID>` for full reset |
| iOS onboarding is shorter than Android (language only → home) | Mark skipped steps as pass with platform note |

**VM Service scroll expression** (target app root library):
```dart
(() { var count = 0; void visit(Element el) { if (el.widget is Scrollable) { try { final s = (el as StatefulElement).state as ScrollableState; final p = s.position; if (p.maxScrollExtent > 0 && p.pixels < p.maxScrollExtent) { p.jumpTo((p.pixels + 500).clamp(0.0, p.maxScrollExtent)); count++; } } catch (_) {} } el.visitChildren(visit); } WidgetsBinding.instance.rootElement?.visitChildren(visit); return count; })()
```

**iOS simulator auth** (dev Firebase tokens rejected by prod API — needs local backend):
```bash
# .dev.env must point to a local/dev backend
API_BASE_URL=http://<your-backend-host>:<port>/
USE_WEB_AUTH=false
USE_AUTH_CUSTOM_TOKEN=true
# Regenerate envied after .dev.env change, rebuild app
```
