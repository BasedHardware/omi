import XCTest

@testable import Omi_Computer

final class PTTSilentMicRecoveryPolicyTests: XCTestCase {
  /// The 0→1 case: the first press of a session that comes back dead gets its
  /// capture rebuilt straight away. Waiting for a second dead turn assumes the
  /// user will press again — on a fresh install they were just told "Hold longer
  /// to record", and mostly they do not.
  func testFirstDeadTurnOfSessionRequestsRecoveryWithoutASecond() {
    var policy = PTTSilentMicRecoveryPolicy()

    XCTAssertTrue(
      policy.recordDiscardedTurn(holdSec: 1.0, totalSec: 1.0, peak: 0).shouldRebuildCapture)
    XCTAssertEqual(policy.consecutiveDeadMicTurns, 0)
  }

  /// A press that delivered no audio at all reports zero seconds. Judging on the
  /// press instead of on delivered audio is what makes `capture_never_operational`
  /// — the largest new-user failure class — reachable by recovery at all.
  func testDeadTurnIsJudgedOnTheHoldNotOnDeliveredAudio() {
    var policy = PTTSilentMicRecoveryPolicy()

    XCTAssertTrue(
      policy.recordDiscardedTurn(holdSec: 0.52, totalSec: 0, peak: 0).shouldRebuildCapture)
  }

  /// Once a rebuild has been issued, the ordinary two-turn threshold applies
  /// again so a genuinely broken microphone cannot spin on every press.
  func testAfterFirstRecoveryTheTwoTurnThresholdApplies() {
    var policy = PTTSilentMicRecoveryPolicy()

    XCTAssertTrue(
      policy.recordDiscardedTurn(holdSec: 1.0, totalSec: 1.0, peak: 0).shouldRebuildCapture)
    XCTAssertFalse(
      policy.recordDiscardedTurn(holdSec: 1.0, totalSec: 1.0, peak: 0).shouldRebuildCapture)
    XCTAssertEqual(policy.consecutiveDeadMicTurns, 1)
    XCTAssertTrue(
      policy.recordDiscardedTurn(holdSec: 1.0, totalSec: 1.0, peak: 0).shouldRebuildCapture)
  }

  func testShortSilentTapDoesNotCountAsDeadMic() {
    var policy = PTTSilentMicRecoveryPolicy()

    XCTAssertFalse(
      policy.recordDiscardedTurn(holdSec: 0.05, totalSec: 0.05, peak: 0).shouldRebuildCapture)
    XCTAssertEqual(policy.consecutiveDeadMicTurns, 0)
  }

  /// The observed fresh-install sequence was dead → audible → audible → dead, and
  /// the audible-but-still-discarded turns in the middle wiped the streak so the
  /// rebuild never armed. An audible turn proves the microphone is alive; it does
  /// not prove capture is healthy for a whole turn, and only a committed turn
  /// (`recordSuccessfulTurn`) does.
  func testAudibleDiscardedTurnBetweenDeadTurnsDoesNotResetTheStreak() {
    var policy = armedRecoveryPolicy()

    XCTAssertFalse(
      policy.recordDiscardedTurn(holdSec: 1.0, totalSec: 1.0, peak: 0).shouldRebuildCapture)
    XCTAssertEqual(policy.consecutiveDeadMicTurns, 1)

    XCTAssertFalse(
      policy.recordDiscardedTurn(
        holdSec: 1.0,
        totalSec: 1.0,
        peak: PTTSilentMicRecoveryPolicy.deadMicPeakThreshold + 1
      ).shouldRebuildCapture)
    XCTAssertEqual(policy.consecutiveDeadMicTurns, 1)

    XCTAssertTrue(
      policy.recordDiscardedTurn(holdSec: 1.0, totalSec: 1.0, peak: 0).shouldRebuildCapture)
  }

  func testCommittedTurnResetsDeadMicCounter() {
    var policy = armedRecoveryPolicy()

    XCTAssertFalse(
      policy.recordDiscardedTurn(holdSec: 1.0, totalSec: 1.0, peak: 0).shouldRebuildCapture)
    XCTAssertNil(policy.recordSuccessfulTurn())

    XCTAssertEqual(policy.consecutiveDeadMicTurns, 0)
  }

  func testCommittedTurnPreventsNonConsecutiveDeadMicRecovery() {
    var policy = armedRecoveryPolicy()

    XCTAssertFalse(
      policy.recordDiscardedTurn(holdSec: 1.0, totalSec: 1.0, peak: 0).shouldRebuildCapture)
    XCTAssertNil(policy.recordSuccessfulTurn())

    XCTAssertFalse(
      policy.recordDiscardedTurn(holdSec: 1.0, totalSec: 1.0, peak: 0).shouldRebuildCapture)
    XCTAssertEqual(policy.consecutiveDeadMicTurns, 1)
  }

  /// A press too short to judge is neutral: it must leave the prior judgeable
  /// dead-mic evidence intact rather than erasing or resolving it.
  func testUnjudgeablePressBetweenDeadTurnsPreservesDeadMicEvidence() {
    var policy = armedRecoveryPolicy()

    XCTAssertFalse(
      policy.recordDiscardedTurn(holdSec: 1.0, totalSec: 1.0, peak: 0).shouldRebuildCapture)
    XCTAssertFalse(
      policy.recordDiscardedTurn(holdSec: 0, totalSec: 0, peak: 0).shouldRebuildCapture)
    XCTAssertEqual(policy.consecutiveDeadMicTurns, 1)

    XCTAssertTrue(
      policy.recordDiscardedTurn(holdSec: 1.0, totalSec: 1.0, peak: 0).shouldRebuildCapture)
  }

