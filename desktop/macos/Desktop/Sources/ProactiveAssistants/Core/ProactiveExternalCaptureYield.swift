import Foundation

/// Decides, once per capture tick, whether Omi must skip its periodic screen capture to
/// yield to an **external capture** in progress:
///
/// - a screenshot / screen-recording app frontmost (CleanShot, Shottr, macOS screenshot, …):
///   concurrent ScreenCaptureKit use stalls the user's capture UI for 20–60s (#6819), and
/// - an active outgoing call screen share (Zoom/Teams/Meet presenting): the same WindowServer
///   capture-arbitration contention has been observed to stop the user's share outright
///   (issue #10143).
///
/// Both conditions run the same pause/backoff state machine (`ProactiveScreenshotCaptureGate`):
/// pause every tick while the condition holds, then hold a short backoff after it clears so the
/// other app's teardown/editor UI isn't disturbed either.
/// Failure class: FC-concurrent-capture-contention.
struct ProactiveExternalCaptureYield {
  private(set) var screenshotGate = ProactiveScreenshotCaptureGate()
  private(set) var shareGate = ProactiveScreenshotCaptureGate()

  /// True when this tick must skip capture. `isScreenShareActive` is an autoclosure so the
  /// share check (a CGWindowList enumeration) is not evaluated while the screenshot gate
  /// already pauses the tick.
  mutating func shouldYield(
    isScreenshotAppFrontmost: Bool,
    isScreenShareActive: @autoclosure () -> Bool,
    now: Date,
    screenshotBackoffDuration: TimeInterval,
    shareBackoffDuration: TimeInterval
  ) -> Bool {
    let wasScreenshotAppFrontmost = screenshotGate.wasScreenshotAppFrontmost
    switch screenshotGate.nextDecision(
      isScreenshotAppFrontmost: isScreenshotAppFrontmost,
      now: now,
      backoffDuration: screenshotBackoffDuration
    ) {
    case .pause:
      if !wasScreenshotAppFrontmost {
        log("ProactiveAssistantsPlugin: Screenshot app frontmost — pausing capture to avoid WindowServer contention")
      }
      return true
    case .resumeIntoBackoff:
      log(
        "ProactiveAssistantsPlugin: Screenshot app no longer frontmost, holding backoff for \(Int(max(0, screenshotGate.backoffUntil.timeIntervalSinceNow)))s"
      )
      return true
    case .resumeAndCapture:
      log("ProactiveAssistantsPlugin: Screenshot app no longer frontmost, holding backoff for 0s")
    case .continueBackoff:
      return true
    case .capture:
      break
    }

    let wasScreenSharing = shareGate.wasScreenshotAppFrontmost
    switch shareGate.nextDecision(
      isScreenshotAppFrontmost: isScreenShareActive(),
      now: now,
      backoffDuration: shareBackoffDuration
    ) {
    case .pause:
      if !wasScreenSharing {
        log("ProactiveAssistantsPlugin: Active screen share detected — pausing capture until the share ends")
      }
      return true
    case .resumeIntoBackoff:
      log(
        "ProactiveAssistantsPlugin: Screen share ended, holding backoff for \(Int(max(0, shareGate.backoffUntil.timeIntervalSinceNow)))s"
      )
      return true
    case .resumeAndCapture:
      log("ProactiveAssistantsPlugin: Screen share ended, resuming capture")
      return false
    case .continueBackoff:
      return true
    case .capture:
      return false
    }
  }

  mutating func reset() {
    screenshotGate.reset()
    shareGate.reset()
  }
}
