import XCTest

@testable import Omi_Computer

final class LocalExtensionQAStorageTests: XCTestCase {
  func testOnlyExplicitNamedQAUsesAnIsolatedTemporaryRoot() {
    let temporary = URL(fileURLWithPath: "/tmp/owned-fixture", isDirectory: true)
    let first = LocalExtensionQAStorage.root(
      enabled: true, isNonProduction: true,
      bundleIdentifier: "com.omi.omi-marketplace-setup", temporaryDirectory: temporary)
    XCTAssertEqual(first?.deletingLastPathComponent(), temporary)
    XCTAssertEqual(
      first,
      LocalExtensionQAStorage.root(
        enabled: true, isNonProduction: true,
        bundleIdentifier: "com.omi.omi-marketplace-setup", temporaryDirectory: temporary))
    XCTAssertNotEqual(
      first,
      LocalExtensionQAStorage.root(
        enabled: true, isNonProduction: true,
        bundleIdentifier: "com.omi.omi-other-setup", temporaryDirectory: temporary))
    let longPrefix = "com.omi.omi-" + String(repeating: "x", count: 80)
    XCTAssertNotEqual(
      LocalExtensionQAStorage.root(
        enabled: true, isNonProduction: true, bundleIdentifier: longPrefix + "a", temporaryDirectory: temporary),
      LocalExtensionQAStorage.root(
        enabled: true, isNonProduction: true, bundleIdentifier: longPrefix + "b", temporaryDirectory: temporary))
    XCTAssertNil(
      LocalExtensionQAStorage.root(
        enabled: true, isNonProduction: true,
        bundleIdentifier: "com.omi.omi-invalid/../path", temporaryDirectory: temporary))
  }

  func testProductionBetaSharedDevAndUnsetFlagKeepTheirUsualStorage() {
    let temporary = URL(fileURLWithPath: "/tmp/owned-fixture", isDirectory: true)
    for bundle in ["com.omi.computer-macos", "com.omi.computer-macos.beta", "com.omi.desktop-dev"] {
      XCTAssertNil(
        LocalExtensionQAStorage.root(
          enabled: true, isNonProduction: true, bundleIdentifier: bundle, temporaryDirectory: temporary))
    }
    XCTAssertNil(
      LocalExtensionQAStorage.root(
        enabled: false, isNonProduction: true,
        bundleIdentifier: "com.omi.omi-marketplace-setup", temporaryDirectory: temporary))
    XCTAssertNil(
      LocalExtensionQAStorage.root(
        enabled: true, isNonProduction: false,
        bundleIdentifier: "com.omi.omi-marketplace-setup", temporaryDirectory: temporary))
  }
}
