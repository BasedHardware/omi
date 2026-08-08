import UIKit

class SceneDelegate: UIResponder, UIWindowSceneDelegate {
  var window: UIWindow?

  func scene(_ scene: UIScene, willConnectTo session: UISceneSession, options connectionOptions: UIScene.ConnectionOptions) {
    guard let windowScene = (scene as? UIWindowScene) else { return }

    window = UIWindow(windowScene: windowScene)

    let lynxView = LynxView { builder in
#if DEBUG
      builder.enableGenericResourceFetcher = .true
      builder.genericResourceFetcher = GenericResourceFetcher()
#endif
      builder.screenSize = windowScene.screen.bounds.size
      builder.fontScale = 1.0
    }

    lynxView.preferredLayoutWidth = windowScene.screen.bounds.size.width
    lynxView.preferredLayoutHeight = windowScene.screen.bounds.size.height
    lynxView.layoutWidthMode = .exact
    lynxView.layoutHeightMode = .exact

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
