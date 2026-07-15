import XCTest

@testable import Omi_Computer

final class RealtimeScreenEvidenceTests: XCTestCase {
  private let turnID = VoiceTurnID(UUID(uuidString: "00000000-0000-0000-0000-000000000001")!)
  private let responseID = VoiceResponseID("response-1")
  private let sessionObjectID = ObjectIdentifier(RealtimeScreenEvidenceTests.self)

  private func evidence(
    id: String = "evidence-1",
    app: String? = "Codex",
    bytes: Int = 900_000
  ) -> RealtimeScreenEvidenceDescriptor {
    RealtimeScreenEvidenceDescriptor(
      evidenceID: id,
      turnID: turnID,
      capturedAt: Date(timeIntervalSince1970: 1_000),
      target: .frontmostDisplay,
      frontmostApp: app,
      frontmostBundleID: "com.openai.codex",
      windowID: 7,
      displayID: 3,
      imageByteCount: bytes,
      imageDigest: bytes > 0 ? "digest" : nil)
  }

  private func request(
    descriptor: RealtimeScreenEvidenceDescriptor? = nil,
    callID: String = "screenshot-1",
    epoch: Int = 7
  ) -> RealtimeScreenScreenshotRequest {
    RealtimeScreenScreenshotRequest(
      descriptor: descriptor ?? evidence(),
      turnID: turnID,
      responseID: responseID,
      sessionObjectID: sessionObjectID,
      screenshotCallID: callID,
      turnEpoch: epoch)
  }

  private func receipt(
    descriptor: RealtimeScreenEvidenceDescriptor? = nil,
    callID: String = "screenshot-1",
    epoch: Int = 7
  ) -> RealtimeScreenObservationReceipt {
    let descriptor = descriptor ?? evidence()
    return RealtimeScreenObservationReceipt(
      request: request(descriptor: descriptor, callID: callID, epoch: epoch),
      descriptor: descriptor)
  }

  func testPTTCaptureStartsInertUntilScreenshotToolIsAdmitted() {
    XCTAssertFalse(RealtimeScreenGroundingState.inactive.suppressesProviderOutput)
    XCTAssertTrue(
      RealtimeScreenGroundingState.awaitingScreenshot(request()).suppressesProviderOutput)
  }

  func testTransportDispatchedReceiptAdmitsScreenReportWithoutInputTranscript() {
    let state = RealtimeScreenGroundingState.awaitingReport(receipt())

    XCTAssertEqual(
      RealtimeScreenGroundingPolicy.reportDecision(
        state: state,
        answer: "A dark editor window.",
        sourceObjectID: sessionObjectID,
        activeTurnID: turnID,
        activeResponseID: responseID,
        currentTurnEpoch: 7),
      .accepted)
  }

  func testReportBeforeTransportReceiptIsRejectedWithoutRedeemingItLater() {
    let state = RealtimeScreenGroundingState.awaitingScreenshot(request())

    XCTAssertEqual(
      RealtimeScreenGroundingPolicy.reportDecision(
        state: state,
        answer: "A dark editor window.",
        sourceObjectID: sessionObjectID,
        activeTurnID: turnID,
        activeResponseID: responseID,
        currentTurnEpoch: 7),
      .evidenceUnavailable)
  }

  func testReceiptRequiresCurrentSessionResponseTurnAndEpoch() {
    let state = RealtimeScreenGroundingState.awaitingReport(receipt())

    XCTAssertEqual(
      RealtimeScreenGroundingPolicy.reportDecision(
        state: state,
        answer: "A dark editor window.",
        sourceObjectID: sessionObjectID,
        activeTurnID: turnID,
        activeResponseID: responseID,
        currentTurnEpoch: 8),
      .staleReceipt)
  }

  func testScreenshotTransportDispatchRequiresTheExactAdmittedToolCall() {
    let descriptor = evidence()
    let request = request(descriptor: descriptor)
    let attachment = RealtimeScreenEvidenceAttachment(descriptor: descriptor, jpeg: Data([1, 2, 3]))

    XCTAssertFalse(
      request.acceptsTransportDispatch(
        attachment: attachment,
        sourceObjectID: sessionObjectID,
        activeTurnID: turnID,
        activeResponseID: responseID,
        currentTurnEpoch: 7,
        callID: "different-screenshot-call"))
    XCTAssertTrue(
      request.acceptsTransportDispatch(
        attachment: attachment,
        sourceObjectID: sessionObjectID,
        activeTurnID: turnID,
        activeResponseID: responseID,
        currentTurnEpoch: 7,
        callID: "screenshot-1"))
  }

