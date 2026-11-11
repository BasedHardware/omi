import XCTest

@testable import Omi_Computer

/// The restoring phase's one guaranteed escape. The launch attempt being
/// superseded — by the restore flow's own invalidation branches or by any newer
/// auth flow — must not defuse the watchdog, because every fenced exit in the
/// restore is silent and nothing else resolves the phase.
@MainActor
final class AuthRestoreWatchdogTests: XCTestCase {

  func testRestoringPhaseResolvesEvenWhenTheLaunchAttemptWasSuperseded() {
    let auth = AuthService.shared
    let launchAttempt = auth.beginSessionAttempt()
    AuthState.shared.transition(to: .restoring)
    // Whatever raced at launch supersedes the launch attempt. With the
    // attempt-gated watchdog this left `.restoring` stuck for the whole
    // session: the fenced restore exits silently and the watchdog returned
    // without resolving anything.
    let superseding = auth.beginSessionAttempt()
    XCTAssertNotEqual(launchAttempt, superseding)
    XCTAssertFalse(
      auth.isSessionAttemptCurrent(launchAttempt),
      "precondition: the launch attempt no longer owns the session")

    // omi-test-quality: wall-clock-wait -- the watchdog is a real main-queue
    // asyncAfter; the seam exposes an injectable timeout instead of a clock.
    auth.armRestoringPhaseWatchdog(attempt: launchAttempt, timeout: 0.2)

    let deadline = Date().addingTimeInterval(3)
    while Date() < deadline, AuthState.shared.isRestoringAuth {
      RunLoop.main.run(until: Date().addingTimeInterval(0.02))
    }

    XCTAssertFalse(
      AuthState.shared.isRestoringAuth,
      "a superseded launch attempt must not leave the restoring phase stuck")
    XCTAssertEqual(
      AuthState.shared.sessionPhase, .recoveryRequired,
      "the watchdog lands in the same recoverable state the ungated case always did")
    AuthState.shared.transition(to: .signedOut)
  }

  func testTheWatchdogLeavesARestoringPhaseAloneWhileASignInOwnsTheUI() {
    let auth = AuthService.shared
    let launchAttempt = auth.beginSessionAttempt()
    AuthState.shared.transition(to: .restoring)
    AuthState.shared.isLoading = true

    auth.armRestoringPhaseWatchdog(attempt: launchAttempt, timeout: 0.2)

    let deadline = Date().addingTimeInterval(0.6)
    while Date() < deadline {
      RunLoop.main.run(until: Date().addingTimeInterval(0.02))
      guard AuthState.shared.isRestoringAuth else {
        XCTFail("a running sign-in (isLoading) must not be flipped by the watchdog")
        break
      }
    }
    XCTAssertTrue(
      AuthState.shared.isRestoringAuth,
      "a user-driven sign-in defers the watchdog via isLoading")

    AuthState.shared.isLoading = false
    AuthState.shared.transition(to: .signedOut)
  }
}
