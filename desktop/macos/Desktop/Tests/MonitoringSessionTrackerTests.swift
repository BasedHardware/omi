import XCTest

@testable import Omi_Computer

/// Pure logic tests for `MonitoringSessionTracker` / `MonitoringSessionRecovery` —
/// no singletons, no timers, no PostHog. Every scenario is driven by explicit
/// `Date` values so behavior is deterministic.
final class MonitoringSessionTrackerTests: XCTestCase {
  private let epoch = Date(timeIntervalSinceReferenceDate: 0)

  private func date(_ offsetSeconds: Double) -> Date {
    epoch.addingTimeInterval(offsetSeconds)
  }

  func testSimpleStartStopDuration() {
    var tracker = MonitoringSessionTracker()
    tracker.start(at: date(0), sessionID: "session-1")

    let summary = tracker.finish(at: date(600), reason: .userToggle)

    XCTAssertEqual(summary.sessionID, "session-1")
    XCTAssertEqual(summary.durationSeconds, 600)
    XCTAssertEqual(summary.pausedSeconds, 0)
    XCTAssertEqual(summary.activeSeconds, 600)
    XCTAssertEqual(summary.stopReason, .userToggle)
    XCTAssertEqual(summary.durationSource, .wallClock)
  }

  func testPauseResumeSubtractsFromActiveDuration() {
    var tracker = MonitoringSessionTracker()
    tracker.start(at: date(0), sessionID: "session-2")

    tracker.pause(at: date(100))
    tracker.resume(at: date(160))  // 60s paused

    let summary = tracker.finish(at: date(300), reason: .userToggle)

    XCTAssertEqual(summary.durationSeconds, 300)
    XCTAssertEqual(summary.pausedSeconds, 60)
    XCTAssertEqual(summary.activeSeconds, 240)
  }

  /// Screen lock and system sleep are independent interruption sources that
  /// can overlap in real usage — lock, then sleep, then wake, then unlock —
  /// and must still collapse into exactly one paused interval, not two. Since
  /// `pause`/`resume` carry no source identity, the interval closes at the
  /// first `resume` call (here, wake); the later, redundant `resume` (unlock)
  /// is a no-op rather than opening/closing a second interval.
  func testOverlappingPausesCountOnce() {
    var tracker = MonitoringSessionTracker()
    tracker.start(at: date(0), sessionID: "session-3")

    tracker.pause(at: date(50))  // screen lock begins
    tracker.pause(at: date(55))  // system sleep begins — already paused, no-op
    tracker.resume(at: date(80))  // system wakes — closes the interval: 50 -> 80 = 30s
    tracker.resume(at: date(90))  // screen unlocks — already resumed, no-op

    let summary = tracker.finish(at: date(200), reason: .userToggle)

    XCTAssertEqual(summary.pausedSeconds, 30)
    XCTAssertEqual(summary.activeSeconds, 170)
  }

  func testPauseWhileAlreadyPausedIsANoOp() {
    var tracker = MonitoringSessionTracker()
    tracker.start(at: date(0), sessionID: "session-4")

    tracker.pause(at: date(10))
    tracker.pause(at: date(20))  // no-op: must not reset the interval start
    tracker.resume(at: date(30))

    let summary = tracker.finish(at: date(100), reason: .userToggle)

    XCTAssertEqual(summary.pausedSeconds, 20)  // 10 -> 30, not 20 -> 30
  }

  func testResumeWhileNotPausedIsANoOp() {
    var tracker = MonitoringSessionTracker()
    tracker.start(at: date(0), sessionID: "session-5")

    tracker.resume(at: date(10))  // no-op, never paused

    let summary = tracker.finish(at: date(100), reason: .userToggle)

    XCTAssertEqual(summary.pausedSeconds, 0)
    XCTAssertEqual(summary.activeSeconds, 100)
  }

  func testFinishWhilePausedClosesTheOpenInterval() {
    var tracker = MonitoringSessionTracker()
    tracker.start(at: date(0), sessionID: "session-6")

    tracker.pause(at: date(80))
    let summary = tracker.finish(at: date(100), reason: .userToggle)  // never resumed

    XCTAssertEqual(summary.pausedSeconds, 20)
    XCTAssertEqual(summary.activeSeconds, 80)
  }

  func testBackwardsClockClampsToZeroAndFlagsAnomaly() {
    var tracker = MonitoringSessionTracker()
    tracker.start(at: date(1000), sessionID: "session-7")

    let summary = tracker.finish(at: date(500), reason: .userToggle)  // clock moved backwards

    XCTAssertEqual(summary.durationSeconds, 0)
    XCTAssertEqual(summary.activeSeconds, 0)
    XCTAssertEqual(summary.durationSource, .clockAnomaly)
  }

  func testStopReasonIsCarriedThroughToTheSummary() {
    var tracker = MonitoringSessionTracker()
    tracker.start(at: date(0), sessionID: "session-8")

    let summary = tracker.finish(at: date(10), reason: .permissionRevoked)

    XCTAssertEqual(summary.stopReason, .permissionRevoked)
  }

  // MARK: - Recovery

  func testRecoveryWithEndedAtIsRecoveredClean() {
    let record = MonitoringSessionRecord(
      sessionID: "session-9",
      startedAt: date(0),
      lastHeartbeatAt: date(590),
      pausedSeconds: 30,
      endedAt: date(600),
      endReason: MonitoringStopReason.appQuit.rawValue
    )

    let outcome = MonitoringSessionRecovery.recover(record, now: date(700))

    XCTAssertEqual(outcome.sessionID, "session-9")
    XCTAssertEqual(outcome.durationSeconds, 600)
    XCTAssertEqual(outcome.pausedSeconds, 30)
    XCTAssertEqual(outcome.activeSeconds, 570)
    XCTAssertEqual(outcome.stopReason, .appQuit)
    XCTAssertEqual(outcome.durationSource, .recoveredClean)
    XCTAssertEqual(outcome.recoveredAfterSeconds, 110)  // 700 - 590
  }

  func testRecoveryWithoutEndedAtIsRecoveredHeartbeat() {
    let record = MonitoringSessionRecord(
      sessionID: "session-10",
      startedAt: date(0),
      lastHeartbeatAt: date(240),
      pausedSeconds: 0,
      endedAt: nil,
      endReason: nil
    )

    let outcome = MonitoringSessionRecovery.recover(record, now: date(1000))

    XCTAssertEqual(outcome.durationSeconds, 240)
    XCTAssertEqual(outcome.activeSeconds, 240)
    XCTAssertEqual(outcome.stopReason, .sessionLost)
    XCTAssertEqual(outcome.durationSource, .recoveredHeartbeat)
    XCTAssertEqual(outcome.recoveredAfterSeconds, 760)  // 1000 - 240
  }
}
