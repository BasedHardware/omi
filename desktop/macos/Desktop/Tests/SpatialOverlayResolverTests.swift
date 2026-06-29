import XCTest

@testable import Omi_Computer

final class SpatialOverlayResolverTests: XCTestCase {
  private let screen = SpatialOverlayScreen(
    id: "main",
    frame: CGRect(x: 0, y: 0, width: 1440, height: 900),
    visibleFrame: CGRect(x: 0, y: 24, width: 1440, height: 876)
  )

  func testResolverPrefersAccessibilityCandidateOverHeuristicForGuidance() throws {
    let explicit = candidate(
      id: "add-ax",
      rect: CGRect(x: 1180, y: 160, width: 80, height: 36),
      source: .accessibility,
      confidence: 0.95,
      uses: [.displayGuidance, .performClick]
    )
    let heuristic = candidate(
      id: "add-heuristic",
      rect: CGRect(x: 1190, y: 162, width: 2, height: 2),
      source: .layoutHeuristic,
      confidence: 0.99,
      uses: [.displayGuidance]
    )
    let snapshot = SpatialOverlayDesktopSnapshot(
      screens: [screen], candidates: [heuristic, explicit])

    let resolution = try SpatialOverlayAnchorResolver()
      .resolve(
        SpatialOverlayAnchorSpec(
          id: "claude.add.guidance", use: .displayGuidance, minimumConfidence: 0.5),
        in: snapshot
      )
      .get()

    XCTAssertEqual(resolution.candidate.id, "add-ax")
  }

  func testResolverAppliesConfidenceThresholdBeforeSourceRanking() throws {
    let lowConfidenceAX = candidate(
      id: "add-ax-low",
      rect: CGRect(x: 1180, y: 160, width: 80, height: 36),
      source: .accessibility,
      confidence: 0.2,
      uses: [.displayGuidance, .performClick]
    )
    let goodHeuristic = candidate(
      id: "add-heuristic-good",
      rect: CGRect(x: 1190, y: 162, width: 2, height: 2),
      source: .layoutHeuristic,
      confidence: 0.9,
      uses: [.displayGuidance]
    )
    let snapshot = SpatialOverlayDesktopSnapshot(
      screens: [screen], candidates: [lowConfidenceAX, goodHeuristic])

    let resolution = try SpatialOverlayAnchorResolver()
      .resolve(
        SpatialOverlayAnchorSpec(
          id: "claude.add.guidance", use: .displayGuidance, minimumConfidence: 0.5),
        in: snapshot
      )
      .get()

    XCTAssertEqual(resolution.candidate.id, "add-heuristic-good")
  }

  func testResolverRejectsHeuristicForClickUse() {
    let heuristic = candidate(
      id: "add-heuristic",
      rect: CGRect(x: 1190, y: 162, width: 2, height: 2),
      source: .layoutHeuristic,
      confidence: 0.99,
      uses: [.displayGuidance, .performClick]
    )
    let snapshot = SpatialOverlayDesktopSnapshot(screens: [screen], candidates: [heuristic])

    let result = SpatialOverlayAnchorResolver()
      .resolve(
        SpatialOverlayAnchorSpec(
          id: "claude.add.click", use: .performClick, minimumConfidence: 0.95),
        in: snapshot
      )

    XCTAssertEqual(result.failure, .noCandidateAllowedForUse(.performClick))
  }

  func testStaticProviderFiltersCandidatesByRequestedAnchorTokenBeforeRanking() throws {
    let connect = candidate(
      id: "claude-connect-ocr",
      rect: CGRect(x: 1020, y: 260, width: 120, height: 44),
      source: .ocr,
      confidence: 0.97,
      uses: [.displayGuidance, .performClick]
    )
    let add = candidate(
      id: "claude-add-explicit-0",
      rect: CGRect(x: 1180, y: 160, width: 80, height: 36),
      source: .accessibility,
      confidence: 0.91,
      uses: [.displayGuidance, .performClick]
    )
    let snapshot = SpatialOverlayDesktopSnapshot(screens: [screen], candidates: [connect, add])

    let resolution = try SpatialOverlayAnchorResolver()
      .resolve(
        SpatialOverlayAnchorSpec(
          id: "claude.add.guidance", use: .displayGuidance, minimumConfidence: 0.5),
        in: snapshot
      )
      .get()

    XCTAssertEqual(resolution.candidate.id, "claude-add-explicit-0")
  }

  func testReplayFixturePlacesCalloutWithArrowTipOnResolvedTarget() throws {
    let target = candidate(
      id: "connect-ocr",
      rect: CGRect(x: 1080, y: 420, width: 120, height: 44),
      source: .ocr,
      confidence: 0.91,
      uses: [.displayGuidance, .performClick]
    )
    let fixture = SpatialOverlayReplayFixture(
      id: "claude-connect-detail",
      snapshot: SpatialOverlayDesktopSnapshot(screens: [screen], candidates: [target]),
      placementSpec: SpatialOverlayPlacementSpec(
        overlaySize: CGSize(width: 330, height: 118),
        preferredEdges: [.above, .below, .trailing, .leading],
        canCoverTarget: true
      )
    )

    let placement = try fixture.place(
      SpatialOverlayAnchorSpec(
        id: "claude.connect.guidance", use: .displayGuidance, minimumConfidence: 0.5)
    ).get()

    XCTAssertEqual(placement.globalArrowTip.x, target.targetPoint.x, accuracy: 3)
    XCTAssertEqual(placement.globalArrowTip.y, target.targetPoint.y, accuracy: 3)
  }

  private func candidate(
    id: String,
    rect: CGRect,
    source: SpatialOverlayTargetSource,
    confidence: Double,
    uses: Set<SpatialOverlayAnchorUse>
  ) -> SpatialOverlayAnchorCandidate {
    SpatialOverlayAnchorCandidate(
      id: id,
      targetRect: rect,
      screen: screen,
      evidence: [
        SpatialOverlayTargetEvidence(source: source, confidence: confidence, label: id)
      ],
      confidence: confidence,
      allowedUses: uses
    )
  }
}

extension Result {
  fileprivate var failure: Failure? {
    if case .failure(let failure) = self {
      return failure
    }
    return nil
  }
}
