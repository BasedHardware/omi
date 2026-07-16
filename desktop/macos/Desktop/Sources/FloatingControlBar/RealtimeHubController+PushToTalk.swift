import AppKit
import CoreGraphics
import Foundation
import OmiSupport

extension RealtimeHubController {
  // MARK: - PTT integration

  /// PTT-down: make sure the socket is warm and reset per-turn state. The typed
  /// result is the caller's fail-closed gate for buffered audio replay.
  @discardableResult
  func beginTurn(turnID requestedTurnID: VoiceTurnID? = nil) -> RealtimeInputPreparationResult {
    if discardMismatchedSessionIfNeeded() { ensureWarm() }
    turnPreparationTask?.cancel()
    turnPreparationTask = nil
    // Barge-in: was a reply from the previous turn still in flight when the user
    // started talking again?
    let providerResponseInFlight = reducerInterruptsPreviousTurn
    let voicePlaybackActive = FloatingBarVoicePlaybackService.shared.isSpeaking
    let bargeIn = providerResponseInFlight || reducerNativePlaybackActive || voicePlaybackActive
    let bargeInAction = RealtimeHubBargeInAction.decide(
      providerResponseInFlight: providerResponseInFlight,
      playbackActive: reducerNativePlaybackActive || voicePlaybackActive,
      strategy: session?.bargeInStrategy ?? .inSessionCancel)
    let supersedesPendingReplacement = replacementAudioBuffer != nil
    let requiresCompletedGeminiSessionBoundary =
      sessionProvider == .gemini && geminiSessionNeedsTurnBoundary
    let interruptedTurnIdempotencyKey = turnIdempotencyKey
    let interruptedTurnTask = bargeIn ? captureInterruptedTurnPayloadIfNeeded() : nil
    let turnID =
      requestedTurnID
      ?? VoiceTurnCoordinator.shared.activeTurnID
      ?? VoiceTurnCoordinator.shared.begin(intent: .hold)
    guard VoiceTurnCoordinator.shared.requireCurrentOwner(for: turnID) != nil else {
      log("RealtimeHub: refusing to begin provider input for a stale voice owner")
      return .rejected
    }
    admittedInputTurnID = nil
    if let pending = reconnectAudioBuffer, pending.turnID != turnID {
      reconnectAudioBuffer = nil
      log("RealtimeHub: discarded reconnect audio for a superseded rapid PTT turn")
    }
    let responseID = VoiceResponseID(UUID().uuidString)
    voiceResponseID = responseID
    realtimePlaybackEpoch += 1
    var deferredFreshSessionContextPrefetch = false
    turnTranscript = ""
    providerTranscriptFinalized = false
    lastInputTranscriptUpdateAt = nil
    assistantText = ""
    audioReceivedThisTurn = false
    lastExternalToolName = ""
    lastExternalToolErrorCode = ""
    turnIdempotencyKey = "voice:\(turnID.rawValue.uuidString.lowercased())"
    resetScreenGrounding(for: turnID)
    if let interruptedTurnTask, !supersedesPendingReplacement {
      if !providerResponseInFlight || session?.bargeInStrategy != .freshSession {
        enqueueTurnPersistence(idempotencyKey: interruptedTurnIdempotencyKey) { [weak self] in
          guard let interruptedTurn = await interruptedTurnTask.value else { return true }
          return await self?.persistTurnDirectlyToKernel(
            ownerID: interruptedTurn.ownerID,
            userText: interruptedTurn.userText,
            assistantText: interruptedTurn.assistantText,
            interrupted: true,
            idempotencyKey: interruptedTurn.idempotencyKey,
            acceptedSpawnOwnerID: interruptedTurn.acceptedSpawnOwnerID) ?? false
        }
      }
    }
    turnEpoch += 1
    let preparationEpoch = turnEpoch
    turnAudio16k.removeAll(keepingCapacity: true)
    earlyLIDTask = nil
    turnEarlyVerdictCode = nil
    fullLIDTask = nil
    testProviderTranscriptOverride = nil  // never leak a test override into a real turn
    clearRealtimeToolTracking()
    lastTurnAt = Date()
    if bargeIn {
      pcmPlayer?.stop()  // stop the prior reply locally only for a real barge-in.
    }
    FloatingBarVoicePlaybackService.shared.interruptCurrentResponse()
    responseGlowGate.clearImmediately()
    if supersedesPendingReplacement {
      if restartSessionForBargeIn(interruptedTurnTask: interruptedTurnTask) {
        deferredFreshSessionContextPrefetch = true
        log("RealtimeHub[gemini]: rotating pending replacement to the newest PTT turn")
      } else {
        session?.cancelActiveResponse()
      }
    } else if requiresCompletedGeminiSessionBoundary {
      if restartSessionForBargeIn(interruptedTurnTask: nil) {
        deferredFreshSessionContextPrefetch = true
        geminiSessionNeedsTurnBoundary = false
        log("RealtimeHub[gemini]: replacing completed-turn session before next PTT")
      } else {
        session?.cancelActiveResponse()
      }
    } else {
      switch bargeInAction {
      case .cancelInSession:
        // OpenAI exposes an explicit response.cancel path, so the warm socket and
        // conversation context survive while the next input buffer starts clean.
        log("RealtimeHub[\(providerTag)]: barge-in — interrupting in-flight reply (same session)")
        session?.cancelActiveResponse()
      case .replaceSession:
        // Gemini Live has no reliable in-session cancel for a streaming reply. Reusing
        // that socket can leave the next PTT turn queued behind the old generation, so
        // replace the connection and let the fresh session buffer this new turn while it opens.
        if restartSessionForBargeIn(interruptedTurnTask: interruptedTurnTask) {
          deferredFreshSessionContextPrefetch = true
          log("RealtimeHub: barge-in — replacing session for clean next turn")
        } else {
          session?.cancelActiveResponse()
        }
      case .stopPlaybackTail:
        log("RealtimeHub[\(providerTag)]: barge-in — stopping local playback tail")
      case .none:
        break
      }
    }
    if !deferredFreshSessionContextPrefetch {
      guard beginContextFreshInputPreparation(
        turnID: turnID,
        responseID: responseID,
        interrupting: providerResponseInFlight
      ) else {
        log("RealtimeHub: unable to establish a context-fresh PTT input boundary")
        return .rejected
      }
      let cachedRequirement = voiceSessionContext(for: currentOwnerScope)
      if cachedRequirement.isResolved {
        guard var pending = reconnectAudioBuffer,
          pending.turnID == turnID,
          pending.bindRequiredContextFreshnessIdentity(cachedRequirement.snapshotFreshnessIdentity)
        else {
          failContextFreshInputPreparation(
            turnID: turnID,
            message: "Voice context admission identity is unavailable")
          return .rejected
        }
        reconnectAudioBuffer = pending
        if isTransportReady,
          cachedRequirement.snapshotFreshnessIdentity == sessionVoiceContextFreshnessIdentity
        {
          // The common path: the launch/post-turn prewarm already installed the
          // exact immutable context. Open its input window synchronously; do
          // not fetch or replace a session from the physical press path.
          finishContextFreshInputOnCurrentSession()
        } else {
          pendingContextCacheReplacement = true
          requestSessionHandoff(
            reason: .voiceContextFreshness,
            preservingReconnectAudio: true)
        }
        return .accepted
      }

      // No cached requirement exists yet (cold start or a transient kernel
      // read). Capture immediately, then bind and hand off exactly once when
      // the canonical snapshot arrives. A failed read takes the typed fallback
      // route rather than terminalizing a user's already-captured turn.
      turnPreparationTask = Task { @MainActor [weak self] in
        guard let self else { return }
        guard !Task.isCancelled else { return }
        guard await self.refreshVoiceContextSnapshot() else {
          self.failContextFreshInputPreparation(
            turnID: turnID,
            message: "Voice context is temporarily unavailable")
          return
        }
        guard !Task.isCancelled,
          self.contextFreshInputPreparationIsCurrent(
            turnID: turnID,
            preparationEpoch: preparationEpoch)
        else { return }
        let current = self.voiceSessionContext(for: self.currentOwnerScope)
        guard var pending = self.reconnectAudioBuffer,
          pending.turnID == turnID,
          pending.bindRequiredContextFreshnessIdentity(current.snapshotFreshnessIdentity)
        else {
          self.failContextFreshInputPreparation(
            turnID: turnID,
            message: "Voice context admission identity is unavailable")
          return
        }
        self.reconnectAudioBuffer = pending
        self.pendingContextCacheReplacement = true
        guard !Task.isCancelled,
          self.contextFreshInputPreparationIsCurrent(
            turnID: turnID,
            preparationEpoch: preparationEpoch)
        else { return }
        self.requestSessionHandoff(
          reason: .voiceContextFreshness,
          preservingReconnectAudio: true)
      }
    }
    return .accepted
  }

