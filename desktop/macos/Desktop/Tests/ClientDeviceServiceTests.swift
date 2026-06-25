import CryptoKit
import XCTest

@testable import Desktop

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
}
