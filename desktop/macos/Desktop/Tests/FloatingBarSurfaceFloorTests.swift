import AppKit
import XCTest

@testable import Omi_Computer
@testable import VoiceTurnDomain

/// The closed notch surface is a function of presentation state, and the
/// window can never *settle* below it.
///
/// #12630 and #12882 each fixed a handful of resize paths that substituted a
/// bare transient size for the composed closed surface. Both fixes were
/// correct and both left the class open: any new call site, any ordering
/// race between two resizes aimed at the same transition, and AppKit auto
/// layout could still land the window on a stale size with a card, a status
/// banner, or the thinking mark rendering inside it. These tests assert the
/// class is closed at the boundary every path crosses — the settle point —
/// rather than at the call sites.
@MainActor
final class FloatingBarSurfaceFloorTests: XCTestCase {

  private func withNotchMode(_ body: () -> Void) {
    let previousForceNoNotch = getenv("OMI_FORCE_NO_NOTCH").map { String(cString: $0) }
    let previousForceNotch = getenv("OMI_FORCE_NOTCH").map { String(cString: $0) }
    unsetenv("OMI_FORCE_NO_NOTCH")
    setenv("OMI_FORCE_NOTCH", "1", 1)
    defer {
      if let previousForceNoNotch {
        setenv("OMI_FORCE_NO_NOTCH", previousForceNoNotch, 1)
      } else {
        unsetenv("OMI_FORCE_NO_NOTCH")
      }
      if let previousForceNotch {
        setenv("OMI_FORCE_NOTCH", previousForceNotch, 1)
      } else {
        unsetenv("OMI_FORCE_NOTCH")
      }
    }
    body()
  }

  private func makeWindow() -> FloatingControlBarWindow {
    let window = FloatingControlBarWindow(
      contentRect: .zero,
      styleMask: [.borderless, .nonactivatingPanel],
      backing: .buffered,
      defer: false
    )
    window.makeKeyAndOrderFront(nil)
    return window
  }

  private func card(_ title: String = "Meeting notes ready") -> FloatingBarNotification {
    FloatingBarNotification(
      ownerID: "test-owner",
      title: title,
      message: "Apple product presentation — three decisions and one open question",
      assistantId: "proactive_assistant",
      kind: .memory
    )
  }

  private func scrunchedFrame(for window: FloatingControlBarWindow) -> NSRect {
    NSRect(x: window.frame.midX - 60, y: window.frame.maxY - 30, width: 120, height: 30)
  }

  private func presenter(for window: FloatingControlBarWindow) -> FloatingControlBarState.PTTBarPresenter {
    FloatingControlBarState.PTTBarPresenter(
      barState: window.state,
      resizeForPTT: { [weak window] in window?.resizeForPTTState(expanded: $0) }
    )
  }

  // MARK: - The pure policy

  func testDeferralNamesEverySurfaceThatOwnsItsOwnFrame() {
    XCTAssertEqual(
      FloatingBarSurfaceFloor.deferral(
        isVisible: false, isUserDragging: false, isUserResizing: false,
        isConversationOpen: false, isRevealOrRetractInFlight: false),
      .windowHidden)
    XCTAssertEqual(
      FloatingBarSurfaceFloor.deferral(
        isVisible: true, isUserDragging: true, isUserResizing: false,
        isConversationOpen: false, isRevealOrRetractInFlight: false),
      .userDragging)
    XCTAssertEqual(
      FloatingBarSurfaceFloor.deferral(
        isVisible: true, isUserDragging: false, isUserResizing: true,
        isConversationOpen: false, isRevealOrRetractInFlight: false),
      .userResizing)
    XCTAssertEqual(
      FloatingBarSurfaceFloor.deferral(
        isVisible: true, isUserDragging: false, isUserResizing: false,
        isConversationOpen: true, isRevealOrRetractInFlight: false),
      .conversationOpen)
    XCTAssertEqual(
      FloatingBarSurfaceFloor.deferral(
        isVisible: true, isUserDragging: false, isUserResizing: false,
        isConversationOpen: false, isRevealOrRetractInFlight: true),
      .revealOrRetractInFlight)
    XCTAssertNil(
      FloatingBarSurfaceFloor.deferral(
        isVisible: true, isUserDragging: false, isUserResizing: false,
        isConversationOpen: false, isRevealOrRetractInFlight: false))
  }

