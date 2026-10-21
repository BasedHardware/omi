import AppKit

/// How one track segment's colour meets the next.
///
/// Segments used to butt against each other as solid fills, so a day read as a row of hard
/// colour switches. Adjacent segments now ease into each other: each edge is drawn in the colour
/// halfway between the two apps, and both segments blend toward that shared colour over a short
/// run, so the seam is continuous from either side. The body of a segment stays its own colour —
/// the blend is an edge treatment, not a wash, and a segment's identity is still readable at its
/// centre.
///
/// Pure arithmetic over `RewindActivityBlock`s and colours, so a hermetic test can drive it without
/// a window server; `RewindTrackNSView` only asks it what to draw.
enum RewindTrackGradient {
  /// Neighbours further apart than this many seconds are not one stretch of the day and keep a
  /// hard edge. `RewindTrackWindow.blocks` tiles its output, so on a real track this is only ever
  /// exceeded by a deliberately sparse input.
  static let contiguousGap: Double = 90

  /// The widest run, in points, over which an edge eases toward its neighbour. Kept short: a wide
  /// blend on a narrow segment would leave it with no body colour at all.
  static let maximumBlendWidth: CGFloat = 28

  /// The colours a segment's two edges are drawn in, and how far in each blend reaches.
  struct Edges: Equatable {
    let leading: NSColor
    let trailing: NSColor
    let blendWidth: CGFloat
  }

  static func isContiguous(_ earlier: RewindActivityBlock, _ later: RewindActivityBlock) -> Bool {
    later.startedAt - earlier.endedAt <= contiguousGap
  }

  /// The midpoint of two colours in device RGB — the one colour both sides of a seam agree on.
  static func blend(_ a: NSColor, _ b: NSColor) -> NSColor {
    guard let a = a.usingColorSpace(.deviceRGB), let b = b.usingColorSpace(.deviceRGB) else { return a }
    return NSColor(
      deviceRed: (a.redComponent + b.redComponent) / 2,
      green: (a.greenComponent + b.greenComponent) / 2,
      blue: (a.blueComponent + b.blueComponent) / 2,
      alpha: 1)
  }

  /// The edges for `block`, given its neighbours on the track and its drawn width.
  ///
  /// An edge blends only toward a neighbour that is contiguous *and* a different app; a same-app
  /// neighbour (a sparse sample can split one stretch) is the same colour, and a hard edge into the
  /// same colour is invisible anyway. `width` bounds the blend so it never exceeds half the segment.
  static func edges(
    for block: RewindActivityBlock,
    previous: RewindActivityBlock?,
    next: RewindActivityBlock?,
    width: CGFloat,
    colour: (String) -> NSColor
  ) -> Edges {
    let body = colour(block.app)
    var leading = body
    if let previous, previous.app != block.app, isContiguous(previous, block) {
      leading = blend(colour(previous.app), body)
    }
    var trailing = body
    if let next, next.app != block.app, isContiguous(block, next) {
      trailing = blend(body, colour(next.app))
    }
    return Edges(leading: leading, trailing: trailing, blendWidth: min(maximumBlendWidth, max(0, width) / 2))
  }

  /// The gradient that paints a segment left to right: its leading edge easing into the body over
  /// `blendWidth`, the body, then the body easing into the trailing edge.
  static func gradient(body: NSColor, edges: Edges, width: CGFloat) -> NSGradient? {
    guard width > 0 else { return nil }
    let inset = min(0.5, edges.blendWidth / width)
    return NSGradient(
      colorsAndLocations: (edges.leading, 0), (body, inset), (body, 1 - inset), (edges.trailing, 1))
  }
}
