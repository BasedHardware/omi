import XCTest

@testable import Omi_Computer

final class StartupSystemMaintenancePolicyTests: XCTestCase {
  func testStartupMaintenanceIsRestrictedToTheAppBundle() {
    let bundlePath = "/Applications/omi.app"

    let commands = StartupSystemMaintenancePolicy.commands(bundlePath: bundlePath)

    XCTAssertEqual(
      commands,
      [
        StartupSystemMaintenanceCommand(
          label: "AppDelegate: strip provenance xattrs",
          executable: "/usr/bin/xattr",
          arguments: ["-cr", bundlePath]
        )
      ]
    )
  }

  func testStartupMaintenanceNeverRestartsSharedMacOSServices() {
    let commands = StartupSystemMaintenancePolicy.commands(bundlePath: "/Applications/omi.app")

    XCTAssertFalse(commands.contains { $0.executable == "/usr/bin/killall" })
    XCTAssertFalse(commands.contains { $0.arguments.contains("Dock") })
    XCTAssertFalse(commands.contains { $0.arguments.contains("iconservicesagent") })
  }
}
