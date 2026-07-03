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
    XCTAssertTrue(source.contains("observeRuntimeProjectionFailures()"))
    XCTAssertTrue(source.contains("surfaceRuntimeFailure(projection)"))
  }

  func testTaskChatUsesContextPacketsWhilePreservingVisibleTaskContext() throws {
    let source = try sourceFile("ProactiveAssistants/Assistants/TaskAgent/TaskChatState.swift")

    XCTAssertTrue(source.contains("buildContextPacketSummary("))
    XCTAssertTrue(source.contains("build_desktop_context_packet"))
    XCTAssertTrue(source.contains("DesktopContextPacket"))
    XCTAssertTrue(source.contains("# Task Context\\n\\n\\(taskContext)\\n\\n---\\n\\n# User Message"))
    XCTAssertTrue(source.contains("The full task context is included below in the prompt."))
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

  func testFailureTranscriptFormatterUsesStructuredProjectionFailure() {
    let projection = AgentRunProjection(
      surface: .taskChat(taskId: "task-runtime-failure"),
      sessionId: "session-1",
      runId: "run-1",
      attemptId: "attempt-1",
      adapterSessionId: nil,
      status: .failed,
      statusText: nil,
      errorMessage: nil,
      failure: AgentRuntimeFailure(
        code: "adapter_process_exited",
        userMessage: "OpenClaw failed: OpenAI API error: upstream unavailable",
        technicalMessage: "OpenAI API error: upstream unavailable",
        source: "adapter_process",
        adapterId: "openclaw",
        provider: "openai",
        retryable: true
      ),
      updatedAt: Date(),
      completedAt: Date(),
      costUsd: nil,
      inputTokens: nil,
      outputTokens: nil
    )

    XCTAssertEqual(
      AgentFailureTranscriptFormatter.errorText(for: projection),
      "OpenClaw failed: OpenAI API error: upstream unavailable"
    )
    XCTAssertEqual(
      AgentFailureTranscriptFormatter.transcriptText(for: AgentFailureTranscriptFormatter.errorText(for: projection) ?? ""),
      "Failed: OpenClaw failed: OpenAI API error: upstream unavailable"
    )
  }

  func testFailureTranscriptFormatterDoesNotDoublePrefix() {
    XCTAssertEqual(
      AgentFailureTranscriptFormatter.transcriptText(for: "OpenClaw failed"),
      "Failed: OpenClaw failed"
    )
    XCTAssertEqual(
      AgentFailureTranscriptFormatter.transcriptText(for: "Failed: OpenClaw failed"),
      "Failed: OpenClaw failed"
    )
  }

  func testRuntimeFailureProjectionSurfacingDoesNotReRecordStatus() throws {
    let source = try sourceFile("ProactiveAssistants/Assistants/TaskAgent/TaskChatState.swift")
    guard let functionRange = source.range(of: "func surfaceRuntimeFailure(") else {
      return XCTFail("surfaceRuntimeFailure function missing")
    }
    let rest = source[functionRange.lowerBound...]
    let nextFunction = rest.range(of: "\n    private func observeRuntimeProjectionFailures()")
    let body = nextFunction.map { String(rest[..<$0.lowerBound]) } ?? String(rest)

    XCTAssertFalse(body.contains("TaskAgentStatusRegistry.shared.markFailed"))
    XCTAssertTrue(body.contains("appendFailureTranscriptMessage(errorText"))
  }

  func testTerminalFailureFinalizeDoesNotPersistFailureTranscriptTwice() throws {
    let source = try sourceFile("ProactiveAssistants/Assistants/TaskAgent/TaskChatState.swift")
    guard let branchRange = source.range(of: "if terminalStatus == .failed || terminalStatus == .timedOut || terminalStatus == .orphaned {") else {
      return XCTFail("terminal failure branch missing")
    }
    let rest = source[branchRange.lowerBound...]
    guard let elseRange = rest.range(of: "\n                } else {") else {
      return XCTFail("terminal failure branch end missing")
    }
    let branch = String(rest[..<elseRange.lowerBound])

    XCTAssertTrue(branch.contains("surfaceCurrentRuntimeFailureIfNeeded(fallbackMessage: \"Agent failed\")"))
    XCTAssertTrue(branch.contains("let shouldPersistPartial"))
    XCTAssertTrue(branch.contains("if shouldPersistPartial"))
    XCTAssertFalse(branch.contains("persistMessage(messages[index])"))
  }

  func testTerminalFailureMarksRemainingToolCallsFailed() throws {
    let source = try sourceFile("ProactiveAssistants/Assistants/TaskAgent/TaskChatState.swift")

    XCTAssertTrue(
      source.contains("private func completeRemainingToolCalls(messageId: String, terminalStatus: ToolCallStatus = .completed)")
    )
    XCTAssertTrue(
      source.contains("ToolCallBlockUpdater.completeRemainingToolCalls(\n            in: &messages[index].contentBlocks,\n            terminalStatus: terminalStatus\n        )")
    )
    XCTAssertTrue(source.contains("completeRemainingToolCalls(messageId: aiMessageId, terminalStatus: .failed)"))
    XCTAssertTrue(source.contains("terminalStatus: failedByUserStop ? .completed : .failed"))
    XCTAssertTrue(source.contains("completeRemainingToolCalls(messageId: activeAssistantMessageId, terminalStatus: .failed)"))
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
