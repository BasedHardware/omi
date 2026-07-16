import AppKit
import CoreGraphics
import Foundation
import OmiSupport
import VoiceTurnDomain

extension RealtimeHubController {
  // MARK: - Warm session lifecycle (kept open between turns)

  /// Open the WS now if it isn't already (no-op if already warm). BYOK → connect
  /// client-direct with the user's key. Otherwise, if signed in → mint a server-side
  /// ephemeral token and connect with it.
  func ensureWarm() {
    #if DEBUG
      // The local-profile action owns an already-installed hermetic transport.
      // Re-entering normal warm-up here would replace it and mint a real provider
      // token while the offline gauntlet is exercising the production reducer.
      if isAuthorizedLocalProfileTransport() { return }
    #endif
    guard !RuntimeOwnerIdentity.effectiveOwnerTransitionInProgress else {
      log("RealtimeHub: warm start denied during effective-owner transition")
      return
    }
    guard
      RealtimeHubLifecyclePolicy.canStartGeneralWarmSession(
        replacementPending: replacementAudioBuffer != nil)
    else {
      log("RealtimeHub: general warm skipped while barge-in replacement owns session startup")
      return
    }
    let provider = effectiveProvider
    let ownerScope = currentOwnerScope
    if session != nil, sessionProvider == provider,
      RealtimeHubOwnerFence.canReuseWarmSession(
        sessionOwner: sessionOwnerScope,
        currentOwnerID: RuntimeOwnerIdentity.currentOwnerId())
    {
      return
    }
    if session != nil, sessionOwnerScope != ownerScope {
      log("RealtimeHub: rebuilding warm session after authenticated owner changed")
      discardSessionAfterOwnerChange()
    }
    if session != nil { teardownSession() }

    if let key = APIKeyService.byokKey(provider.byokProvider) {
      let fingerprint = APIKeyService.byokFingerprint(key)
      guard
        CredentialHealthManager.shared.canUseBYOK(
          provider: provider.byokProvider, fingerprint: fingerprint)
      else {
        log("RealtimeHub: skipping known-bad \(provider.displayName) BYOK key fingerprint")
        if failoverToAlternateProvider(reason: "auth") {
          return
        } else if AuthService.shared.isSignedIn {
          guard case .authenticated = ownerScope else { return }
          mintAndConnect(provider: provider, ownerScope: ownerScope)
        } else {
          CredentialHealthManager.shared.recordProviderFailure(
            .providerAuthFailed(provider: provider, mode: .byok),
            provider: provider,
            authMode: .byok,
            fingerprint: fingerprint,
            context: "realtime_byok_blocked")
        }
        return
      }
      startSession(provider: provider, auth: .byokKey(key), ownerScope: ownerScope)
    } else if AuthService.shared.isSignedIn {
      guard case .authenticated = ownerScope else {
        log("RealtimeHub: signed-in state has no stable owner identity — hub unavailable")
        return
      }
      mintAndConnect(provider: provider, ownerScope: ownerScope)
    } else {
      log("RealtimeHub: no BYOK key and not signed in — hub unavailable (cascade).")
    }
  }

  func completeExternalRunAuthority(
    turnID: VoiceTurnID,
    reason: VoiceTurnTerminalReason
  ) {
    guard let state = externalRunAuthorityState, state.turnID == turnID else { return }
    externalRunAuthorityState = nil
    authorizedRealtimeInvocations = authorizedRealtimeInvocations.filter {
      $0.value.turnID != turnID
    }
    completedAuthorizedRealtimeInvocationIDs.removeAll()
    let terminalStatus = RealtimeExternalRunTerminalPolicy.status(for: reason)
    let errorCode = terminalStatus == .failed ? reason.rawValue : nil
    let terminalizationID = UUID()
    let task = Task { @MainActor [weak self] in
      let resolution = await awaitWithTimeout(
        Self.ownerTransitionExternalRunBindingTimeout
      ) { () -> ExternalRunBindingResolution in
        do {
          return .bound(try await state.task.value)
        } catch {
          let code =
            (error as? ExternalSurfaceAuthorityError)?.code
            ?? "external_surface_begin_failed"
          return .failed(code)
        }
      }
      switch resolution {
      case .some(.bound(let binding)):
        guard let self else {
          return ExternalRunTerminalizationResult(
            binding: binding,
            cleanupCapability: nil,
            closed: false,
            failureCode: "realtime_controller_released")
        }
        return await self.terminalizeExternalRun(
          binding: binding,
          terminalStatus: terminalStatus,
          errorCode: errorCode)
      case .some(.failed(let code)):
        log("RealtimeHub: external run completion failed code=\(code)")
        return ExternalRunTerminalizationResult(
          binding: nil,
          cleanupCapability: nil,
          closed: false,
          failureCode: code)
      case .none:
        state.task.cancel()
        log("RealtimeHub: external run begin drain timed out at owner boundary")
        return ExternalRunTerminalizationResult(
          binding: nil,
          cleanupCapability: nil,
          closed: false,
          failureCode: "external_surface_begin_drain_timeout")
      }
    }
    trackExternalRunTerminalization(
      id: terminalizationID,
      ownerID: state.ownerID,
      terminalStatus: terminalStatus,
      errorCode: errorCode,
      task: task)
  }

  func terminalizeExternalRun(
    binding: ExternalSurfaceRunBinding,
    terminalStatus: ExternalSurfaceRunTerminalStatus,
    errorCode: String?,
    cleanupCapability: RuntimeOwnerTransitionCleanupCapability? = nil
  ) async -> ExternalRunTerminalizationResult {
    let effectiveCleanupCapability =
      cleanupCapability
      ?? RuntimeOwnerIdentity.transitionCleanupCapability(
        forPreviousOwnerID: binding.ownerID)
    do {
      #if DEBUG
        if let ownerBoundaryExternalRunCompletion {
          try await ownerBoundaryExternalRunCompletion(
            binding,
            terminalStatus,
            errorCode,
            effectiveCleanupCapability)
        } else {
          _ = try await AgentRuntimeProcess.shared.completeExternalSurfaceRun(
            clientId: Self.externalRunClientID,
            harnessMode: Self.externalRunHarnessMode,
            binding: binding,
            terminalStatus: terminalStatus,
            errorCode: errorCode,
            transitionCleanupCapability: effectiveCleanupCapability)
        }
      #else
        _ = try await AgentRuntimeProcess.shared.completeExternalSurfaceRun(
          clientId: Self.externalRunClientID,
          harnessMode: Self.externalRunHarnessMode,
          binding: binding,
          terminalStatus: terminalStatus,
          errorCode: errorCode,
          transitionCleanupCapability: effectiveCleanupCapability)
      #endif
      return ExternalRunTerminalizationResult(
        binding: binding,
        cleanupCapability: effectiveCleanupCapability,
        closed: true,
        failureCode: nil)
    } catch {
      let code =
        (error as? ExternalSurfaceAuthorityError)?.code
        ?? "external_surface_complete_failed"
      log("RealtimeHub: external run completion failed code=\(code)")
      return ExternalRunTerminalizationResult(
        binding: binding,
        cleanupCapability: effectiveCleanupCapability,
        closed: false,
        failureCode: code)
    }
  }

