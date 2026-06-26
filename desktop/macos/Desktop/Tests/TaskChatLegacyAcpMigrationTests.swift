import XCTest

@testable import Omi_Computer

final class TaskChatLegacyAcpMigrationTests: XCTestCase {
  func testTaskChatRecordStoresOnlyExplicitLegacyAcpSessionId() {
    let message = ChatMessage(id: "message-1", text: "hello", sender: .user)

    let legacyRecord = TaskChatMessageRecord.from(
      message,
      taskId: "task-1",
      acpSessionId: "acp-native-session-1"
    )
    let canonicalRecord = TaskChatMessageRecord.from(
      message,
      taskId: "task-1",
      acpSessionId: nil
    )

    XCTAssertEqual(legacyRecord.acpSessionId, "acp-native-session-1")
    XCTAssertNil(canonicalRecord.acpSessionId)
  }

  func testTaskChatStateSeparatesCanonicalOmiAndLegacyAcpSessionSources() throws {
    let source = try sourceFile("ProactiveAssistants/Assistants/TaskAgent/TaskChatState.swift")

    XCTAssertTrue(source.contains("@Published var legacyAcpSessionId: String?"))
    XCTAssertTrue(source.contains("@Published var currentOmiSessionId: String?"))
    XCTAssertFalse(source.contains("@Published var currentSessionId: String?"))
    XCTAssertTrue(source.contains("omiSessionId: currentOmiSessionId ?? AgentRuntimeStatusStore.shared.knownSessionId(for: .taskChat(taskId: taskId))"))
    XCTAssertTrue(source.contains("resume: legacyAcpSessionId"))
    XCTAssertTrue(source.contains("legacyAcpSessionId = adapterSessionId"))
    XCTAssertFalse(source.contains("legacyAcpSessionId = queryResult.omiSessionId"))
  }

  func testActionItemChatSessionIdLegacyMarkerStillUsesTaskId() throws {
    let coordinator = try sourceFile("ProactiveAssistants/Assistants/TaskAgent/TaskChatCoordinator.swift")

    XCTAssertTrue(coordinator.contains("updateChatSessionId(taskId: task.id, sessionId: task.id)"))
    XCTAssertFalse(coordinator.contains("chatSessionId = state.currentOmiSessionId"))
    XCTAssertFalse(coordinator.contains("chatSessionId = state.legacyAcpSessionId"))
  }

  private func sourceFile(_ relativePath: String) throws -> String {
    let sourceURL = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources")
      .appendingPathComponent(relativePath)
    return try String(contentsOf: sourceURL, encoding: .utf8)
  }
}
