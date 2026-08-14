import React_RCTAppDelegate
import UIKit

class SceneDelegate: UIResponder, UIWindowSceneDelegate {
  var window: UIWindow?

  func scene(
    _ scene: UIScene,
    willConnectTo session: UISceneSession,
    options connectionOptions: UIScene.ConnectionOptions
  ) {
    guard
      let windowScene = scene as? UIWindowScene,
      let appDelegate = UIApplication.shared.delegate as? AppDelegate,
      let factory = appDelegate.reactNativeFactory
    else {
      return
    }

    let window = UIWindow(windowScene: windowScene)
    let allowedRoutes = Set(["Home", "Chat", "Conversations", "Memories", "Tasks"])
    let requestedRoute = ProcessInfo.processInfo.environment["OMI_INITIAL_ROUTE"]
    let initialRoute = requestedRoute.flatMap { allowedRoutes.contains($0) ? $0 : nil } ?? "Home"
    self.window = window
    appDelegate.window = window
    factory.startReactNative(
      withModuleName: "RnRuntime",
      in: window,
      initialProperties: ["initialRoute": initialRoute],
      launchOptions: nil
    )
  }
}