  func captureInterruptedTurnPayloadIfNeeded() -> Task<InterruptedTurnPayload?, Never>? {
    if turnPersistenceLedger.pendingContinuityKeys.contains(turnIdempotencyKey)
      || turnPersistenceLedger.receipt(for: turnIdempotencyKey)?.accepted == true
      || !prefetchedVoiceContextTurnIDs.isDisjoint(
        with: KernelTurnProjection.stableTurnIDs(continuityKey: turnIdempotencyKey)
      )
    {
      return nil
    }
    let providerText = turnTranscript
    let localTask = fullLIDTask
    guard !providerText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || localTask != nil
    else { return nil }
    let preferredLanguages = AssistantSettings.shared.voiceBaseLanguages
    let partialAssistantText = assistantText
    let idempotencyKey = turnIdempotencyKey
    let acceptedSpawnOwnerID = acceptedSpawnJournalReceiptByContinuityKey[idempotencyKey]?.ownerID
    guard let ownerID = VoiceTurnCoordinator.shared.activeTurn?.ownerID else { return nil }
    return Task {
      let resolution = await Self.resolveTranscript(
        providerText: providerText,
        preferredLanguages: preferredLanguages,
        localTask: localTask)
      guard !resolution.userText.isEmpty else { return nil }
      return InterruptedTurnPayload(
        ownerID: ownerID,
        userText: resolution.userText,
        assistantText: InterruptedTurnPayload.visibleAssistantText(
          partialAssistantText: partialAssistantText),
        idempotencyKey: idempotencyKey,
        acceptedSpawnOwnerID: acceptedSpawnOwnerID)
    }
  }

