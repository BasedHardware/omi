import AppKit
import OmiTheme
import SwiftUI
import XCTest

@testable import Omi_Computer

/// The floating bar's notification cards must land on a ground, in **both** of the bar's
/// presentations.
///
/// The regression this file exists for shipped as white-on-white. `barNotification` dispatches to five
/// different cards, and exactly one of them — the generic `notificationView` — carried
/// `floatingBackground()` itself. Docked to the notch that cost nothing, because every card there sits
/// on `unifiedFloatingSurface`'s opaque black dock shape. Undocked, the notification is a bare sibling
/// of the pill in a `VStack` with no shared ground at all, so the receipt, the reach error, the end
/// card and the suggestion each rendered their white type straight onto the desktop. Measured on the
/// running app over a light window: card text `(255,255,255)` on a ground of `(182,182,182)`, a
/// contrast ratio of 2.03:1 — and 1.1:1 on the body copy. Nothing logged, and over a dark desktop it
/// looks perfect.
///
/// So the assertion is a render, not a spelling check: mount the real `FloatingControlBarView` with a
/// real notification in state, over a **white** backdrop — the case the shipped shape got wrong —
/// and read back what the card is actually drawn on. A source-level check that
/// `floatingBackground` appears somewhere would have passed on the broken shape, because it did
/// appear, on the one branch nobody was looking at.
@MainActor
final class FloatingBarNotificationGroundTests: XCTestCase {

  private static let size = NSSize(width: 420, height: 200)

  /// Every card the bar can put below the pill. The point of the list is that it is the *whole*
  /// list — a ground owned per-card is exactly what let four of these drift apart.
  private static let assistantIDs: [String] = [
    "reach_error",
    NotchMoment.receiptAssistantId,
    NotchMoment.endAssistantId,
    "suggestion",
    "proactive_assistant",
  ]

  private func makeState(assistantID: String) -> FloatingControlBarState {
    let state = FloatingControlBarState()
    // The undocked presentation: no notch island, no conversation, no hover menu. This is the branch
    // where the bar has no shared ground of its own.
    state.usesNotchIsland = false
    state.currentNotification = FloatingBarNotification(
      ownerID: "test-owner",
      title: "Couldn't reach Omi",
      message: "Error 502",
      assistantId: assistantID,
      kind: ProactiveNotificationKind.from(assistantId: assistantID))
    return state
  }

  private func makeView(state: FloatingControlBarState) -> some View {
    FloatingControlBarView(
      window: nil,
      onPlayPause: {},
      onAskAI: {},
      onHide: {},
      onSendQuery: { _ in },
      onCloseAI: {},
      onEscape: {},
      onClearVisibleConversation: {},
      onRate: { _, _, _ in },
      onShareLink: { nil }
    )
    .environmentObject(state)
  }

  /// Renders the bar over an opaque white backdrop and returns the bitmap.
  ///
  /// White because that is the failing case and the one a light desktop, a light window, or the app's
  /// own pinned-light shell puts behind the bar. The blurred material cannot render into an offscreen
  /// bitmap (`NSVisualEffectView` blends `.behindWindow`), which is fine and is the point: what is
  /// under test is the *scrim*, and a card with no scrim leaves the backdrop untouched.
  private func render(_ view: some View) throws -> NSBitmapImageRep {
    let host = NSHostingView(rootView: view)
    host.frame = NSRect(origin: .zero, size: Self.size)

    let backdrop = NSView(frame: host.frame)
    backdrop.wantsLayer = true
    backdrop.layer?.backgroundColor = NSColor.white.cgColor
    backdrop.addSubview(host)
    backdrop.layoutSubtreeIfNeeded()

    let rep = try XCTUnwrap(backdrop.bitmapImageRepForCachingDisplay(in: backdrop.bounds))
    backdrop.cacheDisplay(in: backdrop.bounds, to: rep)
    return rep
  }

  /// The darkest pixel anywhere in the render.
  ///
  /// Darkest rather than a fixed coordinate: the five cards are different heights and lay their type
  /// out differently, and pinning a probe point would make this test a layout assertion that breaks
  /// every time someone moves a label. A card that painted no ground leaves nothing dark behind —
  /// its own type is white — so "is anything here dark" is precisely the question.
  private func darkestBrightness(_ rep: NSBitmapImageRep) -> CGFloat {
    var darkest: CGFloat = 1
    for y in stride(from: 0, to: rep.pixelsHigh, by: 2) {
      for x in stride(from: 0, to: rep.pixelsWide, by: 2) {
        guard let color = rep.colorAt(x: x, y: y)?.usingColorSpace(.deviceRGB) else { continue }
        darkest = min(darkest, color.brightnessComponent)
      }
    }
    return darkest
  }

  /// The claim, for every card the bar can show: undocked, it is drawn on the pill's black glass.
  ///
  /// `0.35` is far above the ground the scrim actually produces over white (`#0A0A0C` at 0.85 leaves
  /// roughly 0.18) and far below anything an ungrounded card can reach, whose darkest pixel is the
  /// white backdrop itself. A threshold that loose is deliberate: this test is about whether a ground
  /// exists at all, and the exact scrim value is `FloatingGlassChromeTests`' job.
  func testEveryUndockedNotificationCardIsDrawnOnAGround() throws {
    for assistantID in Self.assistantIDs {
      let rep = try render(makeView(state: makeState(assistantID: assistantID)))
      XCTAssertLessThan(
        darkestBrightness(rep), 0.35,
        """
        the "\(assistantID)" card rendered with no ground of its own over a white backdrop — \
        undocked there is nothing under it but the desktop, so its white type is invisible
        """)
    }
  }

  /// The other half of the same contract: the ground belongs to the *surface*, so it must not also be
  /// worn by a card. Two scrims halve the passthrough the first was tuned for, which is what makes a
  /// translucent panel read as muddy over one desktop and opaque over another
  /// (`notchGlassPanel`'s "apply once").
  ///
  /// Asserted as a value rather than by counting modifiers: one scrim over white lands near
  /// `InkGlass`-tuned 0.18, two lands near 0.03. The floor here fails only on the doubled case.
  func testTheGroundIsWornOnceAndNotStackedPerCard() throws {
    let rep = try render(makeView(state: makeState(assistantID: NotchMoment.receiptAssistantId)))
    XCTAssertGreaterThan(
      darkestBrightness(rep), 0.04,
      "the card ground is darker than a single scrim over white; a second `floatingBackground` is stacked on it")
  }
}
