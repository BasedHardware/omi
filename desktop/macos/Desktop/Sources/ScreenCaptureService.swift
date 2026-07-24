import AppKit
import CoreGraphics
import Foundation
import ImageIO
import ScreenCaptureKit

final class ScreenCaptureService: Sendable {
  private let maxSize: CGFloat = 3000
  private let jpegQuality: CGFloat = 0.8
  private static let activeWindowResolveTimeoutNs: UInt64 = 500_000_000  // 500ms
  private static let activeWindowCacheTTL: TimeInterval = 2

  /// Serializes all reads and writes to axFailureCountByBundleID and axSystemwideDisabled.
  /// Both vars are accessed from the MainActor (captureFrame start) AND the cooperative
  /// thread pool (captureActiveWindowCGImage runs non-isolated), so a lock is required.
  private static let axStateLock = NSLock()
  /// Tracks consecutive AX cannotComplete failures per bundle ID.
  /// Apps that consistently fail (Qt, OpenGL, etc.) are skipped for AX after the threshold.
  /// Must be accessed only while holding axStateLock.
  nonisolated(unsafe) private static var axFailureCountByBundleID: [String: Int] = [:]
  private static let axSkipThreshold = 3

  /// When the AX API is disabled system-wide (apiDisabled error), skip all AX attempts
  /// to avoid spamming a failing call on every capture cycle (every ~1 second).
  /// Must be accessed only while holding axStateLock.
  nonisolated(unsafe) private static var axSystemwideDisabled = false

  /// Cache the last successfully resolved active window (with a non-nil window ID).
  /// A frontmost helper, secure surface, or transient WindowServer lookup can resolve
  /// an app name without a capture target. That result must never replace a known-good
  /// target, or recording drops during the transition.
  internal struct ActiveWindowSnapshot: Equatable {
    let appName: String?
    let windowTitle: String?
    let windowID: CGWindowID?
    let resolvedAt: Date
  }
  nonisolated(unsafe) private static var lastActiveWindowSnapshot: ActiveWindowSnapshot?
  nonisolated(unsafe) private static var isActiveWindowResolutionInFlight = false
  /// Limits the transition fallback message to once per no-window streak.
  nonisolated(unsafe) private static var isInNilWindowFallbackStreak = false

  /// Test seam for deterministic resolver behavior without querying WindowServer.
  nonisolated(unsafe) internal static var _resolverOverrideForTests:
    (@Sendable () async -> (appName: String?, windowTitle: String?, windowID: CGWindowID?)?)?

  /// Cache for SCShareableContent to avoid hammering the WindowServer every capture tick.
  /// SCShareableContent.excludingDesktopWindows enumerates every on-screen window through
  /// the WindowServer; calling it every 3 seconds contends with other screen-capture apps
  /// (CleanShot, Zoom share, Loom, etc.) and causes UI stalls. Re-use a recent snapshot
  /// for up to `sharedContentTTL` seconds; refresh on demand when a target window isn't
  /// present in the cache.
  private static let sharedContentLock = NSLock()
  nonisolated(unsafe) private static var cachedSharedContent: Any?  // SCShareableContent, typed Any so this decl predates macOS 14 gate
  nonisolated(unsafe) private static var sharedContentCachedAt: Date?
  private static let sharedContentTTL: TimeInterval = 5.0

  @available(macOS 14.0, *)
  private static func sharedContent(forceRefresh: Bool = false) async throws -> SCShareableContent {
    if !forceRefresh,
      !UserDefaults.standard.bool(forKey: .rewindDisableContentCache)
    {
      let cached: SCShareableContent? = sharedContentLock.withLock {
        guard let ts = sharedContentCachedAt,
          Date().timeIntervalSince(ts) < sharedContentTTL,
          let content = cachedSharedContent as? SCShareableContent
        else { return nil }
        return content
      }
      if let cached { return cached }
    }

    let content = try await SCShareableContent.excludingDesktopWindows(
      false,
      onScreenWindowsOnly: true
    )
    sharedContentLock.withLock {
      cachedSharedContent = content
      sharedContentCachedAt = Date()
    }
    return content
  }

  init() {}

  /// Check whether macOS TCC says this app has Screen Recording permission.
  ///
  /// Do not spawn `/usr/sbin/screencapture` here. That helper process can fail
  /// for reasons unrelated to this app's TCC grant, which made Omi show a red
  /// "Screen Recording disabled" state while System Settings correctly showed
  /// the app as allowed.
  static func checkPermission(forceActualTestIfPreflightDenied: Bool = false) -> Bool {
    let preflightGranted = CGPreflightScreenCaptureAccess()

    if !preflightGranted {
      log("Screen capture: CGPreflight says no permission")

      if forceActualTestIfPreflightDenied {
        log("Screen capture: ignoring forced helper capture test; preflight is authoritative")
      }
      return false
    }

    return true
  }

  enum ScreenRecordingRequestDestination: Equatable {
    case alreadyGranted
    case systemSettings
  }

  static func screenRecordingRequestDestination(
    hasPermissionNow: Bool
  ) -> ScreenRecordingRequestDestination {
    hasPermissionNow ? .alreadyGranted : .systemSettings
  }

