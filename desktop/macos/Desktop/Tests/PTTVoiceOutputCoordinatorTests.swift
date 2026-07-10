import XCTest

@testable import Omi_Computer

@MainActor
final class PTTVoiceOutputCoordinatorTests: XCTestCase {
  func testAudioPlayerMustActuallyStartBeforePlaybackOwnsLease() {
    XCTAssertTrue(VoicePlaybackStartPolicy.accepts(started: true))
    XCTAssertFalse(VoicePlaybackStartPolicy.accepts(started: false))
  }

  func testFillerCarriesTextIntoSystemVoiceFallback() throws {
    let sourceURL = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources/FloatingControlBar/FloatingBarVoicePlaybackService.swift")
    let source = try String(contentsOf: sourceURL, encoding: .utf8)

    XCTAssertTrue(source.contains("startPlayback(audioData, fallbackText: phrase)"))
    XCTAssertTrue(source.contains("no fallback speech available"))
  }
  func testFallbackCannotStartAfterNativeRealtimeLease() {
    let coordinator = VoiceOutputCoordinator()
    let turnID = coordinator.beginTurn()
    let native = tryLease(coordinator.acquire(.nativeRealtime, turnID: turnID))

    XCTAssertEqual(native?.lane, .nativeRealtime)
    XCTAssertEqual(
      coordinator.acquire(.selectedVoiceFallback, turnID: turnID),
      native.map { .denied(active: $0) })
  }

  func testLateNativeAudioIsDeniedAfterFallbackLease() {
    let coordinator = VoiceOutputCoordinator()
    let turnID = coordinator.beginTurn()
    let fallback = tryLease(coordinator.acquire(.selectedVoiceFallback, turnID: turnID))

    XCTAssertEqual(
      coordinator.acquire(.nativeRealtime, turnID: turnID),
      fallback.map { .denied(active: $0) })
  }

  func testEveryPTTAudibleLaneCompetesForTheSameLease() {
    for firstLane in VoiceOutputLane.allCases {
      for competingLane in VoiceOutputLane.allCases where competingLane != firstLane {
        let coordinator = VoiceOutputCoordinator()
        let turnID = coordinator.beginTurn()
        let first = tryLease(coordinator.acquire(firstLane, turnID: turnID))

        XCTAssertEqual(
          coordinator.acquire(competingLane, turnID: turnID),
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

  func testSameLaneAcquireIsIdempotent() throws {
    let coordinator = VoiceOutputCoordinator()
    let turnID = coordinator.beginTurn()
    let first = try XCTUnwrap(tryLease(coordinator.acquire(.nativeRealtime, turnID: turnID)))
    let second = try XCTUnwrap(tryLease(coordinator.acquire(.nativeRealtime, turnID: turnID)))

    XCTAssertEqual(first, second)
  }

  func testDeterministicAckSuppressesProviderOutputForTurn() {
    let coordinator = VoiceOutputCoordinator()
    let turnID = coordinator.beginTurn()

    XCTAssertNotNil(tryLease(coordinator.acquire(.deterministicAgentAck, turnID: turnID)))
    XCTAssertTrue(coordinator.snapshot().providerOutputSuppressed)
  }

  func testStaleReleaseCannotClearCurrentLease() throws {
    let coordinator = VoiceOutputCoordinator()
    let firstTurnID = coordinator.beginTurn()
    let staleLease = try XCTUnwrap(
      tryLease(coordinator.acquire(.nativeRealtime, turnID: firstTurnID)))
    let secondTurnID = coordinator.beginTurn()
    let currentLease = try XCTUnwrap(
      tryLease(coordinator.acquire(.selectedVoiceFallback, turnID: secondTurnID)))

    XCTAssertFalse(coordinator.release(staleLease))
    XCTAssertEqual(coordinator.snapshot().activeLease, currentLease)
  }

  func testStaleTurnCannotAcquireOrEndCurrentTurn() {
    let coordinator = VoiceOutputCoordinator()
    let staleTurnID = coordinator.beginTurn()
    let currentTurnID = coordinator.beginTurn()

    XCTAssertEqual(coordinator.acquire(.nativeRealtime, turnID: staleTurnID), .staleTurn)
    XCTAssertFalse(coordinator.endTurn(staleTurnID))
    XCTAssertEqual(coordinator.snapshot().turnID, currentTurnID)
  }

  func testReleaseRequiresExactLeaseIdentity() throws {
    let coordinator = VoiceOutputCoordinator()
    let turnID = coordinator.beginTurn()
    let lease = try XCTUnwrap(tryLease(coordinator.acquire(.nativeRealtime, turnID: turnID)))
    let impostor = VoiceOutputLease(id: VoiceLeaseID(), turnID: turnID, lane: .nativeRealtime)

    XCTAssertFalse(coordinator.release(impostor))
    XCTAssertEqual(coordinator.snapshot().activeLease, lease)
    XCTAssertTrue(coordinator.release(lease))
    XCTAssertNil(coordinator.snapshot().activeLease)
  }

  func testInterruptRequiresCurrentTurnAndRevokesLease() {
    let coordinator = VoiceOutputCoordinator()
    let turnID = coordinator.beginTurn()
    XCTAssertNotNil(tryLease(coordinator.acquire(.systemVoiceFallback, turnID: turnID)))

    XCTAssertFalse(coordinator.interrupt(turnID: VoiceTurnID()))
    XCTAssertNotNil(coordinator.snapshot().activeLease)
    XCTAssertTrue(coordinator.interrupt(turnID: turnID))
    XCTAssertNil(coordinator.snapshot().activeLease)
  }

  private func tryLease(_ decision: VoiceOutputDecision) -> VoiceOutputLease? {
    guard case .acquired(let lease) = decision else { return nil }
    return lease
  }
}
