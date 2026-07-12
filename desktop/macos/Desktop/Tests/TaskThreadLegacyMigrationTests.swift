import XCTest

@testable import Omi_Computer

@MainActor
final class TaskThreadLegacyMigrationTests: XCTestCase {
  private var testUserID: String!
  private var userDirectory: URL!

  override func setUp() async throws {
    try await super.setUp()
    testUserID = "task-thread-migration-\(UUID().uuidString)"
    await RewindDatabase.shared.close()
    await TaskChatMessageStorage.shared.invalidateCache()
    RewindDatabase.currentUserId = testUserID
    await RewindDatabase.shared.configure(userId: testUserID)
    try await RewindDatabase.shared.initialize()
    let appSupport = FileManager.default.urls(
      for: .applicationSupportDirectory,
      in: .userDomainMask
    ).first!
    userDirectory = appSupport
      .appendingPathComponent("Omi", isDirectory: true)
      .appendingPathComponent("users", isDirectory: true)
      .appendingPathComponent(testUserID, isDirectory: true)
  }

  override func tearDown() async throws {
    await RewindDatabase.shared.close()
    await TaskChatMessageStorage.shared.invalidateCache()
    RewindDatabase.currentUserId = nil
    if let userDirectory { try? FileManager.default.removeItem(at: userDirectory) }
    try await super.tearDown()
  }

  func testLegacyTaskHistoriesCoalesceOnlyLatestHundredRowsAcrossWorkstream() async throws {
    for index in 0..<120 {
      let sourceTaskID = index < 70 ? "legacy-task-a" : "legacy-task-b"
      _ = try await TaskChatMessageStorage.shared.insert(
        TaskChatMessageRecord(
          taskId: sourceTaskID,
          messageId: "message-\(index)",
          sender: index.isMultiple(of: 2) ? "user" : "ai",
          messageText: "bounded message \(index)",
          createdAt: Date(timeIntervalSince1970: TimeInterval(index)),
          updatedAt: Date(timeIntervalSince1970: TimeInterval(index))
        )
      )
    }

    let moved = try await TaskChatMessageStorage.shared.migrateLegacyMessages(
      fromTaskIds: ["legacy-task-a", "legacy-task-b"],
      toWorkstreamId: "workstream-1"
    )
    let migrated = try await TaskChatMessageStorage.shared.getMessages(forWorkstreamId: "workstream-1")
    let legacyA = try await TaskChatMessageStorage.shared.getMessages(forTaskId: "legacy-task-a")
    let legacyB = try await TaskChatMessageStorage.shared.getMessages(forTaskId: "legacy-task-b")

    XCTAssertEqual(moved, 100)
    XCTAssertEqual(migrated.count, 100)
    XCTAssertEqual(migrated.first?.messageId, "message-20")
    XCTAssertEqual(migrated.last?.messageId, "message-119")
    XCTAssertEqual(legacyA.map(\.messageId), (0..<20).map { "message-\($0)" })
    XCTAssertTrue(legacyB.isEmpty)
  }
}
