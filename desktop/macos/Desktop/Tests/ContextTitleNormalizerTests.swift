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

  func testLeadingUnreadBadgeIsRemovedForBrowsers() {
    // `(4) Home / X` and `Home / X` are the same page with a different badge.
    // The pre-existing count regexes were `$`-anchored, so these hashed apart.
    XCTAssertEqual(
      ContextTitleNormalizer.identityKey(appName: "Google Chrome", windowTitle: "(4) Home / X"),
      ContextTitleNormalizer.identityKey(appName: "Google Chrome", windowTitle: "Home / X"))
    XCTAssertEqual(
      ContextTitleNormalizer.identityKey(appName: "Safari", windowTitle: "[12] Inbox - Gmail"),
      ContextTitleNormalizer.identityKey(appName: "Safari", windowTitle: "Inbox - Gmail"))
  }

  func testLeadingBadgeStripDoesNotCollapseTrailingIdentity() {
    // The leading strip must not weaken the deliberate per-item granularity that
    // `testNumericDocumentSuffixRemainsPartOfIdentityOutsideMessagingApps` guards.
    XCTAssertNotEqual(
      ContextTitleNormalizer.identityKey(appName: "Google Chrome", windowTitle: "Issue (123)"),
      ContextTitleNormalizer.identityKey(appName: "Google Chrome", windowTitle: "Issue (456)"))
  }

  func testLeadingBadgeIsPreservedOutsideBrowsersAndMessaging() {
    XCTAssertNotEqual(
      ContextTitleNormalizer.identityKey(appName: "Preview", windowTitle: "(1) Draft"),
      ContextTitleNormalizer.identityKey(appName: "Preview", windowTitle: "Draft"))
  }

  func testSlackWebItemCounterIsRemoved() {
    // Slack's web title says "1 new item", which the original `messages?`
    // pattern never matched, leaving two buckets for one workspace.
    XCTAssertEqual(
      ContextTitleNormalizer.normalize("Unread messages - acme - 1 new item", appName: "Slack"),
      ContextTitleNormalizer.normalize("Unread messages - acme - 3 new items", appName: "Slack"))
  }

  func testUntitledDoesNotBecomeMergeableIdentity() {
    XCTAssertNil(ContextTitleNormalizer.normalize("   ", appName: "Safari"))
  }

  func testBlankAndNoiseOnlyTitlesDoNotShareIdentityKey() {
    XCTAssertNil(ContextTitleNormalizer.identityKey(appName: "Safari", windowTitle: "   "))
    XCTAssertNil(ContextTitleNormalizer.identityKey(appName: "Safari", windowTitle: nil))
    XCTAssertNil(ContextTitleNormalizer.identityKey(appName: "Safari", windowTitle: "✳ ◐"))
    XCTAssertNotEqual(
      ContextTitleNormalizer.identityKey(appName: "Safari", windowTitle: "Report"),
      ContextTitleNormalizer.identityKey(appName: "Safari", windowTitle: "   "))
  }
}
