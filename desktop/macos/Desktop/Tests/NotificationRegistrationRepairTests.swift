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
}