  func trackExternalRunTerminalization(
    id: UUID,
    ownerID: String,
    terminalStatus: ExternalSurfaceRunTerminalStatus,
    errorCode: String?,
    task: Task<ExternalRunTerminalizationResult, Never>
  ) {
    externalRunTerminalizations[id] = TrackedExternalRunTerminalization(
      ownerID: ownerID,
      terminalStatus: terminalStatus,
      errorCode: errorCode,
      task: task)

    Task { @MainActor [weak self] in
      let result = await task.value
      guard let self else { return }
      self.reconcileTrackedExternalRunTerminalization(id: id, result: result)
    }
  }

  func reconcileTrackedExternalRunTerminalization(
    id: UUID,
    result: ExternalRunTerminalizationResult
  ) {
    // Only a confirmed ordinary close is safe to forget. A failed begin with
    // no binding is unresolved, not proof that Node created no run; retain it
    // until owner quiescence's correlated owner-wide revocation barrier.
    if result.cleanupCapability == nil, result.closed {
      removeTrackedExternalRunTerminalization(id)
    }
  }

  func removeTrackedExternalRunTerminalization(_ id: UUID) {
    externalRunTerminalizations.removeValue(forKey: id)
  }

  func voiceTurnDidTerminate(turnID: VoiceTurnID) {
    if admittedInputTurnID == turnID { admittedInputTurnID = nil }
    if let terminal = VoiceTurnCoordinator.shared.model.lastTerminal,
      terminal.turnID == turnID
    {
      completeExternalRunAuthority(turnID: turnID, reason: terminal.reason)
      if screenEvidence?.descriptor.turnID == turnID {
        clearScreenGrounding(stage: terminal.reason == .success ? "released" : "cancelled")
      }
    } else if screenEvidence?.descriptor.turnID == turnID {
      clearScreenGrounding(stage: "cancelled")
    }
    if pendingSessionRefreshReason != nil { applyPendingSessionRefreshIfIdle() }
  }

  /// Managed users: fetch a short-lived ephemeral token from the backend (gated by
  /// auth + paywall there), then connect. On any failure (incl. 402 not-entitled),
  /// leave the session nil so PTT falls back to the cascade.
  func mintAndConnect(
    provider: RealtimeHubProvider,
    ownerScope: RealtimeHubOwnerScope
  ) {
    guard case .authenticated(let ownerID) = ownerScope,
      isOwnerScopeCurrent(ownerScope),
      let mintGeneration = beginMint(ownerScope: ownerScope)
    else { return }
    let providerParam = provider == .openai ? "openai" : "gemini"
    log("RealtimeHub: minting ephemeral \(provider.displayName) token (managed)")
    Task { [weak self] in
      guard let self else { return }
      let token: String
      do {
        token = try await APIClient.shared.mintRealtimeToken(
          provider: providerParam,
          expectedOwnerID: ownerID)
      } catch let error as RealtimeTokenMintError {
        guard
          self.acceptMintCompletionOrRewarm(
            generation: mintGeneration,
            ownerScope: ownerScope)
        else { return }
        _ = self.releaseMint(generation: mintGeneration, ownerScope: ownerScope)
        self.recordRealtimeMintFailure(
          error, provider: providerParam, phase: "warm", context: "realtime_mint")
        if error.healthError.failureClass.isAccountWide {
          log("RealtimeHub: account credential failure during mint — staying on cascade")
        } else if !self.failoverToAlternateProvider(
          reason: self.failoverReason(for: error.healthError.failureClass))
        {
          log("⚠️ RealtimeHub: ephemeral mint failed on both providers — staying on cascade")
        }
        return
      } catch let error as CredentialHealthError {
        guard
          self.acceptMintCompletionOrRewarm(
            generation: mintGeneration,
            ownerScope: ownerScope)
        else { return }
        _ = self.releaseMint(generation: mintGeneration, ownerScope: ownerScope)
        CredentialHealthManager.shared.record(error, context: "realtime_mint")
        DesktopDiagnosticsManager.shared.recordRealtimeTokenMintFailed(
          provider: providerParam,
          reason: error.failureClass.logValue,
          phase: "warm",
          httpStatusCode: error.failureClass.httpStatusCode)
        if error.failureClass.isAccountWide {
          log("RealtimeHub: account credential failure during mint — staying on cascade")
        } else if !self.failoverToAlternateProvider(
          reason: self.failoverReason(for: error.failureClass))
        {
          log("⚠️ RealtimeHub: ephemeral mint failed on both providers — staying on cascade")
        }
        return
      } catch {
        guard
          self.acceptMintCompletionOrRewarm(
            generation: mintGeneration,
            ownerScope: ownerScope)
        else { return }
        _ = self.releaseMint(generation: mintGeneration, ownerScope: ownerScope)
        let typed = CredentialHealthError.backendTransient(
          statusCode: nil, message: error.localizedDescription)
        CredentialHealthManager.shared.record(typed, context: "realtime_mint")
        DesktopDiagnosticsManager.shared.recordRealtimeTokenMintFailed(
          provider: providerParam,
          reason: "backend_transient",
          phase: "warm")
        if !self.failoverToAlternateProvider() {
          log("⚠️ RealtimeHub: ephemeral mint failed on both providers — staying on cascade")
        }
        return
      }
      guard
        self.acceptMintCompletionOrRewarm(
          generation: mintGeneration,
          ownerScope: ownerScope)
      else { return }
      _ = self.releaseMint(generation: mintGeneration, ownerScope: ownerScope)
      // Provider may have changed (picker/failover) while minting; only connect if still wanted.
      guard self.effectiveProvider == provider, self.session == nil else {
        self.ensureWarm()
        return
      }
      self.startSession(
        provider: provider,
        auth: .ephemeral(token),
        ownerScope: ownerScope)
    }
  }

  func startSession(
    provider: RealtimeHubProvider,
    auth: HubAuth,
    ownerScope: RealtimeHubOwnerScope
  ) {
    guard !RuntimeOwnerIdentity.effectiveOwnerTransitionInProgress else {
      log("RealtimeHub: physical session start denied during effective-owner transition")
      return
    }
    guard isOwnerScopeCurrent(ownerScope) else {
      log("RealtimeHub: session start rejected after authenticated owner changed")
      ensureWarm()
      return
    }
    let topLevelContext = voiceSessionContext(for: ownerScope)
    sessionVoiceContextFreshnessIdentity = topLevelContext.snapshotFreshnessIdentity
    let instructions = RealtimeHubTools.systemInstruction(
      kernelContext: topLevelContext.rendered,
      kernelSemanticGuidance: topLevelContext.semanticGuidance,
      userLanguages: AssistantSettings.shared.voiceBaseLanguages)
    let s = RealtimeHubSession(
      provider: provider,
      auth: auth,
      instructions: instructions,
      availableDirectedProviders: registeredDirectedProviderIDs,
      contextPlanID: topLevelContext.planID,
      stableCacheIdentity: topLevelContext.stableCacheIdentity,
      dynamicContextIdentity: topLevelContext.dynamicContextIdentity,
      contextCacheReplaced: pendingContextCacheReplacement,
      delegate: self)
    pendingContextCacheReplacement = false
    lastWarmAt = nil
    hubConnected = false
    session = s
    voiceSessionID = VoiceSessionID()
    sessionProvider = provider
    sessionAuth = auth
    sessionOwnerBinding = PhysicalSessionOwnerBinding(
      sourceID: ObjectIdentifier(s),
      ownerScope: ownerScope)
    // Both providers stream native spoken audio (24k PCM) → StreamingPCMPlayer;
    // selected app voice playback handles any no-audio fallback.
    if pcmPlayer == nil {
      pcmPlayer = makePCMPlayer()
    }
    s.start()
    log(
      "RealtimeHub: warming \(provider.displayName) session "
        + "(\(auth.isEphemeral ? "ephemeral/managed" : "client-direct/BYOK"), "
        + "contextChars=\(topLevelContext.rendered.count) plan=\(topLevelContext.planID.prefix(24)))")
  }