  /// Legacy synchronous permission probe. Keep this as a TCC preflight wrapper
  /// so callers cannot accidentally make the UI depend on a child CLI process.
  static func testCapturePermission() -> Bool {
    checkPermission()
  }

  /// Test whether ScreenCaptureKit can enumerate shareable content.
  /// Use this only for capture-engine diagnostics, not for the permission badge.
  @available(macOS 14.0, *)
  static func testCaptureCapability() async -> Bool {
    await testScreenCaptureKitPermission()
  }

  /// Open System Preferences to Screen Recording settings
  static func openScreenRecordingPreferences() {
    Task { await PermissionDragGuidance.presentDragToGrantHelper() }

    if let url = URL(
      string: "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture")
    {
      let opened = NSWorkspace.shared.open(url)
      if opened {
        log("Opened Screen Recording preferences via URL scheme")
        // Bring System Settings to front after a brief moment to ensure it's visible
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.3) {
          if let settingsApp = NSRunningApplication.runningApplications(
            withBundleIdentifier: "com.apple.systempreferences"
          ).first
            ?? NSRunningApplication.runningApplications(withBundleIdentifier: "com.apple.Preferences").first
          {
            settingsApp.activate()
          }
        }
      } else {
        log("Failed to open Screen Recording preferences via URL scheme — trying fallback")
        // Fallback: open System Settings directly
        NSWorkspace.shared.open(URL(string: "x-apple.systempreferences:")!)
      }
    }
  }

  /// Trigger ScreenCaptureKit consent dialog (macOS 14+)
  /// This is SEPARATE from CGRequestScreenCaptureAccess() - it triggers the
  /// ScreenCaptureKit-specific permission for capturing windows/displays.
  @available(macOS 14.0, *)
  static func requestScreenCaptureKitPermission() async -> Bool {
    do {
      // This call triggers the ScreenCaptureKit consent dialog if not already granted
      _ = try await SCShareableContent.excludingDesktopWindows(false, onScreenWindowsOnly: true)
      log("ScreenCaptureKit: Permission granted or already available")
      return true
    } catch {
      logError("ScreenCaptureKit: Permission request failed", error: error)
      return false
    }
  }

  /// Force re-register this app with Launch Services to ensure it's the authoritative version
  /// This fixes issues where multiple app bundles with the same bundle ID confuse macOS
  /// about which app to grant permissions to.
  /// Runs the process on a background thread to avoid blocking the main thread.
  static func ensureLaunchServicesRegistration() {
    guard let bundlePath = Bundle.main.bundlePath as String? else {
      log("Launch Services: Failed to get bundle path")
      return
    }

    log("Launch Services: Re-registering \(bundlePath)...")

    let lsregisterPath =
      "/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister"

    DispatchQueue.global(qos: .utility).async {
      runLsregister(path: lsregisterPath, bundlePath: bundlePath)
    }
  }

  /// Synchronous version — call from a background thread when CGRequestScreenCaptureAccess()
  /// must run after registration completes (e.g. permission trigger flow).
  static func ensureLaunchServicesRegistrationSync() {
    guard let bundlePath = Bundle.main.bundlePath as String? else {
      log("Launch Services: Failed to get bundle path")
      return
    }

    log("Launch Services: Re-registering (sync) \(bundlePath)...")

    let lsregisterPath =
      "/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister"
    runLsregister(path: lsregisterPath, bundlePath: bundlePath)
  }

  private static func runLsregister(path: String, bundlePath: String) {
    let process = Process()
    process.executableURL = URL(fileURLWithPath: path)
    // -f = force registration even if already registered
    // This makes this specific app bundle authoritative
    process.arguments = ["-f", bundlePath]
    process.standardOutput = FileHandle.nullDevice
    process.standardError = FileHandle.nullDevice

    do {
      try process.run()
      process.waitUntilExit()
      log("Launch Services: Registration completed (exit code: \(process.terminationStatus))")
    } catch {
      logError("Launch Services: Failed to register", error: error)
    }
  }

  /// Request all screen capture permissions (both traditional TCC and ScreenCaptureKit)
  @MainActor
  static func requestAllScreenCapturePermissions() {
    // 0. Ensure this app is the authoritative version in Launch Services
    // This fixes issues where stale registrations from old builds, DMGs, or Trash
    // cause macOS to grant permissions to the wrong app
    ensureLaunchServicesRegistration()

    // 1. Request traditional Screen Recording TCC permission.
    // Activate first so the request fires while Omi is frontmost. A
    // screen-capture access request from a backgrounded app does not reliably
    // register the kTCCServiceScreenCapture row, so the app never appears in the
    // Screen Recording list (PERM-02). This mirrors requestMicrophonePermission,
    // which activates before requesting and reliably creates its TCC row.
    NSApp.activate()
    CGRequestScreenCaptureAccess()

    // 2. Request ScreenCaptureKit permission (macOS 14+)
    if #available(macOS 14.0, *) {
      Task {
        _ = await requestScreenCaptureKitPermission()
      }
    }

    if !CGPreflightScreenCaptureAccess() {
      Task { await PermissionDragGuidance.presentDragToGrantHelper() }
    }

    // Note: callers are responsible for opening System Settings
    // (removed duplicate open that conflicted with caller's own open call)
  }

  /// Structured variant for owner-bound tool execution. It keeps the
  /// ScreenCaptureKit request attached to the permission request lifetime so
  /// the caller can fence every state or Settings publication after the await.
  @MainActor
  static func requestAllScreenCapturePermissionsAwaitingScreenCaptureKit() async -> Bool {
    ensureLaunchServicesRegistration()
    NSApp.activate()
    let tccGranted = CGRequestScreenCaptureAccess()
    if #available(macOS 14.0, *) {
      _ = await requestScreenCaptureKitPermission()
    }
    return tccGranted || checkPermission()
  }

  /// Guided grant flow (PERM-02 / BL-050): register the screen-recording TCC row
  /// **while Omi is frontmost**, then open System Settings so the user lands on a
  /// list that already contains Omi. Opening Settings first backgrounded the app
  /// before the registering call, so a screen-capture request from the
  /// backgrounded app never created the `kTCCServiceScreenCapture` row and Omi
  /// never appeared in the list. Mirrors MemoryExportExecutor.requestScreenRecordingApprovalForCloudSetup, the existing register-while-frontmost path.
  @MainActor
  static func requestScreenRecordingAccessAndOpenSettings() {
    switch screenRecordingRequestDestination(hasPermissionNow: checkPermission()) {
    case .alreadyGranted:
      NSApp.activate()
    case .systemSettings:
      requestAllScreenCapturePermissions()
      openScreenRecordingPreferences()
    }
  }

  /// Perform one throwaway ScreenCaptureKit *capture* so macOS surfaces the
  /// "…is requesting to bypass the system private window picker and directly
  /// access your screen and audio" consent NOW, in-context on the permissions
  /// step, instead of the first time a real capture runs (e.g. the onboarding
  /// voice/screen demo, which is where users hit it).
  ///
  /// Enumerating shareable content (`SCShareableContent`) does NOT trigger this
  /// consent — only an actual `SCScreenshotManager.captureImage` with an
  /// app-built `SCContentFilter` does. So we do a minimal 2×2 display capture.
  /// Best-effort: requires Screen Recording TCC already granted, and on some
  /// macOS versions the consent recurs periodically regardless; errors are
  /// swallowed so this never blocks or disrupts onboarding.
  @available(macOS 14.0, *)
  static func primeCaptureConsent() async {
    do {
      let content = try await SCShareableContent.excludingDesktopWindows(false, onScreenWindowsOnly: true)
      guard let display = content.displays.first else { return }
      let filter = SCContentFilter(display: display, excludingWindows: [])
      let config = SCStreamConfiguration()
      config.width = 2
      config.height = 2
      _ = try await SCScreenshotManager.captureImage(contentFilter: filter, configuration: config)
      log("Primed ScreenCaptureKit capture consent")
    } catch {
      log("primeCaptureConsent skipped: \(error.localizedDescription)")
    }
  }

  /// Test if ScreenCaptureKit specifically works (macOS 14+)
  /// Returns true if ScreenCaptureKit consent is granted, false if declined
  @available(macOS 14.0, *)
  static func testScreenCaptureKitPermission() async -> Bool {
    do {
      _ = try await SCShareableContent.excludingDesktopWindows(false, onScreenWindowsOnly: true)
      return true
    } catch {
      log("ScreenCaptureKit test failed: \(error.localizedDescription)")
      return false
    }
  }

  /// Check if ScreenCaptureKit is in a broken state (TCC says yes, but SCK says no)
  /// This happens when the user declines the ScreenCaptureKit dialog or after rebuilds
  @available(macOS 14.0, *)
  static func isScreenCaptureKitBroken() async -> Bool {
    // If traditional TCC is granted but ScreenCaptureKit fails, it's broken
    let tccGranted = CGPreflightScreenCaptureAccess()
    if !tccGranted {
      return false  // Not broken, just not granted
    }

    let sckGranted = await testScreenCaptureKitPermission()
    return !sckGranted  // Broken if TCC yes but SCK no
  }

  /// Attempt soft recovery of screen capture permission without resetting TCC.
  /// Re-registers with Launch Services and re-requests ScreenCaptureKit consent.
  /// Returns true if capture works after recovery.
  static func attemptSoftRecovery() async -> Bool {
    log("Screen capture: Attempting soft recovery (lsregister + SCK re-request)...")

    // 1. Re-register with Launch Services synchronously so the OS maps our bundle ID
    //    to the current app binary (fixes stale registrations from old builds/updates)
    ensureLaunchServicesRegistrationSync()

    // 2. Re-request ScreenCaptureKit consent (macOS 14+)
    //    This can fix the "TCC says yes but SCK says no" broken state
    if #available(macOS 14.0, *) {
      let sckGranted = await requestScreenCaptureKitPermission()
      if sckGranted {
        log("Screen capture: Soft recovery succeeded (SCK re-consent granted)")
        return true
      }
      log("Screen capture: SCK re-request did not succeed, testing actual capture...")
    }

    // 3. If ScreenCaptureKit is unavailable, fall back to TCC preflight. The
    // permission indicator remains separate from capture-engine health.
    let granted = checkPermission()
    log("Screen capture: Soft recovery TCC preflight = \(granted ? "GRANTED" : "DENIED")")
    return granted
  }

  /// Reset screen capture permission using tccutil (nuclear option).
  /// This removes the TCC entry entirely — user must re-grant in System Settings.
  /// Only use as a last resort when soft recovery has already failed.
  static func resetScreenCapturePermission() -> Bool {
    let bundleId = Bundle.main.bundleIdentifier ?? "com.omi.computer-macos"
    log("Resetting screen capture permission for \(bundleId) via tccutil (hard reset)...")

    let process = Process()
    process.executableURL = URL(fileURLWithPath: "/usr/bin/tccutil")
    process.arguments = ["reset", "ScreenCapture", bundleId]

    do {
      try process.run()
      process.waitUntilExit()
      let success = process.terminationStatus == 0
      log("tccutil reset ScreenCapture completed with exit code: \(process.terminationStatus)")
      return success
    } catch {
      logError("Failed to run tccutil", error: error)
      return false
    }
  }

  /// Try soft recovery first, then restart the app.
  /// Does NOT reset TCC — preserves the user's existing permission grant.
  /// The restart refreshes the app's permission state with the OS.
  @MainActor
  static func softRecoveryAndRestart() {
    if UpdaterViewModel.isUpdateInProgress {
      log("Sparkle update in progress, skipping screen capture soft recovery restart")
      return
    }

    let bundleURL = Bundle.main.bundleURL

    Task.detached {
      // Re-register with Launch Services so the OS recognizes this binary
      ensureLaunchServicesRegistrationSync()

      // Re-request ScreenCaptureKit consent
      if #available(macOS 14.0, *) {
        _ = await requestScreenCaptureKitPermission()
      }

      await MainActor.run {
        AnalyticsManager.shared.screenCaptureResetCompleted(success: true)
        log("Screen capture: Soft recovery done, restarting app to refresh permission state...")

        let task = Process()
        task.executableURL = URL(fileURLWithPath: "/bin/sh")
        task.arguments = ["-c", screenCaptureRelaunchCommand(appPath: bundleURL.path)]

        do {
          try task.run()
          log("Restart scheduled, terminating current instance...")
          DispatchQueue.main.async {
            NSApplication.shared.terminate(nil)
          }
        } catch {
          logError("Failed to schedule restart", error: error)
        }
      }
    }
  }

  /// Hard reset: wipe TCC entry and restart. User must re-grant permission.
  /// Only use when soft recovery has already been tried and failed.
  @MainActor
  static func resetScreenCapturePermissionAndRestart() {
    if UpdaterViewModel.isUpdateInProgress {
      log(
        "Sparkle update in progress, skipping screen capture reset restart (Sparkle will handle relaunch)"
      )
      return
    }

    let bundleURL = Bundle.main.bundleURL

    // Run blocking Process calls on a background thread
    Task.detached {
      // First ensure this app is the authoritative version in Launch Services
      // This fixes issues where tccutil resets permission for a stale app registration
      ensureLaunchServicesRegistrationSync()

      let success = resetScreenCapturePermission()

      await MainActor.run {
        // Track reset completion
        AnalyticsManager.shared.screenCaptureResetCompleted(success: success)

        if success {
          log("Screen capture permission reset, restarting app...")

          let task = Process()
          task.executableURL = URL(fileURLWithPath: "/bin/sh")
          task.arguments = ["-c", screenCaptureRelaunchCommand(appPath: bundleURL.path)]

          do {
            try task.run()
            log("Restart scheduled, terminating current instance...")
            DispatchQueue.main.async {
              NSApplication.shared.terminate(nil)
            }
          } catch {
            logError("Failed to schedule restart", error: error)
          }
        } else {
          log("Screen capture permission reset failed")
        }
      }
    }
  }

  nonisolated static func screenCaptureRelaunchCommand(appPath: String) -> String {
    AppState.relaunchCommand(
      appPath: appPath,
      isNonProduction: AppBuild.isNonProduction,
      automationPort: DesktopAutomationLaunchOptions.port,
      terminatingProcessIdentifier: ProcessInfo.processInfo.processIdentifier
    )
  }

  /// Get the window ID of the frontmost application's main window
  private static func getActiveWindowID() -> CGWindowID? {
    let (_, _, windowID) = getActiveWindowInfo()
    return windowID
  }

  /// Resolve active window info asynchronously with timeout and cache fallback.
  /// This prevents rare SkyLight/CGWindowList stalls from blocking capture.
  static func getActiveWindowInfoAsync() async -> (
    appName: String?, windowTitle: String?, windowID: CGWindowID?
  ) {
    // Avoid stacking multiple slow window enumeration tasks if one is already in flight.
    let shouldStartNewResolution = axStateLock.withLock { () -> Bool in
      if isActiveWindowResolutionInFlight {
        return false
      }
      isActiveWindowResolutionInFlight = true
      return true
    }

    if !shouldStartNewResolution {
      if let cached = getCachedActiveWindowSnapshot() {
        return (cached.appName, cached.windowTitle, cached.windowID)
      }
      return (nil, nil, nil)
    }

    defer {
      axStateLock.withLock {
        isActiveWindowResolutionInFlight = false
      }
    }

    let resolved: (appName: String?, windowTitle: String?, windowID: CGWindowID?)?
    if let override = _resolverOverrideForTests {
      resolved = await override()
    } else {
      resolved = await resolveActiveWindowInfoWithTimeout()
    }

    // A nil window ID is a real resolver result, but not a captureable one. Do
    // not poison the last-known-good cache with it.
    if let resolved, resolved.windowID != nil {
      let snapshot = ActiveWindowSnapshot(
        appName: resolved.appName,
        windowTitle: resolved.windowTitle,
        windowID: resolved.windowID,
        resolvedAt: Date()
      )
      axStateLock.withLock {
        lastActiveWindowSnapshot = snapshot
        isInNilWindowFallbackStreak = false
      }
      return resolved
    }

    // The capture caller needs to see system-owned no-window targets so it can
    // pause instead of capturing the previous app from the cache.
    if let resolved, ScreenCaptureTargetPolicy.shouldWaitForUserWindow(appName: resolved.appName) {
      return resolved
    }

    // Preserve capture through a brief helper/system/secure-window transition.
    if let cached = getCachedActiveWindowSnapshot() {
      let shouldLog = axStateLock.withLock { () -> Bool in
        guard !isInNilWindowFallbackStreak else { return false }
        isInNilWindowFallbackStreak = true
        return true
      }
      if shouldLog {
        if resolved == nil {
          log("ScreenCaptureService: Active window lookup timed out, using cached window info")
        } else {
          log("ScreenCaptureService: Frontmost app has no captureable window; using last known good window")
        }
      }
      return (cached.appName, cached.windowTitle, cached.windowID)
    }

    // A no-window result is distinct from a timeout. Let the caller pause the
    // current tick rather than turning a normal secure/system surface into an
    // engine failure.
    if let resolved {
      return resolved
    }

    log("ScreenCaptureService: Active window lookup timed out with no cached fallback")
    return (nil, nil, nil)
  }

  // MARK: - Test-only helpers

  internal static func _resetActiveWindowCacheForTests() {
    axStateLock.withLock {
      lastActiveWindowSnapshot = nil
      isActiveWindowResolutionInFlight = false
      isInNilWindowFallbackStreak = false
    }
  }

  internal static func _seedActiveWindowCacheForTests(
    appName: String?,
    windowTitle: String?,
    windowID: CGWindowID?,
    resolvedAt: Date
  ) {
    axStateLock.withLock {
      lastActiveWindowSnapshot = ActiveWindowSnapshot(
        appName: appName,
        windowTitle: windowTitle,
        windowID: windowID,
        resolvedAt: resolvedAt
      )
    }
  }

  internal static func _peekActiveWindowCacheForTests() -> ActiveWindowSnapshot? {
    axStateLock.withLock { lastActiveWindowSnapshot }
  }

  private static func resolveActiveWindowInfoWithTimeout() async -> (
    appName: String?, windowTitle: String?, windowID: CGWindowID?
  )? {
    await withTaskGroup(of: (appName: String?, windowTitle: String?, windowID: CGWindowID?)?.self) { group in
      group.addTask(priority: .userInitiated) {
        let info = getActiveWindowInfo()
        if info.appName == nil && info.windowTitle == nil && info.windowID == nil {
          return nil
        }
        return info
      }

      group.addTask {
        try? await Task.sleep(nanoseconds: activeWindowResolveTimeoutNs)
        return nil
      }

      let firstCompleted = await group.next() ?? nil
      group.cancelAll()
      return firstCompleted
    }
  }

  private static func getCachedActiveWindowSnapshot() -> ActiveWindowSnapshot? {
    axStateLock.withLock {
      guard let snapshot = lastActiveWindowSnapshot else { return nil }
      guard Date().timeIntervalSince(snapshot.resolvedAt) <= activeWindowCacheTTL else { return nil }
      return snapshot
    }
  }

  /// Get the active app name, window title, and window ID
  static func getActiveWindowInfo() -> (
    appName: String?, windowTitle: String?, windowID: CGWindowID?
  ) {
    guard let frontApp = NSWorkspace.shared.frontmostApplication else {
      return (nil, nil, nil)
    }

    let appName = frontApp.localizedName
    let activePID = frontApp.processIdentifier
    let bundleID = frontApp.bundleIdentifier ?? ""

    // Get all on-screen windows
    guard
      let windowList = CGWindowListCopyWindowInfo(
        [.optionOnScreenOnly, .excludeDesktopElements], kCGNullWindowID) as? [[String: Any]]
    else {
      return (appName, nil, nil)
    }

    // Try Accessibility API first (most accurate - gets actual focused window).
    // Skip if AX is disabled system-wide (apiDisabled) or this app exceeded the cannotComplete threshold.
    let skipAX = axStateLock.withLock {
      axSystemwideDisabled
        || (!bundleID.isEmpty && (axFailureCountByBundleID[bundleID] ?? 0) >= axSkipThreshold)
    }
    if !skipAX,
      let axResult = getWindowInfoViaAccessibility(
        pid: activePID, bundleID: bundleID, windowList: windowList)
    {
      return (appName, axResult.title, axResult.windowID)
    }

    // Fallback to largest window heuristic
    var appWindows: [(title: String?, windowID: CGWindowID, area: CGFloat)] = []

    for window in windowList {
      guard let windowPID = window[kCGWindowOwnerPID as String] as? Int32,
        windowPID == activePID
      else {
        continue
      }

      if let bounds = window[kCGWindowBounds as String] as? [String: CGFloat],
        let width = bounds["Width"],
        let height = bounds["Height"],
        width > 100 && height > 100,
        let windowNumber = window[kCGWindowNumber as String] as? CGWindowID
      {
        let windowTitle = window[kCGWindowName as String] as? String
        appWindows.append((title: windowTitle, windowID: windowNumber, area: width * height))
      }
    }

    guard !appWindows.isEmpty else {
      return (appName, nil, nil)
    }

    // CGWindowListCopyWindowInfo returns windows in front-to-back z-order,
    // so the first element for a given PID is the frontmost on screen.
    // Among windows with the largest area, prefer the frontmost (first in the
    // array) so we capture the window the user is looking at instead of the
    // backmost equal-sized window (which is often the first one opened).
    // Fixes: https://github.com/BasedHardware/omi/issues/6552
    let maxArea = appWindows.map(\.area).max()!
    let frontmost = appWindows.first(where: { $0.area == maxArea })!

    return (appName, frontmost.title, frontmost.windowID)
  }

  /// Private API: get CGWindowID directly from an AXUIElement (avoids fragile position/size matching)
  @_silgen_name("_AXUIElementGetWindow")
  private static func _AXUIElementGetWindow(_ element: AXUIElement, _ windowID: UnsafeMutablePointer<CGWindowID>)
    -> AXError

  /// Get focused window info using Accessibility API, then match to CGWindowList for windowID
  private static func getWindowInfoViaAccessibility(
    pid: pid_t, bundleID: String, windowList: [[String: Any]]
  ) -> (title: String?, windowID: CGWindowID)? {
    let appElement = AXUIElementCreateApplication(pid)

    // Get the focused window
    var focusedWindow: CFTypeRef?
    let focusResult = AXUIElementCopyAttributeValue(
      appElement, kAXFocusedWindowAttribute as CFString, &focusedWindow)

    guard focusResult == .success, let windowElement = focusedWindow else {
      if focusResult == .apiDisabled {
        // System-wide AX permission issue. Set a flag so we stop attempting
        // AX on every capture cycle — avoids spinning on a known-broken call.
        let wasAlreadyDisabled = axStateLock.withLock {
          let prev = axSystemwideDisabled
          axSystemwideDisabled = true
          return prev
        }
        if !wasAlreadyDisabled {
          log(
            "ACCESSIBILITY_AX: apiDisabled (\(focusResult.rawValue)) — disabling AX attempts until next launch"
          )
        }
      } else if focusResult == .cannotComplete {
        // App-specific failure (Qt, OpenGL, Python-based apps often don't implement AX).
        // Track per bundle ID and suppress logs after the threshold to avoid spam.
        let count = axStateLock.withLock {
          let c = (axFailureCountByBundleID[bundleID] ?? 0) + 1
          axFailureCountByBundleID[bundleID] = c
          return c
        }
        if count == 1 {
          log(
            "ACCESSIBILITY_AX: cannotComplete for \(bundleID) (1st failure, will suppress after \(axSkipThreshold))"
          )
        } else if count == axSkipThreshold {
          log(
            "ACCESSIBILITY_AX: cannotComplete for \(bundleID) — \(axSkipThreshold) failures reached, skipping AX for this app going forward"
          )
        }
      }
      return nil
    }

    // On success, reset failure count in case the app's AX state recovered
    if !bundleID.isEmpty {
      axStateLock.withLock { axFailureCountByBundleID[bundleID] = 0 }
    }

    // Get window title from AX
    var titleValue: CFTypeRef?
    AXUIElementCopyAttributeValue(
      windowElement as! AXUIElement, kAXTitleAttribute as CFString, &titleValue)
    let axTitle = titleValue as? String

    // Try direct CGWindowID lookup first (handles multiple windows of same app correctly)
    var directWindowID: CGWindowID = 0
    let directResult = _AXUIElementGetWindow(windowElement as! AXUIElement, &directWindowID)
    if directResult == .success && directWindowID != 0 {
      // Verify the window ID exists in the on-screen window list
      let existsOnScreen = windowList.contains { window in
        (window[kCGWindowNumber as String] as? CGWindowID) == directWindowID
      }
      if existsOnScreen {
        return (title: axTitle, windowID: directWindowID)
      }
    }

    // Fallback: match by position/size (for apps where _AXUIElementGetWindow fails)
    var positionValue: CFTypeRef?
    let posResult = AXUIElementCopyAttributeValue(
      windowElement as! AXUIElement, kAXPositionAttribute as CFString, &positionValue)

    guard posResult == .success, let posRef = positionValue else {
      return nil
    }

    var position = CGPoint.zero
    if !AXValueGetValue(posRef as! AXValue, .cgPoint, &position) {
      return nil
    }

    var sizeValue: CFTypeRef?
    let sizeResult = AXUIElementCopyAttributeValue(
      windowElement as! AXUIElement, kAXSizeAttribute as CFString, &sizeValue)

    guard sizeResult == .success, let sizeRef = sizeValue else {
      return nil
    }

    var size = CGSize.zero
    if !AXValueGetValue(sizeRef as! AXValue, .cgSize, &size) {
      return nil
    }

    guard size.width > 100 && size.height > 100 else {
      return nil
    }

    for window in windowList {
      guard let windowPID = window[kCGWindowOwnerPID as String] as? Int32,
        windowPID == pid,
        let bounds = window[kCGWindowBounds as String] as? [String: CGFloat],
        let x = bounds["X"],
        let y = bounds["Y"],
        let width = bounds["Width"],
        let height = bounds["Height"],
        let windowNumber = window[kCGWindowNumber as String] as? CGWindowID
      else {
        continue
      }

      let tolerance: CGFloat = 2.0
      if abs(x - position.x) < tolerance && abs(y - position.y) < tolerance
        && abs(width - size.width) < tolerance && abs(height - size.height) < tolerance
      {
        let title = axTitle ?? (window[kCGWindowName as String] as? String)
        return (title: title, windowID: windowNumber)
      }
    }

    return nil
  }

  // MARK: - Async Capture (Primary API)

  /// Async capture - main entry point
  func captureActiveWindowAsync() async -> Data? {
    let (_, _, windowID) = await Self.getActiveWindowInfoAsync()
    guard let windowID else {
      log("No active window ID found")
      return nil
    }

    log("Capturing window ID: \(windowID)")

    if #available(macOS 14.0, *) {
      return await captureWithScreenCaptureKit(windowID: windowID)
    } else {
      // Fallback: run screencapture on background thread for macOS 13.x
      return await captureWithScreencaptureAsync(windowID: windowID)
    }
  }

  /// Capture dimensions that preserve the window's aspect ratio, or nil for a
  /// degenerate frame. `static` so it is synchronously unit-testable.
  ///
  /// A zero-width frame makes `aspectRatio` 0, so `configWidth / aspectRatio` is
  /// NaN (0/0). NaN fails every comparison, so the `> maxSize` clamp does not fire
  /// and `Int(NaN)` traps — an uncatchable crash, not a thrown error. Refuse to
  /// capture a zero-area window instead.
  static func captureDimensions(
    width: CGFloat, height: CGFloat, maxSize: CGFloat
  ) -> (width: Int, height: Int)? {
    guard width > 0, height > 0 else { return nil }

    let aspectRatio = width / height
    var configWidth = min(width, maxSize)
    var configHeight = configWidth / aspectRatio
    if configHeight > maxSize {
      configHeight = maxSize
      configWidth = configHeight * aspectRatio
    }
    return (Int(configWidth), Int(configHeight))
  }

  /// Aspect-preserving stream configuration, or nil if the window has no area.
  private func captureConfiguration(for window: SCWindow) -> SCStreamConfiguration? {
    guard
      let size = Self.captureDimensions(
        width: window.frame.width, height: window.frame.height, maxSize: maxSize)
    else { return nil }

    let config = SCStreamConfiguration()
    config.scalesToFit = true
    config.showsCursor = false
    config.width = size.width
    config.height = size.height
    return config
  }

  /// Capture using ScreenCaptureKit (macOS 14.0+)
  @available(macOS 14.0, *)
  private func captureWithScreenCaptureKit(windowID: CGWindowID) async -> Data? {
    do {
      var content = try await Self.sharedContent()
      var window = content.windows.first(where: { $0.windowID == windowID })
      if window == nil {
        content = try await Self.sharedContent(forceRefresh: true)
        window = content.windows.first(where: { $0.windowID == windowID })
      }
      guard let window else {
        log("Window not found in SCShareableContent")
        return nil
      }
      guard let config = captureConfiguration(for: window) else {
        log("Skipping capture of zero-area window frame")
        return nil
      }

      let filter = SCContentFilter(desktopIndependentWindow: window)

      let image = try await SCScreenshotManager.captureImage(
        contentFilter: filter,
        configuration: config
      )

      return jpegData(from: image)
    } catch {
      log("ScreenCaptureKit error: \(error.localizedDescription)")
      return nil
    }
  }

  /// Async wrapper for screencapture CLI (macOS 13.x fallback)
  private func captureWithScreencaptureAsync(windowID: CGWindowID) async -> Data? {
    await withCheckedContinuation { continuation in
      DispatchQueue.global(qos: .userInitiated).async {
        let result = self.captureWithScreencapture(windowID: windowID)
        continuation.resume(returning: result)
      }
    }
  }

  // MARK: - CGImage Capture (macOS 14+)

  /// Result of an attempted per-window capture.
  /// Distinguishes "the window went away" (normal — the user closed a tab / modal)
  /// from a real capture engine failure (permission revoked, stream error, etc.).
  enum WindowCaptureResult {
    case success(CGImage)
    case windowGone
    case failed
  }

  /// Capture the active window and return the raw CGImage (no JPEG encoding).
  /// Use this on macOS 14+ to avoid redundant encode/decode round-trips.
  @available(macOS 14.0, *)
  /// Capture a specific window by ID (avoids re-resolving the active window).
  /// Returns a detailed result so the caller can distinguish transient window
  /// disappearance from real capture failures.
  func captureWindowCGImage(windowID: CGWindowID) async -> WindowCaptureResult {
    do {
      var content = try await Self.sharedContent()
      if !content.windows.contains(where: { $0.windowID == windowID }) {
        content = try await Self.sharedContent(forceRefresh: true)
      }

      let filterAndConfig: (SCContentFilter, SCStreamConfiguration)? = autoreleasepool {
        guard let window = content.windows.first(where: { $0.windowID == windowID }),
          let config = captureConfiguration(for: window)
        else {
          return nil
        }

        return (SCContentFilter(desktopIndependentWindow: window), config)
      }

      guard let (filter, config) = filterAndConfig else {
        // Window ID no longer exists, or it reports a zero-area frame — the user
        // closed a tab, dismissed a modal, or the app destroyed the window between
        // resolution and capture. This is routine, not a capture failure. Caller
        // should re-resolve and retry.
        log("Window \(windowID) not capturable in SCShareableContent (closed or zero-area)")
        return .windowGone
      }

      let image = try await SCScreenshotManager.captureImage(
        contentFilter: filter,
        configuration: config
      )
      return .success(image)
    } catch {
      log("ScreenCaptureKit CGImage error for window \(windowID): \(error.localizedDescription)")
      return .failed
    }
  }

  /// Resolve and capture the active window while retaining whether the target
  /// disappeared/unavailable versus the capture engine failing.
  func captureActiveWindowCGImage() async -> WindowCaptureResult {
    let (_, _, windowID) = await Self.getActiveWindowInfoAsync()
    guard let windowID else {
      return .windowGone
    }
    return await captureWindowCGImage(windowID: windowID)
  }

  /// Encode a CGImage to JPEG data. Public wrapper for use by callers that need JPEG once.
  /// Wrapped in autoreleasepool because callers often run this in detached Tasks
  /// on the cooperative thread pool, which doesn't drain autorelease pools.
  func encodeJPEG(from cgImage: CGImage) -> Data? {
    return autoreleasepool {
      jpegData(from: cgImage)
    }
  }

  // MARK: - Synchronous Capture (Legacy)

  /// Capture the active window and return as JPEG data (synchronous - legacy)
  func captureActiveWindow() -> Data? {
    guard let windowID = Self.getActiveWindowID() else {
      log("No active window ID found")
      return nil
    }

    log("Capturing window ID: \(windowID)")
    // Use screencapture CLI (works on all macOS versions)
    return captureWithScreencapture(windowID: windowID)
  }

  /// Capture window using screencapture CLI
  private func captureWithScreencapture(windowID: CGWindowID) -> Data? {
    let tempPath = NSTemporaryDirectory() + "omi_capture_\(UUID().uuidString).jpg"

    let process = Process()
    process.executableURL = URL(fileURLWithPath: "/usr/sbin/screencapture")
    process.arguments = ["-l", String(windowID), "-x", "-o", tempPath]

    do {
      try process.run()
      process.waitUntilExit()

      if process.terminationStatus != 0 {
        logError("screencapture failed with exit code: \(process.terminationStatus)")
        return nil
      }

      let data = try Data(contentsOf: URL(fileURLWithPath: tempPath))
      try? FileManager.default.removeItem(atPath: tempPath)

      // Load, resize if needed, and re-encode
      guard let nsImage = NSImage(data: data) else {
        return nil
      }

      var finalImage = nsImage
      let size = nsImage.size
      if max(size.width, size.height) > maxSize {
        let ratio = maxSize / max(size.width, size.height)
        let newSize = NSSize(width: size.width * ratio, height: size.height * ratio)
        finalImage = resizeImage(nsImage, to: newSize)
      }

      return jpegData(from: finalImage)

    } catch {
      try? FileManager.default.removeItem(atPath: tempPath)
      return nil
    }
  }

  // MARK: - Image Processing

  /// Resize an NSImage to the specified size
  private func resizeImage(_ image: NSImage, to newSize: NSSize) -> NSImage {
    let newImage = NSImage(size: newSize)
    newImage.lockFocus()
    NSGraphicsContext.current?.imageInterpolation = .high
    image.draw(
      in: NSRect(origin: .zero, size: newSize),
      from: NSRect(origin: .zero, size: image.size),
      operation: .copy,
      fraction: 1.0
    )
    newImage.unlockFocus()
    return newImage
  }

  /// Convert CGImage to JPEG data using CGImageDestination (avoids NSImage→TIFF round-trip)
  private func jpegData(from cgImage: CGImage) -> Data? {
    let data = NSMutableData()
    guard
      let destination = CGImageDestinationCreateWithData(
        data as CFMutableData, "public.jpeg" as CFString, 1, nil)
    else {
      return nil
    }
    let options: [CFString: Any] = [kCGImageDestinationLossyCompressionQuality: jpegQuality]
    CGImageDestinationAddImage(destination, cgImage, options as CFDictionary)
    guard CGImageDestinationFinalize(destination) else {
      return nil
    }
    return data as Data
  }

  /// Convert NSImage to JPEG data
  private func jpegData(from image: NSImage) -> Data? {
    guard let tiffData = image.tiffRepresentation,
      let bitmap = NSBitmapImageRep(data: tiffData)
    else {
      return nil
    }

    return bitmap.representation(
      using: .jpeg,
      properties: [.compressionFactor: jpegQuality]
    )
  }
}
