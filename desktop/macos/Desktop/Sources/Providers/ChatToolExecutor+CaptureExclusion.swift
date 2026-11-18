import AppKit
import Foundation

/// `capture_screen` leaves out the apps Omi never looks at; see `CaptureScreenExclusion`.
extension ChatToolExecutor {
  static func captureScreenLeavingOutRefusedApps() async -> ScreenCaptureManager.ChatScreenshotCapture? {
    let running = NSWorkspace.shared.runningApplications.map { app in
      UIAutomationRunningApp(
        pid: app.processIdentifier, bundleID: app.bundleIdentifier ?? "", localizedName: app.localizedName,
        bundleURL: app.bundleURL, isActive: app.isActive)
    }
    let excluded = CaptureScreenExclusion.excludedPIDs(
      running: running, ownPID: ProcessInfo.processInfo.processIdentifier,
      isExcludedFromCapture: { RewindSettings.shared.isAppExcluded($0) })
    log("capture_screen: leaving out \(excluded.count) app(s)")
    return await ScreenCaptureManager.captureScreenWithDetailTiles(excluding: excluded)
  }
}
