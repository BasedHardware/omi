import VoiceTurnDomain
import XCTest

@testable import Omi_Computer

@MainActor
final class VoiceTurnCoordinatorTests: XCTestCase {
  func testTerminalTelemetryUsesThePhysicalTurnBoundary() throws {
    DesktopDiagnosticsManager.shared.resetForTests()
    defer { DesktopDiagnosticsManager.shared.resetForTests() }

    let coordinator = VoiceTurnCoordinator(scheduler: ManualVoiceTurnScheduler())
    let turnID = coordinator.begin(intent: .hold)
    coordinator.publish(.finish(turnID: turnID, reason: .providerNoResponse))

    let url = try XCTUnwrap(DesktopDiagnosticsManager.shared.writeDiagnosticsAttachment())
    defer { try? FileManager.default.removeItem(at: url) }
    let data = try Data(contentsOf: url)
    let root = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
    let snapshots = try XCTUnwrap(root["snapshots"] as? [[String: Any]])
    let start = try XCTUnwrap(snapshots.first { $0["event"] as? String == "voice_turn_started" })
    let terminal = try XCTUnwrap(snapshots.first { $0["event"] as? String == "voice_turn_terminal" })

    XCTAssertEqual(start["attempt_id"] as? String, turnID.description)
    XCTAssertEqual(terminal["attempt_id"] as? String, turnID.description)
    XCTAssertEqual(terminal["terminal_reason"] as? String, "provider_no_response")
    XCTAssertEqual(terminal["outcome"] as? String, "failure")
    XCTAssertEqual(terminal["response_outcome"] as? String, "failure")
    XCTAssertNotNil(terminal["duration_ms"] as? Int)
  }

  func testNestedDeferredHubCommitQueuesWithoutSynchronousStateMutation() {
    let coordinator = VoiceTurnCoordinator(scheduler: ManualVoiceTurnScheduler())
    var sawQueuedPreCommitState = false
    coordinator.setEffectHandler { effect in
      guard case .finalizeCapturedInput(let turnID) = effect else { return }
      XCTAssertTrue(coordinator.canCommitHubTurn(turnID))

      // The physical PTT finalizer runs while the coordinator drains this
      // effect. Its commit-deferred event is deliberately FIFO-queued, so an
      // immediate read still observes the pre-commit finalizing state.
      coordinator.publish(.hubCommitDeferred(turnID: turnID))
      sawQueuedPreCommitState = coordinator.canCommitHubTurn(turnID)
    }

    let turnID = coordinator.begin(intent: .hold)
    coordinator.publish(.selectRoute(turnID: turnID, route: .hub(sessionID: VoiceSessionID())))
    coordinator.publish(.finalize(turnID: turnID))

    XCTAssertTrue(sawQueuedPreCommitState)
    XCTAssertEqual(coordinator.activeTurn?.phase, .awaitingResponse)
    XCTAssertTrue(coordinator.activeTurn?.hubCommitPending == true)
    XCTAssertEqual(coordinator.model.invalidTransitionCount, 0)
  }

  func testNestedHubCommitClaimRunsProviderEffectAfterClaimStateIsApplied() {
    let coordinator = VoiceTurnCoordinator(scheduler: ManualVoiceTurnScheduler())
    var providerEffectTurn: VoiceTurn?
    coordinator.setEffectHandler { effect in
      switch effect {
      case .finalizeCapturedInput(let turnID):
        // Match the physical PTT path: its finalization effect requests the
        // hub claim while the coordinator is already draining effects.
        coordinator.publish(.hubCommitClaimed(turnID: turnID))
      case .commitClaimedHubInput:
        providerEffectTurn = coordinator.activeTurn
      default:
        break
      }
    }

    let turnID = coordinator.begin(intent: .hold)
    coordinator.publish(.selectRoute(turnID: turnID, route: .hub(sessionID: VoiceSessionID())))
    coordinator.publish(.finalize(turnID: turnID))

    XCTAssertEqual(providerEffectTurn?.id, turnID)
    XCTAssertEqual(providerEffectTurn?.phase, .awaitingResponse)
    XCTAssertTrue(providerEffectTurn?.hubCommitPending == true)
  }

