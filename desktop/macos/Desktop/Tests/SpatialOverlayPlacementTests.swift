import XCTest

@testable import Omi_Computer

final class SpatialOverlayPlacementTests: XCTestCase {
  private let screen = SpatialOverlayScreen(
    id: "main",
    frame: CGRect(x: 0, y: 0, width: 1440, height: 900),
    visibleFrame: CGRect(x: 0, y: 24, width: 1440, height: 876)
  )

  func testPlacesAboveTargetWithArrowTipAligned() throws {
    let target = candidate(rect: CGRect(x: 700, y: 420, width: 80, height: 36))
    let spec = SpatialOverlayPlacementSpec(
      overlaySize: CGSize(width: 330, height: 118),
      preferredEdges: [.above],
      canCoverTarget: true
    )

    let result = try SpatialOverlayPlacementSolver.place(target: target, spec: spec).get()

    XCTAssertEqual(result.attachmentEdge, .above)
    XCTAssertEqual(result.globalArrowTip.x, target.targetPoint.x, accuracy: 0.1)
    XCTAssertEqual(result.globalArrowTip.y, target.targetPoint.y, accuracy: 0.1)
    XCTAssertTrue(
      screen.visibleFrame.insetBy(dx: spec.margin, dy: spec.margin).contains(result.panelFrame))
  }

  func testSwitchesEdgeWhenPreferredPlacementWouldCoverTarget() throws {
    let target = candidate(rect: CGRect(x: 700, y: 830, width: 80, height: 36))
    let spec = SpatialOverlayPlacementSpec(
      overlaySize: CGSize(width: 330, height: 118),
      preferredEdges: [.above, .below],
      canCoverTarget: true
    )

    let result = try SpatialOverlayPlacementSolver.place(target: target, spec: spec).get()

    XCTAssertEqual(result.attachmentEdge, .below)
    XCTAssertEqual(result.globalArrowTip.x, target.targetPoint.x, accuracy: 0.1)
    XCTAssertEqual(result.globalArrowTip.y, target.targetPoint.y, accuracy: 0.1)
  }

  func testRectangularTargetCanBeAvoidedWithoutCoveringIt() throws {
    let target = candidate(rect: CGRect(x: 700, y: 420, width: 80, height: 36))
    let spec = SpatialOverlayPlacementSpec(
      overlaySize: CGSize(width: 330, height: 118),
      preferredEdges: [.above],
      canCoverTarget: false
    )

    let result = try SpatialOverlayPlacementSolver.place(target: target, spec: spec).get()

    XCTAssertEqual(result.attachmentEdge, .above)
    XCTAssertFalse(result.panelFrame.intersects(target.targetRect.insetBy(dx: -spec.avoidTargetPadding, dy: -spec.avoidTargetPadding)))
    XCTAssertEqual(result.globalArrowTip.x, target.targetPoint.x, accuracy: 0.1)
    XCTAssertEqual(result.globalArrowTip.y, target.targetRect.maxY, accuracy: 0.1)
  }

  func testFailsWhenClampingWouldDetachArrow() {
    let target = candidate(rect: CGRect(x: 12, y: 420, width: 20, height: 20))
    let spec = SpatialOverlayPlacementSpec(
      overlaySize: CGSize(width: 330, height: 118),
      preferredEdges: [.above]
    )

    let result = SpatialOverlayPlacementSolver.place(target: target, spec: spec)

    XCTAssertEqual(result.failure, .arrowCannotReachTargetAfterClamping)
  }

  func testArrowSizeConstrainsTipInset() throws {
    let target = candidate(rect: CGRect(x: 118, y: 420, width: 20, height: 20))
    let spec = SpatialOverlayPlacementSpec(
      overlaySize: CGSize(width: 330, height: 118),
      preferredEdges: [.above],
      margin: 12,
      arrowSize: CGSize(width: 96, height: 13),
      minimumArrowInset: 10,
      canCoverTarget: true
    )

    let result = try SpatialOverlayPlacementSolver.place(target: target, spec: spec).get()

    XCTAssertGreaterThanOrEqual(result.arrowTipInPanel.x, spec.arrowSize.width / 2)
  }

