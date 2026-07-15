import XCTest

@testable import Omi_Computer

@MainActor
final class VoiceTurnOutputOwnershipTests: XCTestCase {
  func testAudioPlayerMustActuallyStartBeforePlaybackOwnsLease() {
    XCTAssertTrue(VoicePlaybackStartPolicy.accepts(started: true))
    XCTAssertFalse(VoicePlaybackStartPolicy.accepts(started: false))
  }

  func testOldSystemSpeechCallbackCannotOwnNewerUtterance() {
    let firstUtterance = NSObject()
    let currentUtterance = NSObject()
    let leaseID = VoiceLeaseID()
    let token = SystemSpeechToken(
      generation: 8,
      leaseID: leaseID,
      utterance: currentUtterance)

    XCTAssertFalse(
      SystemSpeechCallbackPolicy.accepts(
        callbackUtterance: firstUtterance,
        currentToken: token,
        playbackGeneration: 8,
        activeLeaseID: leaseID))
    XCTAssertFalse(
      SystemSpeechCallbackPolicy.accepts(
        callbackUtterance: currentUtterance,
        currentToken: token,
        playbackGeneration: 9,
        activeLeaseID: leaseID))
    XCTAssertFalse(
      SystemSpeechCallbackPolicy.accepts(
        callbackUtterance: currentUtterance,
        currentToken: token,
        playbackGeneration: 8,
        activeLeaseID: VoiceLeaseID()))
    XCTAssertTrue(
      SystemSpeechCallbackPolicy.accepts(
        callbackUtterance: currentUtterance,
        currentToken: token,
        playbackGeneration: 8,
        activeLeaseID: leaseID))
  }

  func testCancelledBackgroundKickoffCannotUseCachedOrSystemFallback() {
    let leaseID = VoiceLeaseID()
    let token = VoiceSynthesisToken(generation: 4, leaseID: leaseID)

    XCTAssertFalse(
      VoiceSynthesisFallbackPolicy.shouldUseFallback(
        afterCancellation: true,
        token: token,
        playbackGeneration: 4,
        activeLeaseID: leaseID))
    XCTAssertTrue(
      VoiceSynthesisFallbackPolicy.shouldUseFallback(
        afterCancellation: false,
        token: token,
        playbackGeneration: 4,
        activeLeaseID: leaseID))
  }

  func testSupersededCloudSynthesisCannotFallbackIntoNewLease() {
    let token = VoiceSynthesisToken(generation: 4, leaseID: VoiceLeaseID())

    XCTAssertFalse(
      VoiceSynthesisFallbackPolicy.shouldUseFallback(
        afterCancellation: false,
        token: token,
        playbackGeneration: 4,
        activeLeaseID: VoiceLeaseID()))
  }

  func testFillerCarriesTextIntoSystemVoiceFallback() throws {
    let sourceURL = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources/FloatingControlBar/FloatingBarVoicePlaybackService.swift")
    let source = try String(contentsOf: sourceURL, encoding: .utf8)

    XCTAssertTrue(source.contains("startPlayback(audioData, fallbackText: phrase)"))
    XCTAssertTrue(source.contains("no fallback speech available"))
    XCTAssertTrue(source.contains("recordSelectedVoiceFallback("))
    XCTAssertTrue(source.contains("to: \"system_voice_fallback\""))
    XCTAssertTrue(source.contains("outcome: .degraded"))
    XCTAssertTrue(source.contains("? .exhausted : .degraded"))
  }
  func testFallbackCannotStartAfterNativeRealtimeLease() {
    let (coordinator, turnID) = awaitingCoordinator()
    let native = tryLease(coordinator.acquireOutput(.nativeRealtime, turnID: turnID))

    XCTAssertEqual(native?.lane, .nativeRealtime)
    XCTAssertEqual(
      coordinator.acquireOutput(.selectedVoiceFallback, turnID: turnID),
      native.map { .denied(active: $0) })
  }

