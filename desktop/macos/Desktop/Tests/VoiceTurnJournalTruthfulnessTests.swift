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
