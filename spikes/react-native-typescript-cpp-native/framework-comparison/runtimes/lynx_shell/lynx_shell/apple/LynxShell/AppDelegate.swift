import UIKit

@UIApplicationMain
class AppDelegate: UIResponder, UIApplicationDelegate {
  var window: UIWindow?

  func application(_ application: UIApplication, didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]?) -> Bool {
    let lynxEnv = LynxEnv.sharedInstance()
    let config = LynxConfig(provider: TemplateProvider())

    // Register new modules with:
    // config.register(YourModuleName.self)

    lynxEnv.prepareConfig(config)

    return true
  }
}