  func testLateNativeAudioIsDeniedAfterFallbackLease() {
    let (coordinator, turnID) = awaitingCoordinator()
    let fallback = tryLease(coordinator.acquireOutput(.selectedVoiceFallback, turnID: turnID))

    XCTAssertEqual(
      coordinator.acquireOutput(.nativeRealtime, turnID: turnID),
      fallback.map { .denied(active: $0) })
  }

  func testEveryPTTAudibleLaneCompetesForTheSameLease() {
    for firstLane in VoiceOutputLane.allCases {
      for competingLane in VoiceOutputLane.allCases where competingLane != firstLane {
        let (coordinator, turnID) = awaitingCoordinator()
        let first = tryLease(coordinator.acquireOutput(firstLane, turnID: turnID))

        XCTAssertEqual(
          coordinator.acquireOutput(competingLane, turnID: turnID),
          first.map { .denied(active: $0) },
          "\(competingLane) should not overlap \(firstLane)")
      }
    }
  }

  func testFillerIsTheOnlyLaneThatYieldsToRealOutputOnTheSameTurn() throws {
    let turnID = VoiceTurnID()
    let filler = VoiceOutputLease(id: VoiceLeaseID(), turnID: turnID, lane: .filler)

    for lane in VoiceOutputLane.allCases where lane != .filler {
      XCTAssertTrue(
        VoiceOutputHandoffPolicy.fillerCanYield(
          active: filler,
          to: lane,
          turnID: turnID))
    }
    XCTAssertFalse(
      VoiceOutputHandoffPolicy.fillerCanYield(
        active: filler,
        to: .filler,
        turnID: turnID))

    let native = VoiceOutputLease(id: VoiceLeaseID(), turnID: turnID, lane: .nativeRealtime)
    XCTAssertFalse(
      VoiceOutputHandoffPolicy.fillerCanYield(
        active: native,
        to: .selectedVoiceFallback,
        turnID: turnID))
    XCTAssertFalse(
      VoiceOutputHandoffPolicy.fillerCanYield(
        active: filler,
        to: .nativeRealtime,
        turnID: VoiceTurnID()))
  }

  func testFillerReleaseDoesNotFinishProviderAndRealOutputCanTakeLease() throws {
    let (coordinator, turnID) = awaitingCoordinator()
    let filler = try XCTUnwrap(tryLease(coordinator.acquireOutput(.filler, turnID: turnID)))

    XCTAssertTrue(coordinator.releaseOutput(filler))
    XCTAssertEqual(coordinator.activeTurn?.phase, .awaitingResponse)
    XCTAssertFalse(coordinator.activeTurn?.providerFinished == true)
    XCTAssertEqual(coordinator.activeTurn?.journalFinalization, .pending)

    let realOutput = try XCTUnwrap(
      tryLease(coordinator.acquireOutput(.selectedVoiceFallback, turnID: turnID)))
    XCTAssertEqual(realOutput.lane, .selectedVoiceFallback)
    XCTAssertEqual(coordinator.outputSnapshot.activeLease, realOutput)
  }

  func testSameLaneAcquireIsIdempotent() throws {
    let (coordinator, turnID) = awaitingCoordinator()
    let first = try XCTUnwrap(tryLease(coordinator.acquireOutput(.nativeRealtime, turnID: turnID)))
    let second = try XCTUnwrap(tryLease(coordinator.acquireOutput(.nativeRealtime, turnID: turnID)))

    XCTAssertEqual(first, second)
  }

  func testDeterministicAckSuppressesProviderOutputForTurn() {
    let (coordinator, turnID) = awaitingCoordinator()

    XCTAssertNotNil(tryLease(coordinator.acquireOutput(.deterministicAgentAck, turnID: turnID)))
    XCTAssertTrue(coordinator.outputSnapshot.providerOutputSuppressed)
  }

