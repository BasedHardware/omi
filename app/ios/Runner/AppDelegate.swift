import UIKit
import Flutter
import UserNotifications
import app_links
import EventKit

@main
@objc class AppDelegate: FlutterAppDelegate {
  private var methodChannel: FlutterMethodChannel?
  private var appleRemindersChannel: FlutterMethodChannel?
  private let eventStore = EKEventStore()

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
    
    // Create Apple Reminders method channel
    appleRemindersChannel = FlutterMethodChannel(name: "com.omi.apple_reminders", binaryMessenger: controller!.binaryMessenger)
    appleRemindersChannel?.setMethodCallHandler { [weak self] (call, result) in
      self?.handleAppleRemindersCall(call, result: result)
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

  private func handleSetNotificationOnKillService(call: FlutterMethodCall) {
    NSLog("handleMethodCall: setNotificationOnKillService")
    
    if let args = call.arguments as? Dictionary<String, Any> {
      notificationTitleOnKill = args["title"] as? String
      notificationBodyOnKill = args["description"] as? String
    }
    
  }
  
  private func handleAppleRemindersCall(_ call: FlutterMethodCall, result: @escaping FlutterResult) {
    switch call.method {
    case "hasPermission":
      hasRemindersPermission(result: result)
    case "requestPermission":
      requestRemindersPermission(result: result)
    case "addReminder":
      addReminder(call: call, result: result)
    default:
      result(FlutterMethodNotImplemented)
    }
  }
  
  private func hasRemindersPermission(result: @escaping FlutterResult) {
    let status = EKEventStore.authorizationStatus(for: .reminder)
    result(status == .authorized)
  }
  
  private func requestRemindersPermission(result: @escaping FlutterResult) {
    let status = EKEventStore.authorizationStatus(for: .reminder)
    
    if status == .authorized {
      result(true)
      return
    }
    
    if status == .denied || status == .restricted {
      result(false)
      return
    }
    
    // Request permission
    eventStore.requestAccess(to: .reminder) { granted, error in
      DispatchQueue.main.async {
        if let error = error {
          print("Error requesting reminders permission: \(error.localizedDescription)")
          result(false)
          return
        }
        result(granted)
      }
    }
  }
  
  private func addReminder(call: FlutterMethodCall, result: @escaping FlutterResult) {
    guard let args = call.arguments as? [String: Any] else {
      result(FlutterError(code: "INVALID_ARGUMENTS", message: "Invalid arguments", details: nil))
      return
    }
    
    guard let title = args["title"] as? String else {
      result(FlutterError(code: "MISSING_TITLE", message: "Title is required", details: nil))
      return
    }
    
    let notes = args["notes"] as? String
    let listName = args["listName"] as? String ?? "Omi Action Items"
    let dueDate: Date? = {
      if let dueDateMs = args["dueDate"] as? Int64 {
        return Date(timeIntervalSince1970: TimeInterval(dueDateMs) / 1000.0)
      }
      return nil
    }()
    
    // Check permission
    let status = EKEventStore.authorizationStatus(for: .reminder)
    guard status == .authorized else {
      result(FlutterError(code: "PERMISSION_DENIED", message: "Reminders permission not granted", details: nil))
      return
    }
    
    // Find or create the calendar
    var targetCalendar: EKCalendar?
    
    // Look for existing calendar with the specified name
    let calendars = eventStore.calendars(for: .reminder)
    targetCalendar = calendars.first { $0.title == listName }
    
    // If not found, create a new calendar
    if targetCalendar == nil {
      targetCalendar = EKCalendar(for: .reminder, eventStore: eventStore)
      targetCalendar?.title = listName
      targetCalendar?.cgColor = UIColor.systemBlue.cgColor
      
      // Set the source (usually the local source)
      if let localSource = eventStore.sources.first(where: { $0.sourceType == .local }) {
        targetCalendar?.source = localSource
      } else if let defaultSource = eventStore.defaultCalendarForNewReminders()?.source {
        targetCalendar?.source = defaultSource
      }
      
      do {
        try eventStore.saveCalendar(targetCalendar!, commit: true)
      } catch {
        print("Error creating calendar: \(error.localizedDescription)")
        // Fall back to default calendar
        targetCalendar = eventStore.defaultCalendarForNewReminders()
      }
    }
    
    guard let calendar = targetCalendar else {
      result(FlutterError(code: "NO_CALENDAR", message: "Could not find or create calendar", details: nil))
      return
    }
    
    // Create the reminder
    let reminder = EKReminder(eventStore: eventStore)
    reminder.title = title
    reminder.notes = notes
    reminder.calendar = calendar
    
    if let dueDate = dueDate {
      let dueDateComponents = Calendar.current.dateComponents([.year, .month, .day, .hour, .minute], from: dueDate)
      reminder.dueDateComponents = dueDateComponents
    }
    
    // Save the reminder
    do {
      try eventStore.save(reminder, commit: true)
      result(true)
    } catch {
      print("Error saving reminder: \(error.localizedDescription)")
      result(FlutterError(code: "SAVE_FAILED", message: "Failed to save reminder: \(error.localizedDescription)", details: nil))
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
