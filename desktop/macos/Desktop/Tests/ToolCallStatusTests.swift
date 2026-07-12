import XCTest

@testable import Omi_Computer

/// Locks in the contract for the extended `ToolCallStatus` enum and the
/// `isInFlight` computed property that downstream guards rely on.
final class ToolCallStatusTests: XCTestCase {

  // MARK: - isInFlight contract

  func testIsInFlightTrueForRunningSlowStalled() {
    XCTAssertTrue(ToolCallStatus.running.isInFlight)
    XCTAssertTrue(ToolCallStatus.slow.isInFlight)
    XCTAssertTrue(ToolCallStatus.stalled.isInFlight)
  }

  func testIsInFlightFalseForCompletedFailed() {
    XCTAssertFalse(ToolCallStatus.completed.isInFlight)
    XCTAssertFalse(ToolCallStatus.failed.isInFlight)
  }

  /// Adding a new enum case without updating this expectation should
  /// force a conscious decision about whether that state is in-flight.
  func testIsInFlightCoversEveryCase() {
    XCTAssertEqual(ToolCallStatus.allCases.count, 5)
    XCTAssertEqual(
      ToolCallStatus.allCases.filter(\.isInFlight),
      [.running, .slow, .stalled]
    )
  }

  // MARK: - Stall tracking-id derivation

  /// The `StallDetector` registration site and the `applyStallTransitions`
  /// match site MUST derive a tool's tracking key the same way, or stall
  /// transitions for `toolUseId`-less tools are silently dropped. Both go
  /// through `ChatProvider.stallTrackingId`; this locks its contract.
  func testStallTrackingIdUsesToolUseIdWhenPresent() {
    XCTAssertEqual(
      ChatProvider.stallTrackingId(toolUseId: "abc123", name: "execute_sql"),
      "abc123"
    )
  }

  func testStallTrackingIdFallsBackToNameWhenToolUseIdMissing() {
    XCTAssertEqual(
      ChatProvider.stallTrackingId(toolUseId: nil, name: "execute_sql"),
      "untracked-execute_sql"
    )
  }

  // MARK: - Bridge status mapping

  func testBridgeTerminalFailureStatusesMapToFailed() {
    XCTAssertEqual(ChatProvider.mapBridgeToolStatus("failed"), .failed)
    XCTAssertEqual(ChatProvider.mapBridgeToolStatus("cancelled"), .failed)
    XCTAssertEqual(ChatProvider.mapBridgeToolStatus("interrupted"), .failed)
    XCTAssertEqual(ToolCallStatus.fromBridgeStatus("failed"), .failed)
    XCTAssertEqual(ToolCallStatus.fromBridgeStatus("cancelled"), .failed)
    XCTAssertEqual(ToolCallStatus.fromBridgeStatus("interrupted"), .failed)
  }

  func testBridgeStartedAndCompletedStatusesMapToExpectedStates() {
    XCTAssertEqual(ChatProvider.mapBridgeToolStatus("started"), .running)
    XCTAssertEqual(ChatProvider.mapBridgeToolStatus("completed"), .completed)
    XCTAssertEqual(ToolCallStatus.fromBridgeStatus("started"), .running)
    XCTAssertEqual(ToolCallStatus.fromBridgeStatus("completed"), .completed)
  }

  func testIntentionalStoppedErrorCompletesRemainingToolsWithoutFailureUI() {
    XCTAssertEqual(
      ChatProvider.remainingToolStatusAfterPartialResponseError(BridgeError.stopped),
      .completed
    )
  }

  func testBridgeFailuresMarkRemainingToolsFailed() {
    XCTAssertEqual(
      ChatProvider.remainingToolStatusAfterPartialResponseError(BridgeError.timeout),
      .failed
    )
  }

  func testSystemStopsAndFailedPreconditionsMarkRemainingToolsFailed() {
    XCTAssertEqual(
      ChatProvider.remainingToolStatusAfterPartialResponseError(
        BridgeError.stopped,
        watchdogFired: true
      ),
      .failed
    )
    XCTAssertEqual(
      ChatProvider.remainingToolStatusAfterPartialResponseError(
        BridgeError.stopped,
        toolStallAbortFired: true
      ),
      .failed
    )
    XCTAssertEqual(
      ChatProvider.remainingToolStatusAfterPartialResponseError(
        BridgeError.stopped,
        stopReason: .browserExtensionMissing
      ),
      .failed
    )
  }

  func testLateResultToolStatusPreservesTerminalTruth() {
    XCTAssertEqual(
      ChatProvider.lateResultToolStatus(watchdogFired: false, toolStallAbortFired: false),
      .completed
    )
    XCTAssertEqual(
      ChatProvider.lateResultToolStatus(watchdogFired: true, toolStallAbortFired: false),
      .failed
    )
    XCTAssertEqual(
      ChatProvider.lateResultToolStatus(watchdogFired: false, toolStallAbortFired: true),
      .failed
    )
    XCTAssertEqual(
      ChatProvider.lateResultToolStatus(
        watchdogFired: false,
        toolStallAbortFired: false,
        stopReason: .browserExtensionMissing
      ),
      .failed
    )
  }

