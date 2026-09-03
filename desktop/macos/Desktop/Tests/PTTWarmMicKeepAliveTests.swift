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

    // Scoped to the function that displaces the capture, and ordered: a re-arm
    // that sits anywhere else in the file, or ahead of the release, would satisfy
    // a whole-file `contains` while leaving the microphone exactly as cold as the
    // regression left it.
    guard let body = functionBody(named: "func startMicCaptureIfNeeded() async -> Bool {", in: source)
    else { return XCTFail("startMicCaptureIfNeeded not found — the displacing path moved") }

    guard let release = body.range(of: "PushToTalkManager.shared.releaseParkedMicCapture()") else {
      return XCTFail("ambient startup no longer releases the parked PTT capture")
    }
    guard
      let rearm = body.range(
        of: "PushToTalkManager.shared.schedulePTTCaptureWarmup(trigger: .ambientCaptureStarted)")
    else {
      return XCTFail("releasing the parked PTT capture must be followed by re-arming one")
    }
    XCTAssertTrue(
      release.upperBound < rearm.lowerBound,
      "the re-arm must follow the release, not precede it")
  }

  /// Brace-matched body of a Swift function, so an ordering assertion cannot be
  /// satisfied by a match somewhere else in the file.
  private func functionBody(named signature: String, in source: String) -> Substring? {
    guard let start = source.range(of: signature) else { return nil }
    var depth = 1
    var index = start.upperBound
    while index < source.endIndex {
      switch source[index] {
      case "{": depth += 1
      case "}":
        depth -= 1
        if depth == 0 { return source[start.upperBound..<index] }
      default: break
      }
      index = source.index(after: index)
    }
    return nil
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

  /// A warm capture whose CoreAudio start has not resolved holds the same device
  /// as a parked one, and it cannot be stopped: `AudioCaptureService.stopCapture`
  /// returns immediately while `isCapturing` is false, and that flag only flips
  /// at the end of the HAL setup — the whole window the warm-up exists to hide.
  /// So the boundary every caller awaits is the warm start's own completion, and
  /// that completion is what has to stop the capture.
  func testAnInFlightWarmCaptureIsTornDownByItsOwnCompletion() throws {
    let source = try pushToTalkManagerSource()

    XCTAssertTrue(
      source.contains("guard let self, self.warmCapture?.service === capture else {"),
      "the warm start's completion must defer to whoever released it")
    guard let superseded = source.range(of: "guard let self, self.warmCapture?.service === capture else {")
    else { return XCTFail("the superseded branch moved") }
    let branch = String(source[superseded.lowerBound...].prefix(500))
    XCTAssertTrue(
      branch.contains("capture.stopCapture()") && branch.contains("await capture.waitForPhysicalStop()"),
      "a superseded warm capture must be stopped and drained, not merely dropped")
    XCTAssertTrue(
      source.contains("guard RuntimeOwnerIdentity.currentOwnerId() == ownerID,"),
      "a capture opened for the previous owner must not park under the next one")
    XCTAssertTrue(
      source.contains("if displacedWarmCapture { await self.drainInFlightWarmCapture() }"),
      "a turn starting must drain the warm teardown before opening the device")
    XCTAssertTrue(
      source.contains("let displacedWarmCapture = hasWarmCaptureToDrain"),
      "a release that kept its handle still leaves a teardown for the press to wait on")
  }

  /// Releasing must not consume the teardown handle. Terminal cleanup and capture
  /// rebuilds release with no async boundary to wait on; if that dropped the
  /// handle it would disarm the wait every other caller makes — including the
  /// owner-transition drain, which is INV-AUTH-1 fencing rather than latency.
  func testReleasingAWarmCaptureKeepsTheTeardownHandleForOtherCallers() throws {
    let source = try pushToTalkManagerSource()

    XCTAssertTrue(source.contains("func releaseInFlightWarmCapture() {"))
    XCTAssertTrue(source.contains("warmTeardown = warm.start"))
    XCTAssertFalse(
      source.contains("func releaseInFlightWarmCapture() -> Task<Void, Never>?"),
      "handing the only handle to one caller is what disarmed the other waits")
    XCTAssertTrue(
      source.contains("await drainInFlightWarmCapture(timeout: Self.ownerTransitionWarmCaptureWaitSeconds)"),
      "the owner transition must drain a previous owner's warm capture completely")
    XCTAssertTrue(
      source.contains("|| warmCapture != nil || warmTeardown != nil)"),
      "a second warm capture must not start while one is still tearing down")
  }

  /// A synthetic turn's disposition must not depend on harness timing: the
  /// automation bridge bypasses the microphone entirely, so there is no
  /// capture-start latency to charge to its "hold".
  func testAnAutomationTurnIsNotJudgedOnItsHold() throws {
    let source = try pushToTalkManagerSource()

    XCTAssertTrue(source.contains("pttLifecycle.captureWasRequested ? pttLifecycle.holdSeconds : nil"))
    // Count the thing that must not spread, not the gate that wraps it: the raw
    // hold has exactly one reader, the gate itself. (Counting `judgeableHoldSeconds`
    // instead went red the moment a comment named it — a headcount of the safe
    // name measures prose, a headcount of the unsafe one measures the invariant.)
    XCTAssertEqual(
      source.components(separatedBy: "pttLifecycle.holdSeconds").count - 1, 1,
      "the ungated hold must be read only by judgeableHoldSeconds")
    // And every discard reader takes the gated value.
    XCTAssertEqual(
      source.components(separatedBy: "holdSec: judgeableHoldSeconds ?? totalSec").count - 1, 4,
      "every dead-mic policy call site must pass the gated hold")
    XCTAssertTrue(
      source.contains("holdSeconds: judgeableHoldSeconds,"),
      "the discard judgement must read the gated hold")
    // What makes an automation turn ungated: it returns before `startMicCapture`,
    // so nothing ever records a capture-start request for it.
    let bridge = try pushToTalkManagerSource()
    XCTAssertTrue(bridge.contains("if automationCaptureBypass, let turnID = currentVoiceTurnID {"))
  }

  /// The device the snapshot vetted and the device that actually opened are not
  /// the same thing: `.device(nil)` follows the system default, which can become
  /// a headset in between. Holding a Bluetooth input open unattended is the harm.
  func testAWarmCaptureThatOpensABluetoothInputIsStopped() throws {
    let source = try pushToTalkManagerSource()

    XCTAssertTrue(
      source.contains("guard routeClass != .bluetooth, !capture.isCurrentDeviceBluetoothTransport else {"))
  }

  /// The hold is latched where the key comes up, not at finalization —
  /// finalization is a whole `lockDecision` window later on the default
  /// tap-to-lock path, and longer still on a cold realtime hub.
  func testTheHoldIsLatchedAtKeyUpNotAtFinalization() throws {
    let source = try pushToTalkManagerSource()

    guard let keyUp = source.range(of: "private func handleShortcutUp() {"),
      let release = source.range(of: "pttLifecycle.noteRelease()", range: keyUp.upperBound..<source.endIndex),
      let lockWindow = source.range(of: "enterPendingLockDecision()", range: keyUp.upperBound..<source.endIndex)
    else {
      return XCTFail("the release latch or the tap-to-lock branch moved")
    }
    XCTAssertLessThan(
      release.lowerBound, lockWindow.lowerBound,
      "noteRelease must run before the tap-to-lock window defers finalization")
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
