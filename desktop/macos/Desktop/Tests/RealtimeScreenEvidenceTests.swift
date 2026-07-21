import VoiceTurnDomain
import XCTest

@testable import Omi_Computer

final class RealtimeScreenEvidenceTests: XCTestCase {
  private let turnID = VoiceTurnID(UUID(uuidString: "00000000-0000-0000-0000-000000000001")!)
  private let responseID = VoiceResponseID("response-1")
  private let sessionObjectID = ObjectIdentifier(RealtimeScreenEvidenceTests.self)
  private let freshNow = Date(timeIntervalSince1970: 1_004)

  private func evidence(
    id: String = "evidence-1",
    app: String? = "Codex",
    bytes: Int = 900_000,
    target: RealtimeScreenEvidenceTarget = .frontmostDisplay,
    captureFailure: RealtimeScreenEvidenceCaptureFailure? = nil
  ) -> RealtimeScreenEvidenceDescriptor {
    RealtimeScreenEvidenceDescriptor(
      evidenceID: id,
      turnID: turnID,
      capturedAt: Date(timeIntervalSince1970: 1_000),
      target: target,
      frontmostApp: app,
      frontmostBundleID: "com.openai.codex",
      windowID: 7,
      displayID: 3,
      imageByteCount: bytes,
      imageDigest: bytes > 0 ? "digest" : nil,
      captureFailure: captureFailure)
  }

  func testScreenRecordingDenialIsNotTreatedAsAVisualObservation() {
    let denied = evidence(
      bytes: 0,
      target: .unavailable,
      captureFailure: .screenRecordingPermissionRequired)

    XCTAssertFalse(denied.canVerifyCurrentScreen)
    XCTAssertEqual(
      RealtimeScreenGroundingPolicy.failureText(for: denied),
      "I need Screen Recording permission before I can view your screen. Say ‘grant it’ and I’ll open the permission request."
    )
  }

  func testUnavailableScreenEvidenceContinuesThroughTheNormalVoiceProvider() {
    let denied = evidence(
      bytes: 0,
      target: .unavailable,
      captureFailure: .screenRecordingPermissionRequired)
    let unavailable = evidence(
      bytes: 0,
      target: .unavailable,
      captureFailure: .captureUnavailable)

    XCTAssertEqual(
      RealtimeScreenGroundingPolicy.failureDisposition(for: denied),
      .providerContinuation
    )
    XCTAssertEqual(
      RealtimeScreenGroundingPolicy.failureDisposition(for: unavailable),
      .providerContinuation
    )
  }

