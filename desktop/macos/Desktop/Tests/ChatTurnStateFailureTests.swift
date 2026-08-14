import XCTest

@testable import Omi_Computer

/// Regression coverage for the three turn-state defects a tester found while
/// the backend answered every chat turn with `HTTP 402`:
///
///  * a failed turn left its question orphaned — the transcript showed four
///    consecutive user rows with no assistant row between them — while the
///    only account of the failure was the provider-wide `errorMessage`, which
///    is dismissible, overwritten by the next turn and gone on relaunch;
///  * a second send while a turn was in flight was refused silently, so the
///    reader's message vanished with no explanation and every caller reported
///    a send that never happened;
///  * the composer was emptied at journal acceptance, so a failed turn
///    destroyed what the reader had typed.
@MainActor
final class ChatTurnStateFailureTests: XCTestCase {
  // MARK: - The failure marker lands on the turn that failed

  /// The marker replaces the empty assistant row, so the question it belongs
  /// to can never be left with nothing under it.
  func testFailedTurnMarksItsOwnAssistantRow() {
    let provider = ChatProvider()
    provider.messages = [
      ChatMessage(id: "u1", clientTurnId: "t1", text: "What is the capital of France?", sender: .user),
      ChatMessage(id: "a1", clientTurnId: "t1", text: "", sender: .ai, isStreaming: true),
    ]
    guard
      let notice = ChatTurnFailureNotice.forFailure(
        errorDescription: "HTTP 402 status code (no body)",
        presentsUserError: true
      )
    else { return XCTFail("expected a marker for a bare 402") }

    provider.applyTurnFailureMarker(notice, toAssistantMessage: "a1")

    guard let row = provider.messages.first(where: { $0.id == "a1" }) else {
      return XCTFail("the failing turn's row must still be in the transcript")
    }
    XCTAssertEqual(row.text, notice.text, "The row says why the turn failed")
    XCTAssertFalse(row.isStreaming, "A failed turn is terminal, not still typing")
    XCTAssertEqual(row.journalStatus, .failed)
    XCTAssertEqual(
      provider.messages.map(\.sender), [.user, .ai],
      "The question keeps an answer row — consecutive user rows are the orphan this fixes"
    )
  }

  /// Output the turn did manage to produce is not thrown away to make room
  /// for the reason.
  func testPartialAnswerSurvivesBesideTheMarker() {
    let provider = ChatProvider()
    provider.messages = [
      ChatMessage(id: "a1", text: "Paris is the capital", sender: .ai, isStreaming: true)
    ]
    guard let notice = ChatTurnFailureNotice.stating("Response took too long. Try again.", retryable: true)
    else { return XCTFail("expected a marker") }

    provider.applyTurnFailureMarker(notice, toAssistantMessage: "a1")

    let text = provider.messages[0].text
    XCTAssertTrue(text.hasPrefix("Paris is the capital"), "Delivered text is kept")
    XCTAssertTrue(text.hasSuffix("Response took too long. Try again."), "and still says it did not finish")
  }

  /// The journal projection deletes an empty `.failed` row as a placeholder.
  /// That is the mechanism that orphaned the question, so a row carrying a
  /// reason has to survive the same projection — otherwise the marker would be
  /// erased the moment the journal refreshed.
  func testJournalProjectionKeepsAFailedRowThatCarriesAReasonAndStillDropsEmptyOnes() throws {
    let provider = ChatProvider()
    let surface = provider.mainChatSurfaceReference()

    provider.projectJournalTurns([
      try Self.failedJournalTurn(
        id: "a-reason", seq: 1, surface: surface,
        content: "Omi's AI service declined this request."),
      try Self.failedJournalTurn(id: "a-empty", seq: 2, surface: surface, content: ""),
    ])

    XCTAssertEqual(
      provider.messages.map(\.id), ["a-reason"],
      "A failed row with a reason is a record; a failed row with nothing in it is still a placeholder"
    )
    XCTAssertEqual(provider.messages.first?.journalStatus, .failed)
  }

  // MARK: - The busy guard is said out loud

  /// A second send while a turn is in flight is refused — and the refusal is
  /// reported. A silent `return nil` is a message the reader watched
  /// disappear.
  func testSendWhileBusyIsRefusedWithAnExplanation() async {
    let provider = ChatProvider()
    provider.isSending = true

    XCTAssertFalse(provider.canAcceptSend, "A turn is in flight, so no new turn can start")

    let result = await provider.sendMessage("SECOND TURN beta")

    XCTAssertNil(result, "The second send must not start a turn")
    XCTAssertEqual(
      provider.errorMessage, ChatProvider.sendRefusedWhileBusyMessage,
      "The reader has to be told where their message went"
    )
    XCTAssertNil(provider.currentError)
    XCTAssertTrue(
      provider.messages.isEmpty,
      "A refused send records nothing — no orphaned user row for a turn that never ran"
    )
  }