  func testThresholdRequestsExactlyOneCaptureRebuildUntilNextJudgeableTurn() {
    var policy = armedRecoveryPolicy()

    XCTAssertFalse(
      policy.recordDiscardedTurn(holdSec: 1.0, totalSec: 1.0, peak: 0).shouldRebuildCapture)
    XCTAssertTrue(
      policy.recordDiscardedTurn(holdSec: 1.0, totalSec: 1.0, peak: 0).shouldRebuildCapture)

    let nextTurn = policy.recordDiscardedTurn(holdSec: 1.0, totalSec: 1.0, peak: 0)
    XCTAssertEqual(nextTurn.recoveryOutcome, .failed)
    XCTAssertFalse(nextTurn.shouldRebuildCapture)
    XCTAssertEqual(policy.consecutiveDeadMicTurns, 1)
  }

  func testAudibleTurnAfterCaptureRebuildRecordsSuccessAndRearmsPolicy() {
    var policy = policyAwaitingRecoveryOutcome()

    XCTAssertEqual(
      policy.recordDiscardedTurn(
        holdSec: 1.0,
        totalSec: 1.0,
        peak: PTTSilentMicRecoveryPolicy.deadMicPeakThreshold + 1
      ).recoveryOutcome,
      .succeeded)
    // The rebuild is spent, so the ordinary two-turn threshold governs from here.
    XCTAssertFalse(
      policy.recordDiscardedTurn(holdSec: 1.0, totalSec: 1.0, peak: 0).shouldRebuildCapture)
    XCTAssertTrue(
      policy.recordDiscardedTurn(holdSec: 1.0, totalSec: 1.0, peak: 0).shouldRebuildCapture)
  }

  func testNearZeroTurnAfterCaptureRebuildRecordsFailureWithoutSpinning() {
    var policy = policyAwaitingRecoveryOutcome()

    let nextTurn = policy.recordDiscardedTurn(holdSec: 1.0, totalSec: 1.0, peak: 0)

    XCTAssertEqual(nextTurn.recoveryOutcome, .failed)
    XCTAssertFalse(nextTurn.shouldRebuildCapture)
    XCTAssertEqual(policy.consecutiveDeadMicTurns, 1)
  }

  func testCaptureRebuildResetsCounterWithoutArmingOutcome() {
    var policy = armedRecoveryPolicy()

    XCTAssertFalse(
      policy.recordDiscardedTurn(holdSec: 1.0, totalSec: 1.0, peak: 0).shouldRebuildCapture)
    XCTAssertEqual(policy.consecutiveDeadMicTurns, 1)
    policy.recordCaptureRebuild()

    XCTAssertEqual(policy.consecutiveDeadMicTurns, 0)
    // Bluetooth silent-mic fallback calls recordCaptureRebuild for counter reset
    // only; it must not arm capture_rebuild outcome tracking.
    XCTAssertNil(policy.recordSuccessfulTurn())
  }

  func testCoreAudioCaptureRebuildArmsOutcomeForNextJudgeableTurn() {
    var policy = PTTSilentMicRecoveryPolicy()

    policy.armCaptureRebuildOutcome()

    XCTAssertEqual(policy.consecutiveDeadMicTurns, 0)
    XCTAssertEqual(policy.recordSuccessfulTurn(), .succeeded)
    XCTAssertNil(policy.recordSuccessfulTurn())
  }

  /// An explicit rebuild counts as this session's first recovery, so the next
  /// dead turn does not get the one-turn threshold a second time.
  func testCoreAudioCaptureRebuildFailureIsRecordedWithoutImmediateRearm() {
    var policy = PTTSilentMicRecoveryPolicy()

    policy.armCaptureRebuildOutcome()
    let nextTurn = policy.recordDiscardedTurn(holdSec: 1.0, totalSec: 1.0, peak: 0)

    XCTAssertEqual(nextTurn.recoveryOutcome, .failed)
    XCTAssertFalse(nextTurn.shouldRebuildCapture)
    XCTAssertEqual(policy.consecutiveDeadMicTurns, 1)
  }

  /// A policy that has already spent its one first-of-session rebuild, so the
  /// two-turn threshold governs everything after it.
  /// A policy whose first-of-session rebuild has been issued and is still
  /// waiting for the next judgeable turn to say whether it worked.
  private func policyAwaitingRecoveryOutcome() -> PTTSilentMicRecoveryPolicy {
    var policy = PTTSilentMicRecoveryPolicy()
    XCTAssertTrue(
      policy.recordDiscardedTurn(holdSec: 1.0, totalSec: 1.0, peak: 0).shouldRebuildCapture)
    return policy
  }

  private func armedRecoveryPolicy() -> PTTSilentMicRecoveryPolicy {
    var policy = PTTSilentMicRecoveryPolicy()
    XCTAssertTrue(
      policy.recordDiscardedTurn(holdSec: 1.0, totalSec: 1.0, peak: 0).shouldRebuildCapture)
    XCTAssertEqual(policy.recordSuccessfulTurn(), .succeeded)
    return policy
  }
}