  struct VoiceSessionContext {
    let sessionID: String
    let rendered: String
    let snapshotFreshnessIdentity: String
    let planID: String
    let stableCacheIdentity: String
    let dynamicContextIdentity: String
    let semanticGuidance: String

    /// Availability contract, mirroring `KernelVoiceContextSnapshot.isResolved`:
    /// a kernel session bound to this owner scope plus a deterministic freshness
    /// identity. Rendered context, plan identities, and semantic guidance are
    /// context *material* — a valid new conversation renders none of it, and
    /// `RealtimeHubTools.escalationBody` omits each empty section on its own.
    /// Requiring them here would fail-closed on the first turn of every session.
    var isResolved: Bool {
      !sessionID.isEmpty && !snapshotFreshnessIdentity.isEmpty
    }
  }

  /// Exact context material selected and rendered by the kernel for realtime.
  func voiceSessionContext(for ownerScope: RealtimeHubOwnerScope) -> VoiceSessionContext {
    guard prefetchedVoiceContextOwnerScope == ownerScope else {
      return VoiceSessionContext(
        sessionID: "", rendered: "", snapshotFreshnessIdentity: "", planID: "",
        stableCacheIdentity: "", dynamicContextIdentity: "", semanticGuidance: "")
    }
    return VoiceSessionContext(
      sessionID: prefetchedVoiceContextSessionID,
      rendered: prefetchedVoiceContext,
      snapshotFreshnessIdentity: prefetchedVoiceContextFreshnessIdentity,
      planID: prefetchedVoiceContextPlanID,
      stableCacheIdentity: prefetchedVoiceStableCacheIdentity,
      dynamicContextIdentity: prefetchedVoiceDynamicContextIdentity,
      semanticGuidance: prefetchedVoiceSemanticGuidance
    )
  }

  /// Prefetch the typed kernel snapshot on PTT key-down before `beginTurn`.
  func prefetchVoiceContextSnapshotIfNeeded() {
    voiceContextPrefetchTask?.cancel()
    voiceContextRefreshGeneration &+= 1
    let refreshGeneration = voiceContextRefreshGeneration
    let ownerScope = currentOwnerScope
    voiceContextPrefetchTask = Task { [weak self] in
      await self?.importLegacyVoiceJournalIfNeeded()
      guard let self, self.isOwnerScopeCurrent(ownerScope) else { return }
      let resolvedSnapshot: KernelVoiceContextSnapshot
      do {
        resolvedSnapshot = try await FloatingControlBarManager.shared.kernelVoiceContextSnapshot()
      } catch is CancellationError {
        // Expected only for a speculative key-down prefetch superseded by the
        // hard refresh. This task owns the suppression.
        return
      } catch {
        return
      }
      let registeredProviders = await AgentRuntimeProcess.shared.registeredDirectedProviderIDs()
      await MainActor.run {
        guard !Task.isCancelled,
          self.voiceContextRefreshGeneration == refreshGeneration,
          self.isOwnerScopeCurrent(ownerScope),
          resolvedSnapshot.isResolved
        else { return }
        self.prefetchedVoiceContext = resolvedSnapshot.context
        self.prefetchedVoiceContextSessionID = resolvedSnapshot.sessionId
        self.prefetchedVoiceContextFreshnessIdentity = resolvedSnapshot.freshnessIdentity
        self.prefetchedVoiceContextPlanID = resolvedSnapshot.contextPlanID
        self.prefetchedVoiceStableCacheIdentity = resolvedSnapshot.stableCacheIdentity
        self.prefetchedVoiceDynamicContextIdentity = resolvedSnapshot.dynamicContextIdentity
        self.prefetchedVoiceSemanticGuidance = resolvedSnapshot.semanticGuidance
        self.updateRegisteredDirectedProviders(registeredProviders)
        self.prefetchedVoiceContextTurnIDs = resolvedSnapshot.turnIDs
        self.prefetchedVoiceContextOwnerScope = ownerScope
        self.reconcileWarmSessionForCurrentRequirement()
      }
    }
  }

  @discardableResult
  func refreshVoiceContextSnapshot() async -> Bool {
    guard !Task.isCancelled else { return false }
    let ownerScope = currentOwnerScope
    await importLegacyVoiceJournalIfNeeded()
    guard !Task.isCancelled, isOwnerScopeCurrent(ownerScope) else { return false }
    voiceContextPrefetchTask?.cancel()
    voiceContextPrefetchTask = nil
    voiceContextRefreshGeneration &+= 1
    let refreshGeneration = voiceContextRefreshGeneration
    let resolvedSnapshot: KernelVoiceContextSnapshot
    do {
      resolvedSnapshot = try await FloatingControlBarManager.shared.kernelVoiceContextSnapshot()
    } catch {
      return false
    }
    let registeredProviders = await AgentRuntimeProcess.shared.registeredDirectedProviderIDs()
    guard resolvedSnapshot.isResolved else {
      log("RealtimeHub: retaining the last voice context after an unresolved kernel snapshot")
      return false
    }
    guard !Task.isCancelled, voiceContextRefreshGeneration == refreshGeneration,
      isOwnerScopeCurrent(ownerScope)
    else {
      return false
    }
    prefetchedVoiceContext = resolvedSnapshot.context
    prefetchedVoiceContextSessionID = resolvedSnapshot.sessionId
    prefetchedVoiceContextFreshnessIdentity = resolvedSnapshot.freshnessIdentity
    prefetchedVoiceContextPlanID = resolvedSnapshot.contextPlanID
    prefetchedVoiceStableCacheIdentity = resolvedSnapshot.stableCacheIdentity
    prefetchedVoiceDynamicContextIdentity = resolvedSnapshot.dynamicContextIdentity
    prefetchedVoiceSemanticGuidance = resolvedSnapshot.semanticGuidance
    updateRegisteredDirectedProviders(registeredProviders)
    prefetchedVoiceContextTurnIDs = resolvedSnapshot.turnIDs
    prefetchedVoiceContextOwnerScope = ownerScope
    reconcileWarmSessionForCurrentRequirement()
    return true
  }

