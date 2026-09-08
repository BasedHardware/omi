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

  func testRenderGeometryUsesPlacementArrowSize() {
    let placement = SpatialOverlayPlacementResult(
      panelFrame: CGRect(x: 100, y: 100, width: 240, height: 120),
      targetPoint: .zero,
      arrowTipInPanel: CGPoint(x: 120, y: 0),
      arrowSize: CGSize(width: 48, height: 24),
      attachmentEdge: .above,
      score: 0,
      clampDelta: .zero,
      diagnostics: []
    )

    let render = SpatialOverlayRenderGeometry(
      placement: placement,
      panelSize: CGSize(width: 240, height: 120)
    )

    XCTAssertEqual(render.pointerFrame.width, 48, accuracy: 0.001)
    XCTAssertEqual(render.pointerFrame.height, 24, accuracy: 0.001)
    XCTAssertEqual(render.bubbleFrame.height, 88, accuracy: 0.001)
  }

  func testPlacementCapsArrowInsetForTinyPanels() throws {
    let screen = SpatialOverlayScreen(
      id: "tiny", frame: CGRect(x: 0, y: 0, width: 320, height: 240),
      visibleFrame: CGRect(x: 0, y: 0, width: 320, height: 240))
    let candidate = SpatialOverlayAnchorCandidate(
      id: "tiny-add",
      targetRect: CGRect(x: 110, y: 100, width: 20, height: 20),
      screen: screen,
      evidence: [SpatialOverlayTargetEvidence(source: .layoutHeuristic, confidence: 0.9)],
      confidence: 0.9,
      allowedUses: [.displayGuidance])

    let placement = try SpatialOverlayPlacementSolver.place(
      target: candidate,
      spec: SpatialOverlayPlacementSpec(
        overlaySize: CGSize(width: 42, height: 34),
        preferredEdges: [.above],
        margin: 0,
        arrowSize: CGSize(width: 96, height: 28),
        minimumArrowInset: 60,
        canCoverTarget: true)
    ).get()

    XCTAssertGreaterThanOrEqual(placement.arrowTipInPanel.x, 0)
    XCTAssertLessThanOrEqual(placement.arrowTipInPanel.x, placement.panelFrame.width)
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
      "primary-reference flip must differ from the old containing-screen flip on a secondary display"
    )
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

  // MARK: Located-modal fallback (AX blind to the Add/Cancel buttons)

  func testClaudeModalRectUnionsLocatedFieldFramesAndRejectsTooFew() {
    let fields = [
      CGRect(x: 310, y: 420, width: 970, height: 56),  // Name
      CGRect(x: 310, y: 510, width: 970, height: 56),  // URL
      CGRect(x: 310, y: 680, width: 970, height: 56),  // client id
    ]
    let rect = CloudConnectorFormAutomation.claudeModalRect(fromFieldFrames: fields)
    XCTAssertEqual(rect?.minX, 310)
    XCTAssertEqual(rect?.maxX, 1280)
    XCTAssertEqual(rect?.minY, 420)
    XCTAssertEqual(rect?.maxY, 736)
    XCTAssertNil(CloudConnectorFormAutomation.claudeModalRect(fromFieldFrames: [fields[0]]))
  }

  func testFooterFallbackAnchorsModalBottomRightAndStaysInsideWindow() {
    let window = CGRect(x: 200, y: 80, width: 1100, height: 820)
    let modal = CGRect(x: 310, y: 420, width: 970, height: 316)  // top-left
    let target = CloudConnectorFormAutomation.claudeAddFallbackFooterTarget(
      modalTopLeft: modal, window: window)
    let footer = try! XCTUnwrap(target)
    // Footer hugs the modal's bottom-right.
    XCTAssertEqual(footer.rect.maxX, modal.maxX, accuracy: 0.001)
    XCTAssertGreaterThanOrEqual(footer.rect.minY, modal.maxY - 0.001)
    // Stays inside the window (never off-screen dead space — the old bug).
    XCTAssertLessThanOrEqual(footer.rect.maxY, window.maxY + 0.001)
    XCTAssertTrue(footer.rect.contains(footer.point))
  }

  /// The exact scenario from the bad screenshot: AX exposes the modal's fields but NOT
  /// the Add/Cancel buttons. The arrow must land on the located modal footer and the
  /// bubble must not cover the modal — never point into the dead space below the window.
  @MainActor
  func testBlindClaudeAddApexLandsOnLocatedModalFooterNotBelowWindow() {
    let flip: CGFloat = 982
    let window = CGRect(x: 160, y: 60, width: 1200, height: 860)  // top-left
    let modal = CGRect(x: 430, y: 260, width: 660, height: 420)  // located via fields

    let footer = try! XCTUnwrap(
      CloudConnectorFormAutomation.claudeAddFallbackFooterTarget(
        modalTopLeft: modal, window: window))

    func toAppKitRect(_ r: CGRect) -> CGRect {
      SpatialOverlayGeometry.appKitFrame(topLeftOrigin: r.origin, size: r.size, flipMaxY: flip)
    }
    func toAppKitPoint(_ p: CGPoint) -> CGPoint { CGPoint(x: p.x, y: flip - p.y) }

    let candidate = SpatialOverlayAnchorCandidate(
      id: "claude-add-modal-footer",
      targetRect: toAppKitRect(footer.rect),
      targetPoint: toAppKitPoint(footer.point),
      screen: SpatialOverlayScreen(
        id: "w", frame: toAppKitRect(window), visibleFrame: toAppKitRect(window),
        exclusionZones: [
          SpatialOverlayExclusionZone(rect: toAppKitRect(modal), kind: .targetWindowChrome)
        ]),
      window: SpatialOverlayWindow(id: "w", frame: toAppKitRect(window)),
      evidence: [SpatialOverlayTargetEvidence(source: .layoutHeuristic, confidence: 0.55)],
      confidence: 0.55,
      allowedUses: [.displayGuidance])

    let placement = try! XCTUnwrap(
      CloudConnectorGuidanceOverlay.placementResult(
        windowFrame: toAppKitRect(window), candidates: [candidate]))
    let render = SpatialOverlayRenderGeometry(
      placement: placement, panelSize: CGSize(width: 330, height: 118))

    // Apex back in top-left space.
    let apex = CGPoint(
      x: render.globalRenderedArrowTip.x, y: flip - render.globalRenderedArrowTip.y)
    XCTAssertTrue(
      footer.rect.insetBy(dx: -3, dy: -3).contains(apex),
      "apex \(apex) must land on the located modal footer \(footer.rect)")
    // Never below the window (the bad-screenshot symptom).
    XCTAssertLessThanOrEqual(apex.y, window.maxY, "apex must not be below the window")
    // Bubble must not cover the modal body.
    let panelTopLeft = CGRect(
      x: placement.panelFrame.minX, y: flip - placement.panelFrame.maxY,
      width: placement.panelFrame.width, height: placement.panelFrame.height)
    XCTAssertFalse(panelTopLeft.intersects(modal), "bubble must not cover the modal body")
  }

  // MARK: Screen Recording fallback instruction card

  @MainActor
  func testInstructionCardUsesCompactHeightForShortClaudeGuidance() {
    let compact = CloudConnectorGuidanceOverlay.instructionCardSize(
      title: "Finish in Claude",
      subtitle: "Click Add in the connector window to finish creating the Omi connector."
    )
    let expanded = CloudConnectorGuidanceOverlay.instructionCardSize(
      title: "Allow Screen Recording for Omi",
      subtitle:
        "Flip the Omi toggle on under Screen & System Audio Recording, then return to Claude and click Add."
    )

    XCTAssertEqual(compact.width, 420)
    XCTAssertEqual(compact.height, 88)
    XCTAssertEqual(expanded.width, 420)
    XCTAssertEqual(expanded.height, 118)
  }

  @MainActor
  func testInstructionCardCentersOnAnchorAndStaysOnScreen() {
    let visible = CGRect(x: 0, y: 0, width: 1512, height: 950)
    let settingsWindow = CGRect(x: 380, y: 120, width: 760, height: 700)
    let card = CGSize(width: 380, height: 96)

    let frame = CloudConnectorGuidanceOverlay.instructionCardFrame(
      anchor: settingsWindow, cardSize: card, visibleFrame: visible)
    // Horizontally centered on the settings window.
    XCTAssertEqual(frame.midX, settingsWindow.midX, accuracy: 0.5)
    // Near the window's top edge (AppKit maxY) and fully on screen.
    XCTAssertLessThanOrEqual(frame.maxY, visible.maxY - 12 + 0.5)
    XCTAssertGreaterThanOrEqual(frame.minX, visible.minX)
    XCTAssertLessThanOrEqual(frame.maxX, visible.maxX)
    XCTAssertEqual(frame.size, card)
  }

  @MainActor
  func testInstructionCardWithoutAnchorStaysWithinVisibleFrame() {
    let visible = CGRect(x: 100, y: 50, width: 1000, height: 800)
    let card = CGSize(width: 380, height: 96)
    let frame = CloudConnectorGuidanceOverlay.instructionCardFrame(
      anchor: nil, cardSize: card, visibleFrame: visible)
    XCTAssertGreaterThanOrEqual(frame.minX, visible.minX)
    XCTAssertLessThanOrEqual(frame.maxX, visible.maxX)
    XCTAssertGreaterThanOrEqual(frame.minY, visible.minY)
    XCTAssertLessThanOrEqual(frame.maxY, visible.maxY)
  }

  @MainActor
  func testFieldCopyCardUsesTallerHeaderForLongSubtitle() {
    let compact = CloudConnectorGuidanceOverlay.fieldCopyCardSize(
      title: "Finish in ChatGPT",
      subtitle: "Copy each value into the connector form.",
      fieldCount: 7
    )
    let expanded = CloudConnectorGuidanceOverlay.fieldCopyCardSize(
      title: "Finish in ChatGPT",
      subtitle:
        "Turn on Developer mode in Settings → Apps, then copy each value into the connector form.",
      fieldCount: 7
    )

    XCTAssertEqual(compact.width, 460)
    XCTAssertEqual(compact.height, 96 + 7 * 30)
    XCTAssertEqual(expanded.width, 460)
    XCTAssertEqual(expanded.height, 118 + 7 * 30)
    XCTAssertGreaterThan(expanded.height, compact.height)
  }

  func testCopyFieldMasksCommonSensitiveLabels() {
    XCTAssertTrue(
      CloudConnectorCopyField(id: "secret", label: "OAuth Client Secret", value: "abc").masksValue)
    XCTAssertTrue(CloudConnectorCopyField(id: "key", label: "API Key", value: "abc").masksValue)
    XCTAssertTrue(
      CloudConnectorCopyField(id: "token", label: "Access Token", value: "abc").masksValue)
    XCTAssertFalse(
      CloudConnectorCopyField(id: "empty", label: "OAuth Client Secret", value: "").masksValue)
    XCTAssertFalse(
      CloudConnectorCopyField(id: "name", label: "Name", value: "Omi Memory").masksValue)
    XCTAssertEqual(
      CloudConnectorCopyField(id: "key2", label: "API Key", value: "secret").displayValue,
      String(repeating: "•", count: 12))
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
      issues.contains(where: {
        if case .arrowMissesTarget = $0 { return true } else { return false }
      }),
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
