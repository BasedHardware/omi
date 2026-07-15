import XCTest

@testable import Omi_Computer

final class APIClientAuthRecoveryTests: XCTestCase {
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