  func updateRegisteredDirectedProviders(_ providers: [String]) {
    let normalized = providers.filter { ["hermes", "openclaw", "codex"].contains($0) }.sorted()
    guard registeredDirectedProviderIDs != normalized else { return }
    registeredDirectedProviderIDs = normalized
    // Tool schemas are immutable per provider session. This asynchronous
    // key-down prefetch used to tear down the socket directly, racing a press.
    // Route it through the same handoff owner and retain any reducer-owned PCM.
    requestSessionHandoff(
      reason: .directedProviderSchema,
      preservingReconnectAudio: reconnectAudioBuffer != nil)
  }

  func reconcileWarmSessionForCurrentRequirement() {
    let requirement = voiceSessionContext(for: currentOwnerScope)
    guard requirement.isResolved else { return }
    if var pending = reconnectAudioBuffer {
      // The speculative key-down read may resolve after capture begins but
      // before a candidate session exists. Move this one buffered turn to the
      // newest canonical requirement so a newly minted socket cannot repeatedly
      // reconnect to the identity it has already superseded.
      guard pending.replaceRequiredContextFreshnessIdentity(requirement.snapshotFreshnessIdentity) else {
        failContextFreshInputPreparation(
          turnID: pending.turnID,
          message: "Voice context admission identity is unavailable")
        return
      }
      reconnectAudioBuffer = pending
    }
    guard session != nil else {
      ensureWarm()
      return
    }
    guard
      RealtimeVoiceContextRefreshPolicy.requiresRefresh(
        currentSnapshotIdentity: requirement.snapshotFreshnessIdentity,
        sessionSnapshotIdentity: sessionVoiceContextFreshnessIdentity)
    else { return }
    requestSessionHandoff(
      reason: .voiceContextFreshness,
      preservingReconnectAudio: reconnectAudioBuffer != nil)
  }

  /// Converts an input already streaming to a live socket into the same
  /// bounded replay representation used for cold admission. This closes the
  /// gap where a mid-hold socket error had no `reconnectAudioBuffer` and thus
  /// terminalized an otherwise recoverable PTT turn.
  @discardableResult
  func beginTransportRebindForActiveInputIfNeeded() -> Bool {
    guard reconnectAudioBuffer == nil,
      let active = VoiceTurnCoordinator.shared.activeTurn,
      active.phase.isRecording || active.hubCommitPending,
      let responseID = voiceResponseID,
      let identity = VoiceTurnCoordinator.shared.reserveEffectIdentity()
    else { return false }
    guard case .hub = active.route else { return false }

    var pending = RealtimeReconnectAudioBuffer(
      turnID: active.id,
      responseID: responseID,
      identity: identity,
      interrupting: reducerInterruptsPreviousTurn)
    guard pending.bindRequiredContextFreshnessIdentity(sessionVoiceContextFreshnessIdentity) else {
      return false
    }
    _ = pending.appendAudio(turnAudio16k)
    reconnectAudioBuffer = pending
    admittedInputTurnID = nil
    VoiceTurnCoordinator.shared.publish(
      .providerReconnectStarted(
        turnID: active.id,
        identity: identity,
        previousSessionID: voiceSessionID))
    log(
      "RealtimeHub: ptt_handoff event=rebind_buffered turn=\(active.id.rawValue.uuidString) "
        + "source=active_input")
    return true
  }

  /// Establish a reducer-owned input boundary before a PTT turn can touch the
  /// provider. The buffer is drained only after the canonical kernel snapshot
  /// has been refreshed and the physical session carries that snapshot.
  @discardableResult
  func beginContextFreshInputPreparation(
    turnID: VoiceTurnID,
    responseID: VoiceResponseID,
    interrupting: Bool
  ) -> Bool {
    guard reconnectAudioBuffer == nil,
      let identity = VoiceTurnCoordinator.shared.reserveEffectIdentity()
    else {
      return false
    }
    reconnectAudioBuffer = RealtimeReconnectAudioBuffer(
      turnID: turnID,
      responseID: responseID,
      identity: identity,
      interrupting: interrupting)
    VoiceTurnCoordinator.shared.publish(
      .providerReconnectStarted(
        turnID: turnID,
        identity: identity,
        previousSessionID: voiceSessionID))
    return true
  }

  /// Drains a PTT input held while the canonical context snapshot was refreshed
  /// onto the already-warm provider. This shares the same reducer fences and
  /// ordered replay path as a physical reconnect without needlessly replacing a
  /// fresh socket.
  func finishContextFreshInputOnCurrentSession() {
    guard let pending = reconnectAudioBuffer, let live = session else { return }
    guard let voiceSessionID else { return }
    let admission = RealtimeInputAdmissionPolicy.decide(
      pending: pending,
      activeTurnID: VoiceTurnCoordinator.shared.activeTurnID,
      sessionContextFreshnessIdentity: sessionVoiceContextFreshnessIdentity)
    if admission == .rejectStaleProviderContext {
      var updated = pending
      guard
        updated.replaceRequiredContextFreshnessIdentity(
          voiceSessionContext(for: currentOwnerScope).snapshotFreshnessIdentity)
      else {
        failContextFreshInputPreparation(
          turnID: pending.turnID,
          message: "Voice context admission identity is unavailable")
        return
      }
      reconnectAudioBuffer = updated
      if updated.requiredContextFreshnessIdentity == sessionVoiceContextFreshnessIdentity {
        finishContextFreshInputOnCurrentSession()
        return
      }
      reconcileWarmSessionForCurrentRequirement()
      return
    }
    guard admission == .admit else {
      reconnectAudioBuffer = nil
      live.abandonInputTurn()
      VoiceTurnCoordinator.shared.publish(
        .providerReconnectFailed(
          turnID: pending.turnID,
          identity: pending.identity,
          message: "realtime context admission rejected: \(admission)"))
      log("RealtimeHub: rejected context-preparation audio before provider admission: \(admission)")
      return
    }
    VoiceTurnCoordinator.shared.publish(
      .providerReconnected(
        turnID: pending.turnID,
        identity: pending.identity,
        sessionID: voiceSessionID))
    guard
      VoiceTurnCoordinator.shared.isProviderConnectionReady(
        turnID: pending.turnID,
        sessionID: voiceSessionID)
    else {
      reconnectAudioBuffer = nil
      live.abandonInputTurn()
      log("RealtimeHub: reducer rejected context-prepared input before audio replay")
      return
    }
    reconnectAudioBuffer = nil
    admittedInputTurnID = pending.turnID
    let candidates = AssistantSettings.shared.voiceBaseLanguages
    if live.supportsInputTranscriptionLanguage, !candidates.isEmpty {
      live.setInputTranscriptionLanguage(candidates.count == 1 ? candidates[0] : turnEarlyVerdictCode)
    }
    live.beginInputTurn(
      turnID: pending.turnID,
      responseID: pending.responseID,
      interrupting: pending.interrupting)
    for pcm16k in pending.audioBuffer {
      sendAudio(pcm16k, to: live)
    }
    if VoiceTurnCoordinator.shared.activeTurn?.hubCommitPending == true {
      live.commitInputTurn()
      VoiceTurnCoordinator.shared.publish(
        .hubCommitAccepted(
          turnID: pending.turnID,
          sessionID: voiceSessionID,
          responseID: pending.responseID))
    }
  }

