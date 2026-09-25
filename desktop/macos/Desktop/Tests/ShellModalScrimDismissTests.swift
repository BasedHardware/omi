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
  /// The paint is inset from its host; the barrier is not. A barrier that shrank to the paint would
  /// leave the inset band inert: the modal would look modal and refuse to close when you clicked in
  /// it. Probed in every undimmed band the surface actually has *and* in the middle, so a barrier
  /// that shrank to the paint fails on the first while the second still proves the harness can see
  /// a tap at all.
  ///
  /// Which band exists is the surface's own arithmetic, not a constant restated here: since the
  /// shell was flushed to its glass the lane fills the window, so `.wholeShell` has no undimmed
  /// side band left, while a `.contentArea` surface still leaves the page's top gap above the dim.
  /// Deriving the probes from `ShellModalScrimLayout` keeps this exercising whichever bands the
  /// product has rather than the ones it had when this was written.
  func testAClickOutsideThePaintedDimStillRunsTheDismiss() throws {
    let size = Self.hostSize
    var probed = 0

    for bounds in ShellModalScrimBounds.allCases {
      for (label, point) in undimmedProbes(for: bounds, in: size) {
        probed += 1
        let dismissals = Counter()
        click(
          at: point,
          on: ShellModalScrim(onTap: { dismissals.increment() })
            .shellModalScrimBounds(bounds))

        XCTAssertEqual(
          dismissals.count, 1,
          "a click \(label) of a \(bounds) dim must still dismiss the modal — modality covers the "
            + "host, only the paint is bounded to the surface")
      }

      let onTheDim = Counter()
      click(
        at: CGPoint(x: size.width / 2, y: size.height / 2),
        on: ShellModalScrim(onTap: { onTheDim.increment() })
          .shellModalScrimBounds(bounds))
      XCTAssertEqual(
        onTheDim.count, 1, "a click on a \(bounds) dim must dismiss the modal")
    }

    XCTAssertGreaterThan(
      probed, 0,
      "precondition: at least one surface still insets its paint, so there is undimmed host to "
        + "click; if this ever reaches zero the barrier's extra extent is no longer observable here")
  }

  /// Points inside `bounds`' host that the dim does **not** paint, derived from the layout itself.
  private func undimmedProbes(
    for bounds: ShellModalScrimBounds,
    in size: CGSize
  ) -> [(String, CGPoint)] {
    let sideBand = (size.width - ShellModalScrimLayout.paintedWidth(bounds, in: size.width)) / 2
    let topBand = ShellModalScrimLayout.topInset(bounds)
    let bottomBand = ShellModalScrimLayout.bottomInset(bounds)

    var probes: [(String, CGPoint)] = []
    if sideBand > 1 {
      probes.append(("beside the dim", CGPoint(x: sideBand / 2, y: size.height / 2)))
    }
    // AppKit's origin is bottom-left, so the paint's *top* inset is the band at the high end of y.
    if topBand > 1 {
      probes.append(("above the dim", CGPoint(x: size.width / 2, y: size.height - topBand / 2)))
    }
    if bottomBand > 1 {
      probes.append(("below the dim", CGPoint(x: size.width / 2, y: bottomBand / 2)))
    }
    return probes
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
  /// tree, not about the closure. The test-only presenter keeps that real window composited without
  /// covering or intercepting the user's desktop.
  private func click(at point: CGPoint, on view: some View) {
    let size = Self.hostSize
    let host = NSHostingView(rootView: view)
    host.frame = NSRect(origin: .zero, size: size)
    let window = NSWindow(
      contentRect: NSRect(origin: .zero, size: size),
      styleMask: [.borderless], backing: .buffered, defer: false)
    window.contentView = host
    NonintrusiveTestWindow.orderIn(window)
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
