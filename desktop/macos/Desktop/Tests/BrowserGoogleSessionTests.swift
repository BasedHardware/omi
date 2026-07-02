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
}