  func testAutomationFinalizeRemainsCommitableWithoutPhysicalCaptureBuffer() {
    let coordinator = VoiceTurnCoordinator(scheduler: ManualVoiceTurnScheduler())
    var physicalFinalizeCount = 0
    coordinator.setEffectHandler { effect in
      guard case .finalizeCapturedInput(let turnID) = effect else { return }
      if PushToTalkManager.shouldFinalizeCapturedInputPhysically(
        turnIntent: coordinator.activeTurn?.intent)
      {
        physicalFinalizeCount += 1
        coordinator.publish(.finish(turnID: turnID, reason: .tooShort))
      }
    }
    let turnID = RealtimeAutomationTurnHarness.begin(on: coordinator)
    coordinator.publish(.selectRoute(turnID: turnID, route: .hub(sessionID: VoiceSessionID())))

    coordinator.publish(.finalize(turnID: turnID))

    XCTAssertEqual(physicalFinalizeCount, 0)
    XCTAssertEqual(coordinator.activeTurn?.phase, .finalizing)
    XCTAssertTrue(coordinator.canCommitHubTurn(turnID))
    coordinator.publish(.hubCommitClaimed(turnID: turnID))
    XCTAssertEqual(coordinator.activeTurn?.phase, .awaitingResponse)
  }

  func testAutomationHarnessSatisfiesCaptureStartDeadline() {
    let scheduler = ManualVoiceTurnScheduler()
    let coordinator = VoiceTurnCoordinator(scheduler: scheduler)

    let turnID = RealtimeAutomationTurnHarness.begin(on: coordinator)
    scheduler.fire(deadline: .captureStart)

    XCTAssertEqual(coordinator.activeTurnID, turnID)
    XCTAssertEqual(coordinator.activeTurn?.captureID, VoiceCaptureID(1))
    XCTAssertEqual(coordinator.activeTurn?.phase, .recording)
  }

  func testFakeClockDrivesLockDeadlineAndRealStopCaptureEffect() {
    let scheduler = ManualVoiceTurnScheduler()
    let coordinator = VoiceTurnCoordinator(scheduler: scheduler)
    var effects: [VoiceTurnEffect] = []
    coordinator.setEffectHandler { effects.append($0) }
    let turnID = coordinator.begin(intent: .hold)
    coordinator.publish(.captureStarted(turnID: turnID, captureID: VoiceCaptureID(1)))
    coordinator.publish(.openLockWindow(turnID: turnID))

    scheduler.fire(deadline: .lockDecision)

    XCTAssertEqual(coordinator.model.turn?.phase, .finalizing)
    XCTAssertTrue(
      effects.contains(.stopCapture(turnID: turnID, captureID: VoiceCaptureID(1))))
  }

  func testCancelledDeadlineCannotMutateLaterTurn() {
    let scheduler = ManualVoiceTurnScheduler()
    let coordinator = VoiceTurnCoordinator(scheduler: scheduler)
    let oldTurn = coordinator.begin(intent: .hold)
    coordinator.publish(.openLockWindow(turnID: oldTurn))
    let newTurn = coordinator.begin(intent: .hold)

    scheduler.fire(deadline: .lockDecision)

    XCTAssertEqual(coordinator.activeTurnID, newTurn)
    XCTAssertEqual(coordinator.model.turn?.phase, .recording)
  }

  func testTimelineReconstructsTurnAndIsBounded() {
    let coordinator = VoiceTurnCoordinator(
      scheduler: ManualVoiceTurnScheduler(),
      timelineLimit: 4)
    let turnID = coordinator.begin(intent: .hold)
    coordinator.publish(.captureStarted(turnID: turnID, captureID: VoiceCaptureID(1)))
    coordinator.publish(.selectRoute(turnID: turnID, route: .deepgramBatch))
    coordinator.publish(.finalize(turnID: turnID))
    coordinator.publish(.transcriptionStarted(turnID: turnID))

    let timeline = coordinator.timelineSnapshot()
    XCTAssertEqual(timeline.count, 4)
    XCTAssertEqual(timeline.last?.turnID, turnID)
    XCTAssertEqual(timeline.last?.phaseAfter, .finalizing)
    XCTAssertEqual(timeline.last?.route, .deepgramBatch)
  }

