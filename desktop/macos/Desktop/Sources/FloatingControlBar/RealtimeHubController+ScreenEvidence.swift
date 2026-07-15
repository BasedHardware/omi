import Foundation

/// Owns the turn-scoped visual evidence boundary apart from the realtime transport lifecycle.
/// Keeping it separate makes its capture → attach → delivery → validation trace independently
/// reviewable, while the controller remains the sole owner of the voice-turn state machine.
extension RealtimeHubController {
  /// Called by PTT-down before Omi expands its overlay. This is the sole visual evidence
  /// candidate for the logical turn; a later provider screenshot request may only transmit
  /// these pixels, never trigger another physical capture.
  func installScreenEvidence(_ evidence: RealtimeScreenEvidence) {
    guard VoiceTurnCoordinator.shared.activeTurnID == evidence.descriptor.turnID else {
      return
    }
    let replacesRawCapture = screenEvidence?.descriptor.evidenceID == evidence.descriptor.evidenceID
    screenEvidence = evidence
    if !replacesRawCapture {
      logScreenEvidence(stage: "captured", evidence: evidence.descriptor)
      if !evidence.encodingFinished {
        startScreenEvidenceEncoding(evidence)
      }
    }
    if evidence.encodingFinished {
      logScreenEvidence(
        stage: evidence.isReadyForProviderDelivery ? "encoded" : "encode_failed",
        evidence: evidence.descriptor)
    }
  }

  func startScreenEvidenceEncoding(_ evidence: RealtimeScreenEvidence) {
    let readiness = RealtimeScreenEvidenceReadiness()
    screenEvidenceReadiness = readiness
    DispatchQueue.global(qos: .userInitiated).async {
      let encoded = RealtimeScreenEvidenceCapture.encode(evidence)
      readiness.resolve(encoded)
      DispatchQueue.main.async {
        guard VoiceTurnCoordinator.shared.activeTurnID == evidence.descriptor.turnID else { return }
        RealtimeHubController.shared.installScreenEvidence(encoded)
      }
    }
  }

  func screenshotToolResultTextForCurrentProvider(
    attachment: RealtimeScreenEvidenceAttachment?
  ) -> String {
    RealtimeHubTools.screenshotToolResult(capturedBytes: attachment?.jpeg.count)
  }

  func resetScreenGrounding(for turnID: VoiceTurnID) {
    if screenEvidence?.descriptor.turnID != turnID {
      screenEvidence = nil
      screenEvidenceReadiness = nil
    }
    // PTT-down capture is inert. A normal turn must never wait for a provider input
    // transcript; only a reducer-admitted screenshot request may seal provider output.
    screenGroundingState = .inactive
    screenAnswerPresented = false
  }

  func clearScreenGrounding(stage: String? = nil) {
    if let evidence = screenEvidence, let stage {
      logScreenEvidence(stage: stage, evidence: evidence.descriptor)
    }
    screenEvidence = nil
    screenEvidenceReadiness = nil
    screenGroundingState = .inactive
    authorizedRealtimeScreenshotImages.removeAll()
    screenAnswerPresented = false
  }

  /// Reserve the visual output gate only after the screenshot call has passed the normal
  /// reducer/session ownership admission. This is intentionally before JPEG work: a model must
  /// not leak an ungrounded answer while the one frozen image is still encoding.
  func admitScreenScreenshotRequest(
    source: RealtimeHubSession,
    turnID: VoiceTurnID,
    responseID: VoiceResponseID,
    callID: String,
    screenshotIdentity: VoiceEffectIdentity,
    turnEpoch: Int
  ) {
    guard case .inactive = screenGroundingState else { return }
    let token = VoiceScreenEvidenceProtocolToken(
      turnID: turnID,
      screenshotCallID: VoiceToolCallID(callID),
      screenshotIdentity: screenshotIdentity)
    let expiresAfter = screenEvidence.map {
      RealtimeScreenEvidenceFreshnessPolicy.remainingLifetime($0.descriptor, now: Date())
    } ?? 0
    VoiceTurnCoordinator.shared.send(
      .screenEvidenceProtocolStartedScoped(
        turnID: turnID,
        token: token,
        expiresAfter: expiresAfter))
    guard VoiceTurnCoordinator.shared.activeTurn?.screenEvidenceProtocol == token else {
      log("RealtimeHub: reducer rejected screen evidence protocol admission")
      return
    }
    let request = RealtimeScreenScreenshotRequest(
      descriptor: screenEvidence?.descriptor,
      turnID: turnID,
      responseID: responseID,
      sessionObjectID: ObjectIdentifier(source),
      screenshotCallID: callID,
      protocolToken: token,
      turnEpoch: turnEpoch)
    screenGroundingState = .awaitingScreenshot(request)
    if let evidence = request.descriptor {
      logScreenEvidence(stage: "screenshot_requested", evidence: evidence, callID: callID)
    } else {
      log("RealtimeHub: ptt_screen_evidence stage=screenshot_requested evidence=unavailable")
    }
  }

