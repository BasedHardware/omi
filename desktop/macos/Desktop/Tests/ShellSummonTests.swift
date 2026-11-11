import AppKit
import OmiTheme
import XCTest

@testable import Omi_Computer

/// Guards the two things that make a summoned shell feel summoned rather than merely floating: it
/// lands where you called it from, and it goes away when you are done with it.
///
/// Every placement claim here is driven through the pure geometry rather than through a window,
/// because the case that actually breaks — a second display, a display that shrank, a display that
/// went away — cannot be produced on a CI runner with one screen. Putting the arithmetic behind
/// `NSWindow` would leave exactly the multi-display behaviour untested, which is the behaviour this
/// feature exists for.
final class ShellSummonTests: XCTestCase {

  private let laptop = NSRect(x: 0, y: 0, width: 1512, height: 900)
  private let studio = NSRect(x: 1512, y: -200, width: 2560, height: 1440)

  // MARK: - Global launch toggle

  @MainActor
  func testGlobalLaunchToggleSummonsAHiddenShell() {
    let window = makeShellWindow()

    XCTAssertFalse(window.isVisible)
    XCTAssertEqual(ShellSummon.toggleAction(for: window, isAppActive: false), .summon)
  }

  @MainActor
  func testGlobalLaunchToggleDismissesTheShellYouAreAlreadyIn() {
    let window = makeShellWindow()
    NonintrusiveTestWindow.orderIn(window)
    defer { window.orderOut(nil) }

    XCTAssertTrue(window.isVisible)
    XCTAssertEqual(ShellSummon.toggleAction(for: window, isAppActive: true), .dismiss)
  }

  /// **The chord is not a hide button.** The shell stays on screen behind whatever you are working in,
  /// so "visible" alone would turn every Open Omi press from another app into a dismissal — the chord
  /// would appear to do nothing, or worse, put Omi away just as you asked for it.
  @MainActor
  func testGlobalLaunchToggleSummonsAVisibleShellWhenYouAreInAnotherApp() {
    let window = makeShellWindow()
    NonintrusiveTestWindow.orderIn(window)
    defer { window.orderOut(nil) }

    XCTAssertTrue(window.isVisible)
    XCTAssertEqual(
      ShellSummon.toggleAction(for: window, isAppActive: false),
      .summon,
      "Open Omi pressed from another app must bring Omi forward, never hide it")
  }

  @MainActor
  func testGlobalLaunchShortcutNeverDismissesAnchoredSignInOrOnboarding() {
    let window = makeShellWindow()
    NonintrusiveTestWindow.orderIn(window)
    defer { window.orderOut(nil) }

    XCTAssertEqual(
      ShellSummon.toggleAction(for: window, presentation: .anchored, isAppActive: true),
      .summon,
      "Command-O must focus the only setup surface rather than hide it")
  }

  @MainActor
  func testPermissionSuspensionRestoresTheVisibleShellWithoutRepositioningIt() throws {
    let window = makeShellWindow()
    window.title = OMIApp.currentWindowTitle
    let placed = NSRect(x: 220, y: 140, width: 960, height: 700)
    window.setFrame(placed, display: false)
    NonintrusiveTestWindow.orderIn(window, preserveFrame: true)
    let captured = window.frame
    defer { window.orderOut(nil) }
    // A session whose window server cannot even HOLD the placed frame (headless
    // review harnesses clamp it to 1×1 points) cannot express any
    // frame-preservation contract; asserting there tests the harness, not the
    // shell. Real sessions keep the placed size and run the full assertion.
    try XCTSkipIf(
      captured.size != placed.size,
      "window server session cannot hold frames (placed \(placed), got \(captured)); "
        + "frame preservation is only testable in a real session")

    XCTAssertTrue(ShellSummon.suspendForPermissionPrompt())
    XCTAssertFalse(window.isVisible)

    ShellSummon.restoreAfterPermissionPrompt()

    XCTAssertTrue(window.isVisible)
    XCTAssertEqual(window.frame, captured, "permission UI must not re-center the user's shell")
  }

  @MainActor
  func testPermissionSuspensionDoesNotReopenAnAlreadyHiddenShell() {
    let window = makeShellWindow()
    window.title = OMIApp.currentWindowTitle
    window.orderOut(nil)

    XCTAssertFalse(ShellSummon.suspendForPermissionPrompt())
  }

