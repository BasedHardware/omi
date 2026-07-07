import AVFoundation
import Combine
import SwiftUI
import UserNotifications

@MainActor
extension AppState {
  func openScreenRecordingPreferences() {
    ScreenCaptureService.openScreenRecordingPreferences()
  }

  func openAutomationPreferences() {
    if let url = URL(
      string: "x-apple.systempreferences:com.apple.preference.security?Privacy_Automation")
    {
      NSWorkspace.shared.open(url)
    }
  }

  func requestNotificationPermission() {
    // First check current authorization status
    UNUserNotificationCenter.current().getNotificationSettings { [weak self] settings in
      DispatchQueue.main.async {
        guard let self = self else { return }

        if settings.authorizationStatus == .notDetermined {
          // First time - show the system prompt
          NotificationRegistrationRepair.requestAuthorizationRepairingLaunchServices(
            reason: "launch_disabled_error",
            previousStatus: "notDetermined"
          ) { [weak self] _ in
            self?.checkNotificationPermission()
          }
        } else if settings.authorizationStatus == .denied {
          // Previously denied - open System Settings so user can enable manually
          self.openNotificationPreferences()
        }
        // If already authorized, checkNotificationPermission() will handle it
      }
    }
  }

  /// Repair LaunchServices registration when notification authorization fails.
  /// The "launch-disabled" flag in LaunchServices prevents the notification center
  /// from registering the app. This unregisters and re-registers to clear the flag.
  func repairNotificationRegistrationAndRetry() {
    NotificationRegistrationRepair.repair(reason: "app_state_retry", includeUnregister: true) {
      [weak self] _ in
      NotificationRegistrationRepair.requestAuthorizationRepairingLaunchServices(
        reason: "launch_disabled_error_retry",
        previousStatus: "post_repair"
      ) { [weak self] _ in
        self?.checkNotificationPermission()
      }
    }

    // After the repair + retry, update our permission state and open System Settings as fallback.
    DispatchQueue.main.asyncAfter(deadline: .now() + 5.0) { [weak self] in
      UNUserNotificationCenter.current().getNotificationSettings { settings in
        DispatchQueue.main.async {
          let isNowGranted = settings.authorizationStatus == .authorized
          self?.hasNotificationPermission = isNowGranted
          if !isNowGranted {
            log("Notification permission still not granted after repair. Opening System Settings.")
            self?.openNotificationPreferences()
          }
        }
      }
    }
  }

  /// Repair notification registration via lsregister, then fall back to System Settings if still broken.
  /// Called from sidebar and settings "Fix" buttons when auth is not authorized.
  func repairNotificationAndFallback() {
    log("Fix button tapped — running lsregister repair for notifications")
    NotificationRegistrationRepair.repair(reason: "settings_fix_button", includeUnregister: true) {
      [weak self] _ in
      NotificationRegistrationRepair.requestAuthorizationRepairingLaunchServices(
        reason: "settings_fix_button_retry",
        previousStatus: "post_repair"
      ) { [weak self] _ in
        self?.checkNotificationPermission()
      }
    }

    // Wait for repair + re-authorization, then check if it worked
    DispatchQueue.main.asyncAfter(deadline: .now() + 4.0) { [weak self] in
      UNUserNotificationCenter.current().getNotificationSettings { settings in
        DispatchQueue.main.async {
          let isNowGranted = settings.authorizationStatus == .authorized
          self?.hasNotificationPermission = isNowGranted
          self?.notificationAlertStyle = settings.alertStyle
          if isNowGranted {
            log("Notification repair succeeded — auth is now authorized")
          } else {
            log(
              "Notification repair didn't restore auth (status=\(settings.authorizationStatus.rawValue)) — opening System Settings"
            )
            self?.openNotificationPreferences()
          }
        }
      }
    }
  }

  /// Trigger screen recording permission prompt
  func triggerScreenRecordingPermission() {
    // Request both traditional TCC and ScreenCaptureKit permissions
    ScreenCaptureService.requestAllScreenCapturePermissions()
  }

