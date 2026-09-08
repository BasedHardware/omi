import VoiceTurnDomain
import XCTest

@testable import Omi_Computer

/// The failure half of the PTT screen protocol.
///
/// A quarter of first "what's on my screen?" questions ended in the canned local string
/// "I couldn't verify the current screen." with no cause: the rejection path routed on a
/// reason string instead of the permission-aware disposition, and a turn with no installed
/// evidence minted a zero report deadline that expired in the same run loop.
///
/// The controller's screen protocol has no hermetic seam — `admitScreenScreenshotRequest` and
/// `markScreenEvidenceTransportEnqueued` both require a live `RealtimeHubSession` plus a
/// reducer-published protocol token — so these drive the pure policies the controller now
/// consults for every one of those decisions.
final class RealtimeScreenEvidenceHonestFailureTests: XCTestCase {
  private let turnID = VoiceTurnID(UUID(uuidString: "00000000-0000-0000-0000-0000000000a1") ?? UUID())
  private let otherTurnID = VoiceTurnID(UUID(uuidString: "00000000-0000-0000-0000-0000000000a2") ?? UUID())
  private let responseID = VoiceResponseID("response-1")
  private let sessionObjectID = ObjectIdentifier(RealtimeScreenEvidenceHonestFailureTests.self)

  private func evidence(
    app: String? = "Codex",
    bytes: Int = 900_000,
    target: RealtimeScreenEvidenceTarget = .frontmostDisplay,
    captureFailure: RealtimeScreenEvidenceCaptureFailure? = nil
  ) -> RealtimeScreenEvidenceDescriptor {
    RealtimeScreenEvidenceDescriptor(
      evidenceID: "evidence-1",
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

  private func request(
    descriptor: RealtimeScreenEvidenceDescriptor?,
    turnID: VoiceTurnID? = nil,
    callID: String = "screenshot-1",
    epoch: Int = 7
  ) -> RealtimeScreenScreenshotRequest {
    let turn = turnID ?? self.turnID
    return RealtimeScreenScreenshotRequest(
      descriptor: descriptor,
      turnID: turn,
      responseID: responseID,
      sessionObjectID: sessionObjectID,
      screenshotCallID: callID,
      protocolToken: VoiceScreenEvidenceProtocolToken(
        turnID: turn,
        screenshotCallID: VoiceToolCallID(callID),
        screenshotIdentity: VoiceEffectIdentity(turnID: turn, effectID: 1)),
      turnEpoch: epoch)
  }

  // MARK: - (a) Expiry with nothing captured is recoverable

  /// The primary fresh-install defect. Before the fix, a protocol that expired without any
  /// installed evidence skipped the disposition entirely (the recoverable exit was gated on
  /// `reason == "capture_unavailable"`) and spoke the canned local string.
  func testProtocolExpiryWithNoInstalledEvidenceStaysRecoverable() {
    XCTAssertEqual(
      RealtimeScreenGroundingPolicy.rejectionDisposition(for: nil),
      .providerContinuation,
      "nothing was captured, so the provider must be allowed to explain why")
  }

  // MARK: - (e) A follow-up turn in a locked session gets the full report window

  /// `enterLockedListening` only captures when there is no live transcription service, and
  /// `resetScreenGrounding` nils the evidence for the new turn ID — so the second screen
  /// question in one locked session admits its protocol with no evidence installed. That used
  /// to mint `expiresAfter = 0`.
  func testFollowUpTurnWithoutEvidenceGetsTheFullReportWindow() {
    XCTAssertEqual(
      RealtimeScreenEvidenceProtocolPolicy.reportDeadline(hasInstalledEvidence: false),
      RealtimeScreenEvidenceProtocolPolicy.maximumReportWait)
    XCTAssertEqual(
      RealtimeScreenEvidenceProtocolPolicy.reportDeadline(hasInstalledEvidence: true),
      RealtimeScreenEvidenceProtocolPolicy.maximumReportWait)
    XCTAssertGreaterThan(
      RealtimeScreenEvidenceProtocolPolicy.reportDeadline(hasInstalledEvidence: false),
      0,
      "a zero deadline expires the protocol before the screenshot tool can reach the provider")
  }

  // MARK: - (b) Granted after launch is its own failure, not "capture unavailable"

  func testGrantGrantedAfterLaunchIsReportedAsNeedingARelaunch() {
    XCTAssertEqual(
      RealtimeScreenEvidenceCapture.captureFailure(
        grantedNow: true, grantedAtLaunch: false, capturedImage: false),
      .screenRecordingNeedsRelaunch)
    XCTAssertEqual(
      RealtimeScreenEvidenceCapture.captureFailure(
        grantedNow: false, grantedAtLaunch: false, capturedImage: false),
      .screenRecordingPermissionRequired)
    XCTAssertEqual(
      RealtimeScreenEvidenceCapture.captureFailure(
        grantedNow: true, grantedAtLaunch: true, capturedImage: false),
      .captureUnavailable,
      "a grant that is live in this process makes a nil image a genuine capture failure")
    XCTAssertNil(
      RealtimeScreenEvidenceCapture.captureFailure(
        grantedNow: true, grantedAtLaunch: true, capturedImage: true))
  }

  func testRelaunchFailureContinuesThroughTheProviderAndNamesTheFix() {
    let relaunch = evidence(
      bytes: 0, target: .unavailable, captureFailure: .screenRecordingNeedsRelaunch)

    XCTAssertEqual(
      RealtimeScreenGroundingPolicy.failureDisposition(for: relaunch), .providerContinuation)
    let spoken = RealtimeScreenGroundingPolicy.failureText(for: relaunch)
    XCTAssertNotEqual(spoken, "I couldn't verify the current screen.")
    XCTAssertTrue(spoken.lowercased().contains("open it again"))
  }

  func testRelaunchToolResultCarriesItsOwnErrorCodeAlongsidePermissionRequired() throws {
    let relaunch = try payload(
      RealtimeHubTools.screenshotToolResult(
        capturedBytes: nil, captureFailure: .screenRecordingNeedsRelaunch))
    let permission = try payload(
      RealtimeHubTools.screenshotToolResult(
        capturedBytes: nil, captureFailure: .screenRecordingPermissionRequired))

    XCTAssertEqual(relaunch["ok"] as? Bool, false)
    let relaunchError = try XCTUnwrap(relaunch["error"] as? [String: Any])
    XCTAssertEqual(relaunchError["code"] as? String, "screen_recording_needs_relaunch")
    let message = try XCTUnwrap(relaunchError["message"] as? String).lowercased()
    XCTAssertTrue(message.contains("after omi launched"))
    XCTAssertTrue(message.contains("quit omi"))
    XCTAssertNil(
      relaunchError["next_tool"],
      "asking for the permission again cannot repair a grant that is already granted")

    let permissionError = try XCTUnwrap(permission["error"] as? [String: Any])
    XCTAssertEqual(permissionError["code"] as? String, "permission_required")
  }

  private func payload(_ json: String) throws -> [String: Any] {
    let data = try XCTUnwrap(json.data(using: .utf8))
    return try XCTUnwrap(try JSONSerialization.jsonObject(with: data) as? [String: Any])
  }

  // MARK: - (c) Table: what reopens the provider and what stays local

  /// Every rejection reason the controller can raise, paired with nothing captured. None of
  /// them may consume the turn with a local terminal answer — there is no evidence to be
  /// authoritative about.
  func testEveryRejectionReasonWithoutEvidenceReopensProviderOutput() {
    let reasons = [
      "report_deadline_expired",
      "evidence_expired",
      "capture_unavailable",
      "tool_wire_enqueue_failed",
      RealtimeScreenGroundingPolicy.transportNotAdmittedReason,
      "evidence_unavailable",
      "transport_not_dispatched",
      "stale_receipt",
      "contradictory_application",
      "empty_answer",
      "evidence_state_changed",
      "continuation_provider_failed",
    ]
    for reason in reasons {
      XCTAssertEqual(
        RealtimeScreenGroundingPolicy.rejectionDisposition(for: nil),
        .providerContinuation,
        "reason \(reason) must not mint a local terminal answer without evidence")
    }
  }

  func testEveryCaptureFailureReopensProviderOutput() {
    for failure in RealtimeScreenEvidenceCaptureFailure.allCases {
      let descriptor = evidence(bytes: 0, target: .unavailable, captureFailure: failure)
      XCTAssertEqual(
        RealtimeScreenGroundingPolicy.rejectionDisposition(for: descriptor),
        .providerContinuation,
        "\(failure.rawValue) is a capability failure the provider can explain")
      XCTAssertFalse(descriptor.canVerifyCurrentScreen)
    }
  }

  /// The other half of the contract: a real capture that then went stale or contradicted the
  /// native frontmost app is still the deterministic local result. Loosening that would let a
  /// model talk about a screen it demonstrably misread.
  func testCapturedEvidenceThatFailsVerificationStaysDeterministic() {
    let captured = evidence()

    XCTAssertEqual(
      RealtimeScreenGroundingPolicy.rejectionDisposition(for: captured),
      .authoritativeLocalResult)
    XCTAssertEqual(
      RealtimeScreenGroundingPolicy.failureText(for: captured),
      "I couldn't verify the current screen.")

    let receipt = RealtimeScreenObservationReceipt(
      request: request(descriptor: captured), descriptor: captured)
    XCTAssertEqual(
      RealtimeScreenGroundingPolicy.reportDecision(
        state: .awaitingReport(receipt),
        observation: "You are in Cursor.",
        sourceObjectID: sessionObjectID,
        activeTurnID: turnID,
        activeResponseID: responseID,
        currentTurnEpoch: 7),
      .contradictoryApplication)
    XCTAssertEqual(
      RealtimeScreenGroundingPolicy.reportDecision(
        state: .awaitingReport(receipt),
        observation: "A dark editor window.",
        sourceObjectID: sessionObjectID,
        activeTurnID: turnID,
        activeResponseID: responseID,
        currentTurnEpoch: 9),
      .staleReceipt)
  }

  // MARK: - (d) A not-admitted transport is rejected, not left pending

  func testNotAdmittedTransportForTheCurrentCallIsRejectedWithANamedReason() {
    let descriptor = evidence()
    let outcome = RealtimeScreenGroundingPolicy.outcomeForNotAdmittedTransport(
      state: .awaitingScreenshot(request(descriptor: descriptor)),
      activeTurnID: turnID,
      currentTurnEpoch: 7,
      enqueuedTurnEpoch: 7,
      callID: "screenshot-1")

    XCTAssertEqual(outcome, .reject(descriptor))
    XCTAssertEqual(RealtimeScreenGroundingPolicy.transportNotAdmittedReason, "transport_not_admitted")
  }

  func testNotAdmittedTransportWithNoEvidenceRejectsAndStaysRecoverable() {
    let outcome = RealtimeScreenGroundingPolicy.outcomeForNotAdmittedTransport(
      state: .awaitingScreenshot(request(descriptor: nil)),
      activeTurnID: turnID,
      currentTurnEpoch: 7,
      enqueuedTurnEpoch: 7,
      callID: "screenshot-1")

    guard case .reject(let descriptor) = outcome else {
      return XCTFail("an admitted protocol that cannot enqueue must not stay pending")
    }
    XCTAssertNil(descriptor)
    XCTAssertEqual(
      RealtimeScreenGroundingPolicy.rejectionDisposition(for: descriptor), .providerContinuation)
  }

  /// The safety half: a late callback from a superseded turn, epoch, or tool call must stay a
  /// no-op so it cannot terminate the protocol that replaced it.
  func testStaleNotAdmittedCallbacksRemainNoOps() {
    let descriptor = evidence()
    let state = RealtimeScreenGroundingState.awaitingScreenshot(request(descriptor: descriptor))

    XCTAssertEqual(
      RealtimeScreenGroundingPolicy.outcomeForNotAdmittedTransport(
        state: state,
        activeTurnID: turnID,
        currentTurnEpoch: 7,
        enqueuedTurnEpoch: 6,
        callID: "screenshot-1"),
      .ignoreStaleCallback)
    XCTAssertEqual(
      RealtimeScreenGroundingPolicy.outcomeForNotAdmittedTransport(
        state: state,
        activeTurnID: turnID,
        currentTurnEpoch: 7,
        enqueuedTurnEpoch: 7,
        callID: "a-different-screenshot-call"),
      .ignoreStaleCallback)
    XCTAssertEqual(
      RealtimeScreenGroundingPolicy.outcomeForNotAdmittedTransport(
        state: state,
        activeTurnID: otherTurnID,
        currentTurnEpoch: 7,
        enqueuedTurnEpoch: 7,
        callID: "screenshot-1"),
      .ignoreStaleCallback)
    XCTAssertEqual(
      RealtimeScreenGroundingPolicy.outcomeForNotAdmittedTransport(
        state: .awaitingReport(
          RealtimeScreenObservationReceipt(
            request: request(descriptor: descriptor), descriptor: descriptor)),
        activeTurnID: turnID,
        currentTurnEpoch: 7,
        enqueuedTurnEpoch: 7,
        callID: "screenshot-1"),
      .ignoreStaleCallback)
  }

  // MARK: - RC-5: the prompt claims an image only where one is attached

  func testScreenRuleClaimsAnAttachedImageOnlyWhenOneIsAttached() {
    let attached = RealtimeHubTools.screenRule(turnFrameAttached: true)
    let notAttached = RealtimeHubTools.screenRule(turnFrameAttached: false)

    XCTAssertTrue(attached.contains("every turn arrives with an image of the user's screen"))
    XCTAssertFalse(notAttached.contains("every turn arrives with an image of the user's screen"))
    XCTAssertTrue(notAttached.contains("needs the screenshot tool first"))
    for rule in [attached, notAttached] {
      XCTAssertTrue(rule.contains("report_screen_observation"), "grounding contract is unconditional")
    }
  }
}
