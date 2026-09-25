import AppKit

/// The full desktop experience must fit on a 1024pt-wide display. Individual
/// rows choose compact layouts below their preferred width; this is only the
/// floor that keeps AppKit from restoring a window wider than the display.
enum DesktopWindowLayoutPolicy {
  static let width: CGFloat = 800
  static let height: CGFloat = 680
  static let minimumContentSize = NSSize(width: width, height: height)

  /// Air between the window frame and the glass. Zero: the visible panel edge *is* the
  /// window edge, so AppKit's resize rim sits on the glass rather than on an invisible
  /// gutter. Chat's own `pageMargin` is interior layout and is not this inset.
  static let windowInset: CGFloat = 0

  @MainActor
  static func maximumContentSize(for window: NSWindow) -> NSSize {
    guard let visibleFrame = (window.screen ?? NSScreen.main)?.visibleFrame else {
      return NSSize(width: 10_000, height: 10_000)
    }
    return window.contentRect(forFrameRect: visibleFrame).size
  }
}
