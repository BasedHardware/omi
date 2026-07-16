import XCTest

@testable import Omi_Computer
@testable import VoiceTurnDomain

private actor OwnerBoundaryExternalRunProbe {
  private var entered = false
  private var released = false
  private var closed = false
  private var observedOwnerID: String?
  private var observedStatus: ExternalSurfaceRunTerminalStatus?
  private var enteredWaiters: [CheckedContinuation<Void, Never>] = []
  private var releaseWaiters: [CheckedContinuation<Void, Never>] = []

  func terminalize(
    binding: ExternalSurfaceRunBinding,
    status: ExternalSurfaceRunTerminalStatus,
    capability: RuntimeOwnerTransitionCleanupCapability?
  ) async throws {
    guard let capability,
      RuntimeOwnerIdentity.authorizesTransitionCleanup(
        capability,
        previousOwnerID: binding.ownerID)
    else {
      throw ExternalSurfaceAuthorityError(code: "test_cleanup_capability_rejected")
    }
    observedOwnerID = binding.ownerID
    observedStatus = status
    entered = true
    let waiters = enteredWaiters
    enteredWaiters.removeAll()
    waiters.forEach { $0.resume() }
    if !released {
      await withCheckedContinuation { continuation in
        releaseWaiters.append(continuation)
      }
    }
    guard
      RuntimeOwnerIdentity.authorizesTransitionCleanup(
        capability,
        previousOwnerID: binding.ownerID)
    else {
      throw ExternalSurfaceAuthorityError(code: "test_cleanup_capability_expired")
    }
    closed = true
  }

  func waitUntilEntered() async {
    guard !entered else { return }
    await withCheckedContinuation { continuation in
      enteredWaiters.append(continuation)
    }
  }

  func release() {
    released = true
    let waiters = releaseWaiters
    releaseWaiters.removeAll()
    waiters.forEach { $0.resume() }
  }

  func snapshot() -> (closed: Bool, ownerID: String?, status: ExternalSurfaceRunTerminalStatus?) {
    (closed, observedOwnerID, observedStatus)
  }
}

final class PushToTalkStateMachineTests: XCTestCase {
  func testRecordingProjectionComesDirectlyFromAuthoritativePhase() {
    XCTAssertTrue(VoiceTurnPhase.recording.isRecording)
    XCTAssertTrue(VoiceTurnPhase.pendingLockDecision.isRecording)
    XCTAssertTrue(VoiceTurnPhase.lockedRecording.isRecording)
    XCTAssertFalse(VoiceTurnPhase.finalizing.isRecording)
    XCTAssertTrue(VoiceTurnPhase.terminal(.success).isTerminal)
  }

  func testCaptureStartAfterFinalizationProducesStopEffect() {
    let reducer = VoiceTurnReducer()
    let turnID = VoiceTurnID()
    var model = reducer.reduce(.idle, .start(turnID: turnID, ownerID: nil, intent: .hold)).model
    model = reducer.reduce(model, .finalize(turnID: turnID)).model
    let captureID = VoiceCaptureID(42)

    let result = reducer.reduce(
      model,
      .captureStarted(turnID: turnID, captureID: captureID))

    XCTAssertEqual(result.model.turn?.phase, .finalizing)
    XCTAssertTrue(result.effects.contains(.stopCapture(turnID: turnID, captureID: captureID)))
  }

  func testCancelFromRecordingStopsCaptureAndTerminatesOnce() {
    let reducer = VoiceTurnReducer()
    let turnID = VoiceTurnID()
    let captureID = VoiceCaptureID(9)
    var model = reducer.reduce(.idle, .start(turnID: turnID, ownerID: nil, intent: .hold)).model
    model = reducer.reduce(model, .captureStarted(turnID: turnID, captureID: captureID)).model

    let cancelled = reducer.reduce(model, .cancel(turnID: turnID, reason: .cancelled))

    XCTAssertEqual(cancelled.model.turn?.phase, .terminal(.cancelled))
    XCTAssertTrue(cancelled.effects.contains(.stopCapture(turnID: turnID, captureID: captureID)))
    XCTAssertEqual(
      cancelled.effects.filter { effect in
        if case .terminal = effect { return true }
        return false
      }.count, 1)
  }

