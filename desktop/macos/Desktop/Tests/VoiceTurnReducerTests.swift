import XCTest

@testable import Omi_Computer

// Test-only convenience. Production leases have no initializer that can mint
// an identity outside VoiceTurnCoordinator.
extension VoiceOutputLease {
  init(id: VoiceLeaseID, turnID: VoiceTurnID, lane: VoiceOutputLane) {
    self.init(
      id: id,
      turnID: turnID,
      lane: lane,
      identity: VoiceEffectIdentity(turnID: turnID, effectID: UInt64.max))
  }
}

final class VoiceTurnReducerTests: XCTestCase {
  private enum DriverFact {
    case providerResponseStarted(
      turnID: VoiceTurnID, sessionID: VoiceSessionID?, responseID: VoiceResponseID?)
    case providerTurnFinished(
      turnID: VoiceTurnID, sessionID: VoiceSessionID?, responseID: VoiceResponseID?)
    case toolStarted(turnID: VoiceTurnID, callID: VoiceToolCallID)
    case toolFinished(turnID: VoiceTurnID, callID: VoiceToolCallID)
    case playbackStarted(turnID: VoiceTurnID, lease: VoiceOutputLease)
    case playbackDrained(turnID: VoiceTurnID, leaseID: VoiceLeaseID)
    case playbackFailed(turnID: VoiceTurnID, leaseID: VoiceLeaseID?, message: String)
  }
  private let reducer = VoiceTurnReducer()

  func testHappyHubTurnTransitionsThroughPlaybackAndTerminatesExactlyOnce() throws {
    let turnID = VoiceTurnID()
    let captureID = VoiceCaptureID(7)
    let sessionID = VoiceSessionID()
    let responseID = VoiceResponseID("response-1")
    let lease = VoiceOutputLease(id: VoiceLeaseID(), turnID: turnID, lane: .nativeRealtime)
    var model = VoiceTurnModel.idle

    model = reduce(model, .start(turnID: turnID, ownerID: nil, intent: .hold)).model
    XCTAssertEqual(model.turn?.phase, .recording)
    XCTAssertEqual(model.turn?.projection.isListening, true)

    model = reduce(model, .captureStarted(turnID: turnID, captureID: captureID)).model
    model = reduce(model, .selectRoute(turnID: turnID, route: .hub(sessionID: sessionID))).model
    model = reduce(model, .finalize(turnID: turnID)).model
    XCTAssertEqual(model.turn?.phase, .finalizing)

    model =
      reduce(
        model,
        .hubCommitAccepted(turnID: turnID, sessionID: sessionID, responseID: responseID)
      ).model
    XCTAssertEqual(model.turn?.phase, .awaitingResponse)
    XCTAssertEqual(model.turn?.projection.isResponseWaiting, true)

    model =
      reduce(
        model,
        .providerResponseStarted(turnID: turnID, sessionID: sessionID, responseID: responseID)
      ).model
    XCTAssertEqual(model.turn?.projection.isThinking, false)

    model = reduce(model, .playbackStarted(turnID: turnID, lease: lease)).model
    XCTAssertEqual(model.turn?.phase, .playing(.nativeRealtime))
    XCTAssertEqual(model.turn?.activeLease?.id, lease.id)
    XCTAssertEqual(model.turn?.activeLease?.lane, lease.lane)

    model =
      reduce(
        model,
        .providerTurnFinished(turnID: turnID, sessionID: sessionID, responseID: responseID)
      ).model

    let drained = reduce(model, .playbackDrained(turnID: turnID, leaseID: lease.id))
    XCTAssertEqual(drained.model.turn?.phase, .awaitingJournal)
    let accepted = acceptJournal(drained.model)
    XCTAssertEqual(accepted.model.turn?.phase, .terminal(.success))
    XCTAssertEqual(
      accepted.model.lastTerminal,
      .init(turnID: turnID, reason: .success, route: .hub(sessionID: sessionID)))
    XCTAssertEqual(accepted.effects.filter(\.isTerminal).count, 1)

    let duplicate = reduce(accepted.model, .finish(turnID: turnID, reason: .success))
    XCTAssertEqual(duplicate.model.duplicateTerminalCount, 1)
    XCTAssertFalse(duplicate.effects.contains(where: \.isTerminal))
  }

  func testOpenAISessionRotationTerminatesActiveHubTurnOnce() {
    let turnID = VoiceTurnID()
    let sessionID = VoiceSessionID()
    let category = RealtimeHubCloseClassifier.category(
      message: "Your session hit the maximum duration of 60 minutes.",
      aliveFor: 60 * 60,
      hasActiveTurn: true,
      provider: .openai)
    XCTAssertEqual(
      RealtimeHubCloseClassifier.sessionRotationPlan(
        for: category,
        hasActiveTurn: true),
      .terminateActiveTurnAndRewarm)

    var model = reduce(.idle, .start(turnID: turnID, ownerID: nil, intent: .hold)).model
    model = reduce(model, .selectRoute(turnID: turnID, route: .hub(sessionID: sessionID))).model

    let terminal = reduce(model, .finish(turnID: turnID, reason: .providerFailed))
    XCTAssertEqual(terminal.model.turn?.phase, .terminal(.providerFailed))
    XCTAssertEqual(terminal.effects.filter(\.isTerminal).count, 1)

    let duplicate = reduce(terminal.model, .finish(turnID: turnID, reason: .providerFailed))
    XCTAssertEqual(duplicate.model.duplicateTerminalCount, 1)
    XCTAssertFalse(duplicate.effects.contains(where: \.isTerminal))
  }

  func testQuickTapLockWindowCanBecomeLockedRecording() {
    let turnID = VoiceTurnID()
    var model = reduce(.idle, .start(turnID: turnID, ownerID: nil, intent: .hold)).model

    model = reduce(model, .openLockWindow(turnID: turnID)).model
    XCTAssertEqual(model.turn?.phase, .pendingLockDecision)
    XCTAssertTrue(model.turn?.deadlines.contains(.lockDecision) == true)

    let locked = reduce(model, .lock(turnID: turnID))
    XCTAssertEqual(locked.model.turn?.phase, .lockedRecording)
    XCTAssertEqual(locked.model.turn?.intent, .locked)
    XCTAssertEqual(locked.model.turn?.projection.isLocked, true)
    XCTAssertTrue(locked.effects.contains(.cancelDeadline(turnID: turnID, deadline: .lockDecision)))
  }

  func testLockWindowDeadlineFinalizesAndStopsCapture() {
    let turnID = VoiceTurnID()
    let captureID = VoiceCaptureID(8)
    var model = reduce(.idle, .start(turnID: turnID, ownerID: nil, intent: .hold)).model
    model = reduce(model, .captureStarted(turnID: turnID, captureID: captureID)).model
    model = reduce(model, .openLockWindow(turnID: turnID)).model

    let result = reduce(model, .deadlineFired(turnID: turnID, deadline: .lockDecision))

    XCTAssertEqual(result.model.turn?.phase, .finalizing)
    XCTAssertTrue(result.effects.contains(.stopCapture(turnID: turnID, captureID: captureID)))
  }

  func testLateCaptureStartAfterFinalizationIsStoppedAndCannotResurrectTurn() {
    let turnID = VoiceTurnID()
    var model = reduce(.idle, .start(turnID: turnID, ownerID: nil, intent: .hold)).model
    model = reduce(model, .finalize(turnID: turnID)).model
    let lateCaptureID = VoiceCaptureID(99)

    let result = reduce(model, .captureStarted(turnID: turnID, captureID: lateCaptureID))

    XCTAssertEqual(result.model.turn?.phase, .finalizing)
    XCTAssertNil(result.model.turn?.captureID)
    XCTAssertEqual(result.model.staleEventCount, 1)
    XCTAssertTrue(result.effects.contains(.stopCapture(turnID: turnID, captureID: lateCaptureID)))
  }

  func testBargeInFromAwaitingResponseStartsNewRecordingTurnAndDropsOldCallbacks() {
    let oldTurnID = VoiceTurnID()
    let newTurnID = VoiceTurnID()
    let sessionID = VoiceSessionID()
    var model = reduce(.idle, .start(turnID: oldTurnID, ownerID: nil, intent: .hold)).model
    model = reduce(model, .selectRoute(turnID: oldTurnID, route: .hub(sessionID: sessionID))).model
    model = reduce(model, .finalize(turnID: oldTurnID)).model
    model = reduce(
      model,
      .hubCommitAccepted(turnID: oldTurnID, sessionID: sessionID, responseID: nil)
    ).model
    XCTAssertEqual(model.turn?.phase, .awaitingResponse)
    XCTAssertTrue(
      PushToTalkManager.admitsListeningStart(
        activeTurnID: oldTurnID,
        phase: model.turn?.phase))

    let bargeIn = reduce(model, .start(turnID: newTurnID, ownerID: nil, intent: .hold))
    model = bargeIn.model
    XCTAssertEqual(model.turn?.id, newTurnID)
    XCTAssertEqual(model.turn?.phase, .recording)
    XCTAssertEqual(
      model.lastTerminal,
      .init(turnID: oldTurnID, reason: .interruptedByBargeIn, route: .hub(sessionID: sessionID)))
    XCTAssertTrue(
      bargeIn.effects.contains(
        .terminal(.init(turnID: oldTurnID, reason: .interruptedByBargeIn, route: .hub(sessionID: sessionID)))))

    let stale = reduce(model, .transcriptionFinal(turnID: oldTurnID, text: "old"))
    XCTAssertEqual(stale.model.turn?.id, newTurnID)
    XCTAssertEqual(stale.model.turn?.projection.transcript, "")
    XCTAssertEqual(stale.model.staleEventCount, 1)
  }

  func testListeningStartAdmissionPreservesIdleAndExistingCaptureExclusivity() {
    let turnID = VoiceTurnID()

    XCTAssertTrue(PushToTalkManager.admitsListeningStart(activeTurnID: nil, phase: nil))
    XCTAssertTrue(
      PushToTalkManager.admitsListeningStart(
        activeTurnID: turnID,
        phase: .pendingLockDecision))
    XCTAssertFalse(
      PushToTalkManager.admitsListeningStart(activeTurnID: turnID, phase: .recording))
    XCTAssertFalse(
      PushToTalkManager.admitsListeningStart(activeTurnID: turnID, phase: .lockedRecording))
    XCTAssertFalse(
      PushToTalkManager.admitsListeningStart(activeTurnID: turnID, phase: .finalizing))
  }

