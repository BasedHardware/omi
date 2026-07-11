import XCTest

@testable import Omi_Computer

final class RewindDatabaseLifecycleTests: XCTestCase {

  func testCloseClearsRunningFlag() async throws {
    let testUserId = "rewind-db-lifecycle-\(UUID().uuidString)"
    let userDir = FileManager.default
      .urls(for: .applicationSupportDirectory, in: .userDomainMask).first!
      .appendingPathComponent("Omi", isDirectory: true)
      .appendingPathComponent("users", isDirectory: true)
      .appendingPathComponent(testUserId, isDirectory: true)
    defer { try? FileManager.default.removeItem(at: userDir) }

    await RewindDatabase.shared.close()
    RewindDatabase.currentUserId = testUserId
    await RewindDatabase.shared.configure(userId: testUserId)
    try await RewindDatabase.shared.initialize()

    let runningFlag = userDir.appendingPathComponent(".omi_running")
    XCTAssertTrue(FileManager.default.fileExists(atPath: runningFlag.path))

    await RewindDatabase.shared.close()

    XCTAssertFalse(FileManager.default.fileExists(atPath: runningFlag.path))
    RewindDatabase.currentUserId = nil
  }
}
