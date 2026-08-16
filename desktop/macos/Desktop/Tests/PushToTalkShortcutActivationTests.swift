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