  func testCanUseTrailingPlacementNearLeftEdge() throws {
    let target = candidate(rect: CGRect(x: 18, y: 420, width: 20, height: 20))
    let spec = SpatialOverlayPlacementSpec(
      overlaySize: CGSize(width: 330, height: 118),
      preferredEdges: [.above, .trailing],
      canCoverTarget: true
    )

    let result = try SpatialOverlayPlacementSolver.place(target: target, spec: spec).get()

    XCTAssertEqual(result.attachmentEdge, .trailing)
    XCTAssertEqual(result.globalArrowTip.x, target.targetPoint.x, accuracy: 0.1)
    XCTAssertEqual(result.globalArrowTip.y, target.targetPoint.y, accuracy: 0.1)
  }

  func testScreenSelectionHandlesNegativeOriginDisplays() {
    let left = SpatialOverlayScreen(
      id: "left",
      frame: CGRect(x: -1280, y: 0, width: 1280, height: 800)
    )
    let main = SpatialOverlayScreen(
      id: "main",
      frame: CGRect(x: 0, y: 0, width: 1440, height: 900)
    )

    let selected = SpatialOverlayGeometry.screen(
      containing: CGRect(x: -900, y: 100, width: 400, height: 400),
      in: [main, left]
    )

    XCTAssertEqual(selected?.id, "left")
  }

  func testImageRectToWindowRectConvertsTopLeftPixelsToAppKitGlobal() {
    let windowFrame = CGRect(x: 100, y: 100, width: 800, height: 600)
    let imageRect = CGRect(x: 700, y: 540, width: 80, height: 40)

    let converted = SpatialOverlayGeometry.imageRectToWindowRect(
      imageRect,
      imageSize: CGSize(width: 800, height: 600),
      windowFrame: windowFrame
    )

    XCTAssertEqual(converted.minX, 800, accuracy: 0.1)
    XCTAssertEqual(converted.minY, 120, accuracy: 0.1)
    XCTAssertEqual(converted.width, 80, accuracy: 0.1)
    XCTAssertEqual(converted.height, 40, accuracy: 0.1)
  }

  func testHardExclusionRejectsCandidate() {
    let exclusion = SpatialOverlayExclusionZone(
      rect: CGRect(x: 520, y: 440, width: 400, height: 160),
      kind: .omiFloatingBar
    )
    let blockedScreen = SpatialOverlayScreen(
      id: "main",
      frame: screen.frame,
      visibleFrame: screen.visibleFrame,
      exclusionZones: [exclusion]
    )
    let target = candidate(
      rect: CGRect(x: 700, y: 420, width: 80, height: 36),
      screen: blockedScreen
    )
    let spec = SpatialOverlayPlacementSpec(
      overlaySize: CGSize(width: 330, height: 118),
      preferredEdges: [.above]
    )

    let result = SpatialOverlayPlacementSolver.place(target: target, spec: spec)

    XCTAssertEqual(result.failure, .blockedByRequiredExclusionZones)
  }

  private func candidate(
    rect: CGRect,
    screen: SpatialOverlayScreen? = nil
  ) -> SpatialOverlayAnchorCandidate {
    SpatialOverlayAnchorCandidate(
      id: "target",
      targetRect: rect,
      screen: screen ?? self.screen,
      evidence: [
        SpatialOverlayTargetEvidence(source: .layoutHeuristic, confidence: 0.7, label: "target")
      ],
      confidence: 0.7,
      allowedUses: [.displayGuidance]
    )
  }
}

extension Result {
  fileprivate var failure: Failure? {
    if case .failure(let error) = self {
      return error
    }
    return nil
  }
}
