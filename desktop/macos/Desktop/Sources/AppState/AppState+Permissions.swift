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
  /// Processes worth asking, frontmost first — never this process.
  ///
  /// Self is excluded because a process can always read its own accessibility tree without the
  /// permission. Probing the frontmost app therefore answered "AX works" whenever Omi itself was
  /// frontmost, which is exactly when someone is looking at the Permissions page.
  var candidates: [AccessibilityProbeCandidate]
  var frontmostName: String
  var finderProcessID: pid_t?
}

struct AccessibilityProbeCandidate: Sendable, Equatable {
  var processID: pid_t
  var name: String
}

/// What a real AX call was able to establish.
///
/// Tri-state on purpose. The old probe collapsed "this app cannot answer" into "accessibility
/// works", so `notImplemented`, `attributeUnsupported`, an unknown error, and a missing frontmost
/// process all read as a healthy permission. A probe that cannot tell must not move the verdict.
enum AccessibilityAXProbeResult: String, Sendable, Equatable {
  /// A foreign application's accessibility tree answered. Only this proves the grant.
  case working
  /// Accessibility was definitively refused — `apiDisabled`, or Finder failing too.
  case failing
  /// Nothing could answer. Says nothing either way.
  case indeterminate
}

/// What the accessibility probes observed. Kept separate from the decision so
/// the decision is a pure function that can be exercised for every combination
/// without a live TCC database.
struct AccessibilityProbeSignals: Sendable, Equatable {
  /// `AXIsProcessTrusted()` — authoritative when true, stale-able when false.
  var tccTrusted: Bool
  /// What a real `AXUIElementCopyAttributeValue` against another app established.
  var axProbe: AccessibilityAXProbeResult
}

enum NotificationPermissionEnableAction: Equatable {
  case refresh
  case requestSystemPrompt
  case openSystemSettings
}

enum NotificationPermissionPolicy {
  static func enableAction(for status: UNAuthorizationStatus) -> NotificationPermissionEnableAction {
    switch status {
    case .notDetermined: .requestSystemPrompt
    case .denied: .openSystemSettings
    case .authorized, .provisional: .refresh
    @unknown default: .openSystemSettings
    }
  }

  static func isGranted(_ status: UNAuthorizationStatus) -> Bool {
    switch status {
    case .authorized, .provisional: true
    case .notDetermined, .denied: false
    @unknown default: false
    }
  }

  static func hasVisibleAlertSurface(
    status: UNAuthorizationStatus,
    alertStyle: UNAlertStyle
  ) -> Bool {
    isGranted(status) && alertStyle != .none
  }
}

@MainActor
extension AppState {
  func openScreenRecordingPreferences() {
    ScreenCaptureService.openScreenRecordingPreferences()
  }

  func openAutomationPreferences() {
    ShellSummon.suspendForPermissionPrompt()
    if let url = URL(
      string: "x-apple.systempreferences:com.apple.preference.security?Privacy_Automation")
    {
      NSWorkspace.shared.open(url)
    }
  }

  func requestNotificationPermission() {
    UserNotificationCallbackBridge.authorizationStatus { [weak self] authorizationStatus in
      guard let self else { return }
      self.notificationAuthorizationStatus = authorizationStatus

      switch NotificationPermissionPolicy.enableAction(for: authorizationStatus) {
      case .refresh:
        self.checkNotificationPermission()
      case .openSystemSettings:
        self.openNotificationPreferences()
      case .requestSystemPrompt:
        NSApp.activate()
        UserNotificationCallbackBridge.requestAuthorization { [weak self] result in
          guard let self else { return }
          if let errorDescription = result.errorDescription {
            log(
              "Notification permission request failed; opening System Settings: \(errorDescription)"
            )
            self.openNotificationPreferences()
          }
          self.refreshNotificationPermissionAfterSystemSettings()
        }
      }
    }
  }

