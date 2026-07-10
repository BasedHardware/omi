import XCTest

@testable import Omi_Computer

@MainActor
final class RealtimeHubBargeInContinuityTests: XCTestCase {
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
    var pending = PendingBargeInReplacementTurn(
      turnID: VoiceTurnID(), responseID: VoiceResponseID("pending"))
    let first = Data(repeating: 1, count: PendingBargeInReplacementTurn.maxBufferedAudioBytes - 8)

    XCTAssertTrue(pending.appendAudio(first))
    XCTAssertFalse(pending.appendAudio(Data(repeating: 2, count: 16)))
    XCTAssertEqual(
      pending.bufferedAudioBytes,
      PendingBargeInReplacementTurn.maxBufferedAudioBytes)
    XCTAssertFalse(pending.appendAudio(Data([3])))
    XCTAssertEqual(
      pending.audioBuffer.reduce(0) { $0 + $1.count },
      PendingBargeInReplacementTurn.maxBufferedAudioBytes)
  }

  func testAudioIngressClosesAtCommitAndCannotRebindToNextTurn() {
    let turnA = VoiceTurnID()
    let turnB = VoiceTurnID()

    XCTAssertTrue(
      VoiceAudioIngressOwnership.accepts(
        turnID: turnA, activeTurnID: turnA, inputTurnInProgress: true))
    XCTAssertFalse(
      VoiceAudioIngressOwnership.accepts(
        turnID: turnA, activeTurnID: turnA, inputTurnInProgress: false))
    XCTAssertFalse(
      VoiceAudioIngressOwnership.accepts(
        turnID: turnA, activeTurnID: turnB, inputTurnInProgress: true))
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

  func testCommitFreezesPreparationBeforeClosingInput() throws {
    let source = try realtimeHubControllerSource()
    let commit = try XCTUnwrap(source.range(of: "func commitTurn() -> RealtimeHubCommitResult"))
    let tail = source[commit.lowerBound...]
    let cancel = try XCTUnwrap(tail.range(of: "turnPreparationTask?.cancel()"))
    let close = try XCTUnwrap(tail.range(of: "inputTurnInProgress = false"))

    XCTAssertLessThan(cancel.lowerBound, close.lowerBound)
    XCTAssertTrue(source.contains("self.inputTurnInProgress,"))
    XCTAssertTrue(source.contains("pendingSessionRefreshReason = \"voice_seed_changed\""))
    XCTAssertTrue(
      source.contains("deferring voice-seed session refresh until the active turn terminates"))
    XCTAssertTrue(source.contains("await persistence.value"))
    XCTAssertTrue(source.contains("await self.refreshVoiceSeedContext()"))
    XCTAssertTrue(source.contains("applying deferred voice seed refresh after turn persistence"))
    XCTAssertTrue(source.contains("let observedTurnEpoch = turnEpoch"))
    XCTAssertTrue(source.contains("let observedPersistenceGeneration = turnPersistenceGeneration"))
    XCTAssertTrue(source.contains("observedTurnEpoch == turnEpoch"))
    XCTAssertTrue(source.contains("observedPersistenceGeneration == turnPersistenceGeneration"))
    XCTAssertTrue(source.contains("let previous = turnPersistenceTask"))
    XCTAssertTrue(source.contains("if let previous { await previous.value }"))
    XCTAssertTrue(source.contains("enqueueTurnPersistence { [weak self] in"))
    XCTAssertTrue(source.contains("persistTurnToKernelThroughTransientFailures"))
    XCTAssertTrue(source.contains("let acknowledged = await recordTurnToKernelAwaiting("))
    XCTAssertTrue(source.contains("try? await Task.sleep(nanoseconds: 250_000_000)"))
    XCTAssertTrue(source.contains("voiceTurnOutbox.enqueue(entry)"))
    XCTAssertTrue(source.contains("scheduleVoiceTurnOutboxDrain"))
    XCTAssertTrue(source.contains("voiceTurnOutbox.seedContext("))
    XCTAssertTrue(source.contains("excludingIdempotencyKeys: prefetchedVoiceSeedIdempotencyKeys"))
    XCTAssertTrue(source.contains("kernelVoiceSeedSnapshot()"))
    XCTAssertTrue(source.contains("stageRealtimeVoiceTurn("))
    XCTAssertTrue(source.contains("await self.awaitTurnPersistenceFence()"))
    XCTAssertTrue(source.contains("let interruptedContinuityTask = bargeInContinuityTask"))
    XCTAssertTrue(source.contains("await interruptedContinuityTask.value"))
    XCTAssertTrue(source.contains("pendingSessionRefreshReason = \"voice_seed_changed\""))
    XCTAssertTrue(source.contains("cancelContinuityFenceActive = true"))
    XCTAssertTrue(source.contains("self.cancelContinuityFenceActive = false"))
    XCTAssertTrue(source.contains("general warm deferred behind canceled-turn continuity fence"))
    XCTAssertTrue(source.contains("session start rejected behind canceled-turn continuity fence"))
  }

  func testCancelKeepsReconnectFenceThroughEveryPersistencePathAndSeedRefresh() throws {
    let source = try realtimeHubControllerSource()
    let cancel = try XCTUnwrap(
      source.range(of: "func cancelTurn(turnID requestedTurnID: VoiceTurnID) -> Bool"))
    let cancelTail = source[cancel.lowerBound...]
    let preparationWait = try XCTUnwrap(
      cancelTail.range(of: "await canceledPreparationTask.value"))
    let continuityWait = try XCTUnwrap(
      cancelTail.range(of: "await interruptedContinuityTask.value"))
    let persistenceFence = try XCTUnwrap(
      cancelTail.range(of: "await self.refreshVoiceSeedAfterPersistenceFence("))
    let fenceRelease = try XCTUnwrap(
      cancelTail.range(of: "self.cancelContinuityFenceActive = false"))

    XCTAssertLessThan(preparationWait.lowerBound, continuityWait.lowerBound)
    XCTAssertLessThan(continuityWait.lowerBound, persistenceFence.lowerBound)
    XCTAssertLessThan(persistenceFence.lowerBound, fenceRelease.lowerBound)

    let helper = try XCTUnwrap(
      source.range(
        of: "private func refreshVoiceSeedAfterPersistenceFence(reason: String) async -> Bool"))
    let helperTail = source[helper.lowerBound...]
    let ordinaryPersistenceWait = try XCTUnwrap(helperTail.range(of: "await persistence.value"))
    let seedRefresh = try XCTUnwrap(helperTail.range(of: "await refreshVoiceSeedContext()"))
    XCTAssertLessThan(ordinaryPersistenceWait.lowerBound, seedRefresh.lowerBound)

    XCTAssertTrue(source.contains("private var voiceSeedRefreshGeneration: UInt64 = 0"))
    XCTAssertTrue(source.contains("voiceSeedRefreshGeneration == refreshGeneration"))
    XCTAssertTrue(source.contains("let resolvedSeed = await seed"))
    XCTAssertTrue(source.contains("let resolvedFloatingStatus = await floatingStatus"))
    XCTAssertTrue(source.contains("prefetchedVoiceSeedContext = resolvedSeed"))
    XCTAssertTrue(source.contains("prefetchedFloatingAgentStatus = resolvedFloatingStatus"))
  }

  func testManagedReplacementFailoverPreservesBufferedTurnAndIdentity() throws {
    let source = try realtimeHubControllerSource()

    XCTAssertTrue(source.contains("let pendingTurn = pendingBargeInReplacement"))
    XCTAssertTrue(source.contains("let responseID = voiceResponseID"))
    XCTAssertTrue(source.contains("pendingBargeInReplacement = pendingTurn"))
    XCTAssertTrue(source.contains("voiceResponseID = responseID"))
    XCTAssertTrue(source.contains("startReplacementSessionForBargeIn(provider: alternate"))
    XCTAssertTrue(source.contains("remintReplacementSessionForBargeIn(provider: alternate)"))
    XCTAssertTrue(
      source.contains(
        "if pendingBargeInReplacement != nil {\n      finishBargeInReplacementAfterSessionReady()"))
    XCTAssertTrue(
      source.contains(
        "if pendingBargeInReplacement != nil {\n      if pendingBargeInReplacement?.appendAudio"
      ))
    XCTAssertTrue(source.contains("if var pending = pendingBargeInReplacement"))
    XCTAssertTrue(source.contains("responding = true\n      session?.commitInputTurn()"))
  }

  func testCompletedGeminiTurnRequiresFreshSessionBeforeNextPTT() throws {
    let source = try realtimeHubControllerSource()

    XCTAssertTrue(source.contains("private var geminiSessionNeedsTurnBoundary = false"))
    XCTAssertTrue(source.contains("sessionProvider == .gemini && geminiSessionNeedsTurnBoundary"))
    XCTAssertTrue(source.contains("restartSessionForBargeIn(interruptedTurnTask: nil)"))
    XCTAssertTrue(source.contains("pendingSessionRefreshReason = \"voice_seed_changed\""))
    XCTAssertTrue(
      source.contains("replacing completed-turn session before next PTT"))
  }

  func testNewPTTRotatesAnInFlightGeminiReplacementInsteadOfCoalescingAudio() throws {
    let source = try realtimeHubControllerSource()

    XCTAssertTrue(source.contains("let supersedesPendingReplacement = pendingBargeInReplacement != nil"))
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
      source.components(separatedBy: "redriveReplacementMintIfStale(generation: generation)").count - 1,
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
    let commit = try XCTUnwrap(source.range(of: "func commitTurn() -> RealtimeHubCommitResult"))
    let tail = source[commit.lowerBound...]
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
      tail.range(of: "let turnID = VoiceTurnCoordinator.shared.begin(intent: .hold)"))
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
    let begin = try XCTUnwrap(tail.range(of: "VoiceTurnCoordinator.shared.begin(intent: .hold)"))
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
          inputTurnInProgress: false,
          responding: false,
          playbackActive: false,
          pendingToolCount: 0,
          coordinatorTurnActive: false,
          minting: false)))
  }

  func testSessionReplacementIsBlockedByEveryActiveTurnDimension() {
    let blocked: [RealtimeHubLifecycleSnapshot] = [
      .init(
        inputTurnInProgress: true, responding: false, playbackActive: false,
        pendingToolCount: 0, coordinatorTurnActive: false, minting: false),
      .init(
        inputTurnInProgress: false, responding: true, playbackActive: false,
        pendingToolCount: 0, coordinatorTurnActive: false, minting: false),
      .init(
        inputTurnInProgress: false, responding: false, playbackActive: true,
        pendingToolCount: 0, coordinatorTurnActive: false, minting: false),
      .init(
        inputTurnInProgress: false, responding: false, playbackActive: false,
        pendingToolCount: 1, coordinatorTurnActive: false, minting: false),
      .init(
        inputTurnInProgress: false, responding: false, playbackActive: false,
        pendingToolCount: 0, coordinatorTurnActive: true, minting: false),
      .init(
        inputTurnInProgress: false, responding: false, playbackActive: false,
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

  func testPrepareReplacementSessionPersistsInterruptedTurnBeforeSeedAndSession() async {
    var steps: [String] = []
    let interrupted = InterruptedTurnPayload(
      userText: "hold on",
      assistantText: "partial reply",
      idempotencyKey: "turn-interrupted"
    )

    await RealtimeHubBargeInContinuity.prepareReplacementSession(
      resolveInterruptedTurn: { interrupted },
      recordInterruptedTurn: { turn in
        steps.append("record:\(turn.idempotencyKey)")
      },
      refreshVoiceSeed: {
        steps.append("seed")
        return true
      },
      startReplacementSession: {
        steps.append("session")
      }
    )

    XCTAssertEqual(steps, ["record:turn-interrupted", "seed", "session"])
  }

  func testPrepareReplacementSessionSkipsRecordWhenNoInterruptedTurn() async {
    var steps: [String] = []

    await RealtimeHubBargeInContinuity.prepareReplacementSession(
      resolveInterruptedTurn: { nil },
      recordInterruptedTurn: { _ in
        steps.append("record")
      },
      refreshVoiceSeed: {
        steps.append("seed")
        return true
      },
      startReplacementSession: {
        steps.append("session")
      }
    )

    XCTAssertEqual(steps, ["seed", "session"])
  }

  func testPrepareReplacementSessionRetriesSupersededSeedBeforeStartingSession() async {
    var steps: [String] = []
    var refreshAttempts = 0

    await RealtimeHubBargeInContinuity.prepareReplacementSession(
      resolveInterruptedTurn: { nil },
      recordInterruptedTurn: { _ in
        XCTFail("no interrupted turn should be recorded")
      },
      refreshVoiceSeed: {
        refreshAttempts += 1
        steps.append("seed:\(refreshAttempts)")
        return refreshAttempts == 3
      },
      startReplacementSession: {
        steps.append("session")
      })

    XCTAssertEqual(steps, ["seed:1", "seed:2", "seed:3", "session"])
  }

  func testReplacementWaitsForLateTranscriptBeforePersistenceSeedAndSession() async {
    var steps: [String] = []

    await RealtimeHubBargeInContinuity.prepareReplacementSession(
      resolveInterruptedTurn: {
        steps.append("resolve:start")
        await Task.yield()
        steps.append("resolve:done")
        return InterruptedTurnPayload(
          userText: "late transcript",
          assistantText: "partial",
          idempotencyKey: "late-turn")
      },
      recordInterruptedTurn: { _ in steps.append("record") },
      refreshVoiceSeed: {
        steps.append("seed")
        return true
      },
      startReplacementSession: { steps.append("session") })

    XCTAssertEqual(steps, ["resolve:start", "resolve:done", "record", "seed", "session"])
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

    let coordinator = VoiceOutputCoordinator()
    let turnID = coordinator.beginTurn()
    guard case .acquired(let native) = coordinator.acquire(.nativeRealtime, turnID: turnID) else {
      return XCTFail("native lane should acquire")
    }
    XCTAssertTrue(coordinator.release(native))
    guard case .acquired(let fallback) = coordinator.acquire(.selectedVoiceFallback, turnID: turnID)
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

  func testFreshSessionBargeInDefersSeedPrefetchUntilContinuityCompletes() throws {
    let source = try realtimeHubControllerSource()

    XCTAssertTrue(source.contains("deferredFreshSessionSeedPrefetch"))
    XCTAssertTrue(source.contains("completeBargeInReplacementAfterContinuity("))
    XCTAssertTrue(
      source.contains("await self.refreshVoiceSeedContext()")
        || source.contains("await refreshVoiceSeedContext()"))
    XCTAssertTrue(source.contains("reconnectWarmSessionIfSeedStale()"))
    XCTAssertTrue(source.contains("sessionVoiceSeedContextSnapshot"))
    XCTAssertTrue(source.contains("recordTurnToKernelAwaiting("))
    XCTAssertTrue(source.contains("RealtimeHubBargeInContinuity.prepareReplacementSession("))
    XCTAssertFalse(source.contains("preserveInterruptedTurnForContinuity()"))
  }

  func testBeginTurnWaitsForActiveSessionBeforeActivityStart() throws {
    let source = try realtimeHubControllerSource()

    XCTAssertTrue(source.contains("inputTurnInProgress = true"))
    XCTAssertTrue(source.contains("await self.waitUntilActive(timeout: 15)"))
    XCTAssertTrue(source.contains("inputTurnActivityStartPending = true"))
  }

  func testHubDidConnectRetriesActivityStartDuringOpenTurn() throws {
    let source = try realtimeHubControllerSource()

    XCTAssertTrue(source.contains("if inputTurnInProgress"))
    XCTAssertTrue(
      source.contains("inputTurnActivityStartPending || sessionProvider == .gemini"))
    XCTAssertTrue(source.contains("responseID: voiceResponseID"))
    XCTAssertTrue(source.contains("interrupting: pendingInputTurnInterrupting"))
  }

  func testPTTArmsVoiceSeedPrefetchBeforeMicCapture() throws {
    let pttSource = try pushToTalkManagerSource()
    let prefetchRange = try XCTUnwrap(pttSource.range(of: "prefetchVoiceSeedContextIfNeeded()"))
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
