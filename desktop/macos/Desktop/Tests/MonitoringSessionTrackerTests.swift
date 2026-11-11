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

    tracker.pause(at: date(100), source: .screenLock)
    tracker.resume(at: date(160), source: .screenLock)  // 60s paused

    let summary = tracker.finish(at: date(300), reason: .userToggle)

    XCTAssertEqual(summary.durationSeconds, 300)
    XCTAssertEqual(summary.pausedSeconds, 60)
    XCTAssertEqual(summary.activeSeconds, 240)
  }

  /// The standard password-after-sleep laptop path: lock, sleep, wake to a
  /// still-locked screen, then unlock. `handleSystemWake` releases only the
  /// sleep hold, and capture genuinely stays down until unlock — so the single
  /// paused interval must run from lock all the way to unlock.
  ///
  /// A first-resume-wins model closes at wake instead and bills every second
  /// of the lock screen after wake as *active* monitoring, which is the number
  /// this whole contract exists to measure.
  func testWakingToALockedScreenKeepsTheSessionPaused() {
    var tracker = MonitoringSessionTracker()
    tracker.start(at: date(0), sessionID: "session-3")

    tracker.pause(at: date(100), source: .screenLock)  // user locks
    tracker.pause(at: date(110), source: .systemSleep)  // machine sleeps
    tracker.resume(at: date(200), source: .systemSleep)  // wakes, still locked
    XCTAssertTrue(tracker.isPaused, "the screen-lock hold must survive the wake")
    tracker.resume(at: date(500), source: .screenLock)  // user unlocks

    let summary = tracker.finish(at: date(600), reason: .userToggle)

    XCTAssertEqual(summary.pausedSeconds, 400)  // 100 -> 500, one interval
    XCTAssertEqual(summary.activeSeconds, 200)  // 0 -> 100 and 500 -> 600
  }

  /// The reverse ordering (sleep first, unlock last) must produce exactly one
  /// interval too — never two, and never a double-counted overlap.
  func testOverlappingSourcesProduceExactlyOneInterval() {
    var tracker = MonitoringSessionTracker()
    tracker.start(at: date(0), sessionID: "session-4")

    tracker.pause(at: date(50), source: .systemSleep)
    tracker.pause(at: date(55), source: .screenLock)
    tracker.resume(at: date(80), source: .screenLock)
    XCTAssertTrue(tracker.isPaused, "the sleep hold is still outstanding")
    tracker.resume(at: date(90), source: .systemSleep)

    let summary = tracker.finish(at: date(200), reason: .userToggle)

    XCTAssertEqual(summary.pausedSeconds, 40)  // 50 -> 90
    XCTAssertEqual(summary.activeSeconds, 160)
  }

  func testDuplicatePauseFromTheSameSourceDoesNotMoveTheIntervalStart() {
    var tracker = MonitoringSessionTracker()
    tracker.start(at: date(0), sessionID: "session-5")

    tracker.pause(at: date(10), source: .screenLock)
    tracker.pause(at: date(20), source: .screenLock)  // redundant notification
    tracker.resume(at: date(30), source: .screenLock)

    let summary = tracker.finish(at: date(100), reason: .userToggle)

    XCTAssertEqual(summary.pausedSeconds, 20)  // 10 -> 30, not 20 -> 30
  }

  /// A spurious resume for a source that never paused must not close another
  /// source's interval — otherwise one stray notification reintroduces exactly
  /// the wake-while-locked bug.
  func testResumeFromASourceThatNeverPausedIsANoOp() {
    var tracker = MonitoringSessionTracker()
    tracker.start(at: date(0), sessionID: "session-6")

    tracker.pause(at: date(10), source: .screenLock)
    tracker.resume(at: date(40), source: .systemSleep)  // never slept
    XCTAssertTrue(tracker.isPaused)
    tracker.resume(at: date(60), source: .screenLock)

    let summary = tracker.finish(at: date(100), reason: .userToggle)

    XCTAssertEqual(summary.pausedSeconds, 50)  // 10 -> 60
  }

  func testResumeWhileNotPausedIsANoOp() {
    var tracker = MonitoringSessionTracker()
    tracker.start(at: date(0), sessionID: "session-7")

    tracker.resume(at: date(10), source: .screenLock)  // no-op, never paused

    let summary = tracker.finish(at: date(100), reason: .userToggle)

    XCTAssertEqual(summary.pausedSeconds, 0)
    XCTAssertEqual(summary.activeSeconds, 100)
  }

  func testFinishWhilePausedClosesTheOpenInterval() {
    var tracker = MonitoringSessionTracker()
    tracker.start(at: date(0), sessionID: "session-8")

    tracker.pause(at: date(80), source: .screenLock)
    let summary = tracker.finish(at: date(100), reason: .userToggle)  // never resumed

    XCTAssertEqual(summary.pausedSeconds, 20)
    XCTAssertEqual(summary.activeSeconds, 80)
  }

  func testBackwardsClockClampsToZeroAndFlagsAnomaly() {
    var tracker = MonitoringSessionTracker()
    tracker.start(at: date(1000), sessionID: "session-9")

    let summary = tracker.finish(at: date(500), reason: .userToggle)  // clock moved backwards

    XCTAssertEqual(summary.durationSeconds, 0)
    XCTAssertEqual(summary.activeSeconds, 0)
    XCTAssertEqual(summary.durationSource, .clockAnomaly)
  }

  func testStopReasonIsCarriedThroughToTheSummary() {
    var tracker = MonitoringSessionTracker()
    tracker.start(at: date(0), sessionID: "session-10")

    let summary = tracker.finish(at: date(10), reason: .permissionRevoked)

    XCTAssertEqual(summary.stopReason, .permissionRevoked)
  }

  // MARK: - Liveness after a live stop

  /// The session must be dead the instant it emits its live `Monitoring
  /// Stopped`. Every persist/stamp path in `ProactiveAssistantsPlugin` is
  /// guarded on `hasActiveSession`, so if a finished session still looked
  /// live, the next lock or sleep would re-persist it *after* the store was
  /// cleared and the following launch would recover it as a second stop.
  func testSessionIsNotActiveAfterFinishing() {
    var tracker = MonitoringSessionTracker()
    tracker.start(at: date(0), sessionID: "session-11")
    XCTAssertTrue(tracker.hasActiveSession)

    tracker.finish(at: date(100), reason: .userToggle)

    XCTAssertFalse(tracker.hasActiveSession)
  }

  func testPauseHeartbeatAndResumeAreNoOpsAfterFinishing() {
    var tracker = MonitoringSessionTracker()
    tracker.start(at: date(0), sessionID: "session-12")
    tracker.finish(at: date(100), reason: .userToggle)
    let afterStop = tracker.record

    tracker.pause(at: date(200), source: .screenLock)
    tracker.heartbeat(at: date(260))
    tracker.resume(at: date(300), source: .screenLock)

    XCTAssertEqual(tracker.record, afterStop, "a finished session must be immutable")
    XCTAssertFalse(tracker.isPaused)
  }

  /// Quitting hours after a live stop must not rewrite that session into a
  /// clean quit for the next launch to recover.
  func testQuitStampIsRefusedForAnAlreadyFinishedSession() {
    var tracker = MonitoringSessionTracker()
    tracker.start(at: date(0), sessionID: "session-13")
    tracker.finish(at: date(100), reason: .userToggle)

    XCTAssertNil(tracker.quitStampedRecord(at: date(30_000)))
  }

  func testQuitStampClosesAnOpenPausedInterval() {
    var tracker = MonitoringSessionTracker()
    tracker.start(at: date(0), sessionID: "session-14")
    tracker.pause(at: date(100), source: .screenLock)

    let stamped = tracker.quitStampedRecord(at: date(400))

    XCTAssertEqual(stamped?.pausedSeconds, 300)
    XCTAssertNil(stamped?.pauseStartedAt)
    XCTAssertEqual(stamped?.endedAt, date(400))
    XCTAssertEqual(stamped?.endReason, MonitoringStopReason.appQuit.rawValue)
  }

  func testQuitStampDoesNotMutateTheLiveSession() {
    var tracker = MonitoringSessionTracker()
    tracker.start(at: date(0), sessionID: "session-15")
    tracker.pause(at: date(100), source: .screenLock)

    _ = tracker.quitStampedRecord(at: date(400))

    XCTAssertTrue(tracker.hasActiveSession, "stamping is a snapshot, not a finish")
    XCTAssertEqual(tracker.record.pausedSeconds, 0)
    XCTAssertEqual(tracker.record.pauseStartedAt, date(100))
  }

  // MARK: - Holds outstanding at start

  /// Monitoring can begin while the screen is already locked — capture intent
  /// restored at launch, a settings sync, a permission retry. A session that
  /// starts unpaused there bills lock-screen time as active, and the matching
  /// unlock arrives with no hold to release.
  func testASessionStartedWhileLockedBeginsPaused() {
    var tracker = MonitoringSessionTracker()
    tracker.start(at: date(0), sessionID: "session-20", heldBy: [.screenLock])
    XCTAssertTrue(tracker.isPaused)

    tracker.resume(at: date(300), source: .screenLock)
    let summary = tracker.finish(at: date(400), reason: .userToggle)

    XCTAssertEqual(summary.pausedSeconds, 300)
    XCTAssertEqual(summary.activeSeconds, 100)
  }

  func testStartingAgainClearsHoldsFromThePreviousSession() {
    var tracker = MonitoringSessionTracker()
    tracker.start(at: date(0), sessionID: "session-21", heldBy: [.screenLock, .systemSleep])
    tracker.finish(at: date(50), reason: .userToggle)

    tracker.start(at: date(100), sessionID: "session-22")

    XCTAssertFalse(tracker.isPaused)
    XCTAssertNil(tracker.record.pauseStartedAt)
  }

  /// The backstop for a wake notification that never arrives. The pause comes
  /// straight off `NSWorkspace.willSleepNotification` while the resume rides an
  /// `AppState` rebroadcast, so a dropped hop must not strand the clock — a
  /// machine cannot be unlocked while asleep, which is what makes releasing the
  /// stale sleep hold on unlock sound.
  func testUnlockCanReleaseAStaleSleepHold() {
    var tracker = MonitoringSessionTracker()
    tracker.start(at: date(0), sessionID: "session-23")

    tracker.pause(at: date(100), source: .screenLock)
    tracker.pause(at: date(110), source: .systemSleep)
    // No wake arrives. Unlock releases both, as `handleScreenUnlock` does.
    tracker.resume(at: date(500), source: .screenLock)
    tracker.resume(at: date(500), source: .systemSleep)

    XCTAssertFalse(tracker.isPaused, "a missed wake must not strand the session paused")
    let summary = tracker.finish(at: date(600), reason: .userToggle)
    XCTAssertEqual(summary.pausedSeconds, 400)
    XCTAssertEqual(summary.activeSeconds, 200)
  }

  // MARK: - Recovery

  func testRecoveryWithEndedAtIsRecoveredClean() {
    let record = MonitoringSessionRecord(
      sessionID: "session-16",
      startedAt: date(0),
      lastHeartbeatAt: date(590),
      pausedSeconds: 30,
      pauseStartedAt: nil,
      endedAt: date(600),
      endReason: MonitoringStopReason.appQuit.rawValue
    )

    let outcome = MonitoringSessionRecovery.recover(record, now: date(700))

    XCTAssertEqual(outcome.sessionID, "session-16")
    XCTAssertEqual(outcome.durationSeconds, 600)
    XCTAssertEqual(outcome.pausedSeconds, 30)
    XCTAssertEqual(outcome.activeSeconds, 570)
    XCTAssertEqual(outcome.stopReason, .appQuit)
    XCTAssertEqual(outcome.durationSource, .recoveredClean)
    XCTAssertEqual(outcome.recoveredAfterSeconds, 110)  // 700 - 590
  }

  func testRecoveryWithoutEndedAtIsRecoveredHeartbeat() {
    let record = MonitoringSessionRecord(
      sessionID: "session-17",
      startedAt: date(0),
      lastHeartbeatAt: date(240),
      pausedSeconds: 0,
      pauseStartedAt: nil,
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

  /// A crash while the screen was locked: the heartbeat kept running (the
  /// machine was awake), so the record ends well after the pause opened. That
  /// open interval has to be closed at the effective end, or every locked
  /// minute before the crash is reported as active monitoring.
  func testRecoveryClosesAPausedIntervalLeftOpenByACrash() {
    let record = MonitoringSessionRecord(
      sessionID: "session-18",
      startedAt: date(0),
      lastHeartbeatAt: date(900),
      pausedSeconds: 0,
      pauseStartedAt: date(300),
      endedAt: nil,
      endReason: nil
    )

    let outcome = MonitoringSessionRecovery.recover(record, now: date(1200))

    XCTAssertEqual(outcome.durationSeconds, 900)
    XCTAssertEqual(outcome.pausedSeconds, 600)  // 300 -> 900
    XCTAssertEqual(outcome.activeSeconds, 300)
  }

  func testRecoveryClosesAnOpenPauseAtACleanQuitTime() {
    let record = MonitoringSessionRecord(
      sessionID: "session-19",
      startedAt: date(0),
      lastHeartbeatAt: date(400),
      pausedSeconds: 10,
      pauseStartedAt: date(200),
      endedAt: date(500),
      endReason: MonitoringStopReason.appQuit.rawValue
    )

    let outcome = MonitoringSessionRecovery.recover(record, now: date(600))

    XCTAssertEqual(outcome.durationSeconds, 500)
    XCTAssertEqual(outcome.pausedSeconds, 310)  // 10 closed + (200 -> 500)
    XCTAssertEqual(outcome.activeSeconds, 190)
  }
}
