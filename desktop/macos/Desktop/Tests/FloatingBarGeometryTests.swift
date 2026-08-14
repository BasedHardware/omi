import AppKit
import XCTest

@testable import Omi_Computer

@MainActor
final class FloatingBarGeometryTests: XCTestCase {
  private let visibleFrame = NSRect(x: 0, y: 0, width: 1440, height: 900)
  private let compactSize = NSSize(width: 40, height: 14)
  private let voiceSize = NSSize(width: 224, height: 42)
  private let topInset: CGFloat = 40

  func testDefaultPillFrameIsTopCenteredInVisibleFrame() {
    let frame = FloatingControlBarGeometry.defaultPillFrame(
      size: compactSize,
      visibleFrame: visibleFrame,
      topInset: topInset
    )

    XCTAssertEqual(frame.origin.x, 700)
    XCTAssertEqual(frame.origin.y, 846)
    XCTAssertEqual(frame.size, compactSize)
  }

  func testDraggableBarForcesPillPresentationOnNotchedDisplays() {
    XCTAssertFalse(
      FloatingControlBarWindow.shouldUseNotchIsland(
        displayHasCameraHousing: true,
        hasActiveIsland: false,
        draggableBarEnabled: true
      )
    )
    XCTAssertFalse(
      FloatingControlBarWindow.shouldUseNotchIsland(
        displayHasCameraHousing: true,
        hasActiveIsland: true,
        draggableBarEnabled: true
      )
    )
    XCTAssertTrue(
      FloatingControlBarWindow.shouldUseNotchIsland(
        displayHasCameraHousing: true,
        hasActiveIsland: false,
        draggableBarEnabled: false
      )
    )
  }

  func testGlowInflatedRestoreRoundTripPreservesCenterOnlyWithMatchingSize() {
    let center = NSPoint(x: 700, y: 820)
    // The restore origin is computed for the glow-INFLATED window (bare 40x14
    // pill grown by the 22/18 glow outsets → 84x50).
    let inflated = NSSize(width: 84, height: 50)
    let origin = FloatingControlBarGeometry.restoreOrigin(center: center, size: inflated)

    // Fixed: snap with the SAME inflated size the origin was computed for →
    // the recorded center is exactly the original center.
    XCTAssertEqual(
      FloatingControlBarGeometry.recordedCenter(afterSnapOrigin: origin, size: inflated),
      center)

    // Bug: snapping with the bare pill size drifts the recorded center by one
    // glow outset (22 left, 18 down) — this is what compounded per re-open cycle.
    let bare = NSSize(width: 40, height: 14)
    XCTAssertEqual(
      FloatingControlBarGeometry.recordedCenter(afterSnapOrigin: origin, size: bare),
      NSPoint(x: center.x - 22, y: center.y - 18))
  }

