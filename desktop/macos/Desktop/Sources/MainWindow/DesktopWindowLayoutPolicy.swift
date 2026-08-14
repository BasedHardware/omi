import AppKit

/// The full desktop experience must fit on a 1024pt-wide display. Individual
/// rows choose compact layouts below their preferred width; this is only the
/// floor that keeps AppKit from restoring a window wider than the display.
enum DesktopWindowLayoutPolicy {
  static let width: CGFloat = 800
  static let height: CGFloat = 680
  static let minimumContentSize = NSSize(width: width, height: height)

  /// Air between the window frame and the glass, in points — never pixels.
  ///
  /// Matches the resize rim so AppKit's edge-resize sits on the visible silhouette,
  /// not on an outer invisible frame. Chat's own `pageMargin` is interior layout
  /// and is not this inset.
  static let windowInset: CGFloat = ShellClickThroughPolicy.resizeRim

  /// Readable lane plus `windowInset` on each side.
  ///
  /// Extra width beyond this is empty wallpaper that still belongs to the window
  /// (the invisible click border). Height stays display-limited: a taller panel
  /// is still hugged glass, not a gutter.
  static let maximumContentWidth =
    ChatComposerLayout.contentLaneMaxWidth + windowInset * 2
}