  @MainActor
  func testHeadlessAutomationRunsRealLifecycleWithoutMicrophonePermission() {
    let manager = PushToTalkManager.shared
    let previousAuthOwner = UserDefaults.standard.object(forKey: .authUserId)
    let previousAutomationOwner = UserDefaults.standard.object(forKey: .automationOwnerOverride)
    manager.cleanup()
    UserDefaults.standard.set("ptt-headless-owner", forKey: .authUserId)
    UserDefaults.standard.removeObject(forKey: .automationOwnerOverride)
    defer {
      manager.cleanup()
      if let previousAuthOwner {
        UserDefaults.standard.set(previousAuthOwner, forKey: .authUserId)
      } else {
        UserDefaults.standard.removeObject(forKey: .authUserId)
      }
      if let previousAutomationOwner {
        UserDefaults.standard.set(previousAutomationOwner, forKey: .automationOwnerOverride)
      } else {
        UserDefaults.standard.removeObject(forKey: .automationOwnerOverride)
      }
    }

    let started = manager.beginPushToTalkForAutomation()
    XCTAssertEqual(started["listening"], "true")
    XCTAssertEqual(VoiceTurnCoordinator.shared.activeTurn?.phase, .recording)

    let stopped = manager.endPushToTalkForAutomation()
    XCTAssertEqual(stopped["finalized"], "true")
    XCTAssertEqual(VoiceTurnCoordinator.shared.model.turn?.phase, .terminal(.tooShort))
    XCTAssertEqual(VoiceTurnCoordinator.shared.model.turn?.projection.hint, "Hold longer to record")
    XCTAssertEqual(VoiceTurnCoordinator.shared.model.staleEventCount, 0)
    XCTAssertEqual(VoiceTurnCoordinator.shared.model.invalidTransitionCount, 0)
  }

  @MainActor
  func testOwnerTransitionTerminatesActiveNonHubCaptureBeforeOwnerBBecomesVisible() async {
    let manager = PushToTalkManager.shared
    let defaults = ownerBoundaryDefaults("non-hub")
    manager.cleanup()
    await transitionOwner(defaults: defaults, to: "owner-a")

    // Install the production physical-effect handler without touching a real
    // microphone, then admit an exact non-hub capture through the reducer.
    _ = manager.beginPushToTalkForAutomation()
    manager.cleanup()
    let turnID = VoiceTurnCoordinator.shared.begin(intent: .hold, ownerID: "owner-a")
    VoiceTurnCoordinator.shared.publish(
      .selectRoute(turnID: turnID, route: .deepgramLive))
    let captureID = VoiceCaptureID(manager.ownerBoundarySnapshot.captureGeneration)
    VoiceTurnCoordinator.shared.publish(
      .captureStarted(turnID: turnID, captureID: captureID))
    let generationBeforeTransition = manager.ownerBoundarySnapshot.captureGeneration

    await transitionOwner(defaults: defaults, to: "owner-b")

    XCTAssertEqual(defaults.string(forKey: .authUserId), "owner-b")
    XCTAssertEqual(VoiceTurnCoordinator.shared.model.lastTerminal?.turnID, turnID)
    XCTAssertEqual(VoiceTurnCoordinator.shared.model.lastTerminal?.reason, .ownerChanged)
    let snapshot = manager.ownerBoundarySnapshot
    XCTAssertNil(snapshot.activeTurnID)
    XCTAssertFalse(snapshot.hasCaptureDriver)
    XCTAssertFalse(snapshot.captureStartInFlight)
    XCTAssertFalse(snapshot.hasTranscriptionDriver)
    XCTAssertFalse(snapshot.hasOmniDriver)
    XCTAssertGreaterThan(snapshot.captureGeneration, generationBeforeTransition)

    manager.cleanup()
    defaults.removePersistentDomain(forName: ownerBoundarySuiteName("non-hub"))
  }

