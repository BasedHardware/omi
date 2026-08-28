import AppKit
import Foundation

/// Where floating panels open.
///
/// The default is the top-right of the display, and the reason it is a fixed corner
/// rather than something anchored to the window underneath is consistency: a card that
/// lands in a different place each time is a card the user has to look for. Once they
/// drag it somewhere, that becomes the place — for every panel after it, across
/// launches, because a position the user chose is a preference, not a gesture.
///
/// The stored value is an offset from the visible frame's top-right corner, not an
/// absolute point, so it survives a different display, a resolution change and the menu
/// bar coming and going. Anything that no longer lands on screen falls back to the
/// corner rather than opening a panel the user cannot reach.
@MainActor
enum PanelPlacementStore {
  private static let offsetXKey = "panelPlacementOffsetX"
  private static let offsetYKey = "panelPlacementOffsetY"
  /// A drag has to actually move the panel before it counts as a choice.
  private static let minimumDragDistance: CGFloat = 8

  /// The panel's top-right corner relative to the visible frame's, or nil until the user
  /// has moved a panel.
  static var offset: CGSize? {
    get {
      let defaults = UserDefaults.standard
      guard defaults.object(forKey: offsetXKey) != nil else { return nil }
      return CGSize(
        width: CGFloat(defaults.double(forKey: offsetXKey)),
        height: CGFloat(defaults.double(forKey: offsetYKey)))
    }
    set {
      let defaults = UserDefaults.standard
      guard let newValue else {
        defaults.removeObject(forKey: offsetXKey)
        defaults.removeObject(forKey: offsetYKey)
        return
      }
      defaults.set(Double(newValue.width), forKey: offsetXKey)
      defaults.set(Double(newValue.height), forKey: offsetYKey)
    }
  }

  static func record(panelFrame: CGRect, visibleFrame: CGRect) {
    let moved = offsetOf(panelFrame: panelFrame, visibleFrame: visibleFrame)
    // The default corner is the absence of a preference. Dragging a panel back to it
    // clears the stored one instead of pinning the same position twice over.
    guard abs(moved.width) > minimumDragDistance || abs(moved.height) > minimumDragDistance else {
      offset = nil
      return
    }
    offset = moved
  }

  static func offsetOf(panelFrame: CGRect, visibleFrame: CGRect) -> CGSize {
    CGSize(
      width: panelFrame.maxX - (visibleFrame.maxX - FormAssistCardPlacement.margin),
      height: panelFrame.maxY - (visibleFrame.maxY - FormAssistCardPlacement.margin))
  }
}
