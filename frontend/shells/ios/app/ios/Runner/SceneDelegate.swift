import Flutter
import UIKit

class SceneDelegate: FlutterSceneDelegate {
  override func scene(
    _ scene: UIScene,
    willConnectTo session: UISceneSession,
    options connectionOptions: UIScene.ConnectionOptions
  ) {
    super.scene(
      scene,
      willConnectTo: session,
      options: connectionOptions)
    guard ProcessInfo.processInfo.arguments.contains(where: {
      $0.hasPrefix("--omi-capture-query=")
    }) else { return }
    (window?.rootViewController as? FlutterViewController)?.setNeedsUpdateOfHomeIndicatorAutoHidden()
  }
}
