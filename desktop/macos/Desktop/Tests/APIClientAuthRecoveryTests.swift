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
    let snippet = String(source[deleteRange!.lowerBound...]).prefix(500)
    XCTAssertTrue(snippet.contains("performVoidRequest"))
    // Whitespace-agnostic check: the old pattern of throwing .unauthorized
    // before the status-code guard should not reappear in the delete method.
    XCTAssertFalse(snippet.contains("throw APIError.unauthorized"))
  }

  func testAuthenticatedMutationsUseShared401RecoveryPath() throws {
    // omi-test-quality: source-inspection -- static contract: INV-AUTH-1 forbids raw session.data bypasses after buildHeaders(requireAuth:)
    let source = try sourceFile("APIClient.swift")
    let methods = [
      "func setConversationVisibility(",
      "func updateGoalProgress(",
      "func completeGoal(",
      "func setRecordingPermission(",
      "func setPrivateCloudSync(",
      "func assignSegmentsBulk(",
      "func reportRealtimeUsage(",
      "func fetchSyncJobStatus(",
    ]
    for marker in methods {
      guard let start = source.range(of: marker) else {
        return XCTFail("Missing \(marker)")
      }
      // Large enough to cover request-body builders before the shared-path call.
      let snippet = String(source[start.lowerBound...]).prefix(1600)
      let usesSharedPath =
        snippet.contains("performVoidRequest")
        || snippet.contains("performRequest")
        || snippet.contains("performAuthenticatedData")
        || snippet.contains("patch(")
      XCTAssertTrue(usesSharedPath, "\(marker) must use the shared 401 recovery path")
      XCTAssertFalse(
        snippet.contains("session.data(for:"),
        "\(marker) must not call session.data directly"
      )
    }
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
