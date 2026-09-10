import AppKit
import OmiTheme
import SwiftUI
import XCTest

@testable import Omi_Computer

/// **One click on a switch flips it exactly once — including a click that drags.**
///
/// `OmiToggleStyle` used to activate on a bare `.onTapGesture`. That had two verified defects:
///
/// 1. **Drag intolerance.** A tap gesture fails when the pointer moves between down and up, and a
///    human click often moves a few points inside the control — the click reads as dead and the
///    user must click again until a clean tap lands. This is the shape of the QA observation on
///    2026-09-09 (Settings toggles "flaky, click repeatedly until one lands"): a `Button`'s
///    activation tracks down-then-up anywhere inside the control, so the same event sequence that
///    a tap gesture drops still fires it.
/// 2. **No accessibility.** A bare gesture on drawn shapes produces no accessibility element, so
///    the app's switches had nothing for assistive tech to find; `Button` is an element by
///    construction (Apple's documented pattern for custom `ToggleStyle`s). This claim is held by
///    construction rather than by a live query: the Settings page wraps its content in an
///    `AXOpaqueProviderGroup` whose subtree System Events cannot see (and often serves stale), a
///    pre-existing page-level opacity that hides every control on the page equally — before and
///    after this change alike. Fixing that exposure is a separate, page-level follow-up.
///
/// A custom `ToggleStyle` gets no native activation from the framework on macOS — the style owns
/// activation (Apple's canonical pattern wraps the visual in a `Button` that toggles
/// `configuration.isOn`) — so these tests pin that the one activation path exists, fires exactly
/// once, and tolerates a small drag. Driven with the `ShellModalScrimDismissTests` harness: a real
/// `Toggle` wearing the production style in an `NSHostingView`, synthetic `NSEvent` pairs through
/// `sendEvent`, recognised synchronously — nothing to wait for.
@MainActor
final class OmiToggleStyleActivationTests: XCTestCase {

  private static let hostSize = CGSize(width: 300, height: 300)

  // MARK: - One click, exactly one activation

  /// A click whose up lands where its down did must write the binding exactly once.
  ///
  /// Two writes is a double-activation (a dead click: on, then immediately off); zero means
  /// activation went missing entirely. Both directions are asserted: the count of writes, and the
  /// state actually flipping.
  func testOneClickOnTheStyledToggleWritesTheBindingExactlyOnce() throws {
    let latch = SetCountingLatch(isOn: false)

    click(
      on: styledToggle(latch),
      down: Self.center,
      up: Self.center)

    XCTAssertEqual(
      latch.setCount, 1,
      "one click on the switch must write the binding exactly once — two writes is a "
        + "double-activation (a dead click), zero means activation went missing")
    XCTAssertTrue(latch.isOn, "one click on an off switch must leave it on")
  }

  /// The claim this file exists for: a click that drags a few points *inside* the switch between
  /// down and up must still activate it exactly once.
  ///
  /// A bare tap gesture drops this event sequence — the drag fails the tap recognition, the click
  /// reads as dead, and the user must click again. A `Button` fires on up-inside-bounds however
  /// far the pointer wandered within the control.
  func testAClickThatDragsInsideTheSwitchStillWritesTheBindingExactlyOnce() throws {
    let latch = SetCountingLatch(isOn: false)

    // Five points of drag, staying well inside the 36×20 track. A human click that isn't a clean
    // tap moves about this much; the switch's own width is 36, so the whole sequence stays on it.
    click(
      on: styledToggle(latch),
      down: Self.center,
      up: CGPoint(x: Self.center.x + 5, y: Self.center.y))

    XCTAssertEqual(
      latch.setCount, 1,
      "a click that drags inside the switch must still activate it exactly once — a control "
        + "that only answers clean taps reads as flaky")
    XCTAssertTrue(latch.isOn, "a dragged click on an off switch must leave it on")
  }

  // MARK: - The style's one activation path

