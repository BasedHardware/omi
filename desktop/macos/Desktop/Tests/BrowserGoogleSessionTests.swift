import XCTest

@testable import Omi_Computer

final class BrowserGoogleSessionTests: XCTestCase {
  private var tempRoot: URL!

  override func setUpWithError() throws {
    try super.setUpWithError()
    tempRoot = FileManager.default.temporaryDirectory
      .appendingPathComponent("browser-google-session-\(UUID().uuidString)", isDirectory: true)
    try FileManager.default.createDirectory(at: tempRoot, withIntermediateDirectories: true)
  }

  override func tearDownWithError() throws {
    if let tempRoot {
      try? FileManager.default.removeItem(at: tempRoot)
    }
    try super.tearDownWithError()
  }

  func testCookiePathsPreferChromiumNetworkCookieStore() throws {
    let defaultProfile = tempRoot.appendingPathComponent("Default", isDirectory: true)
    let networkDir = defaultProfile.appendingPathComponent("Network", isDirectory: true)
    try FileManager.default.createDirectory(at: networkDir, withIntermediateDirectories: true)
    try Data().write(to: defaultProfile.appendingPathComponent("Cookies"))
    try Data().write(to: networkDir.appendingPathComponent("Cookies"))

    let profile2 = tempRoot.appendingPathComponent("Profile 2", isDirectory: true)
    try FileManager.default.createDirectory(at: profile2, withIntermediateDirectories: true)
    try Data().write(to: profile2.appendingPathComponent("Cookies"))

    XCTAssertEqual(
      BrowserGoogleSession.cookiePaths(in: tempRoot.path),
      [
        networkDir.appendingPathComponent("Cookies").path,
        profile2.appendingPathComponent("Cookies").path,
      ])
  }

  // MARK: - Safe Storage keychain read fallback

  /// The in-process `SecItemCopyMatching` read is the primary path (prompt attributed to
  /// this app). The legacy `/usr/bin/security` CLI is only a fallback for environmental
  /// failures — never a second prompt after a user denial, and never when the item is
  /// absent. This locks in that decision across every supported macOS version.
  func testFallsBackToLegacyCLIOnlyForEnvironmentalStatuses() {
    // Environmental failures the in-process read cannot handle → fall back to the CLI.
    XCTAssertTrue(
      BrowserKeychainCache.shouldFallBackToLegacyCLI(afterNativeReadStatus: errSecInteractionNotAllowed))
    XCTAssertTrue(
      BrowserKeychainCache.shouldFallBackToLegacyCLI(afterNativeReadStatus: errSecNotAvailable))

    // Read already succeeded → nothing to retry.
    XCTAssertFalse(
      BrowserKeychainCache.shouldFallBackToLegacyCLI(afterNativeReadStatus: errSecSuccess))

    // User actively denied → do NOT re-prompt via the "security" CLI.
    XCTAssertFalse(
      BrowserKeychainCache.shouldFallBackToLegacyCLI(afterNativeReadStatus: errSecUserCanceled))
    XCTAssertFalse(
      BrowserKeychainCache.shouldFallBackToLegacyCLI(afterNativeReadStatus: errSecAuthFailed))

    // No item (no browser session) → the CLI cannot conjure one either.
    XCTAssertFalse(
      BrowserKeychainCache.shouldFallBackToLegacyCLI(afterNativeReadStatus: errSecItemNotFound))
  }
}
