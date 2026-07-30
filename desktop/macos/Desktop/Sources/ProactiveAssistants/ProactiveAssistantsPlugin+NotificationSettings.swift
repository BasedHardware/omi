import AppKit
import Foundation
@preconcurrency import UserNotifications

/// Sendable values copied from the UserNotifications callback queue before any
/// app state is touched. UserNotifications currently invokes these callbacks on
/// a private XPC queue, which must never inherit MainActor work.
struct UserNotificationSettingsSnapshot: Sendable {
  let authorizationStatus: UNAuthorizationStatus
  let alertStyle: UNAlertStyle
  let soundSetting: UNNotificationSetting
  let badgeSetting: UNNotificationSetting

  init(_ settings: UNNotificationSettings) {
    authorizationStatus = settings.authorizationStatus
    alertStyle = settings.alertStyle
    soundSetting = settings.soundSetting
    badgeSetting = settings.badgeSetting
  }

  init(
    authorizationStatus: UNAuthorizationStatus,
    alertStyle: UNAlertStyle,
    soundSetting: UNNotificationSetting,
    badgeSetting: UNNotificationSetting
  ) {
    self.authorizationStatus = authorizationStatus
    self.alertStyle = alertStyle
    self.soundSetting = soundSetting
    self.badgeSetting = badgeSetting
  }
}

struct UserNotificationAuthorizationResult: Sendable {
  let granted: Bool
  let errorDescription: String?
  let errorDomain: String?
  let errorCode: Int?
}

struct UserNotificationDeliveryResult: Sendable {
  let errorDescription: String?
}

/// A Sendable copy of the bounded string fields accepted by the local
/// distributed-notification test bridge. `Notification.userInfo` is not
/// Sendable and must not cross from Foundation's delivery thread to MainActor.
struct ProactiveTestNotificationPayload: Sendable {
  private static let supportedKeys = [
    "hours", "count", "title", "message", "assistantId", "sourceApp",
    "windowTitle", "contextSummary", "currentActivity", "reasoning", "detail",
  ]

  private let values: [String: String]

  nonisolated init(_ notification: Notification) {
    let userInfo = notification.userInfo
    var copiedValues: [String: String] = [:]
    for key in Self.supportedKeys {
      copiedValues[key] = userInfo?[key] as? String
    }
    values = copiedValues
  }

  subscript(_ key: String) -> String? {
    values[key]
  }
}

/// Selector-based Foundation observers can be called on the posting thread.
/// Keep the Objective-C entrypoint nonisolated, copy only Sendable values, and
/// perform the MainActor hop before touching the actor-isolated plugin.
protocol ProactiveSelectorNotificationCenter: AnyObject {
  func addProactiveObserver(_ observer: NSObject, selector: Selector, name: Notification.Name)
  func removeProactiveObserver(_ observer: NSObject, name: Notification.Name)
}

extension NotificationCenter: ProactiveSelectorNotificationCenter {
  func addProactiveObserver(_ observer: NSObject, selector: Selector, name: Notification.Name) {
    addObserver(observer, selector: selector, name: name, object: nil)
  }

  func removeProactiveObserver(_ observer: NSObject, name: Notification.Name) {
    removeObserver(observer, name: name, object: nil)
  }
}

final class ProactiveTestNotificationObserver: NSObject, @unchecked Sendable {
  let name: Notification.Name
  private let handler: @MainActor @Sendable (ProactiveTestNotificationPayload) -> Void

  init(
    name: Notification.Name,
    handler: @escaping @MainActor @Sendable (ProactiveTestNotificationPayload) -> Void
  ) {
    self.name = name
    self.handler = handler
  }

  func register(in center: ProactiveSelectorNotificationCenter) {
    center.addProactiveObserver(
      self,
      selector: #selector(receive(_:)),
      name: name
    )
  }

  func unregister(from center: ProactiveSelectorNotificationCenter) {
    center.removeProactiveObserver(self, name: name)
  }

  @objc nonisolated func receive(_ notification: Notification) {
    let payload = ProactiveTestNotificationPayload(notification)
    DispatchQueue.main.async { [handler] in
      MainActor.assumeIsolated {
        handler(payload)
      }
    }
  }
}

