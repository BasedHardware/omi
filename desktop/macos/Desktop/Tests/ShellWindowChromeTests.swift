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
  /// band and a thresholded mouse monitor across the content. The native background-drag switch is
  /// deliberately off because AppKit mistakes hosted SwiftUI buttons for background.
  func testTheWindowIsStillMovableWithoutATitleBarToGrab() {
    let window = makeWindow()
    window.isMovableByWindowBackground = false

    ShellWindowChrome.dress(window)

    XCTAssertTrue(window.isMovable, "a floating window that cannot be moved is stranded")
    XCTAssertFalse(window.isMovableByWindowBackground)
    XCTAssertTrue(ShellWindowChrome.hasDragMonitor(in: window))
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
    XCTAssertTrue(
      ShellWindowChrome.shouldBeginDrag(at: NSPoint(x: 450, y: 300), in: window),
      "the replacement must allow a real drag to start over the same hosted SwiftUI surface")
    XCTAssertFalse(
      window.isMovableByWindowBackground,
      "native background dragging steals this hosted button's click before SwiftUI receives it")
    XCTAssertTrue(ShellWindowChrome.hasDragMonitor(in: window))
  }

  func testNativeDragControlsKeepTheirOwnGestures() {
    let window = makeWindow()
    let scrollView = NSScrollView(frame: NSRect(origin: .zero, size: Self.contentSize))
    window.contentView = scrollView
    ShellWindowChrome.dress(window)

    XCTAssertFalse(ShellWindowChrome.shouldBeginDrag(at: NSPoint(x: 450, y: 300), in: window))
  }

  // MARK: - Summoned vs anchored

  /// A summoned shell behaves like the thing it is: it comes up over whatever you were reading, and it
  /// is **still there** when you go back to that. Floating level is the half the user asked for by
  /// name — in front of whatever is behind it — and it is worth nothing on its own if the window
  /// deletes itself the moment the thing behind it takes focus.
  func testASummonedShellFloatsOverOtherAppsAndStaysThereWhenOneTakesFocus() {
    let window = makeWindow()

    ShellWindowChrome.dress(window, as: .summoned)

    XCTAssertEqual(window.level, .floating, "a summoned surface that sinks behind the app you called it over")
    XCTAssertFalse(
      window.hidesOnDeactivate,
      "clicking a browser, or a notification stealing focus, wipes the shell out mid-answer")
    XCTAssertTrue(window.collectionBehavior.contains(.fullScreenAuxiliary))
    XCTAssertTrue(window.collectionBehavior.contains(.moveToActiveSpace))
  }

  /// **The regression guard.** `hidesOnDeactivate` shipped with the summon conversion, and every route
  /// into `dress` runs on a window an earlier pass may already have set it on — launch dresses the
  /// window, a summon re-dresses it, finishing onboarding re-dresses it again. So the property is
  /// *written* `false` rather than left alone: a `dress` that only ever set it in one direction would
  /// leave a hidden shell hidden, and a shell that vanishes when you glance at another app produces no
  /// log line, no crash and no failing build — the user just finds an empty desktop where their answer
  /// was.
  func testDressingAWindowThatHidesItselfClearsThatInEitherPresentation() {
    for presentation in ShellWindowChrome.Presentation.allCases {
      let window = makeWindow()
      // The shape the previous build produced, and the shape a stale re-dress could hand back.
      window.hidesOnDeactivate = true

      ShellWindowChrome.dress(window, as: presentation)

      XCTAssertFalse(
        window.hidesOnDeactivate,
        "\(presentation) still orders itself out whenever another app takes focus")
    }
  }

  /// **The first-run guard.** Onboarding sends people to System Settings for microphone, screen
  /// recording and accessibility. A `.floating` window sits on top of the Settings pane and covers the
  /// control the user was just told to click, so before there is an account and a finished setup the
  /// same window is an ordinary one that can also take a Space of its own.
  func testAnAnchoredShellStaysOutOfTheWayOfTheSettingsPaneItSendsYouTo() {
    let window = makeWindow()
    ShellWindowChrome.dress(window, as: .summoned)

    ShellWindowChrome.dress(window, as: .anchored)

    XCTAssertEqual(window.level, .normal, "onboarding floats over the System Settings pane it just asked for")
    XCTAssertFalse(window.hidesOnDeactivate, "a permission trip deactivates the app; onboarding must survive it")
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
      "the transparent title bar remains a drag handle, and ⌘W routes from the mask")
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
      XCTAssertTrue(ShellWindowChrome.hasDragMonitor(in: window), "\(presentation) cannot be dragged")
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
