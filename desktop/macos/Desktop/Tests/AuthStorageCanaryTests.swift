import XCTest

@testable import Omi_Computer

final class AuthStorageCanaryTests: XCTestCase {
  func testDistributionCanariesBypassProductWillFinishStartup() throws {
    let appFile = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources/OmiApp.swift")
    // omi-test-quality: source-inspection -- static contract: distribution canaries must return before resource loading and instance locking; launch-order behavior has no injectable runtime seam.
    let source = try String(contentsOf: appFile, encoding: .utf8)
    let canaryGuard = try XCTUnwrap(
      source.range(
        of: "if AuthStorageCanary.isRequested || UserNotificationCallbackBridge.isSignedSmokeRequested()"))
    let fontRegistration = try XCTUnwrap(source.range(of: "OmiFontRegistration.registerAll()"))
    let instanceGuard = try XCTUnwrap(source.range(of: "SingleInstanceGuard.enforceSingleInstanceOrExit("))

    XCTAssertLessThan(canaryGuard.lowerBound, fontRegistration.lowerBound)
    XCTAssertLessThan(canaryGuard.lowerBound, instanceGuard.lowerBound)
  }

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