  func testHubBargeInPreservesProviderRuntimeForAtomicHandoff() {
    let oldTurnID = VoiceTurnID()
    let newTurnID = VoiceTurnID()
    let sessionID = VoiceSessionID()
    var model = reduce(.idle, .start(turnID: oldTurnID, ownerID: nil, intent: .hold)).model
    model = reduce(model, .selectRoute(turnID: oldTurnID, route: .hub(sessionID: sessionID))).model

    let result = reduce(model, .start(turnID: newTurnID, ownerID: nil, intent: .hold))

    XCTAssertEqual(result.model.lastTerminal?.route, .hub(sessionID: sessionID))
    XCTAssertFalse(
      result.effects.contains(
        .cancelHub(turnID: oldTurnID, route: .hub(sessionID: sessionID))))
    XCTAssertFalse(
      result.effects.contains { effect in
        if case .stopPlayback(let lease) = effect { return lease.turnID == oldTurnID }
        return false
      })
  }

  func testHubWarmTimeoutFallsBackWithoutTerminatingOrDroppingTurn() {
    let turnID = VoiceTurnID()
    var model = reduce(.idle, .start(turnID: turnID, ownerID: nil, intent: .hold)).model
    model = reduce(model, .selectRoute(turnID: turnID, route: .hubWarmWait)).model
    model = reduce(model, .finalize(turnID: turnID)).model

    let timedOut = reduce(model, .deadlineFired(turnID: turnID, deadline: .hubWarm))

    XCTAssertEqual(timedOut.model.turn?.route, .deepgramBatch)
    XCTAssertEqual(timedOut.model.turn?.phase, .finalizing)
    XCTAssertNil(timedOut.model.turn?.terminalReason)
    XCTAssertTrue(
      timedOut.effects.contains(.fallbackToTranscription(turnID: turnID, reason: .hubWarmTimeout)))
  }

  func testBufferedReconnectSupersedesGenericHubWarmDeadline() {
    let turnID = VoiceTurnID()
    var model = reduce(.idle, .start(turnID: turnID, ownerID: nil, intent: .hold)).model
    model = reduce(model, .selectRoute(turnID: turnID, route: .hubWarmWait)).model
    let reservation = reserveIdentity(model, turnID: turnID)

    let reconnecting = reduce(
      reservation.model,
      .providerReconnectStarted(
        turnID: turnID,
        identity: reservation.identity,
        previousSessionID: nil))

    XCTAssertFalse(reconnecting.model.turn?.deadlines.contains(.hubWarm) == true)
    XCTAssertTrue(reconnecting.model.turn?.deadlines.contains(.providerReconnect) == true)
  }

  func testWarmManagerBufferRemainsRoutableUntilItsPrepareEffectFlushesIt() {
    let turnID = VoiceTurnID()
    let sessionID = VoiceSessionID()
    var model = reduce(.idle, .start(turnID: turnID, ownerID: nil, intent: .hold)).model
    model = reduce(model, .selectRoute(turnID: turnID, route: .hubWarmWait)).model
    let reservation = reserveIdentity(model, turnID: turnID)
    model = reduce(
      reservation.model,
      .providerReconnectStarted(
        turnID: turnID,
        identity: reservation.identity,
        previousSessionID: nil)).model

    let reconnected = reduce(
      model,
      .providerReconnected(
        turnID: turnID,
        identity: reservation.identity,
        sessionID: sessionID))

    XCTAssertEqual(reconnected.model.turn?.providerConnection, .ready)
    XCTAssertEqual(reconnected.model.turn?.sessionID, sessionID)
    XCTAssertEqual(reconnected.model.turn?.route, .hubWarmWait)

    let ready = reduce(reconnected.model, .hubReady(turnID: turnID, sessionID: sessionID))
    XCTAssertEqual(ready.model.turn?.route, .hub(sessionID: sessionID))
    XCTAssertTrue(ready.effects.contains(.prepareHubInput(turnID: turnID, sessionID: sessionID)))
  }

  func testTransportReadyBindsHubRouteAndPreparesContext() {
    let turnID = VoiceTurnID()
    let sessionID = VoiceSessionID()
    var model = reduce(.idle, .start(turnID: turnID, ownerID: nil, intent: .hold)).model
    model = reduce(model, .selectRoute(turnID: turnID, route: .hubWarmWait)).model

    let ready = reduce(model, .hubReady(turnID: turnID, sessionID: sessionID))

    XCTAssertEqual(ready.model.turn?.route, .hub(sessionID: sessionID))
    XCTAssertEqual(ready.model.turn?.sessionID, sessionID)
    XCTAssertEqual(ready.model.turn?.phase, .recording)
    XCTAssertTrue(ready.effects.contains(.cancelDeadline(turnID: turnID, deadline: .hubWarm)))
    XCTAssertTrue(ready.effects.contains(.prepareHubInput(turnID: turnID, sessionID: sessionID)))

    // Binding the route is not an admission grant. `prepareHubInput` opens the
    // context-fresh preparation the driver fences audio behind, so the provider
    // connection is still closed until `providerReconnected` admits the input.
    let reservation = reserveIdentity(ready.model, turnID: turnID)
    let preparing = reduce(
      reservation.model,
      .providerReconnectStarted(
        turnID: turnID,
        identity: reservation.identity,
        previousSessionID: sessionID))
    XCTAssertEqual(
      preparing.model.turn?.providerConnection,
      .reconnecting(identity: reservation.identity, previousSessionID: sessionID))
  }

  /// A turn released while the socket was still warming commits through
  /// `commitBufferedRealtimeHubTurn`, which the PTT driver gates on a `.hub`
  /// route. Leaving the route in warm-wait after `hubReady` stranded the turn in
  /// `finalizing` forever — no commit, no reply, no transcription fallback.
  func testBufferedWarmWaitTurnStaysCommittableAfterTransportReady() {
    let turnID = VoiceTurnID()
    let sessionID = VoiceSessionID()
    var model = reduce(.idle, .start(turnID: turnID, ownerID: nil, intent: .hold)).model
    model = reduce(model, .selectRoute(turnID: turnID, route: .hubWarmWait)).model
    model = reduce(model, .finalize(turnID: turnID)).model
    model = reduce(model, .hubReady(turnID: turnID, sessionID: sessionID)).model

    XCTAssertEqual(model.turn?.phase, .finalizing)
    XCTAssertEqual(model.turn?.route, .hub(sessionID: sessionID))
    XCTAssertFalse(model.turn?.hubCommitPending == true)

    // The driver now owns the hub turn, so its deferred commit is accepted and
    // the replayed audio is committed once admission lands.
    let deferred = reduce(model, .hubCommitDeferred(turnID: turnID))
    XCTAssertTrue(deferred.model.turn?.hubCommitPending == true)
  }

  func testHubAdmissionRejectionAfterTransportReadyFallsBackAfterRelease() {
    let turnID = VoiceTurnID()
    let sessionID = VoiceSessionID()
    var model = reduce(.idle, .start(turnID: turnID, ownerID: nil, intent: .hold)).model
    model = reduce(model, .selectRoute(turnID: turnID, route: .hubWarmWait)).model
    model = reduce(model, .hubReady(turnID: turnID, sessionID: sessionID)).model
    model = reduce(model, .finalize(turnID: turnID)).model

    let rejected = reduce(model, .hubAdmissionRejected(turnID: turnID))

    XCTAssertEqual(rejected.model.turn?.phase, .finalizing)
    XCTAssertEqual(rejected.model.turn?.route, .deepgramBatch)
    XCTAssertFalse(rejected.model.turn?.deadlines.contains(.hubWarm) == true)
    XCTAssertTrue(rejected.model.turn?.deadlines.contains(.transcription) == true)
    XCTAssertTrue(
      rejected.effects.contains(
        .fallbackToTranscription(turnID: turnID, reason: .hubWarmTimeout)))
  }

  func testDeferredCommitTimeoutTerminatesWithTypedReason() {
    let turnID = VoiceTurnID()
    let sessionID = VoiceSessionID()
    var model = reduce(.idle, .start(turnID: turnID, ownerID: nil, intent: .hold)).model
    model = reduce(model, .selectRoute(turnID: turnID, route: .hub(sessionID: sessionID))).model
    model = reduce(model, .finalize(turnID: turnID)).model
    model = reduce(model, .hubCommitDeferred(turnID: turnID)).model

    let result = reduce(model, .deadlineFired(turnID: turnID, deadline: .deferredCommit))

    XCTAssertEqual(result.model.turn?.phase, .terminal(.deferredCommitTimeout))
    XCTAssertEqual(result.model.lastTerminal?.reason, .deferredCommitTimeout)
  }

  func testBargeInReplacementCommitHasDistinctDeadlineAndCanResumeOnFreshSession() {
    let turnID = VoiceTurnID()
    let oldSessionID = VoiceSessionID()
    let replacementSessionID = VoiceSessionID()
    var model = reduce(.idle, .start(turnID: turnID, ownerID: nil, intent: .hold)).model
    model = reduce(model, .selectRoute(turnID: turnID, route: .hub(sessionID: oldSessionID))).model
    model = reduce(model, .finalize(turnID: turnID)).model

    let deferred = reduce(model, .hubCommitDeferredForReplacement(turnID: turnID))
    XCTAssertEqual(deferred.model.turn?.phase, .awaitingResponse)
    XCTAssertTrue(deferred.model.turn?.hubCommitPending == true)
    XCTAssertTrue(deferred.model.turn?.deadlines.contains(.bargeInReplacement) == true)
    XCTAssertFalse(deferred.model.turn?.deadlines.contains(.deferredCommit) == true)

    let accepted = reduce(
      deferred.model,
      .hubCommitAccepted(
        turnID: turnID,
        sessionID: replacementSessionID,
        responseID: nil))
    XCTAssertEqual(accepted.model.turn?.sessionID, replacementSessionID)
    XCTAssertFalse(accepted.model.turn?.hubCommitPending == true)
    XCTAssertFalse(accepted.model.turn?.deadlines.contains(.bargeInReplacement) == true)
    XCTAssertTrue(accepted.model.turn?.deadlines.contains(.providerResponse) == true)
    XCTAssertTrue(
      accepted.effects.contains(
        .cancelDeadline(turnID: turnID, deadline: .bargeInReplacement)))

    let duplicate = reduce(
      accepted.model,
      .hubCommitAccepted(
        turnID: turnID,
        sessionID: replacementSessionID,
        responseID: nil))
    XCTAssertEqual(duplicate.model.invalidTransitionCount, accepted.model.invalidTransitionCount + 1)
  }