  /// Compatibility entry point for older settings surfaces. A normal permission click must never
  /// unregister the app or restart usernoted/NotificationCenter: those operations close system UI,
  /// invalidate in-flight authorization callbacks, and make the toggle appear stuck.
  func repairNotificationAndFallback() {
    log("Notification permission action requested from Settings")
    requestNotificationPermission()
  }

  // MARK: - Permission Status Checks

  /// The two permissions this refresh reads directly out of TCC, on every call, in every build.
  ///
  /// Everything else is excluded because it cannot tell a grant from a late read. Notification
  /// authorisation resolves through a completion handler; system audio is only marked granted once
  /// capture happens to be running; and automation, accessibility and full-disk access are skipped
  /// entirely under `usesLazyDevPermissions`, so their flags settle on some later path. Each of
  /// those would surface as a permission "arriving" one refresh after the fact.
  private var grantedPermissionCount: Int {
    [hasScreenRecordingPermission, hasMicrophonePermission].filter { $0 }.count
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
  /// Open Full Disk Access preferences in System Settings
  func openFullDiskAccessPreferences() {
    if let url = URL(
      string: "x-apple.systempreferences:com.apple.preference.security?Privacy_AllFiles")
    {
      NSWorkspace.shared.open(url)
    }
  }

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
    notificationPermissionRefreshGeneration &+= 1
    let generation = notificationPermissionRefreshGeneration
    DispatchQueue.main.async { [weak self] in
      guard let self else { return }
      UserNotificationCallbackBridge.notificationSettings { settings in
        guard generation == self.notificationPermissionRefreshGeneration else { return }
        let isNowGranted = NotificationPermissionPolicy.isGranted(settings.authorizationStatus)
        self.notificationAuthorizationStatus = settings.authorizationStatus
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

  /// Notification settings may take a short moment to propagate after System Settings changes.
  /// Re-read a bounded number of times and let the generation fence discard stale callbacks.
  func refreshNotificationPermissionAfterSystemSettings() {
    for delay in [0.0, 0.25, 0.75, 1.5] {
      DispatchQueue.main.asyncAfter(deadline: .now() + delay) { [weak self] in
        self?.checkNotificationPermission()
      }
    }
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
    let status = await Task.detached(priority: .userInitiated) { query() }.value
    // Read the grant only after the detached probe returns. A user can grant
    // Automation while the probe is in flight; preserving the value captured
    // before the await would overwrite that newer main-actor state when the
    // result is -600 (System Events was not running).
    return applyAutomationPermissionStatus(status)
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
    // AXUIElement/CGEvent calls can synchronously cross the WindowServer. Keep
    // the fire-and-forget API non-blocking for legacy callers; callers that
    // need the answer must await `refreshAccessibilityPermission()`.
    Task { [weak self] in
      _ = await self?.refreshAccessibilityPermission()
    }
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
    let signals = await Task.detached(priority: .userInitiated) {
      let resolved =
        probe ?? {
          Self.probeAccessibilitySignals(targets: Self.accessibilityProbeTargets())
        }
      return resolved()
    }.value
    applyAccessibilitySignals(signals)
    return hasAccessibilityPermission
  }

  /// AppKit lookups the probe needs. Cheap, cached by AppKit, and main-actor
  /// bound — so they are read here and handed to the probe as plain values.
  nonisolated static func accessibilityProbeTargets() -> AccessibilityProbeTargets {
    let ownPID = ProcessInfo.processInfo.processIdentifier
    let frontmost = NSWorkspace.shared.frontmostApplication
    let finder = NSRunningApplication.runningApplications(
      withBundleIdentifier: "com.apple.finder"
    ).first

    // Frontmost first — it is the app most likely to have a focused window to report — then any
    // other ordinary app, because a single candidate that happens not to implement AX would
    // otherwise leave the probe unable to answer.
    var apps: [NSRunningApplication] = []
    if let frontmost { apps.append(frontmost) }
    apps.append(
      contentsOf: NSWorkspace.shared.runningApplications.filter {
        $0.activationPolicy == .regular && $0.processIdentifier != frontmost?.processIdentifier
      })

    let candidates =
      apps
      .filter { $0.processIdentifier != ownPID }
      .prefix(accessibilityProbeCandidateLimit)
      .map {
        AccessibilityProbeCandidate(
          processID: $0.processIdentifier, name: $0.localizedName ?? "unknown")
      }

    return AccessibilityProbeTargets(
      candidates: Array(candidates),
      frontmostName: frontmost?.localizedName ?? "unknown",
      finderProcessID: finder?.processIdentifier)
  }

  /// Enough candidates to get past a couple of apps that do not implement AX, few enough that a
  /// routine permission poll stays a handful of cross-process calls.
  nonisolated static let accessibilityProbeCandidateLimit = 4

  /// The whole accessibility decision as a pure function of what the probes observed.
  ///
  /// Only two things can establish the grant: `AXIsProcessTrusted()`, or a real accessibility
  /// call succeeding against another application. `AXIsProcessTrusted()` can be stale after a
  /// macOS update or an app re-sign, which is why the second route exists — a working AX call is
  /// proof regardless of what TCC reports.
  ///
  /// A `CGEvent` tap deliberately does *not* appear here. It used to, as a "live TCC read", but
  /// a listen-only session tap is satisfied by **Input Monitoring**, a different permission
  /// entirely. On a machine with Input Monitoring granted and Accessibility switched off, that
  /// rule reported the permission as granted while the System Settings toggle was visibly off.
  ///
  /// "Broken" is the narrow case worth naming: something says the grant exists while real AX
  /// calls are definitively refused — a stale entry left behind by a re-sign, where the toggle
  /// reads enabled and nothing works. An *indeterminate* probe is not broken and not granted; it
  /// leaves the TCC answer standing.
  nonisolated static func accessibilityProjection(
    _ signals: AccessibilityProbeSignals
  ) -> (hasPermission: Bool, isBroken: Bool) {
    switch (signals.tccTrusted, signals.axProbe) {
    case (true, .failing):
      return (true, true)
    case (true, _):
      return (true, false)
    case (false, .working):
      return (true, false)
    case (false, _):
      return (false, false)
    }
  }

  /// Gather the accessibility signals. Safe off the main actor: every call here
  /// is a C API on `ApplicationServices`, not AppKit.
  nonisolated static func probeAccessibilitySignals(
    targets: AccessibilityProbeTargets
  ) -> AccessibilityProbeSignals {
    AccessibilityProbeSignals(
      tccTrusted: AXIsProcessTrusted(),
      axProbe: axProbeResult(targets: targets))
  }

  private func applyAccessibilitySignals(_ signals: AccessibilityProbeSignals) {
    let previouslyGranted = hasAccessibilityPermission
    let previouslyBroken = isAccessibilityBroken
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

    // The capture service latches AX off after one `apiDisabled`, to keep a broken call from
    // running once a second. That latch outlives the breakage, so clear it on the edge into a
    // working grant — otherwise the user grants the permission, sees the row turn green, and
    // still gets window titles instead of URLs until the next launch.
    let nowWorking = projection.hasPermission && !projection.isBroken
    let wasWorking = previouslyGranted && !previouslyBroken
    if nowWorking, !wasWorking {
      ScreenCaptureService.rearmAccessibilityAfterPermissionChange()
    }
  }

  /// Probe the permissions the Settings page shows, regardless of `usesLazyDevPermissions`.
  ///
  /// `checkAllPermissions()` skips accessibility, automation, and full-disk access on named dev
  /// bundles, which is the right trade at *startup* — those probes are slow and can prompt. It is
  /// the wrong trade on the page whose entire job is to report those permissions: the row would
  /// read "Not Granted" forever on a dev build, including right after the user granted it.
  func refreshPermissionsForSettingsPage() {
    checkAllPermissions()
    guard AppBuild.usesLazyDevPermissions else { return }
    checkAccessibilityPermission()
  }

  /// Watch the system's own accessibility-database signal.
  ///
  /// macOS posts `com.apple.accessibility.api` when the AX permission set changes. Without it the
  /// state only refreshes when the app is activated, so a user who grants the permission and stays
  /// in System Settings sees nothing move.
  func startAccessibilityChangeObserver() {
    guard accessibilityChangeObserver == nil else { return }
    accessibilityChangeObserver = DistributedNotificationCenter.default().addObserver(
      forName: NSNotification.Name("com.apple.accessibility.api"),
      object: nil,
      queue: .main
    ) { [weak self] _ in
      Task { @MainActor [weak self] in
        guard let self else { return }
        log("ACCESSIBILITY_CHECK: system reported an accessibility-permission change")
        _ = await self.refreshAccessibilityPermission()
      }
    }
  }

  /// Check Full Disk Access by probing FDA-protected paths.
  /// The TCC database query is unreliable on macOS 15+ (schema changes, ad-hoc signing),
  /// so we probe actual protected directories instead.
  func checkFullDiskAccess() {
    // The file-system probe can synchronously cross tccd. Keep this API
    // compatible for passive callers without making their actor pay that
    // round-trip; callers that need the answer must await the refresh below.
    Task { [weak self] in
      _ = await self?.refreshFullDiskAccess()
    }
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
  /// Ask other applications whether accessibility actually works.
  ///
  /// Returns `.working` on the first candidate that answers, `.failing` only on evidence that the
  /// permission itself is refused, and `.indeterminate` when no candidate could settle it. The
  /// candidate list never contains this process: a process can read its own accessibility tree
  /// without the permission, so probing self reports a grant that does not exist.
  nonisolated static func axProbeResult(targets: AccessibilityProbeTargets) -> AccessibilityAXProbeResult {
    guard !targets.candidates.isEmpty else { return .indeterminate }

    var sawCannotComplete = false
    for candidate in targets.candidates {
      switch focusedWindowError(pid: candidate.processID) {
      case .success, .noValue:
        // `noValue` means the app answered and has no focused window — the call itself worked.
        return .working
      case .apiDisabled:
        log(
          "ACCESSIBILITY_CHECK: AXError.apiDisabled — accessibility refused (tested against \(candidate.name))"
        )
        return .failing
      case .cannotComplete:
        // Ambiguous: a broken permission, or an app that does not implement AX (Qt, OpenGL,
        // Electron-in-some-states). Keep looking; Finder settles it below.
        sawCannotComplete = true
      default:
        // `notImplemented`, `attributeUnsupported`, anything else: this app cannot answer the
        // question. It is not evidence either way, so try the next one.
        continue
      }
    }

    guard sawCannotComplete else { return .indeterminate }
    return confirmAccessibilityBrokenViaFinder(targets: targets) ? .indeterminate : .failing
  }

  nonisolated static func focusedWindowError(pid: pid_t) -> AXError {
    let appElement = AXUIElementCreateApplication(pid)
    var focusedWindow: CFTypeRef?
    return AXUIElementCopyAttributeValue(
      appElement, kAXFocusedWindowAttribute as CFString, &focusedWindow)
  }

  /// Secondary AX check against Finder to disambiguate `cannotComplete`.
  ///
  /// Finder is a known AX-compliant app, so if it fails too the permission is the problem.
  /// Returns whether accessibility looks fine.
  nonisolated static func confirmAccessibilityBrokenViaFinder(
    targets: AccessibilityProbeTargets
  ) -> Bool {
    guard let finderPID = targets.finderProcessID else {
      // Finder not running. The old code fell back to the event tap here, which measures Input
      // Monitoring rather than accessibility — the same conflation that produced a false grant.
      // Unknown is the honest answer.
      log("ACCESSIBILITY_CHECK: AXError.cannotComplete and Finder not running — cannot determine")
      return true
    }
    switch focusedWindowError(pid: finderPID) {
    case .cannotComplete, .apiDisabled:
      log("ACCESSIBILITY_CHECK: cannotComplete confirmed by Finder — permission is truly stuck")
      return false
    default:
      log("ACCESSIBILITY_CHECK: cannotComplete but Finder OK — app-specific AX gap, permission is fine")
      return true
    }
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