  func testPresenterDerivesConsistentListeningThinkingAndTerminalUI() {
    let defaultsKey = "hasCompletedOnboarding"
    let previous = UserDefaults.standard.object(forKey: defaultsKey)
    UserDefaults.standard.set(false, forKey: defaultsKey)
    defer {
      if let previous {
        UserDefaults.standard.set(previous, forKey: defaultsKey)
      } else {
        UserDefaults.standard.removeObject(forKey: defaultsKey)
      }
    }

    let coordinator = VoiceTurnCoordinator(scheduler: ManualVoiceTurnScheduler())
    let barState = FloatingControlBarState()
    coordinator.configure(barState: barState)
    let turnID = coordinator.begin(intent: .hold)
    XCTAssertTrue(barState.isVoiceListening)
    XCTAssertFalse(barState.isThinking)

    coordinator.publish(.selectRoute(turnID: turnID, route: .deepgramBatch))
    coordinator.publish(.finalize(turnID: turnID))
    coordinator.publish(.transcriptionStarted(turnID: turnID))
    XCTAssertFalse(barState.isVoiceListening)
    XCTAssertTrue(barState.isThinking)
    XCTAssertEqual(barState.voiceTranscript, "Transcribing…")
    XCTAssertEqual(barState.pttHintText, "")

    coordinator.publish(.transcriptionFailed(turnID: turnID, message: "fixture"))
    // The capture/listening phase is over, but the pill remains expanded long
    // enough to make the actionable terminal hint visible to the user.
    XCTAssertTrue(barState.isVoiceListening)
    XCTAssertFalse(barState.isThinking)
    XCTAssertFalse(barState.isVoiceResponseActive)
    XCTAssertEqual(barState.pttHintText, "Couldn't transcribe that — try again")
  }

  func testAwaitingResponseRemainsThinkingUntilReducerAdvances() throws {
    let scheduler = ManualVoiceTurnScheduler()
    let coordinator = VoiceTurnCoordinator(scheduler: scheduler)
    let barState = FloatingControlBarState()
    coordinator.configure(barState: barState)
    let turnID = coordinator.begin(intent: .hold)
    coordinator.publish(.selectRoute(turnID: turnID, route: .deepgramBatch))
    coordinator.publish(.finalize(turnID: turnID))
    coordinator.publish(.transcriptionFinal(turnID: turnID, text: "find today's memories"))

    XCTAssertEqual(coordinator.activeTurn?.phase, .awaitingResponse)
    XCTAssertTrue(coordinator.projection.isThinking)
    XCTAssertTrue(barState.isThinking)

    coordinator.refreshPresentation()
    XCTAssertTrue(barState.isThinking)

    let identity = try XCTUnwrap(coordinator.activeTurn?.providerEffectIdentity)
    coordinator.publish(
      .providerResponseStartedScoped(
        turnID: turnID,
        identity: identity,
        sessionID: nil,
        responseID: nil))

    XCTAssertFalse(coordinator.projection.isThinking)
    XCTAssertFalse(barState.isThinking)
  }

  func testTerminalEffectAndCleanupAreExactlyOnce() {
    let coordinator = VoiceTurnCoordinator(scheduler: ManualVoiceTurnScheduler())
    var terminals: [VoiceTurnTerminalRecord] = []
    coordinator.setEffectHandler { effect in
      if case .terminal(let terminal) = effect {
        terminals.append(terminal)
      }
    }
    let turnID = coordinator.begin(intent: .hold)

    coordinator.publish(.cancel(turnID: turnID, reason: .cancelled))
    coordinator.publish(.finish(turnID: turnID, reason: .providerFailed))

    XCTAssertEqual(terminals, [.init(turnID: turnID, reason: .cancelled)])
    XCTAssertEqual(coordinator.model.duplicateTerminalCount, 1)
  }

  func testUnscopedPlaybackUsesPresenterButCannotOverrideActivePTTTurn() {
    let coordinator = VoiceTurnCoordinator(scheduler: ManualVoiceTurnScheduler())
    let barState = FloatingControlBarState()
    coordinator.configure(barState: barState)

    coordinator.setUnscopedResponseActive(true)
    XCTAssertTrue(barState.isVoiceResponseActive)
    coordinator.setUnscopedResponseActive(false)
    XCTAssertFalse(barState.isVoiceResponseActive)

    let turnID = coordinator.begin(intent: .hold)
    coordinator.publish(.selectRoute(turnID: turnID, route: .deepgramBatch))
    coordinator.publish(.finalize(turnID: turnID))
    coordinator.publish(.transcriptionStarted(turnID: turnID))
    coordinator.publish(.transcriptionFinal(turnID: turnID, text: "hello"))
    guard let providerIdentity = coordinator.activeTurn?.providerEffectIdentity else {
      return XCTFail("transcription final must mint a provider identity")
    }
    coordinator.publish(
      .providerResponseStartedScoped(
        turnID: turnID,
        identity: providerIdentity,
        sessionID: nil,
        responseID: nil))
    XCTAssertTrue(barState.isVoiceResponseActive)

    coordinator.setUnscopedResponseActive(false)
    XCTAssertTrue(
      barState.isVoiceResponseActive, "late non-PTT playback must not clear the active turn")
  }

