import XCTest

@testable import Omi_Computer

final class VoiceTurnReducerTests: XCTestCase {
  private let reducer = VoiceTurnReducer()

  func testHappyHubTurnTransitionsThroughPlaybackAndTerminatesExactlyOnce() throws {
    let turnID = VoiceTurnID()
    let captureID = VoiceCaptureID(7)
    let sessionID = VoiceSessionID()
    let responseID = VoiceResponseID("response-1")
    let lease = VoiceOutputLease(id: VoiceLeaseID(), turnID: turnID, lane: .nativeRealtime)
    var model = VoiceTurnModel.idle

    model = reduce(model, .start(turnID: turnID, intent: .hold)).model
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
    XCTAssertEqual(model.turn?.activeLease, lease)

    model =
      reduce(
        model,
        .providerTurnFinished(turnID: turnID, sessionID: sessionID, responseID: responseID)
      ).model

    let drained = reduce(model, .playbackDrained(turnID: turnID, leaseID: lease.id))
    XCTAssertEqual(drained.model.turn?.phase, .terminal(.success))
    XCTAssertEqual(
      drained.model.lastTerminal,
      .init(turnID: turnID, reason: .success, route: .hub(sessionID: sessionID)))
    XCTAssertEqual(drained.effects.filter(\.isTerminal).count, 1)

    let duplicate = reduce(drained.model, .finish(turnID: turnID, reason: .success))
    XCTAssertEqual(duplicate.model.duplicateTerminalCount, 1)
    XCTAssertFalse(duplicate.effects.contains(where: \.isTerminal))
  }

  func testQuickTapLockWindowCanBecomeLockedRecording() {
    let turnID = VoiceTurnID()
    var model = reduce(.idle, .start(turnID: turnID, intent: .hold)).model

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
    var model = reduce(.idle, .start(turnID: turnID, intent: .hold)).model
    model = reduce(model, .captureStarted(turnID: turnID, captureID: captureID)).model
    model = reduce(model, .openLockWindow(turnID: turnID)).model

    let result = reduce(model, .deadlineFired(turnID: turnID, deadline: .lockDecision))

    XCTAssertEqual(result.model.turn?.phase, .finalizing)
    XCTAssertTrue(result.effects.contains(.stopCapture(turnID: turnID, captureID: captureID)))
  }

  func testLateCaptureStartAfterFinalizationIsStoppedAndCannotResurrectTurn() {
    let turnID = VoiceTurnID()
    var model = reduce(.idle, .start(turnID: turnID, intent: .hold)).model
    model = reduce(model, .finalize(turnID: turnID)).model
    let lateCaptureID = VoiceCaptureID(99)

    let result = reduce(model, .captureStarted(turnID: turnID, captureID: lateCaptureID))

    XCTAssertEqual(result.model.turn?.phase, .finalizing)
    XCTAssertNil(result.model.turn?.captureID)
    XCTAssertEqual(result.model.staleEventCount, 1)
    XCTAssertTrue(result.effects.contains(.stopCapture(turnID: turnID, captureID: lateCaptureID)))
  }

  func testOldTurnEventsAreDroppedAfterBargeInStartsNewTurn() {
    let oldTurnID = VoiceTurnID()
    let newTurnID = VoiceTurnID()
    var model = reduce(.idle, .start(turnID: oldTurnID, intent: .hold)).model

    let bargeIn = reduce(model, .start(turnID: newTurnID, intent: .hold))
    model = bargeIn.model
    XCTAssertEqual(model.turn?.id, newTurnID)
    XCTAssertEqual(model.lastTerminal, .init(turnID: oldTurnID, reason: .interruptedByBargeIn))

    let stale = reduce(model, .transcriptionFinal(turnID: oldTurnID, text: "old"))
    XCTAssertEqual(stale.model.turn?.id, newTurnID)
    XCTAssertEqual(stale.model.turn?.projection.transcript, "")
    XCTAssertEqual(stale.model.staleEventCount, 1)
  }