  func testTransportReceiptCannotExistUntilTheExactWireEnqueueCallback() {
    let descriptor = evidence()
    let attachment = RealtimeScreenEvidenceAttachment(descriptor: descriptor, jpeg: Data([1, 2, 3]))
    let state = RealtimeScreenGroundingState.awaitingScreenshot(request(descriptor: descriptor))

    XCTAssertNil(
      RealtimeScreenGroundingPolicy.receiptAfterTransportEnqueued(
        state: state,
        attachment: attachment,
        sourceObjectID: sessionObjectID,
        activeTurnID: turnID,
        activeResponseID: responseID,
        currentTurnEpoch: 7,
        callID: "different-screenshot-call"))
    XCTAssertEqual(
      RealtimeScreenGroundingPolicy.receiptAfterTransportEnqueued(
        state: state,
        attachment: attachment,
        sourceObjectID: sessionObjectID,
        activeTurnID: turnID,
        activeResponseID: responseID,
        currentTurnEpoch: 7,
        callID: "screenshot-1")?.screenshotCallID,
      "screenshot-1")
  }

  func testContradictoryApplicationTextCannotReachNativePresentation() {
    let descriptor = evidence()
    let decision = RealtimeScreenGroundingPolicy.reportDecision(
      state: .awaitingReport(receipt(descriptor: descriptor)),
      answer: "You are in Cursor.",
      sourceObjectID: sessionObjectID,
      activeTurnID: turnID,
      activeResponseID: responseID,
      currentTurnEpoch: 7,
      knownApplicationNames: ["Codex", "Cursor"])

    XCTAssertEqual(decision, .contradictoryApplication)
    XCTAssertEqual(
      RealtimeScreenGroundingPolicy.presentedAnswer(
        evidence: descriptor,
        answer: "A dark editor window."),
      "The frontmost app is Codex. A dark editor window.")
  }

  func testGenericApplicationLanguageDoesNotRejectFinderGroundedVisualDetail() {
    let descriptor = evidence(app: "Finder")

    XCTAssertEqual(
      RealtimeScreenGroundingPolicy.reportDecision(
        state: .awaitingReport(receipt(descriptor: descriptor)),
        answer: "I see a file manager window with multiple application windows on the left.",
        sourceObjectID: sessionObjectID,
        activeTurnID: turnID,
        activeResponseID: responseID,
        currentTurnEpoch: 7,
        knownApplicationNames: ["Finder", "Codex", "Cursor"]),
      .accepted)
  }

  func testVisibleNonForegroundAppDoesNotRejectVisualDetail() {
    let descriptor = evidence(app: "Finder")

    XCTAssertEqual(
      RealtimeScreenGroundingPolicy.reportDecision(
        state: .awaitingReport(receipt(descriptor: descriptor)),
        answer: "A Cursor document is visible behind the Finder window.",
        sourceObjectID: sessionObjectID,
        activeTurnID: turnID,
        activeResponseID: responseID,
        currentTurnEpoch: 7,
        knownApplicationNames: ["Finder", "Cursor"]),
      .accepted)
  }

  func testEmptyReportIsRejectedAfterLocalDispatch() {
    XCTAssertEqual(
      RealtimeScreenGroundingPolicy.reportDecision(
        state: .awaitingReport(receipt()),
        answer: " ",
        sourceObjectID: sessionObjectID,
        activeTurnID: turnID,
        activeResponseID: responseID,
        currentTurnEpoch: 7),
      .emptyAnswer)
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
    let replacementTurn = VoiceTurnID(UUID(uuidString: "00000000-0000-0000-0000-000000000002")!)
    let captured = evidence(id: "old-evidence")

    XCTAssertNil(
      RealtimeScreenEvidenceToolExecutionPolicy.failureEvidence(
        capturedEvidence: captured,
        commandTurnID: turnID,
        activeTurnID: replacementTurn,
        invocationIsCurrent: false))
  }
}