  func testSnapshotHandlerReceivesInitialAndSubsequentAuthoritativeModels() {
    let coordinator = VoiceTurnCoordinator(scheduler: ManualVoiceTurnScheduler())
    var snapshots: [VoiceTurnModel] = []
    coordinator.setSnapshotHandler { snapshots.append($0) }

    let turnID = coordinator.begin(intent: .hold)
    coordinator.publish(.lock(turnID: turnID))

    XCTAssertEqual(snapshots.first, .idle)
    XCTAssertEqual(snapshots.last?.turn?.phase, .lockedRecording)
    XCTAssertEqual(snapshots.count, 3)
  }

  func testHubReadyTransitionIsConsumedBeforeReentrantSnapshot() {
    let coordinator = VoiceTurnCoordinator(scheduler: ManualVoiceTurnScheduler())
    let sessionID = VoiceSessionID()
    var resolutions = 0
    coordinator.setEffectHandler { effect in
      guard case .prepareHubInput(let turnID, let preparedSessionID) = effect else { return }
      XCTAssertEqual(preparedSessionID, sessionID)
      resolutions += 1
      // RealtimeHubController.beginTurn clears its response glow synchronously,
      // which publishes another snapshot. The consumed transition must not run
      // the warm-wait resolver again.
      coordinator.publish(.responseActiveChanged(turnID: turnID, active: false))
    }

    let turnID = coordinator.begin(intent: .hold)
    coordinator.publish(.selectRoute(turnID: turnID, route: .hubWarmWait))
    coordinator.publish(.hubReady(turnID: turnID, sessionID: sessionID))

    XCTAssertEqual(resolutions, 1)
    XCTAssertEqual(coordinator.model.turn?.route, .hub(sessionID: sessionID))
    XCTAssertEqual(
      coordinator.timelineSnapshot().filter { $0.event == "hub_ready" }.count,
      1)
  }

  func testPrepareHubInputCanReserveContextAdmissionIdentityWhileEffectsDrainFIFO() {
    let coordinator = VoiceTurnCoordinator(scheduler: ManualVoiceTurnScheduler())
    let sessionID = VoiceSessionID()
    var reservedIdentity: VoiceEffectIdentity?

    coordinator.setEffectHandler { effect in
      guard case .prepareHubInput(let turnID, _) = effect else { return }
      // This is the real PTT path: `hubReady` emits prepareHubInput, whose
      // handler starts a context-fresh admission while the coordinator remains
      // inside its FIFO effect drain.
      let identity = coordinator.reserveEffectIdentity()
      reservedIdentity = identity
      guard let identity else { return }
      coordinator.publish(
        .providerReconnectStarted(
          turnID: turnID,
          identity: identity,
          previousSessionID: nil))
    }

    let turnID = coordinator.begin(intent: .hold)
    coordinator.publish(.selectRoute(turnID: turnID, route: .hubWarmWait))
    coordinator.publish(.hubReady(turnID: turnID, sessionID: sessionID))

    guard let reservedIdentity else {
      return XCTFail("prepareHubInput must reserve an identity while effects are draining")
    }
    XCTAssertEqual(reservedIdentity.generation, turnID.rawValue)
    guard let connection = coordinator.activeTurn?.providerConnection,
      case .reconnecting(let appliedIdentity, let previousSessionID) = connection
    else {
      return XCTFail("the queued context-admission event must be applied after the effect returns")
    }
    XCTAssertEqual(appliedIdentity, reservedIdentity)
    XCTAssertNil(previousSessionID)
    XCTAssertEqual(coordinator.model.invalidTransitionCount, 0)
  }

  func testSnapshotReentrantEventsDrainFIFOWithoutRecursiveCallbacks() {
    let coordinator = VoiceTurnCoordinator(scheduler: ManualVoiceTurnScheduler())
    var callbackDepth = 0
    var maximumCallbackDepth = 0
    var queuedRouteSelection = false

    coordinator.setSnapshotHandler { model in
      callbackDepth += 1
      maximumCallbackDepth = max(maximumCallbackDepth, callbackDepth)
      defer { callbackDepth -= 1 }

      guard !queuedRouteSelection, let turn = model.turn, turn.phase == .recording else {
        return
      }
      queuedRouteSelection = true
      coordinator.publish(.selectRoute(turnID: turn.id, route: .deepgramBatch))

      XCTAssertEqual(
        coordinator.model.turn?.route,
        .undecided,
        "a nested event must not mutate the model until the current snapshot returns"
      )
    }

    let turnID = coordinator.begin(intent: .hold)

    XCTAssertEqual(maximumCallbackDepth, 1)
    XCTAssertEqual(coordinator.model.turn?.route, .deepgramBatch)
    XCTAssertEqual(
      coordinator.timelineSnapshot().suffix(2).map(\.event),
      ["start", "select_route"]
    )
    XCTAssertEqual(coordinator.activeTurnID, turnID)
  }

