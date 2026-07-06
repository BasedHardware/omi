import XCTest

@testable import Omi_Computer

final class NotificationRegistrationRepairTests: XCTestCase {
  func testVersionRepairRunsOnlyOncePerInstalledVersion() {
    let defaults = UserDefaults(suiteName: "NotificationRegistrationRepairTests")!
    defaults.removePersistentDomain(forName: "NotificationRegistrationRepairTests")

    XCTAssertTrue(
      NotificationRegistrationRepair.shouldRepairForCurrentVersion(
        defaults: defaults,
        versionIdentifier: "0.12.0+12000"
      )
    )

    NotificationRegistrationRepair.markRepairedForCurrentVersion(
      defaults: defaults,
      versionIdentifier: "0.12.0+12000"
    )

    XCTAssertFalse(
      NotificationRegistrationRepair.shouldRepairForCurrentVersion(
        defaults: defaults,
        versionIdentifier: "0.12.0+12000"
      )
    )
    XCTAssertTrue(
      NotificationRegistrationRepair.shouldRepairForCurrentVersion(
        defaults: defaults,
        versionIdentifier: "0.12.1+12001"
      )
    )
  }

  // Regression for #9082: the automatic startup notification-authorization request
  // must run at most once per installed version so a user stuck at .notDetermined
  // does not re-trigger the LaunchServices repair loop on every launch/wake.
  func testStartupAuthorizationAttemptedOnlyOncePerInstalledVersion() {
    let suite = "NotificationRegistrationRepairTests.startupAuth"
    let defaults = UserDefaults(suiteName: suite)!
    defaults.removePersistentDomain(forName: suite)

    XCTAssertTrue(
      NotificationRegistrationRepair.shouldAttemptStartupAuthorizationForCurrentVersion(
        defaults: defaults,
        versionIdentifier: "0.12.0+12000"
      )
    )

    NotificationRegistrationRepair.markStartupAuthorizationAttemptedForCurrentVersion(
      defaults: defaults,
      versionIdentifier: "0.12.0+12000"
    )

    // Same version (re-activation / wake / relaunch) must not re-attempt.
    XCTAssertFalse(
      NotificationRegistrationRepair.shouldAttemptStartupAuthorizationForCurrentVersion(
        defaults: defaults,
        versionIdentifier: "0.12.0+12000"
      )
    )
    // A new version resets the one-shot attempt.
    XCTAssertTrue(
      NotificationRegistrationRepair.shouldAttemptStartupAuthorizationForCurrentVersion(
        defaults: defaults,
        versionIdentifier: "0.12.1+12001"
      )
    )
  }
}
