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

    // Adapter-namespacing guard: adapterSessionId must only be stored into
    // legacyAcpSessionId when the active harness supports legacy resume
    // (ACP/pi-mono), preventing cross-adapter resume ID pollution.
    XCTAssertTrue(source.contains("private var currentHarness: String?"))
    XCTAssertTrue(source.contains("currentHarness = harness"))
    XCTAssertTrue(source.contains("let supportsLegacyResume = (currentHarness == \"acp\" || currentHarness == \"piMono\")"))
  }

  func testTaskChatFailureKeepsVisibleAssistantMessage() throws {
    let source = try sourceFile("ProactiveAssistants/Assistants/TaskAgent/TaskChatState.swift")

    XCTAssertTrue(source.contains("Self.applyFailureTextIfNeeded(to: &messages[index], errorDescription: error.localizedDescription)"))
    XCTAssertTrue(source.contains("persistMessage(messages[index])"))
  }

  @MainActor
  func testTaskChatFailureAddsTextWhenMessageAlreadyHasBlocks() {
    var message = ChatMessage(
      id: "assistant-1",
      text: "",
      sender: .ai,
      isStreaming: true,
      contentBlocks: [
        .toolCall(id: "tool-1", name: "Bash", status: .running, toolUseId: "tool-use-1", input: nil, output: nil)
      ]
    )

    TaskChatState.applyFailureTextIfNeeded(to: &message, errorDescription: "OpenClaw failed")

    XCTAssertEqual(message.text, "Failed: OpenClaw failed")
    XCTAssertFalse(message.contentBlocks.isEmpty)
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