  // MARK: - Landing

  /// The first summon on a display centres the panel there. Not top-left, not wherever the previous
  /// display left it — a surface you called up belongs under your eyes.
  func testAShellNeverPlacedOnThisDisplayArrivesCentredOnIt() {
    let frame = ShellSummonPlacement.frame(remembered: nil, visibleFrame: studio)

    XCTAssertEqual(frame.size, ShellSummonPlacement.defaultSize)
    XCTAssertEqual(frame.midX, studio.midX, accuracy: 0.5, "a summoned panel is centred, not cornered")
    XCTAssertEqual(frame.midY, studio.midY, accuracy: 0.5)
  }

  /// …and the default really is a panel rather than the managed window it replaced. It still has to
  /// clear the floor every destination lays out to, or the shell arrives already clipping content.
  func testTheDefaultPanelIsSmallerThanAWindowButStillFitsTheDestinations() {
    XCTAssertEqual(
      ShellSummonPlacement.defaultSize.width, ChatComposerLayout.contentLaneMaxWidth,
      "a summoned panel is the hugged glass, not a sheet that stretches with the display")
    XCTAssertLessThan(
      ShellSummonPlacement.defaultSize.width, 1200,
      "1200×800 was the managed-window default; a summoned panel must read smaller than that")
    XCTAssertGreaterThanOrEqual(
      ShellSummonPlacement.defaultSize.width, DesktopWindowLayoutPolicy.minimumContentSize.width)
    XCTAssertGreaterThanOrEqual(
      ShellSummonPlacement.defaultSize.height, DesktopWindowLayoutPolicy.minimumContentSize.height)
  }

  func testResetWindowSizeReturnsToTheActualSummonedPanelSize() {
    XCTAssertEqual(
      WindowSizeResetPolicy.defaultSize,
      ShellSummonPlacement.defaultSize,
      "reset must not revive the obsolete 1200×800 managed-window geometry")
  }

  /// A remembered frame already at the hug size is restored exactly. This is the payoff of
  /// per-display memory: the second summon on a display puts the shell back where you left it.
  func testARememberedFrameComesBackUntouched() {
    let placed = NSRect(
      x: 1700, y: 100,
      width: ChatComposerLayout.contentLaneMaxWidth, height: 820)

    let frame = ShellSummonPlacement.frame(remembered: placed, visibleFrame: studio)

    XCTAssertEqual(frame, placed)
  }

  /// A frame remembered from the pre-hug oversized window cannot restore the invisible border,
  /// even on a display that would have room for it.
  func testARememberedPreHugFrameIsHuggedToTheReadableLane() {
    let placed = NSRect(x: 1700, y: 100, width: 1_400, height: 820)

    let frame = ShellSummonPlacement.frame(remembered: placed, visibleFrame: studio)

    XCTAssertEqual(frame.width, ChatComposerLayout.contentLaneMaxWidth)
    XCTAssertEqual(frame.height, 820)
    XCTAssertEqual(frame.origin, placed.origin)
  }

  /// **The display that shrank.** A frame remembered on a 2560pt display, restored after the user
  /// switched that display to a scaled mode, would put the query field past the right edge. It is
  /// pulled back rather than discarded — the user's size is honoured as far as it fits, and the
  /// hug max still wins over a remembered width that would recreate the click border.
  func testARememberedFrameIsPulledBackInsideADisplayThatGotSmaller() {
    let placed = NSRect(x: 2400, y: 900, width: 1200, height: 820)
    let shrunk = NSRect(x: 0, y: 0, width: 1440, height: 900)

    let frame = ShellSummonPlacement.frame(remembered: placed, visibleFrame: shrunk)

    XCTAssertTrue(
      shrunk.contains(frame),
      "a restored frame outside the display is a shell whose query field cannot be reached")
    XCTAssertEqual(
      frame.width, ChatComposerLayout.contentLaneMaxWidth,
      "the remembered 1200 pt width is the invisible border; hug it even though 1440 would fit")
    XCTAssertEqual(frame.height, 820)
  }

