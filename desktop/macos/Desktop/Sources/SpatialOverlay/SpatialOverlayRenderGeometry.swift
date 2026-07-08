import CoreGraphics

/// Pure, testable description of how the guidance overlay is laid out **inside its
/// panel** — the bubble rect, the pointer (arrow) rect, and the rendered arrow apex.
///
/// This is the single source of truth shared by the SwiftUI view that draws the
/// overlay (`CloudConnectorGuidanceView`) and the dogfood tests. The whole point is
/// that the pixel the user sees (`globalRenderedArrowTip`) is provably the same point
/// the solver intended (`SpatialOverlayPlacementResult.globalArrowTip`). Before this
/// module the apex math lived only inside the private SwiftUI view and was never
/// asserted, so the rendered arrow could drift from the solver target with no test
/// catching it.
///
/// Coordinate spaces:
/// - The solver works in **AppKit global** coordinates (origin bottom-left of the
///   primary display, +y up). `placement.arrowTipInPanel` is panel-local AppKit
///   (origin bottom-left of the panel, +y up).
/// - SwiftUI draws top-left origin, +y down. `pointerFrame`/`bubbleFrame`/
///   `renderedArrowTip` are in that SwiftUI panel-local space so the view can consume
///   them directly.
struct SpatialOverlayRenderGeometry: Equatable {
  /// Default visual size of the triangle when it points up/down. For
  /// leading/trailing the width and height swap (the triangle is rotated 90°).
  static let defaultArrowSize = CGSize(width: 18, height: 13)
  /// Inset between the panel edge and the bubble's rounded rectangle.
  static let bubbleInset: CGFloat = 8

  let panelSize: CGSize
  let panelOrigin: CGPoint  // AppKit global origin (bottom-left) of the panel.
  let edge: SpatialOverlayAttachmentEdge
  /// Arrow apex in panel-local AppKit coordinates (origin bottom-left, +y up).
  let arrowTipInPanel: CGPoint
  let arrowSize: CGSize

  init(placement: SpatialOverlayPlacementResult, panelSize: CGSize) {
    self.panelSize = panelSize
    self.panelOrigin = placement.panelFrame.origin
    self.edge = placement.attachmentEdge
    self.arrowTipInPanel = placement.arrowTipInPanel
    self.arrowSize = placement.arrowSize
  }

  /// Apex of the rendered triangle, in SwiftUI panel-local coordinates (top-left, +y down).
  var renderedArrowTip: CGPoint {
    CGPoint(x: arrowTipInPanel.x, y: panelSize.height - arrowTipInPanel.y)
  }

  /// Apex of the rendered triangle in AppKit global coordinates. By construction this
  /// equals `placement.globalArrowTip`; the round-trip test asserts it.
  var globalRenderedArrowTip: CGPoint {
    CGPoint(
      x: panelOrigin.x + renderedArrowTip.x,
      y: panelOrigin.y + (panelSize.height - renderedArrowTip.y)
    )
  }

  /// Bubble (rounded-rect callout) frame in SwiftUI panel-local coordinates.
  var bubbleFrame: CGRect {
    let inset = Self.bubbleInset
    let arrow = arrowSize.height
    switch edge {
    case .above:
      return CGRect(
        x: inset, y: inset, width: panelSize.width - inset * 2,
        height: panelSize.height - arrow - inset)
    case .below:
      return CGRect(
        x: inset, y: arrow, width: panelSize.width - inset * 2,
        height: panelSize.height - arrow - inset)
    case .leading:
      return CGRect(
        x: inset, y: inset, width: panelSize.width - arrow - inset,
        height: panelSize.height - inset * 2)
    case .trailing:
      return CGRect(
        x: arrow, y: inset, width: panelSize.width - arrow - inset,
        height: panelSize.height - inset * 2)
    }
  }

  /// Triangle (pointer) frame in SwiftUI panel-local coordinates. The apex always
  /// lands on `renderedArrowTip` regardless of edge.
  var pointerFrame: CGRect {
    let tip = renderedArrowTip
    let w = arrowSize.width
    let h = arrowSize.height
    switch edge {
    case .above:
      return CGRect(x: tip.x - w / 2, y: tip.y - h, width: w, height: h)
    case .below:
      return CGRect(x: tip.x - w / 2, y: tip.y, width: w, height: h)
    case .leading:
      return CGRect(x: tip.x - h, y: tip.y - w / 2, width: h, height: w)
    case .trailing:
      return CGRect(x: tip.x, y: tip.y - w / 2, width: h, height: w)
    }
  }
}
