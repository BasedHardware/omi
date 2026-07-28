import XCTest

@testable import Omi_Computer

final class SpatialOverlayDogfoodHarnessTests: XCTestCase {
  @MainActor
  func testClaudeAddGuidanceFixtureDoesNotCoverAddButton() throws {
    let fixture = SpatialOverlayDogfoodFixture.claudeAddExplicit
    let addButton = fixture.targetRect

    let placement = try XCTUnwrap(
      CloudConnectorGuidanceOverlay.placementResult(
        windowFrame: fixture.windowFrame,
        candidates: fixture.candidates
      ))

    assertCallout(placement, pointsAt: addButton, doesNotCover: addButton)
    assertTopLeftCallout(placement, fixture: fixture)
  }

  @MainActor
  func testClaudeAddGuidanceFixtureFallsBackWithoutCoveringEstimatedButton() throws {
    let fixture = SpatialOverlayDogfoodFixture.claudeAddHeuristic

    let placement = try XCTUnwrap(
      CloudConnectorGuidanceOverlay.placementResult(
        windowFrame: fixture.windowFrame,
        candidates: fixture.candidates
      ))

    let estimatedButton = try XCTUnwrap(fixture.candidates.first?.targetRect)
    assertCallout(placement, pointsAt: estimatedButton, doesNotCover: estimatedButton)
    assertTopLeftCallout(placement, fixture: fixture)
  }

  @MainActor
  func testClaudeAddGuidanceFixtureCanInferAddButtonFromCancel() throws {
    let fixture = SpatialOverlayDogfoodFixture.claudeAddInferredFromCancel

    let placement = try XCTUnwrap(
      CloudConnectorGuidanceOverlay.placementResult(
        windowFrame: fixture.windowFrame,
        candidates: fixture.candidates
      ))

    assertCallout(placement, pointsAt: fixture.targetRect, doesNotCover: fixture.targetRect)
    assertTopLeftCallout(placement, fixture: fixture)
  }

  func testClaudeAddButtonInferenceUsesCancelFooterGeometry() {
    let cancel = CGRect(x: 1_006, y: 1_296, width: 106, height: 54)
    let add = CloudConnectorFormAutomation.inferredClaudeAddButtonFrameFromCancel(cancel)

    XCTAssertEqual(add.minX, cancel.maxX + 12, accuracy: 0.1)
    XCTAssertEqual(add.midY, cancel.midY, accuracy: 0.1)
    XCTAssertEqual(add.height, cancel.height, accuracy: 0.1)
    XCTAssertGreaterThanOrEqual(add.width, 72)
    XCTAssertLessThanOrEqual(add.width, 96)
  }

  func testClaudeAddDogfoodWouldFailIfOverlayCoveredTarget() {
    let addButton = CGRect(x: 1_124, y: 246, width: 92, height: 54)
    let badPlacement = SpatialOverlayPlacementResult(
      panelFrame: CGRect(x: 890, y: 220, width: 330, height: 118),
      targetPoint: CGPoint(x: addButton.midX, y: addButton.minY),
      arrowTipInPanel: CGPoint(x: 280, y: 26),
      attachmentEdge: .below,
      score: 0,
      clampDelta: .zero,
      diagnostics: []
    )

    XCTAssertTrue(
      SpatialOverlayDogfoodOracle.issues(
        placement: badPlacement,
        targetRect: addButton
      ).contains(.panelCoversTarget)
    )
  }

  private func assertCallout(
    _ placement: SpatialOverlayPlacementResult,
    pointsAt target: CGRect,
    doesNotCover coveredTarget: CGRect,
    file: StaticString = #filePath,
    line: UInt = #line
  ) {
    let issues = SpatialOverlayDogfoodOracle.issues(
      placement: placement,
      targetRect: target,
      coveredTargetRect: coveredTarget
    )

    XCTAssertTrue(issues.isEmpty, "Dogfood overlay issues: \(issues)", file: file, line: line)
  }

  private func assertTopLeftCallout(
    _ placement: SpatialOverlayPlacementResult,
    fixture: SpatialOverlayDogfoodFixture,
    file: StaticString = #filePath,
    line: UInt = #line
  ) {
    let panel = fixture.topLeftRect(appKitRect: placement.panelFrame)
    let arrowTip = CGPoint(
      x: placement.globalArrowTip.x,
      y: fixture.windowFrame.maxY - placement.globalArrowTip.y
    )
    let target = fixture.topLeftTargetRect

    XCTAssertFalse(
      panel.intersects(target),
      "Expected top-left panel \(panel) not to cover target \(target)",
      file: file,
      line: line
    )
    XCTAssertTrue(
      target.insetBy(dx: -3, dy: -3).contains(arrowTip),
      "Expected top-left arrow tip \(arrowTip) to land on target \(target)",
      file: file,
      line: line
    )
  }
}
