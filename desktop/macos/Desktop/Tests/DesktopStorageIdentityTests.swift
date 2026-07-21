import OmiSupport
import XCTest

@testable import Omi_Computer

final class DesktopStorageIdentityTests: XCTestCase {
  func testNamedDevelopmentBundlesHaveDistinctIdentityDerivedRoots() {
    let first = DesktopStorageIdentity(
      bundleIdentifier: "com.omi.omi-memory-atlas",
      localProfileEnabled: false,
      localProfileStorageName: nil)
    let second = DesktopStorageIdentity(
      bundleIdentifier: "com.omi.omi-rewind-fix",
      localProfileEnabled: false,
      localProfileStorageName: nil)

    XCTAssertTrue(first.usesIsolatedStorage)
    XCTAssertTrue(second.usesIsolatedStorage)
    XCTAssertEqual(first.applicationSupportPathComponents, ["Omi Dev Bundles", "com.omi.omi-memory-atlas"])
    XCTAssertEqual(second.applicationSupportPathComponents, ["Omi Dev Bundles", "com.omi.omi-rewind-fix"])
    XCTAssertNotEqual(first.applicationSupportPathComponents, second.applicationSupportPathComponents)
  }

  func testProtectedAndReviewBundleIDsKeepLegacyStorage() {
    let dev = DesktopStorageIdentity(
      bundleIdentifier: "com.omi.desktop-dev",
      localProfileEnabled: false,
      localProfileStorageName: nil)
    let review = DesktopStorageIdentity(
      bundleIdentifier: "com.omi.review-build",
      localProfileEnabled: false,
      localProfileStorageName: nil)

    XCTAssertFalse(dev.usesIsolatedStorage)
    XCTAssertFalse(review.usesIsolatedStorage)
    XCTAssertEqual(dev.applicationSupportPathComponents, ["Omi"])
    XCTAssertEqual(review.applicationSupportPathComponents, ["Omi"])
  }

  func testNamedLocalProfileStillUsesTheBundleIDBoundary() {
    let identity = DesktopStorageIdentity(
      bundleIdentifier: "com.omi.omi-local-memory",
      localProfileEnabled: true,
      localProfileStorageName: "caller-controlled-name")

    XCTAssertEqual(identity.applicationSupportPathComponents, ["Omi Dev Bundles", "com.omi.omi-local-memory"])
  }

  func testInvalidNamedBundleIDCannotSelectAnIsolatedPath() {
    for bundleID in ["com.omi.omi-", "com.omi.omi-../escape", "com.omi.omi-测试"] {
      let identity = DesktopStorageIdentity(
        bundleIdentifier: bundleID,
        localProfileEnabled: false,
        localProfileStorageName: nil)

      XCTAssertFalse(identity.isNamedDevelopmentBundle, "Unexpected named bundle ID: \(bundleID)")
      XCTAssertEqual(identity.applicationSupportPathComponents, ["Omi"])
    }
  }

  func testIsolatedStorageNeverMigratesTheSharedLegacyRoot() {
    XCTAssertFalse(RewindDatabase.shouldMigrateLegacyStorage(isolatedStorage: true))
    XCTAssertTrue(RewindDatabase.shouldMigrateLegacyStorage(isolatedStorage: false))
  }

  func testRuntimeManifestIsOwnerOnlyAndContainsNoCredentials() throws {
    let root = FileManager.default.temporaryDirectory
      .appendingPathComponent("omi-runtime-manifest-\(UUID().uuidString)", isDirectory: true)
    defer { try? FileManager.default.removeItem(at: root) }

    let manifest = DesktopDevRuntimeManifest(
      bundleIdentifier: "com.omi.omi-manifest-test",
      processID: 42,
      startedAt: Date(timeIntervalSince1970: 1_700_000_000),
      appPath: "/Applications/omi-manifest-test.app",
      profileRoot: root.path,
      logPath: "/private/tmp/omi-dev-com.omi.omi-manifest-test-42.log",
      automationPort: 47777)
    try DesktopDevRuntimeManifestStore.write(manifest, in: root)

    let path = DesktopDevRuntimeManifestStore.path(in: root)
    let attributes = try FileManager.default.attributesOfItem(atPath: path.path)
    XCTAssertEqual((attributes[.posixPermissions] as? NSNumber)?.intValue, 0o600)

    let contents = try String(contentsOf: path, encoding: .utf8)
    XCTAssertFalse(contents.localizedCaseInsensitiveContains("token"))
    XCTAssertFalse(contents.localizedCaseInsensitiveContains("credential"))
    XCTAssertFalse(contents.localizedCaseInsensitiveContains("backend"))
  }
}
