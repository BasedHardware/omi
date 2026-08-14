import CoreGraphics

/// Scale of the idle island. Retract animates to `retractedProgress`; anything
/// that cancels that animation without `orderOut` must land back on
/// `revealedProgress` or the chrome stays scaled into the camera housing.
enum FloatingBarNotchRevealPolicy {
  static let retractedProgress: CGFloat = 0.01
  static let revealedProgress: CGFloat = 1

  /// Hover-frame assertions, Space reconciliation, and display revalidation
  /// often no-op `resizeToFrame`. Those must not share a cancellation token
  /// with retract/reveal.
  static var noOpFrameAssertionInvalidatesRevealToken: Bool { false }

  /// A retract whose `orderOut` never ran left the window on-screen at the
  /// collapsed scale. Restore full scale only when nothing else is still
  /// retracting it.
  static func shouldRestoreProgressAfterCancelledRetract(
    windowStillVisible: Bool,
    retractStillInFlight: Bool
  ) -> Bool {
    windowStillVisible && !retractStillInFlight
  }
}

enum FloatingBarNotchTransition {
  static func revealProgress(_ rawProgress: CGFloat) -> CGFloat {
    let progress = min(max(rawProgress, 0), 1)
    return 1 - pow(1 - progress, 2)
  }

  static func hiddenFrame(for targetFrame: CGRect) -> CGRect {
    CGRect(
      x: targetFrame.midX - 1,
      y: targetFrame.maxY - 1,
      width: 2,
      height: 1
    )
  }

  static func growFrame(targetFrame: CGRect, progress rawProgress: CGFloat) -> CGRect {
    let eased = revealProgress(rawProgress)
    let width = max(2, targetFrame.width * eased)
    let height = max(1, targetFrame.height * eased)
    return CGRect(
      x: targetFrame.midX - width / 2,
      y: targetFrame.maxY - height,
      width: width,
      height: height
    )
  }

  static func growFrames(targetFrame: CGRect, steps: Int) -> [CGRect] {
    let frameCount = max(1, steps)
    return (1...frameCount).map { step in
      growFrame(targetFrame: targetFrame, progress: CGFloat(step) / CGFloat(frameCount))
    }
  }
}
