import AppKit
import OmiTheme
import SwiftUI
import XCTest

@testable import Omi_Computer

/// Guards that the main window really is **the desktop with panels on it**, and that removing its
/// chrome removed nothing a user needs.
///
/// This file replaces `ShellGlassGroundTests`, which asserted that an `InkGlassView` was installed as
/// the window's `contentView` so the whole window was one slab of glass. That was the right guard for
/// the earlier safe-area seam, but the shell's current contract is a white AppKit ground with panel
/// styling inside it. The claims below are the ones that are true now, and the two safety ones are new:
/// hiding the traffic lights is only acceptable if closing, minimising and moving all survive it.
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

  /// The window keeps the view it was given, and it composites — `isOpaque = false` with a clear
  /// background — so a pixel no panel covers is the user's wallpaper.
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

  /// The three coloured circles are gone. On a window with no frame behind them they hung attached to
  /// nothing, which reads as a fault rather than as controls.
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
  /// band and a thresholded simultaneous SwiftUI gesture on the visible top bar. The native
  /// background-drag switch is deliberately off because AppKit mistakes hosted buttons for background.
  func testTheWindowIsStillMovableWithoutATitleBarToGrab() {
    let window = makeWindow()
    window.isMovableByWindowBackground = false

    ShellWindowChrome.dress(window)

    XCTAssertTrue(window.isMovable, "a floating window that cannot be moved is stranded")
    XCTAssertFalse(window.isMovableByWindowBackground)
    XCTAssertTrue(
      window.styleMask.contains(.titled),
      "the transparent title bar remains an independent drag handle")
  }

  func testHostedSwiftUIButtonsDoNotEnableNativeBackgroundDragging() throws {
    let window = makeWindow()
    let host = NSHostingView(
      rootView: Button("Rewind") {}
        .buttonStyle(.plain)
        .frame(width: Self.contentSize.width, height: Self.contentSize.height))
    host.frame = NSRect(origin: .zero, size: Self.contentSize)
    window.contentView = host
    ShellWindowChrome.dress(window)
    host.layoutSubtreeIfNeeded()

    let hit = try XCTUnwrap(host.hitTest(NSPoint(x: 450, y: 300)))
    XCTAssertTrue(
      hit.mouseDownCanMoveWindow,
      "the regression fixture no longer reproduces AppKit's SwiftUI misclassification")
    XCTAssertFalse(
      window.isMovableByWindowBackground,
      "native background dragging steals this hosted button's click before SwiftUI receives it")
  }

  func testLegacyWindowDragUsesSwiftUITranslation() {
    XCTAssertEqual(
      ShellWindowChrome.draggedOrigin(
        windowOrigin: NSPoint(x: 100, y: 200),
        translation: CGSize(width: 75, height: 40)),
      NSPoint(x: 175, y: 160))
  }

  // MARK: - Summoned vs anchored

  /// **The app-switcher guard.** The shell used to be a `.floating` panel with `hidesOnDeactivate`, so
  /// switching to any other app ordered it out — and a window that is not on screen is in no switcher's
  /// list, which left ⌥-Tab and ⌘-Tab window cycling with no Omi window to offer at all. These two
  /// properties are the whole difference between an application window and an overlay, so they are
  /// asserted directly rather than through the presentation that happens to be applied.
  func testASummonedShellStaysOnScreenAtNormalLevelSoWindowSwitchersCanOfferIt() {
    let window = makeWindow()

    ShellWindowChrome.dress(window, as: .summoned)

    XCTAssertEqual(window.level, .normal, "an overlay level is not a window any switcher will cycle to")
    XCTAssertFalse(window.hidesOnDeactivate, "AppKit orders a hidden window out of every switcher's list")
    XCTAssertTrue(window.collectionBehavior.contains(.fullScreenAuxiliary))
    XCTAssertTrue(window.collectionBehavior.contains(.moveToActiveSpace))
  }

  /// `dress` runs repeatedly as auth and onboarding change presentation, and no presentation may
  /// reintroduce the auto-hide: a signed-in shell has to survive a trip to another app for the same
  /// reason onboarding has to survive a trip to System Settings.
  func testNoPresentationEverMakesTheShellHideItselfOnDeactivate() {
    let window = makeWindow()

    for presentation in ShellWindowChrome.Presentation.allCases {
      ShellWindowChrome.dress(window, as: presentation)
      XCTAssertFalse(window.hidesOnDeactivate, "\(presentation) hides the shell from every window switcher")
      XCTAssertEqual(window.level, .normal, "\(presentation) puts the shell at a level switchers skip")
    }
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

  /// The shell wears its own glass, not the titled window's — **in both presentations.** The window is
  /// transparent while the inset panels retain their own glass and ambient shadows.
  ///
  /// Anchored was `.titled` while the window had a full-bleed glass ground, and kept it after the
  /// ground was retired. The current mapping keeps the shell's visible depth cue with its panel surfaces.
  func testTheShellWearsGlassThatLeavesTheShadowToItsPanelsInBothPresentations() {
    XCTAssertEqual(ShellWindowChrome.glassKind, .summoned)
    XCTAssertFalse(
      WindowGlass.drawsSystemShadow(ShellWindowChrome.glassKind),
      "the panels inside draw their own ambient shadow; the shell does not add an outer frame shadow")
    XCTAssertTrue(
      WindowGlass.hasTitlebar(ShellWindowChrome.glassKind),
      "the hidden title bar stays so ⌘W routes from the mask; the top bar occupies that band")
  }

  /// …and `dress` really applies it, in both presentations. The mapping above is a value; this is the
  /// window, and a first run that ordered a system shadow around the white shell is the reason the value
  /// alone is not enough of a claim.
  func testNeitherPresentationLetsAppKitDrawTheWindowsOwnShadow() {
    for presentation in ShellWindowChrome.Presentation.allCases {
      let window = makeWindow()
      window.hasShadow = true
      ShellWindowChrome.dress(window, as: presentation)
      XCTAssertFalse(
        window.hasShadow,
        """
        \(presentation) leaves AppKit drawing the window's frame shadow. The panels inside it carry \
        `InkGlassShadow.ambient`, so the shell must not add a second outer frame shadow.
        """)
      XCTAssertFalse(window.isOpaque, "\(presentation) must stay transparent for the desktop to show")
    }
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
      XCTAssertFalse(window.isMovableByWindowBackground, "\(presentation) can steal hosted button clicks")
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

  /// The shell must be dressed by the view that is actually mounted in it, not by a one-shot timed
  /// search of `NSApp.windows`. A cold SwiftUI scene can appear after that timer has already fired.
  func testMountedAttachmentDressesItsExactContainingWindow() throws {
    let window = makeWindow()
    let attachment = ShellWindowAttachmentView(frame: .zero)
    window.contentView = attachment
    window.isOpaque = true
    window.backgroundColor = .windowBackgroundColor
    window.hasShadow = true
    for button in ShellWindowChrome.hiddenStandardButtons {
      window.standardWindowButton(button)?.isHidden = false
    }

    attachment.reassertIfNeeded(force: true)

    let presentation = ShellSummon.presentation()
    XCTAssertTrue(ShellWindowChrome.isDressed(window, as: presentation))
    XCTAssertFalse(window.isOpaque)
    XCTAssertEqual(window.backgroundColor, .clear)
    XCTAssertFalse(window.hasShadow)
    for button in ShellWindowChrome.hiddenStandardButtons {
      XCTAssertEqual(window.standardWindowButton(button)?.isHidden, true)
    }
  }

  func testDressedContractDetectsRecreatedSystemChrome() {
    let window = makeWindow()
    ShellWindowChrome.dress(window, as: .summoned)
    XCTAssertTrue(ShellWindowChrome.isDressed(window, as: .summoned))

    window.standardWindowButton(.closeButton)?.isHidden = false

    XCTAssertFalse(
      ShellWindowChrome.isDressed(window, as: .summoned),
      "a SwiftUI title-bar rebuild must be visible to the attachment's repair guard")
  }

  private func firstVisualEffectView(in view: NSView) -> NSVisualEffectView? {
    if let material = view as? NSVisualEffectView { return material }
    for subview in view.subviews {
      if let found = firstVisualEffectView(in: subview) { return found }
    }
    return nil
  }
}
