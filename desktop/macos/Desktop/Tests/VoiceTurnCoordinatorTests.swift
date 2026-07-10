import XCTest

@testable import Omi_Computer

@MainActor
final class VoiceTurnCoordinatorTests: XCTestCase {
  func testFakeClockDrivesLockDeadlineAndRealStopCaptureEffect() {
    let scheduler = ManualVoiceTurnScheduler()
    let coordinator = VoiceTurnCoordinator(scheduler: scheduler)
    var effects: [VoiceTurnEffect] = []
    coordinator.setEffectHandler { effects.append($0) }
    let turnID = coordinator.begin(intent: .hold)
    coordinator.send(.captureStarted(turnID: turnID, captureID: VoiceCaptureID(1)))
    coordinator.send(.openLockWindow(turnID: turnID))

    scheduler.fire(deadline: .lockDecision)

    XCTAssertEqual(coordinator.model.turn?.phase, .finalizing)
    XCTAssertTrue(
      effects.contains(.stopCapture(turnID: turnID, captureID: VoiceCaptureID(1))))
  }

  func testCancelledDeadlineCannotMutateLaterTurn() {
    let scheduler = ManualVoiceTurnScheduler()
    let coordinator = VoiceTurnCoordinator(scheduler: scheduler)
    let oldTurn = coordinator.begin(intent: .hold)
    coordinator.send(.openLockWindow(turnID: oldTurn))
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
    coordinator.send(.captureStarted(turnID: turnID, captureID: VoiceCaptureID(1)))
    coordinator.send(.selectRoute(turnID: turnID, route: .deepgramBatch))
    coordinator.send(.finalize(turnID: turnID))
    coordinator.send(.transcriptionStarted(turnID: turnID))

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

    coordinator.send(.selectRoute(turnID: turnID, route: .deepgramBatch))
    coordinator.send(.finalize(turnID: turnID))
    coordinator.send(.transcriptionStarted(turnID: turnID))
    XCTAssertFalse(barState.isVoiceListening)
    XCTAssertTrue(barState.isThinking)
    XCTAssertEqual(barState.voiceTranscript, "Transcribing…")

    coordinator.send(.transcriptionFailed(turnID: turnID, message: "fixture"))
    // The capture/listening phase is over, but the pill remains expanded long
    // enough to make the actionable terminal hint visible to the user.
    XCTAssertTrue(barState.isVoiceListening)
    XCTAssertFalse(barState.isThinking)
    XCTAssertFalse(barState.isVoiceResponseActive)
    XCTAssertEqual(barState.pttHintText, "Couldn't transcribe that — try again")
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

    coordinator.send(.cancel(turnID: turnID, reason: .cancelled))
    coordinator.send(.finish(turnID: turnID, reason: .providerFailed))

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
    coordinator.send(.selectRoute(turnID: turnID, route: .deepgramBatch))
    coordinator.send(.finalize(turnID: turnID))
    coordinator.send(.transcriptionStarted(turnID: turnID))
    coordinator.send(.transcriptionFinal(turnID: turnID, text: "hello"))
    coordinator.send(.providerResponseStarted(turnID: turnID, sessionID: nil, responseID: nil))
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
    coordinator.send(.lock(turnID: turnID))

    XCTAssertEqual(snapshots.first, .idle)
    XCTAssertEqual(snapshots.last?.turn?.phase, .lockedRecording)
    XCTAssertEqual(snapshots.count, 3)
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

    coordinator.send(.finalize(turnID: VoiceTurnID()))
    coordinator.send(
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
      (.agentFollowUp, "agent_follow_up"),
    ]
    for (route, expected) in routes {
      XCTAssertEqual(VoiceTurnCoordinator.routeLabel(route), expected, "turn=\(turnID)")
    }
  }

  func testTimelineNeverStoresAssociatedSpeechPayloads() {
    let coordinator = VoiceTurnCoordinator(scheduler: ManualVoiceTurnScheduler())
    let marker = "secret-timeline-marker-442"
    let turnID = coordinator.begin(intent: .hold)
    coordinator.send(.transcriptChanged(turnID: turnID, text: marker))
    coordinator.send(.playbackFailed(turnID: VoiceTurnID(), leaseID: nil, message: marker))

    let events = coordinator.timelineSnapshot().map(\.event)
    XCTAssertTrue(events.contains("transcript_changed"))
    XCTAssertTrue(events.contains("playback_failed"))
    XCTAssertFalse(events.joined().contains(marker))
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