  func testHubBargeInPreservesProviderRuntimeForAtomicHandoff() {
    let oldTurnID = VoiceTurnID()
    let newTurnID = VoiceTurnID()
    let sessionID = VoiceSessionID()
    var model = reduce(.idle, .start(turnID: oldTurnID, intent: .hold)).model
    model = reduce(model, .selectRoute(turnID: oldTurnID, route: .hub(sessionID: sessionID))).model

    let result = reduce(model, .start(turnID: newTurnID, intent: .hold))

    XCTAssertEqual(result.model.lastTerminal?.route, .hub(sessionID: sessionID))
    XCTAssertFalse(
      result.effects.contains(
        .cancelHub(turnID: oldTurnID, route: .hub(sessionID: sessionID))))
    XCTAssertFalse(
      result.effects.contains { effect in
        if case .stopPlayback(let turnID, _) = effect { return turnID == oldTurnID }
        return false
      })
  }

  func testHubWarmTimeoutFallsBackWithoutTerminatingOrDroppingTurn() {
    let turnID = VoiceTurnID()
    var model = reduce(.idle, .start(turnID: turnID, intent: .hold)).model
    model = reduce(model, .selectRoute(turnID: turnID, route: .hubWarmWait)).model
    model = reduce(model, .finalize(turnID: turnID)).model

    let timedOut = reduce(model, .deadlineFired(turnID: turnID, deadline: .hubWarm))

    XCTAssertEqual(timedOut.model.turn?.route, .deepgramBatch)
    XCTAssertEqual(timedOut.model.turn?.phase, .finalizing)
    XCTAssertNil(timedOut.model.turn?.terminalReason)
    XCTAssertTrue(
      timedOut.effects.contains(.fallbackToTranscription(turnID: turnID, reason: .hubWarmTimeout)))
  }

  func testHubReadyCancelsWarmDeadlineAndPreservesRecording() {
    let turnID = VoiceTurnID()
    let sessionID = VoiceSessionID()
    var model = reduce(.idle, .start(turnID: turnID, intent: .hold)).model
    model = reduce(model, .selectRoute(turnID: turnID, route: .hubWarmWait)).model

    let ready = reduce(model, .hubReady(turnID: turnID, sessionID: sessionID))

    XCTAssertEqual(ready.model.turn?.route, .hub(sessionID: sessionID))
    XCTAssertEqual(ready.model.turn?.sessionID, sessionID)
    XCTAssertEqual(ready.model.turn?.phase, .recording)
    XCTAssertTrue(ready.effects.contains(.cancelDeadline(turnID: turnID, deadline: .hubWarm)))
  }

  func testDeferredCommitTimeoutTerminatesWithTypedReason() {
    let turnID = VoiceTurnID()
    let sessionID = VoiceSessionID()
    var model = reduce(.idle, .start(turnID: turnID, intent: .hold)).model
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
    var model = reduce(.idle, .start(turnID: turnID, intent: .hold)).model
    model = reduce(model, .selectRoute(turnID: turnID, route: .hub(sessionID: oldSessionID))).model
    model = reduce(model, .finalize(turnID: turnID)).model

    let deferred = reduce(model, .hubCommitDeferredForReplacement(turnID: turnID))
    XCTAssertEqual(deferred.model.turn?.phase, .awaitingResponse)
    XCTAssertTrue(deferred.model.turn?.deadlines.contains(.bargeInReplacement) == true)
    XCTAssertFalse(deferred.model.turn?.deadlines.contains(.deferredCommit) == true)

    let accepted = reduce(
      deferred.model,
      .hubCommitAccepted(
        turnID: turnID,
        sessionID: replacementSessionID,
        responseID: nil))
    XCTAssertEqual(accepted.model.turn?.sessionID, replacementSessionID)
    XCTAssertFalse(accepted.model.turn?.deadlines.contains(.bargeInReplacement) == true)
    XCTAssertTrue(accepted.model.turn?.deadlines.contains(.providerResponse) == true)
    XCTAssertTrue(
      accepted.effects.contains(
        .cancelDeadline(turnID: turnID, deadline: .bargeInReplacement)))
  }