  /// Mic chunk (16 kHz PCM16 mono) → resample to the provider's rate → session.
  func feedAudio(_ pcm16k: Data, turnID requestedTurnID: VoiceTurnID? = nil) {
    // A first PTT can be buffering while its context-fresh session reconnects. Reconciliation
    // tears a session down and clears that buffer, so it is safe only when no turn owns audio.
    if VoiceTurnCoordinator.shared.activeTurnID == nil,
      discardMismatchedSessionIfNeeded()
    {
      ensureWarm()
    }
    if let requestedTurnID {
      guard requestedTurnID == VoiceTurnCoordinator.shared.activeTurnID,
        VoiceAudioIngressOwnership.accepts(
          turnID: requestedTurnID,
          activeTurnID: VoiceTurnCoordinator.shared.activeTurnID,
          capturingInput: reducerCapturingInput)
      else {
        log("RealtimeHub: dropping audio for closed/stale turn \(requestedTurnID)")
        return
      }
    }
    guard let turnID = requestedTurnID ?? VoiceTurnCoordinator.shared.activeTurnID,
      VoiceTurnCoordinator.shared.requireCurrentOwner(for: turnID) != nil
    else {
      log("RealtimeHub: refusing audio ingress for a stale voice owner")
      return
    }
    bufferTurnAudio(pcm16k)
    if replacementAudioBuffer != nil {
      if replacementAudioBuffer?.appendAudio(pcm16k) == false {
        log(
          "RealtimeHub: replacement audio buffer reached "
            + "\(RealtimeReplacementAudioBuffer.maxBufferedAudioBytes) bytes; truncating turn audio"
        )
      }
      return
    }
    let activeTurnID = VoiceTurnCoordinator.shared.activeTurnID
    if var pending = reconnectAudioBuffer {
      if pending.turnID != activeTurnID {
        reconnectAudioBuffer = nil
        log("RealtimeHub: discarded reconnect audio for a superseded PTT turn")
      } else {
        if pending.appendAudio(pcm16k) == false {
          log(
            "RealtimeHub: reconnect audio buffer reached "
              + "\(RealtimeReconnectAudioBuffer.maxBufferedAudioBytes) bytes; truncating turn audio"
          )
        }
        reconnectAudioBuffer = pending
        return
      }
    }
    guard let s = session else {
      guard let activeTurnID, let responseID = voiceResponseID else {
        log("RealtimeHub[\(providerTag)]: dropping mic audio without a PTT turn identity")
        return
      }
      guard let identity = VoiceTurnCoordinator.shared.reserveEffectIdentity() else { return }
      var pending = RealtimeReconnectAudioBuffer(
        turnID: activeTurnID,
        responseID: responseID,
        identity: identity,
        interrupting: reducerInterruptsPreviousTurn)
      guard pending.bindRequiredContextFreshnessIdentity(sessionVoiceContextFreshnessIdentity) else {
        log("RealtimeHub: refusing audio buffer without an admitted session context identity")
        return
      }
      _ = pending.appendAudio(pcm16k)
      reconnectAudioBuffer = pending
      VoiceTurnCoordinator.shared.send(
        .providerReconnectStarted(
          turnID: activeTurnID,
          identity: identity,
          previousSessionID: voiceSessionID))
      log("RealtimeHub[\(providerTag)]: buffering mic audio until the reconnecting session is ready")
      ensureWarm()
      return
    }
    sendAudio(pcm16k, to: s)
  }

