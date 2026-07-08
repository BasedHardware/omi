import XCTest

@testable import Omi_Computer

final class PTTVoiceOutputCoordinatorTests: XCTestCase {
  func testFallbackCannotStartAfterNativeRealtimeLease() {
    var coordinator = PTTVoiceOutputCoordinator()
    let turnID = coordinator.beginTurn()

    guard case .acquired(let native) = coordinator.acquire(.nativeRealtime, turnID: turnID) else {
      return XCTFail("native realtime lease should acquire")
    }
    XCTAssertEqual(native.lane, .nativeRealtime)

    XCTAssertEqual(
      coordinator.acquire(.selectedVoiceFallback, turnID: turnID),
      .denied(active: native))
  }

  func testLateNativeAudioIsDeniedAfterFallbackLease() {
    var coordinator = PTTVoiceOutputCoordinator()
    let turnID = coordinator.beginTurn()

    guard case .acquired(let fallback) = coordinator.acquire(.selectedVoiceFallback, turnID: turnID) else {
      return XCTFail("fallback lease should acquire")
    }

    XCTAssertEqual(
      coordinator.acquire(.nativeRealtime, turnID: turnID),
      .denied(active: fallback))
  }

  func testDeterministicAckSuppressesProviderOutputForTurn() {
    var coordinator = PTTVoiceOutputCoordinator()
    let turnID = coordinator.beginTurn()

    guard case .acquired(let ack) = coordinator.acquire(.deterministicAgentAck, turnID: turnID) else {
      return XCTFail("deterministic ack lease should acquire")
    }

    XCTAssertTrue(coordinator.snapshot().providerOutputSuppressed)
    XCTAssertEqual(
      coordinator.acquire(.nativeRealtime, turnID: turnID),
      .denied(active: ack))
  }

  func testDeterministicAckDeniedIfNativeAudioAlreadyStarted() {
    var coordinator = PTTVoiceOutputCoordinator()
    let turnID = coordinator.beginTurn()

    guard case .acquired(let native) = coordinator.acquire(.nativeRealtime, turnID: turnID) else {
      return XCTFail("native realtime lease should acquire")
    }

    XCTAssertEqual(
      coordinator.acquire(.deterministicAgentAck, turnID: turnID),
      .denied(active: native))
    XCTAssertFalse(coordinator.snapshot().providerOutputSuppressed)
  }

  func testBargeInRevokesCurrentLease() {
    var coordinator = PTTVoiceOutputCoordinator()
    let oldTurnID = coordinator.beginTurn()
    XCTAssertNotNil(tryLease(coordinator.acquire(.selectedVoiceFallback, turnID: oldTurnID)))

    coordinator.interruptCurrentOutput()
    let newTurnID = coordinator.beginTurn()

    guard case .acquired(let native) = coordinator.acquire(.nativeRealtime, turnID: newTurnID) else {
      return XCTFail("new turn should acquire native lease after interruption")
    }
    XCTAssertEqual(native.turnID, newTurnID)
    XCTAssertNotEqual(native.turnID, oldTurnID)
  }

  func testStaleReleaseCannotClearCurrentLease() throws {
    var coordinator = PTTVoiceOutputCoordinator()
    let firstTurnID = coordinator.beginTurn()
    let staleLease = tryLease(coordinator.acquire(.nativeRealtime, turnID: firstTurnID))
    _ = coordinator.beginTurn()
    let secondTurnID = try XCTUnwrap(coordinator.snapshot().turnID)
    let currentLease = tryLease(coordinator.acquire(.selectedVoiceFallback, turnID: secondTurnID))

    if let staleLease {
      coordinator.release(staleLease)
    }

    XCTAssertEqual(coordinator.snapshot().activeLease, currentLease)
  }

  func testStaleTurnCannotAcquireLease() {
    var coordinator = PTTVoiceOutputCoordinator()
    let oldTurnID = coordinator.beginTurn()
    _ = coordinator.beginTurn()

    XCTAssertEqual(coordinator.acquire(.nativeRealtime, turnID: oldTurnID), .staleTurn)
  }

  private func tryLease(_ decision: PTTVoiceOutputDecision) -> PTTVoiceLease? {
    guard case .acquired(let lease) = decision else { return nil }
    return lease
  }
}
