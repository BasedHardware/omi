# Omi for Android, native (Kotlin, Compose)

Kotlin and Jetpack Compose port of the native iOS app in `../ios`. Same backend, same API
contract, same module layering: one Gradle module per SwiftPM package of the iOS side.

## Layout

- `core/` models, `network/` API client and DTOs, `persistence/` storage, `service/` stores and logic,
  `design/` tokens and strings, `features/` one module per feature, `app/` the application shell
- `device/` the Omi wearable on the Flutter app's native BLE layer
- `audio/` capture, `calls/` phone calls (Twilio Voice and Telecom), `wear/` the Wear OS app
- `Tools/` dev helpers, `docs/` plan, parity audit and per-area notes

## Build

Requires JDK 17+ and the Android SDK (compileSdk 36, minSdk 29).

```
./gradlew :app:assembleDebug
./gradlew test
```

The app applies the `google-services` Gradle plugin. Put your own `app/google-services.json` in
place for a real Firebase project, or use the local demo configuration for development. The file
is not committed here.
