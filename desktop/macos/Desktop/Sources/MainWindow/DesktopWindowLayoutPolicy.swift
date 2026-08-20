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

  /// Readable lane plus `windowInset` on each side.
  ///
  /// Extra width beyond this is empty wallpaper that still belongs to the window
  /// until AppKit clamps the frame. Height stays display-limited: a taller panel
  /// is still hugged glass, not a gutter.
  static let maximumContentWidth =
    ChatComposerLayout.contentLaneMaxWidth + windowInset * 2
}
