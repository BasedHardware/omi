import XCTest

@testable import Omi_Computer

private actor SuspendedTurnPersistenceGate {
  private var suspendedKeys = Set<String>()
  private var suspensionWaiters: [String: [CheckedContinuation<Void, Never>]] = [:]
  private var resultContinuations: [String: CheckedContinuation<Bool, Never>] = [:]

  func persist(continuityKey: String) async -> Bool {
    await withCheckedContinuation { continuation in
      resultContinuations[continuityKey] = continuation
      suspendedKeys.insert(continuityKey)
      let waiters = suspensionWaiters.removeValue(forKey: continuityKey) ?? []
      for waiter in waiters { waiter.resume() }
    }
  }

  func waitUntilSuspended(continuityKey: String) async {
    guard !suspendedKeys.contains(continuityKey) else { return }
    await withCheckedContinuation { continuation in
      suspensionWaiters[continuityKey, default: []].append(continuation)
    }
  }

  func accept(continuityKey: String) -> Bool {
    guard let continuation = resultContinuations.removeValue(forKey: continuityKey) else {
      return false
    }
    continuation.resume(returning: true)
    return true
  }
}

@MainActor
final class RealtimeHubBargeInContinuityTests: XCTestCase {
  func testProviderFailureRegistersContinuityFenceBeforeTranscriptResolution() async {
    let ledger = RealtimeTurnPersistenceLedger()
    let gate = SuspendedTurnPersistenceGate()
    let payload = InterruptedTurnPayload(
      ownerID: "owner-a",
      userText: "request screen recording permission",
      assistantText: "I can help with that",
      idempotencyKey: "voice:failure-fence")
    let capturedTurnTask = Task<InterruptedTurnPayload?, Never> { payload }

    let persistence = RealtimeProviderFailureContinuity.registerCapturedTurn(
      in: ledger,
      continuityKey: payload.idempotencyKey,
      capturedTurnTask: capturedTurnTask
    ) { captured in
      await gate.persist(continuityKey: captured.idempotencyKey)
    }

    XCTAssertEqual(
      ledger.pendingContinuityKeys,
      [payload.idempotencyKey],
      "the next PTT context refresh must see the obligation before async resolution starts")

    await gate.waitUntilSuspended(continuityKey: payload.idempotencyKey)
    let accepted = await gate.accept(continuityKey: payload.idempotencyKey)
    let persisted = await persistence.value
    XCTAssertTrue(accepted)
    XCTAssertTrue(persisted)
    XCTAssertTrue(ledger.pendingContinuityKeys.isEmpty)
  }

  func testProviderFailurePersistsCapturedTurnBeforeTerminalCleanup() async {
    let payload = InterruptedTurnPayload(
      ownerID: "owner-a",
      userText: "request screen recording permission",
      assistantText: "I can help with that",
      idempotencyKey: "voice:failure-a")
    var events: [String] = []

    let accepted = await RealtimeProviderFailureContinuity.persistCapturedTurn(
      resolve: {
        events.append("resolved-before-cleanup")
        return payload
      },
      record: { captured in
        events.append("recorded:\(captured.idempotencyKey)")
        return true
      })

    XCTAssertTrue(accepted)
    XCTAssertEqual(events, ["resolved-before-cleanup", "recorded:voice:failure-a"])
  }

  func testTurnPersistenceLedgerKeepsConcurrentContinuityObligationsIndependent() async {
    let ledger = RealtimeTurnPersistenceLedger()
    let gate = SuspendedTurnPersistenceGate()

    let first = ledger.enqueue(continuityKey: "voice:a", retainingReceipt: true) {
      await gate.persist(continuityKey: "voice:a")
    }
    await gate.waitUntilSuspended(continuityKey: "voice:a")

    let second = ledger.enqueue(continuityKey: "voice:b", retainingReceipt: true) {
      await gate.persist(continuityKey: "voice:b")
    }
    XCTAssertEqual(ledger.pendingContinuityKeys, ["voice:a", "voice:b"])

    let acceptedA = await gate.accept(continuityKey: "voice:a")
    let firstResult = await first.value
    XCTAssertTrue(acceptedA)
    XCTAssertTrue(firstResult, "B must not invalidate A's successful kernel receipt")
    XCTAssertEqual(ledger.pendingContinuityKeys, ["voice:b"])
    XCTAssertEqual(
      ledger.receipt(for: "voice:a"),
      .init(continuityKey: "voice:a", accepted: true))

    await gate.waitUntilSuspended(continuityKey: "voice:b")
    let acceptedB = await gate.accept(continuityKey: "voice:b")
    let secondResult = await second.value
    XCTAssertTrue(acceptedB)
    XCTAssertTrue(secondResult)
    XCTAssertTrue(ledger.pendingContinuityKeys.isEmpty)
    XCTAssertEqual(
      ledger.receipt(for: "voice:b"),
      .init(continuityKey: "voice:b", accepted: true))
  }

  func testAcceptedSpawnOwnsJournalAndProviderCompletionMakesNoSecondMutation() async {
    var refreshCount = 0
    var mutationCount = 0

    let accepted = await RealtimeTurnJournalAuthority.persist(
      turnOwnerID: "owner-a",
      acceptedSpawnOwnerID: "owner-a",
      refreshAcceptedSpawn: {
        refreshCount += 1
        return true
      },
      recordProviderExchange: {
        mutationCount += 1
        return true
      })

    XCTAssertTrue(accepted)
    XCTAssertEqual(refreshCount, 1)
    XCTAssertEqual(
      mutationCount, 0,
      "provider turn_done must not write after spawn admission recorded the canonical exchange")
  }

  func testBargedTurnRetainsSpawnJournalAuthorityAfterTransportTrackingClears() async {
    let interrupted = InterruptedTurnPayload(
      ownerID: "owner-a",
      userText: "ask a subagent to check the release",
      assistantText: "Starting a background agent now",
      idempotencyKey: "voice:spawn-barged",
      acceptedSpawnOwnerID: "owner-a")
    var refreshCount = 0
    var mutationCount = 0

    let accepted = await RealtimeProviderFailureContinuity.persistCapturedTurn(
      resolve: { interrupted },
      record: { captured in
        await RealtimeTurnJournalAuthority.persist(
          turnOwnerID: captured.ownerID,
          acceptedSpawnOwnerID: captured.acceptedSpawnOwnerID,
          refreshAcceptedSpawn: {
            refreshCount += 1
            return true
          },
          recordProviderExchange: {
            mutationCount += 1
            return true
          })
      })

    XCTAssertTrue(accepted)
    XCTAssertEqual(refreshCount, 1)
    XCTAssertEqual(
      mutationCount, 0,
      "a barge-in must retain the accepted spawn receipt rather than append a second provider exchange")
  }

  func testProviderCompletionRecordsWhenNoSpawnReceiptOwnsTheExchange() async {
    var mutationCount = 0

    let accepted = await RealtimeTurnJournalAuthority.persist(
      turnOwnerID: "owner-a",
      acceptedSpawnOwnerID: nil,
      refreshAcceptedSpawn: { XCTFail("no spawn receipt exists"); return false },
      recordProviderExchange: {
        mutationCount += 1
        return true
      })

    XCTAssertTrue(accepted)
    XCTAssertEqual(mutationCount, 1)
  }