  /// A released PTT turn remains eligible for context preparation while its
  /// reducer-owned commit is deferred. This lets a short press finish the
  /// snapshot/reconnect/replay sequence instead of abandoning its captured
  /// audio when the key is released before the snapshot arrives.
  func contextFreshInputPreparationIsCurrent(
    turnID: VoiceTurnID,
    preparationEpoch: Int
  ) -> Bool {
    guard VoiceTurnCoordinator.shared.activeTurnID == turnID,
      turnEpoch == preparationEpoch,
      let activeTurn = VoiceTurnCoordinator.shared.activeTurn,
      activeTurn.id == turnID
    else {
      return false
    }
    return activeTurn.phase.isRecording || activeTurn.hubCommitPending
  }

  /// A failed kernel snapshot must release the buffered PTT boundary. Leaving
  /// it pending would prevent the next press from reserving a new input turn.
  func failContextFreshInputPreparation(
    turnID: VoiceTurnID,
    message: String
  ) {
    guard let pending = reconnectAudioBuffer, pending.turnID == turnID else { return }
    reconnectAudioBuffer = nil
    if admittedInputTurnID == turnID { admittedInputTurnID = nil }
    guard VoiceTurnCoordinator.shared.activeTurnID == turnID else { return }
    session?.abandonInputTurn()
    VoiceTurnCoordinator.shared.publish(
      .providerReconnectFailed(
        turnID: turnID,
        identity: pending.identity,
        message: message))
  }

  @discardableResult
  func enqueueTurnPersistence(
    idempotencyKey: String,
    retainingReceipt: Bool = false,
    _ operation: @escaping @MainActor () async -> Bool
  ) -> Task<Bool, Never> {
    turnPersistenceLedger.enqueue(
      continuityKey: idempotencyKey,
      retainingReceipt: retainingReceipt,
      operation)
  }

  /// A deterministic screen-verification failure becomes visible before the provider can
  /// continue. Successful reports do not use this path: they keep provider narration open.
  /// Register its canonical journal obligation through the same retained receipt
  /// path as other authoritative local results before the reducer closes the turn.
  @discardableResult
  func enqueueAuthoritativeScreenEvidenceFailurePersistence(
    ownerID: String,
    assistantText: String
  ) -> Task<Bool, Never> {
    let idempotencyKey = turnIdempotencyKey
    let userText = turnTranscript.trimmingCharacters(in: .whitespacesAndNewlines)
    return enqueueTurnPersistence(idempotencyKey: idempotencyKey, retainingReceipt: true) { [weak self] in
      await self?.persistTurnDirectlyToKernel(
        ownerID: ownerID,
        userText: userText,
        assistantText: assistantText,
        interrupted: false,
        idempotencyKey: idempotencyKey,
        acceptedSpawnOwnerID: nil) ?? false
    }
  }

  /// The kernel journal and its SQLite outbox are the only durable transcript
  /// authority. Swift may retry this idempotent RPC in-process, but never stores
  /// a second durable queue.
  func persistTurnDirectlyToKernel(
    ownerID: String,
    userText: String,
    assistantText: String,
    interrupted: Bool,
    idempotencyKey: String,
    acceptedSpawnOwnerID: String?
  ) async -> Bool {
    guard AuthorizedToolExecution.isOwnerCurrent(ownerID) else {
      log("RealtimeHub: refusing voice journal write after authenticated owner changed")
      return false
    }
    let surface = FloatingControlBarManager.shared.mainChatSurfaceReference()
    let kernelOwnsExchange = RealtimeHubContinuityRestore.kernelOwnsExchange(
      continuityKey: idempotencyKey,
      kernelTurnIDs: prefetchedVoiceContextTurnIDs)
    return await RealtimeTurnJournalAuthority.persist(
      turnOwnerID: ownerID,
      acceptedSpawnOwnerID: acceptedSpawnOwnerID,
      kernelOwnsExchange: kernelOwnsExchange,
      refreshAcceptedSpawn: {
        guard AuthorizedToolExecution.isOwnerCurrent(ownerID) else { return false }
        await FloatingControlBarManager.shared.refreshKernelJournal(surface: surface)
        return AuthorizedToolExecution.isOwnerCurrent(ownerID)
      },
      recordProviderExchange: {
        guard AuthorizedToolExecution.isOwnerCurrent(ownerID) else { return false }
        for attempt in 0..<2 {
          guard AuthorizedToolExecution.isOwnerCurrent(ownerID) else { return false }
          let accepted = await FloatingControlBarManager.shared.recordExchange(
            surface: surface,
            ownerID: ownerID,
            userText: userText,
            assistantText: assistantText,
            origin: "realtime_voice",
            continuityKey: idempotencyKey)
          guard AuthorizedToolExecution.isOwnerCurrent(ownerID) else { return false }
          if accepted { return true }
          if attempt == 0 { try? await Task.sleep(nanoseconds: 250_000_000) }
        }
        log("RealtimeHub: kernel journal rejected voice turn (code=journal_record_failed)")
        return false
      })
  }

  /// Imports at most 200 entries per pass from the retired Swift queue. This is
  /// an upgrade-only reader: successful entries move into the kernel journal and
  /// are deleted from UserDefaults; no new entry is ever written here.
  func importLegacyVoiceJournalIfNeeded() async {
    guard let ownerID = RuntimeOwnerIdentity.currentOwnerId(),
      !legacyVoiceJournalImportedOwners.contains(ownerID)
    else { return }
    if let existing = legacyVoiceJournalImportTask {
      await existing.value
      return
    }
    let task = Task { @MainActor [weak self] in
      guard let self else { return }
      guard let candidates = self.legacyVoiceJournalImportStore.nextBatch(ownerID: ownerID) else {
        log("RealtimeHub: legacy voice journal import skipped unreadable data")
        self.legacyVoiceJournalImportedOwners.insert(ownerID)
        return
      }
      if candidates.isEmpty {
        self.legacyVoiceJournalImportedOwners.insert(ownerID)
        return
      }

      var importedKeys = Set<String>()
      for entry in candidates {
        guard RuntimeOwnerIdentity.currentOwnerId() == ownerID else { break }
        let surface = AgentSurfaceReference(
          surfaceKind: entry.surfaceKind,
          externalRefKind: entry.externalRefKind,
          externalRefId: entry.externalRefID)
        let accepted = await FloatingControlBarManager.shared.recordExchange(
          surface: surface,
          ownerID: ownerID,
          userText: entry.userText,
          assistantText: entry.assistantText,
          origin: "realtime_voice",
          continuityKey: entry.idempotencyKey)
        guard accepted else { break }
        importedKeys.insert(entry.idempotencyKey)
      }

      self.legacyVoiceJournalImportStore.acknowledge(
        ownerID: ownerID, idempotencyKeys: importedKeys)
      if self.legacyVoiceJournalImportStore.nextBatch(ownerID: ownerID)?.isEmpty == true {
        self.legacyVoiceJournalImportedOwners.insert(ownerID)
      }
    }
    legacyVoiceJournalImportTask = task
    await task.value
    legacyVoiceJournalImportTask = nil
  }

  func awaitTurnPersistenceFence() async {
    while !Task.isCancelled {
      let observedGeneration = turnPersistenceLedger.generation
      await turnPersistenceLedger.awaitPendingObligations()
      guard observedGeneration == turnPersistenceLedger.generation else { continue }
      return
    }
  }

