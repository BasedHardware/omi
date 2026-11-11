import AppKit
import XCTest

@testable import Omi_Computer

/// The two rules that decide whether a keystroke may become the user's Omi chord.
///
/// Both were found by walking the live flow: with the shortcut step on screen, a bare `L` typed in
/// **another application** was captured by the step's global monitor, persisted as
/// `askOmiShortcut`, and confirmed with "Perfect, that works." — which would have made every `L`
/// typed anywhere on the Mac open Omi.
@MainActor
final class SBOnboardingShortcutRecordingTests: XCTestCase {

  // MARK: - Where the keystroke came from

  func testRecordingOnlyListensToKeystrokesAimedAtOmi() {
    XCTAssertTrue(SBOnboardingModel.acceptsRecordingSource(appIsActive: true))
    XCTAssertFalse(
      SBOnboardingModel.acceptsRecordingSource(appIsActive: false),
      "a key typed in another app must not become the user's Omi chord")
  }

  // MARK: - What the chord may be

  func testABareLetterIsRefusedAsAGlobalChord() {
    let bareL = ShortcutSettings.KeyboardShortcut(keyCode: 37, keyDisplay: "L")

    XCTAssertFalse(
      SBOnboardingModel.acceptsRecordedChord(bareL),
      "askOmiShortcut is a global hotkey; a modifier-less key would swallow that letter everywhere")
  }

  func testTheOfferedOpenChordsAreAccepted() {
    XCTAssertTrue(SBOnboardingModel.acceptsRecordedChord(ShortcutSettings.askOmiCommandOShortcut))
    XCTAssertTrue(SBOnboardingModel.acceptsRecordedChord(ShortcutSettings.askOmiCommandReturnShortcut))
  }

  func testTheOfferedTalkChordsAreAccepted() {
    for modifiers: NSEvent.ModifierFlags in [.function, .option, .control] {
      XCTAssertTrue(
        SBOnboardingModel.acceptsRecordedChord(
          ShortcutSettings.KeyboardShortcut(modifierOnly: modifiers)),
        "every hold-to-talk option this step offers must still be recordable")
    }
  }

  func testAModifiedKeyTypedByTheUserIsAccepted() {
    let commandShiftK = ShortcutSettings.KeyboardShortcut(
      keyCode: 40, keyDisplay: "K", modifiers: [.command, .shift])

    XCTAssertTrue(SBOnboardingModel.acceptsRecordedChord(commandShiftK))
  }

  // MARK: - The refusal has to be visible

  /// Refusing a bare key is right; refusing it *silently* is what shipped. The step invited "press
  /// any key", the monitor dropped the event, and nothing on screen changed — so to the user the
  /// step had simply stopped working. The decision is a value now so this is assertable at all.
  func testABareKeyIsRefusedWithSomethingToSay() {
    let bareL = ShortcutSettings.KeyboardShortcut(keyCode: 37, keyDisplay: "L")

    XCTAssertEqual(SBOnboardingModel.decideRecordedChord(bareL), .refuseBareKey)
  }

  func testAnOfferedChordIsAcceptedRatherThanExplained() {
    XCTAssertEqual(
      SBOnboardingModel.decideRecordedChord(ShortcutSettings.askOmiControlCommandOShortcut),
      .accept(ShortcutSettings.askOmiControlCommandOShortcut))
  }

  /// An unrecordable event (a modifier release with nothing pending) is not a refusal — surfacing
  /// "add a modifier" for it would fire the message at someone who pressed nothing.
  func testAnUnreadableEventIsIgnoredRatherThanRefused() {
    XCTAssertEqual(SBOnboardingModel.decideRecordedChord(nil), .ignore)
  }

  // MARK: - What the step offers

  /// The first option is the one the user is steered onto, and it must be the one that costs them
  /// nothing. Whatever is picked here is registered with `RegisterEventHotKey`, which preempts the
  /// frontmost app and consumes the key — so offering ⌘O first taught new users to take File ▸ Open
  /// away from every app on their Mac. ⌃⌘O collides with nothing.
  func testTheFirstOfferedOpenChordIsTheOneThatCollidesWithNothing() throws {
    let appState = AppState()
    let model = SBOnboardingModel(appState: appState, chatProvider: ChatProvider(), onComplete: nil)
    let first = try withExtendedLifetime(appState) { try XCTUnwrap(model.openShortcutOptions.first) }

    XCTAssertEqual(first.shortcut, ShortcutSettings.askOmiControlCommandOShortcut)
    XCTAssertEqual(first.shortcut, GlobalShortcutManager.summonShortcut)
  }

  /// ⌘O stays offered — it is a reasonable thing to want — but not silently.
  func testTheCommandOOptionNamesWhatItCosts() {
    let appState = AppState()
    let model = SBOnboardingModel(appState: appState, chatProvider: ChatProvider(), onComplete: nil)
    withExtendedLifetime(appState) {
      let commandO = model.openShortcutOptions.first { $0.shortcut == ShortcutSettings.askOmiCommandOShortcut }
      XCTAssertNotNil(commandO, "⌘O must remain available to anyone who wants it")
      XCTAssertNotEqual(commandO?.sub, "press to set", "the chord that takes File ▸ Open must say so")
    }
  }
}