  @MainActor
  func testOwnerTransitionClosesWarmHubAndPurgesOwnerAContext() async {
    let manager = PushToTalkManager.shared
    let hub = RealtimeHubController.shared
    let defaults = ownerBoundaryDefaults("warm-hub")
    manager.cleanup()
    await transitionOwner(defaults: defaults, to: "owner-a")
    hub.installOwnerBoundaryFixture(ownerID: "owner-a")

    XCTAssertEqual(
      hub.ownerBoundarySnapshot,
      RealtimeHubOwnerBoundarySnapshot(
        hasPhysicalSession: true,
        physicalOwnerID: "owner-a",
        prefetchedOwnerID: "owner-a",
        prefetchedContextIsEmpty: false,
        hasPendingOwnerWork: true,
        hubConnected: true,
        turnAudioByteCount: 16))

    await transitionOwner(defaults: defaults, to: "owner-b")

    XCTAssertEqual(defaults.string(forKey: .authUserId), "owner-b")
    assertHubOwnerBoundaryIsEmpty(hub.ownerBoundarySnapshot)
    defaults.removePersistentDomain(forName: ownerBoundarySuiteName("warm-hub"))
  }

  @MainActor
  func testOwnerTransitionTerminatesActiveHubAndDrainsItsPhysicalSession() async {
    let manager = PushToTalkManager.shared
    let hub = RealtimeHubController.shared
    let defaults = ownerBoundaryDefaults("active-hub")
    manager.cleanup()
    await transitionOwner(defaults: defaults, to: "owner-a")

    _ = manager.beginPushToTalkForAutomation()
    manager.cleanup()
    hub.installOwnerBoundaryFixture(ownerID: "owner-a")
    let turnID = VoiceTurnCoordinator.shared.begin(intent: .hold, ownerID: "owner-a")
    VoiceTurnCoordinator.shared.publish(
      .selectRoute(turnID: turnID, route: .hub(sessionID: nil)))
    let captureID = VoiceCaptureID(manager.ownerBoundarySnapshot.captureGeneration)
    VoiceTurnCoordinator.shared.publish(
      .captureStarted(turnID: turnID, captureID: captureID))

    await transitionOwner(defaults: defaults, to: "owner-b")

    XCTAssertEqual(defaults.string(forKey: .authUserId), "owner-b")
    XCTAssertEqual(VoiceTurnCoordinator.shared.model.lastTerminal?.turnID, turnID)
    XCTAssertEqual(VoiceTurnCoordinator.shared.model.lastTerminal?.reason, .ownerChanged)
    assertHubOwnerBoundaryIsEmpty(hub.ownerBoundarySnapshot)

    manager.cleanup()
    defaults.removePersistentDomain(forName: ownerBoundarySuiteName("active-hub"))
  }

  @MainActor
  func testOwnerTransitionAwaitsExternalVoiceRunTerminalizationBeforeOwnerBAdmission() async {
    let manager = PushToTalkManager.shared
    let hub = RealtimeHubController.shared
    let defaults = ownerBoundaryDefaults("active-external-run")
    let probe = OwnerBoundaryExternalRunProbe()
    manager.cleanup()
    await transitionOwner(defaults: defaults, to: "owner-a")

    _ = manager.beginPushToTalkForAutomation()
    manager.cleanup()
    hub.installOwnerBoundaryFixture(ownerID: "owner-a")
    let turnID = VoiceTurnCoordinator.shared.begin(intent: .hold, ownerID: "owner-a")
    VoiceTurnCoordinator.shared.publish(
      .selectRoute(turnID: turnID, route: .hub(sessionID: nil)))
    VoiceTurnCoordinator.shared.publish(
      .captureStarted(
        turnID: turnID,
        captureID: VoiceCaptureID(manager.ownerBoundarySnapshot.captureGeneration)))
    hub.installOwnerBoundaryExternalRunFixture(
      ownerID: "owner-a",
      turnID: turnID
    ) { binding, status, _, capability in
      try await probe.terminalize(
        binding: binding,
        status: status,
        capability: capability)
    }

    let transition = Task { @MainActor in
      await self.transitionOwner(defaults: defaults, to: "owner-b")
    }
    await probe.waitUntilEntered()

    XCTAssertEqual(defaults.string(forKey: .authUserId), "owner-a")
    XCTAssertNil(
      RuntimeOwnerIdentity.currentOwnerId(
        defaults: defaults,
        allowAutomationOverride: false))
    let suspendedTerminal = await probe.snapshot()
    XCTAssertFalse(suspendedTerminal.closed)

    await probe.release()
    await transition.value

    let terminal = await probe.snapshot()
    XCTAssertTrue(terminal.closed)
    XCTAssertEqual(terminal.ownerID, "owner-a")
    XCTAssertEqual(terminal.status, .cancelled)
    XCTAssertEqual(defaults.string(forKey: .authUserId), "owner-b")
    XCTAssertEqual(VoiceTurnCoordinator.shared.model.lastTerminal?.reason, .ownerChanged)
    assertHubOwnerBoundaryIsEmpty(hub.ownerBoundarySnapshot)

    manager.cleanup()
    defaults.removePersistentDomain(forName: ownerBoundarySuiteName("active-external-run"))
  }

