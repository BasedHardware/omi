import XCTest

@testable import Omi_Computer

@MainActor
final class OmiAppWindowTitleTests: XCTestCase {
  func testNamedBuildIncludesVersion() {
    XCTAssertEqual(
      OMIApp.windowTitle(
        displayName: "Omi Beta",
        version: "0.12.73",
        launchMode: .full,
        isNonProduction: true),
      "Omi Beta v0.12.73")
  }

  func testNamedRewindBuildIncludesVersion() {
    XCTAssertEqual(
      OMIApp.windowTitle(
        displayName: "Omi Dev",
        version: "0.12.73",
        launchMode: .rewind,
        isNonProduction: true),
      "Omi Dev Rewind v0.12.73")
  }

  func testEmptyVersionFallsBackToName() {
    XCTAssertEqual(
      OMIApp.windowTitle(
        displayName: "Omi Beta",
        version: "",
        launchMode: .full,
        isNonProduction: true),
      "Omi Beta")
  }

  func testProductionTitleRemainsUnchanged() {
    XCTAssertEqual(
      OMIApp.windowTitle(
        displayName: "ignored",
        version: "0.12.70",
        launchMode: .full,
        isNonProduction: false),
      "omi v0.12.70")
  }
}
