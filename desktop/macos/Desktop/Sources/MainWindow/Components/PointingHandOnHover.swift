import AppKit
import SwiftUI

/// The pointing hand while a clickable element is hovered, pushed
/// and popped in balance. SwiftUI does not deliver `onHover(false)` when a
/// hovered view leaves the hierarchy — a transcript refresh or re-sync rebuilds
/// every bubble — so an unpaired push would leave the hand over the whole app;
/// `onDisappear` is the exit that hover never reports.
///
/// Shared: every clickable surface that is not a system control uses `.pointingHandOnHover()` rather
/// than pushing `NSCursor` itself.
struct PointingHandOnHover: ViewModifier {
  var onHoverChange: ((Bool) -> Void)? = nil
  @State private var didPushCursor = false

  func body(content: Content) -> some View {
    content
      .onHover { hovering in
        onHoverChange?(hovering)
        setHovered(hovering)
      }
      .onDisappear { setHovered(false) }
  }

  private func setHovered(_ hovering: Bool) {
    if hovering, !didPushCursor {
      NSCursor.pointingHand.push()
      didPushCursor = true
    } else if !hovering, didPushCursor {
      NSCursor.pop()
      didPushCursor = false
    }
  }
}

extension View {
  /// The pointing hand over a clickable surface, balanced even when the view disappears mid-hover.
  func pointingHandOnHover(_ onHoverChange: ((Bool) -> Void)? = nil) -> some View {
    modifier(PointingHandOnHover(onHoverChange: onHoverChange))
  }
}
