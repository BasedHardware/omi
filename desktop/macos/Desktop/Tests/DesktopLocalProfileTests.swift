import OmiSupport
import XCTest

final class DesktopLocalProfileTests: XCTestCase {
  func testNamedDevelopmentBundleUsesDedicatedStorageRoot() {
    XCTAssertEqual(
      DesktopLocalProfile.storageDirectoryName(
        bundleIdentifier: "com.omi.omi-memory-atlas-types",
        localProfileEnabled: false,
        localProfileStorageName: nil),
      "Omi-com.omi.omi-memory-atlas-types")
  }

  func testProductionAndDefaultDevBundleKeepSharedStorageRoot() {
    for bundleIdentifier in ["com.omi.computer-macos", "com.omi.desktop-dev"] {
      XCTAssertEqual(
        DesktopLocalProfile.storageDirectoryName(
          bundleIdentifier: bundleIdentifier,
          localProfileEnabled: false,
          localProfileStorageName: nil),
        "Omi")
    }
  }

  func testLocalProfileStorageNameTakesPrecedence() {
    XCTAssertEqual(
      DesktopLocalProfile.storageDirectoryName(
        bundleIdentifier: "com.omi.omi-memory-atlas-types",
        localProfileEnabled: true,
        localProfileStorageName: "Omi-local-test"),
      "Omi-local-test")
  }
}
