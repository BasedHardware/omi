import AppKit

@MainActor
extension AppDelegate {
  private static let shellWindowLaunchRetryDelay: TimeInterval = 0.2

  /// SwiftUI's `main` scene is not guaranteed to exist when the application delegate finishes
  /// launching. Keep asking for it for a bounded period so a profile reset cannot leave the app
  /// running with no usable window, while preserving the intentional headless update relaunch.
  func scheduleShellWindowPresentation(
    restoreMainWindowAfterUpdateRelaunch: Bool?,
    attempt: Int = 0
  ) {
    if let window = ShellSummon.shellWindow() {
      ShellSummon.applyPresentation(to: window)
      if restoreMainWindowAfterUpdateRelaunch == false {
        window.orderOut(nil)
        log("AppDelegate: Shell suppressed after background update relaunch")
      } else if DesktopAutomationWindowPresentation.currentMode != .normal {
        DesktopAutomationWindowPresentation.applyLaunchMode(to: window)
        log(
          "AppDelegate: Shell launched in \(DesktopAutomationWindowPresentation.currentMode.rawValue) automation presentation"
        )
      } else {
        NSApp.activate()
        ShellSummon.summon(alwaysPlace: true)
        log("AppDelegate: Shell summoned on launch")
      }
      return
    }

    if restoreMainWindowAfterUpdateRelaunch == false {
      log("AppDelegate: Shell suppressed after background update relaunch; no window to hide")
      return
    }

    switch ShellWindowLaunchRecoveryPolicy.decision(for: attempt) {
    case .requestWindow:
      // `openWindow` is idempotent for an existing scene. Repeating it at a slow cadence also
      // covers the brief period where SwiftUI has not registered the environment action yet.
      Self.openMainWindow?()
      log("AppDelegate: Requested main scene while waiting for shell window (attempt \(attempt))")
    case .retry:
      break
    case .stop:
      log("AppDelegate: ERROR - shell window not found after launch recovery retries")
      return
    }

    DispatchQueue.main.asyncAfter(deadline: .now() + Self.shellWindowLaunchRetryDelay) { [weak self] in
      self?.scheduleShellWindowPresentation(
        restoreMainWindowAfterUpdateRelaunch: restoreMainWindowAfterUpdateRelaunch,
        attempt: attempt + 1)
    }
  }
}
