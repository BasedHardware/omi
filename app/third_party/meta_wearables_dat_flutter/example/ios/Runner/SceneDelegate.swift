import Flutter
import UIKit

/// Forwards inbound URL contexts (the Meta AI registration callback
/// `metawearablesdatexample://...`) to `meta_wearables_dat_flutter` via a
/// well-known NSNotification.
///
/// Why this is required:
/// - Apps with `UIApplicationSceneManifest` in Info.plist receive URLs in
///   `UISceneDelegate`, NOT in `AppDelegate.application(_:open:options:)`.
/// - `FlutterSceneDelegate` does not auto-forward URLs to plugins.
/// - Without this delegate the registration round-trip from Meta AI never
///   completes (Allow → "Internal error" toast in Meta AI, or the host app
///   silently sits at `registrationState=.available`).
///
/// We post `MetaWearablesDatHandleURL` instead of going through a Flutter
/// MethodChannel because (a) the channel needs a `FlutterViewController`
/// the scene may not have published yet on iOS 18+ implicit-engine setups,
/// and (b) we'd rather not import `MWDATCore` into the example target.
/// The plugin subscribes to the notification in
/// `MetaWearablesDatPlugin.register(with:)` and calls
/// `Wearables.shared.handleUrl` itself.
///
/// If your app uses the classic `AppDelegate` lifecycle (no scene manifest)
/// you don't need this file — the plugin also registers itself via
/// `registrar.addApplicationDelegate(self)` and consumes the URL from
/// `application(_:open:options:)` directly.
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
    guard !urlContexts.isEmpty else { return }
    for context in urlContexts {
      let url = context.url
      print("[meta_wearables_dat_flutter] SceneDelegate <- open url \(url)")
      NotificationCenter.default.post(
        name: Notification.Name("MetaWearablesDatHandleURL"),
        object: nil,
        userInfo: ["url": url],
      )
    }
  }
}
