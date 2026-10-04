import AppKit
import XCTest

@testable import Omi_Computer

/// The rule that makes a shortcut recorder work at all: while it is listening, nothing else in this
/// app may act on a keystroke.
///
/// The reported defect was that Settings could not rebind a shortcut onto the chord it was already
/// bound to — pressing it ran the old binding and toggled the window instead of recording. Ask Omi is
/// a Carbon hotkey and a Carbon hotkey *preempts* the frontmost app, so the recorder's
/// `NSEvent.addLocalMonitorForEvents` never saw the event; ⌘-chords had a second way to lose, to the
/// main menu's key equivalents. Onboarding stood both down inline and Settings stood down neither,
/// which is why the rule now lives in a type instead of at a call site.
@MainActor
final class ShortcutCaptureSessionTests: XCTestCase {

  /// A stand-in for the app's menu bar. `NSApp` does not exist in this process and the test bundle is
  /// required not to create one (see `HomeStageCloseSemanticsTests`), so the session is handed a
  /// menu slot instead of reaching for the real one.
  private final class MenuSlot {
    var menu: NSMenu?
    init(_ menu: NSMenu?) { self.menu = menu }
  }

  private func makeSession(
    menu: MenuSlot, suspensions: @escaping (Bool) -> Void = { _ in }
  ) -> ShortcutCaptureSession {
    ShortcutCaptureSession(
      suspendGlobalShortcuts: suspensions,
      readMainMenu: { menu.menu },
      writeMainMenu: { menu.menu = $0 })
  }

  // MARK: - Standing down

  /// All three layers, in one call. Each is listed because each intercepts somewhere different, and
  /// a session that suspended two of them would still lose the chord the user is most likely to type.
  func testBeginningACaptureStandsDownEveryLayerThatCouldEatTheChord() {
    let menu = MenuSlot(NSMenu(title: "test"))
    var suspensions: [Bool] = []
    let session = makeSession(menu: menu) { suspensions.append($0) }

    session.begin()

    XCTAssertEqual(suspensions, [true], "the Carbon hotkeys are still registered and still preempt")
    XCTAssertNil(menu.menu, "a menu key equivalent claims ⌘W before a local monitor ever runs")
    XCTAssertTrue(
      ShortcutCaptureSession.isCapturing,
      "push-to-talk reads this; without it, rebinding the talk chord starts a voice turn instead")

    session.end()
  }

  /// And hands all three back — the same menu object, not a rebuilt one.
  func testEndingACaptureHandsTheKeyboardBack() {
    let original = NSMenu(title: "test")
    let menu = MenuSlot(original)
    var suspensions: [Bool] = []
    let session = makeSession(menu: menu) { suspensions.append($0) }

    session.begin()
    session.end()

    XCTAssertEqual(suspensions, [true, false])
    XCTAssertIdentical(menu.menu, original, "the app got back a different menu than it handed over")
    XCTAssertFalse(ShortcutCaptureSession.isCapturing)
  }

  // MARK: - Re-entry

  /// **The case that makes this a session rather than two calls.** Settings begins a capture by
  /// stopping the previous one, and a recorder that re-arms without disarming would otherwise save
  /// the `nil` menu it installed itself — and the Mac would never get its menu bar back.
  func testReArmingWithoutDisarmingDoesNotLoseTheMenu() {
    let original = NSMenu(title: "test")
    let menu = MenuSlot(original)
    let session = makeSession(menu: menu)

    session.begin()
    session.begin()
    session.end()

    XCTAssertIdentical(menu.menu, original)
    XCTAssertFalse(ShortcutCaptureSession.isCapturing)
  }

  /// Teardown runs on paths where capture never started — a Settings pane dismissed without anyone
  /// pressing Save. Ending a session that never began must not suspend, resume, or blank the menu.
  func testEndingASessionThatNeverBeganIsANoOp() {
    let original = NSMenu(title: "test")
    let menu = MenuSlot(original)
    var suspensions: [Bool] = []
    let session = makeSession(menu: menu) { suspensions.append($0) }

    session.end()

    XCTAssertEqual(suspensions, [], "a resume nobody asked for re-registers hotkeys out of turn")
    XCTAssertIdentical(menu.menu, original)
    XCTAssertFalse(ShortcutCaptureSession.isCapturing)
  }

  /// A recorder torn down mid-capture — its view dismissed, its window closed — must not leave the
  /// Mac without a menu bar and without Ask Omi.
  func testASessionDroppedMidCaptureRestoresTheApp() {
    let original = NSMenu(title: "test")
    let menu = MenuSlot(original)
    var suspensions: [Bool] = []

    do {
      let session = makeSession(menu: menu) { suspensions.append($0) }
      session.begin()
      XCTAssertTrue(ShortcutCaptureSession.isCapturing)
    }

    XCTAssertEqual(suspensions, [true, false], "the hotkeys stayed suspended for the rest of the run")
    XCTAssertIdentical(menu.menu, original)
    XCTAssertFalse(ShortcutCaptureSession.isCapturing)
  }

  // MARK: - The layer a Boolean can reach

  /// Push-to-talk is the one stander-down that is an in-process monitor, so it is gated rather than
  /// torn down. The gate is the reported defect in its own right: the talk chord is exactly the one a
  /// user retypes when rebinding talk.
  func testPushToTalkIgnoresTheKeyboardWhileARecorderOwnsIt() {
    XCTAssertFalse(
      PushToTalkManager.acceptsShortcutEvents(isRecordingAShortcut: true, pttEnabled: true),
      "rebinding push-to-talk onto its own chord starts a voice turn instead of recording it")
    XCTAssertTrue(
      PushToTalkManager.acceptsShortcutEvents(isRecordingAShortcut: false, pttEnabled: true),
      "the gate outlived the recorder and push-to-talk is deaf")
    XCTAssertFalse(
      PushToTalkManager.acceptsShortcutEvents(isRecordingAShortcut: false, pttEnabled: false),
      "the pre-existing `pttEnabled` gate must survive being folded into this one")
    XCTAssertFalse(
      PushToTalkManager.acceptsShortcutEvents(isRecordingAShortcut: true, pttEnabled: false))
  }
}
