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
}
