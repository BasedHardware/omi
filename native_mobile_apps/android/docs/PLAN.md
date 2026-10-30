# Omi native Android: plan

Native Kotlin + Jetpack Compose port of the native SwiftUI app (`~/CODING/omi-native`, source
pinned at `eceb1de`), with the exact iOS design. Method: the Flow iOS -> Android playbook
(`~/CODING/flow/android/CONVERSION_APPROACH.md`): tokens 1:1 under the same names, a reference
screen first, then screen by screen with the Swift file open next to the Kotlin one.

## Decisions

| Topic | Decision | Why |
|---|---|---|
| Source of truth | omi-native iOS (design + behavior), not the Flutter app | Product owner: Android copies the native iOS app exactly |
| Modules | `core <- network <- persistence <- service <- design <- features <- app`, same as the SwiftPM packages | 1:1 file mapping, enforced dependency direction |
| DI | Manual `AppEnvironment` + one CompositionLocal per store (`service/Environment.kt`) | iOS composes `AppEnvironment.swift` by hand and injects via `.environment`; no Hilt/KSP |
| State | Stores hold Compose snapshot state (`var x by mutableStateOf`) | Same semantics as `@Observable`: screens recompose on what they read; stores port line by line |
| API | One interface + implementation per domain in `network/endpoints/<Domain>.kt`, `APIClient` delegates (`by`) | Swift spreads `APIClient` over `+Domain.swift` extensions; this keeps parallel agents out of each other's files |
| DTOs | Generated from the same OpenAPI spec and the same `TARGET_SCHEMAS` as Swift (`Tools/api/generate_kotlin_openapi_types.py`) | Identical type and property names, mappers port mechanically |
| Strings | `Tools/l10n/xcstrings2android.py`: iOS `Localizable.xcstrings` -> `values-*/strings.xml`, ARB fallback for Android-only keys; `L("key")` | Same keys and translations as iOS, 49 locales |
| Font | SF Pro Display from `omi-fresh/app/assets/fonts` (the Flutter app already ships it on Android) | Exact look. Open: licence decision before a store release; no upright semibold (w600 renders bold, as in Flutter) |
| Icons | `SFImage("sf.name")`, Material Symbols Rounded variable font, map in `SFSymbols.kt`, checked by `Tools/icons/check_symbols.py` | SF Symbols cannot ship on Android; call sites keep the SF names |
| Shapes | `ContinuousRoundedShape` (Apple squircle control points) | `.continuous` corners everywhere on iOS |
| Controls | iOS-style own components (menu, context menu, sheets, grouped lists, press feedback without ripple) | Material defaults would break the 1:1 look |
| Persistence | `FlutterSharedPreferences`, `flutter.` keys and encodings (ADR 0002 of omi-native) | In-place update over the Flutter Android app keeps settings; rollback still readable |
| Package | namespace + classes `com.friend.ios`; release applicationId `com.friend.ios`; debug `com.friend.ios.native.dev` | Same component names as the Flutter app for an in-place update; debug installs next to Flutter |
| Native code reuse | Flutter's Kotlin under `app/android/.../com/friend/ios/{ble,batch,phonemic,limitless,sync,fgs}` (MIT) for capture | Already native and tested; replace Pigeon with Kotlin interfaces |

## Platform mapping

| iOS | Android |
|---|---|
| CoreBluetooth Omi driver, MCUmgr DFU | Flutter's `OmiBleManager` / `OmiBleForegroundService` + companion device; nRF mcumgr-android |
| Phone mic + Opus, background audio | Flutter's `phonemic` (AudioRecord, JNI Opus, vendored libopus), foreground service `microphone` |
| `/v4/listen` WebSocket, SSE chat | OkHttp WebSocket, OkHttp streaming lines |
| Live Activity | Ongoing notification (Android 16 Live Updates where available) |
| Widgets | Glance |
| Siri / App Intents / Spotlight | App shortcuts, dynamic shortcuts |
| APNs via FCM | FCM |
| CallKit + Twilio | ConnectionService + Twilio Voice Android |
| HealthKit | Health Connect |
| EventKit Reminders | dropped (Google Tasks via backend integration) |
| Apple Watch (`Watch/`, WatchConnectivity) | Wear OS app `:wear` (same applicationId), Wearable Data Layer: MessageClient control, one ChannelClient stream per recording, DataItems for state and queued messages (`core/.../watch/WatchWire.kt`) |
| Stripe in Safari view | Custom Tabs |
| Universal links, `omi://` | App Links + intent filters |

## Phases

| Phase | Content | Done when |
|---|---|---|
| A0 Foundation | Gradle, tokens, components, icons, strings, DTOs, prefs, auth, AppEnvironment, debug launch extras | done 2026-10-08 |
| A1 Reference screen | Shell + Memories with real data; iOS side-by-side; product owner's design OK | screenshot pair approved |
| A2 Read | Home (TodayScreen), Conversations + detail, Search, All tasks, Memory sheets | PARITY rows green |
| A3 Chat / agent | ChatScreen, SSE, hand-over, agent runs | |
| A4 Capture | phone mic, Omi BLE, listen socket, foreground services, offline sync | real Omi on a real phone |
| A5 Settings | full tree per omi-native `docs/STRUCTURE.md` | |
| A6 Onboarding + system | sign-in (Google), onboarding, push, widgets, live notification, deep links | |
| A7 Migration + hardening | read Flutter files in place (`app_flutter/wals.json`, audio), CI, release signing | in-place update test passes |

## Working rules (from the iOS build)

- Parity is tracked per iOS screen in `docs/PARITY.md` and checked in code, not in docs.
- Design: one screen + side-by-side screenshot to the product owner before rolling a look out.
- Parallel agents: at most 3-4 Gradle builds at once; each owns its files (`YOU OWN` / `Do NOT edit`); new strings only via the generator.
- Test against `alice` (or fresh test uids); the product owner's real account read-only.
- Stubs carry `TODO(visual-stub)`; `grep -rn "TODO(visual-stub)"` is the open list.

## Dev loop

```
python3 Tools/l10n/xcstrings2android.py           # strings
python3 Tools/api/generate_kotlin_openapi_types.py # DTOs
python3 Tools/icons/check_symbols.py               # every SF Symbol mapped
./gradlew :app:installDebug
adb reverse tcp:8000 tcp:8000 && adb reverse tcp:9099 tcp:9099
adb shell am start -n com.friend.ios.native.dev/com.friend.ios.MainActivity \
  --es omiAutoSignIn alice --ez omiSkipOnboarding true --es omiTab memory
```