  func testAuthoritativeScreenEvidenceCanTakeOverSpeculativeNativeLease() throws {
    let (coordinator, turnID) = awaitingCoordinator()
    let native = try XCTUnwrap(tryLease(coordinator.acquireOutput(.nativeRealtime, turnID: turnID)))

    XCTAssertTrue(coordinator.releaseOutput(native))
    let screen = try XCTUnwrap(
      tryLease(coordinator.acquireOutput(.deterministicScreenEvidence, turnID: turnID)))

    XCTAssertEqual(screen.lane, .deterministicScreenEvidence)
    XCTAssertEqual(coordinator.outputSnapshot.activeLease, screen)
  }

  func testStaleReleaseCannotClearCurrentLease() throws {
    let (coordinator, firstTurnID) = awaitingCoordinator()
    let staleLease = try XCTUnwrap(
      tryLease(coordinator.acquireOutput(.nativeRealtime, turnID: firstTurnID)))
    let secondTurnID = coordinator.begin(intent: .hold)
    coordinator.send(.selectRoute(turnID: secondTurnID, route: .deepgramBatch))
    coordinator.send(.finalize(turnID: secondTurnID))
    coordinator.send(.transcriptionStarted(turnID: secondTurnID))
    coordinator.send(.transcriptionFinal(turnID: secondTurnID, text: "second"))
    let currentLease = try XCTUnwrap(
      tryLease(coordinator.acquireOutput(.selectedVoiceFallback, turnID: secondTurnID)))

    XCTAssertFalse(coordinator.releaseOutput(staleLease))
    XCTAssertEqual(coordinator.outputSnapshot.activeLease, currentLease)
  }

  func testStaleTurnCannotAcquireOrEndCurrentTurn() {
    let (coordinator, staleTurnID) = awaitingCoordinator()
    let currentTurnID = coordinator.begin(intent: .hold)

    XCTAssertEqual(coordinator.acquireOutput(.nativeRealtime, turnID: staleTurnID), .staleTurn)
    XCTAssertEqual(coordinator.outputSnapshot.turnID, currentTurnID)
  }

  func testReleaseRequiresExactLeaseIdentity() throws {
    let (coordinator, turnID) = awaitingCoordinator()
    let lease = try XCTUnwrap(tryLease(coordinator.acquireOutput(.nativeRealtime, turnID: turnID)))
    let impostor = VoiceOutputLease(id: VoiceLeaseID(), turnID: turnID, lane: .nativeRealtime)

    XCTAssertFalse(coordinator.releaseOutput(impostor))
    XCTAssertEqual(coordinator.outputSnapshot.activeLease, lease)
    XCTAssertTrue(coordinator.releaseOutput(lease))
    XCTAssertNil(coordinator.outputSnapshot.activeLease)
  }

  func testInterruptRequiresCurrentTurnAndRevokesLease() {
    let (coordinator, turnID) = awaitingCoordinator()
    XCTAssertNotNil(tryLease(coordinator.acquireOutput(.systemVoiceFallback, turnID: turnID)))

    coordinator.send(.interrupt(turnID: VoiceTurnID()))
    XCTAssertNotNil(coordinator.outputSnapshot.activeLease)
    coordinator.send(.interrupt(turnID: turnID))
    XCTAssertNil(coordinator.outputSnapshot.activeLease)
    XCTAssertEqual(coordinator.model.lastTerminal?.reason, .explicitInterrupt)
  }

  private func awaitingCoordinator() -> (VoiceTurnCoordinator, VoiceTurnID) {
    let coordinator = VoiceTurnCoordinator()
    let turnID = coordinator.begin(intent: .hold)
    coordinator.send(.selectRoute(turnID: turnID, route: .deepgramBatch))
    coordinator.send(.finalize(turnID: turnID))
    coordinator.send(.transcriptionStarted(turnID: turnID))
    coordinator.send(.transcriptionFinal(turnID: turnID, text: "fixture"))
    return (coordinator, turnID)
  }

  private func tryLease(_ decision: VoiceOutputDecision) -> VoiceOutputLease? {
    guard case .acquired(let lease) = decision else { return nil }
    return lease
  }
}
