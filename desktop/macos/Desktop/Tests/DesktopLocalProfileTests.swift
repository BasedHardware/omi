import OmiSupport
import XCTest

final class DesktopLocalProfileTests: XCTestCase {
  func testNamedDevelopmentBundleUsesDedicatedStorageRoot() {
    XCTAssertEqual(
      DesktopStorageIdentity(
        bundleIdentifier: "com.omi.omi-memory-atlas-types",
        localProfileEnabled: false,
        localProfileStorageName: nil
      ).applicationSupportPathComponents,
      ["Omi Dev Bundles", "com.omi.omi-memory-atlas-types"]
    )
  }

  func testProductionAndDefaultDevBundleKeepSharedStorageRoot() {
    for bundleIdentifier in ["com.omi.computer-macos", "com.omi.desktop-dev"] {
      XCTAssertEqual(
        DesktopStorageIdentity(
          bundleIdentifier: bundleIdentifier,
          localProfileEnabled: false,
          localProfileStorageName: nil
        ).applicationSupportPathComponents,
        ["Omi"]
      )
    }
  }

  func testNamedDevelopmentBundleTakesPrecedenceOverLocalProfileStorage() {
    XCTAssertEqual(
      DesktopStorageIdentity(
        bundleIdentifier: "com.omi.omi-memory-atlas-types",
        localProfileEnabled: true,
        localProfileStorageName: "Omi-local-test"
      ).applicationSupportPathComponents,
      ["Omi Dev Bundles", "com.omi.omi-memory-atlas-types"]
    )
  }
}
