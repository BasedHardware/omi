import XCTest

@testable import Omi_Computer

final class TaskChatKernelIdentityTests: XCTestCase {
  func testTaskChatRecordDoesNotPersistSessionIdentity() {
    let message = ChatMessage(id: "message-1", text: "hello", sender: .user)
    let record = TaskChatMessageRecord.from(message, taskId: "task-1")
    XCTAssertEqual(record.taskId, "task-1")
    XCTAssertEqual(record.messageId, "message-1")
  }

  func testTaskChatStateUsesSharedRuntimeNotPerTaskBridge() throws {
    let source = try sourceFile("ProactiveAssistants/Assistants/TaskAgent/TaskChatState.swift")
    XCTAssertTrue(source.contains("TaskChatRuntime.query("))
    XCTAssertFalse(source.contains("private var agentBridge"))
    XCTAssertFalse(source.contains("ensureBridgeStarted"))
  }

  func testTaskChatStateUsesKernelSurfaceRef() throws {
    let source = try sourceFile("ProactiveAssistants/Assistants/TaskAgent/TaskChatState.swift")

    XCTAssertTrue(
      source.contains("AgentSurfaceReference.taskChat(taskId: taskId)")
        || source.contains("projection.surface == .taskChat(taskId: taskId)")
    )
    XCTAssertFalse(source.contains("legacyAcpSessionId"))
    XCTAssertFalse(source.contains("currentOmiSessionId"))
    XCTAssertFalse(source.contains("getACPSessionId"))
    XCTAssertFalse(source.contains("acpSessionId"))
  }

  func testTaskChatFailureKeepsVisibleAssistantMessage() throws {
    let source = try sourceFile("ProactiveAssistants/Assistants/TaskAgent/TaskChatState.swift")

    XCTAssertTrue(source.contains("Self.applyFailureTextIfNeeded(to: &messages[index], errorDescription: error.localizedDescription)"))
    XCTAssertTrue(source.contains("persistMessage(messages[index])"))
    XCTAssertTrue(source.contains("observeRuntimeProjectionFailures()"))
    XCTAssertTrue(source.contains("surfaceRuntimeFailure(projection)"))
  }

  func testTaskChatSendsRawPromptAndSurfaceContextToKernel() throws {
    let source = try sourceFile("ProactiveAssistants/Assistants/TaskAgent/TaskChatState.swift")

    XCTAssertTrue(source.contains("prompt: trimmedText"))
    XCTAssertTrue(source.contains("surfaceContextJson: taskContext"))
    XCTAssertFalse(source.contains("buildContextPacketSummary("))
    XCTAssertFalse(source.contains("build_desktop_context_packet"))
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
    XCTAssertEqual(message.contentBlocks.count, 2)
    guard case .text(_, "Failed: OpenClaw failed") = message.contentBlocks[1] else {
      return XCTFail("Expected failure text to be visible in structured chat blocks")
    }
  }

  @MainActor
  func testTaskChatFailureKeepsPlainPartialTextVisible() {
    var message = ChatMessage(
      id: "assistant-1",
      text: "Partial answer",
      sender: .ai,
      isStreaming: true
    )

    TaskChatState.applyFailureTextIfNeeded(to: &message, errorDescription: "OpenClaw failed")

    XCTAssertEqual(message.text, "Partial answer\n\nFailed: OpenClaw failed")
    XCTAssertTrue(message.contentBlocks.isEmpty)
  }

  @MainActor
  func testTaskChatFailureDoesNotDuplicateSplitPartialTextBlocks() {
    var message = ChatMessage(
      id: "assistant-1",
      text: "Partial answer",
      sender: .ai,
      isStreaming: true,
      contentBlocks: [
        .text(id: "text-1", text: "Partial "),
        .thinking(id: "thinking-1", text: "Looking up context"),
        .text(id: "text-2", text: "answer"),
      ]
    )

    TaskChatState.applyFailureTextIfNeeded(to: &message, errorDescription: "OpenClaw failed")

    XCTAssertEqual(message.text, "Partial answer\n\nFailed: OpenClaw failed")
    XCTAssertEqual(message.contentBlocks.count, 4)
    guard case .text(_, "Partial ") = message.contentBlocks[0],
          case .thinking(_, "Looking up context") = message.contentBlocks[1],
          case .text(_, "answer") = message.contentBlocks[2],
          case .text(_, "Failed: OpenClaw failed") = message.contentBlocks[3] else {
      return XCTFail("Expected split partial text to stay in place with only failure text appended")
    }
  }

  func testTaskChatUserStopDoesNotAppendFailureText() throws {
    let source = try sourceFile("ProactiveAssistants/Assistants/TaskAgent/TaskChatState.swift")

    XCTAssertTrue(source.contains("if !failedByUserStop {\n                        Self.applyFailureTextIfNeeded"))
    XCTAssertTrue(source.contains("terminalStatus: failedByUserStop ? .completed : .failed"))
  }

  func testTaskChatFollowUpSignalsLocalSendWhenUserRowIsAppended() throws {
    let source = try sourceFile("ProactiveAssistants/Assistants/TaskAgent/TaskChatState.swift")

    XCTAssertTrue(source.contains("if !isFollowUp {\n            localSendToken = LocalSendToken"))
    XCTAssertTrue(source.contains("messages.append(userMessage)\n        localSendToken = LocalSendToken"))
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
      source.contains("streamingBuffer.completeRemainingToolCalls(")
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