  func testEffectReentrantTerminalEventRunsAfterCurrentEffectReturns() {
    let coordinator = VoiceTurnCoordinator(scheduler: ManualVoiceTurnScheduler())
    let turnID = coordinator.begin(intent: .hold)
    let captureID = VoiceCaptureID(91)
    coordinator.publish(.captureStarted(turnID: turnID, captureID: captureID))

    var callbackDepth = 0
    var maximumCallbackDepth = 0
    var queuedCancellation = false
    var effects: [VoiceTurnEffect] = []
    coordinator.setEffectHandler { effect in
      callbackDepth += 1
      maximumCallbackDepth = max(maximumCallbackDepth, callbackDepth)
      effects.append(effect)
      defer { callbackDepth -= 1 }

      guard !queuedCancellation, effect == .stopCapture(turnID: turnID, captureID: captureID) else {
        return
      }
      queuedCancellation = true
      coordinator.publish(.cancel(turnID: turnID, reason: .cancelled))

      XCTAssertEqual(
        coordinator.model.turn?.phase,
        .finalizing,
        "a nested terminal event must wait until the current effect returns"
      )
    }

    coordinator.publish(.finalize(turnID: turnID))

    XCTAssertEqual(maximumCallbackDepth, 1)
    XCTAssertEqual(coordinator.model.turn?.phase, .terminal(.cancelled))
    XCTAssertEqual(
      effects.compactMap { effect -> VoiceTurnTerminalRecord? in
        if case .terminal(let terminal) = effect { return terminal }
        return nil
      },
      [.init(turnID: turnID, reason: .cancelled)]
    )
    XCTAssertEqual(
      coordinator.timelineSnapshot().suffix(2).map(\.event),
      ["finalize", "cancel"]
    )
  }

  func testResetCancelsOutstandingDeadlinesAndReturnsPresentationToIdle() {
    let scheduler = ManualVoiceTurnScheduler()
    let coordinator = VoiceTurnCoordinator(scheduler: scheduler)
    let barState = FloatingControlBarState()
    coordinator.configure(barState: barState)
    _ = coordinator.begin(intent: .hold)
    XCTAssertTrue(barState.isVoiceListening)
    XCTAssertGreaterThan(scheduler.activeCount, 0)

    coordinator.reset()

    XCTAssertNil(coordinator.activeTurn)
    XCTAssertNil(coordinator.model.turn)
    XCTAssertFalse(barState.isVoiceListening)
    XCTAssertEqual(scheduler.activeCount, 0)
  }

  func testStaleAndInvalidTransitionsRemainObservableEffects() {
    let coordinator = VoiceTurnCoordinator(scheduler: ManualVoiceTurnScheduler())
    var effects: [VoiceTurnEffect] = []
    coordinator.setEffectHandler { effects.append($0) }
    let turnID = coordinator.begin(intent: .hold)

    coordinator.publish(.finalize(turnID: VoiceTurnID()))
    coordinator.publish(
      .hubCommitAccepted(turnID: turnID, sessionID: VoiceSessionID(), responseID: nil))

    XCTAssertTrue(
      effects.contains(where: {
        if case .staleEventDropped = $0 { return true }
        return false
      }))
    XCTAssertTrue(
      effects.contains(where: {
        if case .invalidTransition = $0 { return true }
        return false
      }))
    XCTAssertEqual(coordinator.model.staleEventCount, 1)
    XCTAssertEqual(coordinator.model.invalidTransitionCount, 1)
  }