  /// Completes the reducer-owned journal fence only after the canonical kernel
  /// has acknowledged this turn's stable idempotency key. Merely enqueueing the
  /// durable outbox entry is not logical success.
  func finalizeJournal(turnID: VoiceTurnID, identity: VoiceEffectIdentity) {
    let idempotencyKey = turnIdempotencyKey
    Task { @MainActor [weak self] in
      guard let self else { return }
      let receipt = await self.turnPersistenceLedger.consumeReceipt(for: idempotencyKey)
      guard VoiceTurnCoordinator.shared.activeTurnID == turnID else { return }
      let accepted = receipt?.accepted == true
      guard VoiceTurnCoordinator.shared.activeTurnID == turnID else { return }
      if accepted {
        VoiceTurnCoordinator.shared.publish(
          .journalAccepted(turnID: turnID, identity: identity))
        // The provider only receives kernel context when its socket starts.
        // Re-warm after the durable journal acknowledgement so the usual next
        // PTT press is already fresh. A press that races this handoff owns a
        // bounded buffer instead of being failed or sent to generic warm wait.
        self.requestSessionHandoff(reason: .persistedVoiceContext)
      } else {
        VoiceTurnCoordinator.shared.publish(
          .journalFailed(
            turnID: turnID,
            identity: identity,
            message: "kernel journal did not acknowledge the turn"))
      }
    }
  }

  func detachPhysicalSessionForTeardown(
    preservingReconnectAudio: Bool = false
  ) -> RealtimeHubSession? {
    let detachedSession = session
    // Detach first so a socket we're dropping can't deliver a late error/close to us
    // and tear down the fresh session we're about to create.
    detachedSession?.detach()
    session = nil
    voiceSessionID = nil
    // The buffered reconnect input is the logical owner of its response ID.
    // Rebind it here so callbacks from the fresh physical socket pass the same
    // identity fence that guarded the original PTT turn.
    voiceResponseID = RealtimeHubReconnectIdentityPolicy.responseIDAfterSessionDetach(
      preservingReconnectAudio: preservingReconnectAudio,
      pendingReconnect: reconnectAudioBuffer)
    sessionProvider = nil
    sessionAuth = nil
    sessionOwnerBinding = nil
    #if DEBUG
      localProfileTransportAuthority = nil
    #endif
    hubConnected = false  // no live session → PTT falls back to the cascade until re-warm
    sessionVoiceContextFreshnessIdentity = ""
    admittedInputTurnID = nil
    geminiSessionNeedsTurnBoundary = false
    if !preservingReconnectAudio {
      reconnectAudioBuffer = nil
    }
    clearBargeInReplacementState()
    clearRealtimeToolTracking()
    return detachedSession
  }

  func teardownSession(preservingReconnectAudio: Bool = false) {
    guard
      let detachedSession = detachPhysicalSessionForTeardown(
        preservingReconnectAudio: preservingReconnectAudio
      )
    else { return }
    schedulePhysicalSessionTeardown(detachedSession)
  }

  func schedulePhysicalSessionTeardown(_ detachedSession: RealtimeHubSession) {
    let sessionID = ObjectIdentifier(detachedSession)
    guard detachedSessionsAwaitingDrain[sessionID] == nil else { return }
    detachedSessionsAwaitingDrain[sessionID] = detachedSession
    Task { @MainActor [weak self, weak detachedSession] in
      guard let detachedSession else { return }
      await detachedSession.stopAndWait()
      self?.detachedSessionsAwaitingDrain.removeValue(forKey: sessionID)
    }
  }

  func clearBargeInReplacementState() {
    bargeInReplacementGeneration &+= 1
    replacementAudioBuffer = nil
    pendingBargeInProvider = nil
    pendingBargeInAuth = nil
    pendingBargeInOwnerScope = nil
    bargeInContinuityTask?.cancel()
    bargeInContinuityTask = nil
  }

  @discardableResult
  func prepareBargeInReplacement() -> Bool {
    guard let provider = sessionProvider ?? pendingBargeInProvider,
      let auth = sessionAuth ?? pendingBargeInAuth,
      let ownerScope = sessionOwnerScope ?? pendingBargeInOwnerScope,
      RealtimeHubOwnerFence.acceptsBargeInReplacement(
        sessionOwner: ownerScope,
        replacementOwner: ownerScope,
        currentOwnerID: RuntimeOwnerIdentity.currentOwnerId()),
      let turnID = VoiceTurnCoordinator.shared.activeTurnID,
      VoiceTurnCoordinator.shared.activeTurn?.ownerID == ownerScope.authenticatedOwnerID,
      let responseID = voiceResponseID,
      let identity = VoiceTurnCoordinator.shared.reserveEffectIdentity()
    else { return false }
    let interruptedSession = session
    interruptedSession?.detach()
    session = nil
    sessionProvider = nil
    sessionAuth = nil
    sessionOwnerBinding = nil
    hubConnected = false
    if let interruptedSession {
      schedulePhysicalSessionTeardown(interruptedSession)
    }
    replacementAudioBuffer = RealtimeReplacementAudioBuffer(
      turnID: turnID,
      responseID: responseID,
      identity: identity)
    VoiceTurnCoordinator.shared.publish(
      .providerReplacementStarted(
        turnID: turnID,
        identity: identity,
        previousResponseID: nil,
        nextResponseID: responseID))
    pendingBargeInProvider = provider
    pendingBargeInAuth = auth
    pendingBargeInOwnerScope = ownerScope
    return true
  }