  private func request(
    descriptor: RealtimeScreenEvidenceDescriptor? = nil,
    callID: String = "screenshot-1",
    epoch: Int = 7
  ) -> RealtimeScreenScreenshotRequest {
    let token = VoiceScreenEvidenceProtocolToken(
      turnID: turnID,
      screenshotCallID: VoiceToolCallID(callID),
      screenshotIdentity: VoiceEffectIdentity(turnID: turnID, effectID: 1))
    return RealtimeScreenScreenshotRequest(
      descriptor: descriptor ?? evidence(),
      turnID: turnID,
      responseID: responseID,
      sessionObjectID: sessionObjectID,
      screenshotCallID: callID,
      protocolToken: token,
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

  func testAcceptedScreenEvidenceReopensProviderOutputForTheGroundedAnswer() {
    XCTAssertTrue(
      RealtimeScreenGroundingState.awaitingReport(receipt()).suppressesProviderOutput,
      "output stays gated until the provider proves it used the current evidence")
    XCTAssertFalse(
      RealtimeScreenGroundingState.accepted(receipt()).suppressesProviderOutput,
      "the verified provider continuation is the user-facing answer and must not be discarded")
  }

  func testProviderOutputPresentationHasOneContractForAudioAndText() {
    XCTAssertEqual(
      RealtimeProviderOutputPresentationPolicy.decide(
        screenGroundingState: .awaitingReport(receipt()),
        reducerOutputSuppressed: false),
      .suppressScreenGrounding)
    XCTAssertEqual(
      RealtimeProviderOutputPresentationPolicy.decide(
        screenGroundingState: .accepted(receipt()),
        reducerOutputSuppressed: false),
      .present,
      "the verified continuation must reach both native audio and text presentation")
    XCTAssertEqual(
      RealtimeProviderOutputPresentationPolicy.decide(
        screenGroundingState: .inactive,
        reducerOutputSuppressed: false),
      .present,
      "a durable spawn receipt does not preempt native realtime audio")
    XCTAssertEqual(
      RealtimeProviderOutputPresentationPolicy.decide(
        screenGroundingState: .inactive,
        reducerOutputSuppressed: true),
      .suppressReducerOwnedOutput)
  }

  func testProtocolTokenSurvivesTransportReceiptAndLocalRejection() {
    let request = request()
    let receipt = RealtimeScreenObservationReceipt(request: request, descriptor: evidence())

    XCTAssertEqual(receipt.protocolToken, request.protocolToken)
    XCTAssertEqual(
      RealtimeScreenGroundingState.rejected(receipt.descriptor, receipt.protocolToken).protocolToken,
      request.protocolToken)
    XCTAssertEqual(RealtimeScreenGroundingState.awaitingReport(receipt).diagnosticsLabel, "awaiting_report")
  }

  func testFreshnessRemainingLifetimeEndsAtTheSameFiveSecondBoundary() {
    let descriptor = evidence()

    XCTAssertEqual(
      RealtimeScreenEvidenceFreshnessPolicy.remainingLifetime(
        descriptor,
        now: Date(timeIntervalSince1970: 1_004)),
      1,
      accuracy: 0.001)
    XCTAssertEqual(
      RealtimeScreenEvidenceFreshnessPolicy.remainingLifetime(
        descriptor,
        now: Date(timeIntervalSince1970: 1_006)),
      0)
  }

  func testTransportDispatchedReceiptAdmitsScreenReportWithoutInputTranscript() {
    let state = RealtimeScreenGroundingState.awaitingReport(receipt())

    XCTAssertEqual(
      RealtimeScreenGroundingPolicy.reportDecision(
        state: state,
        observation: "A dark editor window.",
        sourceObjectID: sessionObjectID,
        activeTurnID: turnID,
        activeResponseID: responseID,
        currentTurnEpoch: 7,
        now: freshNow),
      .accepted)
  }

  func testReportBeforeTransportReceiptIsRejectedWithoutRedeemingItLater() {
    let state = RealtimeScreenGroundingState.awaitingScreenshot(request())

    XCTAssertEqual(
      RealtimeScreenGroundingPolicy.reportDecision(
        state: state,
        observation: "A dark editor window.",
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
        observation: "A dark editor window.",
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

    XCTAssertEqual(
      RealtimeScreenGroundingPolicy.receiptAfterTransportEnqueued(
        state: state,
        attachment: attachment,
        sourceObjectID: sessionObjectID,
        activeTurnID: turnID,
        activeResponseID: responseID,
        currentTurnEpoch: 7,
        enqueuedTurnEpoch: 7,
        callID: "different-screenshot-call"),
      .notAdmitted)
    guard
      case .accepted(let receipt) =
        RealtimeScreenGroundingPolicy.receiptAfterTransportEnqueued(
          state: state,
          attachment: attachment,
          sourceObjectID: sessionObjectID,
          activeTurnID: turnID,
          activeResponseID: responseID,
          currentTurnEpoch: 7,
          enqueuedTurnEpoch: 7,
          callID: "screenshot-1",
          now: Date(timeIntervalSince1970: 1_004.999))
    else {
      return XCTFail("Expected the matching transport enqueue to mint a receipt")
    }
    XCTAssertEqual(receipt.screenshotCallID, "screenshot-1")
  }

  func testTransportEnqueueFailsClosedWhenFrozenEvidenceExpires() {
    let descriptor = evidence()
    let attachment = RealtimeScreenEvidenceAttachment(descriptor: descriptor, jpeg: Data([1, 2, 3]))

    XCTAssertEqual(
      RealtimeScreenGroundingPolicy.receiptAfterTransportEnqueued(
        state: .awaitingScreenshot(request(descriptor: descriptor)),
        attachment: attachment,
        sourceObjectID: sessionObjectID,
        activeTurnID: turnID,
        activeResponseID: responseID,
        currentTurnEpoch: 7,
        enqueuedTurnEpoch: 7,
        callID: "screenshot-1",
        now: Date(timeIntervalSince1970: 1_005)),
      .evidenceExpired(descriptor))
  }

  func testExpiredEvidenceFromOldEnqueueEpochCannotRejectCurrentTurn() {
    let descriptor = evidence()
    let attachment = RealtimeScreenEvidenceAttachment(descriptor: descriptor, jpeg: Data([1, 2, 3]))

    XCTAssertEqual(
      RealtimeScreenGroundingPolicy.receiptAfterTransportEnqueued(
        state: .awaitingScreenshot(request(descriptor: descriptor)),
        attachment: attachment,
        sourceObjectID: sessionObjectID,
        activeTurnID: turnID,
        activeResponseID: responseID,
        currentTurnEpoch: 7,
        enqueuedTurnEpoch: 6,
        callID: "screenshot-1",
        now: Date(timeIntervalSince1970: 1_005)),
      .notAdmitted)
  }

  func testReportRemainsAdmissibleAfterFreshTransportReceiptExpires() {
    // The JPEG crossed into the provider transport at <5 seconds. Its later model report must
    // be bounded by the dedicated report deadline, not reclassified as an older screen.
    XCTAssertEqual(
      RealtimeScreenGroundingPolicy.reportDecision(
        state: .awaitingReport(receipt()),
        observation: "A dark editor window.",
        sourceObjectID: sessionObjectID,
        activeTurnID: turnID,
        activeResponseID: responseID,
        currentTurnEpoch: 7,
        now: Date(timeIntervalSince1970: 1_005)),
      .accepted)
  }

  func testReportDeadlineIsIndependentOfCaptureFreshness() {
    XCTAssertEqual(RealtimeScreenEvidenceProtocolPolicy.maximumReportWait, 8)
    XCTAssertLessThan(
      RealtimeScreenEvidenceFreshnessPolicy.maximumAge,
      RealtimeScreenEvidenceProtocolPolicy.maximumReportWait)
  }

  func testContradictoryApplicationTextCannotVerifyScreenGrounding() {
    let descriptor = evidence()
    let decision = RealtimeScreenGroundingPolicy.reportDecision(
      state: .awaitingReport(receipt(descriptor: descriptor)),
      observation: "You are in Cursor.",
      sourceObjectID: sessionObjectID,
      activeTurnID: turnID,
      activeResponseID: responseID,
      currentTurnEpoch: 7,
      now: freshNow)
    XCTAssertEqual(decision, .contradictoryApplication)
  }

  func testFrozenReceiptDoesNotDependOnLaterAmbientApplicationState() {
    XCTAssertEqual(
      RealtimeScreenGroundingPolicy.reportDecision(
        state: .awaitingReport(receipt()),
        observation: "You are in Codex.",
        sourceObjectID: sessionObjectID,
        activeTurnID: turnID,
        activeResponseID: responseID,
        currentTurnEpoch: 7,
        now: freshNow),
      .accepted,
      "only the frontmost app stored in the frozen receipt may participate in verification")
  }

  func testGenericApplicationLanguageDoesNotRejectFinderGroundedVisualDetail() {
    let descriptor = evidence(app: "Finder")

    XCTAssertEqual(
      RealtimeScreenGroundingPolicy.reportDecision(
        state: .awaitingReport(receipt(descriptor: descriptor)),
        observation: "I see a file manager window with multiple application windows on the left.",
        sourceObjectID: sessionObjectID,
        activeTurnID: turnID,
        activeResponseID: responseID,
        currentTurnEpoch: 7,
        now: freshNow),
      .accepted)
  }

  func testVisibleNonForegroundAppDoesNotRejectVisualDetail() {
    let descriptor = evidence(app: "Finder")

    XCTAssertEqual(
      RealtimeScreenGroundingPolicy.reportDecision(
        state: .awaitingReport(receipt(descriptor: descriptor)),
        observation: "A Cursor document is visible behind the Finder window.",
        sourceObjectID: sessionObjectID,
        activeTurnID: turnID,
        activeResponseID: responseID,
        currentTurnEpoch: 7,
        now: freshNow),
      .accepted)
  }

  func testEmptyReportIsRejectedAfterLocalDispatch() {
    XCTAssertEqual(
      RealtimeScreenGroundingPolicy.reportDecision(
        state: .awaitingReport(receipt()),
        observation: " ",
        sourceObjectID: sessionObjectID,
        activeTurnID: turnID,
        activeResponseID: responseID,
        currentTurnEpoch: 7,
        now: freshNow),
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
