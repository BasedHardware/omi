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
      screenGroundingState = .awaitingTranscript(evidence.descriptor)
      logScreenEvidence(stage: "captured", evidence: evidence.descriptor)
      if !evidence.encodingFinished {
        startScreenEvidenceEncoding(evidence)
      }
    } else if case .awaitingTranscript = screenGroundingState {
      screenGroundingState = .awaitingTranscript(evidence.descriptor)
    }
    if evidence.encodingFinished {
      logScreenEvidence(
        stage: evidence.isReadyForProviderDelivery ? "encoded" : "encode_failed",
        evidence: evidence.descriptor)
      if screenTranscriptFinalized {
        resolveScreenGroundingAfterFinalTranscript()
      }
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
    RealtimeHubTools.screenshotToolResult(
      evidenceID: attachment?.descriptor.evidenceID,
      frontmostApp: attachment?.descriptor.frontmostApp,
      capturedBytes: attachment?.jpeg.count)
  }

  func resetScreenGrounding(for turnID: VoiceTurnID) {
    if screenEvidence?.descriptor.turnID != turnID {
      screenEvidence = nil
      screenEvidenceReadiness = nil
    }
    screenGroundingState = .awaitingTranscript(screenEvidence?.descriptor)
    deferredProviderAudio.removeAll(keepingCapacity: true)
    deferredProviderText.removeAll(keepingCapacity: true)
    deliveredScreenEvidenceID = nil
    pendingScreenObservation = nil
    screenTranscriptFinalized = false
    screenAnswerPresented = false
  }

  func clearScreenGrounding(stage: String? = nil) {
    if let evidence = screenEvidence, let stage {
      logScreenEvidence(stage: stage, evidence: evidence.descriptor)
    }
    screenEvidence = nil
    screenEvidenceReadiness = nil
    screenGroundingState = .inactive
    deferredProviderAudio.removeAll(keepingCapacity: false)
    deferredProviderText.removeAll(keepingCapacity: false)
    authorizedRealtimeScreenshotImages.removeAll()
    deliveredScreenEvidenceID = nil
    pendingScreenObservation = nil
    screenTranscriptFinalized = false
    screenAnswerPresented = false
  }

  func markScreenEvidenceDelivered(_ attachment: RealtimeScreenEvidenceAttachment) {
    guard screenEvidence?.descriptor.turnID == attachment.descriptor.turnID,
      screenEvidence?.descriptor.evidenceID == attachment.descriptor.evidenceID
    else { return }
    deliveredScreenEvidenceID = attachment.descriptor.evidenceID
    logScreenEvidence(stage: "delivered", evidence: attachment.descriptor)
    resolvePendingScreenObservationIfReady()
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
    let message = "RealtimeHub: ptt_screen_evidence stage=\(stage) evidence=\(evidence.opaqueID) "
      + "turn=\(turn) target=\(evidence.target.rawValue) capture_age=\(ageBucket) bytes=\(bytesBucket) "
      + "app=\(evidence.opaqueAppID ?? "") has_window=\(evidence.windowID != nil) "
      + "has_display=\(evidence.displayID != nil) image=\(image) "
      + "call=\(callHash.prefix(12)) image_tokens=\(tokens)"
    log(message)
  }

  func rejectScreenEvidence(
    _ evidence: RealtimeScreenEvidenceDescriptor?,
    reason: String
  ) {
    screenGroundingState = .rejected(evidence)
    deferredProviderAudio.removeAll(keepingCapacity: false)
    deferredProviderText.removeAll(keepingCapacity: false)
    if let evidence {
      logScreenEvidence(stage: "report_rejected", evidence: evidence)
    }
    DesktopDiagnosticsManager.shared.recordFallback(
      area: "realtime_hub",
      from: "screen_evidence",
      to: "none",
      reason: "capability_mismatch",
      outcome: .exhausted,
      extra: ["screen_evidence_reason": reason, "user_visible": true])
    presentScreenEvidenceAnswer(RealtimeScreenGroundingPolicy.failureText)
  }

  func presentScreenEvidenceAnswer(_ answer: String) {
    guard !screenAnswerPresented else { return }
    screenAnswerPresented = true
    assistantText = answer.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !assistantText.isEmpty,
      let lease = acquireVoiceOutput(.deterministicScreenEvidence, reason: "screen_evidence_verified")
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
