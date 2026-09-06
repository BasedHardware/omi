import AppKit
import XCTest

@testable import Omi_Computer
@testable import VoiceTurnDomain

/// A mounted notification card owns the notch surface until it is dismissed.
///
/// The regression these tests exist for: `resizeForPTTState` substituted the
/// bare voice island for whatever the surface was showing, checking only
/// `showingAIConversation`. Interject deliberately keeps the card up while the
/// user holds the reply shortcut against it ("hold fn to reply"), so holding
/// fn on a card resized a 508pt panel down to the ~270pt notch lobe and kept
/// it there for the whole turn — listening, thinking, and answering. The card
/// stayed mounted inside it, so its copy re-wrapped into three truncated
/// words: the "scrunched notch".
///
/// `FloatingControlBarGeometry.collapsedSurfaceSize` already encoded the right
/// rule, and `FloatingBarGeometryTests` already asserted it. That is exactly
/// why the bug shipped: the invariant was tested on the authority while the
/// live PTT path never called it. These tests assert it on the paths that
/// actually resize the window.
@MainActor
final class FloatingBarNotchCardSizingTests: XCTestCase {

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
    FloatingControlBarWindow(
      contentRect: .zero,
      styleMask: [.borderless, .nonactivatingPanel],
      backing: .buffered,
      defer: false
    )
  }

  /// The projection a too-short hold publishes: a banner hint, no listening.
  private static let hintProjection = VoiceTurnUIProjection(hint: "Hold longer to record")

  private func card(_ title: String = "Memory") -> FloatingBarNotification {
    FloatingBarNotification(
      ownerID: "test-owner",
      title: title,
      message: "User is asked to find learned lessons in Claude Code sessions",
      assistantId: "proactive_assistant",
      kind: .memory
    )
  }

  // MARK: - The live PTT path

  func testHoldingPushToTalkAgainstAMountedCardKeepsTheCardSurface() {
    withNotchMode {
      let window = makeWindow()
      defer { window.close() }
      window.makeKeyAndOrderFront(nil)

      window.showNotification(card(), animated: false)
      let mounted = window.frame
      XCTAssertGreaterThan(mounted.width, 0)

      // Listening and thinking are the two states Interject runs *while* the
      // card is still on screen. Neither may shrink the panel under it.
      for expanded in [true, false] {
        let ptt = window.pushToTalkSurfaceSize(expanded: expanded)
        XCTAssertGreaterThanOrEqual(
          ptt.width + FloatingControlBarWindow.notchGlowOutsetX * 2, mounted.width,
          "PTT (expanded=\(expanded)) must not narrow the panel under a mounted card")
        XCTAssertGreaterThanOrEqual(
          ptt.height + FloatingControlBarWindow.notchGlowOutsetBottom, mounted.height,
          "PTT (expanded=\(expanded)) must not clip the card body")
      }
    }
  }

  /// End to end through the production trigger: the reducer projection that
  /// `VoiceTurnCoordinator` publishes, applied by the real presenter, which is
  /// what calls `resizeForPTTState`.
  func testVoiceProjectionWhileACardIsMountedNeverTargetsTheBareIsland() {
    withNotchMode {
      let window = makeWindow()
      defer { window.close() }
      window.makeKeyAndOrderFront(nil)

      window.showNotification(card(), animated: false)
      let mounted = window.frame

      let presenter = FloatingControlBarState.PTTBarPresenter(
        barState: window.state,
        resizeForPTT: { [weak window] in window?.resizeForPTTState(expanded: $0) }
      )
      presenter.apply(VoiceTurnUIProjection(isListening: true))

      // The pre-fix code took the panel down to the listening lobe here.
      XCTAssertGreaterThanOrEqual(window.frame.width, mounted.width)
      XCTAssertGreaterThanOrEqual(window.frame.height, mounted.height)
      XCTAssertNotNil(window.state.currentNotification, "the card must still be mounted")
    }
  }

  func testPushToTalkWithoutACardStillUsesTheBareIsland() {
    withNotchMode {
      let window = makeWindow()
      defer { window.close() }
      window.makeKeyAndOrderFront(nil)

      let listening = window.pushToTalkSurfaceSize(expanded: true)
      let idle = window.pushToTalkSurfaceSize(expanded: false)

      window.showNotification(card(), animated: false)
      XCTAssertGreaterThan(
        window.pushToTalkSurfaceSize(expanded: true).width, listening.width,
        "the card must be what grows the surface — not a new unconditional minimum")
      XCTAssertGreaterThan(window.pushToTalkSurfaceSize(expanded: false).width, idle.width)
    }
  }

  // MARK: - The status-banner path

  /// A too-short hold or a mic error draws a status banner under the chrome.
  /// It used to *replace* the whole closed surface with `notchExpandedWidth`,
  /// which both narrowed a mounted card and clipped its body off the bottom.
  func testStatusBannerWhileACardIsMountedStacksInsteadOfReplacing() {
    withNotchMode {
      let window = makeWindow()
      defer { window.close() }
      window.makeKeyAndOrderFront(nil)

      let presenter = FloatingControlBarState.PTTBarPresenter(
        barState: window.state,
        resizeForPTT: { [weak window] in window?.resizeForPTTState(expanded: $0) }
      )

      presenter.apply(Self.hintProjection)
      let hintOnly = window.closedSurfaceSize(usesNotchIsland: true)
      XCTAssertFalse(window.state.pttHintText.isEmpty, "the banner must actually be showing")

      window.showNotification(card(), animated: false)
      let cardPlusBanner = window.closedSurfaceSize(usesNotchIsland: true)

      presenter.apply(.idle)
      let cardOnly = window.closedSurfaceSize(usesNotchIsland: true)

      XCTAssertEqual(
        cardPlusBanner.width, FloatingControlBarWindow.notificationWidth, accuracy: 0.5,
        "a mounted card keeps its own width, not the notch-expanded hint width")
      XCTAssertGreaterThan(cardPlusBanner.width, hintOnly.width)
      XCTAssertEqual(
        cardPlusBanner.height, cardOnly.height + FloatingControlBarWindow.pttStatusBannerBudget,
        accuracy: 0.5,
        "the banner stacks on top of the card instead of replacing it")
    }
  }

  // MARK: - Pre-chat center capture

  func testSavingThePreChatCenterDoesNotCollapseAMountedCard() {
    withNotchMode {
      let previousDraggable = ShortcutSettings.shared.draggableBarEnabled
      ShortcutSettings.shared.draggableBarEnabled = false
      defer { ShortcutSettings.shared.draggableBarEnabled = previousDraggable }

      let window = makeWindow()
      defer { window.close() }
      window.makeKeyAndOrderFront(nil)

      window.showNotification(card(), animated: false)
      let mounted = window.frame

      // A prefilled query records the pre-chat pill center before the chat
      // surface opens. Recording it must not snap the visible card down to the
      // collapsed island.
      window.savePreChatCenterIfNeeded()

      XCTAssertEqual(window.frame, mounted)
      XCTAssertNotNil(window.state.currentNotification)
    }
  }

  // MARK: - The pure rule

  func testNotificationPreservingSurfaceSizeKeepsTheCardWhole() {
    let card = NSSize(width: 508, height: 194)
    let island = NSSize(width: 290, height: 38)

    let listening = FloatingControlBarGeometry.notificationPreservingSurfaceSize(
      transientSize: island,
      hasMountedNotification: true,
      notificationSize: card
    )
    XCTAssertEqual(listening, card)

    let withBanner = FloatingControlBarGeometry.notificationPreservingSurfaceSize(
      transientSize: NSSize(width: 382, height: 76),
      hasMountedNotification: true,
      notificationSize: card,
      additionalHeight: 38
    )
    XCTAssertEqual(withBanner.width, 508, accuracy: 0.001)
    XCTAssertEqual(withBanner.height, 232, accuracy: 0.001, "the banner stacks with the card")
  }

  func testNotificationPreservingSurfaceSizeIsTransparentWithoutACard() {
    let island = NSSize(width: 290, height: 38)
    XCTAssertEqual(
      FloatingControlBarGeometry.notificationPreservingSurfaceSize(
        transientSize: island,
        hasMountedNotification: false,
        notificationSize: NSSize(width: 508, height: 194),
        additionalHeight: 38
      ),
      island,
      "the transient surface already carries its own budget when no card is up")
  }

  func testATransientSurfaceWiderThanTheCardStillWins() {
    let card = NSSize(width: 508, height: 194)
    let wide = NSSize(width: 640, height: 38)
    let size = FloatingControlBarGeometry.notificationPreservingSurfaceSize(
      transientSize: wide,
      hasMountedNotification: true,
      notificationSize: card
    )
    XCTAssertEqual(size.width, 640, accuracy: 0.001)
    XCTAssertEqual(size.height, 194, accuracy: 0.001)
  }
}