  /// Keep a local copy of the turn's audio and kick the early language-ID pass once
  /// ~1.5 s has accumulated — it runs WHILE the user is still holding the key, so the
  /// verdict is ready at PTT-up and hinting the provider costs zero perceived latency.
  /// Skipped for single-language users (no identification needed to pick the hint).
  func bufferTurnAudio(_ pcm16k: Data) {
    guard turnAudio16k.count < Self.maxTurnAudioBytes else { return }
    turnAudio16k.append(pcm16k)
    guard earlyLIDTask == nil, turnAudio16k.count >= Self.earlyLIDBytes else { return }
    let candidates = AssistantSettings.shared.voiceBaseLanguages
    guard candidates.count > 1 else { return }
    let audio = Data(turnAudio16k.prefix(Self.earlyLIDBytes * 2))
    let epoch = turnEpoch
    let task = Task.detached(priority: .userInitiated) {
      await PTTLanguageIdentifier.shared.identify(pcm16k: audio, candidates: candidates)
    }
    earlyLIDTask = task
    // Land the verdict back on the turn as soon as it's ready (normally well before
    // PTT-up). Commit reads it synchronously — no await window, no droppable turn.
    Task { @MainActor [weak self] in
      let verdict = await task.value
      guard let self, self.turnEpoch == epoch else { return }
      self.turnEarlyVerdictCode = verdict.languageCode
    }
  }

