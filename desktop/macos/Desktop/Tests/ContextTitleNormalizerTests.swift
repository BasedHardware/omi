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

  func testNumericDocumentSuffixRemainsPartOfIdentityOutsideMessagingApps() {
    XCTAssertNotEqual(
      ContextTitleNormalizer.identityKey(appName: "Safari", windowTitle: "Issue (123)"),
      ContextTitleNormalizer.identityKey(appName: "Safari", windowTitle: "Issue (456)"))
  }

  func testMessagingUnreadCountIsRemovedOnlyForMessagingApps() {
    XCTAssertEqual(
      ContextTitleNormalizer.normalize("Project room (42)", appName: "Telegram"),
      ContextTitleNormalizer.normalize("Project room", appName: "Telegram"))
    XCTAssertNotEqual(
      ContextTitleNormalizer.normalize("Project room (42)", appName: "Safari"),
      ContextTitleNormalizer.normalize("Project room", appName: "Safari"))
  }

  func testUntitledDoesNotBecomeMergeableIdentity() {
    XCTAssertNil(ContextTitleNormalizer.normalize("   ", appName: "Safari"))
  }
}