  func testTransportReadyCannotAdmitInputWithoutExactContextBinding() {
    let turnID = VoiceTurnID()
    let responseID = VoiceResponseID("response-a")
    let identity = VoiceEffectIdentity(turnID: turnID, effectID: 1)
    var pending = RealtimeReconnectAudioBuffer(
      turnID: turnID,
      responseID: responseID,
      identity: identity,
      interrupting: false)

    XCTAssertEqual(
      RealtimeInputAdmissionPolicy.decide(
        pending: pending,
        activeTurnID: turnID,
        sessionContextFreshnessIdentity: "seed-a"),
      .rejectMissingContextIdentity)

    XCTAssertTrue(pending.bindRequiredContextFreshnessIdentity("seed-a"))
    XCTAssertEqual(
      RealtimeInputAdmissionPolicy.decide(
        pending: pending,
        activeTurnID: VoiceTurnID(),
        sessionContextFreshnessIdentity: "seed-a"),
      .rejectSupersededTurn)
    XCTAssertEqual(
      RealtimeInputAdmissionPolicy.decide(
        pending: pending,
        activeTurnID: turnID,
        sessionContextFreshnessIdentity: "seed-b"),
      .rejectStaleProviderContext)
    XCTAssertEqual(
      RealtimeInputAdmissionPolicy.decide(
        pending: pending,
        activeTurnID: turnID,
        sessionContextFreshnessIdentity: "seed-a"),
      .admit)
  }

  func testProviderCycleWithToolsCannotFinalizeLogicalTurn() {
    XCTAssertEqual(
      RealtimeProviderTurnDoneDisposition.decide(
        pendingToolCount: 2, postToolContinuationRequired: true),
      .awaitToolContinuation)
    XCTAssertEqual(
      RealtimeProviderTurnDoneDisposition.decide(
        pendingToolCount: 1, postToolContinuationRequired: true),
      .awaitToolContinuation)
    XCTAssertEqual(
      RealtimeProviderTurnDoneDisposition.decide(
        pendingToolCount: 0, postToolContinuationRequired: true),
      .awaitToolContinuation)
    XCTAssertEqual(
      RealtimeProviderTurnDoneDisposition.decide(
        pendingToolCount: 0, postToolContinuationRequired: false),
      .finalizeLogicalTurn)
  }

  func testSecondBargeInTurnExecutesAuthorizedToolWithoutFinalTranscriptAndFencesOldTurn() throws {
    let fallback = try XCTUnwrap(
      RealtimeExternalRunPromptPolicy.promptForAuthorizedTool(
        transcript: "",
        isFinal: false))
    XCTAssertEqual(fallback.source, .authorizedToolFallback)
    XCTAssertTrue(fallback.prompt.contains("already authorized one tool invocation"))
    XCTAssertTrue(fallback.prompt.contains("Do not infer, expand"))

    let finalTranscript = try XCTUnwrap(
      RealtimeExternalRunPromptPolicy.promptForAuthorizedTool(
        transcript: "  ask a subagent to check the latest models  ",
        isFinal: true))
    XCTAssertEqual(finalTranscript.source, .finalizedTranscript)
    XCTAssertEqual(finalTranscript.prompt, "ask a subagent to check the latest models")

    let partialPermissionTranscript = RealtimeExternalRunPromptPolicy.promptForAuthorizedTool(
      transcript: "Can you check Slack's screen share permission?",
      isFinal: false,
      toolName: "check_permission_status",
      arguments: ["type": "screen_share"])
    XCTAssertEqual(partialPermissionTranscript?.source, .partialTranscript)
    XCTAssertEqual(
      partialPermissionTranscript?.prompt,
      "Can you check Slack's screen share permission?",
      "A pre-final permission tool must retain the spoken target for the shared policy to reject external apps.")

    XCTAssertNil(
      RealtimeExternalRunPromptPolicy.promptForAuthorizedTool(
        transcript: "",
        isFinal: false,
        toolName: "request_permission",
        arguments: ["type": "screen_recording"]),
      "Permission tools must fail closed rather than deriving authority from type-only provider arguments.")

    let requestStartedAt = Date(timeIntervalSinceReferenceDate: 100)
    XCTAssertEqual(
      RealtimePermissionTranscriptSettlementPolicy.decision(
        toolName: "request_permission",
        transcriptIsFinal: false,
        hasTranscript: false,
        lastTranscriptUpdate: nil,
        requestStartedAt: requestStartedAt,
        now: requestStartedAt),
      .wait(RealtimePermissionTranscriptSettlementPolicy.maximumWait))
    XCTAssertEqual(
      RealtimePermissionTranscriptSettlementPolicy.decision(
        toolName: "request_permission",
        transcriptIsFinal: false,
        hasTranscript: true,
        lastTranscriptUpdate: requestStartedAt,
        requestStartedAt: requestStartedAt,
        now: requestStartedAt.addingTimeInterval(
          RealtimePermissionTranscriptSettlementPolicy.maximumWait)),
      .execute,
      "Gemini's settled live transcript remains usable after the bounded collection window.")
    XCTAssertEqual(
      RealtimePermissionTranscriptSettlementPolicy.decision(
        toolName: "request_permission",
        transcriptIsFinal: false,
        hasTranscript: false,
        lastTranscriptUpdate: nil,
        requestStartedAt: requestStartedAt,
        now: requestStartedAt.addingTimeInterval(
          RealtimePermissionTranscriptSettlementPolicy.maximumWait)),
      .reject,
      "A missing transcript must never be turned into a type-only permission request.")
    XCTAssertEqual(
      RealtimePermissionTranscriptSettlementPolicy.decision(
        toolName: "request_permission",
        transcriptIsFinal: false,
        hasTranscript: true,
        lastTranscriptUpdate: requestStartedAt.addingTimeInterval(
          RealtimePermissionTranscriptSettlementPolicy.maximumWait - 0.1),
        requestStartedAt: requestStartedAt,
        now: requestStartedAt.addingTimeInterval(
          RealtimePermissionTranscriptSettlementPolicy.maximumWait)),
      .reject,
      "A transcript that is still changing at the deadline must not lose a late external-app target.")

    let oldTurnID = VoiceTurnID()
    let newTurnID = VoiceTurnID()
    let identity = VoiceEffectIdentity(turnID: oldTurnID, effectID: 7)
    let source = NSObject()
    XCTAssertTrue(
      RealtimeToolTurnOwnership.accepts(
        turnID: oldTurnID,
        identity: identity,
        sourceObjectID: ObjectIdentifier(source),
        turnEpoch: 3,
        activeTurnID: oldTurnID,
        activeToolIdentity: identity,
        activeSourceObjectID: ObjectIdentifier(source),
        currentTurnEpoch: 3))
    XCTAssertFalse(
      RealtimeToolTurnOwnership.accepts(
        turnID: oldTurnID,
        identity: identity,
        sourceObjectID: ObjectIdentifier(source),
        turnEpoch: 3,
        activeTurnID: newTurnID,
        activeToolIdentity: nil,
        activeSourceObjectID: ObjectIdentifier(source),
        currentTurnEpoch: 4))
  }