  func sendAudio(_ pcm16k: Data, to s: RealtimeHubSession) {
    let rate = s.requiredInputSampleRate
    let pcm =
      rate == 16000 ? pcm16k : PushToTalkManager.resamplePCM16(pcm16k, from: 16000, to: rate)
    s.sendAudio(pcm)
  }

  /// PTT-up: end the turn; the model now responds (and may call tools).
  func commitTurn() -> RealtimeHubCommitResult {
    // Preserve a context-fresh reconnect buffer through PTT-up; its deferred commit is drained
    // by finishContextFreshInputOnCurrentSession once the replacement socket is ready.
    if VoiceTurnCoordinator.shared.activeTurnID == nil,
      discardMismatchedSessionIfNeeded()
    {
      ensureWarm()
    }
    guard let turnID = VoiceTurnCoordinator.shared.activeTurnID,
      VoiceTurnCoordinator.shared.requireCurrentOwner(for: turnID) != nil
    else {
      log("RealtimeHub: rejected duplicate/stale physical commit before provider side effects")
      return .rejectedNoSession
    }
    guard VoiceTurnCoordinator.shared.canCommitHubTurn(turnID) else {
      if RealtimeHubCommitOwnershipPolicy.isAlreadyOwned(
        turn: VoiceTurnCoordinator.shared.activeTurn,
        requestedTurnID: turnID)
      {
        log("RealtimeHub: physical commit is already owned by the pending realtime turn")
        return .alreadyOwned
      }
      log("RealtimeHub: rejected duplicate/stale physical commit before provider side effects")
      return .rejectedNoSession
    }

    if let pending = replacementAudioBuffer {
      VoiceTurnCoordinator.shared.send(.hubCommitDeferredForReplacement(turnID: turnID))
      prepareAcceptedCommit()
      log(
        "RealtimeHub[\(providerTag)]: barge-in replacement not ready at commit — "
          + "deferring commit (bufferedChunks=\(pending.audioBuffer.count))"
      )
      return .deferredForReplacement
    }
    if let pending = reconnectAudioBuffer {
      VoiceTurnCoordinator.shared.send(.hubCommitDeferred(turnID: turnID))
      prepareAcceptedCommit(preservingContextPreparation: true)
      log(
        "RealtimeHub[\(providerTag)]: session reconnect not ready at commit — "
          + "deferring commit (bufferedChunks=\(pending.audioBuffer.count))"
      )
      ensureWarm()
      return .deferredForReconnect
    }
    guard session != nil, voiceSessionID != nil else {
      turnPreparationTask?.cancel()
      turnPreparationTask = nil
      exitVoiceUI(clearResponseGlow: true)
      return .rejectedNoSession
    }

    // The coordinator deliberately queues nested events while it is reducing
    // `.finalizeCapturedInput`.  Do not inspect the turn immediately after
    // sending this claim: that sees the prior `.finalizing` state and falsely
    // rejects a valid physical PTT release.  The reducer emits the provider
    // effect after it has applied this claim, and `commitClaimedHubInput` below
    // is the sole driver for the actual provider commit.
    VoiceTurnCoordinator.shared.send(.hubCommitClaimed(turnID: turnID))
    return .accepted
  }