  /// An idle provider still admits a send; the guard must not latch.
  func testIdleProviderAcceptsSend() {
    let provider = ChatProvider()

    XCTAssertTrue(provider.canAcceptSend)

    provider.isSending = true
    XCTAssertFalse(provider.canAcceptSend)

    provider.isSending = false
    XCTAssertTrue(provider.canAcceptSend, "The admission decision follows the turn, it does not stick")
  }

  // MARK: - The composer keeps what the reader typed

  /// The composer is emptied at journal acceptance, long before the turn
  /// resolves. A failed turn gives the text back, so retrying is pressing
  /// return again.
  func testFailedTurnGivesTheTypedTextBack() {
    let provider = ChatProvider()
    provider.draftText = ""

    provider.restoreComposerAfterFailedTurn("What did I work on today?", turnOwner: .mainChat)

    XCTAssertEqual(provider.draftText, "What did I work on today?")
  }

  /// Live typing always wins: the reader has moved on, and their text is not
  /// ours to overwrite.
  func testRestoreNeverOverwritesLiveTyping() {
    let provider = ChatProvider()
    provider.draftText = "something else entirely"

    provider.restoreComposerAfterFailedTurn("What did I work on today?", turnOwner: .mainChat)

    XCTAssertEqual(provider.draftText, "something else entirely")
  }

  /// The main composer is the only one this restores into — a floating or
  /// voice turn has no main-window text to give back.
  func testRestoreIsScopedToTheMainComposer() {
    let provider = ChatProvider()
    provider.draftText = ""

    provider.restoreComposerAfterFailedTurn("spoken question", turnOwner: .floatingVoice)

    XCTAssertEqual(provider.draftText, "")
  }

  // MARK: - Which endings earn a marker

  /// `forTurn` is the one decision point. Stop earns nothing, the watchdog
  /// earns its own copy, and a provider failure earns the classifier's.
  func testOnlyRealFailuresEarnAMarker() {
    func notice(_ error: Error, watchdogFired: Bool = false) -> ChatTurnFailureNotice? {
      ChatTurnFailureNotice.forTurn(
        error: error,
        watchdogFired: watchdogFired,
        toolStallAbortFired: false,
        timeoutMessage: ChatProvider.stoppedTurnErrorMessage(watchdogFired: watchdogFired),
        providerAuthMessage: "Reconnect Claude in Settings."
      )
    }

    XCTAssertNil(notice(BridgeError.stopped), "Pressing Stop is not a failure")
    XCTAssertEqual(
      notice(BridgeError.stopped, watchdogFired: true)?.text,
      ChatProvider.stoppedTurnErrorMessage(watchdogFired: true),
      "A watchdog stop is a timeout and says so, even though it arrives as .stopped"
    )
    XCTAssertEqual(
      notice(BridgeError.agentError("HTTP 402 status code (no body)"))?.retryable,
      false,
      "The billing rejection must not invite a retry"
    )
    XCTAssertEqual(
      notice(
        BridgeError.agentRuntimeFailure(
          AgentRuntimeFailure(
            code: "adapter_execution_failed",
            userMessage: "The local agent reset its session after an error. Send your message again.",
            technicalMessage: "HTTP 402 status code (no body)",
            retryable: true,
            recoveryAction: "worker_recycled"
          )
        )
      )?.retryable,
      false,
      "Worker recycle must not turn a 402 into a retryable session reset"
    )
    XCTAssertEqual(
      notice(BridgeError.nodeNotFound)?.text,
      ChatErrorState.bridgeUnavailable(reason: .nodeMissing).userFacingSummary,
      "A card that survives words the row, so the two surfaces cannot disagree"
    )
  }

  // MARK: - Helpers

  private static func failedJournalTurn(
    id: String,
    seq: Int,
    surface: AgentSurfaceReference,
    content: String
  ) throws -> KernelJournalTurn {
    try XCTUnwrap(
      KernelJournalTurn(dictionary: [
        "conversationId": "conversation-1",
        "turnId": id,
        "turnSeq": seq,
        "conversationGeneration": 1,
        "generationBaseTurnSeq": 0,
        "producerId": "producer:\(id)",
        "payloadHash": "sha256:\(id)",
        "role": "assistant",
        "surfaceKind": surface.surfaceKind,
        "externalRefKind": surface.externalRefKind,
        "externalRefId": surface.externalRefId,
        "content": content,
        "origin": "main_chat",
        "status": KernelJournalTurnStatus.failed.rawValue,
        "contentBlocks": [],
        "resources": [],
        "metadataJson": "{}",
        "createdAtMs": 1_700_000_000_000 + seq,
        "updatedAtMs": 1_700_000_000_000 + seq,
      ]))
  }
}
