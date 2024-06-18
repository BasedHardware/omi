import UIKit

import Flutter
import workmanager

@UIApplicationMain
@objc class AppDelegate: FlutterAppDelegate {
  override func application(
    _ application: UIApplication,
    didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]?
  ) -> Bool {
    GeneratedPluginRegistrant.register(with: self)
    // here, Without this code the task will not work.
    // SwiftFlutterForegroundTaskPlugin.setPluginRegistrantCallback(regbisterPlugins)
    if #available(iOS 10.0, *) {
      UNUserNotificationCenter.current().delegate = self as? UNUserNotificationCenterDelegate
    }
    // In AppDelegate.application method
    WorkmanagerPlugin.registerBGProcessingTask(withIdentifier: "daily-summary")

    // Register a periodic task in iOS 13+
    WorkmanagerPlugin.registerPeriodicTask(withIdentifier: "com.friend-app-with-wearable.ios12.daily-summary", frequency: NSNumber(value: 60*60*24))
//     UIApplication.shared.setMinimumBackgroundFetchInterval(TimeInterval(60*15))

    return super.application(application, didFinishLaunchingWithOptions: launchOptions)
  }
}

// here
// func registerPlugins(registry: FlutterPluginRegistry) {
//   GeneratedPluginRegistrant.register(with: registry)
// }