  /// The session reports this only after its local websocket transport has accepted the exact
  /// image/function-response wire. It is not a remote provider acknowledgement, so the receipt
  /// is scoped to the exact session, response, tool call, and epoch that created the image.
  func markScreenEvidenceTransportEnqueued(
    _ attachment: RealtimeScreenEvidenceAttachment,
    source: RealtimeHubSession,
    callID: String,
    turnEpoch: Int
  ) {
    let receiptDecision = RealtimeScreenGroundingPolicy.receiptAfterTransportEnqueued(
      state: screenGroundingState,
      attachment: attachment,
      sourceObjectID: ObjectIdentifier(source),
      activeTurnID: VoiceTurnCoordinator.shared.activeTurnID,
      activeResponseID: voiceResponseID,
      currentTurnEpoch: realtimeToolTurnEpoch,
      enqueuedTurnEpoch: turnEpoch,
      callID: callID)
    switch receiptDecision {
    case .accepted(let receipt):
      screenGroundingState = .awaitingReport(receipt)
      logScreenEvidence(stage: "tool_wire_enqueued", evidence: attachment.descriptor, callID: callID)
    case .evidenceExpired(let evidence):
      rejectScreenEvidence(evidence, reason: "evidence_expired")
    case .notAdmitted:
      return
    }
  }

  func logScreenEvidence(
    stage: String,
    evidence: RealtimeScreenEvidenceDescriptor,
    callID: String? = nil,
    imageTokenCount: Int? = nil
  ) {
    let ageMs = max(0, Int(Date().timeIntervalSince(evidence.capturedAt) * 1_000))
    let ageBucket = ageMs < 1_000 ? "lt_1s" : ageMs < 5_000 ? "lt_5s" : "gte_5s"
    let bytesBucket = evidence.imageByteCount == 0 ? "0" : evidence.imageByteCount < 256_000
      ? "lt_256k" : evidence.imageByteCount < 1_024_000 ? "lt_1m" : "gte_1m"
    let callHash = callID.map { KernelTurnProjection.stableTurnID(continuityKey: $0, role: "screen_call") }
      ?? ""
    let turn = String(evidence.turnID.rawValue.uuidString.prefix(8))
    let image = evidence.imageDigest.map { String($0.prefix(12)) } ?? ""
    let tokens = imageTokenCount.map(String.init) ?? ""
    let transcriptSeen = lastInputTranscriptUpdateAt != nil
    let message = "RealtimeHub: ptt_screen_evidence stage=\(stage) evidence=\(evidence.opaqueID) "
      + "provider=\(providerTag) turn=\(turn) epoch=\(realtimeToolTurnEpoch) "
      + "input_transcription_seen=\(transcriptSeen) target=\(evidence.target.rawValue) "
      + "capture_age=\(ageBucket) bytes=\(bytesBucket) "
      + "app=\(evidence.opaqueAppID ?? "") has_window=\(evidence.windowID != nil) "
      + "has_display=\(evidence.displayID != nil) image=\(image) "
      + "call=\(callHash.prefix(12)) image_tokens=\(tokens)"
    log(message)
  }

  func rejectScreenEvidence(
    _ evidence: RealtimeScreenEvidenceDescriptor?,
    reason: String
  ) {
    if case .rejected = screenGroundingState { return }
    guard let token = screenGroundingState.protocolToken else { return }
    screenGroundingState = .rejected(evidence, token)
    if let evidence {
      logScreenEvidence(stage: "report_rejected_\(reason)", evidence: evidence)
    }
    DesktopDiagnosticsManager.shared.recordFallback(
      area: "realtime_hub",
      from: "screen_evidence",
      to: "none",
      reason: "capability_mismatch",
      outcome: .exhausted,
      extra: ["screen_evidence_reason": reason, "user_visible": true])
    _ = completeScreenEvidenceProtocol(
      token,
      outcome: .failed,
      answer: RealtimeScreenGroundingPolicy.failureText)
  }

  /// A provider terminal/error may arrive without the report half of the screen
  /// protocol. Resolve its reducer-owned token while the turn is still live;
  /// terminal cleanup itself must only revoke late callbacks silently.
  @discardableResult
  func resolvePendingScreenEvidenceBeforeProviderTermination(
    turnID: VoiceTurnID,
    reason: VoiceTurnTerminalReason
  ) -> Bool {
    let evidence: RealtimeScreenEvidenceDescriptor?
    switch screenGroundingState {
    case .awaitingScreenshot(let request) where request.turnID == turnID:
      evidence = request.descriptor
    case .awaitingReport(let receipt) where receipt.turnID == turnID:
      evidence = receipt.descriptor
    case .inactive, .awaitingScreenshot, .awaitingReport, .accepted, .rejected:
      return false
    }
    rejectScreenEvidence(evidence, reason: "continuation_\(reason.rawValue)")
    return VoiceTurnCoordinator.shared.activeTurn?.providerFinished == true
  }

