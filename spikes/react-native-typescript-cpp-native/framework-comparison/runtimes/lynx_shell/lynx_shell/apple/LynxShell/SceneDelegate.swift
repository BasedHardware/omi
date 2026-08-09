import UIKit

class SceneDelegate: UIResponder, UIWindowSceneDelegate {
  var window: UIWindow?

  func scene(_ scene: UIScene, willConnectTo session: UISceneSession, options connectionOptions: UIScene.ConnectionOptions) {
    guard let windowScene = (scene as? UIWindowScene) else { return }

    window = UIWindow(windowScene: windowScene)

    let lynxView = LynxView { builder in
      builder.config = LynxConfig(provider: nil)
      builder.config?.register(OmiNativeModule.self)
#if DEBUG
      builder.enableGenericResourceFetcher = .true
      builder.genericResourceFetcher = GenericResourceFetcher()
#endif
      builder.screenSize = windowScene.screen.bounds.size
      builder.fontScale = 1.0
    }

    lynxView.preferredLayoutWidth = windowScene.screen.bounds.size.width
    lynxView.preferredLayoutHeight = windowScene.screen.bounds.size.height
    lynxView.layoutWidthMode = LynxViewSizeMode(rawValue: 1)!
    lynxView.layoutHeightMode = LynxViewSizeMode(rawValue: 1)!

     let rootViewController = UIViewController()
    window?.rootViewController = rootViewController
    rootViewController.view = lynxView

#if DEBUG
    lynxView.loadTemplate(
      fromURL: "http://localhost:3000/main.lynx.bundle?fullscreen=true",
      initData: nil
    )
#else
    lynxView.loadTemplate(fromURL: "main.lynx")
#endif

    window?.makeKeyAndVisible()
  }
}
