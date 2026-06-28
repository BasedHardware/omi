import XCTest

@testable import Omi_Computer

final class SpatialOverlayDogfoodHarnessTests: XCTestCase {
  private let claudeScreenshotScreen = SpatialOverlayScreen(
    id: "claude-screenshot",
    frame: CGRect(x: 0, y: 0, width: 1510, height: 1596),
    visibleFrame: CGRect(x: 0, y: 0, width: 1510, height: 1596)
  )

  @MainActor
  func testClaudeAddGuidanceFixtureDoesNotCoverAddButton() throws {
    let windowFrame = claudeScreenshotScreen.frame
    let addButton = CGRect(x: 1_124, y: 246, width: 92, height: 54)
    let candidates = CloudConnectorFormAutomation.claudeAddGuidanceCandidates(
      windowFrame: windowFrame,
      explicitTargetFrames: [addButton]
    )

    let placement = try XCTUnwrap(CloudConnectorGuidanceOverlay.placementResult(
      windowFrame: windowFrame,
      candidates: candidates
    ))

    assertCallout(placement, pointsAt: addButton, doesNotCover: addButton)
  }

  @MainActor
  func testClaudeAddGuidanceFixtureFallsBackWithoutCoveringEstimatedButton() throws {
    let windowFrame = claudeScreenshotScreen.frame
    let candidates = CloudConnectorFormAutomation.claudeAddGuidanceCandidates(
      windowFrame: windowFrame,
      explicitTargetFrames: []
    )

    let placement = try XCTUnwrap(CloudConnectorGuidanceOverlay.placementResult(
      windowFrame: windowFrame,
      candidates: candidates
    ))

    let estimatedButton = try XCTUnwrap(candidates.first?.targetRect)
    assertCallout(placement, pointsAt: estimatedButton, doesNotCover: estimatedButton)
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
}