  @MainActor
  func testUnresolvedExternalVoiceRunStaysTrackedUntilOwnerWideRevocation() async {
    let manager = PushToTalkManager.shared
    let hub = RealtimeHubController.shared
    let defaults = ownerBoundaryDefaults("unresolved-external-run")
    manager.cleanup()
    await transitionOwner(defaults: defaults, to: "owner-a")

    // Install the production terminal-effect handler without starting a real
    // microphone capture, then model a begin whose receipt was lost to Swift.
    _ = manager.beginPushToTalkForAutomation()
    manager.cleanup()
    let turnID = VoiceTurnCoordinator.shared.begin(intent: .hold, ownerID: "owner-a")
    hub.installOwnerBoundaryUnresolvedExternalRunFixture(
      ownerID: "owner-a",
      turnID: turnID)

    VoiceTurnCoordinator.shared.publish(.cancel(turnID: turnID, reason: .cancelled))
    await hub.settleOwnerBoundaryExternalRunTerminalizations()

    XCTAssertTrue(
      hub.ownerBoundarySnapshot.hasPendingOwnerWork,
      "an unknown binding must remain tracked until owner-wide runtime revocation")

    await transitionOwner(defaults: defaults, to: "owner-b")

    XCTAssertEqual(defaults.string(forKey: .authUserId), "owner-b")
    assertHubOwnerBoundaryIsEmpty(hub.ownerBoundarySnapshot)

    manager.cleanup()
    defaults.removePersistentDomain(forName: ownerBoundarySuiteName("unresolved-external-run"))
  }

  @MainActor
  private func transitionOwner(defaults: UserDefaults, to ownerID: String) async {
    await RuntimeOwnerIdentity.performEffectiveOwnerTransition(
      defaults: defaults,
      allowAutomationOverride: false,
      plannedNextOwner: { _, _ in ownerID },
      retargetLocalStorage: { _, _ in },
      ownerDidChange: {}
    ) { defaults in
      defaults.set(ownerID, forKey: .authUserId)
    }
  }

  private func ownerBoundaryDefaults(_ suffix: String) -> UserDefaults {
    let name = ownerBoundarySuiteName(suffix)
    let defaults = UserDefaults(suiteName: name)!
    defaults.removePersistentDomain(forName: name)
    return defaults
  }

  private func ownerBoundarySuiteName(_ suffix: String) -> String {
    "PushToTalkStateMachineTests.owner-boundary.\(suffix)"
  }

  private func assertHubOwnerBoundaryIsEmpty(
    _ snapshot: RealtimeHubOwnerBoundarySnapshot,
    file: StaticString = #filePath,
    line: UInt = #line
  ) {
    XCTAssertFalse(snapshot.hasPhysicalSession, file: file, line: line)
    XCTAssertNil(snapshot.physicalOwnerID, file: file, line: line)
    XCTAssertNil(snapshot.prefetchedOwnerID, file: file, line: line)
    XCTAssertTrue(snapshot.prefetchedContextIsEmpty, file: file, line: line)
    XCTAssertFalse(snapshot.hasPendingOwnerWork, file: file, line: line)
    XCTAssertFalse(snapshot.hubConnected, file: file, line: line)
    XCTAssertEqual(snapshot.turnAudioByteCount, 0, file: file, line: line)
  }
}
