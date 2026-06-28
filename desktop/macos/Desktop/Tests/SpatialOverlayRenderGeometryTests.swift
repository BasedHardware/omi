import XCTest

@testable import Omi_Computer

/// These tests close the gap that let the bad Claude-overlay screenshot ship while the
/// old harness stayed green: they validate the **rendered** arrow apex (the pixel the
/// user sees) and exercise the full accessibility→AppKit→solver→render pipeline against
/// an independent ground-truth Add-button rect, in one shared coordinate space.
final class SpatialOverlayRenderGeometryTests: XCTestCase {

  // MARK: Rendered apex matches solver intent on every edge

  func testRenderedArrowApexEqualsSolverGlobalArrowTipForEveryEdge() {
    let panelSize = CGSize(width: 330, height: 118)
    for edge in SpatialOverlayAttachmentEdge.allCases {
      // A representative panel anywhere on screen with the apex offset into the panel.
      let panelFrame = CGRect(x: 640, y: 410, width: panelSize.width, height: panelSize.height)
      let arrowTipInPanel: CGPoint
      switch edge {
      case .above: arrowTipInPanel = CGPoint(x: 165, y: 0)
      case .below: arrowTipInPanel = CGPoint(x: 165, y: panelSize.height)
      case .leading: arrowTipInPanel = CGPoint(x: panelSize.width, y: 59)
      case .trailing: arrowTipInPanel = CGPoint(x: 0, y: 59)
      }
      let placement = SpatialOverlayPlacementResult(
        panelFrame: panelFrame,
        targetPoint: .zero,
        arrowTipInPanel: arrowTipInPanel,
        attachmentEdge: edge,
        score: 0,
        clampDelta: .zero,
        diagnostics: []
      )
      let render = SpatialOverlayRenderGeometry(placement: placement, panelSize: panelSize)

      XCTAssertEqual(
        render.globalRenderedArrowTip.x, placement.globalArrowTip.x, accuracy: 0.001,
        "edge \(edge): rendered apex x drifted from solver target")
      XCTAssertEqual(
        render.globalRenderedArrowTip.y, placement.globalArrowTip.y, accuracy: 0.001,
        "edge \(edge): rendered apex y drifted from solver target")

      // The pointer triangle's apex vertex must coincide with the rendered tip.
      let apexVertex = apexVertex(of: render.pointerFrame, edge: edge)
      XCTAssertEqual(
        apexVertex.x, render.renderedArrowTip.x, accuracy: 0.001,
        "edge \(edge): triangle apex x not at rendered tip")
      XCTAssertEqual(
        apexVertex.y, render.renderedArrowTip.y, accuracy: 0.001,
        "edge \(edge): triangle apex y not at rendered tip")

      // The bubble must never overlap the arrow's tip pixel.
      XCTAssertFalse(
        render.bubbleFrame.contains(render.renderedArrowTip),
        "edge \(edge): bubble covers the arrow tip")
    }
  }

  /// Mirrors `TrianglePointer.path(in:)` — the vertex that should land on the target.
  private func apexVertex(of rect: CGRect, edge: SpatialOverlayAttachmentEdge) -> CGPoint {
    switch edge {
    case .above: return CGPoint(x: rect.midX, y: rect.maxY)
    case .below: return CGPoint(x: rect.midX, y: rect.minY)
    case .leading: return CGPoint(x: rect.maxX, y: rect.midY)
    case .trailing: return CGPoint(x: rect.minX, y: rect.midY)
    }
  }

  // MARK: Coordinate conversion uses the primary display as the flip reference

  func testGlobalTopLeftFlipUsesPrimaryReferenceNotContainingScreen() {
    // A secondary display to the right of and taller than the primary. A target on the
    // secondary must flip against the PRIMARY maxY, otherwise the panel lands at the
    // wrong absolute Y (the multi-monitor variant of the bad screenshot).
    let primaryMaxY: CGFloat = 982
    let secondaryScreenFrame = CGRect(x: 1512, y: -200, width: 1920, height: 1200)

    let targetTopLeft = CGRect(x: 1800, y: 300, width: 100, height: 40)

    let correct = SpatialOverlayGeometry.appKitFrame(
      topLeftOrigin: targetTopLeft.origin, size: targetTopLeft.size, flipMaxY: primaryMaxY)
    let buggyContainingScreenFlip = SpatialOverlayGeometry.appKitFrame(
      topLeftOrigin: targetTopLeft.origin, size: targetTopLeft.size,
      screenFrame: secondaryScreenFrame)

    XCTAssertEqual(correct.minY, primaryMaxY - 300 - 40, accuracy: 0.001)
    XCTAssertNotEqual(
      correct.minY, buggyContainingScreenFlip.minY,
      "primary-reference flip must differ from the old containing-screen flip on a secondary display")
  }

