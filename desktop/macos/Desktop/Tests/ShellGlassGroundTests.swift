import AppKit
import OmiTheme
import SwiftUI
import XCTest

@testable import Omi_Computer

/// Guards that the main window really has **one ground, and that it is the whole window**.
///
/// The regression this file exists for shipped as a window that looked half-converted: the top ~32 pt
/// — the band a `.hiddenTitleBar` window puts the traffic lights in — had no ground at all, and the
/// glass only began below it. Measured on the running app over a solid black backdrop, that band read
/// `(0,0,0)`: the backdrop straight through, no material and no scrim.
///
/// The cause was the *owner*, not the drawing. The ground was a SwiftUI `.background { … }` at the root
/// of `DesktopHomeView`, and a SwiftUI background is laid out inside the hosting view's safe area —
/// which for this window is `top: 32`. Nothing about the source looked wrong, nothing logged, and
/// `.ignoresSafeArea()` on the content did not move it.
///
/// So the assertions here are geometric and behavioural: mount a real `NSHostingView` in a real
/// `.fullSizeContentView` window, run the real installer, and read back where the ground actually is.
/// Every case fails on the shipped shape.
@MainActor
final class ShellGlassGroundTests: XCTestCase {

  private static let contentSize = NSSize(width: 900, height: 600)

  /// A window in the same state the app's is: hidden title bar, full-size content view, SwiftUI inside.
  private func makeWindow() -> NSWindow {
    let window = NSWindow(
      contentRect: NSRect(origin: .zero, size: Self.contentSize),
      styleMask: [.titled, .closable, .resizable, .fullSizeContentView],
      backing: .buffered,
      defer: true)
    window.contentView = NSHostingView(rootView: Text("shell"))
    return window
  }

  /// The claim: the ground **is** the content view, so there is no band of the window it misses.
  ///
  /// Asserting the ground's frame against `contentLayoutRect` would pass on the broken shape — that
  /// rect already excludes the title bar. The window's *content view bounds* is the rect that has to be
  /// covered, and the title bar band is inside it precisely because the window is full-size-content.
  func testGroundCoversTheWholeContentViewIncludingTheTitlebarBand() throws {
    let window = makeWindow()
    let hosted = try XCTUnwrap(window.contentView)

    let ground = ShellGlassGround.install(in: window)
    window.layoutIfNeeded()

    XCTAssertTrue(
      window.contentView === ground,
      "the ground is the content view; anything between it and the window can paint over the desktop")
    XCTAssertEqual(
      ground.bounds.size, Self.contentSize,
      "a ground smaller than the content view leaves a strip of bare window")
    XCTAssertEqual(
      ground.panel.frame, ground.bounds,
      "the shell ground is full-bleed: the panel fills its host, corner to corner")

    // The band the traffic lights sit in. The shipped SwiftUI background started at y = 32 here.
    let materialInWindow = ground.material.convert(ground.material.bounds, to: nil)
    XCTAssertEqual(
      materialInWindow, NSRect(origin: .zero, size: Self.contentSize),
      "the material must reach the window's own edges — a 32 pt gap is the safe-area inset returning")

    XCTAssertTrue(
      hosted.isDescendant(of: ground.panel),
      "the SwiftUI content must be hosted *inside* the ground, never beside or under it")
  }

  /// A window that is glass on launch and bare after a drag is the same defect on a delay.
  func testGroundStillFillsTheContentViewAfterAResize() throws {
    let window = makeWindow()
    let ground = ShellGlassGround.install(in: window)
    window.layoutIfNeeded()

    let resized = NSSize(width: 1280, height: 820)
    window.setContentSize(resized)
    window.layoutIfNeeded()
    ground.layoutSubtreeIfNeeded()

    XCTAssertEqual(ground.bounds.size, resized)
    XCTAssertEqual(
      ground.material.convert(ground.material.bounds, to: nil),
      NSRect(origin: .zero, size: resized),
      "the ground stopped tracking the window; autoresizing is what keeps one ground one ground")
    XCTAssertEqual(
      try XCTUnwrap(ground.panel.subviews.last).frame.size, resized,
      "the hosted content stopped tracking the panel")
  }

  /// Launch installs the ground and a summon re-applies it. A second pass must re-assert, never stack:
  /// two `NSVisualEffectView`s over the same desktop is the muddy-panel failure `InkGlass` prevents.
  func testDressingTheWindowTwiceLeavesExactlyOneGround() throws {
    let window = makeWindow()
    let hosted = try XCTUnwrap(window.contentView)

    let first = ShellGlassGround.dress(window)
    let second = ShellGlassGround.dress(window)
    window.layoutIfNeeded()

    XCTAssertTrue(first === second, "a second pass built a second ground")
    XCTAssertEqual(
      countVisualEffectViews(in: try XCTUnwrap(window.contentView)), 1,
      "exactly one material per window — a second scrim halves the passthrough the first was tuned for")
    XCTAssertTrue(hosted.isDescendant(of: first.panel), "the content was re-parented out of the ground")
  }

  /// The two halves are one decision. A window wearing the glass with no ground is a transparent hole;
  /// a ground in a window that still paints its own background has an opaque sheet in front of the
  /// desktop. Both render, and neither is glass — so the shell only ever gets them together.
  func testDressingAWindowBothWearsTheGlassAndInstallsTheGround() throws {
    let window = makeWindow()
    window.isOpaque = true
    window.backgroundColor = .windowBackgroundColor
    window.appearance = NSAppearance(named: .darkAqua)

    let ground = ShellGlassGround.dress(window)

    XCTAssertFalse(window.isOpaque)
    XCTAssertEqual(window.backgroundColor, .clear)
    XCTAssertEqual(window.appearance?.name, .aqua)
    XCTAssertTrue(window.contentView === ground)
    XCTAssertEqual(
      ground.panel.appearance?.name, InkGlass.appearanceName,
      "the panel is the light pin everything hosted inside it resolves against")
  }

  /// The shell's ground draws no shadow of its own — the titled window's frame already casts one.
  func testTheShellGroundCastsNoSecondShadow() throws {
    let window = makeWindow()
    let ground = ShellGlassGround.install(in: window)
    window.layoutIfNeeded()

    XCTAssertNil(ground.style.shadow)
    XCTAssertEqual(ground.style.cornerRadius, 0, "a rounded ground inside a square window shows corners")
    XCTAssertTrue(WindowGlass.drawsSystemShadow(.titled))
  }

  private func countVisualEffectViews(in view: NSView) -> Int {
    (view is NSVisualEffectView ? 1 : 0)
      + view.subviews.reduce(0) { $0 + countVisualEffectViews(in: $1) }
  }
}