  func testDiagnosticLabelsAreStableAndLowCardinality() {
    let turnID = VoiceTurnID()
    let phases: [(VoiceTurnPhase, String)] = [
      (.idle, "idle"),
      (.pendingLockDecision, "pending_lock_decision"),
      (.recording, "recording"),
      (.lockedRecording, "locked_recording"),
      (.finalizing, "finalizing"),
      (.awaitingResponse, "awaiting_response"),
      (.awaitingTools, "awaiting_tools"),
      (.playing(.filler), "playing_filler"),
      (.terminal(.providerFailed), "terminal_provider_failed"),
    ]
    for (phase, expected) in phases {
      XCTAssertEqual(VoiceTurnCoordinator.phaseLabel(phase), expected)
    }

    let routes: [(VoiceTurnRoute, String)] = [
      (.undecided, "undecided"),
      (.hubWarmWait, "hub_warm_wait"),
      (.hub(sessionID: VoiceSessionID()), "hub"),
      (.omniSTT, "omni_stt"),
      (.deepgramBatch, "deepgram_batch"),
      (.deepgramLive, "deepgram_live"),
    ]
    for (route, expected) in routes {
      XCTAssertEqual(VoiceTurnCoordinator.routeLabel(route), expected, "turn=\(turnID)")
    }
  }

  func testTimelineNeverStoresAssociatedSpeechPayloads() {
    let coordinator = VoiceTurnCoordinator(scheduler: ManualVoiceTurnScheduler())
    let marker = "secret-timeline-marker-442"
    let turnID = coordinator.begin(intent: .hold)
    coordinator.publish(.transcriptChanged(turnID: turnID, text: marker))
    let staleID = VoiceTurnID()
    coordinator.publish(
      .playbackFailedScoped(
        turnID: staleID,
        identity: VoiceEffectIdentity(turnID: staleID, effectID: 1),
        leaseID: nil,
        message: marker))

    let events = coordinator.timelineSnapshot().map(\.event)
    XCTAssertTrue(events.contains("transcript_changed"))
    XCTAssertTrue(events.contains("playback_failed_scoped"))
    XCTAssertFalse(events.joined().contains(marker))
  }

  func testNonHubJournalAcceptanceWaitsForIndependentPlaybackFence() throws {
    DesktopDiagnosticsManager.shared.resetForTests()
    defer { DesktopDiagnosticsManager.shared.resetForTests() }
    let coordinator = VoiceTurnCoordinator(scheduler: ManualVoiceTurnScheduler())
    let turnID = coordinator.begin(intent: .hold)
    coordinator.publish(.selectRoute(turnID: turnID, route: .deepgramBatch))
    coordinator.publish(.finalize(turnID: turnID))
    coordinator.publish(.transcriptionStarted(turnID: turnID))
    coordinator.publish(.transcriptionFinal(turnID: turnID, text: "hello"))
    let providerIdentity = try XCTUnwrap(coordinator.activeTurn?.providerEffectIdentity)
    coordinator.publish(
      .providerResponseStartedScoped(
        turnID: turnID,
        identity: providerIdentity,
        sessionID: nil,
        responseID: nil))
    guard
      case .acquired(let lease) = coordinator.acquireOutput(
        .selectedVoiceFallback, turnID: turnID)
    else { return XCTFail("expected output lease") }
    let token = try XCTUnwrap(coordinator.nonHubCompletionToken(for: turnID))

    XCTAssertTrue(coordinator.completeNonHubProvider(token, outcome: .journalAccepted))
    XCTAssertEqual(coordinator.activeTurn?.phase, .playing(.selectedVoiceFallback))
    XCTAssertTrue(coordinator.activeTurn?.providerFinished == true)
    guard case .accepted = coordinator.activeTurn?.journalFinalization else {
      return XCTFail("canonical journal acceptance must be retained while playback drains")
    }

    XCTAssertTrue(coordinator.releaseOutput(lease))
    XCTAssertEqual(coordinator.model.lastTerminal?.turnID, turnID)
    XCTAssertEqual(coordinator.model.lastTerminal?.reason, .success)

    let url = try XCTUnwrap(DesktopDiagnosticsManager.shared.writeDiagnosticsAttachment())
    defer { try? FileManager.default.removeItem(at: url) }
    let data = try Data(contentsOf: url)
    let root = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
    let snapshots = try XCTUnwrap(root["snapshots"] as? [[String: Any]])
    let terminal = try XCTUnwrap(snapshots.first { $0["event"] as? String == "voice_turn_terminal" })
    XCTAssertEqual(terminal["response_outcome"] as? String, "success")
    XCTAssertNotNil(terminal["duration_ms"] as? Int)
  }

