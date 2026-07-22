import AppKit
import CoreGraphics
import Foundation
import OmiSupport
import VoiceTurnDomain

private struct RealtimeToolArgumentsBox: @unchecked Sendable {
  let value: [String: Any]
  init(_ value: [String: Any]) { self.value = value }
}

extension RealtimeHubController {
  // MARK: - RealtimeHubSessionDelegate

  func isCurrentSession(_ source: RealtimeHubSession) -> Bool {
    let isLiveSessionObject = source === session
    let sessionOwnerIsCurrent = RealtimeHubOwnerFence.canReuseWarmSession(
      sessionOwner: sessionOwnerScope,
      currentOwnerID: RuntimeOwnerIdentity.currentOwnerId())
    guard
      RealtimeHubReconnectIdentityPolicy.admitsSessionCallback(
        isLiveSessionObject: isLiveSessionObject,
        sessionOwnerIsCurrent: sessionOwnerIsCurrent)
    else {
      if isLiveSessionObject {
        log("RealtimeHub: dropping socket callback after authenticated owner changed")
        discardSessionAfterOwnerChange()
        ensureWarm()
      }
      return false
    }
    return true
  }

  func acceptsTurnEvent(
    _ identity: RealtimeHubEventIdentity?,
    source: RealtimeHubSession
  ) -> Bool {
    guard isCurrentSession(source), let identity else { return false }
    guard VoiceTurnCoordinator.shared.requireCurrentOwner(for: identity.turnID) != nil else {
      log("RealtimeHub: dropping provider event after authenticated owner changed")
      return false
    }
    guard identity.turnID == VoiceTurnCoordinator.shared.activeTurnID,
      RealtimeHubEventOwnership.accepts(
        identity,
        activeTurnID: VoiceTurnCoordinator.shared.activeTurnID,
        activeResponseID: voiceResponseID)
    else {
      log(
        "RealtimeHub: dropping stale provider event turn=\(identity.turnID) "
          + "response=\(identity.responseID)")
      return false
    }
    return true
  }

  func sendToolResultIfCurrent(
    source: RealtimeHubSession,
    callId: String,
    name: String,
    output: String,
    screenEvidence: RealtimeScreenEvidenceAttachment? = nil,
    expectedTurnEpoch: Int? = nil
  ) {
    guard isCurrentSession(source) else {
      log("RealtimeHub[\(providerTag)]: dropping stale tool result \(name)")
      return
    }
    let turnEpoch = expectedTurnEpoch ?? realtimeToolTurnEpoch
    let key = toolCallKey(callId: callId, name: name, turnEpoch: turnEpoch)
    guard turnEpoch == realtimeToolTurnEpoch,
      let identity = toolEffectIdentityByTransportKey[key]
    else {
      log("RealtimeHub[\(providerTag)]: dropping stale tool result \(name) epoch=\(turnEpoch)")
      return
    }
    toolEffectIdentityByTransportKey.removeValue(forKey: key)
    let turnID = VoiceTurnID(identity.generation)
    let deferredScreenProtocol =
      name == HubTool.screenshot.rawValue
      && screenGroundingState.protocolToken?.screenshotCallID == VoiceToolCallID(callId)
      && screenGroundingState.protocolToken?.screenshotIdentity == identity
    let toolIsActive = VoiceTurnCoordinator.shared.isToolEffectActive(
      turnID: turnID,
      callID: VoiceToolCallID(callId),
      identity: identity)
    guard toolIsActive || deferredScreenProtocol else {
      log("RealtimeHub[\(providerTag)]: dropping tool result after reducer revoked \(name)")
      return
    }
    if !deferredScreenProtocol {
      VoiceTurnCoordinator.shared.publish(
        .toolFinishedScoped(
          turnID: turnID,
          identity: identity,
          callID: VoiceToolCallID(callId)))
    }
    let providerResult = RealtimeProviderToolResultPolicy.prepare(
      provider: effectiveProvider,
      name: name,
      output: output)
    if providerResult.wasOversized {
      DesktopDiagnosticsManager.shared.recordFallback(
        area: "realtime_hub",
        from: "tool_result_full",
        to: "tool_result_error",
        reason: "capability_mismatch",
        outcome: .degraded,
        extra: [
          "tool": name,
          "original_bytes": providerResult.originalByteCount,
          "provider_bytes": providerResult.output.utf8.count,
          "user_visible": true,
        ])
    }
    log(
      "RealtimeHub[\(providerTag)]: tool result \(name) raw_bytes=\(providerResult.originalByteCount) "
        + "provider_bytes=\(providerResult.output.utf8.count) oversized=\(providerResult.wasOversized)"
    )
    if let screenEvidence {
      // `sendToolResult` crosses the provider session's serial queue. Do not mint the visual
      // receipt until that queue has accepted the exact image/function-response wire; scheduling
      // the asynchronous call is not yet a transport fact.
      logScreenEvidence(stage: "tool_wire_scheduled", evidence: screenEvidence.descriptor, callID: callId)
      source.sendToolResult(
        callId: callId,
        name: name,
        output: providerResult.output,
        screenEvidence: screenEvidence,
        onWireEnqueued: { [weak self, weak source] didEnqueue in
          DispatchQueue.main.async {
            guard let self, let source else { return }
            guard didEnqueue else {
              self.logScreenEvidence(
                stage: "tool_wire_enqueue_failed",
                evidence: screenEvidence.descriptor,
                callID: callId)
              self.rejectScreenEvidence(screenEvidence.descriptor, reason: "tool_wire_enqueue_failed")
              return
            }
            self.markScreenEvidenceTransportEnqueued(
              screenEvidence,
              source: source,
              callID: callId,
              turnEpoch: turnEpoch)
          }
        })
    } else {
      source.sendToolResult(
        callId: callId,
        name: name,
        output: providerResult.output)
    }
  }

  @discardableResult
  func beginExternalRunAuthorityIfNeeded(
    turnID: VoiceTurnID,
    prompt: String
  ) -> Task<ExternalSurfaceRunBinding, Error> {
    if let state = externalRunAuthorityState, state.turnID == turnID {
      return state.task
    }
    let normalizedPrompt = prompt.trimmingCharacters(in: .whitespacesAndNewlines)
    let sessionID = prefetchedVoiceContextSessionID
    let capturedOwnerID = RuntimeOwnerIdentity.currentOwnerId() ?? ""
    let task = Task<ExternalSurfaceRunBinding, Error> {
      guard !capturedOwnerID.isEmpty,
        RuntimeOwnerIdentity.currentOwnerId() == capturedOwnerID
      else {
        throw ExternalSurfaceAuthorityError(code: "external_surface_owner_unavailable")
      }
      guard !sessionID.isEmpty else {
        throw ExternalSurfaceAuthorityError(code: "realtime_voice_session_unavailable")
      }
      let runtime = AgentRuntimeProcess.shared
      return try await runtime.beginExternalSurfaceRun(
        clientId: Self.externalRunClientID,
        harnessMode: Self.externalRunHarnessMode,
        ownerID: capturedOwnerID,
        sessionID: sessionID,
        turnID: turnID.rawValue.uuidString.lowercased(),
        prompt: normalizedPrompt,
        mode: .act)
    }
    externalRunAuthorityState = .init(
      ownerID: capturedOwnerID,
      turnID: turnID,
      task: task)
    return task
  }