  /// Performs the provider side of a physical hub commit after the reducer has
  /// applied its `hubCommitClaimed` state transition. This runs from the
  /// coordinator effect queue, so it cannot observe the stale state that
  /// existed before a nested commit claim was reduced.
  func commitClaimedHubInput(turnID: VoiceTurnID) {
    guard let activeTurn = VoiceTurnCoordinator.shared.activeTurn,
      activeTurn.id == turnID,
      activeTurn.phase == .awaitingResponse,
      activeTurn.hubCommitPending,
      VoiceTurnCoordinator.shared.requireCurrentOwner(for: turnID) != nil
    else {
      log("RealtimeHub: dropped stale claimed physical commit")
      return
    }

    guard let s = session, let voiceSessionID else {
      log("RealtimeHub: claimed physical commit lost its session before provider side effects")
      turnPreparationTask?.cancel()
      turnPreparationTask = nil
      VoiceTurnCoordinator.shared.send(.finish(turnID: turnID, reason: .providerFailed))
      exitVoiceUI(clearResponseGlow: true)
      return
    }

    let candidates = AssistantSettings.shared.voiceBaseLanguages
    prepareAcceptedCommit()
    // Hint the provider's transcription with the identified language, entirely
    // synchronously: one configured language → hint it directly; several → whatever the
    // mid-hold verdict produced by now (nil clears any stale hint from a prior turn and
    // leaves the provider on auto-detect — same as today's behavior).
    if s.supportsInputTranscriptionLanguage, !candidates.isEmpty {
      s.setInputTranscriptionLanguage(candidates.count == 1 ? candidates[0] : turnEarlyVerdictCode)
    }
    if let voiceResponseID {
      // PTT-up can beat asynchronous context preparation. Queue begin before
      // commit on the session transport so Gemini always has activityStart and
      // OpenAI always has an immutable event identity.
      s.beginInputTurn(
        turnID: turnID,
        responseID: voiceResponseID,
        interrupting: reducerInterruptsPreviousTurn)
    }
    s.commitInputTurn()
    VoiceTurnCoordinator.shared.send(
      .hubCommitAccepted(
        turnID: turnID,
        sessionID: voiceSessionID,
        responseID: voiceResponseID))
  }

  /// Prepare local state shared by immediate and deferred hub commits. Screen
  /// pixels are captured only by the kernel-authorized screenshot tool; voice
  /// commits themselves never attach an ambient frame.
  func prepareAcceptedCommit(preservingContextPreparation: Bool = false) {
    let candidates = AssistantSettings.shared.voiceBaseLanguages
    if !preservingContextPreparation {
      turnPreparationTask?.cancel()
      turnPreparationTask = nil
    }
    // Runs during the seconds the model spends answering; consumed at turn-done.
    if !turnAudio16k.isEmpty {
      let audio = turnAudio16k
      fullLIDTask = Task.detached(priority: .userInitiated) {
        await PTTLanguageIdentifier.shared.identify(pcm16k: audio, candidates: candidates)
      }
    }
  }

  /// Await a task's value with a REAL deadline on return time. A plain withTaskGroup
  /// race is not enough: the group awaits its remaining children at scope exit and
  /// `Task<T, Never>.value` is not cancellation-interruptible, so the "timeout" would
  /// still block for the task's full duration (e.g. a cold model load). Unstructured
  /// racers + a resume-once gate make the deadline bound the return, not just the value.
  static func value<T: Sendable>(of task: Task<T, Never>, timeoutMs: UInt64) async -> T? {
    let once = RealtimeHubResumeOnceGate()
    return await withCheckedContinuation { (cont: CheckedContinuation<T?, Never>) in
      Task {
        let v = await task.value
        if once.first() { cont.resume(returning: v) }
      }
      Task {
        try? await Task.sleep(nanoseconds: timeoutMs * 1_000_000)
        if once.first() { cont.resume(returning: nil) }
      }
    }
  }

  static func resolveTranscript(
    providerText: String,
    preferredLanguages: [String],
    localTask: Task<PTTLanguageIdentifier.Verdict, Never>?
  ) async -> RealtimeHubTranscriptResolution {
    let trimmedProvider = providerText.trimmingCharacters(in: .whitespacesAndNewlines)
    let providerLanguage =
      trimmedProvider.isEmpty
      ? nil : PTTLanguageIdentifier.dominantLanguage(of: trimmedProvider, hints: [])
    let needsLocal =
      trimmedProvider.isEmpty
      || (!preferredLanguages.isEmpty
        && (providerLanguage.map { !preferredLanguages.contains($0) } ?? false))
    let verdict =
      needsLocal && localTask != nil
      ? await value(of: localTask!, timeoutMs: 20_000) : nil
    return RealtimeHubTranscriptPolicy.resolve(
      providerText: trimmedProvider,
      preferredLanguages: preferredLanguages,
      localTranscript: verdict?.transcript,
      localLanguage: verdict?.languageCode)
  }