  func testDeliveredVoiceAnswerDoesNotBecomeResponseFailureWhenJournalFailsLater() throws {
    DesktopDiagnosticsManager.shared.resetForTests()
    defer { DesktopDiagnosticsManager.shared.resetForTests() }
    let coordinator = VoiceTurnCoordinator(scheduler: ManualVoiceTurnScheduler())
    let turnID = coordinator.begin(intent: .hold)
    coordinator.publish(.selectRoute(turnID: turnID, route: .deepgramBatch))
    coordinator.publish(.finalize(turnID: turnID))
    coordinator.publish(.transcriptionStarted(turnID: turnID))
    coordinator.publish(.transcriptionFinal(turnID: turnID, text: "hello"))
    let providerIdentity = try XCTUnwrap(coordinator.activeTurn?.providerEffectIdentity)
    coordinator.publish(
      .providerResponseStartedScoped(
        turnID: turnID,
        identity: providerIdentity,
        sessionID: nil,
        responseID: nil))
    guard
      case .acquired(let lease) = coordinator.acquireOutput(
        .selectedVoiceFallback, turnID: turnID)
    else { return XCTFail("expected output lease") }
    let token = try XCTUnwrap(coordinator.nonHubCompletionToken(for: turnID))

    XCTAssertTrue(coordinator.releaseOutput(lease))
    XCTAssertTrue(coordinator.completeNonHubProvider(token, outcome: .journalFailed))
    XCTAssertEqual(coordinator.model.lastTerminal?.reason, .journalFailed)

    let url = try XCTUnwrap(DesktopDiagnosticsManager.shared.writeDiagnosticsAttachment())
    defer { try? FileManager.default.removeItem(at: url) }
    let data = try Data(contentsOf: url)
    let root = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
    let snapshots = try XCTUnwrap(root["snapshots"] as? [[String: Any]])
    let terminal = try XCTUnwrap(snapshots.first { $0["event"] as? String == "voice_turn_terminal" })
    XCTAssertEqual(terminal["outcome"] as? String, "failure")
    XCTAssertEqual(terminal["response_outcome"] as? String, "success")
  }

  func testFillerDrainDoesNotHideLaterVoicePlaybackFailure() throws {
    DesktopDiagnosticsManager.shared.resetForTests()
    defer { DesktopDiagnosticsManager.shared.resetForTests() }
    let coordinator = VoiceTurnCoordinator(scheduler: ManualVoiceTurnScheduler())
    let turnID = coordinator.begin(intent: .hold)
    coordinator.publish(.selectRoute(turnID: turnID, route: .deepgramBatch))
    coordinator.publish(.finalize(turnID: turnID))
    coordinator.publish(.transcriptionStarted(turnID: turnID))
    coordinator.publish(.transcriptionFinal(turnID: turnID, text: "hello"))
    let providerIdentity = try XCTUnwrap(coordinator.activeTurn?.providerEffectIdentity)
    coordinator.publish(
      .providerResponseStartedScoped(
        turnID: turnID,
        identity: providerIdentity,
        sessionID: nil,
        responseID: nil))

    guard case .acquired(let filler) = coordinator.acquireOutput(.filler, turnID: turnID) else {
      return XCTFail("expected filler lease")
    }
    XCTAssertTrue(coordinator.releaseOutput(filler))
    guard
      case .acquired(let response) = coordinator.acquireOutput(
        .selectedVoiceFallback, turnID: turnID)
    else { return XCTFail("expected response lease") }

    coordinator.publish(
      .playbackFailedScoped(
        turnID: turnID,
        identity: response.identity,
        leaseID: response.id,
        message: "playback failed"))
    XCTAssertEqual(coordinator.model.lastTerminal?.reason, .playbackFailed)

    let url = try XCTUnwrap(DesktopDiagnosticsManager.shared.writeDiagnosticsAttachment())
    defer { try? FileManager.default.removeItem(at: url) }
    let data = try Data(contentsOf: url)
    let root = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
    let snapshots = try XCTUnwrap(root["snapshots"] as? [[String: Any]])
    let terminal = try XCTUnwrap(snapshots.first { $0["event"] as? String == "voice_turn_terminal" })
    XCTAssertEqual(terminal["outcome"] as? String, "failure")
    XCTAssertEqual(terminal["response_outcome"] as? String, "failure")
  }

  func testNonHubCompletionTokenCannotCloseReplacementTurn() throws {
    let coordinator = VoiceTurnCoordinator(scheduler: ManualVoiceTurnScheduler())
    let oldTurnID = coordinator.begin(intent: .hold)
    coordinator.publish(.selectRoute(turnID: oldTurnID, route: .deepgramBatch))
    coordinator.publish(.finalize(turnID: oldTurnID))
    coordinator.publish(.transcriptionStarted(turnID: oldTurnID))
    coordinator.publish(.transcriptionFinal(turnID: oldTurnID, text: "old"))
    let staleToken = try XCTUnwrap(coordinator.nonHubCompletionToken(for: oldTurnID))

    let newTurnID = coordinator.begin(intent: .hold)
    XCTAssertFalse(coordinator.completeNonHubProvider(staleToken, outcome: .journalAccepted))
    XCTAssertEqual(coordinator.activeTurnID, newTurnID)
    XCTAssertEqual(coordinator.activeTurn?.phase, .recording)
  }