  func invokeExternallyAuthorizedTool(
    source: RealtimeHubSession,
    turnID: VoiceTurnID,
    identity: VoiceEffectIdentity,
    callId: String,
    name: String,
    arguments: [String: Any],
    expectedTurnEpoch: Int,
    permissionTranscriptRequestStartedAt: Date? = nil
  ) {
    let now = Date()
    let transcript = turnTranscript.trimmingCharacters(in: .whitespacesAndNewlines)
    let permissionRequestStartedAt = permissionTranscriptRequestStartedAt ?? now
    switch RealtimePermissionTranscriptSettlementPolicy.decision(
      toolName: name,
      transcriptIsFinal: providerTranscriptFinalized,
      hasTranscript: !transcript.isEmpty,
      lastTranscriptUpdate: lastInputTranscriptUpdateAt,
      requestStartedAt: permissionRequestStartedAt,
      now: now)
    {
    case .wait(let delay):
      Task { [weak self, source] in
        try? await Task.sleep(for: .seconds(delay))
        guard let self,
          self.isCurrentToolTurn(
            source: source,
            callId: callId,
            name: name,
            expectedTurnEpoch: expectedTurnEpoch)
        else { return }
        self.invokeExternallyAuthorizedTool(
          source: source,
          turnID: turnID,
          identity: identity,
          callId: callId,
          name: name,
          arguments: arguments,
          expectedTurnEpoch: expectedTurnEpoch,
          permissionTranscriptRequestStartedAt: permissionRequestStartedAt)
      }
      return
    case .reject:
      log("RealtimeHub[\(providerTag)]: rejecting permission tool without settled voice transcript context")
      sendToolResultIfCurrent(
        source: source,
        callId: callId,
        name: name,
        output: "The permission tool could not be safely authorized because the voice transcript was unavailable.",
        expectedTurnEpoch: expectedTurnEpoch)
      return
    case .execute:
      break
    }
    guard
      let promptSelection = RealtimeExternalRunPromptPolicy.promptForAuthorizedTool(
        transcript: transcript,
        isFinal: providerTranscriptFinalized,
        toolName: name,
        arguments: arguments)
    else {
      log("RealtimeHub[\(providerTag)]: rejecting permission tool without voice transcript context")
      sendToolResultIfCurrent(
        source: source,
        callId: callId,
        name: name,
        output: "The permission tool could not be safely authorized because the voice transcript was unavailable.",
        expectedTurnEpoch: expectedTurnEpoch)
      return
    }
    if promptSelection.source == .authorizedToolFallback {
      DesktopDiagnosticsManager.shared.recordFallback(
        area: "realtime_hub",
        from: "provider_transcript",
        to: "authorized_tool",
        reason: "capability_mismatch",
        outcome: .recovered,
        extra: ["user_visible": true])
      log("RealtimeHub[\(providerTag)]: executing authorized tool without final provider transcript")
    }
    executeExternallyAuthorizedTool(
      source: source,
      turnID: turnID,
      identity: identity,
      callId: callId,
      name: name,
      arguments: arguments,
      expectedTurnEpoch: expectedTurnEpoch,
      runPrompt: promptSelection.prompt)
  }

  func executeExternallyAuthorizedTool(
    source: RealtimeHubSession,
    turnID: VoiceTurnID,
    identity: VoiceEffectIdentity,
    callId: String,
    name: String,
    arguments: [String: Any],
    expectedTurnEpoch: Int,
    runPrompt: String
  ) {
    guard
      isCurrentToolTurn(
        source: source,
        callId: callId,
        name: name,
        expectedTurnEpoch: expectedTurnEpoch)
    else { return }
    let invocationID = RealtimeExternalToolInvocationIdentity.make(
      turnID: turnID,
      providerCallID: callId,
      toolName: name)
    let runTask = beginExternalRunAuthorityIfNeeded(turnID: turnID, prompt: runPrompt)
    let argumentsBox = RealtimeToolArgumentsBox(arguments)
    Task { [weak self, source, argumentsBox] in
      guard let self else { return }
      do {
        let arguments = argumentsBox.value
        let binding = try await runTask.value
        guard
          self.isCurrentToolTurn(
            source: source,
            callId: callId,
            name: name,
            expectedTurnEpoch: expectedTurnEpoch)
        else { return }
        let inputHash = try AuthorizedToolExecution.inputHash(for: arguments)
        let invocation = RealtimeAuthorizedToolInvocation(
          invocationID: invocationID,
          binding: binding,
          turnID: turnID,
          callID: VoiceToolCallID(callId),
          effectIdentity: identity,
          canonicalToolName: name,
          inputHash: inputHash,
          sourceObjectID: ObjectIdentifier(source),
          turnEpoch: expectedTurnEpoch)
        self.authorizedRealtimeInvocations[invocationID] = invocation
        defer {
          self.authorizedRealtimeInvocations.removeValue(forKey: invocationID)
          self.authorizedRealtimeScreenshotImages.removeValue(forKey: invocationID)
        }
        let output = try await AgentRuntimeProcess.shared.invokeExternalSurfaceTool(
          clientId: Self.externalRunClientID,
          harnessMode: Self.externalRunHarnessMode,
          binding: binding,
          invocationID: invocationID,
          toolName: name,
          input: arguments)
        // The tool may complete after a barge-in or owner/session replacement.
        // Never let that stale completion mutate either journal ownership or the
        // visible pill projection.
        guard
          self.isCurrentToolTurn(
            source: source,
            callId: callId,
            name: name,
            expectedTurnEpoch: expectedTurnEpoch)
        else { return }
        self.lastExternalToolName = name
        self.lastExternalToolErrorCode = ""
        if name == "spawn_agent" {
          let spawnOutcome = RealtimeSpawnAgentToolOutcome.classify(
            output: output,
            expectedContinuityKey: self.turnIdempotencyKey)
          let expectedContinuityKey = "voice:\(turnID.rawValue.uuidString.lowercased())"
          switch spawnOutcome {
          case .accepted(let receipt) where receipt.continuityKey == expectedContinuityKey:
            self.acceptedSpawnJournalReceiptByContinuityKey[receipt.continuityKey] =
              AcceptedSpawnJournalReceipt(ownerID: binding.ownerID, receipt: receipt)
            self.turnPersistenceLedger.recordAcceptedReceipt(for: receipt.continuityKey)
            self.lastTurnDiagnostics = [
              "provider": self.providerTag,
              "provider_transcript": self.turnTranscript,
              "provider_transcript_language": "",
              "saved_user_text": self.turnTranscript,
              "used_local_transcript": "false",
              "local_transcript": "",
              "local_language": "",
              "assistant_reply": receipt.assistantText,
              "provider_assistant_reply": self.assistantText,
              "external_tool_name": name,
              "external_tool_error": "",
            ]
            // The receipt is canonical for journal persistence, while the same
            // realtime turn remains the sole audible response. Clearing any
            // pre-tool speculation keeps it out of the visible reply without
            // interrupting native provider audio or changing voices.
            self.assistantText = ""
            log(
              "RealtimeHub[\(self.providerTag)]: accepted spawn receipt; preserving native provider continuation"
            )
            if let pill = receipt.pillProjection {
              AgentPillsManager.shared.upsertSpawnedPill(
                id: pill.pillID,
                query: pill.objective,
                title: pill.title,
                sessionId: pill.sessionID,
                runId: pill.runID,
                attemptId: pill.attemptID,
                provider: pill.provider,
                producingJournalSurface: FloatingControlBarManager.shared.realtimeVoiceSurfaceReference())
            }
          case .setupNeeded(let provider):
            self.lastExternalToolErrorCode = "provider_setup_needed"
            self.sendToolResultIfCurrent(
              source: source,
              callId: callId,
              name: name,
              output: RealtimeProviderToolResultPolicy.rejectedOutput(
                code: "provider_setup_needed",
                message: provider.setupNeededStatus,
                preservingCanonicalEnvelopeFrom: output),
              expectedTurnEpoch: expectedTurnEpoch)
            VoiceTurnCoordinator.shared.publish(.finish(turnID: turnID, reason: .providerFailed))
            return
          case .accepted, .rejected:
            log("RealtimeHub[\(self.providerTag)]: spawn_agent rejected without a canonical child receipt")
            self.sendToolResultIfCurrent(
              source: source,
              callId: callId,
              name: name,
              output: RealtimeProviderToolResultPolicy.rejectedOutput(
                code: "realtime_spawn_rejected",
                message: "The background agent could not start. Please try again.",
                preservingCanonicalEnvelopeFrom: output),
              expectedTurnEpoch: expectedTurnEpoch)
            VoiceTurnCoordinator.shared.publish(.finish(turnID: turnID, reason: .providerFailed))
            return
          }
        }
        let screenshotImage = self.authorizedRealtimeScreenshotImages.removeValue(
          forKey: invocationID)
        self.sendToolResultIfCurrent(
          source: source,
          callId: callId,
          name: name,
          output: output,
          screenEvidence: screenshotImage,
          expectedTurnEpoch: expectedTurnEpoch)
      } catch {
        let code =
          (error as? ExternalSurfaceAuthorityError)?.code
          ?? "external_surface_tool_failed"
        guard
          self.isCurrentToolTurn(
            source: source,
            callId: callId,
            name: name,
            expectedTurnEpoch: expectedTurnEpoch)
        else { return }
        self.lastExternalToolName = name
        self.lastExternalToolErrorCode = code
        log("RealtimeHub[\(self.providerTag)]: kernel rejected tool \(name) code=\(code)")
        self.sendToolResultIfCurrent(
          source: source,
          callId: callId,
          name: name,
          output: RealtimeProviderToolResultPolicy.rejectedOutput(
            code: code,
            message: "The tool could not be authorized. Please try again."),
          expectedTurnEpoch: expectedTurnEpoch)
      }
    }
  }

