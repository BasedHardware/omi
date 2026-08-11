import XCTest

@testable import Omi_Computer

final class ContextTitleNormalizerTests: XCTestCase {
  func testCosmeticNoiseDoesNotChangeIdentity() {
    XCTAssertEqual(
      ContextTitleNormalizer.identityKey(appName: "Telegram", windowTitle: "Project room (42) ⠋ 12:34"),
      ContextTitleNormalizer.identityKey(appName: "Telegram", windowTitle: "  Project   room "))
  }

  func testAppSpecificMessagingCounterIsRemoved() {
    XCTAssertEqual(
      ContextTitleNormalizer.normalize("Launch – 4 new messages", appName: "Slack"),
      "Launch")
  }

  func testUntitledDoesNotBecomeMergeableIdentity() {
    XCTAssertNil(ContextTitleNormalizer.normalize("   ", appName: "Safari"))
  }
}
