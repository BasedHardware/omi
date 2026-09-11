import XCTest

@testable import Omi_Computer

/// What the shortcut recorder card's button offers to do.
///
/// The card used to offer "Save" for a shortcut that was already saved. Its button's action is
/// `startShortcutCapture`, and the capture handler commits a chord the moment the keys go down, so
/// there has never been an unsaved state for a Save to resolve — pressing it discarded the chord and
/// listened again. A label naming an action the control does not perform is the kind of thing that
/// reads fine in a diff and wrong in the app, so it is stated here instead.
final class ShortcutRecorderActionTests: XCTestCase {

  /// The reported complaint, as the assertion that would have caught it.
  func testTheIdleButtonOffersToRedoRatherThanToSave() {
    XCTAssertEqual(ShortcutRecorderAction.label(isRecording: false), "Redo")
  }

  /// While the monitor is armed the button reports the state instead, so the card has somewhere to
  /// say "your keystroke is being read right now" — the one moment the user needs that feedback.
  func testTheButtonReportsListeningWhileTheRecorderIsArmed() {
    XCTAssertEqual(ShortcutRecorderAction.label(isRecording: true), "Listening…")
  }

  /// Neither state may name an action this button cannot perform. Pinned as a claim rather than left
  /// to the two equalities above, because "Save" is the word anyone would reach for again.
  func testNeitherStatePromisesToSave() {
    for isRecording in [true, false] {
      XCTAssertFalse(
        ShortcutRecorderAction.label(isRecording: isRecording).localizedCaseInsensitiveContains(
          "save"),
        "the recorder has no unsaved state: the chord is committed on key-down, not by this button")
    }
  }
}