  func testHeadlessPTTAuthorizationUsesExactInjectedTranscriptOverProviderArtifact() {
    let selection = RealtimeAutomationTranscriptOverridePolicy.select(
      providerText: "¿Qué es el número de serie?",
      providerIsFinal: true,
      forcedText: "Request it now.")

    XCTAssertEqual(selection.text, "Request it now.")
    XCTAssertTrue(selection.isFinal)
    XCTAssertTrue(selection.usedOverride)

    let productionSelection = RealtimeAutomationTranscriptOverridePolicy.select(
      providerText: "Request Omi's Screen Recording permission.",
      providerIsFinal: true,
      forcedText: nil)
    XCTAssertEqual(
      productionSelection,
      .init(
        text: "Request Omi's Screen Recording permission.",
        isFinal: true,
        usedOverride: false))
  }

  func testCompletedProviderCallReplayCannotExecutePhysicalToolTwice() {
    let turnID = VoiceTurnID()
    let invocationID = RealtimeExternalToolInvocationIdentity.make(
      turnID: turnID,
      providerCallID: "provider-call-7",
      toolName: "point_click")
    XCTAssertEqual(
      invocationID,
      RealtimeExternalToolInvocationIdentity.make(
        turnID: turnID,
        providerCallID: "provider-call-7",
        toolName: "point_click"))
    XCTAssertNotEqual(
      invocationID,
      RealtimeExternalToolInvocationIdentity.make(
        turnID: turnID,
        providerCallID: "provider-call-8",
        toolName: "point_click"))

    var completed: Set<String> = []
    var physicalExecutionCount = 0
    for _ in 0..<2 {
      guard RealtimeAuthorizedInvocationReplayGate.shouldExecute(
        invocationID: invocationID,
        completedInvocationIDs: completed)
      else { continue }
      completed.insert(invocationID)
      physicalExecutionCount += 1
    }
    XCTAssertEqual(physicalExecutionCount, 1)
  }

  func testProviderEventIdentityCannotCrossTurnOrResponseBoundary() {
    let turnA = VoiceTurnID()
    let turnB = VoiceTurnID()
    let responseA = VoiceResponseID("response-a")
    let responseB = VoiceResponseID("response-b")
    let eventA = RealtimeHubEventIdentity(turnID: turnA, responseID: responseA)

    XCTAssertTrue(
      RealtimeHubEventOwnership.accepts(
        eventA, activeTurnID: turnA, activeResponseID: responseA))
    XCTAssertFalse(
      RealtimeHubEventOwnership.accepts(
        eventA, activeTurnID: turnB, activeResponseID: responseA))
    XCTAssertFalse(
      RealtimeHubEventOwnership.accepts(
        eventA, activeTurnID: turnA, activeResponseID: responseB))
    XCTAssertFalse(
      RealtimeHubEventOwnership.accepts(
        nil, activeTurnID: turnA, activeResponseID: responseA))
  }

  func testContextFreshReconnectKeepsBufferedResponseIdentityForFreshSocket() {
    let turnID = VoiceTurnID()
    let responseID = VoiceResponseID("context-reconnect-response")
    let pendingReconnect = RealtimeReconnectAudioBuffer(
      turnID: turnID,
      responseID: responseID,
      identity: VoiceEffectIdentity(turnID: turnID, effectID: 1),
      interrupting: false)

    let retainedResponseID = RealtimeHubReconnectIdentityPolicy.responseIDAfterSessionDetach(
      preservingReconnectAudio: true,
      pendingReconnect: pendingReconnect)
    XCTAssertEqual(retainedResponseID, responseID)
    XCTAssertTrue(
      RealtimeHubEventOwnership.accepts(
        RealtimeHubEventIdentity(turnID: turnID, responseID: responseID),
        activeTurnID: turnID,
        activeResponseID: retainedResponseID))
    XCTAssertFalse(
      RealtimeHubEventOwnership.accepts(
        RealtimeHubEventIdentity(turnID: turnID, responseID: VoiceResponseID("stale-response")),
        activeTurnID: turnID,
        activeResponseID: retainedResponseID))

    XCTAssertNil(
      RealtimeHubReconnectIdentityPolicy.responseIDAfterSessionDetach(
        preservingReconnectAudio: false,
        pendingReconnect: pendingReconnect))
    XCTAssertNil(
      RealtimeHubReconnectIdentityPolicy.responseIDAfterSessionDetach(
        preservingReconnectAudio: true,
        pendingReconnect: nil))
  }

  func testGeminiInputTranscriptCannotCrossCompletedTurnBoundary() {
    let turnA = RealtimeHubEventIdentity(
      turnID: VoiceTurnID(), responseID: VoiceResponseID("response-a"))
    let turnB = RealtimeHubEventIdentity(
      turnID: VoiceTurnID(), responseID: VoiceResponseID("response-b"))

    XCTAssertEqual(
      GeminiRealtimeEventOwnership.inputIdentity(active: turnA, completed: nil),
      turnA)
    XCTAssertEqual(
      GeminiRealtimeEventOwnership.inputIdentity(active: turnA, completed: turnA),
      turnA)
    XCTAssertEqual(
      GeminiRealtimeEventOwnership.inputIdentity(active: nil, completed: turnA),
      turnA)
    XCTAssertNil(
      GeminiRealtimeEventOwnership.inputIdentity(active: turnB, completed: turnA))
  }

  func testGeminiReplacementAudioBufferIsBounded() {
    let turnID = VoiceTurnID()
    var pending = RealtimeReplacementAudioBuffer(
      turnID: turnID,
      responseID: VoiceResponseID("pending"),
      identity: VoiceEffectIdentity(turnID: turnID, effectID: 1))
    let first = Data(repeating: 1, count: RealtimeReplacementAudioBuffer.maxBufferedAudioBytes - 8)

    XCTAssertTrue(pending.appendAudio(first))
    XCTAssertFalse(pending.appendAudio(Data(repeating: 2, count: 16)))
    XCTAssertEqual(
      pending.bufferedAudioBytes,
      RealtimeReplacementAudioBuffer.maxBufferedAudioBytes)
    XCTAssertFalse(pending.appendAudio(Data([3])))
    XCTAssertEqual(
      pending.audioBuffer.reduce(0) { $0 + $1.count },
      RealtimeReplacementAudioBuffer.maxBufferedAudioBytes)
  }

