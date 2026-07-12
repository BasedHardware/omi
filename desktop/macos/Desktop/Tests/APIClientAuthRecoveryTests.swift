import XCTest

@testable import Omi_Computer

final class APIClientAuthRecoveryTests: XCTestCase {
  func testAPIClientCentralizes401RefreshAndInvalidate() throws {
    let source = try sourceFile("APIClient.swift")
    XCTAssertTrue(source.contains("invalidateSessionAfterUnauthorized"))
    XCTAssertTrue(source.contains("authorizedRetryRequest"))
    XCTAssertTrue(source.contains("struct RequestAuthPolicy"))
    XCTAssertTrue(source.contains("sessionPreserving"))
    XCTAssertTrue(source.contains("AuthSessionCoordinator.shared.handleHTTPUnauthorized"))
    XCTAssertTrue(source.contains("performVoidRequest"))
  }

  func testDeleteUsesShared401RecoveryPath() throws {
    let source = try sourceFile("APIClient.swift")
    let deleteRange = source.range(of: "func delete(")
    XCTAssertNotNil(deleteRange)
    let snippet = String(source[deleteRange!.lowerBound...]).prefix(900)
    XCTAssertTrue(snippet.contains("performVoidRequest"))
    // Whitespace-agnostic check: the old pattern of throwing .unauthorized
    // before the status-code guard should not reappear in the delete method.
    XCTAssertFalse(snippet.contains("throw APIError.unauthorized"))
  }

  func testAuthBackoffTrackerFullyRemoved() throws {
    let trackerPath = sourceRoot().appendingPathComponent("AuthBackoffTracker.swift")
    XCTAssertFalse(FileManager.default.fileExists(atPath: trackerPath.path))

    let callSites = [
      "Providers/ChatProvider.swift",
      "AppState/AppState+DataLoading.swift",
      "Stores/TasksStore.swift",
      "Stores/DashboardTaskRefreshService.swift",
      "MainWindow/CrispManager.swift",
      "MainWindow/Pages/MemoriesPage.swift",
    ]
    for relative in callSites {
      let source = try sourceFile(relative)
      XCTAssertFalse(source.contains("AuthBackoffTracker"), "expected no AuthBackoffTracker in \(relative)")
    }
  }

  private func sourceRoot() -> URL {
    URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources")
  }

  private func sourceFile(_ relativePath: String) throws -> String {
    try String(contentsOf: sourceRoot().appendingPathComponent(relativePath), encoding: .utf8)
  }
}