  /// Trigger automation permission by attempting to use Apple Events
  nonisolated func triggerAutomationPermission() {
    // Run a simple AppleScript to trigger the permission prompt
    // This must be done on a background thread since it's nonisolated
    Task.detached {
      // First, ensure System Events is running — without it, the TCC prompt won't appear
      // and checkAutomationPermission returns -600 (procNotFound)
      let launchScript = NSAppleScript(
        source: """
              launch application "System Events"
          """)
      var launchError: NSDictionary?
      launchScript?.executeAndReturnError(&launchError)
      if let launchError = launchError {
        log("AUTOMATION_TRIGGER: Failed to launch System Events: \(launchError)")
      } else {
        log("AUTOMATION_TRIGGER: System Events launched successfully")
      }

      // Small delay to let System Events initialize
      try? await Task.sleep(nanoseconds: 500_000_000)

      // Now trigger the actual TCC prompt
      let script = NSAppleScript(
        source: """
              tell application "System Events"
                  return name of first process whose frontmost is true
              end tell
          """)
      var error: NSDictionary?
      script?.executeAndReturnError(&error)

      if let error = error {
        let errorNum = error[NSAppleScript.errorNumber] as? Int ?? 0
        let errorMsg = error[NSAppleScript.errorMessage] as? String ?? "unknown"
        log("AUTOMATION_TRIGGER: AppleScript failed: \(errorNum) - \(errorMsg)")
      } else {
        log("AUTOMATION_TRIGGER: AppleScript succeeded, permission may have been granted")
      }

      // Re-check permission status after the TCC dialog
      await MainActor.run { [weak self] in
        self?.checkAutomationPermission()
      }

      // Small delay to let the check complete
      try? await Task.sleep(nanoseconds: 300_000_000)

      // Only open Settings if the TCC dialog didn't grant permission
      let granted = await MainActor.run { [weak self] in
        self?.hasAutomationPermission ?? false
      }
      if !granted {
        await MainActor.run {
          if let url = URL(
            string: "x-apple.systempreferences:com.apple.preference.security?Privacy_Automation")
          {
            NSWorkspace.shared.open(url)
          }
        }
      }
    }
  }

  // MARK: - Permission Status Checks

  /// Check and update all permission states
  func checkAllPermissions() {
    checkNotificationPermission()
    checkScreenRecordingPermission()
    checkMicrophonePermission()
    checkSystemAudioPermission()

    if AppBuild.usesLazyDevPermissions {
      log("Permissions: lazy dev mode enabled, skipping startup automation/accessibility/FDA probes")
      return
    }

    checkAutomationPermission()
    checkAccessibilityPermission()
    checkFullDiskAccess()
    // One-time startup diagnostic for accessibility
    let osVersion = ProcessInfo.processInfo.operatingSystemVersion
    let bundleId = Bundle.main.bundleIdentifier ?? "unknown"
    log(
      "ACCESSIBILITY_STARTUP: bundleId=\(bundleId), macOS=\(osVersion.majorVersion).\(osVersion.minorVersion).\(osVersion.patchVersion), TCC=\(hasAccessibilityPermission), broken=\(isAccessibilityBroken), onboarded=\(hasCompletedOnboarding)"
    )
    // Only check Bluetooth if already initialized (to avoid triggering permission prompt early)
    if bluetoothStateCancellable != nil {
      checkBluetoothPermission()
    }
  }

  /// Check Bluetooth permission status
  /// Bluetooth is considered "granted" if state is poweredOn or poweredOff (allowed but BT off)
  /// IMPORTANT: Only call this after initializeBluetoothIfNeeded() has been called
  func checkBluetoothPermission() {
    // Guard: Only check if Bluetooth has been initialized (to avoid triggering permission prompt early)
    guard bluetoothStateCancellable != nil else {
      log("BLUETOOTH_CHECK: Skipping - Bluetooth not initialized yet")
      return
    }
    let state = BluetoothManager.shared.bluetoothState
    let oldValue = hasBluetoothPermission
    // poweredOn = ready to use, poweredOff = allowed but BT is off
    // unauthorized = denied
    let newValue = state == .poweredOn || state == .poweredOff
    log(
      "BLUETOOTH_CHECK: state=\(BluetoothManager.shared.bluetoothStateDescription), stateRaw=\(state.rawValue), auth=\(BluetoothManager.shared.authorizationDescription), granted=\(newValue)"
    )
    if newValue != oldValue {
      log(
        "Bluetooth permission changed: \(oldValue) -> \(newValue), state=\(BluetoothManager.shared.bluetoothStateDescription)"
      )
    }
    hasBluetoothPermission = newValue
  }