  /// The five-second freshness boundary is a protocol deadline, not a generic
  /// provider timeout. Its reducer-issued token makes a stale delayed callback
  /// unable to affect a replacement turn.
  func expireScreenEvidenceProtocol(turnID: VoiceTurnID, token: VoiceScreenEvidenceProtocolToken) {
    guard token.turnID == turnID,
      VoiceTurnCoordinator.shared.activeTurn?.screenEvidenceProtocol == token,
      screenGroundingState.protocolToken == token
    else { return }
    let evidence: RealtimeScreenEvidenceDescriptor?
    switch screenGroundingState {
    case .awaitingScreenshot(let request):
      evidence = request.descriptor
    case .awaitingReport(let receipt):
      evidence = receipt.descriptor
    case .inactive, .accepted, .rejected:
      return
    }
    rejectScreenEvidence(evidence, reason: "freshness_expired")
  }

  /// Registers the one canonical journal obligation before changing reducer
  /// completion state. The reducer then keeps tool/playback/journal fences in
  /// one place while a native screen answer replaces provider narration.
  @discardableResult
  func completeScreenEvidenceProtocol(
    _ token: VoiceScreenEvidenceProtocolToken,
    outcome: VoiceScreenEvidenceProtocolOutcome,
    answer: String
  ) -> Bool {
    guard VoiceTurnCoordinator.shared.activeTurnID == token.turnID,
      VoiceTurnCoordinator.shared.activeTurn?.screenEvidenceProtocol == token,
      let ownerID = VoiceTurnCoordinator.shared.requireCurrentOwner(for: token.turnID)
    else { return false }
    let presentedAnswer = answer.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !presentedAnswer.isEmpty else { return false }

    assistantText = presentedAnswer
    _ = enqueueAuthoritativeScreenEvidencePersistence(
      ownerID: ownerID,
      assistantText: presentedAnswer)
    VoiceTurnCoordinator.shared.send(
      .authoritativeLocalResultAcceptedScoped(
        turnID: token.turnID,
        identity: token.screenshotIdentity,
        callID: token.screenshotCallID,
        kind: .screenEvidence(outcome)))
    guard VoiceTurnCoordinator.shared.activeTurnID == token.turnID,
      VoiceTurnCoordinator.shared.activeTurn?.screenEvidenceProtocol == nil
    else { return false }

    presentScreenEvidenceAnswer(presentedAnswer)
    VoiceTurnCoordinator.shared.send(
      .toolFinishedScoped(
        turnID: token.turnID,
        identity: token.screenshotIdentity,
        callID: token.screenshotCallID))
    return true
  }

  func presentScreenEvidenceAnswer(_ answer: String) {
    guard !screenAnswerPresented else { return }
    screenAnswerPresented = true
    assistantText = answer.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !assistantText.isEmpty else { return }
    takeOverVoiceOutputForAuthoritativeLocalResult()
    guard let lease = acquireVoiceOutput(.deterministicScreenEvidence, reason: "screen_evidence_verified")
    else { return }
    responseGlowGate.markPlaybackActive(lease: lease)
    FloatingBarVoicePlaybackService.shared.speakOneShot(assistantText, lease: lease)
  }

  /// Async tool work must pass this second fence after every suspension point. The invocation is
  /// removed during terminal cleanup, so a resumed old task cannot affect a replacement turn.
  func isCurrentAuthorizedRealtimeInvocation(
    _ command: AuthorizedToolExecution,
    invocation: RealtimeAuthorizedToolInvocation
  ) -> Bool {
    guard let current = authorizedRealtimeInvocations[command.invocationID],
      current.turnID == invocation.turnID,
      current.callID == invocation.callID,
      current.effectIdentity == invocation.effectIdentity,
      current.sourceObjectID == invocation.sourceObjectID,
      current.turnEpoch == invocation.turnEpoch
    else { return false }
    return RealtimeAuthorizedToolOwnership.accepts(
      command: command,
      invocation: current,
      activeTurnID: VoiceTurnCoordinator.shared.activeTurnID,
      activeToolIdentity: VoiceTurnCoordinator.shared.activeTurn?.toolEffectIdentities[current.callID],
      activeSourceObjectID: session.map(ObjectIdentifier.init),
      currentTurnEpoch: realtimeToolTurnEpoch)
  }

  /// A screenshot tool request may arrive while JPEG encoding is still running. The pixels were
  /// already frozen at PTT-down; wait off-main for that one encoder rather than recapturing or
  /// treating an in-flight image as unavailable.
  func screenEvidenceForAuthorizedScreenshot() async -> RealtimeScreenEvidence? {
    guard let evidence = screenEvidence else { return nil }
    if evidence.isReadyForProviderDelivery { return evidence }
    guard !evidence.encodingFinished, let readiness = screenEvidenceReadiness else {
      return evidence
    }
    let ready = await withCheckedContinuation {
      (continuation: CheckedContinuation<RealtimeScreenEvidence?, Never>) in
      DispatchQueue.global(qos: .userInitiated).async {
        continuation.resume(returning: readiness.wait(timeout: 1.5))
      }
    }
    guard let ready,
      screenEvidence?.descriptor.evidenceID == ready.descriptor.evidenceID,
      VoiceTurnCoordinator.shared.activeTurnID == ready.descriptor.turnID
    else { return nil }
    return ready
  }
}