  func executeAuthorizedRealtimeTool(
    _ command: AuthorizedToolExecution
  ) async -> AuthorizedRealtimeToolExecutionResult {
    guard let invocation = authorizedRealtimeInvocations[command.invocationID] else {
      return .failed(Self.authorizedRealtimeToolError(code: "unknown_realtime_invocation"))
    }
    let activeSourceObjectID = session.map(ObjectIdentifier.init)
    let activeToolIdentity = VoiceTurnCoordinator.shared.activeTurn?
      .toolEffectIdentities[invocation.callID]
    guard
      RealtimeAuthorizedToolOwnership.accepts(
        command: command,
        invocation: invocation,
        activeTurnID: VoiceTurnCoordinator.shared.activeTurnID,
        activeToolIdentity: activeToolIdentity,
        activeSourceObjectID: activeSourceObjectID,
        currentTurnEpoch: realtimeToolTurnEpoch)
    else {
      log("RealtimeHub: rejected stale/mismatched authorized realtime tool command")
      return .failed(
        Self.authorizedRealtimeToolError(code: "stale_realtime_tool_authorization"))
    }
    guard AuthorizedToolExecution.isOwnerCurrent(command.ownerID) else {
      return .failed(Self.authorizedRealtimeOwnerChangedError())
    }
    guard
      RealtimeAuthorizedInvocationReplayGate.shouldExecute(
        invocationID: command.invocationID,
        completedInvocationIDs: completedAuthorizedRealtimeInvocationIDs)
    else {
      log("RealtimeHub: rejected replayed authorized realtime tool command")
      return .failed(
        Self.authorizedRealtimeToolError(code: "replayed_realtime_tool_authorization"))
    }
    completedAuthorizedRealtimeInvocationIDs.insert(command.invocationID)

    guard let tool = HubTool(rawValue: command.canonicalToolName) else {
      return .failed(Self.authorizedRealtimeToolError(code: "unsupported_realtime_tool"))
    }
    switch tool {
    case .getTasks:
      await TasksStore.shared.loadDashboardTasks(expectedOwnerID: command.ownerID)
      guard AuthorizedToolExecution.isOwnerCurrent(command.ownerID) else {
        return .failed(Self.authorizedRealtimeOwnerChangedError())
      }
      let overdue = TasksStore.shared.overdueTasks
      let today = TasksStore.shared.todaysTasks
      func list(_ items: [TaskActionItem]) -> String {
        items.prefix(15).map { "- \($0.description) [id:\($0.id)]" }.joined(separator: "\n")
      }
      var output = ""
      if !overdue.isEmpty { output += "Overdue (\(overdue.count)):\n\(list(overdue))\n" }
      if !today.isEmpty { output += "Due today (\(today.count)):\n\(list(today))\n" }
      return .succeeded(output.isEmpty ? "No tasks overdue or due today." : output)

    case .askHigherModel:
      let query = (command.input["query"] as? String) ?? turnTranscript
      let toolContext = (command.input["context"] as? String) ?? ""
      let kernelContext = voiceSessionContext(for: currentOwnerScope)
      guard kernelContext.isResolved else {
        return .failed(Self.authorizedRealtimeToolError(code: "kernel_context_unavailable"))
      }
      return await escalateToHigherModel(
        query,
        kernelSemanticGuidance: kernelContext.semanticGuidance,
        kernelContext: kernelContext.rendered,
        stableCacheIdentity: kernelContext.stableCacheIdentity,
        dynamicContextIdentity: kernelContext.dynamicContextIdentity,
        contextPlanID: kernelContext.planID,
        toolContext: toolContext,
        ownerID: command.ownerID)

    case .screenshot:
      // Preserve the original descriptor before suspension. The timeout branch must never read
      // mutable `screenEvidence` after a barge-in, because that may already belong to a new turn.
      let capturedEvidence = screenEvidence?.descriptor
      let currentEvidence = await screenEvidenceForAuthorizedScreenshot()
      let invocationIsCurrent = isCurrentAuthorizedRealtimeInvocation(command, invocation: invocation)
      guard invocationIsCurrent else {
        return .failed(Self.authorizedRealtimeToolError(code: "stale_realtime_tool_authorization"))
      }
      guard
        let captureResult = Self.performOwnerBoundPhysicalEffect(
          expectedOwnerID: command.ownerID,
          effect: { [currentEvidence] in [currentEvidence] })
      else {
        return .failed(Self.authorizedRealtimeOwnerChangedError())
      }
      let evidence = captureResult[0]
      guard let evidence,
        evidence.descriptor.turnID == VoiceTurnCoordinator.shared.activeTurnID,
        let jpeg = evidence.jpeg,
        evidence.descriptor.canVerifyCurrentScreen
      else {
        guard
          let failureEvidence = RealtimeScreenEvidenceToolExecutionPolicy.failureEvidence(
            capturedEvidence: capturedEvidence,
            commandTurnID: invocation.turnID,
            activeTurnID: VoiceTurnCoordinator.shared.activeTurnID,
            invocationIsCurrent: invocationIsCurrent)
        else {
          return .failed(Self.authorizedRealtimeToolError(code: "stale_realtime_tool_authorization"))
        }
        rejectScreenEvidence(failureEvidence, reason: "capture_unavailable")
        return .succeeded(
          screenshotToolResultTextForCurrentProvider(
            attachment: nil,
            unavailableEvidence: failureEvidence))
      }
      let attachment = RealtimeScreenEvidenceAttachment(descriptor: evidence.descriptor, jpeg: jpeg)
      // The provider receives these exact pre-overlay pixels only inside the matching tool
      // response. Gemini must not race a separate realtime video frame against an unblocked
      // function, and a later pointer-selected display can never replace this evidence.
      authorizedRealtimeScreenshotImages[command.invocationID] = attachment
      return .succeeded(screenshotToolResultTextForCurrentProvider(attachment: attachment))

    case .pointClick:
      guard let x = Self.finiteCoordinate(command.input["x"]),
        let y = Self.finiteCoordinate(command.input["y"])
      else {
        return .succeeded(
          "Could not click: point_click requires finite numeric x and y coordinates.")
      }
      guard
        Self.click(
          at: CGPoint(x: x, y: y),
          expectedOwnerID: command.ownerID)
      else {
        return AuthorizedToolExecution.isOwnerCurrent(command.ownerID)
          ? .succeeded("Could not click.")
          : .failed(Self.authorizedRealtimeOwnerChangedError())
      }
      return .succeeded("Clicked at \(Int(x)), \(Int(y)).")

    default:
      return .failed(Self.authorizedRealtimeToolError(code: "wrong_realtime_executor_tool"))
    }
  }

