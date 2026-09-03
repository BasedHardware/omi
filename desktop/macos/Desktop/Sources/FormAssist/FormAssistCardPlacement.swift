import CoreGraphics
import Foundation

/// Where the card goes so it does not cover the fields it is about.
///
/// The shared connector placement puts a card over the window it points at, which is
/// right for "click Add in this dialog" and wrong here: the user is reading the form
/// underneath it. Top-right of the display, out of the way of every form layout, and in
/// the same place every time so it is never hunted for. Anchoring to the window
/// underneath was tried and is worse — the card lands somewhere new for every window,
/// which is the opposite of not having to look for it.
///
/// The one thing that moves it is the user moving it. `offset` is their remembered
/// choice, applied to the corner and clamped; see `PanelPlacementStore`.
///
/// Rectangles are AppKit-oriented (origin bottom-left).
enum FormAssistCardPlacement {
  static let margin: CGFloat = 16

  /// The tallest the card may be: half the display it lands on. A form with more fields
  /// than that scrolls inside the card rather than growing down the screen — the card
  /// sits over the form the user is reading, so covering all of it is never right.
  static func maxCardHeight(visibleFrame: CGRect) -> CGFloat {
    max(0, visibleFrame.height / 2)
  }

  static func frame(cardSize: CGSize, visibleFrame: CGRect, offset: CGSize? = nil) -> CGRect {
    let width = min(cardSize.width, visibleFrame.width - margin * 2)
    let height = min(cardSize.height, visibleFrame.height - margin * 2)
    let corner = CGRect(
      x: max(visibleFrame.minX + margin, visibleFrame.maxX - width - margin),
      y: max(visibleFrame.minY + margin, visibleFrame.maxY - height - margin),
      width: width,
      height: height
    )
    guard let offset, offset != .zero else { return corner }

    let proposed = corner.offsetBy(dx: offset.width, dy: offset.height)
    let clamped = CGRect(
      x: min(
        max(proposed.minX, visibleFrame.minX + margin),
        max(visibleFrame.minX + margin, visibleFrame.maxX - width - margin)),
      y: min(
        max(proposed.minY, visibleFrame.minY + margin),
        max(visibleFrame.minY + margin, visibleFrame.maxY - height - margin)),
      width: width,
      height: height
    )
    // A remembered position that no longer lands on this display — a smaller screen, a
    // monitor unplugged — is not a position any more. Sliding it back to an edge would
    // put the card somewhere the user never chose, so the default corner wins instead.
    let slid = max(abs(clamped.minX - proposed.minX), abs(clamped.minY - proposed.minY))
    return slid > max(width, height) / 2 ? corner : clamped
  }
}