  // MARK: Full pipeline against an independent, screenshot-derived Add rect

  @MainActor
  func testRealisticClaudeAddScreenshotApexLandsOnIndependentGroundTruth() {
    let scene = RealisticClaudeAddScene()

    // Build candidates through the real code path, with the explicit Add frame the page
    // would expose (converted to AppKit exactly as the live code does).
    let candidates = CloudConnectorFormAutomation.claudeAddGuidanceCandidates(
      windowFrame: scene.windowAppKit,
      explicitTargetFrames: [scene.addButtonAppKit]
    )
    let placement = CloudConnectorGuidanceOverlay.placementResult(
      windowFrame: scene.windowAppKit,
      candidates: candidates
    )
    let unwrapped = try? XCTUnwrap(placement)
    guard let placement = unwrapped else { return }

    let render = SpatialOverlayRenderGeometry(
      placement: placement, panelSize: CGSize(width: 330, height: 118))

    // Convert the rendered apex back to the screenshot's top-left space and assert it
    // lands on the INDEPENDENT ground-truth Add rect (not the solver's own target).
    let apexTopLeft = scene.toTopLeft(render.globalRenderedArrowTip)
    XCTAssertTrue(
      scene.addButtonTopLeft.insetBy(dx: -3, dy: -3).contains(apexTopLeft),
      "rendered apex \(apexTopLeft) must land on the real Add button \(scene.addButtonTopLeft)")

    // The bubble must not cover the Add button (touching its top edge is allowed).
    let panelTopLeft = scene.toTopLeftRect(placement.panelFrame)
    XCTAssertFalse(
      panelTopLeft.intersects(scene.addButtonTopLeft),
      "bubble \(panelTopLeft) must not cover the Add button \(scene.addButtonTopLeft)")
  }

  func testRealisticSceneFailsWhenApexIsBelowTheButton() {
    // Regression guard: a placement whose apex sits below the footer (the exact bad
    // screenshot) must be reported as an issue.
    let scene = RealisticClaudeAddScene()
    let belowFooterTopLeft = CGPoint(
      x: scene.addButtonTopLeft.midX, y: scene.addButtonTopLeft.maxY + 90)
    let badApex = scene.toAppKit(belowFooterTopLeft)
    let panel = CGRect(
      x: scene.addButtonAppKit.midX - 165, y: badApex.y - 118, width: 330, height: 118)

    let issues = SpatialOverlayDogfoodOracle.issues(
      arrowTip: badApex,
      panelFrame: panel,
      targetRect: scene.addButtonAppKit
    )
    XCTAssertTrue(
      issues.contains(where: { if case .arrowMissesTarget = $0 { return true } else { return false } }),
      "an apex below the button must be flagged as arrowMissesTarget")
  }
}

/// A deterministic stand-in for a real laptop screenshot of Claude's "Add custom
/// connector" modal. All rects are authored in top-left (screenshot) coordinates and
/// converted with a fixed flip reference so the test is independent of the test
/// runner's actual displays.
private struct RealisticClaudeAddScene {
  /// MacBook 14" "More Space" logical height; the flip reference for the primary display.
  let primaryMaxY: CGFloat = 982

  /// Browser window, top-left global coords (not at the origin — exercises the offset).
  let windowTopLeft = CGRect(x: 200, y: 80, width: 1100, height: 820)

  /// INDEPENDENT ground truth: where the Add button actually is in the screenshot.
  let addButtonTopLeft = CGRect(x: 1140, y: 720, width: 92, height: 44)

  var windowAppKit: CGRect { toAppKitRect(windowTopLeft) }
  var addButtonAppKit: CGRect { toAppKitRect(addButtonTopLeft) }

  func toAppKitRect(_ rect: CGRect) -> CGRect {
    SpatialOverlayGeometry.appKitFrame(
      topLeftOrigin: rect.origin, size: rect.size, flipMaxY: primaryMaxY)
  }

  func toTopLeftRect(_ appKit: CGRect) -> CGRect {
    CGRect(x: appKit.minX, y: primaryMaxY - appKit.maxY, width: appKit.width, height: appKit.height)
  }

  func toTopLeft(_ appKit: CGPoint) -> CGPoint {
    CGPoint(x: appKit.x, y: primaryMaxY - appKit.y)
  }

  func toAppKit(_ topLeft: CGPoint) -> CGPoint {
    CGPoint(x: topLeft.x, y: primaryMaxY - topLeft.y)
  }
}
