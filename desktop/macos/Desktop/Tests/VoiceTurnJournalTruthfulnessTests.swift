import XCTest

@testable import Omi_Computer
@testable import VoiceTurnDomain

#if DEBUG
  /// The journal is the model's only memory across push-to-talk presses, and the
  /// kernel prompt calls it canonical. These tests pin the properties that keep it
  /// from lying: a turn cannot claim completion it did not reach, and a backend
  /// tool failure cannot reach the model wearing a success.
  @MainActor
  final class VoiceTurnJournalTruthfulnessTests: XCTestCase {

    // MARK: - I1: journal status is a total function of the terminal reason

    func testOnlySuccessJournalsAsCompleted() {
      XCTAssertEqual(VoiceTurnJournalStatusPolicy.status(for: .success), .completed)
    }

    func testEveryNonSuccessTerminalReasonJournalsAsFailed() {
      // The dead `interrupted: Bool` meant a barge-in, a provider error and a
      // timeout were all sealed `.completed`, so the model read its own truncated
      // half-sentence back as a finished answer.
      for reason in VoiceTurnTerminalReason.allCases where reason != .success {
        XCTAssertEqual(
          VoiceTurnJournalStatusPolicy.status(for: reason), .failed,
          "\(reason.rawValue) must not be journaled as a completed answer")
      }
    }

    // MARK: - I1b: delivery state separates "cut off" from "fully heard"

    func testBargeInAfterFullDeliveryJournalsAsCompleted() {
      // A barge-in after playback drained interrupts the silence, not the
      // answer. Journaling it `.failed` taught the model its own delivered
      // answer was cut off, and it re-delivered that answer turns later on an
      // unrelated question (measured 2026-09-04: three fully spoken replies in
      // one session sealed `interrupted_by_barge_in`, followed by exactly that
      // recurrence).
      XCTAssertEqual(
        VoiceTurnJournalStatusPolicy.status(for: .interruptedByBargeIn, answerDelivered: true),
        .completed)
      XCTAssertEqual(
        VoiceTurnJournalStatusPolicy.status(for: .explicitInterrupt, answerDelivered: true),
        .completed)
    }

    func testDeliveryDoesNotRescueNonInterruptionFailures() {
      for reason in VoiceTurnTerminalReason.allCases
      where reason != .success && reason != .interruptedByBargeIn && reason != .explicitInterrupt {
        XCTAssertEqual(
          VoiceTurnJournalStatusPolicy.status(for: reason, answerDelivered: true), .failed,
          "\(reason.rawValue) must not become a completed answer because audio drained")
      }
    }

    func testInterruptedTurnPayloadCarriesDeliveryState() {
      let delivered = InterruptedTurnPayload(
        ownerID: "owner", userText: "what is it?", assistantText: "The full answer.",
        idempotencyKey: "voice:abc", answerDelivered: true)
      let cutOff = InterruptedTurnPayload(
        ownerID: "owner", userText: "what is it?", assistantText: "The full ans",
        idempotencyKey: "voice:abc")

      XCTAssertTrue(delivered.answerDelivered)
      XCTAssertFalse(cutOff.answerDelivered)
      XCTAssertNotEqual(delivered, cutOff)
    }

    func testScreenObservationTravelsInUserRowMetadata() throws {
      // Regression: "what was the last word of the first riddle?" failed because what Omi saw on
      // the earlier turn lived only in a dropped tool observation. The user row now carries it.
      let projection = RealtimeStreamingJournalProjection(
        ownerID: "owner", continuityKey: "voice:abc",
        admissionSurface: AgentSurfaceReference(surfaceKind: "main_chat", externalRefKind: "chat", externalRefId: "x"),
        screenContext: "Browser shows a riddle: I have keys but open no locks ... never go inside.")
      let write = projection.userMessage(text: "what's the answer?").journalWrite(
        origin: "realtime_voice", status: .completed, continuityKey: "voice:abc", messageSource: "realtime_voice")
      let metadata = try XCTUnwrap(
        JSONSerialization.jsonObject(with: Data(write.metadataJSON.utf8)) as? [String: Any])
      XCTAssertEqual(
        metadata["screen_context"] as? String,
        "Browser shows a riddle: I have keys but open no locks ... never go inside.")
      XCTAssertEqual(write.role, "user")

      let plain = RealtimeStreamingJournalProjection(
        ownerID: "owner", continuityKey: "voice:def",
        admissionSurface: AgentSurfaceReference(surfaceKind: "main_chat", externalRefKind: "chat", externalRefId: "x"))
      let plainWrite = plain.userMessage(text: "hi").journalWrite(origin: "realtime_voice", status: .completed)
      let plainMetadata = try XCTUnwrap(
        JSONSerialization.jsonObject(with: Data(plainWrite.metadataJSON.utf8)) as? [String: Any])
      XCTAssertNil(plainMetadata["screen_context"])
    }

    func testTerminalReasonTravelsInAssistantRowMetadata() throws {
      // Status alone cannot separate a legitimate barge-in from a hard failure;
      // the reason is what makes the truncation-cause split measurable.
      let message = ChatMessage(
        id: "turn-1", text: "Partial ans", createdAt: Date(), sender: .ai)
      let write = message.journalWrite(
        origin: "realtime_voice",
        status: .failed,
        continuityKey: "voice:abc",
        messageSource: "realtime_voice",
        terminalReason: VoiceTurnTerminalReason.interruptedByBargeIn.rawValue)

      let metadata = try XCTUnwrap(
        JSONSerialization.jsonObject(with: Data(write.metadataJSON.utf8)) as? [String: Any])
      XCTAssertEqual(metadata["terminalReason"] as? String, "interrupted_by_barge_in")
      XCTAssertEqual(write.status, .failed)
    }

    func testSuccessfulTurnCarriesNoTerminalReasonAnnotation() throws {
      let message = ChatMessage(
        id: "turn-2", text: "Full answer.", createdAt: Date(), sender: .ai)
      let write = message.journalWrite(
        origin: "realtime_voice",
        status: .completed,
        continuityKey: "voice:def",
        messageSource: "realtime_voice")

      let metadata = try XCTUnwrap(
        JSONSerialization.jsonObject(with: Data(write.metadataJSON.utf8)) as? [String: Any])
      XCTAssertNil(metadata["terminalReason"])
    }

    func testJournalUpdateCarriesTerminalReasonOnTheStreamingPath() throws {
      // The streaming finalize path hardcoded `metadataJSON: nil`, so without this
      // the majority of real voice turns would carry status without a reason.
      let message = ChatMessage(
        id: "turn-3", text: "Cut off mid-", createdAt: Date(), sender: .ai)
      let update = message.journalUpdate(
        status: .failed, terminalReason: VoiceTurnTerminalReason.providerFailed.rawValue)

      let metadataJSON = try XCTUnwrap(update.metadataJSON)
      let metadata = try XCTUnwrap(
        JSONSerialization.jsonObject(with: Data(metadataJSON.utf8)) as? [String: Any])
      XCTAssertEqual(metadata["terminalReason"] as? String, "provider_failed")
      XCTAssertEqual(update.status, .failed)
    }

    // MARK: - I1c: answer-text completion separates "fragment" from "delivery cut"

    func testAnswerTextCompletionTravelsInAssistantRowMetadata() throws {
      // 2026-09-09 incident: a barge-in after the provider finished cut only
      // spoken delivery, but the `.failed` row was indistinguishable from a
      // mid-stream fragment — so later context re-answered the thread. The
      // row must state the answer text completed.
      let message = ChatMessage(
        id: "turn-4", text: "The complete answer.", createdAt: Date(), sender: .ai)
      let write = message.journalWrite(
        origin: "realtime_voice",
        status: .failed,
        continuityKey: "voice:abc",
        messageSource: "realtime_voice",
        terminalReason: VoiceTurnTerminalReason.interruptedByBargeIn.rawValue,
        answerTextCompleted: true)

      let metadata = try XCTUnwrap(
        JSONSerialization.jsonObject(with: Data(write.metadataJSON.utf8)) as? [String: Any])
      XCTAssertEqual(metadata["terminalReason"] as? String, "interrupted_by_barge_in")
      XCTAssertEqual(metadata["answerTextCompleted"] as? Bool, true)
    }

    func testAnswerTextCompletionStaysAbsentForFragments() throws {
      // Absent means "fragment or legacy row": the renderer's stricter
      // cut-off guidance applies. The key must not appear with a false value.
      let message = ChatMessage(
        id: "turn-5", text: "Cut off mid-", createdAt: Date(), sender: .ai)
      let write = message.journalWrite(
        origin: "realtime_voice",
        status: .failed,
        continuityKey: "voice:abc",
        messageSource: "realtime_voice",
        terminalReason: VoiceTurnTerminalReason.interruptedByBargeIn.rawValue)

      let metadata = try XCTUnwrap(
        JSONSerialization.jsonObject(with: Data(write.metadataJSON.utf8)) as? [String: Any])
      XCTAssertNil(metadata["answerTextCompleted"])
    }

    func testJournalUpdateCarriesAnswerTextCompletionOnTheStreamingPath() throws {
      // The barge-in rows from the incident were finalized through the
      // streaming path (metadata = terminalReason only), so the flag must
      // ride the same update.
      let message = ChatMessage(
        id: "turn-6", text: "The complete answer.", createdAt: Date(), sender: .ai)
      let update = message.journalUpdate(
        status: .failed,
        terminalReason: VoiceTurnTerminalReason.interruptedByBargeIn.rawValue,
        answerTextCompleted: true)

      let metadataJSON = try XCTUnwrap(update.metadataJSON)
      let metadata = try XCTUnwrap(
        JSONSerialization.jsonObject(with: Data(metadataJSON.utf8)) as? [String: Any])
      XCTAssertEqual(metadata["terminalReason"] as? String, "interrupted_by_barge_in")
      XCTAssertEqual(metadata["answerTextCompleted"] as? Bool, true)

      let fragment = ChatMessage(
        id: "turn-7", text: "Cut off mid-", createdAt: Date(), sender: .ai)
      let fragmentUpdate = fragment.journalUpdate(
        status: .failed,
        terminalReason: VoiceTurnTerminalReason.interruptedByBargeIn.rawValue)
      let fragmentMetadataJSON = try XCTUnwrap(fragmentUpdate.metadataJSON)
      let fragmentMetadata = try XCTUnwrap(
        JSONSerialization.jsonObject(with: Data(fragmentMetadataJSON.utf8)) as? [String: Any])
      XCTAssertNil(fragmentMetadata["answerTextCompleted"])
    }

    func testSealedTerminalRevisionKeepsAnswerTextCompletion() throws {
      // A sealed row exists only when the funnel journaled at
      // provider-response-finish: the downgraded row keeps stating the answer
      // text completed (#12743 revision).
      let revision = KernelJournalTurnUpdate.sealedTerminalRevision(
        turnId: "turn-8", terminalReason: "answer_not_delivered", answerTextCompleted: true)
      let revisionMetadataJSON = try XCTUnwrap(revision.metadataJSON)
      let metadata = try XCTUnwrap(
        JSONSerialization.jsonObject(with: Data(revisionMetadataJSON.utf8)) as? [String: Any])
      XCTAssertEqual(metadata["terminalReason"] as? String, "answer_not_delivered")
      XCTAssertEqual(metadata["answerTextCompleted"] as? Bool, true)

      let legacy = KernelJournalTurnUpdate.sealedTerminalRevision(
        turnId: "turn-9", terminalReason: "playback_failed")
      let legacyMetadataJSON = try XCTUnwrap(legacy.metadataJSON)
      let legacyMetadata = try XCTUnwrap(
        JSONSerialization.jsonObject(with: Data(legacyMetadataJSON.utf8)) as? [String: Any])
      XCTAssertNil(legacyMetadata["answerTextCompleted"])
    }

    // MARK: - I2: a failed tool result reaches the model as a failure

    func testFailedBackendToolProducesTheEnvelopeTheRelayTreatsAsFailure() throws {
      // `relay-tool-result.ts` flips an invocation to `failed` on `ok:false` or an
      // `error` key. Prose alone was indistinguishable from success, which is how a
      // write that never landed was still spoken as "I've added that".
      let json = ChatToolExecutor.toolFailureEnvelope(
        code: "backend_tool_failed", message: "Task service returned 500")

      let payload = try XCTUnwrap(
        JSONSerialization.jsonObject(with: Data(json.utf8)) as? [String: Any])
      XCTAssertEqual(payload["ok"] as? Bool, false)
      let error = try XCTUnwrap(payload["error"] as? [String: Any])
      XCTAssertEqual(error["code"] as? String, "backend_tool_failed")
      XCTAssertEqual(error["message"] as? String, "Task service returned 500")
    }

    func testFailureEnvelopeSurvivesUnencodableMessages() throws {
      // The fallback must still be a failure envelope: degrading to prose would
      // reintroduce exactly the ambiguity this fixes.
      let json = ChatToolExecutor.toolFailureEnvelope(
        code: "backend_tool_unreachable", message: "\u{FFFF}\u{0000}")

      let payload = try XCTUnwrap(
        JSONSerialization.jsonObject(with: Data(json.utf8)) as? [String: Any])
      XCTAssertEqual(payload["ok"] as? Bool, false)
      XCTAssertNotNil(payload["error"])
    }
  }
#endif