  func testNormalHubCommitMustBeReducerClaimedBeforeProviderSideEffects() {
    let turnID = VoiceTurnID()
    let sessionID = VoiceSessionID()
    var model = reduce(.idle, .start(turnID: turnID, ownerID: nil, intent: .hold)).model
    model = reduce(model, .selectRoute(turnID: turnID, route: .hub(sessionID: sessionID))).model
    model = reduce(model, .finalize(turnID: turnID)).model

    let claimed = reduce(model, .hubCommitClaimed(turnID: turnID))
    XCTAssertEqual(claimed.model.turn?.phase, .awaitingResponse)
    XCTAssertTrue(claimed.model.turn?.hubCommitPending == true)
    XCTAssertNil(claimed.model.turn?.providerEffectIdentity)
    XCTAssertTrue(claimed.effects.contains(.commitClaimedHubInput(turnID: turnID)))

    let accepted = reduce(
      claimed.model,
      .hubCommitAccepted(turnID: turnID, sessionID: sessionID, responseID: nil))
    XCTAssertFalse(accepted.model.turn?.hubCommitPending == true)
    XCTAssertNotNil(accepted.model.turn?.providerEffectIdentity)

    let duplicateClaim = reduce(accepted.model, .hubCommitClaimed(turnID: turnID))
    XCTAssertEqual(
      duplicateClaim.model.invalidTransitionCount,
      accepted.model.invalidTransitionCount + 1)
  }

  func testClaimedHubCommitDefersPhysicalDriverUntilReducerStateIsApplied() {
    let turnID = VoiceTurnID()
    let sessionID = VoiceSessionID()
    var model = reduce(.idle, .start(turnID: turnID, ownerID: nil, intent: .hold)).model
    model = reduce(model, .selectRoute(turnID: turnID, route: .hub(sessionID: sessionID))).model
    model = reduce(model, .finalize(turnID: turnID)).model

    let claimed = reduce(model, .hubCommitClaimed(turnID: turnID))

    XCTAssertEqual(claimed.model.turn?.phase, .awaitingResponse)
    XCTAssertTrue(claimed.model.turn?.hubCommitPending == true)
    XCTAssertEqual(claimed.effects, [.commitClaimedHubInput(turnID: turnID)])
  }

  func testBargeInReplacementDeadlineTerminatesWithTypedReason() {
    let turnID = VoiceTurnID()
    var model = reduce(.idle, .start(turnID: turnID, ownerID: nil, intent: .hold)).model
    model = reduce(model, .selectRoute(turnID: turnID, route: .hub(sessionID: nil))).model
    model = reduce(model, .finalize(turnID: turnID)).model
    model = reduce(model, .hubCommitDeferredForReplacement(turnID: turnID)).model

    let result = reduce(
      model,
      .deadlineFired(turnID: turnID, deadline: .bargeInReplacement))

    XCTAssertEqual(result.model.turn?.phase, .terminal(.bargeInReplacementTimeout))
    XCTAssertEqual(result.model.lastTerminal?.reason, .bargeInReplacementTimeout)
  }

  func testStaleBargeInReplacementDeadlineCannotTerminalizeAdvancedTurn() {
    let turnID = VoiceTurnID()
    var model = reduce(.idle, .start(turnID: turnID, ownerID: nil, intent: .hold)).model
    model = reduce(model, .selectRoute(turnID: turnID, route: .hub(sessionID: nil))).model
    model = reduce(model, .finalize(turnID: turnID)).model
    model = reduce(model, .hubCommitDeferredForReplacement(turnID: turnID)).model
    model.turn?.phase = .finalizing

    let stale = reduce(
      model,
      .deadlineFired(turnID: turnID, deadline: .bargeInReplacement))

    XCTAssertEqual(stale.model.turn?.phase, .finalizing)
    XCTAssertEqual(stale.model.staleEventCount, model.staleEventCount + 1)
    XCTAssertFalse(stale.effects.contains(where: \.isTerminal))
  }

  func testProviderNoResponseDeadlineTerminatesAndShowsActionableHint() {
    let (model, turnID, _, _) = awaitingHubResponse()

    let result = reduce(model, .deadlineFired(turnID: turnID, deadline: .providerResponse))

    XCTAssertEqual(result.model.turn?.phase, .terminal(.providerNoResponse))
    XCTAssertEqual(result.model.turn?.projection.isListening, false)
    XCTAssertEqual(result.model.turn?.projection.isThinking, false)
    XCTAssertEqual(result.model.turn?.projection.isResponseActive, false)
    XCTAssertEqual(result.model.turn?.projection.hint, "Couldn't get a voice reply — try again")
    XCTAssertTrue(result.model.turn?.deadlines.contains(.hintVisibility) == true)
  }

  func testProviderEventFromReplacedSessionIsDropped() {
    let (model, turnID, _, responseID) = awaitingHubResponse()
    let staleSession = VoiceSessionID()

    let result = reduce(
      model,
      .providerResponseStarted(turnID: turnID, sessionID: staleSession, responseID: responseID))

    XCTAssertEqual(result.model.turn?.phase, .awaitingResponse)
    XCTAssertEqual(result.model.staleEventCount, 1)
  }

  func testProviderEventFromReplacedResponseIsDropped() {
    let (model, turnID, sessionID, _) = awaitingHubResponse()

    let result = reduce(
      model,
      .providerResponseStarted(
        turnID: turnID,
        sessionID: sessionID,
        responseID: VoiceResponseID("stale")))

    XCTAssertEqual(result.model.turn?.phase, .awaitingResponse)
    XCTAssertEqual(result.model.staleEventCount, 1)
  }

  func testProviderCallbackMissingKnownIdentityIsDropped() {
    let (model, turnID, _, _) = awaitingHubResponse()

    let response = reduce(
      model,
      .providerResponseStarted(turnID: turnID, sessionID: nil, responseID: nil))
    let finished = reduce(
      model,
      .providerTurnFinished(turnID: turnID, sessionID: nil, responseID: nil))

    XCTAssertEqual(response.model.turn?.phase, .awaitingResponse)
    XCTAssertEqual(response.model.staleEventCount, 1)
    XCTAssertEqual(finished.model.turn?.phase, .awaitingResponse)
    XCTAssertEqual(finished.model.staleEventCount, 1)
  }

  func testProviderCanFinishSuccessfullyWithoutStartingPlayback() {
    let (model, turnID, sessionID, responseID) = awaitingHubResponse()

    let result = reduce(
      model,
      .providerTurnFinished(turnID: turnID, sessionID: sessionID, responseID: responseID))

    XCTAssertEqual(result.model.turn?.phase, .awaitingJournal)
    let accepted = acceptJournal(result.model)
    XCTAssertEqual(accepted.model.turn?.phase, .terminal(.success))
    XCTAssertEqual(accepted.model.lastTerminal?.reason, .success)
  }

  func testToolCompletionKeepsTurnOpenUntilEveryToolFinishes() {
    let (startingModel, turnID, sessionID, responseID) = awaitingHubResponse()
    var model = reduce(
      startingModel,
      .providerResponseStarted(turnID: turnID, sessionID: sessionID, responseID: responseID)
    ).model
    let first = VoiceToolCallID("first")
    let second = VoiceToolCallID("second")
    model = reduce(model, .toolStarted(turnID: turnID, callID: first)).model
    model = reduce(model, .toolStarted(turnID: turnID, callID: second)).model

    model = reduce(model, .toolFinished(turnID: turnID, callID: first)).model
    XCTAssertEqual(model.turn?.phase, .awaitingTools)
    XCTAssertEqual(model.turn?.pendingToolCallIDs, [second])

    let finished = reduce(model, .toolFinished(turnID: turnID, callID: second))
    XCTAssertEqual(finished.model.turn?.phase, .awaitingResponse)
    XCTAssertTrue(finished.model.turn?.pendingToolCallIDs.isEmpty == true)
    XCTAssertTrue(
      finished.effects.contains(.cancelDeadline(turnID: turnID, deadline: .pendingTools)))
    XCTAssertTrue(finished.model.turn?.deadlines.contains(.providerResponse) == true)
  }

  func testProviderFinishDuringToolWaitRequiresPostToolContinuationBeforeJournal() throws {
    let (startingModel, turnID, sessionID, responseID) = awaitingHubResponse()
    let callID = VoiceToolCallID("pending")
    var model = reduce(
      startingModel,
      .providerResponseStarted(turnID: turnID, sessionID: sessionID, responseID: responseID)
    ).model
    model = reduce(model, .toolStarted(turnID: turnID, callID: callID)).model

    let providerFinished = reduce(
      model,
      .providerTurnFinished(turnID: turnID, sessionID: sessionID, responseID: responseID))
    XCTAssertEqual(providerFinished.model.turn?.phase, .awaitingTools)
    XCTAssertNil(providerFinished.model.lastTerminal)

    let toolFinished = reduce(
      providerFinished.model,
      .toolFinished(turnID: turnID, callID: callID))
    XCTAssertEqual(toolFinished.model.turn?.phase, .awaitingResponse)
    XCTAssertEqual(toolFinished.model.turn?.journalFinalization, .pending)
    XCTAssertFalse(toolFinished.model.turn?.providerFinished == true)

    let providerIdentity = try XCTUnwrap(toolFinished.model.turn?.providerEffectIdentity)
    var continuation = reduce(
      toolFinished.model,
      .providerResponseStartedScoped(
        turnID: turnID,
        identity: providerIdentity,
        sessionID: sessionID,
        responseID: responseID)).model
    continuation = reduce(
      continuation,
      .providerTurnFinishedScoped(
        turnID: turnID,
        identity: providerIdentity,
        sessionID: sessionID,
        responseID: responseID)).model
    guard case .writing = continuation.turn?.journalFinalization else {
      return XCTFail("the post-tool answer must open the journal fence")
    }
    let accepted = acceptJournal(continuation)
    XCTAssertEqual(accepted.model.turn?.phase, .terminal(.success))
    XCTAssertEqual(accepted.model.lastTerminal?.reason, .success)
  }