  // MARK: - Tool-call content block lifecycle

  func testStreamingBufferPreservesTextBeforeToolOrder() {
    let messageId = "assistant-1"
    var messages = [ChatMessage(id: messageId, text: "", sender: .ai, isStreaming: true)]
    let buffer = ChatStreamingBuffer(flushInterval: 0.1)

    buffer.appendText(messageId: messageId, text: "Before tool.", scheduleFlush: {})
    buffer.applyToolActivity(
      messageId: messageId,
      toolName: "Bash",
      status: .running,
      toolUseId: "tool-1",
      input: ["command": "pwd"],
      messages: &messages
    )

    XCTAssertEqual(messages[0].contentBlocks.count, 2)
    guard case .text(_, "Before tool.") = messages[0].contentBlocks[0],
          case .toolCall(_, "Bash", .running, "tool-1", _, _) = messages[0].contentBlocks[1] else {
      return XCTFail("Expected text before the tool call")
    }
  }

  func testStreamingBufferPreservesThinkingBeforeTextOrder() {
    let messageId = "assistant-1"
    var messages = [ChatMessage(id: messageId, text: "", sender: .ai, isStreaming: true)]
    let buffer = ChatStreamingBuffer(flushInterval: 0.1)

    buffer.appendThinking(messageId: messageId, text: "Thinking.", scheduleFlush: {})
    buffer.appendText(messageId: messageId, text: "Answer.", scheduleFlush: {})
    buffer.flush(messages: &messages)

    XCTAssertEqual(messages[0].contentBlocks.count, 2)
    guard case .thinking(_, "Thinking.") = messages[0].contentBlocks[0],
          case .text(_, "Answer.") = messages[0].contentBlocks[1] else {
      return XCTFail("Expected thinking before answer text")
    }
  }

  func testStreamingBufferPreservesTextThinkingTextOrder() {
    let messageId = "assistant-1"
    var messages = [ChatMessage(id: messageId, text: "", sender: .ai, isStreaming: true)]
    let buffer = ChatStreamingBuffer(flushInterval: 0.1)

    buffer.appendText(messageId: messageId, text: "A", scheduleFlush: {})
    buffer.appendThinking(messageId: messageId, text: "B", scheduleFlush: {})
    buffer.appendText(messageId: messageId, text: "C", scheduleFlush: {})
    buffer.flush(messages: &messages)

    XCTAssertEqual(messages[0].text, "AC")
    XCTAssertEqual(messages[0].contentBlocks.count, 3)
    guard case .text(_, "A") = messages[0].contentBlocks[0],
          case .thinking(_, "B") = messages[0].contentBlocks[1],
          case .text(_, "C") = messages[0].contentBlocks[2] else {
      return XCTFail("Expected text, thinking, text block order")
    }
  }

  func testDiscardingRevokedTurnPreservesNewerTurnSegments() {
    var messages = [
      ChatMessage(id: "revoked", text: "", sender: .ai, isStreaming: true),
      ChatMessage(id: "current", text: "", sender: .ai, isStreaming: true),
    ]
    let buffer = ChatStreamingBuffer(flushInterval: 10)

    buffer.appendText(messageId: "revoked", text: "late output", scheduleFlush: {})
    buffer.appendText(messageId: "current", text: "current output", scheduleFlush: {})
    buffer.discardPendingSegments(messageId: "revoked")
    buffer.flush(messages: &messages)

    XCTAssertEqual(messages[0].text, "")
    XCTAssertEqual(messages[1].text, "current output")
  }

  func testManualFlushCancelsScheduledFlush() {
    let messageId = "assistant-1"
    var messages = [ChatMessage(id: messageId, text: "", sender: .ai, isStreaming: true)]
    let buffer = ChatStreamingBuffer(flushInterval: 0.01)
    let staleFlush = expectation(description: "scheduled flush should be cancelled by manual flush")
    staleFlush.isInverted = true

    buffer.appendText(messageId: messageId, text: "Before tool.", scheduleFlush: {
      staleFlush.fulfill()
    })
    buffer.flush(messages: &messages)

    wait(for: [staleFlush], timeout: 0.05)
    XCTAssertEqual(messages[0].text, "Before tool.")
  }

  func testDuplicateStartForSameToolUseIdUpdatesExistingBlock() {
    var blocks: [ChatContentBlock] = []

    ToolCallBlockUpdater.applyToolActivity(
      to: &blocks,
      toolName: "execute_sql",
      status: .running,
      toolUseId: "tool-1",
      input: ["query": "select 1"]
    )
    ToolCallBlockUpdater.applyToolActivity(
      to: &blocks,
      toolName: "execute_sql",
      status: .running,
      toolUseId: "tool-1",
      input: nil
    )

    XCTAssertEqual(blocks.count, 1)
    guard case .toolCall(_, let name, let status, let toolUseId, let input, _) = blocks[0] else {
      return XCTFail("Expected a tool-call block")
    }
    XCTAssertEqual(name, "execute_sql")
    XCTAssertEqual(status, .running)
    XCTAssertEqual(toolUseId, "tool-1")
    XCTAssertEqual(input?.summary, "select 1")
  }