  func completeBargeInReplacementAfterContinuity(
    interruptedTurnTask: Task<InterruptedTurnPayload?, Never>?
  ) {
    guard let replacementOwnerScope = pendingBargeInOwnerScope,
      isOwnerScopeCurrent(replacementOwnerScope)
    else {
      clearBargeInReplacementState()
      ensureWarm()
      return
    }
    bargeInContinuityTask?.cancel()
    bargeInReplacementGeneration &+= 1
    let generation = bargeInReplacementGeneration
    bargeInContinuityTask = Task { @MainActor [weak self] in
      guard let self else { return }
      let outcome = await RealtimeHubBargeInContinuity.prepareReplacementSession(
        resolveInterruptedTurn: {
          guard generation == self.bargeInReplacementGeneration,
            self.isOwnerScopeCurrent(replacementOwnerScope)
          else { return nil }
          guard let interruptedTurnTask else { return nil }
          return await interruptedTurnTask.value
        },
        recordInterruptedTurn: { [weak self] turn in
          guard let self, generation == self.bargeInReplacementGeneration,
            self.isOwnerScopeCurrent(replacementOwnerScope),
            turn.ownerID == replacementOwnerScope.authenticatedOwnerID
          else { return false }
          let task = self.enqueueTurnPersistence(idempotencyKey: turn.idempotencyKey) {
            [weak self] in
            await self?.persistTurnDirectlyToKernel(
              ownerID: turn.ownerID,
              userText: turn.userText,
              assistantText: turn.assistantText,
              interrupted: true,
              idempotencyKey: turn.idempotencyKey,
              acceptedSpawnOwnerID: turn.acceptedSpawnOwnerID) ?? false
          }
          return await task.value
        },
        refreshVoiceContext: { [weak self] in
          guard let self, generation == self.bargeInReplacementGeneration,
            self.isOwnerScopeCurrent(replacementOwnerScope)
          else { return nil }
          await self.awaitTurnPersistenceFence()
          guard generation == self.bargeInReplacementGeneration,
            self.isOwnerScopeCurrent(replacementOwnerScope)
          else { return nil }
          guard await self.refreshVoiceContextSnapshot() else { return nil }
          return self.prefetchedVoiceContextTurnIDs
        },
        startReplacementSession: { [weak self] in
          guard let self,
            generation == self.bargeInReplacementGeneration,
            self.isOwnerScopeCurrent(replacementOwnerScope),
            self.pendingBargeInOwnerScope == replacementOwnerScope,
            let provider = self.pendingBargeInProvider,
            let auth = self.pendingBargeInAuth
          else { return }
          switch auth {
          case .byokKey:
            self.startReplacementSessionForBargeIn(
              provider: provider,
              auth: auth,
              ownerScope: replacementOwnerScope)
          case .ephemeral:
            self.remintReplacementSessionForBargeIn(provider: provider)
          }
        }
      )
      guard outcome != .started, outcome != .cancelled,
        generation == self.bargeInReplacementGeneration,
        self.isOwnerScopeCurrent(replacementOwnerScope),
        let provider = self.pendingBargeInProvider
      else { return }
      let reason: String
      switch outcome {
      case .interruptedTurnPersistenceFailed:
        reason = "interrupted turn could not be persisted"
      case .contextUnavailable:
        reason = "interrupted turn context did not become visible"
      case .started, .cancelled:
        return
      }
      self.failBargeInReplacement(provider: provider, reason: reason)
    }
  }

  @discardableResult
  func restartSessionForBargeIn(
    interruptedTurnTask: Task<InterruptedTurnPayload?, Never>?
  ) -> Bool {
    guard prepareBargeInReplacement() else { return false }
    completeBargeInReplacementAfterContinuity(interruptedTurnTask: interruptedTurnTask)
    return true
  }

  func remintReplacementSessionForBargeIn(provider: RealtimeHubProvider) {
    guard let ownerScope = pendingBargeInOwnerScope,
      case .authenticated(let ownerID) = ownerScope,
      isOwnerScopeCurrent(ownerScope)
    else {
      clearBargeInReplacementState()
      ensureWarm()
      return
    }
    guard let mintGeneration = beginMint(ownerScope: ownerScope) else {
      log(
        "RealtimeHub[\(provider.displayName)]: barge-in replacement queued behind existing token mint"
      )
      return
    }
    let replacementGeneration = bargeInReplacementGeneration
    let providerParam = provider == .openai ? "openai" : "gemini"
    log("RealtimeHub[\(provider.displayName)]: minting fresh token for barge-in replacement")
    Task { [weak self] in
      guard let self else { return }
      if self.redriveReplacementMintIfStale(
        replacementGeneration: replacementGeneration,
        mintGeneration: mintGeneration,
        ownerScope: ownerScope)
      {
        return
      }
      guard self.replacementAudioBuffer != nil else {
        _ = self.releaseMint(generation: mintGeneration, ownerScope: ownerScope)
        return
      }
      guard self.effectiveProvider == provider, self.session == nil else {
        _ = self.releaseMint(generation: mintGeneration, ownerScope: ownerScope)
        self.clearBargeInReplacementState()
        self.ensureWarm()
        return
      }
      let token: String
      do {
        token = try await APIClient.shared.mintRealtimeToken(
          provider: providerParam,
          expectedOwnerID: ownerID)
      } catch let error as RealtimeTokenMintError {
        if self.redriveReplacementMintIfStale(
          replacementGeneration: replacementGeneration,
          mintGeneration: mintGeneration,
          ownerScope: ownerScope)
        {
          return
        }
        guard self.releaseMint(generation: mintGeneration, ownerScope: ownerScope) else { return }
        self.recordRealtimeMintFailure(
          error,
          provider: providerParam,
          phase: "barge_in_replacement",
          context: "realtime_barge_in_mint")
        if self.shouldFailoverToAlternate(for: error.healthError.failureClass),
          self.failoverBargeInReplacement(
            from: provider,
            reason: self.failoverReason(for: error.healthError.failureClass))
        {
          return
        }
        self.failBargeInReplacement(provider: provider, reason: error.localizedDescription)
        if !error.healthError.failureClass.isAccountWide {
          log("⚠️ RealtimeHub[\(provider.displayName)]: barge-in replacement token mint failed")
        }
        return
      } catch let error as CredentialHealthError {
        if self.redriveReplacementMintIfStale(
          replacementGeneration: replacementGeneration,
          mintGeneration: mintGeneration,
          ownerScope: ownerScope)
        {
          return
        }
        guard self.releaseMint(generation: mintGeneration, ownerScope: ownerScope) else { return }
        CredentialHealthManager.shared.record(error, context: "realtime_barge_in_mint")
        DesktopDiagnosticsManager.shared.recordRealtimeTokenMintFailed(
          provider: providerParam,
          reason: error.failureClass.logValue,
          phase: "barge_in_replacement",
          httpStatusCode: error.failureClass.httpStatusCode)
        if self.shouldFailoverToAlternate(for: error.failureClass),
          self.failoverBargeInReplacement(
            from: provider,
            reason: self.failoverReason(for: error.failureClass))
        {
          return
        }
        self.failBargeInReplacement(provider: provider, reason: error.localizedDescription)
        if !error.failureClass.isAccountWide {
          log("⚠️ RealtimeHub[\(provider.displayName)]: barge-in replacement token mint failed")
        }
        return
      } catch {
        if self.redriveReplacementMintIfStale(
          replacementGeneration: replacementGeneration,
          mintGeneration: mintGeneration,
          ownerScope: ownerScope)
        {
          return
        }
        guard self.releaseMint(generation: mintGeneration, ownerScope: ownerScope) else { return }
        DesktopDiagnosticsManager.shared.recordRealtimeTokenMintFailed(
          provider: providerParam,
          reason: "backend_transient",
          phase: "barge_in_replacement")
        if self.failoverBargeInReplacement(from: provider, reason: "other") {
          return
        }
        self.failBargeInReplacement(provider: provider, reason: error.localizedDescription)
        log("⚠️ RealtimeHub[\(provider.displayName)]: barge-in replacement token mint failed")
        return
      }
      if self.redriveReplacementMintIfStale(
        replacementGeneration: replacementGeneration,
        mintGeneration: mintGeneration,
        ownerScope: ownerScope)
      {
        return
      }
      guard self.releaseMint(generation: mintGeneration, ownerScope: ownerScope) else { return }
      self.startReplacementSessionForBargeIn(
        provider: provider,
        auth: .ephemeral(token),
        ownerScope: ownerScope)
    }
  }

