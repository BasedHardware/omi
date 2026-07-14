import XCTest

@testable import Omi_Computer

final class RealtimeScreenEvidenceTests: XCTestCase {
  private func evidence(
    id: String = "evidence-1",
    app: String? = "Codex",
    bytes: Int = 900_000
  ) -> RealtimeScreenEvidenceDescriptor {
    RealtimeScreenEvidenceDescriptor(
      evidenceID: id,
      turnID: VoiceTurnID(UUID(uuidString: "00000000-0000-0000-0000-000000000001")!),
      capturedAt: Date(timeIntervalSince1970: 1_000),
      target: .frontmostDisplay,
      frontmostApp: app,
      frontmostBundleID: "com.openai.codex",
      windowID: 7,
      displayID: 3,
      imageByteCount: bytes,
      imageDigest: bytes > 0 ? "digest" : nil
    )
  }

  func testCurrentScreenTranscriptRequiresExactTurnEvidenceReport() {
    let descriptor = evidence()
    let state = RealtimeScreenGroundingPolicy.stateAfterFinalTranscript(
      "What do you see on my screen?", evidence: descriptor)
    XCTAssertEqual(state, .awaitingReport(descriptor))
    XCTAssertEqual(
      RealtimeScreenGroundingPolicy.reportDecision(
        state: state,
        evidenceID: "evidence-1",
        frontmostApp: "codex",
        answer: "You have Codex open.",
        deliveredEvidenceID: "evidence-1"),
      .accepted)
  }

  func testCurrentScreenTranscriptFailsClosedWithoutVerifiableEvidence() {
    XCTAssertEqual(
      RealtimeScreenGroundingPolicy.stateAfterFinalTranscript(
        "What am I looking at?", evidence: nil),
      .rejected(nil))

    let unavailable = evidence(app: nil, bytes: 0)
    XCTAssertEqual(
      RealtimeScreenGroundingPolicy.stateAfterFinalTranscript(
        "What am I looking at?", evidence: unavailable),
      .rejected(unavailable))
  }

  func testScreenReportRejectsWrongEvidenceOrFrontmostApplication() {
    let descriptor = evidence()
    let state = RealtimeScreenGroundingState.awaitingReport(descriptor)
    XCTAssertEqual(
      RealtimeScreenGroundingPolicy.reportDecision(
        state: state,
        evidenceID: "stale-evidence",
        frontmostApp: "Codex",
        answer: "Codex",
        deliveredEvidenceID: "evidence-1"),
      .wrongEvidence)
    XCTAssertEqual(
      RealtimeScreenGroundingPolicy.reportDecision(
        state: state,
        evidenceID: "evidence-1",
        frontmostApp: "Cursor",
        answer: "Cursor is open.",
        deliveredEvidenceID: "evidence-1"),
      .wrongApplication)
  }

  func testReportBeforeFinalTranscriptCannotBecomeAnAcceptedScreenAnswer() {
    let descriptor = evidence()
    XCTAssertEqual(
      RealtimeScreenGroundingPolicy.reportDecision(
        state: .awaitingTranscript(descriptor),
        evidenceID: "evidence-1",
        frontmostApp: "Codex",
        answer: "Codex is open.",
        deliveredEvidenceID: "evidence-1"),
      .evidenceUnavailable)
  }

  func testReportWithoutScreenshotDeliveryFailsClosed() {
    let descriptor = evidence()
    XCTAssertEqual(
      RealtimeScreenGroundingPolicy.reportDecision(
        state: .awaitingReport(descriptor),
        evidenceID: "evidence-1",
        frontmostApp: "Codex",
        answer: "A dark editor window.",
        deliveredEvidenceID: nil),
      .screenshotNotDelivered)
  }

  func testContradictoryApplicationTextCannotReachNativePresentation() {
    let descriptor = evidence()
    let decision = RealtimeScreenGroundingPolicy.reportDecision(
      state: .awaitingReport(descriptor),
      evidenceID: "evidence-1",
      frontmostApp: "Codex",
      answer: "You are in Cursor.",
      deliveredEvidenceID: "evidence-1",
      knownApplicationNames: ["Codex", "Cursor"])

    XCTAssertEqual(decision, .contradictoryApplication)
    XCTAssertEqual(
      RealtimeScreenGroundingPolicy.presentedAnswer(
        evidence: descriptor,
        answer: "A dark editor window."),
      "The frontmost app is Codex. A dark editor window.")
  }

  func testEncodingReadinessWaitsForAndReturnsTheFrozenAttachment() async {
    let descriptor = evidence(bytes: 3)
    let expected = RealtimeScreenEvidence(
      descriptor: descriptor,
      preOverlayImage: nil,
      jpeg: Data([1, 2, 3]),
      encodingFinished: true)
    let readiness = RealtimeScreenEvidenceReadiness()
    let waiterStarted = DispatchSemaphore(value: 0)
    let waitTask = Task { () -> RealtimeScreenEvidence? in
      await withCheckedContinuation { continuation in
        DispatchQueue.global(qos: .userInitiated).async {
          waiterStarted.signal()
          continuation.resume(returning: readiness.wait(timeout: 1))
        }
      }
    }

    XCTAssertEqual(waiterStarted.wait(timeout: .now() + 1), .success)
    readiness.resolve(expected)
    let delivered = await waitTask.value

    XCTAssertEqual(delivered?.descriptor.evidenceID, descriptor.evidenceID)
    XCTAssertEqual(delivered?.jpeg, Data([1, 2, 3]))
  }

  func testBargeInDuringScreenshotReadinessCannotRejectReplacementTurn() {
    let originalTurn = VoiceTurnID(UUID(uuidString: "00000000-0000-0000-0000-000000000001")!)
    let replacementTurn = VoiceTurnID(UUID(uuidString: "00000000-0000-0000-0000-000000000002")!)
    let captured = RealtimeScreenEvidenceDescriptor(
      evidenceID: "old-evidence",
      turnID: originalTurn,
      capturedAt: Date(timeIntervalSince1970: 1_000),
      target: .frontmostDisplay,
      frontmostApp: "Codex",
      frontmostBundleID: "com.openai.codex",
      windowID: 7,
      displayID: 3,
      imageByteCount: 3,
      imageDigest: "digest")

    XCTAssertNil(
      RealtimeScreenEvidenceToolExecutionPolicy.failureEvidence(
        capturedEvidence: captured,
        commandTurnID: originalTurn,
        activeTurnID: replacementTurn,
        invocationIsCurrent: false))
  }

  func testNonvisualTranscriptDoesNotBlockProviderOutput() {
    XCTAssertEqual(
      RealtimeScreenGroundingPolicy.stateAfterFinalTranscript(
        "What did I ask you yesterday?", evidence: evidence()),
      .passthrough)
  }
}