  func testLateToolCycleFinishStillCannotSkipPostToolContinuation() throws {
    let (startingModel, turnID, sessionID, responseID) = awaitingHubResponse()
    let callID = VoiceToolCallID("fast-tool")
    var model = reduce(
      startingModel,
      .providerResponseStarted(turnID: turnID, sessionID: sessionID, responseID: responseID)
    ).model
    model = reduce(model, .toolStarted(turnID: turnID, callID: callID)).model
    model = reduce(model, .toolFinished(turnID: turnID, callID: callID)).model
    XCTAssertTrue(model.turn?.postToolContinuationRequired == true)

    let delayedCycleFinish = reduce(
      model,
      .providerTurnFinished(turnID: turnID, sessionID: sessionID, responseID: responseID))
    XCTAssertEqual(delayedCycleFinish.model.turn?.phase, .awaitingResponse)
    XCTAssertEqual(delayedCycleFinish.model.turn?.journalFinalization, .pending)
    XCTAssertFalse(delayedCycleFinish.model.turn?.providerFinished == true)

    let providerIdentity = try XCTUnwrap(delayedCycleFinish.model.turn?.providerEffectIdentity)
    var continuation = reduce(
      delayedCycleFinish.model,
      .providerResponseStartedScoped(
        turnID: turnID,
        identity: providerIdentity,
        sessionID: sessionID,
        responseID: responseID)).model
    XCTAssertFalse(continuation.turn?.postToolContinuationRequired == true)
    continuation = reduce(
      continuation,
      .providerTurnFinishedScoped(
        turnID: turnID,
        identity: providerIdentity,
        sessionID: sessionID,
        responseID: responseID)).model
    guard case .writing = continuation.turn?.journalFinalization else {
      return XCTFail("only the post-tool answer may open the journal fence")
    }
  }

  func testToolAndPlaybackCanDrainInEitherOrderWithoutClosingEarly() throws {
    let (startingModel, turnID, sessionID, responseID) = awaitingHubResponse()
    let callID = VoiceToolCallID("tool")
    let lease = VoiceOutputLease(id: VoiceLeaseID(), turnID: turnID, lane: .nativeRealtime)
    var model = reduce(
      startingModel,
      .providerResponseStarted(turnID: turnID, sessionID: sessionID, responseID: responseID)
    ).model
    model = reduce(model, .playbackStarted(turnID: turnID, lease: lease)).model
    model = reduce(model, .toolStarted(turnID: turnID, callID: callID)).model
    model =
      reduce(
        model,
        .providerTurnFinished(turnID: turnID, sessionID: sessionID, responseID: responseID)
      ).model

    let drained = reduce(model, .playbackDrained(turnID: turnID, leaseID: lease.id))
    XCTAssertEqual(drained.model.turn?.phase, .awaitingTools)
    XCTAssertNil(drained.model.lastTerminal)

    let finished = reduce(drained.model, .toolFinished(turnID: turnID, callID: callID))
    XCTAssertEqual(finished.model.turn?.phase, .awaitingResponse)
    XCTAssertEqual(finished.model.turn?.journalFinalization, .pending)

    let providerIdentity = try XCTUnwrap(finished.model.turn?.providerEffectIdentity)
    var continuation = reduce(
      finished.model,
      .providerResponseStartedScoped(
        turnID: turnID,
        identity: providerIdentity,
        sessionID: sessionID,
        responseID: responseID)).model
    continuation = reduce(
      continuation,
      .providerTurnFinishedScoped(
        turnID: turnID,
        identity: providerIdentity,
        sessionID: sessionID,
        responseID: responseID)).model
    XCTAssertEqual(acceptJournal(continuation).model.turn?.phase, .terminal(.success))
  }

  func testCanonicalSpawnReceiptCompletesWithoutProviderContinuation() throws {
    let (startingModel, turnID, sessionID, responseID) = awaitingHubResponse()
    let reservation = reserveIdentity(startingModel, turnID: turnID)
    let toolIdentity = reservation.identity
    let callID = VoiceToolCallID("spawn-agent")
    var model = reduce(
      reservation.model,
      .toolStartedScoped(turnID: turnID, identity: toolIdentity, callID: callID)
    ).model

    XCTAssertTrue(model.turn?.postToolContinuationRequired == true)
    XCTAssertTrue(model.turn?.deadlines.contains(.pendingTools) == true)
    XCTAssertFalse(model.turn?.deadlines.contains(.providerResponse) == true)

    model = reduce(
      model,
      .authoritativeLocalResultAcceptedScoped(
        turnID: turnID,
        identity: toolIdentity,
        callID: callID,
        kind: .spawnReceipt)
    ).model

    XCTAssertTrue(model.turn?.providerFinished == true)
    XCTAssertFalse(model.turn?.postToolContinuationRequired == true)
    guard case .writing = model.turn?.journalFinalization else {
      return XCTFail("the canonical receipt must open the journal fence")
    }

    let finished = reduce(
      model,
      .toolFinishedScoped(turnID: turnID, identity: toolIdentity, callID: callID)
    ).model
    let accepted = acceptJournal(finished)
    XCTAssertEqual(accepted.model.turn?.phase, .terminal(.success))
    XCTAssertEqual(accepted.model.lastTerminal?.reason, .success)
    XCTAssertEqual(accepted.model.lastTerminal?.route, .hub(sessionID: sessionID))
    XCTAssertEqual(accepted.model.turn?.responseID, responseID)
  }

  func testVerifiedScreenEvidenceRequiresProviderContinuationForTheOriginalRequest() throws {
    let (startingModel, turnID, sessionID, responseID) = awaitingHubResponse()
    let screenshotReservation = reserveIdentity(startingModel, turnID: turnID)
    let screenshotIdentity = screenshotReservation.identity
    let screenshotCallID = VoiceToolCallID("screenshot")
    var model = reduce(
      screenshotReservation.model,
      .toolStartedScoped(
        turnID: turnID,
        identity: screenshotIdentity,
        callID: screenshotCallID)).model
    let token = VoiceScreenEvidenceProtocolToken(
      turnID: turnID,
      screenshotCallID: screenshotCallID,
      screenshotIdentity: screenshotIdentity)
    model = reduce(
      model,
      .screenEvidenceProtocolStartedScoped(
        turnID: turnID,
        token: token,
        expiresAfter: 5)).model

    let reportReservation = reserveIdentity(model, turnID: turnID)
    let reportIdentity = reportReservation.identity
    let reportCallID = VoiceToolCallID("report")
    model = reduce(
      reportReservation.model,
      .toolStartedScoped(turnID: turnID, identity: reportIdentity, callID: reportCallID)).model
    let providerIdentity = try XCTUnwrap(model.turn?.providerEffectIdentity)
    model = reduce(
      model,
      .providerTurnFinishedScoped(
        turnID: turnID,
        identity: providerIdentity,
        sessionID: sessionID,
        responseID: responseID)).model
    XCTAssertEqual(model.turn?.phase, .awaitingTools)
    model = reduce(
      model,
      .screenEvidenceReportVerifiedScoped(
        turnID: turnID,
        screenshotIdentity: screenshotIdentity,
        screenshotCallID: screenshotCallID,
        reportIdentity: reportIdentity,
        reportCallID: reportCallID)
    ).model

    XCTAssertNil(model.turn?.screenEvidenceProtocol)
    XCTAssertFalse(model.turn?.providerFinished == true)
    XCTAssertTrue(model.turn?.postToolContinuationRequired == true)
    XCTAssertFalse(model.turn?.deadlines.contains(.providerResponse) == true)
    XCTAssertEqual(model.turn?.journalFinalization, .pending)

    model = reduce(
      model,
      .toolFinishedScoped(turnID: turnID, identity: screenshotIdentity, callID: screenshotCallID)
    ).model
    model = reduce(
      model,
      .toolFinishedScoped(turnID: turnID, identity: reportIdentity, callID: reportCallID)
    ).model
    XCTAssertEqual(model.turn?.phase, .awaitingResponse)
    XCTAssertTrue(model.turn?.deadlines.contains(.providerResponse) == true)
    XCTAssertEqual(model.turn?.journalFinalization, .pending)
  }

  func testFailedScreenEvidenceCompletesWithoutProviderContinuation() {
    let (startingModel, turnID, _, _) = awaitingHubResponse()
    let reservation = reserveIdentity(startingModel, turnID: turnID)
    let screenshotIdentity = reservation.identity
    let screenshotCallID = VoiceToolCallID("screenshot")
    var model = reduce(
      reservation.model,
      .toolStartedScoped(
        turnID: turnID,
        identity: screenshotIdentity,
        callID: screenshotCallID)).model
    let token = VoiceScreenEvidenceProtocolToken(
      turnID: turnID,
      screenshotCallID: screenshotCallID,
      screenshotIdentity: screenshotIdentity)
    model = reduce(
      model,
      .screenEvidenceProtocolStartedScoped(
        turnID: turnID,
        token: token,
        expiresAfter: 5)).model
    model = reduce(
      model,
      .authoritativeLocalResultAcceptedScoped(
        turnID: turnID,
        identity: screenshotIdentity,
        callID: screenshotCallID,
        kind: .screenEvidenceFailure)
    ).model

    XCTAssertNil(model.turn?.screenEvidenceProtocol)
    XCTAssertTrue(model.turn?.providerFinished == true)
    XCTAssertFalse(model.turn?.postToolContinuationRequired == true)
    XCTAssertFalse(model.turn?.deadlines.contains(.providerResponse) == true)

    model = reduce(
      model,
      .toolFinishedScoped(turnID: turnID, identity: screenshotIdentity, callID: screenshotCallID)
    ).model
    XCTAssertEqual(acceptJournal(model).model.turn?.phase, .terminal(.success))
  }

  func testFailedScreenEvidenceRejectsLateProviderToolWithoutReopeningTheTurn() {
    let (startingModel, turnID, _, _) = awaitingHubResponse()
    let screenshotReservation = reserveIdentity(startingModel, turnID: turnID)
    let screenshotIdentity = screenshotReservation.identity
    let screenshotCallID = VoiceToolCallID("screenshot")
    var model = reduce(
      screenshotReservation.model,
      .toolStartedScoped(
        turnID: turnID,
        identity: screenshotIdentity,
        callID: screenshotCallID)).model
    let token = VoiceScreenEvidenceProtocolToken(
      turnID: turnID,
      screenshotCallID: screenshotCallID,
      screenshotIdentity: screenshotIdentity)
    model = reduce(
      model,
      .screenEvidenceProtocolStartedScoped(
        turnID: turnID,
        token: token,
        expiresAfter: RealtimeScreenEvidenceProtocolPolicy.maximumReportWait)).model
    model = reduce(
      model,
      .authoritativeLocalResultAcceptedScoped(
        turnID: turnID,
        identity: screenshotIdentity,
        callID: screenshotCallID,
        kind: .screenEvidenceFailure)
    ).model

    let lateReportReservation = reserveIdentity(model, turnID: turnID)
    let lateReport = reduce(
      lateReportReservation.model,
      .toolStartedScoped(
        turnID: turnID,
        identity: lateReportReservation.identity,
        callID: VoiceToolCallID("report-screen-observation")))

    XCTAssertEqual(lateReport.model.staleEventCount, lateReportReservation.model.staleEventCount + 1)
    XCTAssertEqual(lateReport.model.turn?.pendingToolCallIDs, Set([screenshotCallID]))
    XCTAssertTrue(lateReport.model.turn?.providerFinished == true)
    XCTAssertFalse(lateReport.model.turn?.postToolContinuationRequired == true)

    model = reduce(
      lateReport.model,
      .toolFinishedScoped(turnID: turnID, identity: screenshotIdentity, callID: screenshotCallID)
    ).model
    XCTAssertEqual(acceptJournal(model).model.turn?.phase, .terminal(.success))
  }