  func testScreenChangeReconcilesTheFloatingBarPresentationAndFrame() throws {
    // omi-test-quality: source-inspection -- static contract: AppKit delegate callback must retain the reconciliation wiring
    let source = try String(
      contentsOf: URL(fileURLWithPath: #filePath)
        .deletingLastPathComponent()
        .deletingLastPathComponent()
        .appendingPathComponent("Sources/FloatingControlBar/FloatingControlBarWindow.swift"),
      encoding: .utf8
    )
    guard let methodStart = source.range(of: "func windowDidChangeScreen(_ notification: Notification)") else {
      return XCTFail("Expected the floating bar to reconcile direct window screen changes")
    }
    guard let nextMethod = source.range(of: "func windowDidResignKey", range: methodStart.upperBound..<source.endIndex)
    else {
      return XCTFail("Expected windowDidChangeScreen to precede the next window delegate method")
    }

    let method = String(source[methodStart.lowerBound..<nextMethod.lowerBound])
    XCTAssertTrue(method.contains("let previousUsesNotchIsland = state.usesNotchIsland"))
    XCTAssertTrue(method.contains("updateNotchIslandState()"))
    XCTAssertTrue(method.contains("guard !state.showingAIConversation else { return }"))
    XCTAssertTrue(method.contains("frameForCurrentState(on: screen, usesNotchIsland: state.usesNotchIsland)"))
    XCTAssertTrue(method.contains("resizeToFrame("))
  }

  func testTopCenterExpansionKeepsTopEdgeAndHorizontalCenterFixed() {
    let compactFrame = NSRect(x: 586, y: 876, width: 268, height: 58)
    let expandedFrame = FloatingControlBarGeometry.topCenterAnchoredFrame(
      currentFrame: compactFrame,
      targetSize: NSSize(width: 430, height: 110)
    )

    XCTAssertEqual(expandedFrame.midX, compactFrame.midX)
    XCTAssertEqual(expandedFrame.maxY, compactFrame.maxY)
    XCTAssertEqual(expandedFrame.size, NSSize(width: 430, height: 110))
  }

  func testNotchTransitionIgnoresTransientPTTOffset() {
    let displayFrame = NSRect(x: 0, y: 0, width: 1710, height: 1107)
    let transientPTTFrame = NSRect(x: 716, y: 1049, width: 351, height: 58)

    let agentListFrame = FloatingControlBarGeometry.topAnchoredFrame(
      currentFrame: transientPTTFrame,
      targetSize: NSSize(width: 430, height: 338),
      screenFrame: displayFrame,
      pinsToScreenCenter: true
    )
    let collapsedFrame = FloatingControlBarGeometry.topAnchoredFrame(
      currentFrame: transientPTTFrame,
      targetSize: transientPTTFrame.size,
      screenFrame: displayFrame,
      pinsToScreenCenter: true
    )

    XCTAssertNotEqual(transientPTTFrame.midX, displayFrame.midX)
    XCTAssertEqual(agentListFrame.midX, displayFrame.midX)
    XCTAssertEqual(collapsedFrame.origin.x, 680)
    XCTAssertLessThanOrEqual(abs(collapsedFrame.midX - displayFrame.midX), 0.5)
  }

  func testNotchSurfaceStateSequenceStaysCenteredAndTopAnchoredOnOffsetDisplay() {
    let screenFrame = NSRect(x: 1920, y: -100, width: 1728, height: 1117)
    let shiftedTransientFrame = NSRect(x: 2637, y: 959, width: 351, height: 58)
    let glowOutset = NSSize(
      width: FloatingControlBarWindow.notchGlowOutsetX * 2,
      height: FloatingControlBarWindow.notchGlowOutsetBottom
    )
    let pttSurfaceSize = NSSize(
      width: FloatingControlBarWindow.notchHiddenCenterWidth
        + FloatingControlBarWindow.notchActiveSideWidth * 2,
      height: FloatingControlBarWindow.notchChromeHeight
    )
    let agentListSurfaceSize = NSSize(
      width: FloatingControlBarWindow.notchExpandedWidth,
      height: FloatingControlBarWindow.notchChromeHeight
        + FloatingControlBarWindow.notchHoverMenuHeight(agentCount: 3)
    )
    let collapsedSurfaceSize = NSSize(
      width: FloatingControlBarWindow.notchHiddenCenterWidth
        + FloatingControlBarWindow.notchCompactSideWidth * 2,
      height: FloatingControlBarWindow.notchChromeHeight
    )
    func windowSize(_ surfaceSize: NSSize) -> NSSize {
      NSSize(
        width: surfaceSize.width + glowOutset.width,
        height: surfaceSize.height + glowOutset.height
      )
    }

    let placement = FloatingControlBarGeometry.SurfacePlacement.notch(screenFrame: screenFrame)
    let pttFrame = FloatingControlBarGeometry.surfaceTransitionFrame(
      currentFrame: shiftedTransientFrame,
      targetSize: windowSize(pttSurfaceSize),
      transition: .pushToTalk(expanded: true),
      placement: placement
    )
    let agentListFrame = FloatingControlBarGeometry.surfaceTransitionFrame(
      currentFrame: pttFrame,
      targetSize: windowSize(agentListSurfaceSize),
      transition: .agentSwitcher(visible: true),
      placement: placement
    )
    let collapsedFrame = FloatingControlBarGeometry.surfaceTransitionFrame(
      currentFrame: agentListFrame,
      targetSize: windowSize(collapsedSurfaceSize),
      transition: .agentSwitcher(visible: false),
      placement: placement
    )

    XCTAssertNotEqual(shiftedTransientFrame.midX, screenFrame.midX)
    XCTAssertEqual(pttFrame.size, windowSize(pttSurfaceSize))
    XCTAssertEqual(agentListFrame.size, windowSize(agentListSurfaceSize))
    XCTAssertEqual(collapsedFrame.size, windowSize(collapsedSurfaceSize))
    for frame in [pttFrame, agentListFrame, collapsedFrame] {
      XCTAssertEqual(frame.midX, screenFrame.midX, accuracy: 0.5)
      XCTAssertEqual(frame.maxY, screenFrame.maxY)
    }
  }

  func testNotchIslandExpansionRecentersShiftedPanelOnDisplay() {
    let shiftedFrame = NSRect(x: 606, y: 876, width: 268, height: 58)
    let expandedFrame = FloatingControlBarGeometry.topAnchoredFrame(
      currentFrame: shiftedFrame,
      targetSize: NSSize(width: 430, height: 110),
      screenFrame: visibleFrame,
      pinsToScreenCenter: true
    )

    XCTAssertEqual(shiftedFrame.midX, 740)
    XCTAssertEqual(expandedFrame.midX, visibleFrame.midX)
    XCTAssertEqual(expandedFrame.maxY, visibleFrame.maxY)
    XCTAssertEqual(expandedFrame.size, NSSize(width: 430, height: 110))
  }

  func testChatAndHoverKeepNotchControlsAtCompactHeaderWidth() {
    let compactChromeWidth: CGFloat = 268
    let expandedSurfaceWidth: CGFloat = 900

    for hoverProgress in [CGFloat(0), 0.5, 1] {
      for isChatPresented in [false, true] {
        XCTAssertEqual(
          NotchChromeLayout.width(
            chromeWidth: compactChromeWidth,
            expandedWidth: expandedSurfaceWidth,
            switcherProgress: hoverProgress,
            isChatPresented: isChatPresented
          ),
          compactChromeWidth
        )
      }
    }
  }

  func testRestoringVisibleChatAlsoPinsNotchControls() {
    XCTAssertTrue(
      NotchChromeLayout.isChatPinned(
        showingAIConversation: false,
        hasVisibleConversation: true
      )
    )
    XCTAssertEqual(
      NotchChromeLayout.width(
        chromeWidth: 268,
        expandedWidth: 1_200,
        switcherProgress: 1,
        isChatPresented: NotchChromeLayout.isChatPinned(
          showingAIConversation: false,
          hasVisibleConversation: true
        )
      ),
      268
    )
  }

  func testPTTExpansionKeepsCompactPillCenter() {
    let compactFrame = FloatingControlBarGeometry.defaultPillFrame(
      size: compactSize,
      visibleFrame: visibleFrame,
      topInset: topInset
    )

    let voiceFrame = FloatingControlBarGeometry.pushToTalkFrame(
      currentFrame: compactFrame,
      expanded: true,
      draggable: false,
      visibleFrame: visibleFrame,
      topInset: topInset,
      compactSize: compactSize,
      voiceSize: voiceSize
    )

    XCTAssertEqual(voiceFrame.midX, compactFrame.midX)
    XCTAssertEqual(voiceFrame.midY, compactFrame.midY)
    XCTAssertEqual(voiceFrame.size, voiceSize)
  }

  func testPTTExpansionIgnoresTransientFrameWhenDraggingDisabled() {
    let notificationFrame = NSRect(x: 505, y: 738, width: 430, height: 122)

    let voiceFrame = FloatingControlBarGeometry.pushToTalkFrame(
      currentFrame: notificationFrame,
      expanded: true,
      draggable: false,
      visibleFrame: visibleFrame,
      topInset: topInset,
      compactSize: compactSize,
      voiceSize: voiceSize
    )

    XCTAssertEqual(voiceFrame.origin.x, 608)
    XCTAssertEqual(voiceFrame.origin.y, 832)
    XCTAssertEqual(voiceFrame.size, voiceSize)
  }

  func testPTTCollapseSnapsToDefaultWhenDraggingDisabled() {
    let shiftedVoiceFrame = NSRect(x: 612, y: 832, width: voiceSize.width, height: voiceSize.height)

    let collapsedFrame = FloatingControlBarGeometry.pushToTalkFrame(
      currentFrame: shiftedVoiceFrame,
      expanded: false,
      draggable: false,
      visibleFrame: visibleFrame,
      topInset: topInset,
      compactSize: compactSize,
      voiceSize: voiceSize
    )

    XCTAssertEqual(collapsedFrame.origin.x, 700)
    XCTAssertEqual(collapsedFrame.origin.y, 846)
    XCTAssertEqual(collapsedFrame.size, compactSize)
  }

  func testPTTCollapsePreservesUserCenterWhenDraggingEnabled() {
    let shiftedVoiceFrame = NSRect(x: 612, y: 832, width: voiceSize.width, height: voiceSize.height)

    let collapsedFrame = FloatingControlBarGeometry.pushToTalkFrame(
      currentFrame: shiftedVoiceFrame,
      expanded: false,
      draggable: true,
      visibleFrame: visibleFrame,
      topInset: topInset,
      compactSize: compactSize,
      voiceSize: voiceSize
    )

    XCTAssertEqual(collapsedFrame.midX, shiftedVoiceFrame.midX)
    XCTAssertEqual(collapsedFrame.midY, shiftedVoiceFrame.midY)
    XCTAssertEqual(collapsedFrame.size, compactSize)
  }

  func testDraggablePillPTTSequencePreservesUserCenter() {
    let draggedPillFrame = NSRect(x: 184, y: 612, width: compactSize.width, height: compactSize.height)
    let placement = FloatingControlBarGeometry.SurfacePlacement.pill(
      draggable: true,
      canonicalCompactFrame: draggedPillFrame
    )
    let expandedFrame = FloatingControlBarGeometry.surfaceTransitionFrame(
      currentFrame: draggedPillFrame,
      targetSize: voiceSize,
      transition: .pushToTalk(expanded: true),
      placement: placement
    )
    let collapsedFrame = FloatingControlBarGeometry.surfaceTransitionFrame(
      currentFrame: expandedFrame,
      targetSize: compactSize,
      transition: .pushToTalk(expanded: false),
      placement: placement
    )

    XCTAssertEqual(expandedFrame.midX, draggedPillFrame.midX)
    XCTAssertEqual(expandedFrame.midY, draggedPillFrame.midY)
    XCTAssertEqual(collapsedFrame.midX, draggedPillFrame.midX)
    XCTAssertEqual(collapsedFrame.midY, draggedPillFrame.midY)
  }

  func testNotchChromeActivationIgnoresTransparentBottomOutset() {
    let windowFrame = NSRect(x: 500, y: 800, width: 360, height: 58)

    XCTAssertTrue(
      FloatingControlBarGeometry.notchChromeActivationContains(
        mouseLocation: NSPoint(x: 680, y: 850),
        windowFrame: windowFrame,
        chromeHeight: 17,
        horizontalOutset: 24
      ))
    XCTAssertFalse(
      FloatingControlBarGeometry.notchChromeActivationContains(
        mouseLocation: NSPoint(x: 680, y: 838),
        windowFrame: windowFrame,
        chromeHeight: 17,
        horizontalOutset: 24
      ))
  }

  func testNotchChromeActivationLocalIgnoresTransparentBottomOutset() {
    let windowSize = NSSize(width: 360, height: 58)

    XCTAssertTrue(
      FloatingControlBarGeometry.notchChromeActivationContainsLocal(
        localPoint: NSPoint(x: 180, y: 50),
        windowSize: windowSize,
        chromeHeight: 17,
        horizontalOutset: 24
      ))
    XCTAssertFalse(
      FloatingControlBarGeometry.notchChromeActivationContainsLocal(
        localPoint: NSPoint(x: 180, y: 40),
        windowSize: windowSize,
        chromeHeight: 17,
        horizontalOutset: 24
      ))
  }

  func testNotchOpenMenuRetentionIncludesRowsButNotBottomGlow() {
    let windowSize = NSSize(width: 430, height: FloatingControlBarWindow.notchChromeHeight + 96 + 24)
    let visibleSurfaceHeight: CGFloat = FloatingControlBarWindow.notchChromeHeight + 96

    XCTAssertTrue(
      FloatingControlBarGeometry.notchChromeActivationContainsLocal(
        localPoint: NSPoint(x: 215, y: windowSize.height - visibleSurfaceHeight + 6),
        windowSize: windowSize,
        chromeHeight: visibleSurfaceHeight,
        horizontalOutset: 24
      ))
    XCTAssertFalse(
      FloatingControlBarGeometry.notchChromeActivationContainsLocal(
        localPoint: NSPoint(x: 215, y: 8),
        windowSize: windowSize,
        chromeHeight: visibleSurfaceHeight,
        horizontalOutset: 24
      ))
  }

  /// The hover surface used to collapse to nothing without subagents. It now always
  /// carries the shortcut legend and capture controls, so hovering the notch is never a
  /// no-op — but it must still be tall enough for the agent rows when there are any.
  func testNotchHoverMenuAlwaysReservesRoomForTheControlPanel() {
    XCTAssertEqual(
      FloatingControlBarWindow.notchHoverMenuHeight(agentCount: 0),
      FloatingControlBarWindow.notchControlPanelHeight
        + FloatingControlBarWindow.notchHoverMenuBottomMargin
    )
  }

  /// Spawned agents own the top of the hover surface; the control panel stacks beneath
  /// them. If the surface stopped growing per agent the panel would be drawn on top of
  /// the agent rows.
  func testControlPanelStacksBelowAgentRowsRatherThanOverlappingThem() {
    XCTAssertEqual(FloatingControlBarWindow.notchControlPanelTopOffset(agentCount: 0), 0)

    for count in 1...8 {
      let offset = FloatingControlBarWindow.notchControlPanelTopOffset(agentCount: count)
      XCTAssertEqual(
        offset,
        FloatingControlBarWindow.notchAgentListHeight(agentCount: count),
        "panel must start below all \(count) agent row(s)"
      )
      XCTAssertEqual(
        FloatingControlBarWindow.notchHoverMenuHeight(agentCount: count),
        offset + FloatingControlBarWindow.notchControlPanelHeight
          + FloatingControlBarWindow.notchHoverMenuBottomMargin,
        "surface must be tall enough for the rows plus the whole panel"
      )
    }
  }

  func testNotchHoverMenuGrowsWithEachAdditionalSubagent() {
    let empty = FloatingControlBarWindow.notchHoverMenuHeight(agentCount: 0)
    let one = FloatingControlBarWindow.notchHoverMenuHeight(agentCount: 1)
    let many = FloatingControlBarWindow.notchHoverMenuHeight(agentCount: 8)
    XCTAssertGreaterThan(one, empty)
    XCTAssertGreaterThan(many, one, "eight agent rows must not be clipped")
  }

  func testNotchChromeHeightUsesMeasuredAuxiliaryAreaHeight() {
    let height = FloatingControlBarWindow.notchChromeHeight(
      topSafeAreaInset: 30,
      auxiliaryTopLeftArea: NSRect(x: 0, y: 860, width: 600, height: 48),
      auxiliaryTopRightArea: NSRect(x: 840, y: 860, width: 600, height: 48)
    )

    XCTAssertEqual(height, 48)
  }

  func testNotchChromeHeightFallsBackToSafeAreaInset() {
    let height = FloatingControlBarWindow.notchChromeHeight(
      topSafeAreaInset: 44,
      auxiliaryTopLeftArea: nil,
      auxiliaryTopRightArea: nil
    )

    XCTAssertEqual(height, 44)
  }

  func testNotchChromeHeightKeepsDefaultForLegacyDisplays() {
    let height = FloatingControlBarWindow.notchChromeHeight(
      topSafeAreaInset: 0,
      auxiliaryTopLeftArea: nil,
      auxiliaryTopRightArea: nil
    )

    XCTAssertEqual(height, FloatingControlBarWindow.notchChromeHeight)
  }

  func testMeasuredNotchChromeHeightAcceptsFullVisibleChromeButNotGlow() {
    let measuredChromeHeight = FloatingControlBarWindow.notchChromeHeight(
      topSafeAreaInset: 48,
      auxiliaryTopLeftArea: nil,
      auxiliaryTopRightArea: nil
    )
    let windowSize = NSSize(width: 360, height: measuredChromeHeight + FloatingControlBarWindow.notchGlowOutsetBottom)

    XCTAssertTrue(
      FloatingControlBarGeometry.notchChromeActivationContainsLocal(
        localPoint: NSPoint(x: 180, y: FloatingControlBarWindow.notchGlowOutsetBottom + 2),
        windowSize: windowSize,
        chromeHeight: measuredChromeHeight,
        horizontalOutset: FloatingControlBarWindow.notchGlowOutsetX
      ))
    XCTAssertFalse(
      FloatingControlBarGeometry.notchChromeActivationContainsLocal(
        localPoint: NSPoint(x: 180, y: FloatingControlBarWindow.notchGlowOutsetBottom - 2),
        windowSize: windowSize,
        chromeHeight: measuredChromeHeight,
        horizontalOutset: FloatingControlBarWindow.notchGlowOutsetX
      ))
  }

  /// Regression: with a conversation open but no expanded response (the "thinking" state), the
  /// notch window's fixed 430×527 frame accepted clicks everywhere, parking an invisible dead zone
  /// over the main window's Tasks/Rewind/Apps pills. Whole-window hits belong only to content that
  /// visibly fills the window: an expanded response panel or a notification card.
  func testAThinkingConversationDoesNotOwnTheWholeNotchWindow() {
    XCTAssertFalse(
      FloatingControlBarGeometry.notchWholeWindowHitsAllowed(
        showingAIConversation: true, showingAIResponse: false, hasNotification: false),
      "thinking without a response panel must keep the content-derived hit region")
    XCTAssertFalse(
      FloatingControlBarGeometry.notchWholeWindowHitsAllowed(
        showingAIConversation: false, showingAIResponse: false, hasNotification: false))
    XCTAssertTrue(
      FloatingControlBarGeometry.notchWholeWindowHitsAllowed(
        showingAIConversation: true, showingAIResponse: true, hasNotification: false))
    XCTAssertTrue(
      FloatingControlBarGeometry.notchWholeWindowHitsAllowed(
        showingAIConversation: false, showingAIResponse: false, hasNotification: true))
  }

  /// Regression: while an expanded response panel or a notification card was showing, the
  /// whole window frame accepted clicks — including the transparent glow outsets around the
  /// visible surface. Clicks on other apps landing in that ring were silently swallowed and
  /// the clicked app never activated (the "dead zone" report). Surface-filling content owns
  /// exactly the surface: frame minus the horizontal and bottom glow outsets.
  func testSurfaceFillingContentDoesNotOwnTheTransparentGlowRing() {
    // Response-panel shaped window: 382×527 surface + 24pt glow on each side and below.
    let windowSize = NSSize(width: 430, height: 551)

    XCTAssertTrue(
      FloatingControlBarGeometry.notchSurfaceContentContainsLocal(
        localPoint: NSPoint(x: 215, y: 300),
        windowSize: windowSize, bottomOutset: 24, horizontalOutset: 24),
      "the visible surface stays interactive")
    XCTAssertTrue(
      FloatingControlBarGeometry.notchSurfaceContentContainsLocal(
        localPoint: NSPoint(x: 24, y: 24),
        windowSize: windowSize, bottomOutset: 24, horizontalOutset: 24),
      "the surface's bottom-left corner is still content (resize grip corner)")
    XCTAssertFalse(
      FloatingControlBarGeometry.notchSurfaceContentContainsLocal(
        localPoint: NSPoint(x: 12, y: 300),
        windowSize: windowSize, bottomOutset: 24, horizontalOutset: 24),
      "left glow ring passes clicks through")
    XCTAssertFalse(
      FloatingControlBarGeometry.notchSurfaceContentContainsLocal(
        localPoint: NSPoint(x: 424, y: 300),
        windowSize: windowSize, bottomOutset: 24, horizontalOutset: 24),
      "right glow ring passes clicks through")
    XCTAssertFalse(
      FloatingControlBarGeometry.notchSurfaceContentContainsLocal(
        localPoint: NSPoint(x: 215, y: 10),
        windowSize: windowSize, bottomOutset: 24, horizontalOutset: 24),
      "glow margin below the surface passes clicks through")
  }

  func testNotchChromeActivationIgnoresHorizontalGlowOutsets() {
    let windowFrame = NSRect(x: 500, y: 800, width: 360, height: 58)

    XCTAssertFalse(
      FloatingControlBarGeometry.notchChromeActivationContains(
        mouseLocation: NSPoint(x: 512, y: 850),
        windowFrame: windowFrame,
        chromeHeight: 17,
        horizontalOutset: 24
      ))
    XCTAssertFalse(
      FloatingControlBarGeometry.notchChromeActivationContains(
        mouseLocation: NSPoint(x: 848, y: 850),
        windowFrame: windowFrame,
        chromeHeight: 17,
        horizontalOutset: 24
      ))
  }

  func testTransparentPanelIgnoresMouseOutsideItsVisibleHitRegion() {
    let frame = NSRect(x: 500, y: 800, width: 360, height: 58)
    let visibleLocalRegion = NSRect(x: 24, y: 24, width: 312, height: 34)

    XCTAssertFalse(
      FloatingBarMouseInterceptionPolicy.shouldIgnoreMouseEvents(
        mouseLocation: NSPoint(x: 680, y: 790),
        windowFrame: frame,
        isVisible: true,
        acceptsMouseHit: visibleLocalRegion.contains),
      "an ordered-in panel stays ready to receive the tracking event when the pointer enters")
    XCTAssertTrue(
      FloatingBarMouseInterceptionPolicy.shouldIgnoreMouseEvents(
        mouseLocation: NSPoint(x: 510, y: 810),
        windowFrame: frame,
        isVisible: true,
        acceptsMouseHit: visibleLocalRegion.contains),
      "transparent glow margin must pass through to the window underneath")
    XCTAssertFalse(
      FloatingBarMouseInterceptionPolicy.shouldIgnoreMouseEvents(
        mouseLocation: NSPoint(x: 680, y: 840),
        windowFrame: frame,
        isVisible: true,
        acceptsMouseHit: visibleLocalRegion.contains),
      "visible notch chrome remains interactive")
    XCTAssertTrue(
      FloatingBarMouseInterceptionPolicy.shouldIgnoreMouseEvents(
        mouseLocation: NSPoint(x: 680, y: 840),
        windowFrame: frame,
        isVisible: false,
        acceptsMouseHit: { _ in true }),
      "an ordered-out panel must never retain event ownership")
  }
}
