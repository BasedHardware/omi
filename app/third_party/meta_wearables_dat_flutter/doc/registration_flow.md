# Registration flow

Registration pairs your app with a specific user's Meta account and
glasses. It is a deep-link round-trip: your app -> Meta AI -> your app.

## End-to-end timeline

```
[1] requestAndroidPermissions()        (Android only, no-op on iOS)
[2] startRegistration()
[3] Meta AI app handles consent
[4] Meta AI deep-links back into your app's URL scheme
[5] Host SceneDelegate posts                       (iOS scene apps)
    MetaWearablesDatHandleURL notification     or  (iOS classic apps,
    AppDelegate routes the URL via the plugin's    automatic)
    application-delegate registrar             or
    Android intent-filter routes the URL           (Android, automatic)
[6] registrationStateStream() emits RegistrationState.registered
[7] activeDeviceStream() emits a non-null DeviceInfo
```

## Code

```dart
import 'package:meta_wearables_dat_flutter/meta_wearables_dat_flutter.dart';

// 1. Permissions (Android only, returns true on iOS).
await MetaWearablesDat.requestAndroidPermissions();

// 2. Listen for state transitions.
MetaWearablesDat.registrationStateStream().listen((state) {
  print('Registration state: $state');
});

// 3. Kick off the flow.
await MetaWearablesDat.startRegistration();
```

On Android the plugin consumes the registration callback URL through
its `<intent-filter>` automatically. On iOS the deep-link reaches your
app's `AppDelegate` for classic-lifecycle apps and the plugin handles
it, but apps with scene-based lifecycle (the Flutter default since
Flutter 3.32) need one extra wiring step — see below.

## iOS: SceneDelegate wiring (required for scene-based apps)

Modern Flutter projects ship with a `UIApplicationSceneManifest` in
`Info.plist` and a `SceneDelegate.swift` file. When that's the case,
iOS delivers the Meta AI callback URL to `scene(_:openURLContexts:)`
on the **host app's** `SceneDelegate`, **not** to `AppDelegate`. A
Flutter plugin cannot inject itself into another file's
`SceneDelegate`, so the host app must forward the URL.

Add the following overrides to `ios/Runner/SceneDelegate.swift`:

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

The plugin listens for the `MetaWearablesDatHandleURL` notification at
`register(with:)` time and routes the URL to
`Wearables.shared.handleUrl(...)` internally, so you do **not** need
to call `MetaWearablesDat.handleUrl(...)` from Dart.

If your app uses the classic `AppDelegate` lifecycle (no scene
manifest), skip this step — the plugin auto-consumes the URL via the
application delegate registrar.

A complete reference implementation lives in
[`example/ios/Runner/SceneDelegate.swift`](../example/ios/Runner/SceneDelegate.swift).

## RegistrationState semantics

| State           | Meaning                                                   |
| --------------- | --------------------------------------------------------- |
| `unavailable`   | SDK not initialised, or no internet.                      |
| `available`     | SDK ready, no glasses paired.                             |
| `registering`   | Mid-flow: Meta AI screen is up, or returning from it.     |
| `registered`    | Glasses paired and active. APIs requiring a device work.  |

## Unregistering

```dart
await MetaWearablesDat.startUnregistration();
```

## Troubleshooting

- **State stays `unavailable`** on Android — `BLUETOOTH_CONNECT` was not
  granted. Call `requestAndroidPermissions()` and verify the user
  accepted.
- **Deep link never returns** — check that your URL scheme matches the
  one in `Info.plist` (iOS) / `AndroidManifest.xml` (Android) and that
  Meta AI is installed.
- **iOS: tapping "Allow" in Meta AI reopens the app but nothing
  happens** — your `SceneDelegate` does not forward the inbound URL.
  Add the `scene(_:openURLContexts:)` /
  `scene(_:willConnectTo:options:)` overrides shown in
  [iOS: SceneDelegate wiring](#ios-scenedelegate-wiring-required-for-scene-based-apps)
  to `ios/Runner/SceneDelegate.swift`. Without them, iOS silently
  drops the callback URL and the SDK never sees the consent grant.
- **Android's `MainActivity` does not receive the deep link** — verify
  `launchMode="singleTop"` and the `<intent-filter>` block.