  func testScreenEvidenceProtocolDeadlineEmitsExactFailureEffect() {
    let (startingModel, turnID, _, _) = awaitingHubResponse()
    let reservation = reserveIdentity(startingModel, turnID: turnID)
    let screenshotIdentity = reservation.identity
    let screenshotCallID = VoiceToolCallID("screenshot")
    var model = reduce(
      reservation.model,
      .toolStartedScoped(
        turnID: turnID,
        identity: screenshotIdentity,
        callID: screenshotCallID)).model
    let token = VoiceScreenEvidenceProtocolToken(
      turnID: turnID,
      screenshotCallID: screenshotCallID,
      screenshotIdentity: screenshotIdentity)
    model = reduce(
      model,
      .screenEvidenceProtocolStartedScoped(
        turnID: turnID,
        token: token,
        expiresAfter: 5)).model

    let expiration = reduce(
      model,
      .deadlineFired(turnID: turnID, deadline: .screenEvidenceProtocol))

    XCTAssertEqual(expiration.model.turn?.screenEvidenceProtocol, token)
    XCTAssertTrue(
      expiration.effects.contains(
        .screenEvidenceProtocolExpired(turnID: turnID, token: token)))
    XCTAssertFalse(expiration.effects.contains(where: \.isTerminal))
  }

  func testScreenEvidenceResolutionFromBargedTurnIsDropped() {
    let (startingModel, turnID, _, _) = awaitingHubResponse()
    let reservation = reserveIdentity(startingModel, turnID: turnID)
    let screenshotIdentity = reservation.identity
    let screenshotCallID = VoiceToolCallID("screenshot")
    var model = reduce(
      reservation.model,
      .toolStartedScoped(
        turnID: turnID,
        identity: screenshotIdentity,
        callID: screenshotCallID)).model
    let token = VoiceScreenEvidenceProtocolToken(
      turnID: turnID,
      screenshotCallID: screenshotCallID,
      screenshotIdentity: screenshotIdentity)
    model = reduce(
      model,
      .screenEvidenceProtocolStartedScoped(
        turnID: turnID,
        token: token,
        expiresAfter: 5)).model
    let replacementID = VoiceTurnID()
    model = reduce(model, .start(turnID: replacementID, ownerID: nil, intent: .hold)).model

    let stale = reduce(
      model,
      .authoritativeLocalResultAcceptedScoped(
        turnID: turnID,
        identity: screenshotIdentity,
        callID: screenshotCallID,
        kind: .screenEvidenceFailure))

    XCTAssertEqual(stale.model.turn?.id, replacementID)
    XCTAssertEqual(stale.model.turn?.phase, .recording)
    XCTAssertEqual(stale.model.staleEventCount, model.staleEventCount + 1)
  }

  func testProviderOutputCannotMutateRecordingTurnBeforeCommit() {
    let turnID = VoiceTurnID()
    let lease = VoiceOutputLease(id: VoiceLeaseID(), turnID: turnID, lane: .nativeRealtime)
    let recording = reduce(.idle, .start(turnID: turnID, ownerID: nil, intent: .hold)).model

    let response = reduce(
      recording,
      .providerResponseStarted(turnID: turnID, sessionID: VoiceSessionID(), responseID: nil))
    let playback = reduce(recording, .playbackStarted(turnID: turnID, lease: lease))

    XCTAssertEqual(response.model.turn?.phase, .recording)
    XCTAssertEqual(response.model.staleEventCount, 1)
    XCTAssertEqual(playback.model.turn?.phase, .recording)
    XCTAssertNil(playback.model.turn?.activeLease)
    XCTAssertEqual(playback.model.invalidTransitionCount, 1)
  }

  func testPendingToolDeadlineTerminates() {
    let (startingModel, turnID, sessionID, responseID) = awaitingHubResponse()
    var model = reduce(
      startingModel,
      .providerResponseStarted(turnID: turnID, sessionID: sessionID, responseID: responseID)
    ).model
    model = reduce(model, .toolStarted(turnID: turnID, callID: VoiceToolCallID("slow"))).model

    let result = reduce(model, .deadlineFired(turnID: turnID, deadline: .pendingTools))

    XCTAssertEqual(result.model.turn?.phase, .terminal(.toolTimeout))
  }

  func testCaptureTranscriptionAndPlaybackDeadlinesHaveDistinctTerminalReasons() {
    let captureTurnID = VoiceTurnID()
    let capturing = reduce(.idle, .start(turnID: captureTurnID, ownerID: nil, intent: .hold)).model
    XCTAssertEqual(
      reduce(capturing, .deadlineFired(turnID: captureTurnID, deadline: .captureStart)).model.turn?
        .phase,
      .terminal(.captureFailed))

    let transcriptionTurnID = VoiceTurnID()
    var transcribing = reduce(.idle, .start(turnID: transcriptionTurnID, ownerID: nil, intent: .hold)).model
    transcribing =
      reduce(
        transcribing,
        .selectRoute(turnID: transcriptionTurnID, route: .deepgramBatch)
      ).model
    transcribing = reduce(transcribing, .finalize(turnID: transcriptionTurnID)).model
    transcribing = reduce(transcribing, .transcriptionStarted(turnID: transcriptionTurnID)).model
    XCTAssertEqual(
      reduce(
        transcribing,
        .deadlineFired(turnID: transcriptionTurnID, deadline: .transcription)
      ).model.turn?.phase,
      .terminal(.transcriptionFailed))

    let (awaiting, playbackTurnID, _, _) = awaitingHubResponse()
    let lease = VoiceOutputLease(id: VoiceLeaseID(), turnID: playbackTurnID, lane: .nativeRealtime)
    let playing = reduce(awaiting, .playbackStarted(turnID: playbackTurnID, lease: lease)).model
    XCTAssertEqual(
      reduce(playing, .deadlineFired(turnID: playbackTurnID, deadline: .playbackDrain)).model.turn?
        .phase,
      .terminal(.playbackFailed))
  }

  func testPlaybackFailureRequiresMatchingLeaseAndShowsErrorHint() {
    let (awaiting, turnID, _, _) = awaitingHubResponse()
    let lease = VoiceOutputLease(id: VoiceLeaseID(), turnID: turnID, lane: .selectedVoiceFallback)
    let playing = reduce(awaiting, .playbackStarted(turnID: turnID, lease: lease)).model

    let stale = reduce(
      playing,
      .playbackFailed(turnID: turnID, leaseID: VoiceLeaseID(), message: "stale"))
    XCTAssertEqual(stale.model.turn?.phase, .playing(.selectedVoiceFallback))
    XCTAssertEqual(stale.model.staleEventCount, 1)

    let failed = reduce(
      playing,
      .playbackFailed(turnID: turnID, leaseID: lease.id, message: "fixture"))
    XCTAssertEqual(failed.model.turn?.phase, .terminal(.playbackFailed))
    XCTAssertEqual(failed.model.turn?.projection.hint, "Audio playback failed")
  }

  func testNativePlaybackProgressRefreshesDrainWatchdogWithoutChangingLease() throws {
    let (awaiting, turnID, _, _) = awaitingHubResponse()
    let requestedLease = VoiceOutputLease(id: VoiceLeaseID(), turnID: turnID, lane: .nativeRealtime)
    let playing = reduce(awaiting, .playbackStarted(turnID: turnID, lease: requestedLease)).model
    let lease = try XCTUnwrap(playing.turn?.activeLease)

    let refreshed = reducer.reduce(
      playing,
      .playbackProgressScoped(turnID: turnID, identity: lease.identity, leaseID: lease.id))

    XCTAssertEqual(refreshed.model.turn?.phase, .playing(.nativeRealtime))
    XCTAssertEqual(refreshed.model.turn?.activeLease, lease)
    XCTAssertEqual(refreshed.model.staleEventCount, playing.staleEventCount)
    XCTAssertTrue(
      refreshed.effects.contains(
        .scheduleDeadline(turnID: turnID, deadline: .playbackDrain, after: reducer.deadlines.playbackDrain)))
  }

  func testCompetingPlaybackLeaseIsRejectedAsInvalidTransition() {
    let (startingModel, turnID, sessionID, responseID) = awaitingHubResponse()
    var model = reduce(
      startingModel,
      .providerResponseStarted(turnID: turnID, sessionID: sessionID, responseID: responseID)
    ).model
    let native = VoiceOutputLease(id: VoiceLeaseID(), turnID: turnID, lane: .nativeRealtime)
    let fallback = VoiceOutputLease(
      id: VoiceLeaseID(), turnID: turnID, lane: .selectedVoiceFallback)
    model = reduce(model, .playbackStarted(turnID: turnID, lease: native)).model

    let result = reduce(model, .playbackStarted(turnID: turnID, lease: fallback))

    XCTAssertEqual(result.model.turn?.activeLease?.id, native.id)
    XCTAssertEqual(result.model.turn?.activeLease?.lane, native.lane)
    XCTAssertEqual(result.model.invalidTransitionCount, 1)
  }

  func testStalePlaybackDrainCannotFinishCurrentLease() {
    let (startingModel, turnID, sessionID, responseID) = awaitingHubResponse()
    var model = reduce(
      startingModel,
      .providerResponseStarted(turnID: turnID, sessionID: sessionID, responseID: responseID)
    ).model
    let lease = VoiceOutputLease(id: VoiceLeaseID(), turnID: turnID, lane: .nativeRealtime)
    model = reduce(model, .playbackStarted(turnID: turnID, lease: lease)).model

    let result = reduce(model, .playbackDrained(turnID: turnID, leaseID: VoiceLeaseID()))

    XCTAssertEqual(result.model.turn?.phase, .playing(.nativeRealtime))
    XCTAssertEqual(result.model.turn?.activeLease?.id, lease.id)
    XCTAssertEqual(result.model.turn?.activeLease?.lane, lease.lane)
    XCTAssertEqual(result.model.staleEventCount, 1)
  }