  nonisolated static func authorizedRealtimeToolError(code: String) -> String {
    #"{"ok":false,"error":{"code":"\#(code)"}}"#
  }

  nonisolated static func authorizedRealtimeOwnerChangedError() -> String {
    authorizedRealtimeToolError(code: AuthorizedToolExecution.Rejection.ownerChangedDuringExecution.code)
  }

  func hubDidConnect(source: RealtimeHubSession) {
    guard isCurrentSession(source) else { return }
    lastWarmAt = Date()
    hubConnected = true  // authenticated + ready — PTT may now route turns to the hub
    let replayedReconnectTurn = reconnectAudioBuffer != nil
    let replayedReplacementTurn = replacementAudioBuffer != nil
    if replayedReplacementTurn {
      finishBargeInReplacementAfterSessionReady()
    }
    if replayedReconnectTurn {
      finishSessionReconnectAfterReady()
    }
    if let turnID = VoiceTurnCoordinator.shared.activeTurnID, let voiceSessionID,
      VoiceTurnCoordinator.shared.activeTurn?.route == .hubWarmWait
    {
      VoiceTurnCoordinator.shared.publish(.hubReady(turnID: turnID, sessionID: voiceSessionID))
    }
    log("RealtimeHub: connected (\(sessionProvider?.displayName ?? "?"))")
    if let fallback = fallbackProvider, let reason = pendingFailoverReason,
      sessionProvider == fallback
    {
      let primary = RealtimeHubSettings.shared.provider
      DesktopDiagnosticsManager.shared.recordFallback(
        area: "realtime_hub",
        from: primary.rawValue,
        to: fallback.rawValue,
        reason: reason,
        outcome: .recovered,
        extra: ["user_visible": false])
      pendingFailoverReason = nil
    }
    // Transport readiness has no authority to open provider input. Reconnect
    // and replacement replay paths above require an exact context admission;
    // an ordinary warm connection waits for prepareHubInput -> beginTurn.
    applyPendingSessionRefreshIfIdle()
  }

  func hubDidReceiveInputTranscript(
    _ text: String,
    isFinal: Bool,
    identity: RealtimeHubEventIdentity?,
    source: RealtimeHubSession
  ) {
    guard acceptsTurnEvent(identity, source: source) else { return }
    let automationSelection = RealtimeAutomationTranscriptOverridePolicy.select(
      providerText: text,
      providerIsFinal: isFinal,
      forcedText: testProviderTranscriptOverride)
    if automationSelection.usedOverride {
      turnTranscript = automationSelection.text
      providerTranscriptFinalized = automationSelection.isFinal
      lastInputTranscriptUpdateAt = Date()
      return
    }
    if isFinal {
      if !text.isEmpty { turnTranscript = text }
      providerTranscriptFinalized = !turnTranscript.trimmingCharacters(
        in: .whitespacesAndNewlines
      ).isEmpty
    } else {
      turnTranscript += text
    }
    if !text.isEmpty { lastInputTranscriptUpdateAt = Date() }
    // Don't surface Gemini's LIVE partial transcript on the bar: on a quiet/near-silent
    // hold it transcribes background noise into random words (the bar shows "…" on commit
    // instead). turnTranscript is still kept for the agent-warm heuristic and the final.
    // The realtime model and kernel route intent. This transport driver never
    // performs a second text heuristic to decide whether an agent should attach.
  }

  func hubDidReceiveAudio(
    _ pcm24k: Data,
    identity: RealtimeHubEventIdentity?,
    source: RealtimeHubSession
  ) {
    guard acceptsTurnEvent(identity, source: source), let identity else { return }
    guard
      RealtimeProviderOutputPresentationPolicy.decide(
        screenGroundingState: screenGroundingState,
        reducerOutputSuppressed: VoiceTurnCoordinator.shared.outputSnapshot.providerOutputSuppressed
      ) == .present
    else { return }
    guard let lease = acquireVoiceOutput(.nativeRealtime, reason: "provider_audio") else { return }
    if let voiceSessionID {
      guard let providerIdentity = VoiceTurnCoordinator.shared.activeTurn?.providerEffectIdentity
      else { return }
      VoiceTurnCoordinator.shared.publish(
        .providerResponseStartedScoped(
          turnID: lease.turnID,
          identity: providerIdentity,
          sessionID: voiceSessionID,
          responseID: identity.responseID))
    }
    // If PTT muted music/system output while listening, make sure the model's
    // reply is audible even if capture teardown restore is delayed by hardware.
    SystemAudioMuteController.shared.restore()
    guard let pcmPlayer, pcmPlayer.enqueue(pcm24k) else {
      // The coordinator reserves the output lease before the physical enqueue.
      // Only a previously scheduled chunk means playback actually started.
      let playbackAlreadyStarted = audioReceivedThisTurn
      switch RealtimeNativeAudioScheduleFailureAction.decide(
        playbackAlreadyStarted: playbackAlreadyStarted)
      {
      case .keepTextFallback:
        log(
          "RealtimeHub[\(providerTag)]: first native audio chunk could not be scheduled; keeping text fallback armed"
        )
        DesktopDiagnosticsManager.shared.recordFallback(
          area: "realtime_hub",
          from: "native_realtime",
          to: "selected_voice_fallback",
          reason: "enqueue_failed",
          outcome: .degraded,
          extra: ["user_visible": false])
        VoiceTurnCoordinator.shared.publish(
          .playbackDrainedScoped(
            turnID: lease.turnID,
            identity: lease.identity,
            leaseID: lease.id))
      case .failTurnAfterPartialPlayback:
        log(
          "RealtimeHub[\(providerTag)]: native audio stream failed after playback started; refusing duplicate full-text fallback"
        )
        VoiceTurnCoordinator.shared.publish(
          .playbackFailedScoped(
            turnID: lease.turnID,
            identity: lease.identity,
            leaseID: lease.id,
            message: "native PCM enqueue failed"))
      }
      return
    }
    audioReceivedThisTurn = true
    realtimePlaybackEpoch = pcmPlayer.playbackEpoch
    // The reducer's drain deadline is an inactivity watchdog. Refresh it only
    // after this exact PCM chunk reached the player, so long healthy native
    // replies are not cut off at a fixed duration while a stalled stream still
    // fails closed.
    _ = VoiceTurnCoordinator.shared.noteOutputProgress(lease)
    responseGlowGate.markPlaybackActive(lease: lease)
  }

