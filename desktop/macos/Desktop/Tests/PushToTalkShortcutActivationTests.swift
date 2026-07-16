import VoiceTurnDomain
import XCTest

@testable import Omi_Computer

final class PushToTalkShortcutActivationTests: XCTestCase {
  func testTypingChordCancelsPendingModifierOnlyPTTBeforeItCanBargeIn() {
    var gate = ModifierOnlyPTTActivationGate()

    XCTAssertEqual(gate.modifierStateChanged(isShortcutActive: true), .scheduleStart)
    XCTAssertTrue(gate.hasPendingStart)

    XCTAssertEqual(gate.nonModifierKeyPressed(), .cancelPendingStart)
    XCTAssertFalse(gate.hasPendingStart)
    XCTAssertFalse(
      gate.consumePendingStart(),
      "The delayed PTT start must not fire after an ordinary typing/navigation key."
    )
    XCTAssertEqual(
      gate.modifierStateChanged(isShortcutActive: false),
      .none,
      "Releasing a modifier that never started PTT must be a true no-op."
    )
  }

  func testIntentionalModifierHoldStartsThenReleasesPTT() {
    var gate = ModifierOnlyPTTActivationGate()

    XCTAssertEqual(gate.modifierStateChanged(isShortcutActive: true), .scheduleStart)
    XCTAssertTrue(gate.consumePendingStart())
    XCTAssertEqual(gate.modifierStateChanged(isShortcutActive: false), .releaseStartedTurn)
  }

  func testQuickModifierTapNeverStartsOrReleasesPTT() {
    var gate = ModifierOnlyPTTActivationGate()

    XCTAssertEqual(gate.modifierStateChanged(isShortcutActive: true), .scheduleStart)
    XCTAssertEqual(gate.modifierStateChanged(isShortcutActive: false), .cancelPendingStart)
    XCTAssertFalse(gate.consumePendingStart())
  }

  func testTypingAfterIntentionalPTTStartDoesNotCancelActiveTurn() {
    var gate = ModifierOnlyPTTActivationGate()

    XCTAssertEqual(gate.modifierStateChanged(isShortcutActive: true), .scheduleStart)
    XCTAssertTrue(gate.consumePendingStart())
    XCTAssertEqual(gate.nonModifierKeyPressed(), .none)
  }

  func testIntentionalModifierHoldMayBargeIntoActiveResponse() {
    var gate = ModifierOnlyPTTActivationGate()

    XCTAssertEqual(gate.modifierStateChanged(isShortcutActive: true), .scheduleStart)
    XCTAssertTrue(
      gate.consumePendingStart(),
      "Once the hold gate elapses without a text key-down, chat-input focus must not suppress PTT."
    )
    XCTAssertTrue(
      PushToTalkManager.admitsListeningStart(
        activeTurnID: VoiceTurnID(),
        phase: .playing(.nativeRealtime)
      )
    )
  }
}
