import XCTest

@testable import Omi_Computer

/// Static contracts for the PTT warm mic keep-alive and mic-contention routing
/// introduced with the Ray-Ban Meta microphone picker. These are labeled
/// source-inspection tripwires, not behavioral coverage: the guarded behavior
/// (CoreAudio IOProc reuse and cross-capture device contention) needs real
/// audio hardware, so the contract asserts the load-bearing code paths exist.
final class PTTWarmMicKeepAliveTests: XCTestCase {

  func testLateMicCaptureStartParksWarmInsteadOfLeakingIntoIdlePTT() throws {
    let source = try pushToTalkManagerSource()

    XCTAssertTrue(source.contains("let generation = micCaptureGeneration"))
    XCTAssertTrue(source.contains("self.parkMicCapture(capture, lease: lease, overrideID: overrideDeviceID)"))
    XCTAssertTrue(source.contains("self.audioCaptureService === capture"))
    XCTAssertTrue(source.contains("PushToTalkManager: mic capture start completed after turn ended — parked warm"))
    XCTAssertTrue(
      source.contains("voiceTurnCoordinator.publish(.captureStarted(turnID: turnID, captureID: captureID))"))
  }

  func testWarmMicReuseRestoresLeaseAndTerminalCleanupDiscardsParking() throws {
    let source = try pushToTalkManagerSource()

    XCTAssertTrue(source.contains("activeMicLease = parked.lease"))
    XCTAssertTrue(source.contains("activeMicOverrideID = overrideDeviceID"))
    // Terminal cleanup must fully release the mic — no warm capture may outlive
    // a turn the user explicitly ended.
    XCTAssertTrue(source.contains("parkWarm: false)"))
    XCTAssertTrue(
      source.contains("private func stopAudioTranscription(discardBufferedAudio: Bool = false, parkWarm: Bool = true)"))
  }

  /// The measured regression: onboarding completion starts ambient
  /// transcription, `startMicCaptureIfNeeded` releases the parked PTT capture so
  /// two IOProcs cannot overlap on one device, and nothing ever put one back. The
  /// release is correct; leaving the microphone cold behind it is not.
  func testAmbientTranscriptionReArmsTheWarmCaptureAfterDisplacingIt() throws {
    let sourceURL = sourcesRoot()
      .appendingPathComponent("AppState/AppState+Transcription.swift")
    // omi-test-quality: source-inspection -- static contract: ambient capture re-arms PTT behind itself
    let source = try String(contentsOf: sourceURL, encoding: .utf8)

    XCTAssertTrue(source.contains("PushToTalkManager.shared.releaseParkedMicCapture()"))
    XCTAssertTrue(
      source.contains(
        "PushToTalkManager.shared.schedulePTTCaptureWarmup(trigger: .ambientCaptureStarted)"),
      "releasing the parked PTT capture must be followed by re-arming one")
  }

  /// Onboarding completion and the first-real-app card both ask for a warm
  /// capture. Neither may release one: the card is shown seconds after ambient
  /// transcription opened the device, and a release there is exactly what left
  /// the first press cold.
  func testOnboardingCompletionAndTheCardWarmRatherThanRelease() throws {
    let onboardingURL = sourcesRoot()
      .appendingPathComponent("Onboarding/SecondBrain/SBOnboardingModel.swift")
    let cardURL = sourcesRoot()
      .appendingPathComponent("ProactiveAssistants/FirstRealApp/FirstRealAppCardCoordinator.swift")
    // omi-test-quality: source-inspection -- static contract: onboarding completion warms PTT capture
    let onboarding = try String(contentsOf: onboardingURL, encoding: .utf8)
    // omi-test-quality: source-inspection -- static contract: the card warms PTT capture when shown
    let card = try String(contentsOf: cardURL, encoding: .utf8)

    XCTAssertTrue(
      onboarding.contains(
        "PushToTalkManager.shared.prewarmMicCapture(trigger: .onboardingCompleted)"))
    XCTAssertFalse(onboarding.contains("releaseParkedMicCapture"))

    XCTAssertTrue(card.contains("PushToTalkManager.shared.prewarmMicCapture(trigger: .firstRealAppCard)"))
    XCTAssertTrue(card.contains("warmCapture()"))
    XCTAssertFalse(card.contains("releaseParkedMicCapture"))
  }

  /// The warm capture is the existing parked mechanism, not a second one: it
  /// hands its capture to `parkMicCapture` and publishes no turn events
  /// (INV-VOICE-1).
  func testWarmCaptureReusesTheParkedMechanismAndOwnsNoTurn() throws {
    let source = try pushToTalkManagerSource()

    XCTAssertTrue(source.contains("func prewarmMicCapture(trigger: PTTWarmCaptureAdmission.Trigger)"))
    XCTAssertTrue(source.contains("self.parkMicCapture(capture, lease: lease, overrideID: overrideDeviceID)"))
    XCTAssertTrue(source.contains("lease.setParked(true)"))
    guard let warmup = source.range(of: "func prewarmMicCapture(") else {
      return XCTFail("prewarmMicCapture is gone — this contract needs rewriting, not deleting")
    }
    let body = String(source[warmup.lowerBound...].prefix(4000))
    XCTAssertFalse(
      body.contains("voiceTurnCoordinator.publish"),
      "a warm capture must not publish turn events (INV-VOICE-1)")
  }

