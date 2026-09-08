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

  func testStartupRepairAttemptedOnlyOncePerInstalledVersion() {
    let defaults = UserDefaults(suiteName: "NotificationRegistrationRepairTests")!
    defaults.removePersistentDomain(forName: "NotificationRegistrationRepairTests")

    XCTAssertTrue(
      NotificationRegistrationRepair.shouldAttemptStartupRepair(
        defaults: defaults,
        versionIdentifier: "0.12.0+12000"
      )
    )

    NotificationRegistrationRepair.markStartupRepairAttempted(
      defaults: defaults,
      versionIdentifier: "0.12.0+12000"
    )

    XCTAssertFalse(
      NotificationRegistrationRepair.shouldAttemptStartupRepair(
        defaults: defaults,
        versionIdentifier: "0.12.0+12000"
      )
    )
    XCTAssertTrue(
      NotificationRegistrationRepair.shouldAttemptStartupRepair(
        defaults: defaults,
        versionIdentifier: "0.12.1+12001"
      )
    )
  }

  func testStartupRepairGuardIsIndependentOfVersionRepairGuard() {
    let defaults = UserDefaults(suiteName: "NotificationRegistrationRepairTests")!
    defaults.removePersistentDomain(forName: "NotificationRegistrationRepairTests")

    // Marking the startup attempt must not consume the version-repair guard, and vice versa.
    NotificationRegistrationRepair.markStartupRepairAttempted(
      defaults: defaults,
      versionIdentifier: "0.12.0+12000"
    )
    XCTAssertTrue(
      NotificationRegistrationRepair.shouldRepairForCurrentVersion(
        defaults: defaults,
        versionIdentifier: "0.12.0+12000"
      )
    )
  }
}
