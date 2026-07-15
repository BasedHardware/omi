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
      lastScreenEvidenceProtocolCompletion = .notRun
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
    screenFailurePresented = false
  }

  func clearScreenGrounding(stage: String? = nil) {
    if let evidence = screenEvidence, let stage {
      logScreenEvidence(stage: stage, evidence: evidence.descriptor)
    }
    screenEvidence = nil
    screenEvidenceReadiness = nil
    screenGroundingState = .inactive
    authorizedRealtimeScreenshotImages.removeAll()
    screenFailurePresented = false
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
    // Capture freshness is enforced when the exact JPEG enters the provider transport. Once it
    // is enqueued while fresh, the report gets this separate bounded wait rather than inheriting
    // a nearly-expired capture timestamp and failing before the model can inspect the image.
    let expiresAfter = screenEvidence == nil ? 0 : RealtimeScreenEvidenceProtocolPolicy.maximumReportWait
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
    let completion = completeScreenEvidenceFailure(
      token,
      failure: RealtimeScreenGroundingPolicy.failureText)
    guard completion != .completed else { return }

    // A screenshot tool is intentionally held pending until this protocol reaches a local
    // terminal state. Never discard a failed completion: otherwise the reducer keeps that tool
    // pending, the provider has already finished, and the turn can only end in tool_timeout.
    if VoiceTurnCoordinator.shared.activeTurnID == token.turnID,
      VoiceTurnCoordinator.shared.activeTurn?.pendingToolCallIDs.contains(token.screenshotCallID) == true
    {
      log("RealtimeHub: ptt_screen_evidence completion_failed=\(completion.rawValue) action=terminal_fail_closed")
      VoiceTurnCoordinator.shared.send(.finish(turnID: token.turnID, reason: .providerFailed))
    }
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

  /// The bounded post-transport report deadline is distinct from the five-second capture
  /// freshness gate. Its reducer-issued token makes a delayed callback unable to affect a
  /// replacement turn.
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
    rejectScreenEvidence(evidence, reason: "report_deadline_expired")
  }

  /// Closes a failed screen-evidence protocol as the one deterministic local
  /// result. Successful screen reports deliberately use a separate reducer
  /// event so the provider continues to answer the original user request.
  @discardableResult
  func completeScreenEvidenceFailure(
    _ token: VoiceScreenEvidenceProtocolToken,
    failure: String
  ) -> RealtimeScreenEvidenceProtocolCompletion {
    guard VoiceTurnCoordinator.shared.activeTurnID == token.turnID else {
      return recordScreenEvidenceProtocolCompletion(.turnNotActive)
    }
    guard VoiceTurnCoordinator.shared.activeTurn?.screenEvidenceProtocol == token else {
      return recordScreenEvidenceProtocolCompletion(.protocolNotActive)
    }
    guard let ownerID = VoiceTurnCoordinator.shared.requireCurrentOwner(for: token.turnID) else {
      return recordScreenEvidenceProtocolCompletion(.ownerNotCurrent)
    }
    let presentedFailure = failure.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !presentedFailure.isEmpty else {
      return recordScreenEvidenceProtocolCompletion(.emptyAnswer)
    }

    assistantText = presentedFailure
    _ = enqueueAuthoritativeScreenEvidenceFailurePersistence(
      ownerID: ownerID,
      assistantText: presentedFailure)
    VoiceTurnCoordinator.shared.send(
      .authoritativeLocalResultAcceptedScoped(
        turnID: token.turnID,
        identity: token.screenshotIdentity,
        callID: token.screenshotCallID,
        kind: .screenEvidenceFailure))
    guard VoiceTurnCoordinator.shared.activeTurnID == token.turnID,
      VoiceTurnCoordinator.shared.activeTurn?.screenEvidenceProtocol == nil
    else {
      return recordScreenEvidenceProtocolCompletion(.reducerDidNotResolve)
    }

    presentScreenEvidenceFailure(presentedFailure)
    VoiceTurnCoordinator.shared.send(
      .toolFinishedScoped(
        turnID: token.turnID,
        identity: token.screenshotIdentity,
        callID: token.screenshotCallID))
    return recordScreenEvidenceProtocolCompletion(.completed)
  }

  /// A verified observation proves that the model received the one fresh image
  /// for this exact turn. It is deliberately not persisted, displayed, or
  /// spoken: the normal provider continuation supplies the user-facing answer.
  @discardableResult
  func acceptScreenEvidenceReport(
    _ token: VoiceScreenEvidenceProtocolToken,
    reportCallID: VoiceToolCallID,
    reportIdentity: VoiceEffectIdentity
  ) -> RealtimeScreenEvidenceProtocolCompletion {
    guard VoiceTurnCoordinator.shared.activeTurnID == token.turnID else {
      return recordScreenEvidenceProtocolCompletion(.turnNotActive)
    }
    guard VoiceTurnCoordinator.shared.activeTurn?.screenEvidenceProtocol == token else {
      return recordScreenEvidenceProtocolCompletion(.protocolNotActive)
    }
    VoiceTurnCoordinator.shared.send(
      .screenEvidenceReportVerifiedScoped(
        turnID: token.turnID,
        screenshotIdentity: token.screenshotIdentity,
        screenshotCallID: token.screenshotCallID,
        reportIdentity: reportIdentity,
        reportCallID: reportCallID))
    guard VoiceTurnCoordinator.shared.activeTurnID == token.turnID,
      VoiceTurnCoordinator.shared.activeTurn?.screenEvidenceProtocol == nil
    else {
      return recordScreenEvidenceProtocolCompletion(.reducerDidNotResolve)
    }
    VoiceTurnCoordinator.shared.send(
      .toolFinishedScoped(
        turnID: token.turnID,
        identity: token.screenshotIdentity,
        callID: token.screenshotCallID))
    return recordScreenEvidenceProtocolCompletion(.completed)
  }

  @discardableResult
  private func recordScreenEvidenceProtocolCompletion(
    _ completion: RealtimeScreenEvidenceProtocolCompletion
  ) -> RealtimeScreenEvidenceProtocolCompletion {
    lastScreenEvidenceProtocolCompletion = completion
    log("RealtimeHub: ptt_screen_evidence protocol_completion=\(completion.rawValue)")
    return completion
  }

  /// Non-production bridge diagnostics deliberately expose state labels and outcome classes
  /// only. They are enough to pinpoint a stuck protocol without logging pixels, app identity,
  /// evidence IDs, transcripts, or model text.
  func automationScreenEvidenceDiagnostics() -> [String: String] {
    [
      "screen_evidence_state": screenGroundingState.diagnosticsLabel,
      "screen_evidence_protocol_active": screenGroundingState.protocolToken == nil ? "false" : "true",
      "screen_evidence_last_completion": lastScreenEvidenceProtocolCompletion.rawValue,
    ]
  }

  /// Typed, bounded PTT state for both the read-only snapshot action and a completed headless
  /// turn. Keeping the fields here prevents the probe from inferring completion from UI copy or
  /// raw logs, and makes a verified screen grounding protocol distinguishable from a generic
  /// chat turn that happens not to have reached provider continuation yet.
  func automationPTTDiagnostics() -> [String: String] {
    let coordinator = VoiceTurnCoordinator.shared
    let turn = coordinator.model.turn
    let terminalReason = turn?.terminalReason?.rawValue ?? ""
    let phase = turn.map { VoiceTurnCoordinator.phaseLabel($0.phase) } ?? "idle"
    let route = turn.map { VoiceTurnCoordinator.routeLabel($0.route) } ?? "none"
    var snapshot = [
      "phase": phase,
      "route": route,
      "terminal_reason": terminalReason,
      "stale_event_count": "\(coordinator.model.staleEventCount)",
      "invalid_transition_count": "\(coordinator.model.invalidTransitionCount)",
      "pending_tool_count": "\(turn?.pendingToolCallIDs.count ?? 0)",
      "post_tool_continuation_required": turn?.postToolContinuationRequired == true ? "true" : "false",
      "provider_finished": turn?.providerFinished == true ? "true" : "false",
    ]
    for (key, value) in automationScreenEvidenceDiagnostics() {
      snapshot[key] = value
    }
    for (key, value) in automationPTTInputDiagnostics() {
      snapshot[key] = value
    }
    return snapshot
  }

  func presentScreenEvidenceFailure(_ failure: String) {
    guard !screenFailurePresented else { return }
    screenFailurePresented = true
    assistantText = failure.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !assistantText.isEmpty else { return }
    takeOverVoiceOutputForAuthoritativeLocalResult()
    guard let lease = acquireVoiceOutput(.deterministicScreenEvidence, reason: "screen_evidence_failed")
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
