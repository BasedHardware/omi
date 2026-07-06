# Troubleshooting

Common pitfalls and how to recognise them.

## Build / setup

- **iOS: "Missing MWDATCore" / "Missing MWDATCamera"** — Swift Package
  Manager support for Flutter plugins is not enabled. Run
  `flutter config --enable-swift-package-manager` once and rebuild.
  Xcode 15.4+ is required.
- **Android: `Could not find com.meta.wearable:mwdat-core...`** —
  GitHub Packages credentials are missing. Add a PAT with
  `read:packages` scope to `local.properties`:
  ```
  github_token=ghp_...
  ```
  or export `GITHUB_TOKEN`. Make sure your app's
  `settings.gradle.kts` includes the GitHub Packages repository in
  `dependencyResolutionManagement.repositories`.
- **`pluginClass: MetaWearablesDatPlugin not found`** when running the
  example — ensure the plugin native folder (`ios/`, `android/`)
  contains the corresponding source file. Re-run
  `flutter pub get`.

## Runtime — registration

- **iOS: Meta AI says "Allow" but never reopens your app, and your app
  never receives a deep-link callback** — the most common cause is
  that your `MWDAT.AppLinkURLScheme` in `Info.plist` is missing the
  `://` suffix. Meta AI builds the callback URL by *literally
  concatenating* this value with the query string
  `?authorityKey=...&metaWearablesAction=register&...`. If you wrote
  `<string>myapp</string>` instead of `<string>myapp://</string>`,
  the callback becomes `myapp?authorityKey=...` — not a valid URL —
  and iOS silently drops it. No error toast, no crash, no log on the
  Flutter side. Fix: ensure the `AppLinkURLScheme` value ends with
  `://`:
  ```xml
  <key>AppLinkURLScheme</key>
  <string>myapp://</string>
  ```
  The scheme **without** `://` must also appear under
  `CFBundleURLTypes[].CFBundleURLSchemes`. Verify with
  `MetaWearablesDat.dumpDiagnostics()` — `MWDAT.AppLinkURLScheme`
  should print with the trailing `://`.