  func testNoSessionReconnectBuffersAudioInOrderUntilCommit() throws {
    let turnID = VoiceTurnID()
    let responseID = VoiceResponseID("reconnect")
    var pending = RealtimeReconnectAudioBuffer(
      turnID: turnID,
      responseID: responseID,
      identity: VoiceEffectIdentity(turnID: turnID, effectID: 2),
      interrupting: false)
    let firstChunk = Data([1, 2])
    let secondChunk = Data([3, 4])

    XCTAssertTrue(pending.appendAudio(firstChunk))
    XCTAssertTrue(pending.appendAudio(secondChunk))

    XCTAssertEqual(pending.turnID, turnID)
    XCTAssertEqual(pending.responseID, responseID)
    XCTAssertEqual(pending.audioBuffer, [firstChunk, secondChunk])

    let source = try realtimeHubControllerSource()
    XCTAssertTrue(source.contains("private var reconnectAudioBuffer: RealtimeReconnectAudioBuffer?"))
    XCTAssertTrue(source.contains("finishSessionReconnectAfterReady()"))
    XCTAssertTrue(source.contains("for pcm16k in pending.audioBuffer"))
    XCTAssertTrue(source.contains("return .deferredForReconnect"))
  }

  func testRapidBargeInCannotCoalesceReconnectAudioAcrossTurns() {
    let firstTurnID = VoiceTurnID()
    let replacementTurnID = VoiceTurnID()
    var firstTurn = RealtimeReconnectAudioBuffer(
      turnID: firstTurnID,
      responseID: VoiceResponseID("first"),
      identity: VoiceEffectIdentity(turnID: firstTurnID, effectID: 1),
      interrupting: false)
    var replacementTurn = RealtimeReplacementAudioBuffer(
      turnID: replacementTurnID,
      responseID: VoiceResponseID("replacement"),
      identity: VoiceEffectIdentity(turnID: replacementTurnID, effectID: 1))

    XCTAssertTrue(firstTurn.appendAudio(Data([1, 2])))
    XCTAssertTrue(replacementTurn.appendAudio(Data([3, 4])))

    XCTAssertNotEqual(firstTurn.turnID, replacementTurn.turnID)
    XCTAssertEqual(firstTurn.audioBuffer, [Data([1, 2])])
    XCTAssertEqual(replacementTurn.audioBuffer, [Data([3, 4])])
  }

  func testAudioIngressClosesAtCommitAndCannotRebindToNextTurn() {
    let turnA = VoiceTurnID()
    let turnB = VoiceTurnID()

    XCTAssertTrue(
      VoiceAudioIngressOwnership.accepts(
        turnID: turnA, activeTurnID: turnA, capturingInput: true))
    XCTAssertFalse(
      VoiceAudioIngressOwnership.accepts(
        turnID: turnA, activeTurnID: turnA, capturingInput: false))
    XCTAssertFalse(
      VoiceAudioIngressOwnership.accepts(
        turnID: turnA, activeTurnID: turnB, capturingInput: true))
  }

  func testWarmHubErrorCannotTerminateFallbackRoute() {
    let sessionID = VoiceSessionID()

    XCTAssertTrue(
      RealtimeHubErrorOwnership.owns(
        route: .hub(sessionID: sessionID), activeSessionID: sessionID))
    XCTAssertFalse(
      RealtimeHubErrorOwnership.owns(
        route: .hub(sessionID: VoiceSessionID()), activeSessionID: sessionID))
    XCTAssertFalse(
      RealtimeHubErrorOwnership.owns(
        route: .deepgramBatch, activeSessionID: sessionID))
    XCTAssertFalse(
      RealtimeHubErrorOwnership.owns(
        route: .omniSTT, activeSessionID: sessionID))
  }

  func testProviderSpecificBargeInPlanIsDeterministic() {
    XCTAssertEqual(
      RealtimeHubBargeInAction.decide(
        providerResponseInFlight: true,
        playbackActive: true,
        strategy: .inSessionCancel),
      .cancelInSession)
    XCTAssertEqual(
      RealtimeHubBargeInAction.decide(
        providerResponseInFlight: true,
        playbackActive: true,
        strategy: .freshSession),
      .replaceSession)
    XCTAssertEqual(
      RealtimeHubBargeInAction.decide(
        providerResponseInFlight: false,
        playbackActive: true,
        strategy: .inSessionCancel),
      .stopPlaybackTail)
    XCTAssertEqual(
      RealtimeHubBargeInAction.decide(
        providerResponseInFlight: false,
        playbackActive: false,
        strategy: .freshSession),
      .none)
  }

  func testStaticCommitAndKernelJournalBoundariesStayOrdered() throws {
    let source = try realtimeHubControllerSource()
    let physicalCommit = try XCTUnwrap(source.range(of: "func commitClaimedHubInput(turnID: VoiceTurnID)"))
    let tail = source[physicalCommit.lowerBound...]
    let cancel = try XCTUnwrap(tail.range(of: "turnPreparationTask?.cancel()"))
    let close = try XCTUnwrap(tail.range(of: "s.commitInputTurn()"))

    XCTAssertLessThan(cancel.lowerBound, close.lowerBound)
    XCTAssertTrue(source.contains("contextFreshInputPreparationIsCurrent("))
    XCTAssertTrue(source.contains("pendingSessionRefreshReason = \"voice_context_changed\""))
    XCTAssertTrue(source.contains("beginContextFreshInputPreparation("))
    XCTAssertTrue(source.contains("finishContextFreshInputOnCurrentSession()"))
    XCTAssertTrue(source.contains("preservingReconnectAudio: true"))
    XCTAssertTrue(source.contains("replacementReason: \"voice_context_changed\""))
    XCTAssertTrue(source.contains("await turnPersistenceLedger.awaitPendingObligations()"))
    XCTAssertTrue(source.contains("await self.refreshVoiceContextSnapshot()"))
    XCTAssertTrue(source.contains("applying deferred voice context refresh after turn persistence"))
    XCTAssertTrue(source.contains("let observedTurnEpoch = turnEpoch"))
    XCTAssertTrue(source.contains("let observedPersistenceGeneration = turnPersistenceLedger.generation"))
    XCTAssertTrue(source.contains("observedTurnEpoch == turnEpoch"))
    XCTAssertTrue(source.contains("observedPersistenceGeneration == turnPersistenceLedger.generation"))
    XCTAssertTrue(source.contains("RealtimeTurnPersistenceLedger"))
    XCTAssertTrue(source.contains("self.obligations[continuityKey]?.id == obligationID"))
    XCTAssertFalse(source.contains("turnPersistenceTask"))
    XCTAssertFalse(source.contains("turnPersistenceGeneration"))
    XCTAssertTrue(source.contains("enqueueTurnPersistence(idempotencyKey:"))
    XCTAssertTrue(source.contains("persistTurnDirectlyToKernel"))
    XCTAssertTrue(source.contains("try? await Task.sleep(nanoseconds: 250_000_000)"))
    XCTAssertFalse(source.contains("RealtimeVoiceTurnOutbox"))
    XCTAssertFalse(source.contains("scheduleVoiceTurnOutboxDrain"))
    XCTAssertTrue(source.contains("importLegacyVoiceJournalIfNeeded"))
    XCTAssertTrue(source.contains("kernelVoiceContextSnapshot()"))
    XCTAssertFalse(source.contains("stageRealtimeVoiceTurn("))
    XCTAssertTrue(source.contains("await self.awaitTurnPersistenceFence()"))
    XCTAssertTrue(source.contains("let interruptedContinuityTask = bargeInContinuityTask"))
    XCTAssertTrue(source.contains("await interruptedContinuityTask.value"))
    XCTAssertTrue(source.contains("pendingSessionRefreshReason = \"voice_context_changed\""))
    XCTAssertTrue(source.contains("cancelContinuityFenceActive = true"))
    XCTAssertTrue(source.contains("self.cancelContinuityFenceActive = false"))
    XCTAssertTrue(source.contains("general warm deferred behind canceled-turn continuity fence"))
    XCTAssertTrue(source.contains("session start rejected behind canceled-turn continuity fence"))
  }