  func testBargeInReplacementDeadlineTerminatesWithTypedReason() {
    let turnID = VoiceTurnID()
    var model = reduce(.idle, .start(turnID: turnID, intent: .hold)).model
    model = reduce(model, .selectRoute(turnID: turnID, route: .hub(sessionID: nil))).model
    model = reduce(model, .finalize(turnID: turnID)).model
    model = reduce(model, .hubCommitDeferredForReplacement(turnID: turnID)).model

    let result = reduce(
      model,
      .deadlineFired(turnID: turnID, deadline: .bargeInReplacement))

    XCTAssertEqual(result.model.turn?.phase, .terminal(.bargeInReplacementTimeout))
    XCTAssertEqual(result.model.lastTerminal?.reason, .bargeInReplacementTimeout)
  }

  func testProviderNoResponseDeadlineTerminatesAndShowsActionableHint() {
    let (model, turnID, _, _) = awaitingHubResponse()

    let result = reduce(model, .deadlineFired(turnID: turnID, deadline: .providerResponse))

    XCTAssertEqual(result.model.turn?.phase, .terminal(.providerNoResponse))
    XCTAssertEqual(result.model.turn?.projection.isListening, false)
    XCTAssertEqual(result.model.turn?.projection.isThinking, false)
    XCTAssertEqual(result.model.turn?.projection.isResponseActive, false)
    XCTAssertEqual(result.model.turn?.projection.hint, "Voice response failed — try again")
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

    XCTAssertEqual(result.model.turn?.phase, .terminal(.success))
    XCTAssertEqual(result.model.lastTerminal?.reason, .success)
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

  func testProviderFinishDuringToolWaitTerminatesAfterLastToolAndOnlyThen() {
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
    XCTAssertEqual(toolFinished.model.turn?.phase, .terminal(.success))
    XCTAssertEqual(toolFinished.model.lastTerminal?.reason, .success)
  }

  func testToolAndPlaybackCanDrainInEitherOrderWithoutClosingEarly() {
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
    XCTAssertEqual(finished.model.turn?.phase, .terminal(.success))
  }

  func testProviderOutputCannotMutateRecordingTurnBeforeCommit() {
    let turnID = VoiceTurnID()
    let lease = VoiceOutputLease(id: VoiceLeaseID(), turnID: turnID, lane: .nativeRealtime)
    let recording = reduce(.idle, .start(turnID: turnID, intent: .hold)).model

    let response = reduce(
      recording,
      .providerResponseStarted(turnID: turnID, sessionID: VoiceSessionID(), responseID: nil))
    let playback = reduce(recording, .playbackStarted(turnID: turnID, lease: lease))

    XCTAssertEqual(response.model.turn?.phase, .recording)
    XCTAssertEqual(response.model.invalidTransitionCount, 1)
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
    let capturing = reduce(.idle, .start(turnID: captureTurnID, intent: .hold)).model
    XCTAssertEqual(
      reduce(capturing, .deadlineFired(turnID: captureTurnID, deadline: .captureStart)).model.turn?
        .phase,
      .terminal(.captureFailed))

    let transcriptionTurnID = VoiceTurnID()
    var transcribing = reduce(.idle, .start(turnID: transcriptionTurnID, intent: .hold)).model
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

    XCTAssertEqual(result.model.turn?.activeLease, native)
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
    XCTAssertEqual(result.model.turn?.activeLease, lease)
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
    XCTAssertEqual(drained.model.turn?.phase, .terminal(.success))
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
    let model = reduce(.idle, .start(turnID: turnID, intent: .hold)).model

    let result = reduce(
      model,
      .hubCommitAccepted(
        turnID: turnID,
        sessionID: VoiceSessionID(),
        responseID: VoiceResponseID("unexpected")))

    XCTAssertEqual(result.model.turn, model.turn)
    XCTAssertEqual(result.model.invalidTransitionCount, 1)
  }

  func testDeferredCommitCannotSkipFinalization() {
    let turnID = VoiceTurnID()
    var recording = reduce(.idle, .start(turnID: turnID, intent: .hold)).model
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
    var model = reduce(.idle, .start(turnID: turnID, intent: .hold)).model
    model = reduce(model, .selectRoute(turnID: turnID, route: route)).model

    let cancelled = reduce(model, .cancel(turnID: turnID, reason: .cancelled))

    XCTAssertTrue(cancelled.effects.contains(.cancelHub(turnID: turnID, route: route)))
    XCTAssertTrue(PushToTalkManager.isHubRoute(route))
    XCTAssertFalse(PushToTalkManager.isHubRoute(.deepgramBatch))
  }

  func testHintDeadlineOnlyClearsTheCurrentTurnHint() {
    let turnID = VoiceTurnID()
    var model = reduce(.idle, .start(turnID: turnID, intent: .hold)).model
    model = reduce(model, .hintChanged(turnID: turnID, text: "Hold longer")).model

    let cleared = reduce(model, .deadlineFired(turnID: turnID, deadline: .hintVisibility))

    XCTAssertEqual(cleared.model.turn?.projection.hint, "")
  }

  func testTerminalHintDeadlineClearsHintWithoutResurrectingTurn() {
    let turnID = VoiceTurnID()
    var model = reduce(.idle, .start(turnID: turnID, intent: .hold)).model
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

  func testRandomizedStaleEventsNeverChangeActiveTurnIdentityOrTerminalizeIt() {
    let activeTurnID = VoiceTurnID()
    var model = reduce(.idle, .start(turnID: activeTurnID, intent: .hold)).model
    let initialStaleCount = model.staleEventCount

    for index in 0..<250 {
      let staleID = VoiceTurnID()
      let event: VoiceTurnEvent
      switch index % 5 {
      case 0: event = .finalize(turnID: staleID)
      case 1: event = .transcriptionFinal(turnID: staleID, text: "stale")
      case 2: event = .toolFinished(turnID: staleID, callID: VoiceToolCallID("\(index)"))
      case 3: event = .playbackDrained(turnID: staleID, leaseID: VoiceLeaseID())
      default: event = .deadlineFired(turnID: staleID, deadline: .providerResponse)
      }
      model = reduce(model, event).model
      XCTAssertEqual(model.turn?.id, activeTurnID)
      XCTAssertFalse(model.turn?.phase.isTerminal == true)
    }

    XCTAssertEqual(model.staleEventCount, initialStaleCount + 250)
  }

  func testClearPresentationIsARealReducerTransition() {
    let turnID = VoiceTurnID()
    var model = reduce(.idle, .start(turnID: turnID, intent: .hold)).model
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
      .playbackFailed(turnID: turnID, leaseID: nil, message: marker),
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
    var model = reduce(.idle, .start(turnID: turnA, intent: .hold)).model
    model = reduce(model, .finalize(turnID: VoiceTurnID())).model
    model =
      reduce(
        model,
        .hubCommitAccepted(turnID: turnA, sessionID: VoiceSessionID(), responseID: nil)
      ).model
    XCTAssertEqual(model.staleEventCount, 1)
    XCTAssertEqual(model.invalidTransitionCount, 1)

    let turnB = VoiceTurnID()
    model = reduce(model, .start(turnID: turnB, intent: .hold)).model

    XCTAssertEqual(model.turn?.id, turnB)
    XCTAssertEqual(model.staleEventCount, 0)
    XCTAssertEqual(model.invalidTransitionCount, 0)
    XCTAssertEqual(model.duplicateTerminalCount, 0)
  }

  private func reduce(_ model: VoiceTurnModel, _ event: VoiceTurnEvent) -> VoiceTurnReduction {
    reducer.reduce(model, event)
  }

  private func awaitingHubResponse()
    -> (VoiceTurnModel, VoiceTurnID, VoiceSessionID, VoiceResponseID)
  {
    let turnID = VoiceTurnID()
    let sessionID = VoiceSessionID()
    let responseID = VoiceResponseID("response")
    var model = reduce(.idle, .start(turnID: turnID, intent: .hold)).model
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
    let recording = reduce(.idle, .start(turnID: turnID, intent: .hold)).model
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
    return [recording, pending, locked, finalizing, awaiting, tools, playing]
  }
}

extension VoiceTurnEffect {
  fileprivate var isTerminal: Bool {
    if case .terminal = self { return true }
    return false
  }
}