  func testProviderTurnDoneWaitsForMatchingPlaybackDrain() {
    let (startingModel, turnID, sessionID, responseID) = awaitingHubResponse()
    var model = reduce(
      startingModel,
      .providerResponseStarted(turnID: turnID, sessionID: sessionID, responseID: responseID)
    ).model
    let lease = VoiceOutputLease(id: VoiceLeaseID(), turnID: turnID, lane: .nativeRealtime)
    model = reduce(model, .playbackStarted(turnID: turnID, lease: lease)).model

    let providerDone = reduce(
      model,
      .providerTurnFinished(turnID: turnID, sessionID: sessionID, responseID: responseID))

    XCTAssertEqual(providerDone.model.turn?.phase, .playing(.nativeRealtime))
    XCTAssertEqual(providerDone.model.turn?.providerFinished, true)
    XCTAssertNil(providerDone.model.lastTerminal)

    let drained = reduce(
      providerDone.model,
      .playbackDrained(turnID: turnID, leaseID: lease.id))
    XCTAssertEqual(drained.model.turn?.phase, .awaitingJournal)
    XCTAssertEqual(acceptJournal(drained.model).model.turn?.phase, .terminal(.success))
  }

  func testPlaybackDrainBeforeProviderDoneReturnsToAwaitingResponse() {
    let (startingModel, turnID, sessionID, responseID) = awaitingHubResponse()
    var model = reduce(
      startingModel,
      .providerResponseStarted(turnID: turnID, sessionID: sessionID, responseID: responseID)
    ).model
    let lease = VoiceOutputLease(id: VoiceLeaseID(), turnID: turnID, lane: .nativeRealtime)
    model = reduce(model, .playbackStarted(turnID: turnID, lease: lease)).model

    let drained = reduce(model, .playbackDrained(turnID: turnID, leaseID: lease.id))

    XCTAssertEqual(drained.model.turn?.phase, .awaitingResponse)
    XCTAssertNil(drained.model.lastTerminal)
    XCTAssertTrue(drained.model.turn?.deadlines.contains(.providerResponse) == true)
  }

  func testCleanupFromEveryNonIdlePhaseConvergesToTerminalThenReset() {
    for model in representativeActiveModels() {
      let cleaned = reduce(model, .cleanup)
      XCTAssertEqual(cleaned.model.turn?.phase, .terminal(.cleanup))
      XCTAssertEqual(cleaned.model.turn?.projection, .idle)
      XCTAssertTrue(cleaned.effects.contains(where: \.isTerminal))

      let reset = reduce(cleaned.model, .reset)
      XCTAssertNil(reset.model.turn)
      XCTAssertEqual(reset.model.lastTerminal?.reason, .cleanup)
    }
  }

  func testInvalidTransitionDoesNotMutateTurn() {
    let turnID = VoiceTurnID()
    let model = reduce(.idle, .start(turnID: turnID, ownerID: nil, intent: .hold)).model

    let result = reduce(
      model,
      .hubCommitAccepted(
        turnID: turnID,
        sessionID: VoiceSessionID(),
        responseID: VoiceResponseID("unexpected")))

    XCTAssertEqual(result.model.turn, model.turn)
    XCTAssertEqual(result.model.invalidTransitionCount, 1)
  }

  func testPrematureSuccessCannotBypassProviderPlaybackOrJournalFences() {
    let (awaiting, turnID, _, _) = awaitingHubResponse()

    let result = reduce(awaiting, .finish(turnID: turnID, reason: .success))

    XCTAssertEqual(result.model.turn?.phase, .awaitingResponse)
    XCTAssertNil(result.model.lastTerminal)
    XCTAssertEqual(result.model.invalidTransitionCount, awaiting.invalidTransitionCount + 1)
    XCTAssertFalse(result.effects.contains(where: \.isTerminal))
  }

  func testDeferredCommitCannotSkipFinalization() {
    let turnID = VoiceTurnID()
    var recording = reduce(.idle, .start(turnID: turnID, ownerID: nil, intent: .hold)).model
    recording =
      reduce(
        recording,
        .selectRoute(turnID: turnID, route: .hub(sessionID: nil))
      ).model

    let generic = reduce(recording, .hubCommitDeferred(turnID: turnID))
    let replacement = reduce(recording, .hubCommitDeferredForReplacement(turnID: turnID))

    XCTAssertEqual(generic.model.turn?.phase, .recording)
    XCTAssertEqual(generic.model.invalidTransitionCount, 1)
    XCTAssertEqual(replacement.model.turn?.phase, .recording)
    XCTAssertEqual(replacement.model.invalidTransitionCount, 1)
  }

  func testHubTerminalCleanupCarriesOldRouteInEffectPayload() {
    let turnID = VoiceTurnID()
    let route = VoiceTurnRoute.hub(sessionID: VoiceSessionID())
    var model = reduce(.idle, .start(turnID: turnID, ownerID: nil, intent: .hold)).model
    model = reduce(model, .selectRoute(turnID: turnID, route: route)).model

    let cancelled = reduce(model, .cancel(turnID: turnID, reason: .cancelled))

    XCTAssertTrue(cancelled.effects.contains(.cancelHub(turnID: turnID, route: route)))
    XCTAssertTrue(PushToTalkManager.isHubRoute(route))
    XCTAssertFalse(PushToTalkManager.isHubRoute(.deepgramBatch))
  }

  func testHintDeadlineOnlyClearsTheCurrentTurnHint() {
    let turnID = VoiceTurnID()
    var model = reduce(.idle, .start(turnID: turnID, ownerID: nil, intent: .hold)).model
    model = reduce(model, .hintChanged(turnID: turnID, text: "Hold longer")).model

    let cleared = reduce(model, .deadlineFired(turnID: turnID, deadline: .hintVisibility))

    XCTAssertEqual(cleared.model.turn?.projection.hint, "")
  }

  func testTerminalHintDeadlineClearsHintWithoutResurrectingTurn() {
    let turnID = VoiceTurnID()
    var model = reduce(.idle, .start(turnID: turnID, ownerID: nil, intent: .hold)).model
    model = reduce(model, .finish(turnID: turnID, reason: .tooShort)).model
    XCTAssertEqual(model.turn?.projection.hint, "Hold longer to record")

    let cleared = reduce(model, .deadlineFired(turnID: turnID, deadline: .hintVisibility))

    XCTAssertEqual(cleared.model.turn?.phase, .terminal(.tooShort))
    XCTAssertEqual(cleared.model.turn?.projection.hint, "")
  }

  func testSemanticPresentationEventsUpdateProjectionWithoutOwningIO() {
    let (startingModel, turnID, _, _) = awaitingHubResponse()
    var model = reduce(startingModel, .transcriptChanged(turnID: turnID, text: "hello")).model
    model = reduce(model, .hintChanged(turnID: turnID, text: "working")).model
    model = reduce(model, .responseWaitingChanged(turnID: turnID, active: true)).model
    XCTAssertEqual(model.turn?.projection.transcript, "hello")
    XCTAssertEqual(model.turn?.projection.hint, "working")
    XCTAssertTrue(model.turn?.projection.isThinking == true)

    model = reduce(model, .responseActiveChanged(turnID: turnID, active: true)).model
    XCTAssertTrue(model.turn?.projection.isResponseActive == true)
    XCTAssertFalse(model.turn?.projection.isResponseWaiting == true)
    XCTAssertFalse(model.turn?.projection.isThinking == true)

    let cleared = reduce(model, .hintChanged(turnID: turnID, text: ""))
    XCTAssertEqual(cleared.model.turn?.projection.hint, "")
    XCTAssertTrue(
      cleared.effects.contains(.cancelDeadline(turnID: turnID, deadline: .hintVisibility)))
  }

  func testDebugPresentationIsTurnScopedAndAutomationOnly() {
    let normalTurnID = VoiceTurnID()
    var normal = reduce(.idle, .start(turnID: normalTurnID, ownerID: nil, intent: .hold)).model
    let rejected = reduce(
      normal,
      .debugPresentationChanged(turnID: normalTurnID, state: .answering))
    XCTAssertEqual(rejected.model.turn?.projection, normal.turn?.projection)
    XCTAssertEqual(rejected.model.invalidTransitionCount, 1)

    let debugTurnID = VoiceTurnID()
    normal = reduce(normal, .start(turnID: debugTurnID, ownerID: nil, intent: .automation)).model
    let thinking = reduce(
      normal,
      .debugPresentationChanged(turnID: debugTurnID, state: .thinking))
    XCTAssertEqual(thinking.model.turn?.projection, VoiceTurnDebugPresentationState.thinking.projection)
    XCTAssertFalse(thinking.model.turn?.deadlines.contains(.captureStart) == true)

    let stale = reduce(
      thinking.model,
      .debugPresentationChanged(turnID: normalTurnID, state: .answering))
    XCTAssertEqual(stale.model.turn?.projection, thinking.model.turn?.projection)
    XCTAssertEqual(stale.model.staleEventCount, 1)

    let idle = reduce(
      thinking.model,
      .debugPresentationChanged(turnID: debugTurnID, state: .idle))
    XCTAssertEqual(idle.model.turn?.phase, .terminal(.cleanup))
    XCTAssertEqual(idle.model.turn?.projection, .idle)
  }

  func testRandomizedStaleEventsNeverChangeActiveTurnIdentityOrTerminalizeIt() {
    let activeTurnID = VoiceTurnID()
    var model = reduce(.idle, .start(turnID: activeTurnID, ownerID: nil, intent: .hold)).model
    let initialStaleCount = model.staleEventCount

    for index in 0..<250 {
      let staleID = VoiceTurnID()
      let reduction: VoiceTurnReduction
      switch index % 5 {
      case 0: reduction = reduce(model, .finalize(turnID: staleID))
      case 1: reduction = reduce(model, .transcriptionFinal(turnID: staleID, text: "stale"))
      case 2:
        reduction = reduce(
          model, DriverFact.toolFinished(turnID: staleID, callID: VoiceToolCallID("\(index)")))
      case 3:
        reduction = reduce(
          model, DriverFact.playbackDrained(turnID: staleID, leaseID: VoiceLeaseID()))
      default: reduction = reduce(model, .deadlineFired(turnID: staleID, deadline: .providerResponse))
      }
      model = reduction.model
      XCTAssertEqual(model.turn?.id, activeTurnID)
      XCTAssertFalse(model.turn?.phase.isTerminal == true)
    }

    XCTAssertEqual(model.staleEventCount, initialStaleCount + 250)
  }

  func testClearPresentationIsARealReducerTransition() {
    let turnID = VoiceTurnID()
    var model = reduce(.idle, .start(turnID: turnID, ownerID: nil, intent: .hold)).model
    model = reduce(model, .transcriptChanged(turnID: turnID, text: "private words")).model
    model = reduce(model, .responseActiveChanged(turnID: turnID, active: true)).model

    let cleared = reduce(model, .clearPresentation(turnID: turnID))

    XCTAssertEqual(cleared.model.turn?.projection, .idle)
    XCTAssertEqual(cleared.model.turn?.phase, .recording)
  }

