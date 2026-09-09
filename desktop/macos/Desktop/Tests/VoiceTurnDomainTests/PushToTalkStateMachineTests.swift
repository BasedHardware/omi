import XCTest

@testable import Omi_Computer
@testable import VoiceTurnDomain

private actor OwnerBoundaryExternalRunProbe {
  private var entered = false
  private var released = false
  private var closed = false
  private var observedOwnerID: String?
  private var observedStatus: ExternalSurfaceRunTerminalStatus?
  private var observedFinalText: String?
  private var enteredWaiters: [CheckedContinuation<Void, Never>] = []
  private var releaseWaiters: [CheckedContinuation<Void, Never>] = []

  func terminalize(
    binding: ExternalSurfaceRunBinding,
    status: ExternalSurfaceRunTerminalStatus,
    finalText: String?,
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
    observedFinalText = finalText
    entered = true
    let waiters = enteredWaiters
    enteredWaiters.removeAll()
    for waiter in waiters { waiter.resume() }
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
    for waiter in waiters { waiter.resume() }
  }

  func snapshot() -> (
    closed: Bool, ownerID: String?, status: ExternalSurfaceRunTerminalStatus?, finalText: String?
  ) {
    (closed, observedOwnerID, observedStatus, observedFinalText)
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
      #if DEBUG
        manager.testingTurnScreenEvidenceCapture = nil
      #endif
      manager.cleanup()
      RealtimeHubController.shared.clearScreenGrounding()
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

    #if DEBUG
      var compositorInvocations = 0
      manager.testingTurnScreenEvidenceCapture = { turnID in
        compositorInvocations += 1
        return RealtimeScreenEvidenceCapture.unavailable(for: turnID, failure: .captureUnavailable)
      }
    #endif

    let started = manager.beginPushToTalkForAutomation()
    XCTAssertEqual(started["listening"], "true")
    XCTAssertEqual(started["screen_evidence"], "skipped")
    XCTAssertEqual(started["hub_ready"], RealtimeHubController.shared.isTransportReady ? "true" : "false")
    XCTAssertTrue(
      started["ptt_admission"] == "immediate" || started["ptt_admission"] == "capture_and_buffer")
    XCTAssertEqual(VoiceTurnCoordinator.shared.activeTurn?.phase, .recording)
    XCTAssertEqual(
      RealtimeHubController.shared.screenEvidence?.descriptor.captureFailure,
      .automationBypass)
    #if DEBUG
      XCTAssertEqual(compositorInvocations, 0, "bypass must not invoke compositor capture")
    #endif

    let stopped = manager.endPushToTalkForAutomation()
    XCTAssertEqual(stopped["finalized"], "true")
    XCTAssertEqual(VoiceTurnCoordinator.shared.model.turn?.phase, .terminal(.tooShort))
    XCTAssertEqual(VoiceTurnCoordinator.shared.model.turn?.projection.hint, "Hold longer to record")
    XCTAssertEqual(VoiceTurnCoordinator.shared.model.staleEventCount, 0)
    XCTAssertEqual(VoiceTurnCoordinator.shared.model.invalidTransitionCount, 0)
  }

  #if DEBUG
    @MainActor
    func testBypassStartDoesNotCaptureSynchronouslyAndDropsLateEvidence() {
      let manager = PushToTalkManager.shared
      let previousAuthOwner = UserDefaults.standard.object(forKey: .authUserId)
      let previousAutomationOwner = UserDefaults.standard.object(forKey: .automationOwnerOverride)
      manager.cleanup()
      RealtimeHubController.shared.clearScreenGrounding()
      UserDefaults.standard.set("ptt-headless-owner", forKey: .authUserId)
      UserDefaults.standard.removeObject(forKey: .automationOwnerOverride)
      var compositorInvocations = 0
      manager.testingTurnScreenEvidenceCapture = { turnID in
        compositorInvocations += 1
        return RealtimeScreenEvidenceCapture.unavailable(for: turnID, failure: .captureUnavailable)
      }
      defer {
        manager.testingTurnScreenEvidenceCapture = nil
        manager.cleanup()
        RealtimeHubController.shared.clearScreenGrounding()
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

      let first = manager.beginPushToTalkForAutomation()
      XCTAssertEqual(first["listening"], "true")
      XCTAssertEqual(first["screen_evidence"], "skipped")
      XCTAssertEqual(compositorInvocations, 0)
      guard let firstTurnID = VoiceTurnCoordinator.shared.activeTurnID else {
        return XCTFail("bypass start must mint a turn")
      }
      let lateEvidence = RealtimeScreenEvidence(
        descriptor: RealtimeScreenEvidenceDescriptor(
          evidenceID: "late-first-turn",
          turnID: firstTurnID,
          capturedAt: Date(),
          target: .frontmostDisplay,
          frontmostApp: "TestApp",
          frontmostBundleID: "com.test.app",
          windowID: 1,
          displayID: 1,
          imageByteCount: 128,
          imageDigest: "late-digest"),
        preOverlayImage: nil,
        jpeg: Data([1, 2, 3]),
        encodingFinished: true)

      XCTAssertEqual(manager.endPushToTalkForAutomation()["finalized"], "true")

      let second = manager.beginPushToTalkForAutomation()
      XCTAssertEqual(second["listening"], "true")
      XCTAssertEqual(second["screen_evidence"], "skipped")
      guard let secondTurnID = VoiceTurnCoordinator.shared.activeTurnID else {
        return XCTFail("second bypass start must mint a turn")
      }
      XCTAssertNotEqual(firstTurnID, secondTurnID)
      RealtimeHubController.shared.installScreenEvidence(lateEvidence)
      XCTAssertEqual(
        RealtimeHubController.shared.screenEvidence?.descriptor.turnID,
        secondTurnID,
        "a deferred capture for an ended turn must not attach to a later turn")
      XCTAssertEqual(
        RealtimeHubController.shared.screenEvidence?.descriptor.captureFailure,
        .automationBypass)
      XCTAssertEqual(compositorInvocations, 0)
    }

    @MainActor
    func testPhysicalPathCapturesSynchronouslyBeforeCaptureStarted() {
      let manager = PushToTalkManager.shared
      let previousAuthOwner = UserDefaults.standard.object(forKey: .authUserId)
      let previousAutomationOwner = UserDefaults.standard.object(forKey: .automationOwnerOverride)
      manager.cleanup()
      RealtimeHubController.shared.clearScreenGrounding()
      UserDefaults.standard.set("ptt-physical-owner", forKey: .authUserId)
      UserDefaults.standard.removeObject(forKey: .automationOwnerOverride)
      let previousMute = ShortcutSettings.shared.pttMuteSystemAudio
      let previousSounds = ShortcutSettings.shared.pttSoundsEnabled
      ShortcutSettings.shared.pttMuteSystemAudio = false
      ShortcutSettings.shared.pttSoundsEnabled = false
      var compositorInvocations = 0
      var captureIDDuringCapture: VoiceCaptureID?
      manager.testingTurnScreenEvidenceCapture = { turnID in
        compositorInvocations += 1
        captureIDDuringCapture = VoiceTurnCoordinator.shared.model.turn?.captureID
        return RealtimeScreenEvidenceCapture.unavailable(for: turnID, failure: .captureUnavailable)
      }
      defer {
        manager.testingTurnScreenEvidenceCapture = nil
        ShortcutSettings.shared.pttMuteSystemAudio = previousMute
        ShortcutSettings.shared.pttSoundsEnabled = previousSounds
        manager.cleanup()
        RealtimeHubController.shared.clearScreenGrounding()
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

      manager.startListeningForPhysicalScreenEvidenceTest()
      XCTAssertEqual(compositorInvocations, 1)
      XCTAssertNil(
        captureIDDuringCapture,
        "physical pre-overlay capture must run before captureStarted is published")
    }
  #endif

  // The owner-boundary suite drives DEBUG-only seams (ownerBoundarySnapshot,
  // RealtimeHubOwnerBoundarySnapshot); the release-mode CI test compile must skip it.
  #if DEBUG
    @MainActor
    func testOwnerBoundaryEffectHandlerInstallDoesNotStartListening() {
      let manager = PushToTalkManager.shared
      manager.cleanup()
      defer { manager.cleanup() }

      manager.installOwnerBoundaryEffectHandlerFixture()

      XCTAssertNil(VoiceTurnCoordinator.shared.activeTurn)
      XCTAssertNil(manager.ownerBoundarySnapshot.activeTurnID)
      XCTAssertFalse(manager.ownerBoundarySnapshot.hasCaptureDriver)
      XCTAssertFalse(manager.ownerBoundarySnapshot.captureStartInFlight)
    }

    @MainActor
    func testOwnerTransitionTerminatesActiveNonHubCaptureBeforeOwnerBBecomesVisible() async {
      let manager = PushToTalkManager.shared
      let defaults = ownerBoundaryDefaults("non-hub")
      manager.cleanup()
      await transitionOwner(defaults: defaults, to: "owner-a")

      manager.installOwnerBoundaryEffectHandlerFixture()
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

      manager.installOwnerBoundaryEffectHandlerFixture()
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

      manager.installOwnerBoundaryEffectHandlerFixture()
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
        turnID: turnID,
        finalText: "Answer captured before UI cleanup."
      ) { binding, status, finalText, _, capability in
        try await probe.terminalize(
          binding: binding,
          status: status,
          finalText: finalText,
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
      XCTAssertEqual(terminal.finalText, "Answer captured before UI cleanup.")
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

      manager.installOwnerBoundaryEffectHandlerFixture()
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
      // `UserDefaults` is non-Sendable and cannot cross from the main actor into
      // the nonisolated `performEffectiveOwnerTransition` boundary under Swift 6.
      // Box it (mirroring the production `RuntimeOwnerDefaultsReference`) and run
      // the transition from a nonisolated static helper so neither `defaults` nor
      // `self` crosses an isolation boundary.
      let boxed = OwnerDefaultsBox(value: defaults)
      do {
        try await Self.runOwnerTransition(boxed: boxed, ownerID: ownerID)
      } catch {
        XCTFail("owner transition failed: \(error)")
      }
    }

    private static nonisolated func runOwnerTransition(
      boxed: OwnerDefaultsBox, ownerID: String
    ) async throws {
      try await RuntimeOwnerIdentity.performEffectiveOwnerTransition(
        defaults: boxed.value,
        allowAutomationOverride: false,
        plannedNextOwner: { _, _ in ownerID },
        retargetLocalStorage: { _, _ in },
        prepareLocalStorageTransition: { _, _ in },
        ownerDidChange: {},
        { defaults in
          defaults.set(ownerID, forKey: .authUserId)
        })
    }

    private func ownerBoundaryDefaults(_ suffix: String) -> UserDefaults {
      let name = ownerBoundarySuiteName(suffix)
      guard let defaults = UserDefaults(suiteName: name) else {
        preconditionFailure("UserDefaults suite unavailable: \(name)")
      }
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
  #endif
}

/// Sendable carrier for a non-Sendable `UserDefaults` so it can cross the
/// nonisolated owner-transition boundary under Swift 6 strict concurrency.
private struct OwnerDefaultsBox: @unchecked Sendable {
  let value: UserDefaults
}