  func testASatisfiedFrameNeedsNoCorrection() {
    let frame = NSRect(x: 100, y: 100, width: 556, height: 220)
    XCTAssertNil(
      FloatingBarSurfaceFloor.correctedFrame(
        effectiveFrame: frame,
        floorSize: NSSize(width: 556, height: 220),
        anchor: .topCenter))
    XCTAssertNil(
      FloatingBarSurfaceFloor.correctedFrame(
        effectiveFrame: frame,
        floorSize: NSSize(width: 300, height: 60),
        anchor: .topCenter),
      "a frame larger than the floor is transparent margin, never corrected")
    XCTAssertNil(
      FloatingBarSurfaceFloor.correctedFrame(
        effectiveFrame: frame,
        floorSize: NSSize(width: 556.4, height: 220.4),
        anchor: .topCenter),
      "sub-epsilon differences are the same frame")
  }

  func testAnUndersizedNotchFrameIsRaisedToTheFloorOnTheDisplayTop() {
    let screen = NSRect(x: 0, y: 0, width: 1440, height: 900)
    let stale = NSRect(x: 660, y: 862, width: 120, height: 38)
    let corrected = FloatingBarSurfaceFloor.correctedFrame(
      effectiveFrame: stale,
      floorSize: NSSize(width: 556, height: 220),
      anchor: .screenTopCenter(screen))
    XCTAssertEqual(corrected, NSRect(x: 442, y: 680, width: 556, height: 220))
  }

  func testTheCorrectionOnlyGrowsAndKeepsTheLargerDimension() {
    let wideButShort = NSRect(x: 0, y: 0, width: 700, height: 20)
    let corrected = FloatingBarSurfaceFloor.correctedFrame(
      effectiveFrame: wideButShort,
      floorSize: NSSize(width: 556, height: 220),
      anchor: .topCenter)
    XCTAssertEqual(corrected?.width, 700, "an already-wider frame keeps its width")
    XCTAssertEqual(corrected?.height, 220)
    XCTAssertEqual(corrected?.maxY, wideButShort.maxY, "a pill grows down from its top edge")
    XCTAssertEqual(corrected?.midX ?? -1, wideButShort.midX, accuracy: 0.001)
  }

  // MARK: - The settle point

  /// Any path that sets an undersized frame directly — auto layout, a direct
  /// setFrame, a stale animation completion — reaches the same settle point.
  func testAFrameSetBelowTheFloorUnderAMountedCardIsRaisedBack() {
    withNotchMode {
      let window = makeWindow()
      defer { window.close() }

      window.showNotification(card(), animated: false)
      let mounted = window.frame
      XCTAssertGreaterThan(mounted.width, 300)

      window.setFrame(scrunchedFrame(for: window), display: false)
      XCTAssertLessThan(window.frame.width, mounted.width, "the direct setFrame must have landed")

      window.settlePendingSurfaceFloorReconcile()

      XCTAssertEqual(window.frame.width, mounted.width, accuracy: 0.5)
      XCTAssertEqual(window.frame.height, mounted.height, accuracy: 0.5)
      XCTAssertTrue(window.surfaceFloorSatisfiedForAutomation)
    }
  }

  /// A producer that mounts a card by mutating state without resizing — or a
  /// resize that never happened because two paths raced — still ends on the
  /// card surface: the state change alone drives the frame.
  func testAStateChangeAloneRaisesTheFrameToTheSurfaceItRequires() {
    withNotchMode {
      let window = makeWindow()
      defer { window.close() }
      window.settlePendingSurfaceFloorReconcile()
      let idle = window.frame

      window.state.currentNotification = card()
      let required = window.surfaceFloorWindowSize()
      XCTAssertGreaterThan(required.width, idle.width, "the card must require more than the idle lobe")

      window.scheduleSurfaceFloorReconcile(reason: "test_state_change")
      window.settlePendingSurfaceFloorReconcile()

      XCTAssertEqual(window.frame.width, required.width, accuracy: 0.5)
      XCTAssertEqual(window.frame.height, required.height, accuracy: 0.5)
    }
  }

  /// A failure hint keeps `isVoiceListening` true, so hint-after-thinking
  /// changes the lifecycle key and fires the island sync. That sync used to
  /// aim at the bare listening island while the hint observer aimed at the
  /// banner surface; the last one to land decided whether the banner fit.
  func testTheLifecycleResizeForAHintAfterThinkingTargetsTheBannerSurface() {
    withNotchMode {
      let window = makeWindow()
      defer { window.close() }
      let presenter = presenter(for: window)

      presenter.apply(VoiceTurnUIProjection(isThinking: true))
      window.syncActiveIsland()
      window.settlePendingSurfaceFloorReconcile()

      presenter.apply(VoiceTurnUIProjection(hint: "Couldn't hear you — try again"))
      XCTAssertFalse(window.state.pttHintText.isEmpty, "the banner must actually be showing")
      window.syncActiveIsland()

      let required = window.surfaceFloorWindowSize()
      XCTAssertGreaterThanOrEqual(
        required.width, FloatingControlBarWindow.notchExpandedWidth,
        "the banner surface is the expanded width")
      XCTAssertTrue(
        window.surfaceFloorSatisfiedForAutomation,
        "the lifecycle resize must aim at the composed surface, not the bare listening island")
    }
  }