  func testCancelKeepsReconnectFenceThroughEveryPersistencePathAndContextRefresh() throws {
    let source = try realtimeHubControllerSource()
    let cancel = try XCTUnwrap(
      source.range(of: "func cancelTurn(turnID requestedTurnID: VoiceTurnID) -> Bool"))
    let cancelTail = source[cancel.lowerBound...]
    let preparationWait = try XCTUnwrap(
      cancelTail.range(of: "await canceledPreparationTask.value"))
    let continuityWait = try XCTUnwrap(
      cancelTail.range(of: "await interruptedContinuityTask.value"))
    let persistenceFence = try XCTUnwrap(
      cancelTail.range(of: "await self.refreshVoiceContextAfterPersistenceFence("))
    let fenceRelease = try XCTUnwrap(
      cancelTail.range(of: "self.cancelContinuityFenceActive = false"))

    XCTAssertLessThan(preparationWait.lowerBound, continuityWait.lowerBound)
    XCTAssertLessThan(continuityWait.lowerBound, persistenceFence.lowerBound)
    XCTAssertLessThan(persistenceFence.lowerBound, fenceRelease.lowerBound)

    let helper = try XCTUnwrap(
      source.range(
        of: "private func refreshVoiceContextAfterPersistenceFence(reason: String) async -> Bool"))
    let helperTail = source[helper.lowerBound...]
    let ordinaryPersistenceWait = try XCTUnwrap(
      helperTail.range(of: "await turnPersistenceLedger.awaitPendingObligations()"))
    let contextRefresh = try XCTUnwrap(helperTail.range(of: "await refreshVoiceContextSnapshot()"))
    XCTAssertLessThan(ordinaryPersistenceWait.lowerBound, contextRefresh.lowerBound)

    XCTAssertTrue(source.contains("private var voiceContextRefreshGeneration: UInt64 = 0"))
    XCTAssertTrue(source.contains("voiceContextRefreshGeneration == refreshGeneration"))
    XCTAssertTrue(
      source.contains(
        "resolvedSnapshot = try await FloatingControlBarManager.shared.kernelVoiceContextSnapshot()"))
    XCTAssertTrue(source.contains("prefetchedVoiceContext = resolvedSnapshot.context"))
    XCTAssertTrue(source.contains("prefetchedVoiceContextFreshnessIdentity = resolvedSnapshot.freshnessIdentity"))
    XCTAssertTrue(source.contains("guard resolvedSnapshot.isResolved else"))
    XCTAssertTrue(source.contains("retaining the last voice context after an unresolved kernel snapshot"))
    XCTAssertTrue(source.contains("failContextFreshInputPreparation("))
    XCTAssertTrue(source.contains("Voice context is temporarily unavailable"))
    XCTAssertFalse(source.contains("prefetchedFloatingAgentStatus"))
    XCTAssertFalse(source.contains("floatingAgentStatusContext"))
  }

  func testManagedReplacementFailoverPreservesBufferedTurnAndIdentity() throws {
    let source = try realtimeHubControllerSource()

    XCTAssertTrue(source.contains("let pendingTurn = replacementAudioBuffer"))
    XCTAssertTrue(source.contains("let responseID = voiceResponseID"))
    XCTAssertTrue(source.contains("replacementAudioBuffer = pendingTurn"))
    XCTAssertTrue(source.contains("voiceResponseID = responseID"))
    XCTAssertTrue(source.contains("pendingBargeInOwnerScope = replacementOwnerScope"))
    XCTAssertTrue(
      source.contains(
        "startReplacementSessionForBargeIn(\n        provider: alternate,"))
    XCTAssertTrue(source.contains("remintReplacementSessionForBargeIn(provider: alternate)"))
    XCTAssertTrue(source.contains("let replayedReplacementTurn = replacementAudioBuffer != nil"))
    XCTAssertTrue(
      source.contains(
        "if replayedReplacementTurn {\n      finishBargeInReplacementAfterSessionReady()"))
    XCTAssertTrue(
      source.contains(
        "if replacementAudioBuffer != nil {\n      if replacementAudioBuffer?.appendAudio"
      ))
    XCTAssertTrue(source.contains("if let pending = replacementAudioBuffer"))
    XCTAssertTrue(source.contains("VoiceTurnCoordinator.shared.activeTurn?.hubCommitPending == true"))
    XCTAssertTrue(source.contains("session?.commitInputTurn()"))
  }

  func testCompletedGeminiTurnRequiresFreshSessionBeforeNextPTT() throws {
    let source = try realtimeHubControllerSource()

    XCTAssertTrue(source.contains("private var geminiSessionNeedsTurnBoundary = false"))
    XCTAssertTrue(source.contains("sessionProvider == .gemini && geminiSessionNeedsTurnBoundary"))
    XCTAssertTrue(source.contains("restartSessionForBargeIn(interruptedTurnTask: nil)"))
    XCTAssertTrue(source.contains("pendingSessionRefreshReason = \"voice_context_changed\""))
    XCTAssertTrue(
      source.contains("replacing completed-turn session before next PTT"))
  }

  func testNewPTTRotatesAnInFlightGeminiReplacementInsteadOfCoalescingAudio() throws {
    let source = try realtimeHubControllerSource()

    XCTAssertTrue(source.contains("let supersedesPendingReplacement = replacementAudioBuffer != nil"))
    XCTAssertTrue(source.contains("if supersedesPendingReplacement {"))
    XCTAssertTrue(source.contains("restartSessionForBargeIn(interruptedTurnTask: interruptedTurnTask)"))
    XCTAssertTrue(source.contains("rotating pending replacement to the newest PTT turn"))
    XCTAssertTrue(source.contains("turnID: pending.turnID"))
    XCTAssertTrue(source.contains("responseID: pending.responseID"))
    XCTAssertTrue(source.contains("if let interruptedTurnTask, !supersedesPendingReplacement"))
  }

  func testFailoverRemintKeepsReplacementRotatableAndRejectsStaleMint() throws {
    let source = try realtimeHubControllerSource()

    XCTAssertTrue(source.contains("pendingBargeInProvider = alternate"))
    XCTAssertTrue(source.contains("pendingBargeInAuth = .ephemeral(\"\")"))
    XCTAssertTrue(source.contains("private var bargeInReplacementGeneration: UInt64 = 0"))
    XCTAssertTrue(source.contains("generation == self.bargeInReplacementGeneration"))
    XCTAssertTrue(source.contains("let currentProvider = pendingBargeInProvider"))
    XCTAssertGreaterThanOrEqual(
      source.components(separatedBy: "self.redriveReplacementMintIfStale(").count - 1,
      5)
  }

