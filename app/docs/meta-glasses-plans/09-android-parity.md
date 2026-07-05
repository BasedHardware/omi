# 09 — Android parity

## Goal
Bring the Meta glasses integration to Android. Today it is iOS-only in several
places; the DAT plugin supports Android, but the app-side glue and manifest are
not wired.

> **Large.** Do it in stages: (A) build/registration works, (B) capture + mic,
> (C) gestures. Ship A first.

## Grounding
- Plugin README (`third_party/meta_wearables_dat_flutter/README.md`) §Android documents the required setup precisely — follow it verbatim:
  - `MainActivity` must extend `FlutterFragmentActivity` (not `FlutterActivity`) — Meta's camera-permission contract needs a `ComponentActivity`.
  - `minSdk = 31`, `ndkVersion = "28.2.13676358"`.
  - Add Meta's GitHub Packages Maven repo with a `read:packages` PAT (`GITHUB_TOKEN` / `github_token` in `android/local.properties`).
  - `AndroidManifest.xml`: `com.meta.wearable.mwdat.APPLICATION_ID`/`CLIENT_TOKEN` (`2020435062214461` / `AR|...` — same as iOS `MWDAT`), `DAM_ENABLED=true`, `ANALYTICS_OPT_OUT=true`, BLUETOOTH/BLUETOOTH_CONNECT/INTERNET perms, and the `omimeta` scheme `<intent-filter>` on the singleTop launcher activity.
- iOS-only app code to port or guard:
  - Gestures use `MPRemoteCommandCenter` via `AppDelegate` + `com.omi/meta_gestures`. Android has no equivalent through that channel — implement with Android `MediaSessionCompat` media-button callbacks in a platform plugin, or ship A/B without gestures and add C later.
  - Audio route: iOS uses `configureForBluetooth` on `com.omi.ios/audioSession`. Android mic routing over Bluetooth SCO needs its own handling.
  - `MetaWearablesProvider` currently does `if (Platform.isIOS)` around the audio-session call — extend with an Android branch (or a no-op that relies on the OS route).

## Steps (stage A)
1. `android/app/src/main/kotlin/.../MainActivity.kt` → `FlutterFragmentActivity`.
2. `android/app/build.gradle.kts`: `minSdk = 31`, `ndkVersion`.
3. `android/settings.gradle.kts`: add the GitHub Packages maven block; document the PAT in `app/AGENTS.md`.
4. `AndroidManifest.xml`: meta-data + perms + `omimeta` intent-filter (dev flavor mirrors iOS `dev.moni11811.omi` values).
5. Verify `startRegistration()` deep-links into Meta AI and returns via `omimeta://` on an Android device with Developer Mode.

## Steps (stage B/C)
6. Wire capture: reuse `MetaWearablesProvider`; add the Android audio-route handling; confirm photo store-and-forward works.
7. Gestures: Android `MediaSessionCompat` → forward media-button events to `com.omi/meta_gestures` with the same `tap`/`swipe_forward` payloads the provider already handles.

## Tests
- Keep `flutter analyze` clean cross-platform. Add a contract-test assertion that `AndroidManifest.xml` carries the MWDAT meta-data and `omimeta` scheme (mirror the iOS Info.plist test).
- Manual: register + capture on an Android device in Developer Mode.

## Acceptance
- Stage A: Android build registers glasses via Meta AI and lists them.
- Stage B: capture + photos work; queue/timeline parity with iOS.
- Stage C: temple-tap toggles capture on Android.
- No iOS regression; analyze clean; l10n unchanged.
