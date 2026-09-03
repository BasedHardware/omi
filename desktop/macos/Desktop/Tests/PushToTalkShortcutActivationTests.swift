import VoiceTurnDomain
import XCTest

@testable import Omi_Computer

private actor PTTBatchContextGate {
  private var transcriptionStartWaiters: [CheckedContinuation<Void, Never>] = []
  private var transcriptionStarted = false
  private var contextDidRelease = false

  func waitForContextRelease() async {
    while !contextDidRelease && !Task.isCancelled {
      await Task.yield()
    }
  }

  func releaseContext() {
    contextDidRelease = true
  }

  func markTranscriptionStarted() {
    transcriptionStarted = true
    let waiters = transcriptionStartWaiters
    transcriptionStartWaiters.removeAll()
    waiters.forEach { $0.resume() }
  }

  func waitForTranscriptionStart() async {
    guard !transcriptionStarted else { return }
    await withCheckedContinuation { continuation in
      transcriptionStartWaiters.append(continuation)
    }
  }

  func hasContextReleased() -> Bool {
    contextDidRelease
  }
}

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

  // MARK: - Bar reveal must never swallow the press

  /// Records the order of the two effects the shipping handlers pass to the seam.
  private func recordPress(barVisible: Bool) -> [String] {
    var calls: [String] = []
    PushToTalkBarRevealPolicy.startPress(
      barVisible: barVisible,
      reveal: { calls.append("reveal") },
      start: { calls.append("start") })
    return calls
  }

  func testHiddenBarPressRevealsTheBarThenStartsTheTurn() {
    // Regression: `handleKeyShortcutDown` revealed the bar and then returned before
    // `handleShortcutDown()`, so startListening() never ran — no start sound, no
    // listening animation. On a second display the bar is re-placed as it follows the
    // cursor, so it is routinely hidden at press time and every first press was lost.
    // This fails if the start effect is ever skipped or ordered before the reveal.
    XCTAssertEqual(recordPress(barVisible: false), ["reveal", "start"])
  }

  func testVisibleBarPressStartsTheTurnWithoutRevealing() {
    XCTAssertEqual(recordPress(barVisible: true), ["start"])
  }

  func testHiddenBarDoubleTapRevealsThenEntersLockedListening() {
    // The same early return ate the first tap of a double tap, which is why locked mode
    // did not work on a second display. The gate reports both quick taps regardless of
    // bar visibility, and the lock site runs through the same seam.
    var gate = ModifierOnlyPTTActivationGate()
    for _ in 0..<2 {
      XCTAssertEqual(gate.modifierStateChanged(isShortcutActive: true), .scheduleStart)
      XCTAssertEqual(
        gate.modifierStateChanged(isShortcutActive: false), .cancelPendingStartAsQuickTap)
    }
    var calls: [String] = []
    PushToTalkBarRevealPolicy.startPress(
      barVisible: false,
      reveal: { calls.append("reveal") },
      start: { calls.append("enterLockedListening") })
    XCTAssertEqual(calls, ["reveal", "enterLockedListening"])
  }

  func testQuickModifierTapNeverStartsOrReleasesPTT() {
    // A quick tap still starts no turn — an accidental brush of the modifier must
    // never record. It is only reported as a quick tap so the double-tap detector
    // can see it; on its own it does nothing.
    var gate = ModifierOnlyPTTActivationGate()

    XCTAssertEqual(gate.modifierStateChanged(isShortcutActive: true), .scheduleStart)
    XCTAssertEqual(
      gate.modifierStateChanged(isShortcutActive: false), .cancelPendingStartAsQuickTap)
    XCTAssertFalse(gate.consumePendingStart())
    XCTAssertFalse(gate.hasStartedTurn, "A quick tap must not leave a turn running.")
  }

  func testModifierHeldAsPartOfAChordIsNeverAQuickTap() {
    // The modifier held for another shortcut (cmd-C and friends) is cancelled by the
    // non-modifier key, so releasing it later stays a plain no-op and must never feed
    // the double-tap detector.
    var gate = ModifierOnlyPTTActivationGate()

    XCTAssertEqual(gate.modifierStateChanged(isShortcutActive: true), .scheduleStart)
    XCTAssertEqual(gate.nonModifierKeyPressed(), .cancelPendingStart)
    XCTAssertEqual(gate.modifierStateChanged(isShortcutActive: false), .none)
  }

  func testRepeatedQuickTapsEachReportAQuickTapWithoutStartingATurn() {
    // Two taps in a row are what locked mode is built on: each must be reported and
    // neither may start a hold turn.
    var gate = ModifierOnlyPTTActivationGate()

    for _ in 0..<2 {
      XCTAssertEqual(gate.modifierStateChanged(isShortcutActive: true), .scheduleStart)
      XCTAssertEqual(
        gate.modifierStateChanged(isShortcutActive: false), .cancelPendingStartAsQuickTap)
    }
    XCTAssertFalse(gate.hasStartedTurn)
    XCTAssertFalse(gate.hasPendingStart)
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

  @MainActor
  func testBatchTranscriptionStartsBeforeContextOCRCompletes() async throws {
    let gate = PTTBatchContextGate()
    let contextTask = Task {
      await gate.waitForContextRelease()
    }
    let transcriptionTask = Task {
      try await PushToTalkManager.runBatchTranscriptionBeforeContext(
        contextTask: contextTask
      ) {
        await gate.markTranscriptionStarted()
        return TranscriptionService.BatchTranscriptionResult(
          transcript: "fixture", provider: "fixture", model: "fixture")
      }
    }

    await gate.waitForTranscriptionStart()
    let contextReleased = await gate.hasContextReleased()
    XCTAssertFalse(
      contextReleased,
      "Batch STT must start while screen/OCR context capture is still in flight")

    let result = try await transcriptionTask.value
    XCTAssertEqual(result.transcript, "fixture")
    contextTask.cancel()
    await contextTask.value
  }
}
