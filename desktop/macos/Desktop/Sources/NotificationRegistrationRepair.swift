import Cocoa
@preconcurrency import UserNotifications

enum NotificationRegistrationRepair {
  static let repairedVersionKey = "notificationRegistrationRepairedAppVersion"
  static let startupRepairAttemptedVersionKey = "notificationStartupRepairAttemptedAppVersion"

  private nonisolated(unsafe) static var isRepairing = false
  private nonisolated(unsafe) static var pendingCompletions: [(Bool) -> Void] = []

  static func currentVersionIdentifier(bundle: Bundle = .main) -> String {
    let version =
      bundle.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? "unknown"
    let build = bundle.object(forInfoDictionaryKey: "CFBundleVersion") as? String ?? "unknown"
    return "\(version)+\(build)"
  }

  static func shouldRepairForCurrentVersion(
    defaults: UserDefaults = .standard,
    versionIdentifier: String = currentVersionIdentifier()
  ) -> Bool {
    defaults.string(forKey: repairedVersionKey) != versionIdentifier
  }

  static func markRepairedForCurrentVersion(
    defaults: UserDefaults = .standard,
    versionIdentifier: String = currentVersionIdentifier()
  ) {
    defaults.set(versionIdentifier, forKey: repairedVersionKey)
  }

  /// Whether the non-user-initiated startup path may attempt a launch-services
  /// notification repair. Users stuck in the launch-disabled + notDetermined state
  /// would otherwise re-run lsregister + killall usernoted/NotificationCenter on
  /// every launch/wake; gate that attempt to once per installed app version.
  static func shouldAttemptStartupRepair(
    defaults: UserDefaults = .standard,
    versionIdentifier: String = currentVersionIdentifier()
  ) -> Bool {
    defaults.string(forKey: startupRepairAttemptedVersionKey) != versionIdentifier
  }

  static func markStartupRepairAttempted(
    defaults: UserDefaults = .standard,
    versionIdentifier: String = currentVersionIdentifier()
  ) {
    defaults.set(versionIdentifier, forKey: startupRepairAttemptedVersionKey)
  }

  @MainActor
  static func repairOnceForCurrentVersion(reason: String) {
    let versionIdentifier = currentVersionIdentifier()
    guard shouldRepairForCurrentVersion(versionIdentifier: versionIdentifier) else { return }

    repair(reason: reason, includeUnregister: true) { success in
      if success {
        markRepairedForCurrentVersion(versionIdentifier: versionIdentifier)
      }
    }
  }

  @MainActor
  static func requestAuthorizationRepairingLaunchServices(
    reason: String,
    previousStatus: String,
    completion: (@Sendable (Bool) -> Void)? = nil
  ) {
    NSApp.activate()
    UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .sound, .badge]) {
      granted, error in
      if let error {
        let nsError = error as NSError
        log(
          "Notification permission request error: \(error.localizedDescription) (domain=\(nsError.domain) code=\(nsError.code))"
        )

        if isLaunchDisabledNotificationError(nsError) {
          DispatchQueue.main.async {
            AnalyticsManager.shared.notificationRepairTriggered(
              reason: reason,
              previousStatus: previousStatus,
              currentStatus: "error_code_1"
            )
            repair(reason: reason, includeUnregister: true) { _ in
              retryAuthorizationAfterRepair(completion: completion)
            }
          }
          return
        }
      }

      DispatchQueue.main.async {
        completion?(granted)
      }
    }
  }

  @MainActor
  static func repair(
    reason: String,
    includeUnregister: Bool,
    completion: ((Bool) -> Void)? = nil
  ) {
    if let completion {
      pendingCompletions.append(completion)
    }

    guard !isRepairing else {
      log("Notification registration repair already running; coalescing request (\(reason))")
      return
    }

    isRepairing = true
    let appPath = Bundle.main.bundlePath
    let bundleURL = Bundle.main.bundleURL
    log("Repairing notification registration via LaunchServices: \(appPath) reason=\(reason)")

    DispatchQueue.global(qos: .utility).async {
      let lsregister =
        "/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister"
      var success = true

      if includeUnregister {
        success = runProcess(lsregister, arguments: ["-u", appPath]) && success
      }
      success = runProcess(lsregister, arguments: ["-f", appPath]) && success

      let restartedUsernoted = runProcess("/usr/bin/killall", arguments: ["usernoted"])
      let restartedNotificationCenter = runProcess(
        "/usr/bin/killall", arguments: ["NotificationCenter"])
      log(
        "Notification registration repair finished: lsregisterSuccess=\(success), usernotedRestarted=\(restartedUsernoted), notificationCenterRestarted=\(restartedNotificationCenter)"
      )

      Thread.sleep(forTimeInterval: 1.5)

      let capturedSuccess = success
      DispatchQueue.main.async {
        var finalSuccess = capturedSuccess
        if let cfURL = bundleURL as CFURL? {
          let registerStatus = LSRegisterURL(cfURL, true)
          let registerSucceeded = registerStatus == noErr
          finalSuccess = registerSucceeded && finalSuccess
          if !registerSucceeded {
            log("LSRegisterURL failed during notification registration repair: \(registerStatus)")
          }
        } else {
          finalSuccess = false
          log("LSRegisterURL skipped during notification registration repair: missing bundle URL")
        }
        finishRepair(success: finalSuccess)
      }
    }
  }

  @MainActor
  private static func finishRepair(success: Bool) {
    let callbacks = pendingCompletions
    pendingCompletions.removeAll()
    isRepairing = false
    callbacks.forEach { $0(success) }
  }

  private static func retryAuthorizationAfterRepair(completion: (@Sendable (Bool) -> Void)?) {
    DispatchQueue.main.asyncAfter(deadline: .now() + 1.0) {
      NSApp.activate()
      UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .sound, .badge]) {
        granted, error in
        if let error {
          log("Notification retry after registration repair failed: \(error.localizedDescription)")
        } else if granted {
          log("Notification permission granted after registration repair")
        }

        DispatchQueue.main.async {
          completion?(granted)
        }
      }
    }
  }

  private static func isLaunchDisabledNotificationError(_ error: NSError) -> Bool {
    error.domain == "UNErrorDomain" && error.code == 1
  }

  private static func runProcess(_ executablePath: String, arguments: [String]) -> Bool {
    let process = Process()
    process.executableURL = URL(fileURLWithPath: executablePath)
    process.arguments = arguments
    process.standardOutput = FileHandle.nullDevice
    process.standardError = FileHandle.nullDevice

    do {
      try process.run()
      process.waitUntilExit()
      return process.terminationStatus == 0
    } catch {
      logError("Notification registration repair command failed: \(executablePath)", error: error)
      return false
    }
  }
}