  /// A warm capture whose CoreAudio start has not resolved yet holds the same
  /// device as a parked one. Every caller that gives up the parked capture — a
  /// turn starting, terminal cleanup, an owner transition, ambient transcription
  /// taking the device — must get the in-flight one too, or two HAL starts race
  /// on one input.
  func testAnInFlightWarmCaptureIsReleasedByTheParkedCaptureHandshake() throws {
    let source = try pushToTalkManagerSource()

    XCTAssertTrue(source.contains("var warmCaptureInFlight: AudioCaptureService?"))
    XCTAssertTrue(source.contains("return releaseInFlightWarmCapture()"))
    XCTAssertTrue(
      source.contains("guard self.warmCaptureInFlight === capture else {"),
      "the warm start's completion must defer to whoever released it")
    XCTAssertTrue(
      source.contains("guard RuntimeOwnerIdentity.currentOwnerId() == ownerID,"),
      "a capture opened for the previous owner must not park under the next one")
  }

  /// The hold is latched at release, at the one shared finalization entry, before
  /// the realtime-hub branch can park the turn for a second or more.
  func testTheHoldIsLatchedAtReleaseBeforeTheHubWarmBranch() throws {
    let source = try pushToTalkManagerSource()

    guard let release = source.range(of: "pttLifecycle.noteRelease()"),
      let hubWait = source.range(of: "finalizing while realtime hub warms")
    else {
      return XCTFail("the release latch or the hub-warm branch moved")
    }
    XCTAssertLessThan(
      release.lowerBound, hubWait.lowerBound,
      "noteRelease must run before finalization can park the turn on the hub warm wait")
  }

  /// A turn that ends because capture was not ready keeps its capture parked —
  /// that parked capture is the retry the hint promises.
  func testCaptureNotReadyKeepsTheWarmCaptureForItsRetry() throws {
    let source = try pushToTalkManagerSource()

    XCTAssertTrue(
      source.contains(
        "case .success, .tooShort, .silentRejected, .interruptedByBargeIn, .captureNotReady:"))
    XCTAssertTrue(source.contains("schedulePTTCaptureWarmup(trigger: .captureNotReady)"))
  }

  func testPTTContentionIgnoresManagersOwnParkedCapture() throws {
    let source = try inputDeviceRoutingSource()

    XCTAssertTrue(source.contains("let parkedCapture = parkedMicCapture?.service"))
    XCTAssertTrue(source.contains("isDeviceActivelyCaptured(defaultInput, excluding: parkedCapture)"))
    XCTAssertTrue(source.contains("hasActiveCapture(excluding: parkedCapture)"))
  }

  func testMicrophonePickerUsesDeviceListenerInsteadOfPolling() throws {
    let sourceURL = sourcesRoot()
      .appendingPathComponent("MainWindow/Pages/Settings/Sections/MicrophonePickerCard.swift")
    // omi-test-quality: source-inspection -- static contract: settings listens for CoreAudio device changes
    let source = try String(contentsOf: sourceURL, encoding: .utf8)

    XCTAssertTrue(source.contains("AudioObjectAddPropertyListenerBlock"))
    XCTAssertTrue(source.contains("kAudioHardwarePropertyDevices"))
    XCTAssertTrue(source.contains(".task(id: deviceListObserver.revision)"))
    XCTAssertFalse(source.contains("refreshDevicesPeriodically"))
    XCTAssertFalse(source.contains("Task.sleep"))
  }

  func testSeedStaleReconnectDefersUntilTurnCompletion() throws {
    let controllerURL = sourcesRoot()
      .appendingPathComponent("FloatingControlBar/RealtimeHubController.swift")
    let lifecycleURL = sourcesRoot()
      .appendingPathComponent("FloatingControlBar/RealtimeHubController+SessionLifecycle.swift")
    // omi-test-quality: source-inspection -- static contract: seed-stale refresh defers past an in-flight turn
    let controller = try String(contentsOf: controllerURL, encoding: .utf8)
    // omi-test-quality: source-inspection -- static contract: turn completion drains the deferred refresh
    let lifecycle = try String(contentsOf: lifecycleURL, encoding: .utf8)

    XCTAssertTrue(controller.contains("pendingSessionRefreshReason = reason"))
    XCTAssertTrue(controller.contains("func applyPendingSessionRefreshIfIdle()"))
    XCTAssertTrue(
      lifecycle.contains("if pendingSessionRefreshReason != nil { applyPendingSessionRefreshIfIdle() }"),
      "turn completion must drain a deferred voice-seed refresh instead of dropping it")
  }

  private func sourcesRoot() -> URL {
    URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources")
  }

  private func pushToTalkManagerSource() throws -> String {
    // omi-test-quality: source-inspection -- static contract: PTT parks and reuses its warm mic capture
    try String(
      contentsOf: sourcesRoot().appendingPathComponent("FloatingControlBar/PushToTalkManager.swift"),
      encoding: .utf8)
  }

  private func inputDeviceRoutingSource() throws -> String {
    // omi-test-quality: source-inspection -- static contract: PTT routes around captures other components hold
    try String(
      contentsOf: sourcesRoot()
        .appendingPathComponent("FloatingControlBar/PushToTalkManager+InputDeviceRouting.swift"),
      encoding: .utf8)
  }
}