  func testProviderResponseAndInputItemIDsOwnCallbackIdentity() throws {
    let session = try realtimeHubSessionSource()

    XCTAssertTrue(session.contains("openAIPendingResponseIdentities.removeFirst()"))
    XCTAssertTrue(session.contains("openAIPendingInputIdentities.removeFirst()"))
    XCTAssertTrue(session.contains("openAIResponseIdentities[id] = pending.identity"))
    XCTAssertTrue(session.contains("openAIInputItemIdentities[itemID] = identity"))
    XCTAssertTrue(session.contains("openAIResponseIdentity(for: e)"))
    XCTAssertTrue(session.contains("openAIInputIdentity(for: e)"))
    XCTAssertTrue(session.contains("emitAudio(d, identity: identity)"))
    XCTAssertTrue(session.contains("finishTurn(identity: responseIdentity)"))
    XCTAssertTrue(
      session.contains("PendingOpenAIResponseIdentity(identity: identity, canceled: false)"))
    XCTAssertTrue(session.contains("openAIPendingResponseIdentities[pendingIndex].canceled = true"))
    XCTAssertTrue(session.contains("guard !pending.canceled else"))
  }

  func testFastCommitQueuesBeginBeforeProviderCommit() throws {
    let source = try realtimeHubControllerSource()
    let physicalCommit = try XCTUnwrap(source.range(of: "func commitClaimedHubInput(turnID: VoiceTurnID)"))
    let tail = source[physicalCommit.lowerBound...]
    let begin = try XCTUnwrap(tail.range(of: "s.beginInputTurn("))
    let providerCommit = try XCTUnwrap(tail.range(of: "s.commitInputTurn()"))

    XCTAssertLessThan(begin.lowerBound, providerCommit.lowerBound)
  }

  func testHeadlessPTTHarnessDrivesReducerRouteAndFinalizeBeforeCommit() throws {
    let source = try realtimeHubControllerSource()
    let harness = try XCTUnwrap(
      source.range(of: "private func runHeadlessPTTTurn("))
    let tail = source[harness.lowerBound...]
    let begin = try XCTUnwrap(
      tail.range(of: "let turnID = RealtimeAutomationTurnHarness.begin(on: VoiceTurnCoordinator.shared)"))
    let route = try XCTUnwrap(
      tail.range(of: ".selectRoute(turnID: turnID, route: .hub(sessionID: nil))"))
    let controllerBegin = try XCTUnwrap(tail.range(of: "beginTurn(turnID: turnID)"))
    let finalize = try XCTUnwrap(
      tail.range(of: "VoiceTurnCoordinator.shared.send(.finalize(turnID: turnID))"))
    let commit = try XCTUnwrap(tail.range(of: "_ = commitTurn()"))

    XCTAssertLessThan(begin.lowerBound, route.lowerBound)
    XCTAssertLessThan(route.lowerBound, controllerBegin.lowerBound)
    XCTAssertLessThan(controllerBegin.lowerBound, finalize.lowerBound)
    XCTAssertLessThan(finalize.lowerBound, commit.lowerBound)
  }

  func testRapidBurstHarnessCommitsEveryClipWithoutWaitingForReplies() throws {
    let source = try realtimeHubControllerSource()
    let harness = try XCTUnwrap(
      source.range(of: "private func runHeadlessRapidPTTBurst("))
    let tail = source[harness.lowerBound...]
    let loop = try XCTUnwrap(tail.range(of: "for clip in clips"))
    let begin = try XCTUnwrap(
      tail.range(of: "RealtimeAutomationTurnHarness.begin(on: VoiceTurnCoordinator.shared)"))
    let finalize = try XCTUnwrap(tail.range(of: ".finalize(turnID: turnID)"))
    let commit = try XCTUnwrap(tail.range(of: "_ = commitTurn()"))
    let wait = try XCTUnwrap(tail.range(of: "while Date() < deadline"))

    XCTAssertLessThan(loop.lowerBound, begin.lowerBound)
    XCTAssertLessThan(begin.lowerBound, finalize.lowerBound)
    XCTAssertLessThan(finalize.lowerBound, commit.lowerBound)
    XCTAssertLessThan(commit.lowerBound, wait.lowerBound)
  }

  func testIdleSessionCanBeReplaced() {
    XCTAssertTrue(
      RealtimeHubLifecyclePolicy.canReplaceSession(
        .init(
          capturingInput: false,
          providerActive: false,
          playbackActive: false,
          pendingToolCount: 0,
          coordinatorTurnActive: false,
          minting: false)))
  }

  func testSessionReplacementIsBlockedByEveryActiveTurnDimension() {
    let blocked: [RealtimeHubLifecycleSnapshot] = [
      .init(
        capturingInput: true, providerActive: false, playbackActive: false,
        pendingToolCount: 0, coordinatorTurnActive: false, minting: false),
      .init(
        capturingInput: false, providerActive: true, playbackActive: false,
        pendingToolCount: 0, coordinatorTurnActive: false, minting: false),
      .init(
        capturingInput: false, providerActive: false, playbackActive: true,
        pendingToolCount: 0, coordinatorTurnActive: false, minting: false),
      .init(
        capturingInput: false, providerActive: false, playbackActive: false,
        pendingToolCount: 1, coordinatorTurnActive: false, minting: false),
      .init(
        capturingInput: false, providerActive: false, playbackActive: false,
        pendingToolCount: 0, coordinatorTurnActive: true, minting: false),
      .init(
        capturingInput: false, providerActive: false, playbackActive: false,
        pendingToolCount: 0, coordinatorTurnActive: false, minting: true),
    ]

    for snapshot in blocked {
      XCTAssertFalse(RealtimeHubLifecyclePolicy.canReplaceSession(snapshot), "\(snapshot)")
    }
  }

  func testGeneralWarmSessionCannotRacePendingBargeInReplacement() {
    XCTAssertTrue(
      RealtimeHubLifecyclePolicy.canStartGeneralWarmSession(replacementPending: false))
    XCTAssertFalse(
      RealtimeHubLifecyclePolicy.canStartGeneralWarmSession(replacementPending: true))
  }

  func testWarmSessionOwnedByACannotBeReusedAfterSwitchToB() {
    let ownerA = RealtimeHubOwnerScope.capture(currentOwnerID: "owner-a")

    XCTAssertTrue(
      RealtimeHubOwnerFence.canReuseWarmSession(
        sessionOwner: ownerA,
        currentOwnerID: "owner-a"))
    XCTAssertFalse(
      RealtimeHubOwnerFence.canReuseWarmSession(
        sessionOwner: ownerA,
        currentOwnerID: "owner-b"))
  }

  func testBargeInRemintOwnedByACannotReplaceSessionAfterSwitchToB() {
    let ownerA = RealtimeHubOwnerScope.capture(currentOwnerID: "owner-a")
    let ownerB = RealtimeHubOwnerScope.capture(currentOwnerID: "owner-b")

    XCTAssertTrue(
      RealtimeHubOwnerFence.acceptsBargeInReplacement(
        sessionOwner: ownerA,
        replacementOwner: ownerA,
        currentOwnerID: "owner-a"))
    XCTAssertFalse(
      RealtimeHubOwnerFence.acceptsBargeInReplacement(
        sessionOwner: ownerA,
        replacementOwner: ownerA,
        currentOwnerID: "owner-b"))
    XCTAssertFalse(
      RealtimeHubOwnerFence.acceptsBargeInReplacement(
        sessionOwner: ownerA,
        replacementOwner: ownerB,
        currentOwnerID: "owner-b"))
  }