  /// Trigger Bluetooth permission by attempting to scan
  /// On macOS, the permission dialog only appears when actually using Bluetooth
  func triggerBluetoothPermission() {
    // Ensure Bluetooth is initialized first (this is expected to be called from the Bluetooth onboarding step)
    initializeBluetoothIfNeeded()

    log(
      "triggerBluetoothPermission: Starting, state=\(BluetoothManager.shared.bluetoothStateDescription), auth=\(BluetoothManager.shared.authorizationDescription)"
    )
    // Trigger the permission prompt by attempting to scan
    // This bypasses state checks because we specifically want the system dialog
    BluetoothManager.shared.triggerPermissionPrompt()
    // Check permission state after a delay to allow user to respond
    DispatchQueue.main.asyncAfter(deadline: .now() + 1.0) {
      log(
        "triggerBluetoothPermission: After 1s delay, state=\(BluetoothManager.shared.bluetoothStateDescription), auth=\(BluetoothManager.shared.authorizationDescription)"
      )
      self.checkBluetoothPermission()
    }
    // Also check again after 3 seconds in case state updates slowly
    DispatchQueue.main.asyncAfter(deadline: .now() + 3.0) {
      log(
        "triggerBluetoothPermission: After 3s delay, state=\(BluetoothManager.shared.bluetoothStateDescription), auth=\(BluetoothManager.shared.authorizationDescription)"
      )
      self.checkBluetoothPermission()
    }
  }

  /// Check if Bluetooth permission was explicitly denied
  /// Returns false if Bluetooth hasn't been initialized yet (to avoid triggering permission prompt)
  func isBluetoothPermissionDenied() -> Bool {
    // Guard: Only check if Bluetooth has been initialized
    guard bluetoothStateCancellable != nil else {
      return false
    }
    return BluetoothManager.shared.bluetoothState == .unauthorized
  }

  /// Check if Bluetooth is reported as unsupported (may be macOS version issue)
  /// Returns false if Bluetooth hasn't been initialized yet (to avoid triggering permission prompt)
  func isBluetoothUnsupported() -> Bool {
    // Guard: Only check if Bluetooth has been initialized
    guard bluetoothStateCancellable != nil else {
      return false
    }
    return BluetoothManager.shared.bluetoothState == .unsupported
  }

  /// Open Bluetooth preferences in System Settings
  func openBluetoothPreferences() {
    if let url = URL(
      string: "x-apple.systempreferences:com.apple.preference.security?Privacy_Bluetooth")
    {
      NSWorkspace.shared.open(url)
    }
  }

