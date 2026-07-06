# Meta Wearables Device Access Toolkit for Flutter

[![pub package](https://img.shields.io/pub/v/meta_wearables_dat_flutter.svg)](https://pub.dev/packages/meta_wearables_dat_flutter)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![style: very good analysis](https://img.shields.io/badge/style-very_good_analysis-B22C89.svg)](https://pub.dev/packages/very_good_analysis)
[![Flutter](https://img.shields.io/badge/flutter-%3E%3D3.32.0-blue.svg)](https://flutter.dev)

A Flutter plugin that brings Meta's Wearables Device Access Toolkit (DAT)
to iOS and Android. Connect to Ray-Ban Meta, Oakley Meta, and Ray-Ban
Display glasses — registration, live video streaming, photo capture,
declarative on-glasses Display Access UI, the Mock Device Kit, and
background streaming — all behind a single Dart API.

Wraps Meta's official DAT SDKs (v0.7.0) as binary dependencies. The DAT
is in developer preview; apps cannot yet ship publicly via the App Store
or Play Store. Create an organisation and release channel in the
[Wearables Developer Center](https://wearables.developer.meta.com/) to
share builds with test users.

> **Unofficial.** Not affiliated with, endorsed by, or officially connected
> to Meta Platforms, Inc. "Meta", "Ray-Ban Meta", "Oakley Meta", and
> "Ray-Ban Display" are trademarks of their respective owners.

## Documentation & Community

Find Meta's full
[developer documentation](https://wearables.developer.meta.com/docs/develop/)
on the Wearables Developer Center.

Plugin-specific guides live in [`doc/`](doc/):

- [`doc/getting_started.md`](doc/getting_started.md) — pubspec, iOS
  `Info.plist`, Android `AndroidManifest.xml`, Developer Mode.
- [`doc/registration_flow.md`](doc/registration_flow.md) — registration
  deep-link wiring.
- [`doc/streaming.md`](doc/streaming.md) — texture rendering, video
  codecs, photo capture, background streaming.
- [`doc/frame_processing.md`](doc/frame_processing.md) — opt-in
  per-frame `videoFramesStream`, recording, OCR/ML pipelines.
- [`doc/display_access.md`](doc/display_access.md) — declarative UI on
  Ray-Ban Display glasses (FlexBox/Text/Image/Button/Icon/VideoPlayer).
- [`doc/mock_device.md`](doc/mock_device.md) — Mock Device Kit.
- [`doc/troubleshooting.md`](doc/troubleshooting.md) — common
  pitfalls.

For help or to suggest feature ideas, open an issue on
[GitHub](https://github.com/iSee-Labs/meta-wearables-dat-flutter/issues).

See the [changelog](CHANGELOG.md) for the latest updates.

## Compatible devices

- Ray-Ban Meta (Gen 1 and Gen 2)
- Oakley Meta (HSTN, Vanguard)
- Ray-Ban Display

A paired phone running the **Meta AI** companion app with **Developer
Mode** enabled is required during the developer preview.

## Including the SDK in your project

```yaml
dependencies:
  meta_wearables_dat_flutter: ^0.7.1
```

```bash
flutter pub get
```

### Enable Developer Mode in the Meta AI app (one-time, per phone)

> **STOP — do this before running anything.** Until your app is approved
> in the Wearables Developer Center, registration is gated by a toggle
> inside the Meta AI mobile app. The manifest values below (`MetaAppID =
> "0"`, `CLIENT_TOKEN = "0"`) are *only* the code-side half of the
> handshake; without the phone-side toggle the SDK will fail with:
>
> - **iOS**: `Internal error` toast in Meta AI immediately after you tap
>   **Allow**, your app never receives the deep link.
> - **Android**: `RegistrationError(code: HTTP_REQUEST_FAILED, ...)`
>   with HTTP 401 from `api2.ar.meta.com` because the SDK falls back to
>   real attestation.
>
> Both symptoms disappear the instant the toggle is on.

1. Open the **Meta AI** app on the same phone you'll run your Flutter
   app on (the one paired with your glasses).
2. Tap your profile/avatar → **Settings** → scroll to the bottom →
   toggle **Developer Mode** on. (Older builds: **Settings →
   Advanced → Developer Mode**.)
3. Restart your Flutter app and try `startRegistration()` again.

The matching code-side switches are `MetaAppID = "0"` in your iOS
`Info.plist` and `APPLICATION_ID = "0"` + `CLIENT_TOKEN = "0"` in your
Android `<meta-data>` — already set in the snippets below.

### iOS

Pick **any short alphanumeric** URL scheme for your app (no
underscores — they break Meta's redirect-URL builder). Examples:
`mywearablesapp`, `metasdkdemo`. The snippets below assume
`mywearablesapp`; replace it everywhere it appears.

#### 1. Enable Swift Package Manager (once per machine)

```bash
flutter config --enable-swift-package-manager
```

#### 2. Raise the iOS deployment target to 17.0

The plugin's iOS SDK requires iOS 17 minimum. Set it in **two**
places — they must match or the build fails:

`ios/Podfile` (uncomment / set the top line):

```ruby
platform :ios, '17.0'
```

`ios/Runner.xcodeproj` → open `ios/Runner.xcworkspace` in Xcode →
**Runner** target → **General** → **Minimum Deployments** → set
**iOS** to **17.0**.

Then refresh CocoaPods:

```bash
cd ios && pod install && cd ..
```

#### 3. Add the `MWDAT` dict and related keys to `ios/Runner/Info.plist`

The DAT SDK validates the `MWDAT` dict as **all-or-nothing
attestation** — all four keys (`AppLinkURLScheme`, `MetaAppID`,
`ClientToken`, `TeamID`) must be present and non-empty or
`startRegistration()` throws `RegistrationError.configurationInvalid`
before Meta AI even opens. Paste this block inside the root `<dict>`
of `Info.plist`:

```xml
<!-- Begin required section for Meta Wearables Device Access Toolkit. -->
<key>MWDAT</key>
<dict>
  <!-- MUST end with "://". Meta AI builds the callback URL by literally
       concatenating this value with "?authorityKey=...&metaWearablesAction=
       register&..."; without the separator the URL is malformed and iOS
       silently drops it. The scheme itself (without "://") must also be
       listed under CFBundleURLTypes below. RFC 3986 — alphanumeric, no
       underscores. -->
  <key>AppLinkURLScheme</key>
  <string>mywearablesapp://</string>

  <!-- "0" = Developer Mode sentinel. Pairs with the Meta AI app's
       Developer Mode toggle (see above). The SDK skips Wearables
       Developer Center attestation when MetaAppID is "0". -->
  <key>MetaAppID</key>
  <string>0</string>

  <!-- Required to be present and non-empty. The value is not validated
       in Developer Mode. For a published app, replace with the value
       from https://developers.meta.com/wearables/. -->
  <key>ClientToken</key>
  <string>developer-mode-placeholder</string>

  <!-- $(DEVELOPMENT_TEAM) is expanded by Xcode at build time from
       Signing & Capabilities. -->
  <key>TeamID</key>
  <string>$(DEVELOPMENT_TEAM)</string>

  <!-- Opt out of the SDK's analytics uploads to api2.ar.meta.com so a
       partial telemetry config in Developer Mode cannot fail
       registration with a misleading "Internal error". -->
  <key>Analytics</key>
  <dict>
    <key>OptOut</key>
    <true/>
  </dict>
</dict>

<!-- The OS routes the Meta AI deep-link callback to whichever app
     declares the matching scheme here. The string MUST match
     AppLinkURLScheme above, WITHOUT the trailing "://". -->
<key>CFBundleURLTypes</key>
<array>
  <dict>
    <key>CFBundleURLSchemes</key>
    <array>
      <string>mywearablesapp</string>
    </array>
  </dict>
</array>

<!-- The DAT SDK preflights `canOpenURL("fb-viewapp://...")` before
     it'll try to open Meta AI. Without `fb-viewapp` here iOS returns
     false and the SDK throws configurationInvalid (raw 1) before
     Meta AI even opens. -->
<key>LSApplicationQueriesSchemes</key>
<array>
  <string>fb-viewapp</string>
</array>

<!-- Streaming session requires `audio` to be declared even if you
     never start a stream during registration. The other three keep
     the BT + glasses transport alive in the background. -->
<key>UIBackgroundModes</key>
<array>
  <string>audio</string>
  <string>bluetooth-central</string>
  <string>bluetooth-peripheral</string>
  <string>external-accessory</string>
</array>

<key>NSBluetoothAlwaysUsageDescription</key>
<string>Needed to connect to Meta AI Glasses.</string>
<key>NSLocalNetworkUsageDescription</key>
<string>Allows your phone to find and connect to your glasses over Wi-Fi.</string>

<key>NSBonjourServices</key>
<array>
  <string>_bonjour._tcp</string>
</array>

<key>UISupportedExternalAccessoryProtocols</key>
<array>
  <string>com.meta.ar.wearable</string>
</array>
<!-- End required section for Meta Wearables Device Access Toolkit. -->
```

#### 4. Forward Meta AI's deep-link callback (scene-based apps)

Flutter ≥ 3.32 generates a scene-based iOS lifecycle (a
`UIApplicationSceneManifest` block in `Info.plist` and a
`ios/Runner/SceneDelegate.swift`). On those apps iOS delivers the
Meta AI callback URL to your **host app's** `SceneDelegate`, not to
the plugin — and `FlutterSceneDelegate` does not auto-forward URLs to
plugins. Replace `ios/Runner/SceneDelegate.swift` with:

```swift
import Flutter
import UIKit

class SceneDelegate: FlutterSceneDelegate {

  override func scene(
    _ scene: UIScene,
    willConnectTo session: UISceneSession,
    options connectionOptions: UIScene.ConnectionOptions
  ) {
    super.scene(scene, willConnectTo: session, options: connectionOptions)
    forward(urlContexts: connectionOptions.urlContexts)
  }

  override func scene(
    _ scene: UIScene,
    openURLContexts URLContexts: Set<UIOpenURLContext>
  ) {
    super.scene(scene, openURLContexts: URLContexts)
    forward(urlContexts: URLContexts)
  }

  private func forward(urlContexts: Set<UIOpenURLContext>) {
    for context in urlContexts {
      NotificationCenter.default.post(
        name: Notification.Name("MetaWearablesDatHandleURL"),
        object: nil,
        userInfo: ["url": context.url],
      )
    }
  }
}
```

The plugin subscribes to `MetaWearablesDatHandleURL` at registration
time and routes the URL to the SDK natively — you do **not** call
`handleUrl(...)` from Dart. If your app uses the classic AppDelegate
lifecycle (no scene manifest), skip this step; the plugin
auto-consumes the URL via `application(_:open:options:)`.

### Android

Pick the same URL scheme you used on iOS (without the `://`
suffix). The snippets below use `mywearablesapp`; replace it
everywhere.

#### 1. Make `MainActivity` extend `FlutterFragmentActivity`

`android/app/src/main/kotlin/.../MainActivity.kt`:

```kotlin
import io.flutter.embedding.android.FlutterFragmentActivity

class MainActivity : FlutterFragmentActivity()
```

Meta's camera-permission contract requires a `ComponentActivity`;
`FlutterFragmentActivity` qualifies, `FlutterActivity` doesn't.

#### 2. Set `minSdk = 31` and use NDK 28.2.13676358

In `android/app/build.gradle.kts`:

```kotlin
android {
    // Meta's `mwdat-core` AAR was built with NDK r27, but most Flutter
    // plugin transitive deps (e.g. `jni`) require r28.2. NDK is
    // backward compatible per AGP's "use highest" rule.
    ndkVersion = "28.2.13676358"

    defaultConfig {
        minSdk = 31
    }
}
```

#### 3. Add Meta's GitHub Packages Maven repo

The Meta Android DAT SDK is published to GitHub Packages and
requires a PAT with the `read:packages` scope.

In `android/settings.gradle.kts`, inside
`dependencyResolutionManagement { repositories { ... } }`:

```kotlin
maven {
    url = uri("https://maven.pkg.github.com/facebook/meta-wearables-dat-android")
    credentials {
        username = "" // not needed; the PAT carries the user
        password = System.getenv("GITHUB_TOKEN")
            ?: providers.gradleProperty("github_token").orNull
            ?: ""
    }
}
```

Then either export `GITHUB_TOKEN` in your shell or add to
`android/local.properties`:

```properties
github_token=ghp_yourPersonalAccessTokenWithReadPackagesScope
```

Create the PAT at
<https://github.com/settings/tokens> with scope **`read:packages`**
only.

#### 4. Add `MWDAT` meta-data, permissions, and the deep-link intent-filter

`android/app/src/main/AndroidManifest.xml`:

```xml
<manifest xmlns:android="http://schemas.android.com/apk/res/android">

  <!-- Required by the Meta Wearables DAT SDK. -->
  <uses-permission android:name="android.permission.BLUETOOTH" />
  <uses-permission android:name="android.permission.BLUETOOTH_CONNECT" />
  <uses-permission android:name="android.permission.INTERNET" />

  <application
      android:name="${applicationName}"
      android:label="Your App"
      android:icon="@mipmap/ic_launcher">

    <!-- Both values must be "0" in Developer Mode (per Meta's official
         Android docs). An empty string causes TOKEN_NOT_CONFIGURED;
         any non-"0" placeholder makes the SDK attempt a real HTTP
         attestation against api2.ar.meta.com and registration fails
         with HTTP 401. For production, replace with the AppID and
         ClientToken from https://developers.meta.com/wearables/.
         DAM_ENABLED tells the SDK you are running in Developer Access
         Mode — without it `usesDam` stays false and the session manager
         rejects every paired device with "No eligible device found".
         ANALYTICS_OPT_OUT prevents the SDK from uploading developer
         analytics during testing. -->
    <meta-data
        android:name="com.meta.wearable.mwdat.APPLICATION_ID"
        android:value="0" />
    <meta-data
        android:name="com.meta.wearable.mwdat.CLIENT_TOKEN"
        android:value="0" />
    <meta-data
        android:name="com.meta.wearable.mwdat.DAM_ENABLED"
        android:value="true" />
    <meta-data
        android:name="com.meta.wearable.mwdat.ANALYTICS_OPT_OUT"
        android:value="true" />

    <activity
        android:name=".MainActivity"
        android:exported="true"
        android:launchMode="singleTop"
        android:theme="@style/LaunchTheme"
        android:configChanges="orientation|keyboardHidden|keyboard|screenSize|smallestScreenSize|locale|layoutDirection|fontScale|screenLayout|density|uiMode"
        android:hardwareAccelerated="true"
        android:windowSoftInputMode="adjustResize">

      <intent-filter>
        <action android:name="android.intent.action.MAIN"/>
        <category android:name="android.intent.category.LAUNCHER"/>
      </intent-filter>

      <!-- Registration callback from the Meta AI app. The scheme MUST
           match AppLinkURLScheme on iOS and the scheme you pick for
           your app. `launchMode="singleTop"` above is required so the
           SDK can find and route the inbound intent. -->
      <intent-filter>
        <action android:name="android.intent.action.VIEW" />
        <category android:name="android.intent.category.BROWSABLE" />
        <category android:name="android.intent.category.DEFAULT" />
        <data android:scheme="mywearablesapp" />
      </intent-filter>
    </activity>
  </application>
</manifest>
```

The plugin's manifest already merges in `FOREGROUND_SERVICE`,
`FOREGROUND_SERVICE_CONNECTED_DEVICE`, `WAKE_LOCK`, and
`POST_NOTIFICATIONS` plus the background-streaming `<service>` entry,
so you don't have to declare them.

## Integration lifecycle

```dart
import 'package:meta_wearables_dat_flutter/meta_wearables_dat_flutter.dart';

// 1. Permissions (Bluetooth/Internet on Android, no-op on iOS).
await MetaWearablesDat.requestAndroidPermissions();

// 2. Register with the Meta AI app via deep link. `appId` and
//    `urlScheme` are read from the host app's Info.plist / Android
//    meta-data — no need to repeat them in Dart.
await MetaWearablesDat.startRegistration();

// 3. Camera permission (Meta AI bottom sheet).
await MetaWearablesDat.requestCameraPermission();

// 4. Start streaming and render the texture.
final textureId = await MetaWearablesDat.startStreamSession();
// Texture(textureId: textureId)

// 5. Capture stills, observe state.
final photo = await MetaWearablesDat.capturePhoto();
MetaWearablesDat.streamSessionStateStream().listen(print);
```

See [`samples/camera_access/`](samples/camera_access/) for a complete
integration that mirrors Meta's official iOS and Android CameraAccess
samples, and [`samples/display_access/`](samples/display_access/) for
the Display Access "Car Maintenance" tutorial on Ray-Ban Display
glasses.

## Developer Terms

- By using the Wearables Device Access Toolkit, you agree to Meta's
  [Meta Wearables Developer Terms](https://wearables.developer.meta.com/terms),
  including the [Acceptable Use Policy](https://wearables.developer.meta.com/acceptable-use-policy).
- By enabling Meta integrations through this plugin, Meta may collect
  information about how users' Meta devices communicate with your app.
  Meta uses this information in accordance with the
  [Meta Privacy Policy](https://www.meta.com/legal/privacy-policy/).
- You may limit Meta's access to data from users' devices by opting
  out of analytics as described below.

### Opting out of data collection

This plugin is a thin bridge — analytics are controlled by Meta's
underlying SDKs and you opt out exactly as you would in a native
project.

**iOS** — add an `Analytics.OptOut` key inside the `MWDAT` dict in
`ios/Runner/Info.plist`:

```xml
<key>MWDAT</key>
<dict>
  <key>Analytics</key>
  <dict>
    <key>OptOut</key>
    <true/>
  </dict>
  <!-- other MWDAT keys ... -->
</dict>
```

**Android** — add the matching `meta-data` entry inside
`android/app/src/main/AndroidManifest.xml`:

```xml
<meta-data
  android:name="com.meta.wearable.mwdat.ANALYTICS_OPT_OUT"
  android:value="true" />
```

Default behavior: if the key is missing or `false`, analytics are
enabled. Set it to `true` to disable data collection.

## AI-Assisted Development

This repository ships config for three AI coding assistants, all
generated from the same canonical knowledge in [`AGENTS.md`](AGENTS.md):

| Tool | Config | How it loads |
|------|--------|--------------|
| [Claude Code](https://docs.anthropic.com/en/docs/claude-code) | `.claude/skills/*.md` | Auto-discovered when you open the project |
| [GitHub Copilot](https://github.com/features/copilot) | `.github/copilot-instructions.md` | Auto-loaded by Copilot in VS Code |
| [Cursor](https://cursor.sh/) | `.cursor/rules/*.mdc` | Auto-loaded with glob-based triggers |

### Quick setup

Install config for your preferred tool:

```bash
./install-skills.sh claude    # Claude Code only
./install-skills.sh copilot   # GitHub Copilot only
./install-skills.sh cursor    # Cursor only
./install-skills.sh agents    # AGENTS.md only
./install-skills.sh all       # All tools
```

Or install everything remotely with a single command:

```bash
curl -sL https://raw.githubusercontent.com/iSee-Labs/meta-wearables-dat-flutter/main/install-skills.sh | bash
```

If you cloned this repository, the config is already included — no
setup needed.

### What's included

- **Getting started** — pubspec wiring, `Info.plist`,
  `AndroidManifest.xml`, Developer Mode.
- **Camera streaming** — texture path, video codecs, photo capture,
  `videoFramesStream`.
- **Display access** — declarative on-glasses UI, callbacks, video.
- **Mock device testing** — `MockDeviceKit` from Dart.
- **Session lifecycle** — `DeviceSession` vs `StreamSession`,
  pause/resume.
- **Permissions & registration** — deep-link callbacks, camera permission flow.
- **Debugging** — registration errors, no eligible device, Maven 401,
  SPM not enabled.
- **Sample app guide** — building a complete Flutter DAT app.

For Meta's full API reference, point your AI tool at the
[llms.txt endpoint](https://wearables.developer.meta.com/llms.txt?full=true).

## License

[MIT](LICENSE) © 2026 iSee Labs.

## Acknowledgments

Built on top of Meta's official open-source SDKs:

- [`meta-wearables-dat-ios`](https://github.com/facebook/meta-wearables-dat-ios)
- [`meta-wearables-dat-android`](https://github.com/facebook/meta-wearables-dat-android)

Architecture inspiration (texture bridge, per-frame stream) drawn from
the community
[`flutter_meta_wearables_dat`](https://github.com/rodcone/flutter_meta_wearables_dat)
plugin. See [`NOTICE`](NOTICE) for full attribution.