  func hubDidEmitText(
    _ text: String,
    isFinal: Bool,
    identity: RealtimeHubEventIdentity?,
    source: RealtimeHubSession
  ) {
    guard acceptsTurnEvent(identity, source: source), let identity else { return }
    guard
      RealtimeProviderOutputPresentationPolicy.decide(
        screenGroundingState: screenGroundingState,
        reducerOutputSuppressed: VoiceTurnCoordinator.shared.outputSnapshot.providerOutputSuppressed
      ) == .present
    else { return }
    if !text.isEmpty {
      assistantText += text
      if let turnID = VoiceTurnCoordinator.shared.activeTurnID,
        let providerIdentity = VoiceTurnCoordinator.shared.activeTurn?.providerEffectIdentity
      {
        VoiceTurnCoordinator.shared.publish(
          .providerResponseStartedScoped(
            turnID: turnID,
            identity: providerIdentity,
            sessionID: voiceSessionID,
            responseID: identity.responseID))
      }
    }
    if isFinal {
      let reply = assistantText.trimmingCharacters(in: .whitespacesAndNewlines)
      // Fallback only: if the model produced text but no native audio this turn,
      // speak it through the selected app voice. Normally both providers stream
      // spoken audio (played by StreamingPCMPlayer) so this stays unused.
      if !audioReceivedThisTurn, !reply.isEmpty,
        let lease = acquireVoiceOutput(.selectedVoiceFallback, reason: "text_no_native_audio")
      {
        DesktopDiagnosticsManager.shared.recordFallback(
          area: "realtime_hub",
          from: "native_realtime",
          to: "selected_voice_fallback",
          reason: "capability_mismatch",
          outcome: .degraded,
          extra: ["user_visible": false])
        responseGlowGate.markPlaybackActive(lease: lease)
        FloatingBarVoicePlaybackService.shared.speakOneShot(reply, lease: lease)
      } else if !audioReceivedThisTurn, reply.isEmpty {
        DesktopDiagnosticsManager.shared.recordFallback(
          area: "realtime_hub",
          from: "native_realtime",
          to: "none",
          reason: "capability_mismatch",
          outcome: .exhausted,
          extra: ["user_visible": true])
      }
      if !reply.isEmpty { log("RealtimeHub: reply received chars=\(reply.count)") }
    }
  }
  func hubDidRequestTool(
    name: String,
    callId: String,
    argumentsJSON: String,
    identity: RealtimeHubEventIdentity?,
    source: RealtimeHubSession
  ) {
    guard acceptsTurnEvent(identity, source: source), let eventIdentity = identity else { return }
    let toolTurnEpoch = realtimeToolTurnEpoch
    let transportKey = toolCallKey(callId: callId, name: name, turnEpoch: toolTurnEpoch)
    guard toolEffectIdentityByTransportKey[transportKey] == nil,
      let turnID = VoiceTurnCoordinator.shared.activeTurnID
    else {
      log("RealtimeHub[\(providerTag)]: dropping duplicate tool call \(name) id=\(callId)")
      return
    }
    guard let toolIdentity = VoiceTurnCoordinator.shared.reserveEffectIdentity() else { return }
    toolEffectIdentityByTransportKey[transportKey] = toolIdentity
    VoiceTurnCoordinator.shared.publish(
      .toolStartedScoped(
        turnID: turnID,
        identity: toolIdentity,
        callID: VoiceToolCallID(callId)))
    guard
      VoiceTurnCoordinator.shared.isToolEffectActive(
        turnID: turnID,
        callID: VoiceToolCallID(callId),
        identity: toolIdentity)
    else {
      toolEffectIdentityByTransportKey.removeValue(forKey: transportKey)
      log("RealtimeHub[\(providerTag)]: reducer rejected tool call \(name) id=\(callId)")
      return
    }
    if name == HubTool.screenshot.rawValue {
      admitScreenScreenshotRequest(
        source: source,
        turnID: turnID,
        responseID: eventIdentity.responseID,
        callID: callId,
        screenshotIdentity: toolIdentity,
        turnEpoch: toolTurnEpoch)
    }
    let arguments =
      (try? JSONSerialization.jsonObject(with: Data(argumentsJSON.utf8)) as? [String: Any]) ?? [:]
    if name == HubTool.reportScreenObservation.rawValue {
      handleScreenObservationReport(
        source: source,
        turnID: turnID,
        callId: callId,
        reportIdentity: toolIdentity,
        arguments: arguments,
        expectedTurnEpoch: toolTurnEpoch)
      return
    }
    invokeExternallyAuthorizedTool(
      source: source,
      turnID: turnID,
      identity: toolIdentity,
      callId: callId,
      name: name,
      arguments: arguments,
      expectedTurnEpoch: toolTurnEpoch)
  }

  func handleScreenObservationReport(
    source: RealtimeHubSession,
    turnID: VoiceTurnID,
    callId: String,
    reportIdentity: VoiceEffectIdentity,
    arguments: [String: Any],
    expectedTurnEpoch: Int
  ) {
    // `answer` is accepted only for already-warm sessions created by a prior
    // bundle. New generated schemas use `observation`, whose value is an
    // internal grounding acknowledgement rather than the user-facing answer.
    let observation = String(
      ((arguments["observation"] as? String) ?? (arguments["answer"] as? String) ?? "").prefix(1_200))
    let accepted = resolveScreenObservation(
      observation: observation,
      source: source,
      turnID: turnID,
      expectedTurnEpoch: expectedTurnEpoch,
      callID: callId,
      reportIdentity: reportIdentity)
    sendToolResultIfCurrent(
      source: source,
      callId: callId,
      name: HubTool.reportScreenObservation.rawValue,
      output: RealtimeHubTools.screenObservationResult(accepted: accepted),
      expectedTurnEpoch: expectedTurnEpoch)
  }

  @discardableResult
  func resolveScreenObservation(
    observation: String,
    source: RealtimeHubSession,
    turnID: VoiceTurnID,
    expectedTurnEpoch: Int,
    callID: String,
    reportIdentity: VoiceEffectIdentity
  ) -> Bool {
    let decision = RealtimeScreenGroundingPolicy.reportDecision(
      state: screenGroundingState,
      observation: observation,
      sourceObjectID: ObjectIdentifier(source),
      activeTurnID: turnID,
      activeResponseID: voiceResponseID,
      currentTurnEpoch: expectedTurnEpoch)
    guard decision == .accepted, case .awaitingReport(let receipt) = screenGroundingState else {
      let reason: String
      switch decision {
      case .evidenceUnavailable: reason = "evidence_unavailable"
      case .transportNotDispatched: reason = "transport_not_dispatched"
      case .staleReceipt: reason = "stale_receipt"
      case .contradictoryApplication: reason = "contradictory_application"
      case .emptyAnswer: reason = "empty_answer"
      case .accepted: reason = "evidence_state_changed"
      }
      if case .awaitingReport = screenGroundingState {
        rejectScreenEvidence(screenEvidence?.descriptor, reason: reason)
      } else {
        // A report that races ahead of the screenshot result is rejected to the provider but
        // never cached or redeemed. The original screenshot call may still complete normally.
        log("RealtimeHub: rejected screen report without a current transport receipt reason=\(reason)")
      }
      return false
    }
    screenGroundingState = .accepted(receipt)
    logScreenEvidence(stage: "report_accepted", evidence: receipt.descriptor, callID: callID)
    return acceptScreenEvidenceReport(
      receipt.protocolToken,
      reportCallID: VoiceToolCallID(callID),
      reportIdentity: reportIdentity)
      == .completed
  }