  /// Check notification permission status and alert style
  func checkNotificationPermission() {
    // Dispatch async to avoid calling UNUserNotificationCenter.current() during
    // SwiftUI view body evaluation, which triggers an assertion in UserNotifications.
    DispatchQueue.main.async { [weak self] in
      guard let self else { return }
      UNUserNotificationCenter.current().getNotificationSettings { settings in
      DispatchQueue.main.async {
        let isNowGranted = settings.authorizationStatus == .authorized
        self.hasNotificationPermission = isNowGranted
        self.notificationAlertStyle = settings.alertStyle

        // Log the current notification settings
        let authStatus =
          switch settings.authorizationStatus {
          case .notDetermined: "notDetermined"
          case .denied: "denied"
          case .authorized: "authorized"
          case .provisional: "provisional"
          case .ephemeral: "ephemeral"
          @unknown default: "unknown"
          }
        let alertStyleName =
          switch settings.alertStyle {
          case .none: "NONE (no banners)"
          case .banner: "BANNER"
          case .alert: "ALERT"
          @unknown default: "unknown"
          }
        log(
          "Notification settings: auth=\(authStatus), alertStyle=\(alertStyleName), sound=\(settings.soundSetting.rawValue), badge=\(settings.badgeSetting.rawValue)"
        )

        // Track notification settings in analytics only when they change
        let soundEnabled = settings.soundSetting == .enabled
        let badgeEnabled = settings.badgeSetting == .enabled
        let settingsChanged =
          authStatus != self.lastNotificationAuthStatus
          || alertStyleName != self.lastNotificationAlertStyle
          || soundEnabled != self.lastNotificationSoundEnabled
          || badgeEnabled != self.lastNotificationBadgeEnabled

        if settingsChanged {
          AnalyticsManager.shared.notificationSettingsChecked(
            authStatus: authStatus,
            alertStyle: alertStyleName,
            soundEnabled: soundEnabled,
            badgeEnabled: badgeEnabled,
            bannersDisabled: settings.alertStyle == .none
          )

          // Detect regression: was authorized, now reverted to notDetermined
          // This happens on macOS 26+ where the OS silently revokes notification permission
          if self.lastNotificationAuthStatus == "authorized" && authStatus == "notDetermined" {
            log(
              "Notification permission REGRESSED from authorized to notDetermined — triggering auto-repair"
            )
            AnalyticsManager.shared.notificationRepairTriggered(
              reason: "auth_regression",
              previousStatus: "authorized",
              currentStatus: "notDetermined"
            )
            self.repairNotificationRegistrationAndRetry()
          }

          // Update last known state
          self.lastNotificationAuthStatus = authStatus
          self.lastNotificationAlertStyle = alertStyleName
          self.lastNotificationSoundEnabled = soundEnabled
          self.lastNotificationBadgeEnabled = badgeEnabled
        }

      }
    }
    }  // end DispatchQueue.main.async
  }

  /// Check screen recording permission status
  func checkScreenRecordingPermission() {
    let permissionGranted = ScreenCaptureService.checkPermission()
    hasScreenRecordingPermission = ScreenRecordingPermissionPolicy.uiPermissionGranted(
      tccGranted: permissionGranted)

    if !permissionGranted {
      isScreenCaptureKitBroken = false
      isScreenRecordingStale = false
      return
    }

    // Permission is granted. Capture-engine failures are handled by the
    // monitoring pipeline and must not make the permission badge red.
    isScreenRecordingStale = false
    isScreenCaptureKitBroken = false
    screenRecordingGrantAttempts = 0
    UserDefaults.standard.removeObject(forKey: NotificationService.screenCaptureResetShownKey)
  }

  /// Check automation permission without triggering a prompt
  /// Uses AEDeterminePermissionToAutomateTarget to query TCC status for System Events
  func checkAutomationPermission() {
    guard !isCheckingAutomationPermission else { return }
    isCheckingAutomationPermission = true
    Task.detached {
      defer { Task { @MainActor in self.isCheckingAutomationPermission = false } }
      let status = Self.queryAutomationPermissionStatus()

      // noErr (0) = granted, errAEEventNotPermitted (-1743) = denied, -1744 = not determined
      // -600 (procNotFound) = System Events not running — try to launch it and retry
      if status == -600 {
        log("AUTOMATION_CHECK: status=-600 (procNotFound), launching System Events and retrying...")
        let launchScript = NSAppleScript(source: "launch application \"System Events\"")
        var launchError: NSDictionary?
        launchScript?.executeAndReturnError(&launchError)

        // Wait for System Events to initialize
        try? await Task.sleep(nanoseconds: 1_000_000_000)

        let retryStatus = Self.queryAutomationPermissionStatus()
        let hasPermission = retryStatus == noErr
        log("AUTOMATION_CHECK: retry status=\(retryStatus), hasPermission=\(hasPermission)")

        await MainActor.run {
          self.hasAutomationPermission = hasPermission
          self.automationPermissionError = hasPermission ? 0 : retryStatus
        }
      } else {
        let hasPermission = status == noErr
        let previousValue = await MainActor.run { self.hasAutomationPermission }
        if hasPermission != previousValue {
          log("AUTOMATION_CHECK: status=\(status), hasPermission=\(hasPermission)")
        }

        await MainActor.run {
          self.hasAutomationPermission = hasPermission
          // Track unexpected errors (not denied/not-determined, which are normal states)
          self.automationPermissionError =
            (status == noErr || status == -1743 || status == -1744) ? 0 : status
        }
      }
    }
  }

