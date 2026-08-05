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
}