  func hubDidFinishTurn(identity: RealtimeHubEventIdentity?, source: RealtimeHubSession) {
    guard acceptsTurnEvent(identity, source: source), let identity else { return }
    hubReconnectStrikes = 0  // a completed provider cycle proves the hub works.
    if let turnID = VoiceTurnCoordinator.shared.activeTurnID {
      _ = resolvePendingScreenEvidenceBeforeProviderTermination(
        turnID: turnID,
        reason: .providerNoResponse)
    }
    let pendingToolCount = VoiceTurnCoordinator.shared.activeTurn?.pendingToolCallIDs.count ?? 0
    let postToolContinuationRequired =
      VoiceTurnCoordinator.shared.activeTurn?.postToolContinuationRequired == true
    switch RealtimeProviderTurnDoneDisposition.decide(
      pendingToolCount: pendingToolCount,
      postToolContinuationRequired: postToolContinuationRequired)
    {
    case .awaitPendingTools:
      log(
        "RealtimeHub[\(providerTag)]: provider cycle done with \(pendingToolCount) tool result(s) pending; waiting for provider tool delivery"
      )
      if let turnID = VoiceTurnCoordinator.shared.activeTurnID,
        let providerIdentity = VoiceTurnCoordinator.shared.activeTurn?.providerEffectIdentity
      {
        VoiceTurnCoordinator.shared.publish(
          .providerTurnFinishedScoped(
            turnID: turnID,
            identity: providerIdentity,
            sessionID: voiceSessionID,
            responseID: identity.responseID))
      }
      return

    case .requestPostToolContinuation:
      log(
        "RealtimeHub[\(providerTag)]: provider cycle ended after tool delivery; requesting one bounded continuation"
      )
      if let turnID = VoiceTurnCoordinator.shared.activeTurnID,
        let providerIdentity = VoiceTurnCoordinator.shared.activeTurn?.providerEffectIdentity
      {
        VoiceTurnCoordinator.shared.publish(
          .providerTurnFinishedScoped(
            turnID: turnID,
            identity: providerIdentity,
            sessionID: voiceSessionID,
            responseID: identity.responseID))
      }
      source.resumeAfterToolOnlyCycle(identity: identity) { [weak self, weak source] resumed in
        DispatchQueue.main.async {
          guard let self, let source else { return }
          self.handlePostToolContinuationStart(
            resumed,
            identity: identity,
            source: source,
            pendingToolCount: pendingToolCount)
        }
      }
      return

    case .finalizeLogicalTurn:
      break
    }
    if sessionProvider == .gemini {
      geminiSessionNeedsTurnBoundary = true
      pendingSessionRefreshReason = "voice_context_changed"
    }
    var heard = turnTranscript.trimmingCharacters(in: .whitespacesAndNewlines)
    if let forced = testProviderTranscriptOverride {
      testProviderTranscriptOverride = nil
      heard = forced
      log("RealtimeHub: TEST override provider transcript → \"\(forced.prefix(60))\"")
    }
    let providerReply = assistantText.trimmingCharacters(in: .whitespacesAndNewlines)
    let acceptedSpawnOwnerID = acceptedSpawnJournalReceiptByContinuityKey[turnIdempotencyKey]?.ownerID
    let reply =
      acceptedSpawnJournalReceiptByContinuityKey[turnIdempotencyKey]?.receipt.assistantText
      ?? providerReply
    log(
      "RealtimeHub[\(providerTag)]: turn done — transcript_chars=\(heard.count) audio=\(audioReceivedThisTurn)"
    )
    if reducerNativePlaybackActive {
      log("RealtimeHub[\(providerTag)]: server turn done; waiting for local playback to drain")
    }
    // Record the completed turn to the kernel; chat UI updates from ordered journal replay.
    if VoiceTurnCoordinator.shared.activeTurn?.journalFinalization == .pending {
      let completedTurnIdempotencyKey = turnIdempotencyKey
      guard let completedTurnOwnerID = VoiceTurnCoordinator.shared.activeTurn?.ownerID else {
        if let activeTurnID = VoiceTurnCoordinator.shared.activeTurnID {
          VoiceTurnCoordinator.shared.publish(.cancel(turnID: activeTurnID, reason: .cancelled))
        }
        return
      }
      let candidates = AssistantSettings.shared.voiceBaseLanguages
      let fullTask = fullLIDTask
      let provider = providerTag
      enqueueTurnPersistence(
        idempotencyKey: completedTurnIdempotencyKey,
        retainingReceipt: true
      ) { [weak self] in
        let resolution = await Self.resolveTranscript(
          providerText: heard,
          preferredLanguages: candidates,
          localTask: fullTask)
        if resolution.usedLocalTranscript {
          log(
            "RealtimeHub: provider transcript language did not match the configured voice languages; using bounded local decode for continuity"
          )
        }
        let accepted =
          await self?.persistTurnDirectlyToKernel(
            ownerID: completedTurnOwnerID,
            userText: resolution.userText,
            assistantText: reply,
            interrupted: false,
            idempotencyKey: completedTurnIdempotencyKey,
            acceptedSpawnOwnerID: acceptedSpawnOwnerID) ?? false
        self?.lastTurnDiagnostics = [
          "provider": provider,
          "provider_transcript": heard,
          "provider_transcript_language": resolution.providerLanguage ?? "",
          "saved_user_text": resolution.userText,
          "used_local_transcript": resolution.usedLocalTranscript ? "true" : "false",
          "local_transcript": resolution.localTranscript ?? "",
          "local_language": resolution.localLanguage ?? "",
          "assistant_reply": reply,
          "provider_assistant_reply": providerReply,
          "external_tool_name": self?.lastExternalToolName ?? "",
          "external_tool_error": self?.lastExternalToolErrorCode ?? "",
        ]
        return accepted
      }
    }
    if let turnID = VoiceTurnCoordinator.shared.activeTurnID,
      VoiceTurnCoordinator.shared.activeTurn?.providerFinished != true,
      let providerIdentity = VoiceTurnCoordinator.shared.activeTurn?.providerEffectIdentity
    {
      VoiceTurnCoordinator.shared.publish(
        .providerTurnFinishedScoped(
          turnID: turnID,
          identity: providerIdentity,
          sessionID: voiceSessionID,
          responseID: identity.responseID))
      if VoiceTurnCoordinator.shared.outputSnapshot.activeLease == nil {
        exitVoiceUI()
        applyPendingSessionRefreshIfIdle()
      }
    } else {
      exitVoiceUI()
      applyPendingSessionRefreshIfIdle()
    }
  }