- **"Internal error" right after tapping "Allow" in the Meta AI app** —
  Meta AI tried to redirect back into your app via the registration
  callback URL, but the redirect failed. Symptoms: Meta AI opens
  cleanly, you tap **Allow**, you stay on the Meta AI screen, and a
  generic "Internal error" toast appears in Meta AI a second later
  (the SDK gave up waiting for the round-trip). The most common cause:

  **Your `AppLinkURLScheme` (and matching `CFBundleURLSchemes` /
  Android `<data android:scheme>`) contains an underscore or some
  other character that is not legal in an RFC 3986 URL scheme.**
  Per RFC 3986 a scheme may only contain `ALPHA / DIGIT / "+" / "-" /
  "."`, starting with a letter. iOS LaunchServices is forgiving and
  will register `my_app` as a URL type, but Meta's redirect-URL
  builder validates the scheme strictly and refuses to issue the
  callback URL. Result: Allow → "Internal error" → no
  `[SceneDelegate] forwarding URL:` log → no `handleUrl` log on the
  Flutter side, because no URL was ever sent. Fix: rename the scheme
  to alphanumeric only (e.g. `metawearablesdatexample` instead of
  `meta_wearables_dat_flutter_example`) in three places:
    1. `MWDAT.AppLinkURLScheme` in `Info.plist`
    2. `CFBundleURLTypes[].CFBundleURLSchemes` in `Info.plist`
    3. `<data android:scheme="...">` in
       `android/app/src/main/AndroidManifest.xml`

  Two other things sometimes trigger the same toast — worth fixing at
  the same time:
    1. Add `Analytics: { OptOut: true }` inside the `MWDAT` dict so the
       SDK does not try to upload telemetry to
       `api2.ar.meta.com` with a Developer Mode `ClientToken`. A
       failed analytics handshake surfaces as the same generic
       "Internal error".
    2. In `UIBackgroundModes` use `audio` (not `processing`). The
       streaming session expects the audio background mode to be
       declared even if you never start a stream during registration;
       the official sample relies on it.

  Two URL-forwarding fixes depending on your iOS app lifecycle:
  - **Scene-based lifecycle** (`UIApplicationSceneManifest` present in
    `Info.plist` + a `SceneDelegate.swift` — the Flutter default on
    Flutter ≥ 3.32): override `scene(_:openURLContexts:)` and
    `scene(_:willConnectTo:options:)` on your `SceneDelegate` and
    post the URL on `NotificationCenter` under the
    `MetaWearablesDatHandleURL` name. The plugin subscribes to that
    notification at registration time and routes the URL to the SDK
    itself — see
    [`example/ios/Runner/SceneDelegate.swift`](../example/ios/Runner/SceneDelegate.swift)
    and the
    [registration-flow doc](registration_flow.md#ios-scenedelegate-wiring-required-for-scene-based-apps)
    for the full snippet.
  - **Classic AppDelegate lifecycle** (no scene manifest): nothing to
    do. The plugin registers itself as a
    `FlutterApplicationLifeCycleDelegate` and the OS routes the URL
    to it via `application(_:open:options:)` automatically.
- **"Internal error" appears even before Meta AI opens** (iOS) —
  Developer Mode is off in the Meta AI app. Fix: open the Meta AI
  mobile app → Settings → enable **Developer Mode** (older builds:
  Settings → Advanced → Developer Mode). Restart your Flutter app and
  try again. See [Getting started, step
  4](getting_started.md#4-enable-developer-mode-in-the-meta-ai-app).
- **Android: `RegistrationError(code: HTTP_REQUEST_FAILED, message:
  ".../oauth/.../register?... HTTP 401 ...")`** — same root cause as
  the iOS "Internal error" above: Developer Mode is off in the Meta
  AI app on the test phone. Unlike iOS (which short-circuits with a
  generic toast inside Meta AI), Android's DAT SDK proceeds to make a
  real HTTP attestation call against `api2.ar.meta.com`, and the
  Wearables Developer Center rejects your unverified `APPLICATION_ID`
  with `401 Unauthorized`. The error surfaces in your Flutter app's
  registration state stream as `RegistrationStateError`. Fix: enable
  Developer Mode on the phone (Meta AI → Settings → Developer Mode),
  then `flutter run` again — no rebuild of your APK is needed. The
  `APPLICATION_ID = "0"` and `CLIENT_TOKEN = "0"` values in your
  `AndroidManifest.xml` are correct for Developer Mode; do not change
  them. See [Getting started, step
  4](getting_started.md#4-enable-developer-mode-in-the-meta-ai-app).
- **`registrationStateStream` stays `unavailable`** on Android — the
  user denied `BLUETOOTH_CONNECT`, or `Wearables.initialize` ran
  before the permission was granted. Call `requestAndroidPermissions`
  and verify `granted == true` before any registration call.
- **iOS `startRegistration` throws `REGISTRATION_ERROR`, message says
  `configurationInvalid` (raw value 1)** — Meta AI never opens. The
  exact error message embedded in `MWDATCore` v0.6.0 is:

  > `[Registration] Partial attestation configuration detected.
  > ClientToken and/or teamID are missing. All values must be present.
  > Add missing values to Info.plist under MWDAT configuration.`

  In v0.6.0 the SDK requires **all four** MWDAT keys to be present and
  non-empty, even in Developer Mode. The values of `ClientToken` /
  `TeamID` aren't validated against the Wearables Developer Center
  when `MetaAppID = "0"`, but they still have to exist. The minimum
  working dict is:
  ```xml
  <key>MWDAT</key>
  <dict>
    <key>AppLinkURLScheme</key>
    <string>your_url_scheme://</string>
    <key>MetaAppID</key>
    <string>0</string>
    <key>ClientToken</key>
    <string>developer-mode-placeholder</string>
    <key>TeamID</key>
    <string>$(DEVELOPMENT_TEAM)</string>
  </dict>
  ```
  `$(DEVELOPMENT_TEAM)` is expanded by Xcode at build time from the
  Signing & Capabilities tab; confirm it actually resolved with
  `plutil -p build/ios/iphoneos/Runner.app/Info.plist | grep -A 6 MWDAT`.
  If `TeamID` shows up empty, set the team in Xcode or hardcode your
  10-character Apple Developer Team ID directly in the plist.

  Other things that can cause the same error:
  - `AppLinkURLScheme` doesn't match a scheme in `CFBundleURLTypes`.
  - `LSApplicationQueriesSchemes` is missing `fb-viewapp` (older
    SDK versions preflight `canOpenURL("fb-viewapp://")`).
  - The Meta AI app isn't installed, or there's no network.

  The plugin's `MetaWearablesDat.dumpDiagnostics()` returns the runtime
  plist + a `preflight` summary so you can inspect what the SDK sees
  without rebuilding — call it from your app and print the result.
- **iOS: tapping "Allow" reopens the host app, but registration
  state never advances to `registered`** — your `SceneDelegate.swift`
  is the Flutter default (an empty `FlutterSceneDelegate` subclass)
  and is silently swallowing the inbound URL. iOS delivers the Meta
  AI callback URL to `scene(_:openURLContexts:)` on the host app's
  scene delegate, and `FlutterSceneDelegate` does not auto-forward it
  to plugins. Add the two `scene(...)` overrides shown in
  [Getting started, step 8](getting_started.md#2-ios-setup) (or in
  [registration_flow.md](registration_flow.md#ios-scenedelegate-wiring-required-for-scene-based-apps))
  to `ios/Runner/SceneDelegate.swift`. After the fix you should see
  `[meta_wearables_dat_flutter] SceneDelegate <- open url ...` in the
  device log right after tapping Allow.
- **Android: deep link does nothing** — your `MainActivity` is
  missing `launchMode="singleTop"` or the `<intent-filter>` block.
  Re-check `AndroidManifest.xml` against the snippet in
  [Getting started](getting_started.md#3-android-setup).

## Runtime — camera permission

- **`MISSING_FRAGMENT_ACTIVITY` on Android** — your `MainActivity`
  extends `FlutterActivity` instead of `FlutterFragmentActivity`. Meta's
  `RequestPermissionContract` requires a `ComponentActivity`.

## Runtime — streaming

- **Android: `SESSION_ERROR: No eligible device found`** even though the
  glasses are paired, BLE-connected, and registration succeeded — the
  `DAM_ENABLED` manifest key is missing. The SDK's internal `DatConfiguration`
  reads `com.meta.wearable.mwdat.DAM_ENABLED` on startup and stores it as a
  `usesDam` flag. The `SessionManager` uses this flag when building the session
  request; without it the eligibility check silently fails regardless of which
  device selector you use. Add:
  ```xml
  <meta-data
      android:name="com.meta.wearable.mwdat.DAM_ENABLED"
      android:value="true" />
  ```
  inside `<application>` in `AndroidManifest.xml`. A logcat warning
  `W/MetaWearablesConfig: com.meta.wearable.mwdat.DAM_ENABLED not found in
  manifest metadata` confirms the key is missing.

- **Texture renders black** — most likely no frames are arriving.
  Common causes:
  - Glasses are not donned (worn). The Meta SDK gates streams behind
    "device on face" detection. For mock devices, call
    `mockDon(uuid)` first.
  - `requestCameraPermission` was never granted.
  - On Android, `setMockCameraFeed` / `setMockCameraFacing` was not
    called for a mock device.
- **`SessionError` with `permissionDenied`** — the user revoked
  camera permission while the session was running. Call
  `requestCameraPermission` again to recover.
- **High CPU on Android during streaming** — expected for v0.1.0.
  The I420 -> ARGB conversion runs on the CPU. v0.1 ships GPU-side
  rendering.

## Runtime — background streaming

- **iOS frames stop within a few seconds of locking the phone** — the
  `UIBackgroundModes` keys are missing or incomplete. Copy the
  four-entry array (`audio`, `bluetooth-central`,
  `bluetooth-peripheral`, `external-accessory`) from
  `example/ios/Runner/Info.plist`. `enableBackgroundStreaming` doesn't
  add these keys for you — they have to be in the app bundle.
- **iOS HEVC decoding stops the moment the app backgrounds** — the
  `VTDecompressionSession` was built with hardware acceleration.
  `BackgroundStreamingController` flips the pipeline into
  `softwareOnly` mode automatically when `enableBackgroundStreaming` is
  called, but only the *next* session picks it up. Either call
  `enableBackgroundStreaming` before `startStreamSession`, or stop +
  restart the stream after toggling.
- **Android: no notification visible while the service is running** —
  `POST_NOTIFICATIONS` is not granted on API 33+. The OS silently
  suppresses the notification (the service still runs). Request the
  permission from your host app's first-run flow:
  ```kotlin
  ActivityCompat.requestPermissions(
    activity,
    arrayOf(Manifest.permission.POST_NOTIFICATIONS),
    requestCode,
  )
  ```
- **Android: `SecurityException` referencing
  `FOREGROUND_SERVICE_CONNECTED_DEVICE`** — your app is targeting
  API ≥ 34 and the host app's runtime context isn't allowed to grant
  the new "Connected device" foreground-service type. Make sure your
  app has the matching permission declared (it's merged in from this
  plugin's manifest automatically; check with
  `./gradlew :app:processDebugMainManifest`).

## File an issue

If you hit something not listed here, open an issue at
<https://github.com/iseelabs/meta_wearables_dat_flutter/issues>
including:

- `flutter doctor -v`
- The full stack trace and any `DatError.code` you observed.
- Whether the bug reproduces against a mock device.