  /// Query the TCC automation permission status for System Events without triggering a prompt
  nonisolated static func queryAutomationPermissionStatus() -> OSStatus {
    let bundleIDString = "com.apple.systemevents"
    var addressDesc = AEAddressDesc()

    let status: OSStatus = bundleIDString.withCString { cString in
      AECreateDesc(typeApplicationBundleID, cString, strlen(cString), &addressDesc)
      let result = AEDeterminePermissionToAutomateTarget(
        &addressDesc,
        typeWildCard,
        typeWildCard,
        false  // askUserIfNeeded = false → never shows dialog
      )
      AEDisposeDesc(&addressDesc)
      return result
    }

    return status
  }

  /// Check accessibility permission status
  /// AXIsProcessTrusted() can return stale data after macOS updates or app re-signs,
  /// so we also do a functional AX test to detect the "broken" state.
  func checkAccessibilityPermission() {
    let tccGranted = AXIsProcessTrusted()
    let previouslyGranted = hasAccessibilityPermission

    if tccGranted {
      hasAccessibilityPermission = true

      // Log transitions
      if !previouslyGranted {
        let bundleId = Bundle.main.bundleIdentifier ?? "unknown"
        log("ACCESSIBILITY_CHECK: Permission granted (bundleId=\(bundleId))")
      }

      // TCC says yes — verify with an actual AX call
      let broken = !testAccessibilityPermission()
      if broken != isAccessibilityBroken {
        isAccessibilityBroken = broken
        if broken {
          log(
            "ACCESSIBILITY_CHECK: TCC says granted but AX calls fail — stuck/broken state detected")
        } else {
          log("ACCESSIBILITY_CHECK: AX calls working normally")
        }
      }
    } else {
      // AXIsProcessTrusted() says not granted — but on macOS 26 this may be stale.
      // Probe via event tap which checks the live TCC database.
      if probeAccessibilityViaEventTap() {
        if !previouslyGranted {
          log(
            "ACCESSIBILITY_CHECK: AXIsProcessTrusted() returned false but event tap succeeded — stale cache detected"
          )
        }
        let axWorks = testAccessibilityPermission()
        hasAccessibilityPermission = true
        if !axWorks {
          if !isAccessibilityBroken {
            log("ACCESSIBILITY_CHECK: Event tap OK but AX calls fail — marking as broken")
          }
          isAccessibilityBroken = true
        } else {
          if isAccessibilityBroken {
            log("ACCESSIBILITY_CHECK: Permission confirmed via event tap probe, AX calls working")
          }
          isAccessibilityBroken = false
        }
      } else {
        // Event tap also failed — permission genuinely not granted
        if previouslyGranted {
          let bundleId = Bundle.main.bundleIdentifier ?? "unknown"
          log("ACCESSIBILITY_CHECK: Permission revoked (bundleId=\(bundleId))")
        }
        hasAccessibilityPermission = false
        isAccessibilityBroken = false
      }
    }
  }

  /// Check Full Disk Access by probing FDA-protected paths.
  /// The TCC database query is unreliable on macOS 15+ (schema changes, ad-hoc signing),
  /// so we probe actual protected directories instead.
  func checkFullDiskAccess() {
    let home = FileManager.default.homeDirectoryForCurrentUser.path
    // These paths are protected by Full Disk Access on all macOS versions.
    // Try to list directory contents — if it succeeds, FDA is granted.
    let protectedPaths = [
      "\(home)/Library/Safari",
      "\(home)/Library/Mail",
      "\(home)/Library/Messages",
    ]

    var granted = false
    for path in protectedPaths {
      if FileManager.default.fileExists(atPath: path) {
        granted = (try? FileManager.default.contentsOfDirectory(atPath: path)) != nil
        break
      }
    }

    if granted != hasFullDiskAccess {
      hasFullDiskAccess = granted
      log("Full Disk Access: \(granted ? "granted" : "not granted") (file probe)")
    }
  }