  /// The session owns whether a continuation can start; the controller owns the reducer terminal
  /// transition. Recheck the original turn/session after the session queue callback so a stale
  /// recovery result cannot finish a replacement PTT turn.
  func handlePostToolContinuationStart(
    _ result: RealtimePostToolContinuationStartResult,
    identity: RealtimeHubEventIdentity,
    source: RealtimeHubSession,
    pendingToolCount: Int
  ) {
    guard acceptsTurnEvent(identity, source: source) else { return }
    let sessionProviderTag = sessionProvider?.rawValue ?? "unbound"
    let controllerAction = RealtimePostToolContinuationControllerAction.decide(result)
    switch result {
    case .started:
      DesktopDiagnosticsManager.shared.recordFallback(
        area: "realtime_hub",
        from: "\(sessionProviderTag)_tool_cycle_complete",
        to: "\(sessionProviderTag)_explicit_post_tool_continuation",
        reason: "provider_no_user_facing_output",
        outcome: .recovered,
        extra: ["pending_tool_count": pendingToolCount])
      log("RealtimeHub[\(sessionProviderTag)]: resumed after tool-only cycle")

    case .alreadyInFlight:
      log("RealtimeHub[\(sessionProviderTag)]: post-tool provider response already in flight")

    case .stale:
      guard controllerAction == .ignoreStaleCallback else { return }
      return

    case .exhausted, .transportUnavailable:
      guard controllerAction == .finishProviderNoResponse else { return }
      log("RealtimeHub[\(sessionProviderTag)]: post-tool continuation unavailable result=\(result)")
      guard let turnID = VoiceTurnCoordinator.shared.activeTurnID else { return }
      VoiceTurnCoordinator.shared.publish(.finish(turnID: turnID, reason: .providerNoResponse))
      if VoiceTurnCoordinator.shared.outputSnapshot.activeLease == nil {
        exitVoiceUI()
        applyPendingSessionRefreshIfIdle()
      }
    }
  }

  func toolCallKey(callId: String, name: String, turnEpoch: Int) -> String {
    "\(turnEpoch):\(name):\(callId)"
  }

  func isCurrentToolTurn(
    source: RealtimeHubSession,
    callId: String,
    name: String,
    expectedTurnEpoch: Int
  ) -> Bool {
    let key = toolCallKey(callId: callId, name: name, turnEpoch: expectedTurnEpoch)
    guard let identity = toolEffectIdentityByTransportKey[key]
    else { return false }
    let callID = VoiceToolCallID(callId)
    return RealtimeToolTurnOwnership.accepts(
      turnID: VoiceTurnID(identity.generation),
      identity: identity,
      sourceObjectID: ObjectIdentifier(source),
      turnEpoch: expectedTurnEpoch,
      activeTurnID: VoiceTurnCoordinator.shared.activeTurnID,
      activeToolIdentity: VoiceTurnCoordinator.shared.activeTurn?.toolEffectIdentities[callID],
      activeSourceObjectID: session.map(ObjectIdentifier.init),
      currentTurnEpoch: realtimeToolTurnEpoch)
  }

  func clearRealtimeToolTracking() {
    realtimeToolTurnEpoch += 1
    toolEffectIdentityByTransportKey.removeAll()
    authorizedRealtimeInvocations.removeAll()
    authorizedRealtimeScreenshotImages.removeAll()
    acceptedSpawnJournalReceiptByContinuityKey.removeAll()
  }

  func coordinatorOpenLoopsIsEmpty(_ raw: String) -> Bool {
    guard let data = raw.data(using: .utf8),
      let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
    else { return false }
    if let openLoops = object["openLoops"] as? [Any] { return openLoops.isEmpty }
    if let items = object["items"] as? [Any] { return items.isEmpty }
    return false
  }

