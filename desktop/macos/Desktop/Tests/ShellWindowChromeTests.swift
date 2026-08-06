import AppKit
import OmiTheme
import SwiftUI
import XCTest

@testable import Omi_Computer

/// Guards that the main window really is **the desktop with panels on it**, and that removing its
/// chrome removed nothing a user needs.
///
/// This file replaces `ShellGlassGroundTests`, which asserted the opposite shape: that an
/// `InkGlassView` was installed as the window's `contentView` so the whole window was one slab of
/// glass. That was the right guard for the bug it was written for — a SwiftUI `.background { … }` is
/// laid out inside the hosting view's safe area, and `.hiddenTitleBar` reports
/// `safeAreaInsets.top == 32`, so the ground began 32 pt down and the top strip showed the backdrop
/// straight through — and it is the wrong guard for the product, which wants no ground at all. The
/// claims below are the ones that are true now, and the two safety ones are new: hiding the traffic
/// lights is only acceptable if closing, minimising and moving all survive it.
@MainActor
final class ShellWindowChromeTests: XCTestCase {

  private static let contentSize = NSSize(width: 900, height: 600)

  /// A window in the same state the app's is: hidden title bar, full-size content view, SwiftUI inside.
  private func makeWindow() -> NSWindow {
    let window = NSWindow(
      contentRect: NSRect(origin: .zero, size: Self.contentSize),
      styleMask: [.titled, .closable, .miniaturizable, .resizable, .fullSizeContentView],
      backing: .buffered,
      defer: true)
    window.contentView = NSHostingView(rootView: Text("shell"))
    return window
  }

  // MARK: - No ground

  /// The claim the ground tests used to make, inverted: **nothing is installed between the window and
  /// the desktop.**
  ///
  /// The window keeps the view it was given, and it composites — `isOpaque = false` with a clear
  /// background — so a pixel no panel covers is the user's wallpaper. Either half alone is the same
  /// defect: an opaque window cannot show the desktop through it, and a window that paints its own
  /// `backgroundColor` slips a sheet in front of it.
  func testTheWindowHasNoGroundAndCompositesTheDesktopThrough() throws {
    let window = makeWindow()
    let hosted = try XCTUnwrap(window.contentView)
    window.isOpaque = true
    window.backgroundColor = .windowBackgroundColor
    window.appearance = NSAppearance(named: .darkAqua)

    ShellWindowChrome.dress(window)

    XCTAssertTrue(
      window.contentView === hosted,
      "the shell re-parented its content into a ground; panels position themselves now")
    XCTAssertNil(
      firstVisualEffectView(in: try XCTUnwrap(window.contentView)),
      "a material at the window root is a full-bleed slab, which is the ground drawn again")
    XCTAssertFalse(window.isOpaque)
    XCTAssertEqual(window.backgroundColor, .clear)
    XCTAssertEqual(
      window.appearance?.name, .aqua,
      "the glass is pinned light; a dark-pinned window renders the dark material and white type on it")
  }

  // MARK: - The chrome that went, and what replaced it

  /// The three coloured circles are gone. On a window with no frame behind them they hung on the
  /// wallpaper attached to nothing, which reads as a fault rather than as controls.
  func testTheStandardWindowButtonsAreHidden() throws {
    let window = makeWindow()

    ShellWindowChrome.dress(window)

    for button in ShellWindowChrome.hiddenStandardButtons {
      XCTAssertEqual(
        window.standardWindowButton(button)?.isHidden, true,
        "\(button) is still drawn over the desktop")
    }
  }

  /// **The safety claim.** `⌘W` and `⌘M` are routed by AppKit from the *style mask*, not from the
  /// buttons, so hiding the buttons must leave both bits set. A window a user can neither close nor
  /// minimise is a worse defect than an ugly one, and it has no runtime signal — it just does nothing
  /// when they press the key.
  func testHidingTheButtonsLeavesTheWindowClosableAndMiniaturizable() {
    let window = makeWindow()
    // A window built without them — the shape a future scene-construction change could produce.
    window.styleMask.subtract(ShellWindowChrome.keyboardWindowCommands)
    XCTAssertFalse(window.styleMask.contains(.closable))

    ShellWindowChrome.dress(window)

    XCTAssertTrue(window.styleMask.contains(.closable), "⌘W has nothing to route to")
    XCTAssertTrue(window.styleMask.contains(.miniaturizable), "⌘M has nothing to route to")
    XCTAssertTrue(
      window.styleMask.isSuperset(of: ShellWindowChrome.keyboardWindowCommands),
      "the keyboard path is the only close/minimise affordance left; it may never be dropped")
  }

  /// …and the window still moves. It has two handles: the transparent title bar over the reserved
  /// band (`GlassShell.titlebarClearance`, which is why the shell draws nothing up there) and the
  /// window background, which is what makes the top bar a drag handle without any view knowing it is
  /// one.
  func testTheWindowIsStillMovableWithoutATitleBarToGrab() {
    let window = makeWindow()
    window.isMovableByWindowBackground = false

    ShellWindowChrome.dress(window)

    XCTAssertTrue(window.isMovable, "a floating window that cannot be moved is stranded")
    XCTAssertTrue(
      window.isMovableByWindowBackground,
      "with no visible frame, the panels and the empty desktop between them are the drag handles")
    XCTAssertTrue(
      window.styleMask.contains(.titled),
      "the transparent title bar is the second drag handle; a borderless window loses it")
  }