  /// A frame larger than the display it is restored onto is shrunk to fit, not centred at its old
  /// size and left hanging off two edges at once. Width also cannot exceed the hug max.
  func testARememberedFrameLargerThanTheDisplayIsShrunkToIt() {
    let placed = NSRect(x: 1512, y: -200, width: 2400, height: 1300)

    let frame = ShellSummonPlacement.frame(remembered: placed, visibleFrame: laptop)

    XCTAssertTrue(laptop.contains(frame))
    XCTAssertEqual(frame.width, ChatComposerLayout.contentLaneMaxWidth)
    XCTAssertEqual(frame.height, laptop.height)
  }

  /// A degenerate stored value — a zero rect from a failed decode, or a frame written while the
  /// window was ordered out — must not produce an invisible shell. It falls back to a fresh landing.
  func testADegenerateRememberedFrameFallsBackToACentredPanel() {
    let frame = ShellSummonPlacement.frame(remembered: .zero, visibleFrame: laptop)

    XCTAssertEqual(frame.size, ShellSummonPlacement.defaultSize)
    XCTAssertEqual(frame.midX, laptop.midX, accuracy: 0.5)
  }

  // MARK: - When a summon moves the shell, and when it must not

  /// The restraint. "Continue in Omi" from the notch, a Dock click, and the menu-bar item all land
  /// here; if every one of them re-placed the window, a shell you were reading would jump under you.
  func testASummonDoesNotMoveAShellYouAreAlreadyUsingOnThisDisplay() {
    XCTAssertFalse(
      ShellSummonPlacement.shouldReposition(isVisible: true, windowDisplayKey: "1", cursorDisplayKey: "1"))
  }

  /// …but calling it from the *other* screen does bring it over, which is the point of asking the
  /// cursor rather than the key window.
  func testASummonFromAnotherDisplayBringsTheShellToThatDisplay() {
    XCTAssertTrue(
      ShellSummonPlacement.shouldReposition(isVisible: true, windowDisplayKey: "1", cursorDisplayKey: "2"))
  }

  /// A shell that is not up is always placed — there is no "where it was" to respect, and this is the
  /// path every hotkey summon takes.
  func testAShellThatIsNotUpIsAlwaysPlaced() {
    XCTAssertTrue(
      ShellSummonPlacement.shouldReposition(isVisible: false, windowDisplayKey: "1", cursorDisplayKey: "1"))
  }

  /// With no cursor display (the pointer between screens, or no screens matched) a visible shell is
  /// left alone. Guessing would move it somewhere the user did not ask for.
  func testAnUnknownCursorDisplayLeavesAVisibleShellWhereItIs() {
    XCTAssertFalse(
      ShellSummonPlacement.shouldReposition(isVisible: true, windowDisplayKey: "1", cursorDisplayKey: nil))
  }

  /// A dismissal composes the AppKit presentation with the shortcut toggle policy: Escape or ⌘W orders
  /// the shell out, and the next Command-O must summon it rather than read it as still open.
  @MainActor
  func testAnOrderedOutShellIsSummonedNotDismissedByTheNextCommandO() {
    let window = makeShellWindow()

    ShellWindowChrome.dress(window, as: .summoned)
    window.orderOut(nil)

    XCTAssertEqual(ShellSummon.toggleAction(for: window, isAppActive: true), .summon)
  }

  // MARK: - Memory

  /// Two displays, two placements, neither overwriting the other. A single remembered frame is the
  /// naive implementation this exists to rule out.
  func testEachDisplayKeepsItsOwnPlacement() {
    var stored: [String: String] = [:]
    let onLaptop = NSRect(x: 100, y: 80, width: 960, height: 700)
    let onStudio = NSRect(x: 1700, y: 200, width: 1400, height: 950)

    stored = ShellFrameMemory.written(onLaptop, forDisplay: "1", into: stored)
    stored = ShellFrameMemory.written(onStudio, forDisplay: "2", into: stored)

    XCTAssertEqual(ShellFrameMemory.read(from: stored, displayKey: "1"), onLaptop)
    XCTAssertEqual(ShellFrameMemory.read(from: stored, displayKey: "2"), onStudio)
  }

  /// An unseen display has no placement rather than someone else's.
  func testADisplayWithNoRememberedPlacementReportsNone() {
    let stored = ShellFrameMemory.written(NSRect(x: 0, y: 0, width: 960, height: 700), forDisplay: "1", into: [:])

    XCTAssertNil(ShellFrameMemory.read(from: stored, displayKey: "7"))
  }