  func testPrepareReplacementSessionPersistsInterruptedTurnBeforeSeedAndSession() async {
    var steps: [String] = []
    let interrupted = InterruptedTurnPayload(
      ownerID: "owner-a",
      userText: "hold on",
      assistantText: "partial reply",
      idempotencyKey: "turn-interrupted"
    )

    let outcome = await RealtimeHubBargeInContinuity.prepareReplacementSession(
      resolveInterruptedTurn: { interrupted },
      recordInterruptedTurn: { turn in
        steps.append("record:\(turn.idempotencyKey)")
        return true
      },
      refreshVoiceContext: {
        steps.append("seed")
        return KernelTurnProjection.stableTurnIDs(continuityKey: "turn-interrupted")
      },
      startReplacementSession: {
        steps.append("session")
      }
    )

    XCTAssertEqual(outcome, .started)
    XCTAssertEqual(steps, ["record:turn-interrupted", "seed", "session"])
  }

  func testPrepareReplacementSessionSkipsRecordWhenNoInterruptedTurn() async {
    var steps: [String] = []

    let outcome = await RealtimeHubBargeInContinuity.prepareReplacementSession(
      resolveInterruptedTurn: { nil },
      recordInterruptedTurn: { _ in
        steps.append("record")
        return true
      },
      refreshVoiceContext: {
        steps.append("seed")
        return []
      },
      startReplacementSession: {
        steps.append("session")
      }
    )

    XCTAssertEqual(outcome, .started)
    XCTAssertEqual(steps, ["seed", "session"])
  }

  func testPrepareReplacementSessionRetriesSupersededSeedBeforeStartingSession() async {
    var steps: [String] = []
    var refreshAttempts = 0

    let outcome = await RealtimeHubBargeInContinuity.prepareReplacementSession(
      resolveInterruptedTurn: { nil },
      recordInterruptedTurn: { _ in
        XCTFail("no interrupted turn should be recorded")
        return false
      },
      refreshVoiceContext: {
        refreshAttempts += 1
        steps.append("seed:\(refreshAttempts)")
        return refreshAttempts == 3 ? [] : nil
      },
      startReplacementSession: {
        steps.append("session")
      })

    XCTAssertEqual(outcome, .started)
    XCTAssertEqual(steps, ["seed:1", "seed:2", "seed:3", "session"])
  }

  func testReplacementWaitsForLateTranscriptBeforePersistenceSeedAndSession() async {
    var steps: [String] = []

    let outcome = await RealtimeHubBargeInContinuity.prepareReplacementSession(
      resolveInterruptedTurn: {
        steps.append("resolve:start")
        await Task.yield()
        steps.append("resolve:done")
        return InterruptedTurnPayload(
          ownerID: "owner-a",
          userText: "late transcript",
          assistantText: "partial",
          idempotencyKey: "late-turn")
      },
      recordInterruptedTurn: { _ in
        steps.append("record")
        return true
      },
      refreshVoiceContext: {
        steps.append("seed")
        return KernelTurnProjection.stableTurnIDs(continuityKey: "late-turn")
      },
      startReplacementSession: { steps.append("session") })

    XCTAssertEqual(outcome, .started)
    XCTAssertEqual(steps, ["resolve:start", "resolve:done", "record", "seed", "session"])
  }

  func testReplacementRejectsResolvedButStaleSnapshotUntilInterruptedTurnsAreVisible() async {
    var steps: [String] = []
    var refreshAttempts = 0
    let continuityKey = "stale-then-fresh"
    let expectedIDs = KernelTurnProjection.stableTurnIDs(continuityKey: continuityKey)

    let outcome = await RealtimeHubBargeInContinuity.prepareReplacementSession(
      resolveInterruptedTurn: {
        InterruptedTurnPayload(
          ownerID: "owner-a",
          userText: "request screen permission",
          assistantText: "requesting it now",
          idempotencyKey: continuityKey)
      },
      recordInterruptedTurn: { _ in
        steps.append("record")
        return true
      },
      refreshVoiceContext: {
        refreshAttempts += 1
        steps.append("seed:\(refreshAttempts)")
        return refreshAttempts == 1 ? [] : expectedIDs
      },
      startReplacementSession: { steps.append("session") })

    XCTAssertEqual(outcome, .started)
    XCTAssertEqual(steps, ["record", "seed:1", "seed:2", "session"])
  }

  func testReplacementFailsClosedWhenInterruptedTurnPersistenceFails() async {
    var steps: [String] = []
    let outcome = await RealtimeHubBargeInContinuity.prepareReplacementSession(
      resolveInterruptedTurn: {
        InterruptedTurnPayload(
          ownerID: "owner-a",
          userText: "request it",
          assistantText: "partial",
          idempotencyKey: "failed-persistence")
      },
      recordInterruptedTurn: { _ in
        steps.append("record")
        return false
      },
      refreshVoiceContext: {
        steps.append("seed")
        return []
      },
      startReplacementSession: { steps.append("session") })

    XCTAssertEqual(outcome, .interruptedTurnPersistenceFailed)
    XCTAssertEqual(steps, ["record"])
  }

  func testReplacementStopsAfterBoundedContextRefreshFailures() async {
    var refreshAttempts = 0
    let outcome = await RealtimeHubBargeInContinuity.prepareReplacementSession(
      resolveInterruptedTurn: { nil },
      recordInterruptedTurn: { _ in true },
      refreshVoiceContext: {
        refreshAttempts += 1
        return nil
      },
      startReplacementSession: { XCTFail("replacement must not start without context") })

    XCTAssertEqual(outcome, .contextUnavailable)
    XCTAssertEqual(refreshAttempts, RealtimeHubBargeInContinuity.maximumContextRefreshAttempts)
  }

  func testTranscriptPolicyUsesLocalDecodeWhenProviderTranscriptIsLate() {
    let resolution = RealtimeHubTranscriptPolicy.resolve(
      providerText: "",
      preferredLanguages: [],
      localTranscript: "locally decoded request",
      localLanguage: "en")

    XCTAssertEqual(resolution.userText, "locally decoded request")
    XCTAssertTrue(resolution.usedLocalTranscript)
  }

  func testTranscriptPolicyKeepsValidProviderTranscript() {
    let resolution = RealtimeHubTranscriptPolicy.resolve(
      providerText: "the provider transcript",
      preferredLanguages: ["en"],
      localTranscript: "local alternative",
      localLanguage: "en")

    XCTAssertEqual(resolution.userText, "the provider transcript")
    XCTAssertFalse(resolution.usedLocalTranscript)
  }

