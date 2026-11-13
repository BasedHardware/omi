import XCTest

@testable import Omi_Computer

/// capture_screen leaves out the apps Omi never looks at.
final class CaptureScreenExclusionTests: XCTestCase {
  private func app(_ pid: pid_t, _ bundleID: String, _ name: String?) -> UIAutomationRunningApp {
    UIAutomationRunningApp(pid: pid, bundleID: bundleID, localizedName: name, bundleURL: nil, isActive: false)
  }

  func testOmiTheRefusedAppsAndCaptureExcludedAppsAreLeftOut() {
    let running = [
      app(10, "com.apple.TextEdit", "TextEdit"),
      app(11, "com.apple.Terminal", "Terminal"),
      app(12, "com.1password.1password", "1Password"),
      app(13, "com.apple.SecurityAgent", nil),
      app(14, "com.omi.computer-macos.beta", "Omi Beta"),
      app(15, "com.apple.Safari", "Safari"),
      app(16, "", "Banking Helper"),
      app(17, "com.apple.Notes", "Notes"),
    ]

    let excluded = CaptureScreenExclusion.excludedPIDs(
      running: running, ownPID: 99, isExcludedFromCapture: { ["Banking Helper", "Notes"].contains($0) })

    XCTAssertEqual(excluded, [99, 11, 12, 13, 14, 16, 17])
  }

  func testTheFilterRemovesExactlyTheLeftOutApplications() {
    struct Listed: Equatable {
      let processID: pid_t
      let name: String
    }
    let listed = [
      Listed(processID: 10, name: "TextEdit"), Listed(processID: 11, name: "Terminal"),
      Listed(processID: 99, name: "Omi"),
    ]

    let removed = CaptureScreenExclusion.applicationsToExclude(listed, processID: \.processID, excluded: [11, 99])

    XCTAssertEqual(removed.map(\.name), ["Terminal", "Omi"])
  }

  func testThePlainCaptureStandsInOnlyWhenNoLeftOutAppIsOnScreen() {
    XCTAssertTrue(CaptureScreenExclusion.plainCaptureAllowed(onScreenWindowOwners: [10, 15], excluded: [11, 99]))
    XCTAssertFalse(
      CaptureScreenExclusion.plainCaptureAllowed(onScreenWindowOwners: [10, 11], excluded: [11, 99]),
      "a terminal covering the screen would end up in the picture")
  }
}