  // MARK: - Summoned vs anchored

  /// A summoned shell behaves like the thing it is: it comes up over whatever you were reading, and
  /// clicking off it puts it back. `hidesOnDeactivate` is the whole click-outside dismissal — there is
  /// no click monitor anywhere, deliberately, because AppKit already owns this.
  func testASummonedShellFloatsOverOtherAppsAndPutsItselfAwayWhenYouClickOff() {
    let window = makeWindow()

    ShellWindowChrome.dress(window, as: .summoned)

    XCTAssertEqual(window.level, .floating, "a summoned surface that sinks behind the app you called it over")
    XCTAssertTrue(window.hidesOnDeactivate, "clicking away is the only dismissal that needs no affordance")
    XCTAssertTrue(window.collectionBehavior.contains(.fullScreenAuxiliary))
    XCTAssertTrue(window.collectionBehavior.contains(.moveToActiveSpace))
  }

  /// **The first-run guard.** Onboarding sends people to System Settings for microphone, screen
  /// recording and accessibility, and every trip deactivates this app. A shell that auto-hid would
  /// vanish on the way out to grant the thing it just asked for, so before there is an account and a
  /// finished setup the same window is an ordinary one.
  func testAnAnchoredShellStaysUpSoAPermissionTripCannotStrandOnboarding() {
    let window = makeWindow()
    ShellWindowChrome.dress(window, as: .summoned)

    ShellWindowChrome.dress(window, as: .anchored)

    XCTAssertFalse(window.hidesOnDeactivate, "onboarding disappears the moment the user grants a permission")
    XCTAssertEqual(window.level, .normal)
    XCTAssertTrue(window.collectionBehavior.contains(.fullScreenPrimary))
  }

  /// The two Space behaviours are mutually exclusive, and `dress` runs repeatedly on one window as the
  /// user finishes onboarding. A pass that only ever *added* its own would leave both set, which AppKit
  /// resolves by giving the window neither.
  func testSwitchingPresentationsNeverLeavesBothFullScreenBehavioursSet() {
    let window = makeWindow()

    ShellWindowChrome.dress(window, as: .anchored)
    ShellWindowChrome.dress(window, as: .summoned)

    XCTAssertFalse(
      window.collectionBehavior.contains(.fullScreenPrimary),
      "a window carrying both full-screen behaviours loses full-screen entirely")
    XCTAssertTrue(window.collectionBehavior.contains(.fullScreenAuxiliary))
  }

  /// The summoned shell wears its own glass, not the titled window's. The difference is one property
  /// and it is visible: AppKit's frame shadow on a window that is a transparent rectangle around
  /// several inset panels draws a hard edge around empty air.
  func testTheSummonedShellWearsGlassThatLeavesTheShadowToItsPanels() {
    XCTAssertEqual(ShellWindowChrome.glassKind(for: .summoned), .summoned)
    XCTAssertEqual(ShellWindowChrome.glassKind(for: .anchored), .titled)
    XCTAssertFalse(
      WindowGlass.drawsSystemShadow(.summoned),
      "the panels inside draw their own ambient shadow; AppKit's would trace the transparent frame")
    XCTAssertTrue(
      WindowGlass.hasTitlebar(.summoned),
      "the transparent title bar is one of the shell's two drag handles, and ⌘W routes from the mask")
  }

  /// Neither presentation may drop the keyboard close/minimise route or the drag handles — the
  /// buttons are hidden in both, so those are the only affordances left.
  func testBothPresentationsKeepTheKeyboardCommandsAndTheDragHandles() {
    for presentation in ShellWindowChrome.Presentation.allCases {
      let window = makeWindow()
      window.styleMask.subtract(ShellWindowChrome.keyboardWindowCommands)

      ShellWindowChrome.dress(window, as: presentation)

      XCTAssertTrue(
        window.styleMask.isSuperset(of: ShellWindowChrome.keyboardWindowCommands),
        "\(presentation) has no ⌘W or ⌘M and no buttons either")
      XCTAssertTrue(window.isMovableByWindowBackground, "\(presentation) cannot be dragged anywhere")
    }
  }

  // MARK: - Idempotence

  /// Launch dresses the window and a summon re-dresses it. A second pass must re-assert, never
  /// accumulate or undo — the summon path runs on a window that has already been used.
  func testDressingTheWindowTwiceIsIdempotent() throws {
    let window = makeWindow()
    let hosted = try XCTUnwrap(window.contentView)

    ShellWindowChrome.dress(window)
    // Something re-asserted the system's own defaults between the two passes.
    window.standardWindowButton(.closeButton)?.isHidden = false
    window.isOpaque = true
    ShellWindowChrome.dress(window)

    XCTAssertTrue(window.contentView === hosted)
    XCTAssertFalse(window.isOpaque)
    XCTAssertEqual(window.standardWindowButton(.closeButton)?.isHidden, true)
    XCTAssertTrue(window.styleMask.contains(.closable))
  }

  private func firstVisualEffectView(in view: NSView) -> NSVisualEffectView? {
    if let material = view as? NSVisualEffectView { return material }
    for subview in view.subviews {
      if let found = firstVisualEffectView(in: subview) { return found }
    }
    return nil
  }
}
