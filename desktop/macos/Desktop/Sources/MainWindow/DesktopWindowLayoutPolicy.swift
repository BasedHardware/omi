import AppKit

/// The full desktop experience must fit on a 1024pt-wide display. Individual
/// rows choose compact layouts below their preferred width; this is only the
/// floor that keeps AppKit from restoring a window wider than the display.
enum DesktopWindowLayoutPolicy {
  static let width: CGFloat = 800
  static let height: CGFloat = 680
  static let minimumContentSize = NSSize(width: width, height: height)

  /// Readable lane plus the page margin on each side, in points — never pixels.
  ///
  /// Extra width beyond this is empty wallpaper that still belongs to the window
  /// (the invisible click border). Height stays display-limited: a taller panel
  /// is still hugged glass, not a gutter.
  static let maximumContentWidth =
    ChatComposerLayout.contentLaneMaxWidth + ChatComposerLayout.pageMargin * 2
}
