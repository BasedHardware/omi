import UIKit
import Flutter
import UserNotifications
import app_links
import AccessorySetupKit

@main
@objc class AppDelegate: FlutterAppDelegate {
  private var methodChannel: FlutterMethodChannel?
  private var accessorySetupChannel: FlutterMethodChannel?
  private var accessorySetupManager: Any? // Using Any to avoid availability issues

  private var notificationTitleOnKill: String?
  private var notificationBodyOnKill: String?

  override func application(
    _ application: UIApplication,
    didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]?
  ) -> Bool {
    GeneratedPluginRegistrant.register(with: self)

      // Retrieve the link from parameters
    if let url = AppLinks.shared.getLink(launchOptions: launchOptions) {
      // We have a link, propagate it to your Flutter app or not
      AppLinks.shared.handleLink(url: url)
      return true // Returning true will stop the propagation to other packages
    }
    //Creates a method channel to handle notifications on kill
    let controller = window?.rootViewController as? FlutterViewController
    methodChannel = FlutterMethodChannel(name: "com.friend.ios/notifyOnKill", binaryMessenger: controller!.binaryMessenger)
    methodChannel?.setMethodCallHandler { [weak self] (call, result) in
      self?.handleMethodCall(call, result: result)
    }
    
    // Initialize AccessorySetupKit method channel
    accessorySetupChannel = FlutterMethodChannel(name: "com.omi.ios/accessorySetup", binaryMessenger: controller!.binaryMessenger)
    accessorySetupChannel?.setMethodCallHandler { [weak self] (call, result) in
      if #available(iOS 18.0, *) {
        self?.handleAccessorySetupCall(call, result: result)
      } else {
        result(FlutterError(code: "UNAVAILABLE", message: "AccessorySetupKit requires iOS 18.0 or later", details: nil))
      }
    }
    
    // Initialize AccessorySetupManager for iOS 18+
    if #available(iOS 18.0, *) {
      accessorySetupManager = AccessorySetupManager()
      if let manager = accessorySetupManager as? AccessorySetupManager {
        manager.setEventHandler { [weak self] (eventType, eventData) in
          self?.accessorySetupChannel?.invokeMethod("onAccessoryEvent", arguments: ["eventType": eventType, "data": eventData])
        }
      }
    }

    // here, Without this code the task will not work.
    SwiftFlutterForegroundTaskPlugin.setPluginRegistrantCallback { registry in
      GeneratedPluginRegistrant.register(with: registry)
    }
    if #available(iOS 10.0, *) {
      UNUserNotificationCenter.current().delegate = self as? UNUserNotificationCenterDelegate
    }

    return super.application(application, didFinishLaunchingWithOptions: launchOptions)
  }

  private func handleMethodCall(_ call: FlutterMethodCall, result: @escaping FlutterResult) {
    switch call.method {
      case "setNotificationOnKillService":
        handleSetNotificationOnKillService(call: call)
      default:
        result(FlutterMethodNotImplemented)
    }
  }
  
  @available(iOS 18.0, *)
  private func handleAccessorySetupCall(_ call: FlutterMethodCall, result: @escaping FlutterResult) {
    guard let manager = accessorySetupManager as? AccessorySetupManager else {
      result(FlutterError(code: "UNAVAILABLE", message: "AccessorySetupManager not initialized", details: nil))
      return
    }
    
    switch call.method {
      case "showAccessoryPicker":
        manager.showAccessoryPicker { success, error in
          if success {
            result(true)
          } else {
            result(FlutterError(code: "PICKER_ERROR", message: error ?? "Unknown error", details: nil))
          }
        }
        
      case "getConnectedAccessories":
        let accessories = manager.getConnectedAccessories()
        result(accessories)
        
      case "removeAccessory":
        guard let args = call.arguments as? [String: Any],
              let accessoryId = args["accessoryId"] as? String else {
          result(FlutterError(code: "INVALID_ARGS", message: "Missing accessoryId", details: nil))
          return
        }
        
        manager.removeAccessory(withId: accessoryId) { success, error in
          if success {
            result(true)
          } else {
            result(FlutterError(code: "REMOVE_ERROR", message: error ?? "Unknown error", details: nil))
          }
        }
        
      case "isAccessorySetupKitAvailable":
        result(true)
        
      default:
        result(FlutterMethodNotImplemented)
    }
  }

  private func handleSetNotificationOnKillService(call: FlutterMethodCall) {
    NSLog("handleMethodCall: setNotificationOnKillService")
    
    if let args = call.arguments as? Dictionary<String, Any> {
      notificationTitleOnKill = args["title"] as? String
      notificationBodyOnKill = args["description"] as? String
    }
    
  }
    

  override func applicationWillTerminate(_ application: UIApplication) {
    // If title and body are nil, then we don't need to show notification.
    if notificationTitleOnKill == nil || notificationBodyOnKill == nil {
      return
    }

    let content = UNMutableNotificationContent()
    content.title = notificationTitleOnKill!
    content.body = notificationBodyOnKill!
    let trigger = UNTimeIntervalNotificationTrigger(timeInterval: 1, repeats: false)
    let request = UNNotificationRequest(identifier: "notification on app kill", content: content, trigger: trigger)

    NSLog("Running applicationWillTerminate")

    UNUserNotificationCenter.current().add(request) { (error) in
      if let error = error {
        NSLog("Failed to show notification on kill service => error: \(error.localizedDescription)")
      } else {
        NSLog("Show notification on kill now")
      }
    }
  }
}

// here
func registerPlugins(registry: FlutterPluginRegistry) {
  GeneratedPluginRegistrant.register(with: registry)
}
