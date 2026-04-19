# Omi App — CLAUDE.md Operational Playbook

> **For AI agents and engineers working on the Flutter app.**
> Read this before making any change to `app/`. It is the authoritative source for build rules,
> operational guardrails, and contribution governance.

---

## Table of Contents

1. [Flow Doc Governance](#1-flow-doc-governance)
2. [Build Bootstrap](#2-build-bootstrap)
3. [Codegen Rules](#3-codegen-rules)
4. [Native Bridge Gotchas](#4-native-bridge-gotchas)
5. [Permission Matrix](#5-permission-matrix)
6. [Test Strategy](#6-test-strategy)
7. [L10n Rules](#7-l10n-rules)
8. [Security Notes](#8-security-notes)

---

## 1. Flow Doc Governance

### Mandatory Update Rule

> **Any PR with significant app changes MUST update the corresponding flow doc.**

| Change type | Required doc update |
|---|---|
| Navigation change, new screen, route rename | `docs/flows/ui-flow.md` + regenerate `generated/ui-flow.screens.yaml` |
| API module change, schema change, websocket event change, deep-link handler change | `docs/flows/data-flow.md` + regenerate `generated/data-flow.inventory.yaml` |
| Provider added/removed/renamed, ProxyProvider chain modified, `lib/main.dart` provider registration | `docs/flows/state-management.md` + regenerate `generated/state-management.providers.yaml` |

### Flow Docs Location

```
app/docs/flows/
  ui-flow.md                          ← Screen registry + navigation graph
  data-flow.md                        ← API chains, websocket, error paths
  state-management.md                 ← Provider tree, blast radius, mutation ownership

app/docs/flows/generated/
  ui-flow.screens.yaml                ← Machine-diffable screen index
  data-flow.inventory.yaml            ← Machine-diffable API/event inventory
  state-management.providers.yaml     ← Machine-diffable provider graph
```

### Generation Scripts

```bash
# Regenerate all artifacts after any relevant code change:
bash app/scripts/agent/generate_ui_flow_index.sh
bash app/scripts/agent/generate_data_flow_inventory.sh
bash app/scripts/agent/generate_state_graph.sh
```

### PR Checklist Enforcement

Until CI enforcement is added, every PR description must include this checklist:

```markdown
## Flow Doc Checklist
- [ ] No navigation/screen changes  OR  `docs/flows/ui-flow.md` updated + YAML regenerated
- [ ] No API/schema/WS/deep-link changes  OR  `docs/flows/data-flow.md` updated + YAML regenerated
- [ ] No provider tree changes  OR  `docs/flows/state-management.md` updated + YAML regenerated
```

---

## 2. Build Bootstrap

### Prerequisites (generated files — must exist before `flutter run`)

| File | How to generate |
|---|---|
| `lib/firebase_options_dev.dart` | `flutterfire configure --project=<dev-project> --out=lib/firebase_options_dev.dart` |
| `lib/firebase_options_prod.dart` | `flutterfire configure --project=<prod-project> --out=lib/firebase_options_prod.dart` |
| `lib/env/env.g.dart` | `dart run build_runner build --delete-conflicting-outputs` |
| `lib/l10n/` (generated) | `flutter gen-l10n` (or `flutter pub run intl_utils:generate`) |

### Flavors

The app uses three flavors: `dev`, `staging`, `prod`.

```bash
flutter run --flavor dev          # local development
flutter run --flavor staging      # pre-release testing
flutter run --flavor prod         # production build
```

Flavor-specific entry points live in `lib/flavors/`. Do **not** hardcode flavor-specific values
outside of these files.

### Full Local Setup Sequence

```bash
# 1. Install dependencies
flutter pub get

# 2. Generate all code (env, JSON serialization, etc.)
dart run build_runner build --delete-conflicting-outputs

# 3. Generate l10n
flutter gen-l10n

# 4. Run on device (dev flavor)
flutter run --flavor dev
```

For platform-specific native setup see `setup.sh` (iOS/Android certificates, provisioning).

---

## 3. Codegen Rules

### Files That Are Auto-Generated — Never Edit Manually

| Pattern | Generator |
|---|---|
| `lib/env/env.g.dart` | `build_runner` (`envied` package) |
| `lib/firebase_options_*.dart` | `flutterfire` CLI |
| `lib/l10n/app_localizations*.dart` | `flutter gen-l10n` |
| `lib/watch_interface/watch_interface.dart` (Pigeon) | `flutter pub run pigeon` — see `pigeons/watch_interface.dart` |
| `**/*.g.dart`, `**/*.freezed.dart` | `build_runner` |

### Regeneration Order

1. `dart run build_runner build --delete-conflicting-outputs`
2. `flutter gen-l10n`
3. Pigeon (only if `pigeons/` source changed): `flutter pub run pigeon --input pigeons/watch_interface.dart`

### Adding a New Generated Field

- Add source in the appropriate annotation (`@EnviedField`, `@JsonSerializable`, etc.)
- Run `build_runner build`
- Commit **both** the source file and the `.g.dart` output

---

## 4. Native Bridge Gotchas

### MethodChannel Catalog

| Channel name | Platform | Purpose | Dart side | Native side |
|---|---|---|---|---|
| `com.friend.ios/notifyOnKill` | iOS | Notify app on kill | `lib/services/notifications.dart` | `ios/Runner/AppDelegate.swift` |
| `com.friend.android/notifyOnKill` | Android | Notify app on kill | `lib/services/notifications.dart` | `android/.../MainActivity.kt` |
| `storageChannel` | Both | Secure key-value storage for auth tokens | `lib/backend/auth/client.dart` | Platform-specific plugin |

### Pigeon Contract Rules (`lib/watch_interface/`)

- The Pigeon-generated file (`watch_interface.dart` in generated form) **must never be edited manually**.
- To add a new method: edit `pigeons/watch_interface.dart`, then run `flutter pub run pigeon --input pigeons/watch_interface.dart`.
- Both the Dart host API and the Swift/Kotlin handler must be updated in the same PR.
- Breaking changes to the Pigeon contract require a version bump comment at the top of the pigeon source.

### BLE / Device Bridge

- BLE operations go through `lib/services/devices/` and `DeviceProvider`.
- Never call BLE APIs directly from UI widgets or page files.
- Connection state is owned by `DeviceProvider`; UI reads it via `context.watch<DeviceProvider>()`.

---

## 5. Permission Matrix

| Feature | iOS permission | Android permission | Declared in |
|---|---|---|---|
| Audio capture (conversations) | `NSMicrophoneUsageDescription` | `RECORD_AUDIO` | `Info.plist` / `AndroidManifest.xml` |
| Bluetooth (device connection) | `NSBluetoothAlwaysUsageDescription` | `BLUETOOTH_SCAN`, `BLUETOOTH_CONNECT` | `Info.plist` / `AndroidManifest.xml` |
| Background audio | `UIBackgroundModes: audio` | `FOREGROUND_SERVICE` | `Info.plist` / `AndroidManifest.xml` |
| Notifications (push) | `UNUserNotificationCenter` request | `POST_NOTIFICATIONS` (API 33+) | Requested at runtime |
| Location (BLE scan on Android 11-) | — | `ACCESS_FINE_LOCATION` | `AndroidManifest.xml` |
| Camera (avatar upload) | `NSCameraUsageDescription` | `CAMERA` | `Info.plist` / `AndroidManifest.xml` |
| Photo library | `NSPhotoLibraryUsageDescription` | `READ_MEDIA_IMAGES` | `Info.plist` / `AndroidManifest.xml` |

**Rule:** Permission request dialogs must use the user-facing string from `lib/l10n/` — never hardcode English-only strings in permission rationale.

---

## 6. Test Strategy

### Test Depth by Change Type

| Change type | Minimum test requirement |
|---|---|
| UI-only (widget layout, color, copy) | Widget test for affected widget; golden test if visual regression risk |
| Provider / state mutation | Unit tests for all mutator methods; mock `ApiService` |
| API / data layer (`lib/backend/http/api/`) | Unit tests with mocked `http.Client`; test happy path + 401 + 5xx |
| Native bridge (Pigeon/MethodChannel) | Platform channel mock in unit test; manual device smoke test required |
| Deep-link / notification routing | Unit test for route-parsing logic; integration test for nav outcome |
| New screen / navigation change | Widget test; update `ui-flow.md` |

### Commands

```bash
# Unit + widget tests
flutter test

# Integration tests (requires connected device/emulator)
flutter test integration_test/

# With coverage
flutter test --coverage
genhtml coverage/lcov.info -o coverage/html
```

---

## 7. L10n Rules

### Always Use `context.l10n`

```dart
// ✅ Correct
Text(context.l10n.settingsTitle)

// ❌ Wrong — hardcoded string
Text('Settings')
```

### Adding a New String

1. Add the key and English value to `lib/l10n/intl_en.arb`.
2. Add the same key (translated) to all other `intl_*.arb` files, or mark with `@<key>` metadata if translation is pending.
3. Run `flutter gen-l10n` to regenerate `lib/l10n/app_localizations*.dart`.
4. Commit both the `.arb` files and the generated output.

### Regeneration Command

```bash
flutter gen-l10n
```

The configuration lives in `l10n.yaml` at the `app/` root.

---

## 8. Security Notes

### Auth Token Lifecycle

- Auth tokens are stored via the secure storage `MethodChannel` (see §4), never in `SharedPreferences` or plain files.
- Token refresh is handled in `lib/backend/auth/client.dart`.
- On a 401 response: the client attempts one silent refresh; on a second 401, it calls `AuthProvider.signOut()` and navigates to the auth screen.
- Never log token values — even at debug level.

### 401 Retry / Sign-out Behavior

```
Request → 401
  → attempt token refresh (one time)
  → if refresh succeeds: retry original request
  → if refresh fails (401 again): AuthProvider.signOut() → navigate to /auth
```

### Transport

- All API calls use HTTPS. The base URL is injected from `lib/env/env.g.dart`.
- WebSocket connections use `wss://`.
- Never disable certificate validation in release builds.

### Deep Links

- Deep-link schemes are registered in `Info.plist` (iOS) and `AndroidManifest.xml` (Android).
- All incoming deep-link parameters are validated before being passed to providers or navigation.
- See `lib/core/app_shell.dart` and `lib/services/notifications.dart` for the entry points.
