import XCTest

@testable import Omi_Computer

final class AuthStorageCanaryTests: XCTestCase {
  func testCanaryProvesWriteReadAndDelete() {
    var value: String?
    let result = AuthStorageCanary.execute(
      hooks: .init(
        set: { newValue, _, _ in
          value = newValue
          return true
        },
        read: { _, _ in value },
        delete: { _, _ in value = nil }
      ))

    XCTAssertEqual(result, .init(success: true, stage: "complete"))
    XCTAssertNil(value)
  }

  func testCanaryFailsWhenSignedArtifactCannotWriteKeychain() {
    let result = AuthStorageCanary.execute(
      hooks: .init(
        set: { _, _, _ in false },
        read: { _, _ in nil },
        delete: { _, _ in }
      ))

    XCTAssertEqual(result, .init(success: false, stage: "write"))
  }

  func testCanaryFailsWhenReadBackDoesNotMatch() {
    let result = AuthStorageCanary.execute(
      hooks: .init(
        set: { _, _, _ in true },
        read: { _, _ in "different" },
        delete: { _, _ in }
      ))

    XCTAssertEqual(result, .init(success: false, stage: "read_back"))
  }
}
