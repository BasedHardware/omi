@preconcurrency import AVFoundation
@preconcurrency import ApplicationServices
import Combine
import SwiftUI
@preconcurrency import UserNotifications

/// How many permissions the last refresh found granted, so the next one can tell a grant from a
/// re-read. `nil` until the first refresh establishes that baseline.
///
/// File scope rather than a stored property because `AppState` is a singleton and this extension
/// cannot add storage to it; the value is meaningful only to `notePermissionGrants` below.
@MainActor private var lastGrantedPermissionCount: Int?

/// The AppKit lookups the accessibility probe depends on, read once on the main
/// actor and handed to the probe as plain values so the expensive cross-process
/// AX round trips can run off it.
struct AccessibilityProbeTargets: Sendable, Equatable {
  var frontmostProcessID: pid_t?
  var frontmostName: String
  var finderProcessID: pid_t?
}

/// What the accessibility probes observed. Kept separate from the decision so
/// the decision is a pure function that can be exercised for every combination
/// without a live TCC database.
struct AccessibilityProbeSignals: Sendable, Equatable {
  /// `AXIsProcessTrusted()` — authoritative when true, stale-able when false.
  var tccTrusted: Bool
  /// A `CGEvent.tapCreate` succeeded, which reads the live TCC database.
  var eventTapWorks: Bool
  /// A real `AXUIElementCopyAttributeValue` succeeded.
  var axCallsWork: Bool
}

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
    UserNotificationCallbackBridge.authorizationStatus { [weak self] authorizationStatus in
      guard let self else { return }

      if authorizationStatus == .notDetermined {
        // First time - show the system prompt
        NotificationRegistrationRepair.requestAuthorizationRepairingLaunchServices(
          reason: "launch_disabled_error",
          previousStatus: "notDetermined"
        ) { [weak self] _ in
          MainActor.assumeIsolated { self?.checkNotificationPermission() }
        }
      } else if authorizationStatus == .denied {
        // Previously denied - open System Settings so user can enable manually
        self.openNotificationPreferences()
      }
      // If already authorized, checkNotificationPermission() will handle it
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
        MainActor.assumeIsolated { self?.checkNotificationPermission() }
      }
    }

    // Wait for repair + re-authorization, then check if it worked
    DispatchQueue.main.asyncAfter(deadline: .now() + 4.0) { [weak self] in
      UserNotificationCallbackBridge.notificationSettings { [weak self] settings in
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

  // MARK: - Permission Status Checks

  /// Permissions this refresh reads synchronously. Notification authorisation is deliberately
  /// absent: it resolves through a completion handler, so it is never settled by the time the
  /// refresh returns and would read as a grant arriving on the following refresh instead.
  private var grantedPermissionCount: Int {
    [
      hasScreenRecordingPermission, hasMicrophonePermission, hasSystemAudioPermission,
      hasAutomationPermission, hasAccessibilityPermission, hasFullDiskAccess,
    ].filter { $0 }.count
  }

  /// Sounds a permission actually landing — the user left for System Settings, granted something,
  /// and came back, which is what drives this refresh.
  ///
  /// The first refresh only records a baseline. At launch every flag is still at its `false`
  /// default, so the jump to the machine's real state is a read rather than a grant, and chiming at
  /// it would mean chiming on every cold start.
  private func notePermissionGrants() {
    let granted = grantedPermissionCount
    defer { lastGrantedPermissionCount = granted }
    guard let previous = lastGrantedPermissionCount, granted > previous else { return }
    OmiUISound.play(.complete)
  }

  /// Check and update all permission states
  func checkAllPermissions() {
    defer { notePermissionGrants() }
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
    // This is observational only. Repairing LaunchServices or opening Settings
    // belongs to the explicit notification Fix/request actions above.
    // Dispatch async to avoid calling UNUserNotificationCenter.current() during
    // SwiftUI view body evaluation, which triggers an assertion in UserNotifications.
    DispatchQueue.main.async { [weak self] in
      guard let self else { return }
      UserNotificationCallbackBridge.notificationSettings { settings in
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

          // Update last known state
          self.lastNotificationAuthStatus = authStatus
          self.lastNotificationAlertStyle = alertStyleName
          self.lastNotificationSoundEnabled = soundEnabled
          self.lastNotificationBadgeEnabled = badgeEnabled
        }
      }
    }  // end DispatchQueue.main.async
  }

  /// Screen recording was granted while this process was running, so capture
  /// stays dead until the app relaunches. Drives the "Reopen Omi" offer.
  var screenRecordingNeedsRelaunch: Bool {
    ScreenRecordingPermissionPolicy.needsRelaunchToApply(
      grantedNow: hasScreenRecordingPermission,
      grantedAtLaunch: screenRecordingGrantedAtLaunch)
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
  ///
  /// Fire-and-forget: the result lands one turn later. Anything that reads
  /// `hasAutomationPermission` on the next line must `await
  /// refreshAutomationPermission()` instead — see its doc comment.
  func checkAutomationPermission() {
    guard !isCheckingAutomationPermission else { return }
    isCheckingAutomationPermission = true
    Task { [weak self] in
      guard let self else { return }
      await self.refreshAutomationPermission()
      self.isCheckingAutomationPermission = false
    }
  }

  /// Await-able automation status refresh — the only correct probe for a caller
  /// that acts on the answer.
  ///
  /// `checkAutomationPermission()` returns before its probe has run, and with
  /// `-600` (System Events stopped) deliberately *preserving* the previous
  /// value, a caller reading the flag immediately afterwards observed the state
  /// from the probe before last. During onboarding that reads as "we asked
  /// macOS and it said no": an Automation permission the user had already
  /// granted was not detected, and they were asked for it again.
  ///
  /// The query itself is a cross-process Apple Event permission lookup, so it
  /// runs off the main actor and only the state write comes back.
  @discardableResult
  func refreshAutomationPermission(
    query: @escaping @Sendable () -> OSStatus = { AppState.queryAutomationPermissionStatus() }
  ) async -> Bool {
    let previousValue = hasAutomationPermission
    let status = await Task.detached(priority: .userInitiated) { query() }.value
    return applyAutomationPermissionStatus(status, previousPermission: previousValue)
  }

  /// Project one observed `OSStatus` onto the shared automation permission
  /// state. Separated from the probe so a request path that already *has* the
  /// answer (the TCC prompt returns it) adopts it directly instead of racing a
  /// second lookup against it.
  ///
  /// noErr (0) = granted, errAEEventNotPermitted (-1743) = denied,
  /// -1744 = not determined, -600 = target not running.
  @discardableResult
  func applyAutomationPermissionStatus(
    _ status: OSStatus,
    previousPermission: Bool? = nil
  ) -> Bool {
    let previousValue = previousPermission ?? hasAutomationPermission
    let projection = Self.automationPermissionProjection(
      status: status,
      previousPermission: previousValue
    )
    if status == -600 {
      log(
        "AUTOMATION_CHECK: status=-600 (procNotFound); preserving last known grant and leaving System Events stopped")
    } else if projection.hasPermission != previousValue {
      log("AUTOMATION_CHECK: status=\(status), hasPermission=\(projection.hasPermission)")
    }
    // Assign only on change — see `applyAccessibilitySignals`.
    if hasAutomationPermission != projection.hasPermission {
      hasAutomationPermission = projection.hasPermission
    }
    if automationPermissionError != projection.error {
      automationPermissionError = projection.error
    }
    return projection.hasPermission
  }

  nonisolated static func automationPermissionProjection(
    status: OSStatus,
    previousPermission: Bool
  ) -> (hasPermission: Bool, error: OSStatus) {
    if status == -600 {
      return (previousPermission, status)
    }
    let hasPermission = status == noErr
    let error = (status == noErr || status == -1743 || status == -1744) ? 0 : status
    return (hasPermission, error)
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
    applyAccessibilitySignals(Self.probeAccessibilitySignals(targets: accessibilityProbeTargets()))
  }

  /// Off-main accessibility refresh, for callers that probe repeatedly.
  ///
  /// The probe is three cross-process round trips —
  /// `AXUIElementCopyAttributeValue` against the frontmost app, a second one
  /// against Finder to disambiguate `cannotComplete`, and `CGEvent.tapCreate`.
  /// Onboarding runs this every 500ms for 20s while a permission step is
  /// visible, which on the main actor is a hitch budget the window cannot pay.
  /// Only the cheap AppKit lookups stay on the main actor; the round trips move
  /// off it and just the projection comes back.
  @discardableResult
  func refreshAccessibilityPermission(
    probe: (@Sendable () -> AccessibilityProbeSignals)? = nil
  ) async -> Bool {
    let targets = accessibilityProbeTargets()
    let resolved = probe ?? { Self.probeAccessibilitySignals(targets: targets) }
    let signals = await Task.detached(priority: .userInitiated) { resolved() }.value
    applyAccessibilitySignals(signals)
    return hasAccessibilityPermission
  }

  /// AppKit lookups the probe needs. Cheap, cached by AppKit, and main-actor
  /// bound — so they are read here and handed to the probe as plain values.
  func accessibilityProbeTargets() -> AccessibilityProbeTargets {
    let frontmost = NSWorkspace.shared.frontmostApplication
    let finder = NSRunningApplication.runningApplications(
      withBundleIdentifier: "com.apple.finder"
    ).first
    return AccessibilityProbeTargets(
      frontmostProcessID: frontmost?.processIdentifier,
      frontmostName: frontmost?.localizedName ?? "unknown",
      finderProcessID: finder?.processIdentifier)
  }

  /// The whole accessibility decision as a pure function of what the probes
  /// observed. `AXIsProcessTrusted()` can be stale after a macOS update or an
  /// app re-sign, so an event tap that succeeds is treated as authoritative
  /// evidence of the grant; a real AX call failing on top of either is what
  /// "broken" means.
  nonisolated static func accessibilityProjection(
    _ signals: AccessibilityProbeSignals
  ) -> (hasPermission: Bool, isBroken: Bool) {
    if signals.tccTrusted { return (true, !signals.axCallsWork) }
    if signals.eventTapWorks { return (true, !signals.axCallsWork) }
    // Event tap also failed — permission genuinely not granted.
    return (false, false)
  }

  /// Gather the accessibility signals. Safe off the main actor: every call here
  /// is a C API on `ApplicationServices`, not AppKit.
  nonisolated static func probeAccessibilitySignals(
    targets: AccessibilityProbeTargets
  ) -> AccessibilityProbeSignals {
    let tccTrusted = AXIsProcessTrusted()
    if tccTrusted {
      return AccessibilityProbeSignals(
        tccTrusted: true,
        eventTapWorks: true,
        axCallsWork: axCallsWork(targets: targets))
    }
    guard probeAccessibilityViaEventTap() else {
      return AccessibilityProbeSignals(tccTrusted: false, eventTapWorks: false, axCallsWork: false)
    }
    return AccessibilityProbeSignals(
      tccTrusted: false,
      eventTapWorks: true,
      axCallsWork: axCallsWork(targets: targets))
  }

  private func applyAccessibilitySignals(_ signals: AccessibilityProbeSignals) {
    let previouslyGranted = hasAccessibilityPermission
    let projection = Self.accessibilityProjection(signals)

    if projection.hasPermission, !previouslyGranted {
      let bundleId = Bundle.main.bundleIdentifier ?? "unknown"
      let route = signals.tccTrusted ? "TCC" : "event tap probe (stale AXIsProcessTrusted)"
      log("ACCESSIBILITY_CHECK: Permission granted via \(route) (bundleId=\(bundleId))")
    } else if !projection.hasPermission, previouslyGranted {
      let bundleId = Bundle.main.bundleIdentifier ?? "unknown"
      log("ACCESSIBILITY_CHECK: Permission revoked (bundleId=\(bundleId))")
    }
    if projection.isBroken != isAccessibilityBroken {
      log(
        projection.isBroken
          ? "ACCESSIBILITY_CHECK: TCC/event tap say granted but AX calls fail — stuck/broken state detected"
          : "ACCESSIBILITY_CHECK: AX calls working normally")
    }

    // Assign only on change: a permission step re-probes twice a second, and an
    // idempotent write to an @Published still redraws every observer.
    if hasAccessibilityPermission != projection.hasPermission {
      hasAccessibilityPermission = projection.hasPermission
    }
    if isAccessibilityBroken != projection.isBroken {
      isAccessibilityBroken = projection.isBroken
    }
  }

  /// Check Full Disk Access by probing FDA-protected paths.
  /// The TCC database query is unreliable on macOS 15+ (schema changes, ad-hoc signing),
  /// so we probe actual protected directories instead.
  func checkFullDiskAccess() {
    applyFullDiskAccess(Self.probeFullDiskAccessGranted())
  }

  /// Off-main Full Disk Access refresh. `contentsOfDirectory` on a
  /// TCC-protected directory is a synchronous tccd round trip; a poll that runs
  /// it on the main actor twice a second stalls the window it is polling for.
  @discardableResult
  func refreshFullDiskAccess(
    probe: @escaping @Sendable () -> Bool = { AppState.probeFullDiskAccessGranted() }
  ) async -> Bool {
    let granted = await Task.detached(priority: .userInitiated) { probe() }.value
    applyFullDiskAccess(granted)
    return granted
  }

  /// These paths are protected by Full Disk Access on all macOS versions.
  /// Listing one successfully is the grant. Pure and thread-safe.
  nonisolated static func probeFullDiskAccessGranted() -> Bool {
    let home = FileManager.default.homeDirectoryForCurrentUser.path
    let protectedPaths = [
      "\(home)/Library/Safari",
      "\(home)/Library/Mail",
      "\(home)/Library/Messages",
    ]

    for path in protectedPaths where FileManager.default.fileExists(atPath: path) {
      return (try? FileManager.default.contentsOfDirectory(atPath: path)) != nil
    }
    return false
  }

  private func applyFullDiskAccess(_ granted: Bool) {
    if granted != hasFullDiskAccess {
      hasFullDiskAccess = granted
      log("Full Disk Access: \(granted ? "granted" : "not granted") (file probe)")
    }
  }

  /// Test if Accessibility API actually works by attempting a real AX call.
  /// Returns true if AX calls succeed, false if permission is stuck/broken.
  nonisolated static func axCallsWork(targets: AccessibilityProbeTargets) -> Bool {
    guard let frontPID = targets.frontmostProcessID else {
      // No frontmost app to test against — can't determine, assume OK
      return true
    }

    let appElement = AXUIElementCreateApplication(frontPID)
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
        "ACCESSIBILITY_CHECK: AXError.apiDisabled — permission stuck (tested against pid \(frontPID), app: \(targets.frontmostName))"
      )
      return false
    case .cannotComplete:
      // cannotComplete is ambiguous: it can mean our permission is broken, OR that the
      // frontmost app doesn't implement AX (e.g. Qt, OpenGL, Python-based apps like PyMOL).
      // Confirm against Finder before concluding the permission is truly broken.
      return confirmAccessibilityBrokenViaFinder(targets: targets)
    default:
      log(
        "ACCESSIBILITY_CHECK: AXError code \(result.rawValue) from app \(targets.frontmostName) — not permission-related, treating as OK"
      )
      return true
    }
  }

  /// Secondary AX check against Finder to disambiguate cannotComplete errors.
  /// If Finder (a known AX-compliant app) also fails, the permission is truly broken.
  /// If Finder succeeds, the original failure was app-specific, not a permission issue.
  nonisolated static func confirmAccessibilityBrokenViaFinder(
    targets: AccessibilityProbeTargets
  ) -> Bool {
    let suspectApp = targets.frontmostName
    if let finderPID = targets.finderProcessID {
      let finderElement = AXUIElementCreateApplication(finderPID)
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
  nonisolated static func probeAccessibilityViaEventTap() -> Bool {
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

    let options =
      ["AXTrustedCheckOptionPrompt": true] as CFDictionary
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
