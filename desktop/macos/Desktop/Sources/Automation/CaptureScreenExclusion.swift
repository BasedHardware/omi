import CoreGraphics
import Foundation
import ScreenCaptureKit

/// The apps `capture_screen` leaves out of its image: Omi itself and every
/// `com.omi.*` build, the apps on the shared UI automation safety floor
/// (terminals, password managers, Keychain, sign-in and authorization
/// prompts) and the apps the person excluded from capture. The same generated
/// floor `ui_snapshot` refuses, so the two tools cannot disagree about which
/// apps Omi never looks at.
///
/// The image is taken with a ScreenCaptureKit filter that removes those apps'
/// windows, so a refused app that is frontmost or fills the screen is simply
/// absent from the picture. When that filter cannot be used, the plain
/// display capture is allowed only if none of those apps has a window on
/// screen; otherwise nothing is captured.
enum CaptureScreenExclusion {
  typealias Floor = GeneratedUIAutomationSafetyFloor

  /// The processes whose windows are left out.
  static func excludedPIDs(
    running: [UIAutomationRunningApp], ownPID: pid_t, isExcludedFromCapture: (String) -> Bool
  ) -> Set<pid_t> {
    var excluded: Set<pid_t> = [ownPID]
    for app in running {
      let bundleID = app.bundleID.lowercased()
      let refused =
        Floor.refusedBundleIDPrefixes.contains(where: bundleID.hasPrefix) || Floor.refusedBundleIDs.contains(bundleID)
      let name = app.localizedName?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
      if refused || (!name.isEmpty && isExcludedFromCapture(name)) { excluded.insert(app.pid) }
    }
    return excluded
  }

  /// The applications the capture filter removes, from what ScreenCaptureKit lists.
  static func applicationsToExclude<Application>(
    _ applications: [Application], processID: (Application) -> pid_t, excluded: Set<pid_t>
  ) -> [Application] {
    applications.filter { excluded.contains(processID($0)) }
  }

  /// Whether the unfiltered display capture may stand in for the filtered one:
  /// only when no left-out app has a window on screen.
  static func plainCaptureAllowed(onScreenWindowOwners: [pid_t], excluded: Set<pid_t>) -> Bool {
    !onScreenWindowOwners.contains(where: excluded.contains)
  }

  /// The display image with the left-out apps' windows removed, or nil.
  static func captureDisplay(_ displayID: CGDirectDisplayID, excluding excluded: Set<pid_t>) async -> CGImage? {
    if ScreenRecordingPermissionPolicy.shouldInvokeScreenCaptureKit(
      grantedAtLaunch: ScreenCaptureService.grantedAtProcessStart)
    {
      do {
        let content = try await SCShareableContent.excludingDesktopWindows(false, onScreenWindowsOnly: true)
        if let display = content.displays.first(where: { $0.displayID == displayID }) {
          let filter = SCContentFilter(
            display: display,
            excludingApplications: applicationsToExclude(
              content.applications, processID: \.processID, excluded: excluded),
            exceptingWindows: [])
          let config = SCStreamConfiguration()
          let mode = CGDisplayCopyDisplayMode(displayID)
          config.width = mode?.pixelWidth ?? display.width * 2
          config.height = mode?.pixelHeight ?? display.height * 2
          config.showsCursor = false
          return try await SCScreenshotManager.captureImage(contentFilter: filter, configuration: config)
        }
        log("CaptureScreenExclusion: display \(displayID) not in shareable content")
      } catch {
        log("CaptureScreenExclusion: filtered capture failed: \(error.localizedDescription)")
      }
    }
    guard plainCaptureAllowed(onScreenWindowOwners: onScreenWindowOwners(), excluded: excluded) else {
      log("CaptureScreenExclusion: a left-out app is on screen and the filter is unavailable; not capturing")
      return nil
    }
    return ScreenCaptureManager.captureScreenImage(displayID: displayID)
  }

  /// Owners of the normal-layer windows on screen now.
  private static func onScreenWindowOwners() -> [pid_t] {
    let windows =
      CGWindowListCopyWindowInfo([.optionOnScreenOnly, .excludeDesktopElements], kCGNullWindowID)
      as? [[String: Any]] ?? []
    return windows.compactMap { window in
      guard (window[kCGWindowLayer as String] as? Int) == 0 else { return nil }
      return (window[kCGWindowOwnerPID as String] as? Int).map { pid_t($0) }
    }
  }
}