  func testDiagnosticLabelsNeverContainSpeechOrErrorPayloads() {
    let marker = "secret-marker-9381"
    let turnID = VoiceTurnID()
    let events: [VoiceTurnEvent] = [
      .transcriptChanged(turnID: turnID, text: marker),
      .transcriptionFinal(turnID: turnID, text: marker),
      .playbackFailedScoped(
        turnID: turnID,
        identity: VoiceEffectIdentity(turnID: turnID, effectID: 1),
        leaseID: nil,
        message: marker),
      .captureFailed(turnID: turnID, captureID: nil, message: marker),
    ]

    for event in events {
      XCTAssertFalse(event.diagnosticLabel.contains(marker))
      let stale = reduce(.idle, event)
      guard case .staleEventDropped(_, let label) = stale.effects.last else {
        return XCTFail("expected stale diagnostic effect")
      }
      XCTAssertEqual(label, event.diagnosticLabel)
      XCTAssertFalse(label.contains(marker))
    }
  }

  func testNewTurnResetsPerTurnAnomalyCounters() {
    let turnA = VoiceTurnID()
    var model = reduce(.idle, .start(turnID: turnA, ownerID: nil, intent: .hold)).model
    model = reduce(model, .finalize(turnID: VoiceTurnID())).model
    model =
      reduce(
        model,
        .hubCommitAccepted(turnID: turnA, sessionID: VoiceSessionID(), responseID: nil)
      ).model
    XCTAssertEqual(model.staleEventCount, 1)
    XCTAssertEqual(model.invalidTransitionCount, 1)

    let turnB = VoiceTurnID()
    model = reduce(model, .start(turnID: turnB, ownerID: nil, intent: .hold)).model

    XCTAssertEqual(model.turn?.id, turnB)
    XCTAssertEqual(model.staleEventCount, 0)
    XCTAssertEqual(model.invalidTransitionCount, 0)
    XCTAssertEqual(model.duplicateTerminalCount, 0)
  }

  func testNonHubPlaybackDrainCannotClaimProviderOrJournalCompletion() throws {
    let turnID = VoiceTurnID()
    var model = reduce(.idle, .start(turnID: turnID, ownerID: nil, intent: .hold)).model
    model = reduce(model, .selectRoute(turnID: turnID, route: .deepgramBatch)).model
    model = reduce(model, .finalize(turnID: turnID)).model
    model = reduce(model, .transcriptionStarted(turnID: turnID)).model
    model = reduce(model, .transcriptionFinal(turnID: turnID, text: "hello")).model
    let providerIdentity = try XCTUnwrap(model.turn?.providerEffectIdentity)
    model = reduce(
      model,
      .providerResponseStartedScoped(
        turnID: turnID,
        identity: providerIdentity,
        sessionID: nil,
        responseID: nil)).model
    let requestedLease = VoiceOutputLease(
      id: VoiceLeaseID(), turnID: turnID, lane: .selectedVoiceFallback)
    model = reduce(model, .playbackStarted(turnID: turnID, lease: requestedLease)).model
    let lease = try XCTUnwrap(model.turn?.activeLease)

    let drained = reduce(
      model,
      .playbackDrainedScoped(
        turnID: turnID,
        identity: lease.identity,
        leaseID: lease.id))

    XCTAssertNil(drained.model.lastTerminal)
    XCTAssertEqual(drained.model.turn?.phase, .awaitingResponse)
    XCTAssertFalse(drained.model.turn?.providerFinished == true)
    XCTAssertEqual(drained.model.turn?.journalFinalization, .pending)

    let providerFinished = reduce(
      drained.model,
      .providerTurnFinishedScoped(
        turnID: turnID,
        identity: providerIdentity,
        sessionID: nil,
        responseID: nil))
    guard case .writing(let journalIdentity) = providerFinished.model.turn?.journalFinalization else {
      return XCTFail("provider completion must open the canonical journal fence")
    }
    let accepted = reduce(
      providerFinished.model,
      .journalAccepted(turnID: turnID, identity: journalIdentity))
    XCTAssertEqual(accepted.model.turn?.phase, .terminal(.success))
  }

  func testReconnectGenerationRejectsOlderSameTurnCallback() {
    let turnID = VoiceTurnID()
    var model = reduce(.idle, .start(turnID: turnID, ownerID: nil, intent: .hold)).model
    model = reduce(model, .selectRoute(turnID: turnID, route: .hub(sessionID: nil))).model
    var reservation = reserveIdentity(model, turnID: turnID)
    model = reservation.model
    let first = reservation.identity
    model = reduce(
      model,
      .providerReconnectStarted(
        turnID: turnID,
        identity: first,
        previousSessionID: nil)).model
    reservation = reserveIdentity(model, turnID: turnID)
    model = reservation.model
    let second = reservation.identity
    model = reduce(
      model,
      .providerReconnectStarted(
        turnID: turnID,
        identity: second,
        previousSessionID: nil)).model

    let stale = reduce(
      model,
      .providerReconnected(
        turnID: turnID,
        identity: first,
        sessionID: VoiceSessionID()))
    XCTAssertEqual(stale.model.staleEventCount, 1)
    XCTAssertEqual(stale.model.turn?.providerConnection, model.turn?.providerConnection)

    let ready = reduce(
      stale.model,
      .providerReconnected(
        turnID: turnID,
        identity: second,
        sessionID: VoiceSessionID()))
    XCTAssertEqual(ready.model.turn?.providerConnection, .ready)
  }

  func testContextRefreshReconnectGatesInputThenRestoresTheSamePhysicalSession() {
    let turnID = VoiceTurnID()
    let existingSessionID = VoiceSessionID()
    var model = reduce(.idle, .start(turnID: turnID, ownerID: nil, intent: .hold)).model
    model = reduce(
      model,
      .selectRoute(turnID: turnID, route: .hub(sessionID: existingSessionID))).model
    let reservation = reserveIdentity(model, turnID: turnID)
    model = reservation.model

    model = reduce(
      model,
      .providerReconnectStarted(
        turnID: turnID,
        identity: reservation.identity,
        previousSessionID: existingSessionID)).model
    let reconnected = reduce(
      model,
      .providerReconnected(
        turnID: turnID,
        identity: reservation.identity,
        sessionID: existingSessionID))

    XCTAssertEqual(reconnected.model.turn?.providerConnection, .ready)
    XCTAssertEqual(reconnected.model.turn?.sessionID, existingSessionID)
    XCTAssertEqual(reconnected.model.turn?.route, .hub(sessionID: existingSessionID))
  }

  func testReconnectDuringFinalizationKeepsPhysicalCommitAndFallbackLegal() {
    let turnID = VoiceTurnID()
    let existingSessionID = VoiceSessionID()
    var model = reduce(.idle, .start(turnID: turnID, ownerID: nil, intent: .hold)).model
    model = reduce(
      model,
      .selectRoute(turnID: turnID, route: .hub(sessionID: existingSessionID))).model
    model = reduce(model, .finalize(turnID: turnID)).model
    let reservation = reserveIdentity(model, turnID: turnID)
    let reconnecting = reduce(
      reservation.model,
      .providerReconnectStarted(
        turnID: turnID,
        identity: reservation.identity,
        previousSessionID: existingSessionID))

    XCTAssertEqual(reconnecting.model.turn?.phase, .finalizing)
    XCTAssertEqual(reconnecting.model.turn?.providerConnection, .reconnecting(
      identity: reservation.identity,
      previousSessionID: existingSessionID))

    let reconnectedSessionID = VoiceSessionID()
    let reconnected = reduce(
      reconnecting.model,
      .providerReconnected(
        turnID: turnID,
        identity: reservation.identity,
        sessionID: reconnectedSessionID))
    XCTAssertEqual(reconnected.model.turn?.phase, .finalizing)
    XCTAssertEqual(reconnected.model.turn?.providerConnection, .ready)

    let deferredCommit = reduce(
      reconnected.model,
      .hubCommitDeferred(turnID: turnID))
    XCTAssertEqual(deferredCommit.model.turn?.phase, .awaitingResponse)
    XCTAssertTrue(deferredCommit.model.turn?.hubCommitPending == true)
    XCTAssertEqual(deferredCommit.model.invalidTransitionCount, 0)

    let batchFallback = reduce(
      reconnected.model,
      .selectRoute(turnID: turnID, route: .deepgramBatch))
    XCTAssertEqual(batchFallback.model.turn?.phase, .finalizing)
    XCTAssertEqual(batchFallback.model.turn?.route, .deepgramBatch)
    XCTAssertEqual(batchFallback.model.invalidTransitionCount, 0)

    let transcriptionStarted = reduce(
      batchFallback.model,
      .transcriptionStarted(turnID: turnID))
    XCTAssertEqual(transcriptionStarted.model.turn?.phase, .finalizing)
    XCTAssertEqual(transcriptionStarted.model.invalidTransitionCount, 0)
  }

  func testReplacementDuringFinalizationKeepsPhysicalCommitLegal() {
    let turnID = VoiceTurnID()
    let existingSessionID = VoiceSessionID()
    let replacementResponseID = VoiceResponseID("replacement-response")
    var model = reduce(.idle, .start(turnID: turnID, ownerID: nil, intent: .hold)).model
    model = reduce(
      model,
      .selectRoute(turnID: turnID, route: .hub(sessionID: existingSessionID))).model
    model = reduce(model, .finalize(turnID: turnID)).model
    let reservation = reserveIdentity(model, turnID: turnID)
    let replacing = reduce(
      reservation.model,
      .providerReplacementStarted(
        turnID: turnID,
        identity: reservation.identity,
        previousResponseID: nil,
        nextResponseID: replacementResponseID))

    XCTAssertEqual(replacing.model.turn?.phase, .finalizing)
    XCTAssertEqual(replacing.model.turn?.providerConnection, .replacing(
      identity: reservation.identity,
      previousResponseID: nil))

    let replacementSessionID = VoiceSessionID()
    let replacementReady = reduce(
      replacing.model,
      .providerReplacementReady(
        turnID: turnID,
        identity: reservation.identity,
        sessionID: replacementSessionID,
        responseID: replacementResponseID))
    XCTAssertEqual(replacementReady.model.turn?.phase, .finalizing)
    XCTAssertEqual(replacementReady.model.turn?.providerConnection, .ready)

    let deferredCommit = reduce(
      replacementReady.model,
      .hubCommitDeferredForReplacement(turnID: turnID))
    XCTAssertEqual(deferredCommit.model.turn?.phase, .awaitingResponse)
    XCTAssertTrue(deferredCommit.model.turn?.hubCommitPending == true)
    XCTAssertEqual(deferredCommit.model.invalidTransitionCount, 0)
  }