  /// Test if Accessibility API actually works by attempting a real AX call.
  /// Returns true if AX calls succeed, false if permission is stuck/broken.
  func testAccessibilityPermission() -> Bool {
    guard let frontApp = NSWorkspace.shared.frontmostApplication else {
      // No frontmost app to test against — can't determine, assume OK
      return true
    }

    let appElement = AXUIElementCreateApplication(frontApp.processIdentifier)
    var focusedWindow: CFTypeRef?
    let result = AXUIElementCopyAttributeValue(
      appElement, kAXFocusedWindowAttribute as CFString, &focusedWindow)

    // .success or .noValue (app has no windows) both mean AX is working
    switch result {
    case .success, .noValue, .notImplemented, .attributeUnsupported:
      return true
    case .apiDisabled:
      // System-wide AX is disabled — unambiguous, no confirmation needed
      log(
        "ACCESSIBILITY_CHECK: AXError.apiDisabled — permission stuck (tested against pid \(frontApp.processIdentifier), app: \(frontApp.localizedName ?? "unknown"))"
      )
      return false
    case .cannotComplete:
      // cannotComplete is ambiguous: it can mean our permission is broken, OR that the
      // frontmost app doesn't implement AX (e.g. Qt, OpenGL, Python-based apps like PyMOL).
      // Confirm against Finder before concluding the permission is truly broken.
      return confirmAccessibilityBrokenViaFinder(suspectApp: frontApp.localizedName ?? "unknown")
    default:
      log(
        "ACCESSIBILITY_CHECK: AXError code \(result.rawValue) from app \(frontApp.localizedName ?? "unknown") — not permission-related, treating as OK"
      )
      return true
    }
  }

  /// Secondary AX check against Finder to disambiguate cannotComplete errors.
  /// If Finder (a known AX-compliant app) also fails, the permission is truly broken.
  /// If Finder succeeds, the original failure was app-specific, not a permission issue.
  func confirmAccessibilityBrokenViaFinder(suspectApp: String) -> Bool {
    if let finder = NSRunningApplication.runningApplications(
      withBundleIdentifier: "com.apple.finder"
    ).first {
      let finderElement = AXUIElementCreateApplication(finder.processIdentifier)
      var finderWindow: CFTypeRef?
      let finderResult = AXUIElementCopyAttributeValue(
        finderElement, kAXFocusedWindowAttribute as CFString, &finderWindow)
      if finderResult == .cannotComplete || finderResult == .apiDisabled {
        log(
          "ACCESSIBILITY_CHECK: AXError.cannotComplete confirmed by Finder — permission is truly stuck (original app: \(suspectApp))"
        )
        return false
      } else {
        log(
          "ACCESSIBILITY_CHECK: AXError.cannotComplete from \(suspectApp) but Finder OK — app-specific AX incompatibility, permission is fine"
        )
        return true
      }
    } else {
      // Finder not running — fall back to event tap probe as tie-breaker
      log(
        "ACCESSIBILITY_CHECK: AXError.cannotComplete from \(suspectApp), Finder not running — using event tap probe"
      )
      return probeAccessibilityViaEventTap()
    }
  }

  /// Probe accessibility permission by attempting to create a CGEvent tap.
  /// Unlike AXIsProcessTrusted(), event tap creation checks the live TCC database,
  /// bypassing the per-process cache that can go stale on macOS 26 (Tahoe).
  func probeAccessibilityViaEventTap() -> Bool {
    let tap = CGEvent.tapCreate(
      tap: .cgSessionEventTap,
      place: .tailAppendEventTap,
      options: .listenOnly,
      eventsOfInterest: CGEventMask(1 << CGEventType.mouseMoved.rawValue),
      callback: { _, _, event, _ in Unmanaged.passRetained(event) },
      userInfo: nil
    )
    if let tap = tap {
      CFMachPortInvalidate(tap)
      return true
    }
    return false
  }