  /// A completed mint belongs to the replacement generation that started it.
  /// Stale success and failure callbacks may only release the mint slot and
  /// redrive the newest generation; they must not mutate that generation's state.
  @discardableResult
  func redriveReplacementMintIfStale(
    replacementGeneration: UInt64,
    mintGeneration: UInt64,
    ownerScope: RealtimeHubOwnerScope
  ) -> Bool {
    guard self.mintGeneration == mintGeneration, mintOwnerScope == ownerScope else { return true }
    let generationChanged = replacementGeneration != bargeInReplacementGeneration
    let ownerChanged =
      !isOwnerScopeCurrent(ownerScope)
      || pendingBargeInOwnerScope != ownerScope
    guard generationChanged || ownerChanged else { return false }
    _ = releaseMint(generation: mintGeneration, ownerScope: ownerScope)
    if ownerChanged {
      log("RealtimeHub: discarding barge-in remint after authenticated owner changed")
      clearBargeInReplacementState()
      ensureWarm()
    } else if replacementAudioBuffer != nil, let currentProvider = pendingBargeInProvider {
      remintReplacementSessionForBargeIn(provider: currentProvider)
    }
    return true
  }

  func startReplacementSessionForBargeIn(
    provider: RealtimeHubProvider,
    auth: HubAuth,
    ownerScope: RealtimeHubOwnerScope
  ) {
    guard
      RealtimeHubOwnerFence.acceptsBargeInReplacement(
        sessionOwner: ownerScope,
        replacementOwner: pendingBargeInOwnerScope,
        currentOwnerID: RuntimeOwnerIdentity.currentOwnerId())
    else {
      clearBargeInReplacementState()
      ensureWarm()
      return
    }
    startSession(provider: provider, auth: auth, ownerScope: ownerScope)
  }

  func finishBargeInReplacementAfterSessionReady() {
    guard let pending = replacementAudioBuffer else { return }
    replacementAudioBuffer = nil
    pendingBargeInProvider = nil
    pendingBargeInAuth = nil
    pendingBargeInOwnerScope = nil
    guard let voiceSessionID else { return }
    VoiceTurnCoordinator.shared.publish(
      .providerReplacementReady(
        turnID: pending.turnID,
        identity: pending.identity,
        sessionID: voiceSessionID,
        responseID: pending.responseID))
    guard
      VoiceTurnCoordinator.shared.isProviderConnectionReady(
        turnID: pending.turnID,
        sessionID: voiceSessionID,
        responseID: pending.responseID)
    else {
      session?.abandonInputTurn()
      log("RealtimeHub: discarded stale barge-in replacement before audio replay")
      return
    }
    if let live = session {
      live.beginInputTurn(
        turnID: pending.turnID,
        responseID: pending.responseID,
        interrupting: false)
    }
    flushBargeInReplacementAudioBuffer(pending.audioBuffer)
    if VoiceTurnCoordinator.shared.activeTurn?.hubCommitPending == true {
      session?.commitInputTurn()
      VoiceTurnCoordinator.shared.publish(
        .hubCommitAccepted(
          turnID: pending.turnID,
          sessionID: voiceSessionID,
          responseID: pending.responseID))
    }
  }

  /// Replays a turn captured while a regular warm session was being replaced.
  /// The provider input window opens before replay so Gemini's activity boundaries
  /// and OpenAI's event ownership remain tied to the original PTT turn.
  func finishSessionReconnectAfterReady() {
    guard let pending = reconnectAudioBuffer, let live = session else { return }
    guard let voiceSessionID else { return }
    let admission = RealtimeInputAdmissionPolicy.decide(
      pending: pending,
      activeTurnID: VoiceTurnCoordinator.shared.activeTurnID,
      sessionContextFreshnessIdentity: sessionVoiceContextFreshnessIdentity)
    if admission == .rejectStaleProviderContext {
      var updated = pending
      guard
        updated.replaceRequiredContextFreshnessIdentity(
          voiceSessionContext(for: currentOwnerScope).snapshotFreshnessIdentity)
      else {
        failContextFreshInputPreparation(
          turnID: pending.turnID,
          message: "Voice context admission identity is unavailable")
        return
      }
      reconnectAudioBuffer = updated
      if updated.requiredContextFreshnessIdentity == sessionVoiceContextFreshnessIdentity {
        finishSessionReconnectAfterReady()
        return
      }
      reconcileWarmSessionForCurrentRequirement()
      return
    }
    guard admission == .admit else {
      reconnectAudioBuffer = nil
      live.abandonInputTurn()
      VoiceTurnCoordinator.shared.publish(
        .providerReconnectFailed(
          turnID: pending.turnID,
          identity: pending.identity,
          message: "realtime reconnect admission rejected: \(admission)"))
      log("RealtimeHub: rejected reconnect audio before provider admission: \(admission)")
      return
    }
    reconnectAudioBuffer = nil
    VoiceTurnCoordinator.shared.publish(
      .providerReconnected(
        turnID: pending.turnID,
        identity: pending.identity,
        sessionID: voiceSessionID))
    guard
      VoiceTurnCoordinator.shared.isProviderConnectionReady(
        turnID: pending.turnID,
        sessionID: voiceSessionID)
    else {
      live.abandonInputTurn()
      log("RealtimeHub: reducer rejected reconnect before audio replay")
      return
    }
    admittedInputTurnID = pending.turnID
    let candidates = AssistantSettings.shared.voiceBaseLanguages
    if live.supportsInputTranscriptionLanguage, !candidates.isEmpty {
      live.setInputTranscriptionLanguage(candidates.count == 1 ? candidates[0] : turnEarlyVerdictCode)
    }
    live.beginInputTurn(
      turnID: pending.turnID,
      responseID: pending.responseID,
      interrupting: pending.interrupting)
    for pcm16k in pending.audioBuffer {
      sendAudio(pcm16k, to: live)
    }
    if VoiceTurnCoordinator.shared.activeTurn?.hubCommitPending == true {
      live.commitInputTurn()
      VoiceTurnCoordinator.shared.publish(
        .hubCommitAccepted(
          turnID: pending.turnID,
          sessionID: voiceSessionID,
          responseID: pending.responseID))
    }
  }

  func failBargeInReplacement(provider: RealtimeHubProvider, reason: String) {
    let failedBuffer = replacementAudioBuffer
    let hadCommittedTurn =
      failedBuffer.map {
        VoiceTurnCoordinator.shared.activeTurn?.id == $0.turnID
          && VoiceTurnCoordinator.shared.activeTurn?.hubCommitPending == true
      } ?? false
    clearBargeInReplacementState()
    log(
      "RealtimeHub[\(provider.displayName)]: barge-in replacement failed "
        + "\(hadCommittedTurn ? "after commit" : "while recording") — \(reason)")
    realtimePlaybackEpoch += 1
    pcmPlayer?.stop()
    responseGlowGate.clearImmediately()
    exitVoiceUI(clearResponseGlow: true)
    if let failedBuffer {
      VoiceTurnCoordinator.shared.publish(
        .providerReplacementFailed(
          turnID: failedBuffer.turnID,
          identity: failedBuffer.identity,
          message: reason))
    }
  }

  func flushBargeInReplacementAudioBuffer(_ bufferedChunks: [Data]) {
    guard let s = session, !bufferedChunks.isEmpty else { return }
    for pcm16k in bufferedChunks {
      sendAudio(pcm16k, to: s)
    }
  }
}