  /// The path the floor caught live on the first run: a too-short release
  /// passes through thinking, then publishes the hint. `isVoiceListening` is
  /// true for a hint, so the presenter re-expands "for voice" — and the
  /// expand edge sized the bare island (386x62) under a banner that needs
  /// 430x100. The expand edge must compose with the closed surface itself,
  /// so the floor is the backstop and not the first line.
  func testTheExpandEdgeDuringAHintCarriesTheBannerBudget() {
    withNotchMode {
      let window = makeWindow()
      defer { window.close() }
      let presenter = presenter(for: window)

      presenter.apply(VoiceTurnUIProjection(isListening: true))
      presenter.apply(VoiceTurnUIProjection(isThinking: true))
      presenter.apply(VoiceTurnUIProjection(hint: "Hold longer to record"))
      XCTAssertTrue(window.state.isVoiceListening, "a hint keeps the voice-expanded state")

      let expandEdge = window.pushToTalkSurfaceSize(expanded: true)
      let composed = window.closedSurfaceSize(usesNotchIsland: true)
      XCTAssertGreaterThanOrEqual(expandEdge.width + 0.5, composed.width)
      XCTAssertGreaterThanOrEqual(
        expandEdge.height + 0.5, composed.height,
        "the expand edge must carry the banner budget, not the bare island height")
      XCTAssertTrue(window.surfaceFloorSatisfiedForAutomation)
    }
  }

  /// The floor never fights an animation heading somewhere acceptable and
  /// never shrinks a frame that is merely larger than required.
  func testTheFloorLeavesALargerFrameAlone() {
    withNotchMode {
      let window = makeWindow()
      defer { window.close() }
      window.settlePendingSurfaceFloorReconcile()

      let oversized = NSRect(
        x: window.frame.midX - 400, y: window.frame.maxY - 300, width: 800, height: 300)
      window.setFrame(oversized, display: false)

      XCTAssertFalse(window.enforceSurfaceFloor(reason: "test"))
      XCTAssertEqual(window.frame.size, oversized.size)
    }
  }

  /// An open conversation owns its geometry — height observers, a user
  /// resize grip — so the floor defers to it entirely.
  func testTheFloorDefersToAnOpenConversation() {
    withNotchMode {
      let window = makeWindow()
      defer { window.close() }
      window.showNotification(card(), animated: false)

      window.state.showingAIConversation = true
      let scrunched = scrunchedFrame(for: window)
      window.setFrame(scrunched, display: false)

      XCTAssertFalse(window.enforceSurfaceFloor(reason: "test"))
      XCTAssertEqual(window.frame.size, scrunched.size)
      XCTAssertTrue(window.surfaceFloorSatisfiedForAutomation, "an open conversation reports satisfied")
    }
  }

  /// Dismissing the card hands the floor back to the idle lobe: the floor is
  /// derived from live state each time, never remembered from the last card.
  func testTheFloorFollowsTheStateDown() {
    withNotchMode {
      let window = makeWindow()
      defer { window.close() }
      window.settlePendingSurfaceFloorReconcile()
      let idle = window.surfaceFloorWindowSize()

      window.showNotification(card(), animated: false)
      XCTAssertGreaterThan(window.surfaceFloorWindowSize().width, idle.width)

      window.dismissNotification(animated: false)
      XCTAssertEqual(window.surfaceFloorWindowSize(), idle)
      XCTAssertFalse(window.enforceSurfaceFloor(reason: "test"), "the idle frame satisfies the idle floor")
    }
  }

  /// A floor check that runs while the user is dragging must not be dropped
  /// forever. Drag-end requeues the reconcile so the card surface is restored.
  func testAFloorCheckDroppedDuringDragIsRequeuedWhenTheDragEnds() {
    withNotchMode {
      let window = makeWindow()
      defer { window.close() }
      window.showNotification(card(), animated: false)
      let mounted = window.frame

      window.beginUserDrag()
      window.setFrame(scrunchedFrame(for: window), display: false)
      XCTAssertFalse(window.enforceSurfaceFloor(reason: "drag"))
      XCTAssertLessThan(window.frame.width, mounted.width)

      window.endUserDrag()
      window.settlePendingSurfaceFloorReconcile()

      XCTAssertEqual(window.frame.width, mounted.width, accuracy: 0.5)
      XCTAssertEqual(window.frame.height, mounted.height, accuracy: 0.5)
    }
  }
}
