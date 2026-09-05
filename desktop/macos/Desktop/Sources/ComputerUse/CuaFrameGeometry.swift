import CoreGraphics
import Foundation

/// The one place a computer-use coordinate is converted, and the only reason
/// clicks land where the model meant.
///
/// Three coordinate spaces meet here and none of them agree:
///
///   * **Global points** — `CGDisplayBounds`, top-left origin, displays laid out
///     side by side so a second monitor starts at a non-zero origin. `CGEvent`
///     mouse positions and accessibility `AXPosition` frames both live here.
///     `NSScreen.frame` does *not*: it is bottom-left origin, and mixing the two
///     is the bug that puts every click on the wrong half of the screen.
///   * **Native pixels** — global points times the display's backing scale. A
///     Retina display is 2x, and a capture is always in pixels.
///   * **Delivered image pixels** — what the model actually saw, after the
///     capture is scaled down to fit inside the vision limits. This is the space
///     the model answers in, because it is the only one it can see.
///
/// A frame records the display it came from and the size it was delivered at, so
/// a point the model names in the picture becomes a point on the desk. Nothing
/// else in the module does coordinate arithmetic.
struct CuaFrameGeometry: Equatable, Sendable {
  /// Where the captured region sits in global points.
  let bounds: CGRect
  /// Size of the image the model was given, in its own pixels.
  let imageSize: CGSize

  /// A point in the delivered image, as a point on the desk.
  ///
  /// Out-of-range input is clamped rather than refused: a model pointing at the
  /// very edge of a window is asking for the edge, and a click one pixel outside
  /// a 1512-wide frame is not a reason to fail a turn.
  func globalPoint(forImagePoint point: CGPoint) -> CGPoint {
    guard imageSize.width > 0, imageSize.height > 0 else { return bounds.origin }
    let x = min(max(point.x, 0), imageSize.width)
    let y = min(max(point.y, 0), imageSize.height)
    return CGPoint(
      x: bounds.minX + (x / imageSize.width) * bounds.width,
      y: bounds.minY + (y / imageSize.height) * bounds.height
    )
  }

  /// A point on the desk, back in the delivered image. The inverse of
  /// `globalPoint(forImagePoint:)`, for reporting where the cursor is in terms
  /// of the picture the model is looking at.
  func imagePoint(forGlobalPoint point: CGPoint) -> CGPoint? {
    guard bounds.width > 0, bounds.height > 0, bounds.contains(point) else { return nil }
    return CGPoint(
      x: (point.x - bounds.minX) / bounds.width * imageSize.width,
      y: (point.y - bounds.minY) / bounds.height * imageSize.height
    )
  }

  /// The delivered size for a capture of `source` pixels.
  ///
  /// Claude rejects an oversized image inside a tool result rather than scaling
  /// it, so the scaling has to happen here. The long edge is capped and the
  /// aspect ratio kept; a source already inside the cap is delivered untouched,
  /// because upscaling costs visual tokens and adds nothing to read.
  static func fittedImageSize(source: CGSize, maxLongEdge: CGFloat) -> CGSize? {
    guard source.width >= 1, source.height >= 1, maxLongEdge >= 1 else { return nil }
    let longEdge = max(source.width, source.height)
    guard longEdge > maxLongEdge else {
      return CGSize(width: source.width.rounded(), height: source.height.rounded())
    }
    let scale = maxLongEdge / longEdge
    return CGSize(
      width: max(1, (source.width * scale).rounded()),
      height: max(1, (source.height * scale).rounded())
    )
  }
}