  func testTranscriptPolicyCorrectsConfiguredLanguageMismatch() {
    let resolution = RealtimeHubTranscriptPolicy.resolve(
      providerText: "ciao come stai",
      preferredLanguages: ["en"],
      localTranscript: "open the calendar",
      localLanguage: "en")

    XCTAssertEqual(resolution.userText, "open the calendar")
    XCTAssertTrue(resolution.usedLocalTranscript)
  }

  func testCanceledTurnFenceResumesOnlyAfterAnotherTurnTerminates() {
    let canceled = VoiceTurnID()
    let next = VoiceTurnID()

    XCTAssertFalse(
      RealtimeHubLifecyclePolicy.shouldResumeCanceledTurnRefresh(
        fenceTurnID: canceled, terminalTurnID: canceled))
    XCTAssertTrue(
      RealtimeHubLifecyclePolicy.shouldResumeCanceledTurnRefresh(
        fenceTurnID: canceled, terminalTurnID: next))
  }

  func testNativeAudioFailureKeepsTextFallbackOnlyBeforePlaybackStarts() {
    XCTAssertEqual(
      RealtimeNativeAudioScheduleFailureAction.decide(playbackAlreadyStarted: false),
      .keepTextFallback)
    XCTAssertEqual(
      RealtimeNativeAudioScheduleFailureAction.decide(playbackAlreadyStarted: true),
      .failTurnAfterPartialPlayback)

    let coordinator = VoiceTurnCoordinator()
    let turnID = coordinator.begin(intent: .hold)
    coordinator.send(.selectRoute(turnID: turnID, route: .deepgramBatch))
    coordinator.send(.finalize(turnID: turnID))
    coordinator.send(.transcriptionStarted(turnID: turnID))
    coordinator.send(.transcriptionFinal(turnID: turnID, text: "fixture"))
    guard case .acquired(let native) = coordinator.acquireOutput(.nativeRealtime, turnID: turnID) else {
      return XCTFail("native lane should acquire")
    }
    XCTAssertTrue(coordinator.releaseOutput(native))
    guard case .acquired(let fallback) = coordinator.acquireOutput(.selectedVoiceFallback, turnID: turnID)
    else { return XCTFail("selected voice fallback should remain available") }
    XCTAssertEqual(fallback.lane, .selectedVoiceFallback)
  }

  func testInterruptedTurnVisibleAssistantTextKeepsPartialReplyOnly() {
    XCTAssertEqual(
      InterruptedTurnPayload.visibleAssistantText(partialAssistantText: "  Partial reply  "),
      "Partial reply"
    )
    XCTAssertEqual(
      InterruptedTurnPayload.visibleAssistantText(partialAssistantText: ""),
      ""
    )
    XCTAssertFalse(
      InterruptedTurnPayload.visibleAssistantText(partialAssistantText: "Still streaming…")
        .localizedCaseInsensitiveContains("interrupted")
    )
  }

  func testFreshSessionBargeInDefersContextPrefetchUntilContinuityCompletes() throws {
    let source = try realtimeHubControllerSource()

    XCTAssertTrue(source.contains("deferredFreshSessionContextPrefetch"))
    XCTAssertTrue(source.contains("completeBargeInReplacementAfterContinuity("))
    XCTAssertTrue(
      source.contains("await self.refreshVoiceContextSnapshot()")
        || source.contains("await refreshVoiceContextSnapshot()"))
    XCTAssertTrue(source.contains("beginContextFreshInputPreparation("))
    XCTAssertTrue(source.contains("sessionVoiceContextFreshnessIdentity"))
    XCTAssertTrue(source.contains("persistTurnDirectlyToKernel("))
    XCTAssertTrue(source.contains("RealtimeHubBargeInContinuity.prepareReplacementSession("))
    XCTAssertFalse(source.contains("preserveInterruptedTurnForContinuity()"))
  }

  func testVoiceContextRefreshPolicyUsesOnlyVersionRendererAndCapability() {
    let baseline = "version-a:renderer-a:capability-1"
    // A monotonic snapshot generation is intentionally absent from this
    // identity: unchanged material must not churn a warm voice socket.
    XCTAssertFalse(RealtimeVoiceContextRefreshPolicy.requiresRefresh(
      currentSnapshotIdentity: baseline,
      sessionSnapshotIdentity: baseline
    ))
    XCTAssertTrue(RealtimeVoiceContextRefreshPolicy.requiresRefresh(
      currentSnapshotIdentity: "version-b:renderer-a:capability-1",
      sessionSnapshotIdentity: baseline
    ))
    XCTAssertTrue(RealtimeVoiceContextRefreshPolicy.requiresRefresh(
      currentSnapshotIdentity: "version-a:renderer-a:capability-2",
      sessionSnapshotIdentity: baseline
    ))
  }

  func testBeginTurnWaitsForActiveSessionBeforeActivityStart() throws {
    let source = try realtimeHubControllerSource()

    XCTAssertTrue(source.contains("self.contextFreshInputPreparationIsCurrent("))
    XCTAssertTrue(source.contains("await self.waitUntilActive(timeout: 15)"))
    XCTAssertTrue(source.contains("inputTurnActivityStartPending = true"))
  }

  func testHubDidConnectCannotOpenInputFromTransportReadiness() throws {
    let source = try realtimeHubControllerSource()
    let connectStart = try XCTUnwrap(
      source.range(of: "func hubDidConnect(source: RealtimeHubSession)"))
    let receiveStart = try XCTUnwrap(
      source.range(
        of: "func hubDidReceiveInputTranscript(",
        range: connectStart.upperBound..<source.endIndex))
    let body = String(source[connectStart.lowerBound..<receiveStart.lowerBound])

    // omi-test-quality: source-inspection -- forbidden-path ratchet paired with
    // `testTransportReadyCannotAdmitInputWithoutExactContextBinding`'s
    // behavioral admission-policy coverage.
    XCTAssertFalse(body.contains("beginInputTurn("))
    XCTAssertTrue(body.contains("Transport readiness has no authority to open provider input"))
  }

  func testPTTArmsVoiceContextPrefetchBeforeMicCapture() throws {
    let pttSource = try pushToTalkManagerSource()
    let prefetchRange = try XCTUnwrap(pttSource.range(of: "prefetchVoiceContextSnapshotIfNeeded()"))
    let captureRange = try XCTUnwrap(
      pttSource.range(of: "captureContextAndStartAudio(preOverlayImage: preOverlayImage)"))
    XCTAssertLessThan(prefetchRange.lowerBound, captureRange.lowerBound)
  }

  private func pushToTalkManagerSource() throws -> String {
    let sourceURL = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources/FloatingControlBar/PushToTalkManager.swift")
    return try String(contentsOf: sourceURL, encoding: .utf8)
  }

  private func realtimeHubControllerSource() throws -> String {
    let sourceURL = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources/FloatingControlBar/RealtimeHubController.swift")
    return try String(contentsOf: sourceURL, encoding: .utf8)
  }

  private func realtimeHubSessionSource() throws -> String {
    let sourceURL = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources/FloatingControlBar/RealtimeHubSession.swift")
    return try String(contentsOf: sourceURL, encoding: .utf8)
  }
}
