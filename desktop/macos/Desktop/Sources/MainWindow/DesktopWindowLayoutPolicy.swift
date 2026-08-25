import AppKit

/// The full desktop experience must fit on a 1024pt-wide display. Individual
/// rows choose compact layouts below their preferred width; this is only the
/// floor that keeps AppKit from restoring a window wider than the display.
enum DesktopWindowLayoutPolicy {
  static let width: CGFloat = 800
  static let height: CGFloat = 680
  static let minimumContentSize = NSSize(width: width, height: height)
}
