import CoreGraphics
import Foundation

/// Where the card goes so it does not cover the fields it is about.
///
/// The shared connector placement puts a card over the window it points at, which is
/// right for "click Add in this dialog" and wrong here: the user is reading the form
/// underneath it. Top-right of the screen, out of the way of every form layout, and in
/// the same place every time so it is never hunted for.
///
/// Rectangles are AppKit-oriented (origin bottom-left).
enum FormAssistCardPlacement {
  static let margin: CGFloat = 16

  static func frame(cardSize: CGSize, visibleFrame: CGRect) -> CGRect {
    CGRect(
      x: max(visibleFrame.minX + margin, visibleFrame.maxX - cardSize.width - margin),
      y: max(visibleFrame.minY + margin, visibleFrame.maxY - cardSize.height - margin),
      width: min(cardSize.width, visibleFrame.width - margin * 2),
      height: min(cardSize.height, visibleFrame.height - margin * 2)
    )
  }
}