  func hubDidError(_ message: String, source: RealtimeHubSession) {
    guard isCurrentSession(source) else { return }
    if reconnectAudioBuffer == nil {
      _ = beginTransportRebindForActiveInputIfNeeded()
    }
    if var pending = reconnectAudioBuffer {
      if pending.beginRebindAttempt() {
        reconnectAudioBuffer = pending
        log(
          "RealtimeHub: ptt_handoff event=rebind_attempt turn=\(pending.turnID.rawValue.uuidString) "
            + "attempt=\(pending.rebindAttempts) reason=transport_failure")
        requestSessionHandoff(
          reason: .transportFailure,
          preservingReconnectAudio: true)
        return
      }
      // The one transparent rebind has already been consumed. Clear the
      // controller buffer before handing the same logical turn to the reducer's
      // established transcription fallback; a late socket callback can no
      // longer replay audio into that fallback turn.
      reconnectAudioBuffer = nil
      VoiceTurnCoordinator.shared.publish(
        .providerReconnectFailed(
          turnID: pending.turnID,
          identity: pending.identity,
          message: "realtime provider reconnect exhausted"))
      log(
        "RealtimeHub: ptt_handoff event=fallback turn=\(pending.turnID.rawValue.uuidString) "
          + "reason=rebind_exhausted")
    }
    var resolvedScreenProtocol = false
    if let turnID = VoiceTurnCoordinator.shared.activeTurnID {
      resolvedScreenProtocol = resolvePendingScreenEvidenceBeforeProviderTermination(
        turnID: turnID,
        reason: .providerFailed)
    }
    // Capture while the reducer still owns this turn. `.providerReconnectFailed`
    // or `.finish` synchronously terminalizes it and `cancelTurn` clears the
    // transcript, so starting this obligation any later loses the just-spoken
    // user turn from the next shared-context snapshot.
    let interruptedTurnTask = captureInterruptedTurnPayloadIfNeeded()
    if let interruptedTurnTask {
      // Register the continuity obligation synchronously, before any terminal
      // reducer event below can schedule the next context refresh. Enqueuing
      // only after transcript resolution creates a TOCTOU window where the
      // next PTT turn can snapshot the journal without this failed turn.
      let failedTurnContinuityKey = turnIdempotencyKey
      _ = RealtimeProviderFailureContinuity.registerCapturedTurn(
        in: turnPersistenceLedger,
        continuityKey: failedTurnContinuityKey,
        capturedTurnTask: interruptedTurnTask
      ) { [weak self] interruptedTurn in
        await self?.persistTurnDirectlyToKernel(
          ownerID: interruptedTurn.ownerID,
          userText: interruptedTurn.userText,
          assistantText: interruptedTurn.assistantText,
          interrupted: true,
          idempotencyKey: interruptedTurn.idempotencyKey,
          acceptedSpawnOwnerID: interruptedTurn.acceptedSpawnOwnerID) ?? false
      }
    }
    // A socket we intentionally dropped is detached in teardownSession() before it's
    // released, so its death-rattle never reaches us — only the live session's errors
    // land here.
    if let reconnect = reconnectAudioBuffer {
      VoiceTurnCoordinator.shared.publish(
        .providerReconnectFailed(
          turnID: reconnect.turnID,
          identity: reconnect.identity,
          message: "realtime provider reconnect failed"))
    }
    // Re-read after the scoped reconnect failure: that event may already have
    // terminalized the turn, and the generic error tail must not finish it twice.
    let activeTurn = VoiceTurnCoordinator.shared.activeTurn
    let ownsActiveHubTurn = RealtimeHubErrorOwnership.owns(
      route: activeTurn?.route,
      activeSessionID: voiceSessionID)
    let hasActiveTurn = ownsActiveHubTurn
    let terminalToolName = lastExternalToolName.isEmpty ? "none" : lastExternalToolName
    let terminalToolErrorCode = lastExternalToolErrorCode.isEmpty ? "none" : lastExternalToolErrorCode
    let terminalHadAcceptedSpawn =
      acceptedSpawnJournalReceiptByContinuityKey[turnIdempotencyKey] != nil
    clearRealtimeToolTracking()
    let aliveFor = (hubConnected ? lastWarmAt.map { Date().timeIntervalSince($0) } : nil) ?? 0
    // Most "session error" closes are expected lifecycle events, not bugs: a socket
    // that lived past the idle window is a normal provider idle-close (Gemini ~2.5min,
    // 1008), and a client "operation was aborted"/cancellation is a teardown. Reporting
    // these to Sentry as errors created the high-volume OMI-DESKTOP-27C cluster. Keep
    // them as local logs; only capture genuine fast-fail provider errors, without raw
    // provider close text for known fast policy/auth/config rejects.
    let closeCategory = RealtimeHubCloseClassifier.category(
      message: message,
      aliveFor: aliveFor,
      hasActiveTurn: hasActiveTurn,
      provider: sessionProvider ?? .openai)
    let provider = sessionProvider
    let authMode: CredentialAuthMode = sessionAuth?.isEphemeral == true ? .managed : .byok
    let fingerprint = provider.flatMap { APIKeyService.byokKey($0.byokProvider) }.map(
      APIKeyService.byokFingerprint)
    var credentialFailureClass: CredentialFailureClass?
    if let provider, !RealtimeHubCloseClassifier.isExpectedLifecycleClose(closeCategory) {
      var failureClass = CredentialHealthManager.classifyProviderClose(
        message: message, provider: provider)
      if authMode == .managed, case .providerAuthFailed = failureClass {
        failureClass = .providerAuthFailed(provider: provider, mode: .managed)
      }
      credentialFailureClass = failureClass
      CredentialHealthManager.shared.recordProviderFailure(
        failureClass,
        provider: provider,
        authMode: authMode,
        fingerprint: fingerprint,
        context: "realtime_socket")
    }
    let categoryText = closeCategory.map { " category=\($0.rawValue)" } ?? ""
    let shouldRedactProviderMessage: Bool = {
      if closeCategory == .providerPolicyCloseFast { return true }
      if closeCategory == .expectedSessionRotation { return true }
      if case .providerAuthFailed = credentialFailureClass { return true }
      if case .providerQuotaExceeded = credentialFailureClass { return true }
      return false
    }()
    let safeMessage = shouldRedactProviderMessage ? "" : " \(message)"
    DesktopDiagnosticsManager.shared.recordRealtimeProviderClose(
      provider: providerTag,
      category: closeCategory?.rawValue,
      aliveFor: aliveFor,
      activeTurn: hasActiveTurn,
      authMode: authMode,
      failureClass: credentialFailureClass)
    if RealtimeHubCloseClassifier.shouldReportToSentry(closeCategory) {
      logError("RealtimeHub: session error —\(categoryText) provider=\(providerTag)\(safeMessage)")
    } else {
      log(
        "RealtimeHub: session closed —\(categoryText) provider=\(providerTag) aliveFor=\(Int(aliveFor))s\(safeMessage)"
      )
    }
    log(
      "RealtimeHub: provider close terminal state tool=\(terminalToolName) "
        + "tool_error=\(terminalToolErrorCode) accepted_spawn=\(terminalHadAcceptedSpawn)"
    )
    if let sessionRotationPlan = RealtimeHubCloseClassifier.sessionRotationPlan(
      for: closeCategory,
      hasActiveTurn: hasActiveTurn)
    {
      recoverFromExpectedSessionRotation(sessionRotationPlan, activeTurn: activeTurn)
      return
    }
    if replacementAudioBuffer != nil, let failedProvider = provider {
      let replacementFailoverReason = failoverReason(for: credentialFailureClass)
      let mayFailOver = credentialFailureClass.map { shouldFailoverToAlternate(for: $0) } ?? true
      if mayFailOver,
        failoverBargeInReplacement(
          from: failedProvider,
          reason: replacementFailoverReason)
      {
        return
      }
      failBargeInReplacement(provider: failedProvider, reason: message)
      teardownSession()
      return
    }
    if ownsActiveHubTurn, !resolvedScreenProtocol, activeTurn?.providerFinished != true {
      terminateActiveHubTurn(activeTurn)
    }
    teardownSession()
    // Provider switching changes the user's voice identity and can fragment model-local
    // context. Only switch for stable credential/quota classes; transient fast closes
    // re-warm the same provider and rely on the shared continuity packet.
    if case .providerAuthFailed = credentialFailureClass {
      if aliveFor < 10, failoverToAlternateProvider(reason: "auth") { return }
      return
    }
    if case .providerQuotaExceeded = credentialFailureClass {
      if failoverToAlternateProvider(reason: "quota") { return }
      return
    }
    // Re-warm so the NEXT PTT uses the hub, not the STT cascade. Gemini idle-closes
    // the socket (~2.5 min, close 1008) even before the first turn; managed users have
    // no BYOK key, so once `session` is nil `isActive` is false and PTT silently falls
    // back to omni STT. So always try to re-warm (the hub is the default voice path).
    // A socket that survived past the idle window was a normal idle-close → reset the
    // strike budget (and the failover, returning to the Auto pick) and keep re-warming.
    if aliveFor > 60 {
      hubReconnectStrikes = 0
      fallbackProvider = nil
      pendingFailoverReason = nil
    }
    guard !reconnectPending, hubReconnectStrikes < Self.maxReconnectStrikes else { return }
    hubReconnectStrikes += 1
    reconnectPending = true
    let reconnectOwnerBoundaryGeneration = ownerBoundaryGeneration
    Task { @MainActor [weak self] in
      try? await Task.sleep(nanoseconds: 1_500_000_000)
      guard !Task.isCancelled, let self else { return }
      guard self.ownerBoundaryGeneration == reconnectOwnerBoundaryGeneration else { return }
      self.reconnectPending = false
      if self.session == nil { self.ensureWarm() }
    }
  }

  /// OpenAI limits realtime sessions to sixty minutes. Rotation is a normal
  /// transport lifecycle event: keep the provider choice, replace the retired
  /// socket immediately, and let the reducer terminalize an interrupted turn.
  func recoverFromExpectedSessionRotation(
    _ plan: RealtimeHubSessionRotationPlan,
    activeTurn: VoiceTurn?
  ) {
    if plan == .terminateActiveTurnAndRewarm {
      terminateActiveHubTurn(activeTurn)
    }
    teardownSession()
    hubReconnectStrikes = 0
    reconnectPending = false
    ensureWarm()
  }

  /// A warm background socket must never terminate a Deepgram/Omni fallback
  /// turn. The reducer deduplicates repeated terminal events, keeping the UI in
  /// a single actionable terminal projection when transport callbacks race.
  func terminateActiveHubTurn(_ activeTurn: VoiceTurn?) {
    pcmPlayer?.stop()
    realtimePlaybackEpoch += 1
    FloatingBarVoicePlaybackService.shared.interruptCurrentResponse()
    if let turnID = activeTurn?.id {
      VoiceTurnCoordinator.shared.publish(.finish(turnID: turnID, reason: .providerFailed))
    }
    exitVoiceUI(clearResponseGlow: true)
  }

  /// Return the floating bar from its PTT voice state to compact after a hub turn.
  func exitVoiceUI(clearResponseGlow: Bool = false) {
    if clearResponseGlow
      || (!audioReceivedThisTurn && !FloatingBarVoicePlaybackService.shared.isSpeaking)
    {
      responseGlowGate.clearImmediately()
    }
    VoiceTurnCoordinator.shared.refreshPresentation()
  }

  func clearResponseGlowIfRealtimeAudioIdle() {
    responseGlowGate.scheduleIdleClear()
  }

}
