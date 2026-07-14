import XCTest

@testable import Omi_Computer

final class PTTSilentMicRecoveryPolicyTests: XCTestCase {
  func testRepeatedDeadMicTurnsRequestRecovery() {
    var policy = PTTSilentMicRecoveryPolicy()

    XCTAssertFalse(policy.recordDiscardedTurn(totalSec: 1.0, peak: 0).shouldRebuildCapture)
    XCTAssertEqual(policy.consecutiveDeadMicTurns, 1)

    XCTAssertTrue(policy.recordDiscardedTurn(totalSec: 1.0, peak: 0).shouldRebuildCapture)
    XCTAssertEqual(policy.consecutiveDeadMicTurns, 0)
  }

  func testShortSilentTapDoesNotCountAsDeadMic() {
    var policy = PTTSilentMicRecoveryPolicy()

    XCTAssertFalse(policy.recordDiscardedTurn(totalSec: 0.05, peak: 0).shouldRebuildCapture)
    XCTAssertEqual(policy.consecutiveDeadMicTurns, 0)
  }

  func testQuietButNonZeroTurnResetsDeadMicCounter() {
    var policy = PTTSilentMicRecoveryPolicy()

    XCTAssertFalse(policy.recordDiscardedTurn(totalSec: 1.0, peak: 0).shouldRebuildCapture)
    XCTAssertFalse(
      policy.recordDiscardedTurn(
        totalSec: 1.0,
        peak: PTTSilentMicRecoveryPolicy.deadMicPeakThreshold + 1
      ).shouldRebuildCapture)
    XCTAssertEqual(policy.consecutiveDeadMicTurns, 0)
  }

  func testSuccessfulTurnResetsDeadMicCounter() {
    var policy = PTTSilentMicRecoveryPolicy()

    XCTAssertFalse(policy.recordDiscardedTurn(totalSec: 1.0, peak: 0).shouldRebuildCapture)
    XCTAssertNil(policy.recordSuccessfulTurn())

    XCTAssertEqual(policy.consecutiveDeadMicTurns, 0)
  }

  func testSuccessfulTurnPreventsNonConsecutiveDeadMicRecovery() {
    var policy = PTTSilentMicRecoveryPolicy()

    XCTAssertFalse(policy.recordDiscardedTurn(totalSec: 1.0, peak: 0).shouldRebuildCapture)
    XCTAssertNil(policy.recordSuccessfulTurn())

    XCTAssertFalse(policy.recordDiscardedTurn(totalSec: 1.0, peak: 0).shouldRebuildCapture)
    XCTAssertEqual(policy.consecutiveDeadMicTurns, 1)
  }

  /// A zero-frame turn is neutral: it must leave the prior judgeable dead-mic
  /// evidence intact so the existing capture rebuild can arm on the next turn.
  func testZeroFrameTurnBetweenNearZeroTurnsPreservesDeadMicEvidence() {
    var policy = PTTSilentMicRecoveryPolicy()

    XCTAssertFalse(policy.recordDiscardedTurn(totalSec: 1.0, peak: 0).shouldRebuildCapture)
    XCTAssertFalse(policy.recordDiscardedTurn(totalSec: 0, peak: 0).shouldRebuildCapture)
    XCTAssertEqual(policy.consecutiveDeadMicTurns, 1)

    XCTAssertTrue(policy.recordDiscardedTurn(totalSec: 1.0, peak: 0).shouldRebuildCapture)
  }

  func testThresholdRequestsExactlyOneCaptureRebuildUntilNextJudgeableTurn() {
    var policy = PTTSilentMicRecoveryPolicy()

    XCTAssertFalse(policy.recordDiscardedTurn(totalSec: 1.0, peak: 0).shouldRebuildCapture)
    XCTAssertTrue(policy.recordDiscardedTurn(totalSec: 1.0, peak: 0).shouldRebuildCapture)

    let nextTurn = policy.recordDiscardedTurn(totalSec: 1.0, peak: 0)
    XCTAssertEqual(nextTurn.recoveryOutcome, .failed)
    XCTAssertFalse(nextTurn.shouldRebuildCapture)
    XCTAssertEqual(policy.consecutiveDeadMicTurns, 1)
  }

  func testAudibleTurnAfterCaptureRebuildRecordsSuccessAndRearmsPolicy() {
    var policy = armedRecoveryPolicy()

    XCTAssertEqual(policy.recordSuccessfulTurn(), .succeeded)
    XCTAssertFalse(policy.recordDiscardedTurn(totalSec: 1.0, peak: 0).shouldRebuildCapture)
    XCTAssertTrue(policy.recordDiscardedTurn(totalSec: 1.0, peak: 0).shouldRebuildCapture)
  }

  func testNearZeroTurnAfterCaptureRebuildRecordsFailureWithoutSpinning() {
    var policy = armedRecoveryPolicy()

    let nextTurn = policy.recordDiscardedTurn(totalSec: 1.0, peak: 0)

    XCTAssertEqual(nextTurn.recoveryOutcome, .failed)
    XCTAssertFalse(nextTurn.shouldRebuildCapture)
    XCTAssertEqual(policy.consecutiveDeadMicTurns, 1)
  }

  func testCaptureRebuildResetsCounterWithoutArmingOutcome() {
    var policy = PTTSilentMicRecoveryPolicy()

    XCTAssertFalse(policy.recordDiscardedTurn(totalSec: 1.0, peak: 0).shouldRebuildCapture)
    policy.recordCaptureRebuild()

    XCTAssertEqual(policy.consecutiveDeadMicTurns, 0)
    // Bluetooth silent-mic fallback calls recordCaptureRebuild for counter reset
    // only; it must not arm capture_rebuild outcome tracking.
    XCTAssertNil(policy.recordSuccessfulTurn())
  }

  private func armedRecoveryPolicy() -> PTTSilentMicRecoveryPolicy {
    var policy = PTTSilentMicRecoveryPolicy()
    XCTAssertFalse(policy.recordDiscardedTurn(totalSec: 1.0, peak: 0).shouldRebuildCapture)
    XCTAssertTrue(policy.recordDiscardedTurn(totalSec: 1.0, peak: 0).shouldRebuildCapture)
    return policy
  }
}