  /// Check if accessibility permission was explicitly denied
  func isAccessibilityPermissionDenied() -> Bool {
    return hasCompletedOnboarding && (!hasAccessibilityPermission || isAccessibilityBroken)
  }

  /// Trigger accessibility permission prompt
  func triggerAccessibilityPermission() {
    let osVersion = ProcessInfo.processInfo.operatingSystemVersion
    let bundleId = Bundle.main.bundleIdentifier ?? "unknown"
    log(
      "ACCESSIBILITY_TRIGGER: User clicked Grant Access — bundleId=\(bundleId), macOS \(osVersion.majorVersion).\(osVersion.minorVersion).\(osVersion.patchVersion)"
    )

    // This will prompt the user if not already trusted
    let options =
      [kAXTrustedCheckOptionPrompt.takeUnretainedValue() as String: true] as CFDictionary
    let trusted = AXIsProcessTrustedWithOptions(options)
    if trusted {
      hasAccessibilityPermission = true
    }
    // Don't set hasAccessibilityPermission = false here — the API may return
    // stale data on macOS 26. Let checkAccessibilityPermission() handle detection
    // via the event tap probe on the next poll cycle.
    log("ACCESSIBILITY_TRIGGER: AXIsProcessTrustedWithOptions returned \(trusted)")

    // On macOS Sequoia+, AXIsProcessTrustedWithOptions no longer shows a visible dialog,
    // so explicitly open System Settings to the Accessibility pane
    if !trusted {
      log("ACCESSIBILITY_TRIGGER: Not trusted, opening System Settings Accessibility pane")
      openAccessibilityPreferences()
    }
  }

  /// Open Accessibility preferences in System Settings
  func openAccessibilityPreferences() {
    if let url = URL(
      string: "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility")
    {
      NSWorkspace.shared.open(url)
    }
  }

  /// Reset accessibility permission (requires terminal command)
  nonisolated func resetAccessibilityPermissionDirect(shouldRestart: Bool = false) -> Bool {
    let bundleId = Bundle.main.bundleIdentifier ?? "com.omi.computer-macos"
    log("Resetting accessibility permission for \(bundleId) via tccutil...")

    let success = SystemCommand.runLogging(
      "tccutil reset Accessibility (\(bundleId))",
      executable: "/usr/bin/tccutil",
      arguments: ["reset", "Accessibility", bundleId])

    if success && shouldRestart {
      restartApp()
    }

    return success
  }

  /// Reset accessibility permission via tccutil and restart the app.
  /// Mirrors ScreenCaptureService.resetScreenCapturePermissionAndRestart().
  func resetAccessibilityPermissionAndRestart() {
    if UpdaterViewModel.isUpdateInProgress {
      log("Sparkle update in progress, skipping accessibility reset restart")
      return
    }

    Task.detached { [weak self] in
      guard let self = self else { return }
      let success = self.resetAccessibilityPermissionDirect(shouldRestart: false)

      await MainActor.run {
        if success {
          log("Accessibility permission reset, restarting app...")
          self.restartApp()
        } else {
          log("Accessibility permission reset failed")
        }
      }
    }
  }

  func showPermissionAlert() {
    let alert = NSAlert()
    alert.messageText = "Permission Required"
    alert.informativeText =
      "Screen Recording permission is needed.\n\nClick 'Grant Screen Permission' in the menu, then add this app and restart."
    alert.alertStyle = .warning
    alert.addButton(withTitle: "OK")
    alert.runModal()
  }

  func showAlert(title: String, message: String) {
    let alert = NSAlert()
    alert.messageText = title
    alert.informativeText = message
    alert.alertStyle = .warning
    alert.addButton(withTitle: "OK")
    alert.runModal()
  }

  // MARK: - Transcription

  /// Toggle transcription on/off
}