  func testContextRefreshReconnectMayFinishAfterShortPressDefersCommit() {
    let turnID = VoiceTurnID()
    let existingSessionID = VoiceSessionID()
    var model = reduce(.idle, .start(turnID: turnID, ownerID: nil, intent: .hold)).model
    model = reduce(
      model,
      .selectRoute(turnID: turnID, route: .hub(sessionID: existingSessionID))).model
    let reservation = reserveIdentity(model, turnID: turnID)
    model = reservation.model
    model = reduce(
      model,
      .providerReconnectStarted(
        turnID: turnID,
        identity: reservation.identity,
        previousSessionID: existingSessionID)).model

    model = reduce(model, .finalize(turnID: turnID)).model
    model = reduce(model, .hubCommitDeferred(turnID: turnID)).model
    XCTAssertTrue(model.turn?.hubCommitPending == true)
    XCTAssertEqual(model.turn?.phase, .awaitingResponse)

    let reconnected = reduce(
      model,
      .providerReconnected(
        turnID: turnID,
        identity: reservation.identity,
        sessionID: existingSessionID))
    XCTAssertEqual(reconnected.model.turn?.providerConnection, .ready)
    XCTAssertTrue(reconnected.model.turn?.hubCommitPending == true)
  }

  func testContextRefreshFailureFallsBackWithTheDeferredShortPressInsteadOfDroppingIt() {
    let turnID = VoiceTurnID()
    var model = reduce(.idle, .start(turnID: turnID, ownerID: nil, intent: .hold)).model
    model = reduce(model, .selectRoute(turnID: turnID, route: .hub(sessionID: VoiceSessionID()))).model
    let reservation = reserveIdentity(model, turnID: turnID)
    model = reservation.model
    model = reduce(
      model,
      .providerReconnectStarted(
        turnID: turnID,
        identity: reservation.identity,
        previousSessionID: nil)).model
    model = reduce(model, .finalize(turnID: turnID)).model
    model = reduce(model, .hubCommitDeferred(turnID: turnID)).model

    let failed = reduce(
      model,
      .providerReconnectFailed(
        turnID: turnID,
        identity: reservation.identity,
        message: "Voice context is temporarily unavailable"))
    XCTAssertEqual(failed.model.turn?.phase, .finalizing)
    XCTAssertEqual(failed.model.turn?.route, .deepgramBatch)
    XCTAssertFalse(failed.model.turn?.hubCommitPending == true)
    XCTAssertTrue(
      failed.effects.contains(
        .fallbackToTranscription(turnID: turnID, reason: .providerFailed)))
  }

  func testExplicitInterruptRevokesToolAndRejectsItsLateCallback() throws {
    let (startingModel, turnID, _, _) = awaitingHubResponse()
    let reservation = reserveIdentity(startingModel, turnID: turnID)
    let toolIdentity = reservation.identity
    let callID = VoiceToolCallID("slow-tool")
    var model = reduce(
      reservation.model,
      .toolStartedScoped(
        turnID: turnID,
        identity: toolIdentity,
        callID: callID)).model
    XCTAssertEqual(model.turn?.phase, .awaitingTools)

    model = reduce(model, .interrupt(turnID: turnID)).model
    XCTAssertEqual(model.turn?.phase, .terminal(.explicitInterrupt))
    let late = reduce(
      model,
      .toolFinishedScoped(
        turnID: turnID,
        identity: toolIdentity,
        callID: callID))
    XCTAssertEqual(late.model.turn?.phase, .terminal(.explicitInterrupt))
    XCTAssertEqual(late.model.staleEventCount, 1)
  }

  func testRapidThreeTurnReplacementLeavesOnlyNewestMutable() {
    let first = VoiceTurnID()
    let second = VoiceTurnID()
    let third = VoiceTurnID()
    var model = reduce(.idle, .start(turnID: first, ownerID: nil, intent: .hold)).model
    model = reduce(model, .start(turnID: second, ownerID: nil, intent: .hold)).model
    model = reduce(model, .start(turnID: third, ownerID: nil, intent: .hold)).model

    model = reduce(model, .finalize(turnID: first)).model
    model = reduce(model, .toolFinished(turnID: second, callID: VoiceToolCallID("late"))).model

    XCTAssertEqual(model.turn?.id, third)
    XCTAssertEqual(model.turn?.phase, .recording)
    XCTAssertEqual(model.turn?.supersededTurnID, second)
    XCTAssertEqual(model.staleEventCount, 2)
  }

  private func reduce(_ model: VoiceTurnModel, _ event: VoiceTurnEvent) -> VoiceTurnReduction {
    reducer.reduce(model, event)
  }

  /// Drives the same scoped facts production drivers use while keeping older
  /// transition-oriented tests concise. No unscoped event exists in production.
  private func reduce(_ initial: VoiceTurnModel, _ fact: DriverFact) -> VoiceTurnReduction {
    var model = initial
    switch fact {
    case .providerResponseStarted(let turnID, let sessionID, let responseID):
      let identity = model.turn?.providerEffectIdentity
        ?? VoiceEffectIdentity(turnID: turnID, effectID: UInt64.max)
      return reducer.reduce(
        model,
        .providerResponseStartedScoped(
          turnID: turnID, identity: identity, sessionID: sessionID, responseID: responseID))
    case .providerTurnFinished(let turnID, let sessionID, let responseID):
      let identity = model.turn?.providerEffectIdentity
        ?? VoiceEffectIdentity(turnID: turnID, effectID: UInt64.max)
      return reducer.reduce(
        model,
        .providerTurnFinishedScoped(
          turnID: turnID, identity: identity, sessionID: sessionID, responseID: responseID))
    case .toolStarted(let turnID, let callID):
      let reservation = reserveIdentity(model, turnID: turnID)
      model = reservation.model
      return reducer.reduce(
        model,
        .toolStartedScoped(
          turnID: turnID, identity: reservation.identity, callID: callID))
    case .toolFinished(let turnID, let callID):
      let identity = model.turn?.toolEffectIdentities[callID]
        ?? VoiceEffectIdentity(turnID: turnID, effectID: UInt64.max)
      return reducer.reduce(
        model,
        .toolFinishedScoped(turnID: turnID, identity: identity, callID: callID))
    case .playbackStarted(let turnID, let requestedLease):
      let reservation = reserveIdentity(model, turnID: turnID)
      model = reservation.model
      let lease = VoiceOutputLease(
        id: requestedLease.id,
        turnID: requestedLease.turnID,
        lane: requestedLease.lane,
        identity: reservation.identity)
      return reducer.reduce(model, .playbackStartedScoped(turnID: turnID, lease: lease))
    case .playbackDrained(let turnID, let leaseID):
      let identity = model.turn?.activeLease?.identity
        ?? VoiceEffectIdentity(turnID: turnID, effectID: UInt64.max)
      return reducer.reduce(
        model,
        .playbackDrainedScoped(turnID: turnID, identity: identity, leaseID: leaseID))
    case .playbackFailed(let turnID, let leaseID, let message):
      let identity = model.turn?.activeLease?.identity
        ?? VoiceEffectIdentity(turnID: turnID, effectID: UInt64.max)
      return reducer.reduce(
        model,
        .playbackFailedScoped(
          turnID: turnID, identity: identity, leaseID: leaseID, message: message))
    }
  }

  private func reserveIdentity(
    _ model: VoiceTurnModel,
    turnID: VoiceTurnID
  ) -> (model: VoiceTurnModel, identity: VoiceEffectIdentity) {
    let effectID = model.turn?.nextEffectID ?? 0
    let reserved = reduce(model, .effectIdentityReserved(turnID: turnID)).model
    return (reserved, VoiceEffectIdentity(turnID: turnID, effectID: effectID))
  }

  private func acceptJournal(_ model: VoiceTurnModel) -> VoiceTurnReduction {
    guard let turn = model.turn, case .writing(let identity) = turn.journalFinalization else {
      return VoiceTurnReduction(model: model, effects: [])
    }
    return reduce(
      model,
      .journalAccepted(turnID: turn.id, identity: identity))
  }

  private func awaitingHubResponse()
    -> (VoiceTurnModel, VoiceTurnID, VoiceSessionID, VoiceResponseID)
  {
    let turnID = VoiceTurnID()
    let sessionID = VoiceSessionID()
    let responseID = VoiceResponseID("response")
    var model = reduce(.idle, .start(turnID: turnID, ownerID: nil, intent: .hold)).model
    model = reduce(model, .selectRoute(turnID: turnID, route: .hub(sessionID: sessionID))).model
    model = reduce(model, .finalize(turnID: turnID)).model
    model =
      reduce(
        model,
        .hubCommitAccepted(turnID: turnID, sessionID: sessionID, responseID: responseID)
      ).model
    return (model, turnID, sessionID, responseID)
  }

  private func representativeActiveModels() -> [VoiceTurnModel] {
    let turnID = VoiceTurnID()
    let sessionID = VoiceSessionID()
    let responseID = VoiceResponseID("response")
    let recording = reduce(.idle, .start(turnID: turnID, ownerID: nil, intent: .hold)).model
    let pending = reduce(recording, .openLockWindow(turnID: turnID)).model
    let locked = reduce(recording, .lock(turnID: turnID)).model
    let finalizing = reduce(recording, .finalize(turnID: turnID)).model
    var awaiting = reduce(
      recording, .selectRoute(turnID: turnID, route: .hub(sessionID: sessionID))
    ).model
    awaiting = reduce(awaiting, .finalize(turnID: turnID)).model
    awaiting =
      reduce(
        awaiting,
        .hubCommitAccepted(turnID: turnID, sessionID: sessionID, responseID: responseID)
      ).model
    let tools = reduce(awaiting, .toolStarted(turnID: turnID, callID: VoiceToolCallID("tool")))
      .model
    let lease = VoiceOutputLease(id: VoiceLeaseID(), turnID: turnID, lane: .nativeRealtime)
    let playing = reduce(awaiting, .playbackStarted(turnID: turnID, lease: lease)).model
    let awaitingJournal = reduce(
      awaiting,
      .providerTurnFinished(turnID: turnID, sessionID: sessionID, responseID: responseID)
    ).model
    return [recording, pending, locked, finalizing, awaiting, tools, playing, awaitingJournal]
  }
}

extension VoiceTurnEffect {
  fileprivate var isTerminal: Bool {
    if case .terminal = self { return true }
    return false
  }
}
