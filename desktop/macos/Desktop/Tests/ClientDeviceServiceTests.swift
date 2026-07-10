import CryptoKit
import XCTest

@testable import Omi_Computer

final class ClientDeviceServiceTests: XCTestCase {
  func testDeviceIdHashIsStableEightHexChars() {
    let hash = ClientDeviceService.shared.deviceIdHash
    XCTAssertEqual(hash.count, 8)
    XCTAssertTrue(hash.allSatisfy { $0.isHexDigit })
    XCTAssertEqual(hash, ClientDeviceService.shared.deviceIdHash)
  }

  func testClientDeviceIdUsesMacosPrefix() {
    let id = ClientDeviceService.shared.clientDeviceId
    XCTAssertTrue(id.hasPrefix("macos_"))
    XCTAssertEqual(id, "macos_\(ClientDeviceService.shared.deviceIdHash)")
  }

  func testNamedDevelopmentBundleUsesBundleScopedInstallId() {
    let suiteName = "ClientDeviceServiceTests.named.\(UUID().uuidString)"
    let defaults = UserDefaults(suiteName: suiteName)!
    defer {
      defaults.removePersistentDomain(forName: suiteName)
    }

    let service = ClientDeviceService(
      bundleIdentifier: "com.omi.omi-menubar-logo",
      userDefaults: defaults
    )
    let hash = service.deviceIdHash

    XCTAssertEqual(hash.count, 8)
    XCTAssertEqual(
      hash,
      ClientDeviceService(
        bundleIdentifier: "com.omi.omi-menubar-logo",
        userDefaults: defaults
      ).deviceIdHash
    )
  }

  func testDesktopDevBundleAlsoUsesUserDefaultsInstallId() {
    // Omi Dev must not touch the shared login-keychain device-id item either.
    let suiteName = "ClientDeviceServiceTests.dev.\(UUID().uuidString)"
    let defaults = UserDefaults(suiteName: suiteName)!
    defer {
      defaults.removePersistentDomain(forName: suiteName)
    }

    let service = ClientDeviceService(
      bundleIdentifier: AppBuild.desktopDevBundleIdentifier,
      userDefaults: defaults
    )
    _ = service.deviceIdHash
    XCTAssertNotNil(defaults.string(forKey: "dev-client-device-install-uuid"))
  }

  func testNamedDevelopmentBundlesDoNotShareInstallIds() {
    let firstSuiteName = "ClientDeviceServiceTests.first.\(UUID().uuidString)"
    let secondSuiteName = "ClientDeviceServiceTests.second.\(UUID().uuidString)"
    let firstDefaults = UserDefaults(suiteName: firstSuiteName)!
    let secondDefaults = UserDefaults(suiteName: secondSuiteName)!
    defer {
      firstDefaults.removePersistentDomain(forName: firstSuiteName)
      secondDefaults.removePersistentDomain(forName: secondSuiteName)
    }

    let first = ClientDeviceService(
      bundleIdentifier: "com.omi.omi-first-feature",
      userDefaults: firstDefaults
    )
    let second = ClientDeviceService(
      bundleIdentifier: "com.omi.omi-second-feature",
      userDefaults: secondDefaults
    )

    _ = first.deviceIdHash
    _ = second.deviceIdHash

    XCTAssertNotEqual(
      firstDefaults.string(forKey: "dev-client-device-install-uuid"),
      secondDefaults.string(forKey: "dev-client-device-install-uuid")
    )
  }

  func testProductionMigratesMirroredInstallIdWhenScopedKeychainIsMissing() {
    let suiteName = "ClientDeviceServiceTests.production-mirror.\(UUID().uuidString)"
    let defaults = UserDefaults(suiteName: suiteName)!
    let mirror = "stable-install-id-before-scoped-keychain"
    defaults.set(mirror, forKey: "client-device-install-uuid-mirror")
    defer {
      defaults.removePersistentDomain(forName: suiteName)
    }

    var persistedInstallIds: [String] = []
    let service = ClientDeviceService(
      bundleIdentifier: AppBuild.productionBundleIdentifier,
      userDefaults: defaults,
      keychainReader: { .missing },
      keychainWriter: { persistedInstallIds.append($0) }
    )

    let expectedHash = SHA256.hash(data: Data(mirror.utf8))
      .map { String(format: "%02x", $0) }
      .joined()
      .prefix(8)
      .description

    XCTAssertEqual(service.deviceIdHash, expectedHash)
    XCTAssertEqual(persistedInstallIds, [mirror])
    XCTAssertEqual(defaults.string(forKey: "client-device-install-uuid-mirror"), mirror)
  }
}