  /// Garbage in the defaults domain — a hand-edited plist, a value written by an older build — reads
  /// as "nothing remembered", not as a zero-sized shell.
  func testAnUndecodableStoredFrameReadsAsNothingRemembered() {
    XCTAssertNil(ShellFrameMemory.read(from: ["1": "not a rect"], displayKey: "1"))
  }

  // MARK: - Escape

  /// **Escape reaches the shell last.** The ordering is what makes one key mean "back" inside the
  /// shell and "put it away" at the top of it, and it is a property of the enum's declaration order,
  /// which is exactly the kind of thing a later edit reorders without noticing.
  @MainActor
  func testANavigationHandlerTakesEscapeBeforeTheShellDoes() {
    let window = NSWindow(
      contentRect: NSRect(x: 0, y: 0, width: 400, height: 300), styleMask: [.titled], backing: .buffered,
      defer: true)
    var shellDismissed = false
    var navigatedHome = false
    let shell = WindowEscapeKeyMonitor.shared.register(window: window, priority: .shell) {
      shellDismissed = true
      return true
    }
    let navigation = WindowEscapeKeyMonitor.shared.register(window: window, priority: .navigation) {
      navigatedHome = true
      return true
    }
    defer {
      WindowEscapeKeyMonitor.shared.unregister(shell)
      WindowEscapeKeyMonitor.shared.unregister(navigation)
    }

    XCTAssertTrue(WindowEscapeKeyMonitor.shared.dispatchEscape(in: window))

    XCTAssertTrue(navigatedHome, "Escape on a page must go Home before it puts the shell away")
    XCTAssertFalse(shellDismissed, "the shell swallowed an Escape that belonged to the page")
  }

  /// **`⌘W` does not retire the shell, it retires a window.** The next summon asks the scene for a
  /// new one, and every per-window attachment has to come with it. A route left on the closed window
  /// would make Escape dismiss nothing and the user's chosen frame never be remembered — neither of
  /// which has any runtime signal, so only a test catches it.
  ///
  /// Asserted from the closed window's side because that half is true in both presentations: an
  /// anchored shell has no Escape route at all, and a summoned one must have moved it.
  @MainActor
  func testReplacingTheShellWindowLeavesNothingBoundToTheClosedOne() {
    let closed = makeShellWindow()
    let replacement = makeShellWindow()

    ShellSummon.applyPresentation(to: closed)
    ShellSummon.applyPresentation(to: replacement)

    XCTAssertFalse(
      WindowEscapeKeyMonitor.shared.dispatchEscape(in: closed),
      "the retired window still owns the shell's Escape route; the visible one has none")
  }

  @MainActor
  // MARK: - Stranded-frame recovery

  /// **A restored frame no display shows is not a placement, it is a lockout.** The sign-in window
  /// shipped restored to a bottom-right corner sliver (a persisted automation-park frame after a
  /// display change), leaving its only controls at coordinates no screen shows — with no rail, no
  /// hotkey and no reachable drag handle to recover it (#11374 follow-up).
  func testACornerSliverFrameIsNotMeaningfullyOnScreen() {
    let primary = NSRect(x: 0, y: 0, width: 2048, height: 1330)
    let secondary = NSRect(x: -1920, y: 250, width: 1920, height: 1080)
    // The exact shipped failure: 960×712 restored so only a 24×32 sliver overlaps the primary.
    let stranded = NSRect(x: 2024, y: -382, width: 960, height: 712)
    XCTAssertFalse(
      ShellSummonPlacement.isMeaningfullyOnScreen(stranded, visibleFrames: [primary, secondary]))
    // Centred on either display is fine.
    XCTAssertTrue(
      ShellSummonPlacement.isMeaningfullyOnScreen(
        ShellSummonPlacement.centered(NSSize(width: 960, height: 700), in: primary),
        visibleFrames: [primary, secondary]))
    // Straddling the seam still counts once a usable panel area is visible somewhere.
    XCTAssertTrue(
      ShellSummonPlacement.isMeaningfullyOnScreen(
        NSRect(x: -400, y: 400, width: 960, height: 700), visibleFrames: [primary, secondary]))
    // An edge-touching hairline does not.
    XCTAssertFalse(
      ShellSummonPlacement.isMeaningfullyOnScreen(
        NSRect(x: 2040, y: 1320, width: 960, height: 700), visibleFrames: [primary]))
    XCTAssertFalse(ShellSummonPlacement.isMeaningfullyOnScreen(stranded, visibleFrames: []))
  }

