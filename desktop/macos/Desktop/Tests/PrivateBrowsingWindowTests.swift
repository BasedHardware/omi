import XCTest

@testable import Omi_Computer

/// Contract for `PrivateBrowsingWindow`: a private / incognito browser window is recognised
/// from its own title, so Rewind can skip it while the same browser's regular windows keep
/// being captured (#6677).
///
/// The negative cases carry the weight here. Per `FC-meeting-trigger-title-identity-drift`,
/// broader title coverage is what turns a marker into a generic-title false positive, so
/// every positive case is paired with a near-miss that must not match.
final class PrivateBrowsingWindowTests: XCTestCase {
  private let safari = "com.apple.Safari"
  private let chrome = "com.google.Chrome"
  private let brave = "com.brave.Browser"

  // MARK: - Measured markers

  func testSafariPrivateWindowIsPrivate() {
    XCTAssertTrue(
      PrivateBrowsingWindow.isPrivate(
        windowTitle: "Example Domain, Private Browsing", bundleIdentifier: safari))
  }

  func testChromeIncognitoWindowIsPrivate() {
    XCTAssertTrue(
      PrivateBrowsingWindow.isPrivate(
        windowTitle: "Example Domain - Google Chrome (Incognito)", bundleIdentifier: chrome))
  }

  func testBravePrivateWindowIsPrivate() {
    XCTAssertTrue(
      PrivateBrowsingWindow.isPrivate(
        windowTitle: "Example Domain - Brave (Private)", bundleIdentifier: brave))
  }

  // MARK: - Regular windows of the same browsers keep capturing

  func testChromeRegularWindowIsNotPrivate() {
    XCTAssertFalse(
      PrivateBrowsingWindow.isPrivate(
        windowTitle: "Example Domain - Google Chrome", bundleIdentifier: chrome),
      "Excluding a private window must not cost the user their regular browsing context")
  }

  func testSafariRegularWindowIsNotPrivate() {
    XCTAssertFalse(
      PrivateBrowsingWindow.isPrivate(windowTitle: "Example Domain", bundleIdentifier: safari))
  }

  // MARK: - Near misses

  func testMarkerMustBeASuffixNotASubstring() {
    XCTAssertFalse(
      PrivateBrowsingWindow.isPrivate(
        windowTitle: "Notes on Private Browsing, and other topics", bundleIdentifier: safari),
      "A page that merely discusses private browsing is a regular window")
  }

  /// The marker embedded mid-title separates a suffix test from a substring test. Without
  /// these two, relaxing `hasSuffix` to `contains` passes the whole suite while every article
  /// that happens to name private browsing silently stops being captured.
  func testSafariMarkerEmbeddedMidTitleIsNotPrivate() {
    XCTAssertFalse(
      PrivateBrowsingWindow.isPrivate(
        windowTitle: "Reading, Private Browsing explained | Blog", bundleIdentifier: safari))
  }

  func testChromeMarkerEmbeddedMidTitleIsNotPrivate() {
    XCTAssertFalse(
      PrivateBrowsingWindow.isPrivate(
        windowTitle: "Guide (Incognito) tips - Google Chrome", bundleIdentifier: chrome))
  }

  func testMarkerIsNotSharedAcrossBrowsers() {
    XCTAssertFalse(
      PrivateBrowsingWindow.isPrivate(
        windowTitle: "Example Domain, Private Browsing", bundleIdentifier: brave),
      "Safari's marker must not be honoured for a browser that was never measured")
  }

  func testUnknownBundleNeverMatches() {
    XCTAssertFalse(
      PrivateBrowsingWindow.isPrivate(
        windowTitle: "Budget (Private)", bundleIdentifier: "com.apple.Numbers"),
      "Title matching must stay scoped to known browser processes")
  }

  // MARK: - Missing signal resolves toward capture

  func testEmptyTitleIsNotPrivate() {
    XCTAssertFalse(
      PrivateBrowsingWindow.isPrivate(windowTitle: "", bundleIdentifier: chrome),
      "A blank title is an unloaded window, not evidence of a private session")
  }

  func testMissingTitleIsNotPrivate() {
    XCTAssertFalse(
      PrivateBrowsingWindow.isPrivate(windowTitle: nil, bundleIdentifier: chrome))
  }

  func testMissingBundleIdentifierIsNotPrivate() {
    XCTAssertFalse(
      PrivateBrowsingWindow.isPrivate(
        windowTitle: "Example Domain - Google Chrome (Incognito)", bundleIdentifier: nil))
  }
}
