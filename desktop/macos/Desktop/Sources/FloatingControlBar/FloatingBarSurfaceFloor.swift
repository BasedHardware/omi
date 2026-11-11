import AppKit

/// The window-frame floor implied by the floating bar's live presentation.
///
/// Every scrunched-notch report has had one shape: a resize path derived the
/// closed surface from what *it* believed was showing — the bare idle lobe,
/// the listening island — instead of from the state that was actually
/// mounted, and the window settled on that stale size with a card, a status
/// banner, or the thinking mark still rendering inside it. #12630 and #12882
/// fixed the call sites they could see by routing them through the composed
/// sizing authorities. That leaves every future call site, every ordering
/// race between two resizes aimed at the same transition, and AppKit auto
/// layout free to reintroduce the class.
///
/// This policy closes the class at the one boundary every path crosses. The
/// closed surface is a pure function of presentation state; whatever resized
/// the window, once the frame settles it may never be smaller than that
/// surface. The window computes the floor from its sizing authorities and
/// asks this policy whether the frame (or the frame an in-flight animation is
/// heading for) needs correcting. Pure so it is testable without a display.
enum FloatingBarSurfaceFloor {
  /// Why the floor is not enforced at this moment. Each case is a surface
  /// that legitimately owns the frame for its duration.
  enum Deferral: Equatable {
    /// An ordered-out window's frame is not on screen; the show path
    /// re-normalises it before the next reveal.
    case windowHidden
    /// The user is dragging the pill; the frame follows the pointer.
    case userDragging
    /// The user is dragging the response resize grip.
    case userResizing
    /// An open conversation (input, response, agent chat) is user content
    /// with its own height observers and a user-resizable frame.
    case conversationOpen
    /// The reveal/retract morph scales content inside a fixed frame and
    /// invalidates frame animations on its own generation.
    case revealOrRetractInFlight
  }

  static func deferral(
    isVisible: Bool,
    isUserDragging: Bool,
    isUserResizing: Bool,
    isConversationOpen: Bool,
    isRevealOrRetractInFlight: Bool
  ) -> Deferral? {
    if !isVisible { return .windowHidden }
    if isUserDragging { return .userDragging }
    if isUserResizing { return .userResizing }
    if isConversationOpen { return .conversationOpen }
    if isRevealOrRetractInFlight { return .revealOrRetractInFlight }
    return nil
  }

  /// The frame the window must land on instead of `effectiveFrame`, or nil
  /// when `effectiveFrame` already satisfies the floor.
  ///
  /// The correction only ever grows: a frame larger than the floor in either
  /// dimension is a transparent margin (the black surface is content-sized
  /// in every closed state), while a frame smaller than the floor clips or
  /// re-wraps whatever is mounted. `anchor` is the placement contract the
  /// window already uses for closed surfaces — the display top-centre for a
  /// notch island, the current top-centre for a pill.
  static func correctedFrame(
    effectiveFrame: NSRect,
    floorSize: NSSize,
    anchor: FloatingControlBarGeometry.TransitionAnchor,
    epsilon: CGFloat = 0.5
  ) -> NSRect? {
    let widthSatisfied = effectiveFrame.width + epsilon >= floorSize.width
    let heightSatisfied = effectiveFrame.height + epsilon >= floorSize.height
    guard !(widthSatisfied && heightSatisfied) else { return nil }
    let size = FloatingControlBarGeometry.unionSize(effectiveFrame.size, floorSize)
    return FloatingControlBarGeometry.targetFrame(
      currentFrame: effectiveFrame,
      targetSize: size,
      anchor: anchor
    )
  }
}