/// The sole boundary for completion-handler UserNotifications APIs.
///
/// System callback registration remains nonisolated and copies only Sendable
/// values. It then makes an explicit GCD hop before entering a MainActor
/// handler, preventing release builds from running actor-isolated work on the
/// framework's private XPC callback queue.
enum UserNotificationCallbackBridge {
  static let signedSmokeResultPathEnvironmentKey = "OMI_NOTIFICATION_CALLBACK_SMOKE_RESULT_PATH"

  typealias SettingsQuery = @Sendable (@escaping @Sendable (UserNotificationSettingsSnapshot) -> Void) -> Void

  nonisolated static func notificationSettings(
    handler: @escaping @MainActor @Sendable (UserNotificationSettingsSnapshot) -> Void
  ) {
    notificationSettings(query: systemNotificationSettingsQuery, handler: handler)
  }

  /// Test seam for the framework callback only. The handoff remains the same
  /// production dispatcher, so callers can prove an off-main callback cannot
  /// enter a MainActor handler directly.
  nonisolated static func notificationSettings(
    query: @escaping SettingsQuery,
    handler: @escaping @MainActor @Sendable (UserNotificationSettingsSnapshot) -> Void
  ) {
    query { snapshot in
      dispatchToMain {
        handler(snapshot)
      }
    }
  }

  nonisolated static func authorizationStatus(
    handler: @escaping @MainActor @Sendable (UNAuthorizationStatus) -> Void
  ) {
    notificationSettings { snapshot in
      handler(snapshot.authorizationStatus)
    }
  }

  nonisolated static func requestAuthorization(
    options: UNAuthorizationOptions = [.alert, .sound, .badge],
    completion: @escaping @MainActor @Sendable (UserNotificationAuthorizationResult) -> Void
  ) {
    UNUserNotificationCenter.current().requestAuthorization(options: options) { granted, error in
      let nsError = error as NSError?
      let result = UserNotificationAuthorizationResult(
        granted: granted,
        errorDescription: error?.localizedDescription,
        errorDomain: nsError?.domain,
        errorCode: nsError?.code
      )
      dispatchToMain {
        completion(result)
      }
    }
  }

  nonisolated static func add(
    _ request: UNNotificationRequest,
    completion: @escaping @MainActor @Sendable (UserNotificationDeliveryResult) -> Void
  ) {
    UNUserNotificationCenter.current().add(request) { error in
      let result = UserNotificationDeliveryResult(errorDescription: error?.localizedDescription)
      dispatchToMain {
        completion(result)
      }
    }
  }

  /// Distribution-only probe for the signed artifact smoke suite. It has no
  /// effect unless the caller provides an explicit marker path, and it queries
  /// notification settings without prompting or accessing product services.
  static func runSignedSmokeIfRequested(
    environment: [String: String] = ProcessInfo.processInfo.environment
  ) -> Bool {
    guard let path = environment[signedSmokeResultPathEnvironmentKey], !path.isEmpty else { return false }
    let resultURL = URL(fileURLWithPath: path)
    authorizationStatus { status in
      let succeeded = Thread.isMainThread
      let marker = "main_actor=\(succeeded ? "true" : "false") authorization_status=\(status.rawValue)\n"
      do {
        try marker.write(to: resultURL, atomically: true, encoding: .utf8)
        chmod(resultURL.path, S_IRUSR | S_IWUSR)
      } catch {
        NSLog("OMI NOTIFICATION CALLBACK SMOKE: failed to write result: %@", error.localizedDescription)
      }
      NSLog("OMI NOTIFICATION CALLBACK SMOKE: mainActor=%@", succeeded ? "true" : "false")
      NSApplication.shared.terminate(nil)
    }
    return true
  }

  nonisolated private static func systemNotificationSettingsQuery(
    completion: @escaping @Sendable (UserNotificationSettingsSnapshot) -> Void
  ) {
    UNUserNotificationCenter.current().getNotificationSettings { settings in
      completion(UserNotificationSettingsSnapshot(settings))
    }
  }

  nonisolated private static func dispatchToMain(_ work: @escaping @MainActor @Sendable () -> Void) {
    DispatchQueue.main.async {
      MainActor.assumeIsolated {
        work()
      }
    }
  }
}