  func testLateDuplicateStartForCompletedToolUseIdDoesNotReopenSpinner() {
    var blocks: [ChatContentBlock] = [
      .toolCall(id: "tool-block", name: "execute_sql", status: .completed, toolUseId: "tool-1", input: nil, output: nil)
    ]

    ToolCallBlockUpdater.applyToolActivity(
      to: &blocks,
      toolName: "execute_sql",
      status: .running,
      toolUseId: "tool-1",
      input: ["query": "select 1"]
    )

    XCTAssertEqual(blocks.count, 1)
    guard case .toolCall(_, _, let status, let toolUseId, let input, _) = blocks[0] else {
      return XCTFail("Expected a tool-call block")
    }
    XCTAssertEqual(status, .completed)
    XCTAssertEqual(toolUseId, "tool-1")
    XCTAssertEqual(input?.summary, "select 1")
  }

  func testDuplicateStartCanAttachLaterToolUseIdToUnidentifiedRunningBlock() {
    var blocks: [ChatContentBlock] = []

    ToolCallBlockUpdater.applyToolActivity(
      to: &blocks,
      toolName: "Bash",
      status: .running,
      toolUseId: nil,
      input: nil
    )
    ToolCallBlockUpdater.applyToolActivity(
      to: &blocks,
      toolName: "Bash",
      status: .running,
      toolUseId: "tool-2",
      input: ["command": "pwd"]
    )

    XCTAssertEqual(blocks.count, 1)
    guard case .toolCall(_, _, .running, let toolUseId, let input, _) = blocks[0] else {
      return XCTFail("Expected a running tool-call block")
    }
    XCTAssertEqual(toolUseId, "tool-2")
    XCTAssertEqual(input?.summary, "pwd")
  }

  func testCompletionMarksAllMatchingDuplicateInFlightBlocks() {
    var blocks: [ChatContentBlock] = [
      .toolCall(id: "old", name: "execute_sql", status: .running, toolUseId: "tool-3", input: nil, output: nil),
      .toolCall(id: "new", name: "execute_sql", status: .running, toolUseId: "tool-3", input: nil, output: nil),
    ]

    ToolCallBlockUpdater.applyToolActivity(
      to: &blocks,
      toolName: "execute_sql",
      status: .completed,
      toolUseId: "tool-3",
      input: nil
    )

    XCTAssertEqual(blocks.count, 2)
    for block in blocks {
      guard case .toolCall(_, _, let status, _, _, _) = block else {
        return XCTFail("Expected only tool-call blocks")
      }
      XCTAssertEqual(status, .completed)
    }
  }

  func testToolOutputUpdatesAllMatchingDuplicateBlocks() {
    var blocks: [ChatContentBlock] = [
      .toolCall(id: "old", name: "execute_sql", status: .completed, toolUseId: "tool-3", input: nil, output: nil),
      .toolCall(id: "new", name: "execute_sql", status: .completed, toolUseId: "tool-3", input: nil, output: nil),
    ]

    ToolCallBlockUpdater.applyToolOutput(
      to: &blocks,
      toolUseId: "tool-3",
      name: "execute_sql",
      output: "1 row(s)"
    )

    for block in blocks {
      guard case .toolCall(_, _, _, _, _, let output) = block else {
        return XCTFail("Expected only tool-call blocks")
      }
      XCTAssertEqual(output, "1 row(s)")
    }
  }

  func testChatResponseMetricsRecordsSqlStatsWithoutCapturedMutableState() {
    let metrics = ChatResponseMetrics()

    XCTAssertTrue(metrics.markFirstOutputIfNeeded())
    XCTAssertFalse(metrics.markFirstOutputIfNeeded())
    XCTAssertTrue(metrics.markGenerationStartedIfNeeded())
    XCTAssertFalse(metrics.markGenerationStartedIfNeeded())

    metrics.recordToolResult(name: "execute_sql", result: "ok\n3 row(s)")
    metrics.recordToolResult(name: "Bash", result: "ignored\n9 row(s)")

    let snapshot = metrics.snapshot()
    XCTAssertEqual(snapshot.sqlQueryCount, 1)
    XCTAssertEqual(snapshot.sqlRowsReturned, 3)
  }

  func testIdlessCompletionFallsBackToToolName() {
    var blocks: [ChatContentBlock] = [
      .toolCall(id: "known-id", name: "Bash", status: .running, toolUseId: "tool-4", input: nil, output: nil)
    ]

    ToolCallBlockUpdater.applyToolActivity(
      to: &blocks,
      toolName: "Bash",
      status: .completed,
      toolUseId: nil,
      input: nil
    )

    guard case .toolCall(_, _, let status, let toolUseId, _, _) = blocks[0] else {
      return XCTFail("Expected a tool-call block")
    }
    XCTAssertEqual(status, .completed)
    XCTAssertEqual(toolUseId, "tool-4")
  }
}
