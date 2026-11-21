# Native mobile apps

Two native rewrites of the Omi mobile app, side by side:

- `ios/` the SwiftUI app (Swift 6, SwiftPM packages, XcodeGen)
- `android/` the Kotlin and Jetpack Compose app, a port of the iOS app with the same module layering

Both talk to the same backend (`backend/`) with the same API contract as the Flutter app in `app/`.
iOS and Android are on par with each other: `android/docs/PARITY.md` is rebuilt from the code of both
apps by `android/Tools/parity/parity_table.py`. Neither is at full parity with the Flutter app yet;
`ios/docs/PARITY-AUDIT.md` lists the missing, partial and native-only features.

## ios/

Installs over the Flutter app (same bundle id) and keeps the user signed in with their paired Omi and
offline recordings.

Layout: `App/` the shell (tabs, header, routing, composition root), `Packages/` the SwiftPM packages
(`OmiCore` models, `OmiNetwork` API client and generated DTOs, `OmiPersistence`, `OmiService` stores
and logic, `OmiDesign` tokens and strings, `OmiFeatures` one module per feature), `Extensions/`
widgets, Live Activity and notification service, `Watch/` the watch recorder, `Tools/` codegen and
dev helpers, `docs/` structure, parity and ADRs.

Build (Xcode 26+, XcodeGen, SwiftLint):

```
cd native_mobile_apps/ios
cp Config/Secrets.xcconfig.example Config/Secrets.xcconfig
xcodegen generate
make test
open Omi.xcodeproj
```

`make check` runs the full gate: package tests, lint, Debug and Release build, string catalog check
and the DTO check. Strings come from the Flutter app's ARB files (`app/lib/l10n`) and DTOs from the
backend's OpenAPI spec; inside this repository both are found automatically. Release builds use the
Flutter app's production Firebase file (`app/setup/release-firebase`); Debug builds use the local
Firebase emulator config.

## android/

One Gradle module per SwiftPM package of the iOS app (`core`, `network`, `persistence`, `service`,
`design`, `features`, `app`) plus `device` (the wearable on the Flutter app's native BLE layer),
`audio`, `calls` and `wear`. Strings are generated from the iOS string catalog and DTOs from the same
OpenAPI spec (`android/Tools/`).

Build (JDK 17+, Android SDK 36):

```
cd native_mobile_apps/android
./gradlew :app:assembleDebug
./gradlew test
```

The app uses the `google-services` Gradle plugin: provide `app/google-services.json` for a Firebase
project, or the local demo config used for development. It is not committed.

## Local backend

Both apps run against the local harness (`make dev-up` at the repository root). iOS reads the host
from `ios/Config/Secrets.xcconfig`; the Android debug build talks to `127.0.0.1` through
`adb reverse tcp:8000 tcp:8000` and `adb reverse tcp:9099 tcp:9099`.

## Proposed backend field

The conversation summary card shows a one-line gist from `structured.short_summary`. The backend does
not send that field yet; its OpenAPI half lives in `ios/docs/backend-patches/` and both apps' DTO
generators apply it. Without the field the card simply shows no gist.