  func testLateOldTurnGlowClearCannotMutateReplacementResponse() throws {
    let coordinator = VoiceTurnCoordinator(scheduler: ManualVoiceTurnScheduler())
    let barState = FloatingControlBarState()
    coordinator.configure(barState: barState)
    let oldTurnID = coordinator.begin(intent: .hold)

    let replacementTurnID = coordinator.begin(intent: .hold)
    coordinator.publish(.selectRoute(turnID: replacementTurnID, route: .deepgramBatch))
    coordinator.publish(.finalize(turnID: replacementTurnID))
    coordinator.publish(.transcriptionStarted(turnID: replacementTurnID))
    coordinator.publish(.transcriptionFinal(turnID: replacementTurnID, text: "replacement"))
    let providerIdentity = try XCTUnwrap(coordinator.activeTurn?.providerEffectIdentity)
    coordinator.publish(
      .providerResponseStartedScoped(
        turnID: replacementTurnID,
        identity: providerIdentity,
        sessionID: nil,
        responseID: nil))
    XCTAssertTrue(barState.isVoiceResponseActive)

    coordinator.publish(.responseActiveChanged(turnID: oldTurnID, active: false))

    XCTAssertEqual(coordinator.activeTurnID, replacementTurnID)
    XCTAssertTrue(barState.isVoiceResponseActive)
    XCTAssertEqual(coordinator.model.staleEventCount, 1)
  }

  func testPendingHubCommitIsAlreadyOwnedInsteadOfEligibleForBatchFallback() {
    let coordinator = VoiceTurnCoordinator(scheduler: ManualVoiceTurnScheduler())
    let turnID = coordinator.begin(intent: .hold)
    coordinator.publish(.selectRoute(turnID: turnID, route: .hub(sessionID: VoiceSessionID())))
    coordinator.publish(.finalize(turnID: turnID))
    coordinator.publish(.hubCommitClaimed(turnID: turnID))

    XCTAssertFalse(coordinator.canCommitHubTurn(turnID))
    XCTAssertTrue(
      RealtimeHubCommitOwnershipPolicy.isAlreadyOwned(
        turn: coordinator.activeTurn,
        requestedTurnID: turnID))
  }

  func testFinalizingHubTurnIsNotClassifiedAsAlreadyOwned() {
    let coordinator = VoiceTurnCoordinator(scheduler: ManualVoiceTurnScheduler())
    let turnID = coordinator.begin(intent: .hold)
    coordinator.publish(.selectRoute(turnID: turnID, route: .hub(sessionID: VoiceSessionID())))
    coordinator.publish(.finalize(turnID: turnID))

    XCTAssertTrue(coordinator.canCommitHubTurn(turnID))
    XCTAssertFalse(
      RealtimeHubCommitOwnershipPolicy.isAlreadyOwned(
        turn: coordinator.activeTurn,
        requestedTurnID: turnID))
  }
}

@MainActor
private final class ManualVoiceTurnCancellation: VoiceTurnDeadlineCancellation {
  var isCancelled = false

  func cancel() {
    isCancelled = true
  }
}

@MainActor
private final class ManualVoiceTurnScheduler: VoiceTurnDeadlineScheduling {
  private struct Scheduled {
    let deadline: VoiceTurnDeadline
    let cancellation: ManualVoiceTurnCancellation
    let action: @MainActor () -> Void
  }

  private var scheduled: [Scheduled] = []

  var activeCount: Int {
    scheduled.filter { !$0.cancellation.isCancelled }.count
  }

  func schedule(
    deadline: VoiceTurnDeadline,
    after interval: TimeInterval,
    action: @escaping @MainActor () -> Void
  )
    -> VoiceTurnDeadlineCancellation
  {
    _ = interval
    let cancellation = ManualVoiceTurnCancellation()
    scheduled.append(.init(deadline: deadline, cancellation: cancellation, action: action))
    return cancellation
  }

  func fire(deadline: VoiceTurnDeadline) {
    guard
      let index = scheduled.firstIndex(where: {
        $0.deadline == deadline && !$0.cancellation.isCancelled
      })
    else { return }
    let item = scheduled.remove(at: index)
    item.action()
  }
}