  /// Abandon the turn without committing (silent tap / cancel). Must leave NO open
  /// turn behind, or the model answers the non-speech later.
  @discardableResult
  func cancelTurn(turnID requestedTurnID: VoiceTurnID) -> Bool {
    let activeOwner = VoiceTurnCoordinator.shared.activeTurnID == requestedTurnID
    let terminalOwner = VoiceTurnCoordinator.shared.activeTurnID == nil
      && VoiceTurnCoordinator.shared.model.lastTerminal?.turnID == requestedTurnID
    guard activeOwner || terminalOwner else {
      log("RealtimeHub: ignored stale cancelTurn id=\(requestedTurnID)")
      return false
    }
    let canceledPreparationTask = turnPreparationTask
    turnPreparationTask?.cancel()
    turnPreparationTask = nil
    reconnectAudioBuffer = nil
    if admittedInputTurnID == requestedTurnID { admittedInputTurnID = nil }
    realtimePlaybackEpoch += 1
    pcmPlayer?.stop()
    turnTranscript = ""
    providerTranscriptFinalized = false
    lastInputTranscriptUpdateAt = nil
    assistantText = ""
    clearRealtimeToolTracking()
    let interruptedContinuityTask = bargeInContinuityTask
    bargeInContinuityTask = nil
    clearBargeInReplacementState()
    // Abandon the open turn WITHOUT tearing down the socket: close the speech window
    // and leave the reply gated off so the model never answers the silence. Keeps the
    // warm session (and its context) so the next real turn is instant and in-context.
    let terminalReason = VoiceTurnCoordinator.shared.model.lastTerminal
      .flatMap { $0.turnID == requestedTurnID ? $0.reason : nil }
    let replaceAbandonedSession = terminalReason != .success
    if terminalReason != .success {
      session?.abandonInputTurn()
    }
    if replaceAbandonedSession {
      // A canceled provider input may still emit commit/activity acknowledgements.
      // Give every abandoned turn a fresh socket boundary, but never make the
      // next physical press wait behind the canceled turn's persistence fence.
      // Its captured audio joins the same typed handoff if it races this work.
      teardownSession()
      pendingSessionRefreshReason = RealtimeHubSessionHandoffReason.persistedVoiceContext.rawValue
      ensureWarm()
      canceledTurnRewarmTask?.cancel()
      canceledTurnRewarmTask = Task { @MainActor [weak self] in
        if let canceledPreparationTask {
          await canceledPreparationTask.value
        }
        if let interruptedContinuityTask {
          await interruptedContinuityTask.value
        }
        guard let self, !Task.isCancelled else { return }
        let refreshed = await self.refreshVoiceContextAfterPersistenceFence(
          reason: RealtimeHubSessionHandoffReason.persistedVoiceContext.rawValue)
        guard !Task.isCancelled else { return }
        guard refreshed else {
          self.canceledTurnRewarmTask = nil
          return
        }
        self.canceledTurnRewarmTask = nil
        if self.pendingSessionRefreshReason == RealtimeHubSessionHandoffReason.persistedVoiceContext.rawValue {
          self.pendingSessionRefreshReason = nil
        }
        log("RealtimeHub: applying canceled-turn voice context refresh after continuity persistence")
        self.requestSessionHandoff(
          reason: .cancelledTurnContinuity,
          preservingReconnectAudio: self.reconnectAudioBuffer != nil)
      }
    }
    exitVoiceUI(clearResponseGlow: true)
    if !replaceAbandonedSession {
      applyPendingSessionRefreshIfIdle()
    }
    return true
}
}