  @MainActor
  func testRecoveryRePlacesAVisibleStrandedShellOntoARealDisplay() throws {
    guard let screen = NSScreen.main ?? NSScreen.screens.first else {
      throw XCTSkip("no display in this session")
    }
    let window = makeShellWindow()
    window.title = OMIApp.currentWindowTitle
    // Strand it: a frame whose overlap with every display is a corner sliver.
    let visible = screen.visibleFrame
    window.setFrame(
      NSRect(x: visible.maxX - 24, y: visible.minY - 680, width: 960, height: 712), display: false)
    NonintrusiveTestWindow.orderIn(window, preserveFrame: true)
    defer { window.orderOut(nil) }
    try XCTSkipIf(
      !window.isVisible, "session cannot order windows in; recovery is untestable here")

    ShellSummon.recoverStrandedFrameIfNeeded()

    XCTAssertTrue(
      ShellSummonPlacement.isMeaningfullyOnScreen(
        window.frame, visibleFrames: NSScreen.screens.map(\.visibleFrame)),
      "recovery must land the shell where its controls are reachable")
  }

  @MainActor
  private func makeShellWindow() -> NSWindow {
    NSWindow(
      contentRect: NSRect(x: 0, y: 0, width: 960, height: 700),
      styleMask: [.titled, .closable, .miniaturizable, .resizable, .fullSizeContentView],
      backing: .buffered,
      defer: true)
  }

  /// …and when the page declines it — you are already Home — the shell gets it. This is the pair that
  /// matters: either half alone describes a different product.
  @MainActor
  func testEscapePutsTheShellAwayOnceNothingInsideItWantsTheKey() {
    let window = NSWindow(
      contentRect: NSRect(x: 0, y: 0, width: 400, height: 300), styleMask: [.titled], backing: .buffered,
      defer: true)
    var shellDismissed = false
    let shell = WindowEscapeKeyMonitor.shared.register(window: window, priority: .shell) {
      shellDismissed = true
      return true
    }
    let navigation = WindowEscapeKeyMonitor.shared.register(window: window, priority: .navigation) { false }
    defer {
      WindowEscapeKeyMonitor.shared.unregister(shell)
      WindowEscapeKeyMonitor.shared.unregister(navigation)
    }

    XCTAssertTrue(WindowEscapeKeyMonitor.shared.dispatchEscape(in: window))

    XCTAssertTrue(shellDismissed)
  }

  /// A fresh install could not finish onboarding: granting the microphone quit the app.
  ///
  /// `requestMicrophonePermission` calls `suspendForPermissionPrompt`, which orders the only
  /// window out so macOS can present the dialog. AppKit reports that as the last window closing,
  /// and the handler returned `!hasCompletedOnboarding` — true during onboarding — so the process
  /// ended before the prompt could be answered and before the completion handler restored the
  /// shell. No crash report, because nothing crashed.
  func testPermissionPromptDoesNotEndOnboarding() {
    XCTAssertFalse(
      ShellSummon.shouldTerminateAfterLastWindowClosed(
        hasCompletedOnboarding: false, isSuspendedForPermissionPrompt: true),
      "quitting here ends onboarding at the moment the user is granting the permission it asked for")
  }

  /// The behaviour the guard must not weaken: before onboarding completes there is no menu-bar
  /// residency to fall back on, so a window the user actually closed still means quit.
  func testClosingTheLastOnboardingWindowStillQuits() {
    XCTAssertTrue(
      ShellSummon.shouldTerminateAfterLastWindowClosed(
        hasCompletedOnboarding: false, isSuspendedForPermissionPrompt: false))
  }

  /// After onboarding the app is a menu-bar resident, so losing the last window is never a quit —
  /// with or without a prompt in flight.
  func testOnboardedAppSurvivesLosingItsLastWindow() {
    for suspended in [true, false] {
      XCTAssertFalse(
        ShellSummon.shouldTerminateAfterLastWindowClosed(
          hasCompletedOnboarding: true, isSuspendedForPermissionPrompt: suspended))
    }
  }
}
