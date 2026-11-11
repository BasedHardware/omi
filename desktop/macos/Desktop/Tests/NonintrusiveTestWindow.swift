import AppKit

@testable import Omi_Computer

/// Keeps AppKit-backed tests real without covering or intercepting the user's desktop.
///
/// Some interaction tests need an ordered window so SwiftUI builds its native hierarchy and
/// synthetic events carry a real window identity. They do not need that window in front of the
/// person running the suite. Keep only a dim one-pixel edge composited in a bottom corner, send the
/// window behind normal apps, and make it click-through while retaining its full content geometry.
@MainActor
enum NonintrusiveTestWindow {
  static let peekSize = NSSize(width: 1, height: 1)
  static let alpha: CGFloat = 0.001

  static func orderIn(_ window: NSWindow, preserveFrame: Bool = false) {
    prepareForOrdering(window)
    var parkedFrame: NSRect?
    if !preserveFrame, let screen = NSScreen.main ?? NSScreen.screens.first {
      let targetFrame = DesktopAutomationWindowPlacement.quietFrame(
        windowSize: window.frame.size,
        visibleFrame: screen.visibleFrame,
        peekSize: peekSize)
      parkedFrame = targetFrame
      window.setFrame(targetFrame, display: false)
    }
    window.orderFrontRegardless()
    // AppKit constrains a titled window during its first ordering. Reapply the parked frame once the
    // window has a number and backing store; alpha is already near-zero, so no full-size frame is
    // composited during this transition.
    if let parkedFrame, window.frame != parkedFrame {
      window.setFrame(parkedFrame, display: false, animate: false)
    }
    window.orderBack(nil)
  }

  /// Prevents the policy's own transition tests from flashing their initial full-size window before
  /// they deliberately exercise quiet mode. No run-loop turn occurs before the test restores alpha.
  static func prepareForOrdering(_ window: NSWindow, lockPosition: Bool = true) {
    window.alphaValue = alpha
    window.ignoresMouseEvents = true
    window.hasShadow = false
    window.level = .normal
    if lockPosition {
      window.isMovable = false
      window.isMovableByWindowBackground = false
    }
  }
}