  /// No file under `Sources/Theme/` may activate a control with a bare tap gesture, and the
  /// toggle style must own exactly one activation path through a `Button`.
  ///
  /// A bare `.onTapGesture` is drag-intolerant and invisible to accessibility; gesture arbitration
  /// is framework-internal so the class cannot be expressed behaviorally for every style body at
  /// once. The click tests above hold the behavior for the toggle; this holds the boundary for the
  /// whole style module.
  func testThemeControlStylesActivateThroughButtonsNotBareTapGestures() throws {
    let themeRoot = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources/Theme")
    let swiftFiles = try FileManager.default
      .subpathsOfDirectory(atPath: themeRoot.path)
      .filter { $0.hasSuffix(".swift") }
      .sorted()
    XCTAssertFalse(
      swiftFiles.isEmpty, "precondition: the Theme module still exists where this test looks")

    var toggleStyleSource: String?
    for relativePath in swiftFiles {
      // omi-test-quality: source-inspection -- static contract: Theme holds the custom control styles; activation is a Button (drag-tolerant, an accessibility element), and a bare tap gesture is neither.
      let source = try String(contentsOf: themeRoot.appendingPathComponent(relativePath), encoding: .utf8)
      XCTAssertFalse(
        source.contains(".onTapGesture"),
        """
        \(relativePath) activates with a bare tap gesture. A tap gesture drops any click that \
        drags inside the control and produces no accessibility element — wrap the control's \
        visual in a Button that drives its state instead.
        """)
      if relativePath.hasSuffix("OmiToggleStyle.swift") {
        toggleStyleSource = source
      }
    }

    let style = try XCTUnwrap(toggleStyleSource, "the toggle style file is where this test looks")
    XCTAssertTrue(
      style.contains("Button {") && style.contains("configuration.isOn.toggle()"),
      "the toggle style's visual must be wrapped in a Button that toggles configuration.isOn — "
        + "a custom ToggleStyle has no native activation on macOS, so removing the Button would "
        + "leave every switch in the app dead")
  }

  // MARK: - The production control under test

  private func styledToggle(_ latch: SetCountingLatch) -> some View {
    Toggle("", isOn: latch.binding)
      .toggleStyle(OmiToggleStyle())
      .frame(width: 36, height: 20)
      .position(x: Self.hostSize.width / 2, y: Self.hostSize.height / 2)
  }

  private static var center: CGPoint {
    CGPoint(x: hostSize.width / 2, y: hostSize.height / 2)
  }

  // MARK: - Driving a real click

  /// Dispatches a real `leftMouseDown`/`leftMouseUp` pair into a window hosting `view` — the
  /// `ShellModalScrimDismissTests` harness. Synthetic clicks rather than calls into the style,
  /// because the thing under test is whether one physical click activates the control exactly
  /// once, which is a fact about event/gesture routing, not about any one handler. The host is
  /// square and the view is pinned to its center, so the SwiftUI center and the AppKit center
  /// (origin bottom-left) are the same point.
  private func click(on view: some View, down: CGPoint, up: CGPoint) {
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

    let toAppKit: (CGPoint) -> NSPoint = { point in
      NSPoint(x: point.x, y: size.height - point.y)
    }
    let downEvent = NSEvent.mouseEvent(
      with: .leftMouseDown, location: toAppKit(down), modifierFlags: [], timestamp: 0,
      windowNumber: window.windowNumber, context: nil, eventNumber: 1, clickCount: 1, pressure: 1)
    let upEvent = NSEvent.mouseEvent(
      with: .leftMouseUp, location: toAppKit(up), modifierFlags: [], timestamp: 0.01,
      windowNumber: window.windowNumber, context: nil, eventNumber: 2, clickCount: 1, pressure: 0)

    if let downEvent { window.sendEvent(downEvent) }
    if let upEvent { window.sendEvent(upEvent) }
  }

  /// A `Binding<Bool>` a test can read back after the view under test has written to it, plus
  /// the count of those writes — one click must produce exactly one.
  private final class SetCountingLatch: @unchecked Sendable {
    private(set) var isOn: Bool
    private(set) var setCount = 0

    init(isOn: Bool) {
      self.isOn = isOn
    }

    var binding: Binding<Bool> {
      Binding(
        get: { self.isOn },
        set: {
          self.setCount += 1
          self.isOn = $0
        })
    }
  }
}
