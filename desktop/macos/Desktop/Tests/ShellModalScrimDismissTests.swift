import AppKit
import SwiftUI
import XCTest

@testable import Omi_Computer

/// **Clicking outside a modal still dismisses it — everywhere, not just where it went dark.**
///
/// `ShellModalScrimTests` (in `PageGlassLaneTests.swift`) holds the other half of the scrim: what it
/// *paints* stops at the shell's surface and never reaches the transparent window's edge. That guard
/// alone would be satisfied by a scrim that also stopped *taking clicks* at the same boundary — and
/// that is the usability bug the visual fix must not trade itself for, because the undimmed border
/// between the panel and the window's edge is exactly where a user clicks to say "close this".
///
/// So this file holds the claim the paint tests cannot: **modality is host scale while only the paint
/// is bounded.** It is held on a real click — an `NSEvent` pair dispatched into the window that hosts
/// the real `ShellModalScrim`, running the caller's real dismiss action — because that is the only
/// thing that distinguishes a barrier that covers the host from one that covers the dim.
///
/// This is what the two Home tripwires in `DashboardCaptureStateTests` used to reach for by grepping
/// `DashboardPage.swift` for `.onTapGesture { dismissAppsPopup() }`. The gesture moved into
/// `ShellModalScrim` when the dim was bounded, and the contract it guards is now exercised here
/// instead of read out of a source file.
///
/// Deterministic and hermetic: SwiftUI recognises the tap inside `sendEvent`, so there is nothing to
/// wait for and no wall-clock sleep here.
@MainActor
final class ShellModalScrimDismissTests: XCTestCase {

  private static let hostSize = CGSize(width: 1_400, height: 800)

  /// **The click that dismisses lands where nothing was painted.**
  ///
  /// The dim is clamped to the shell's lane, so at any real window width there is a band of
  /// undimmed desktop-backed glass on either side of it. A barrier clamped to the same lane would
  /// leave that band inert: the modal would look modal and refuse to close when you clicked beside
  /// it. Asserted at the far corner *and* in the middle so a barrier that shrank to the paint fails
  /// on the first while the second still proves the harness can see a tap at all.
  func testAClickOutsideThePaintedDimStillRunsTheDismiss() throws {
    let size = Self.hostSize
    let laneWidth = ShellModalScrimLayout.laneWidth(for: size.width)
    let sideBand = (size.width - laneWidth) / 2
    XCTAssertGreaterThan(
      sideBand, 1,
      "precondition: the dim is clamped to the lane, so there is undimmed glass beside it")

    for (label, point) in [
      ("beside the dim", CGPoint(x: sideBand / 2, y: size.height / 2)),
      ("above the dim", CGPoint(x: size.width / 2, y: size.height - 2)),
      ("on the dim", CGPoint(x: size.width / 2, y: size.height / 2)),
    ] {
      let dismissals = Counter()
      click(
        at: point,
        on: ShellModalScrim(onTap: { dismissals.increment() }))

      XCTAssertEqual(
        dismissals.count, 1,
        "a click \(label) must still dismiss the modal — modality covers the host, only the paint "
          + "is bounded to the surface")
    }
  }

  /// …and a dim that is pure decoration must not take the click at all.
  ///
  /// The goal celebration paints over the app while the app stays usable. If it swallowed clicks the
  /// user would lose the pointer for the length of an animation, which is the same barrier working
  /// against them.
  func testADecorativeDimDoesNotSwallowTheClick() throws {
    let dismissals = Counter()
    click(
      at: CGPoint(x: Self.hostSize.width / 2, y: Self.hostSize.height / 2),
      on: ShellModalScrim(blocksInteraction: false, onTap: { dismissals.increment() }))

    XCTAssertEqual(
      dismissals.count, 0,
      "a decorative dim must let the pointer through to the app it is celebrating")
  }

  /// **End to end: a presented sheet closes when you click beside it.**
  ///
  /// The whole user-facing contract through production code — `dismissableSheet` mounts the scrim,
  /// the scrim delivers the click, the caller's binding goes false — driven from the one controllable
  /// seam these overlays have. The Home popup and connect sheet are hand-rolled rather than mounted
  /// through this modifier, but they compose the same two pieces, and this is the composition.
  func testClickingBesideAPresentedSheetDismissesIt() throws {
    let size = Self.hostSize
    let sideBand = (size.width - ShellModalScrimLayout.laneWidth(for: size.width)) / 2
    let latch = Latch(isPresented: true)

    click(
      at: CGPoint(x: sideBand / 2, y: size.height / 2),
      on: Color.clear.dismissableSheet(isPresented: latch.binding) {
        Color.clear.frame(width: 200, height: 200)
      })

    XCTAssertFalse(
      latch.isPresented,
      "clicking outside the sheet must dismiss it, including in the band the dim does not paint")
  }

  // MARK: - Driving a real click

  /// Dispatches a real `leftMouseDown`/`leftMouseUp` pair into a window hosting `view`.
  ///
  /// A synthetic click rather than a call to the closure, because the thing under test is whether the
  /// scrim's barrier is under the pointer at that point — which is a fact about the mounted view
  /// tree, not about the closure. `orderFrontRegardless` matches the transcript gesture harness: a
  /// test process is never the active application, and the window must not need to be.
  private func click(at point: CGPoint, on view: some View) {
    let size = Self.hostSize
    let host = NSHostingView(rootView: view)
    host.frame = NSRect(origin: .zero, size: size)
    let window = NSWindow(
      contentRect: NSRect(origin: .zero, size: size),
      styleMask: [.borderless], backing: .buffered, defer: false)
    window.contentView = host
    window.orderFrontRegardless()
    defer {
      window.orderOut(nil)
      window.contentView = nil
    }
    host.layoutSubtreeIfNeeded()

    let location = NSPoint(x: point.x, y: point.y)
    let down = NSEvent.mouseEvent(
      with: .leftMouseDown, location: location, modifierFlags: [], timestamp: 0,
      windowNumber: window.windowNumber, context: nil, eventNumber: 1, clickCount: 1, pressure: 1)
    let up = NSEvent.mouseEvent(
      with: .leftMouseUp, location: location, modifierFlags: [], timestamp: 0.01,
      windowNumber: window.windowNumber, context: nil, eventNumber: 2, clickCount: 1, pressure: 0)

    if let down { window.sendEvent(down) }
    if let up { window.sendEvent(up) }
  }

  /// Counts what the scrim ran, from inside a `@Sendable` closure the view captures.
  private final class Counter: @unchecked Sendable {
    private(set) var count = 0
    func increment() { count += 1 }
  }

  /// A `Binding<Bool>` a test can read back after the view under test has written to it.
  private final class Latch: @unchecked Sendable {
    var isPresented: Bool

    init(isPresented: Bool) {
      self.isPresented = isPresented
    }

    var binding: Binding<Bool> {
      Binding(get: { self.isPresented }, set: { self.isPresented = $0 })
    }
  }
}
