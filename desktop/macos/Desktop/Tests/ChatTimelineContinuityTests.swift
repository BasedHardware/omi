import XCTest

@testable import Omi_Computer

/// Omi chat is one canonical timeline. Main chat, Home chat, and the notch
/// floating-bar chat must all show typed notch turns, notch PTT turns, and
/// assistant tool blocks that link to spawned subagents.
final class ChatTimelineContinuityTests: XCTestCase {

  private func msg(_ text: String, sender: ChatSender, owner: ChatTurnOwner?) -> ChatMessage {
    ChatMessage(text: text, sender: sender, turnOwner: owner)
  }

  func testCanonicalTimelineIncludesMainNotchVoiceAndSubagentTurns() {
    let subagentID = UUID()
    let messages = [
      msg("main question", sender: .user, owner: .mainChat),
      msg("typed notch question", sender: .user, owner: .floatingDefault),
      msg("notch ptt question", sender: .user, owner: .floatingVoice),
      ChatMessage(
        text: "",
        sender: .ai,
        contentBlocks: [
          .toolCall(
            id: "tool_1",
            name: "spawn_agent",
            status: .completed,
            output: "Started agent\nID: \(subagentID.uuidString)"
          )
        ],
        turnOwner: .floatingDefault
      ),
    ]

    XCTAssertEqual(
      messages.map(\.text),
      ["main question", "typed notch question", "notch ptt question", ""]
    )
    XCTAssertEqual(messages[3].contentBlocks.spawnedAgentIDs, [subagentID])
  }

  func testMainChatHidesCompletedNonAgentToolLogsButKeepsAgentLinks() {
    let subagentID = UUID()
    let groups = ContentBlockGroup.visibleChatGroups(
      [
        .text(id: "text_1", text: "I started a background agent for that."),
        .toolCall(
          id: "tool_1",
          name: "search_conversations",
          status: .completed,
          input: ToolCallInput(summary: "designer", details: "query=designer"),
          output: "raw search output"
        ),
        .toolCall(
          id: "tool_2",
          name: "spawn_agent",
          status: .completed,
          input: ToolCallInput(summary: "Sleep Agent", details: "sleep five seconds"),
          output: "Started agent\nID: \(subagentID.uuidString)"
        ),
        .thinking(id: "thinking_1", text: "hidden after completion"),
      ],
      isStreaming: false
    )

    XCTAssertEqual(groups.count, 2)
    guard case .text(_, let text) = groups[0] else {
      return XCTFail("expected final assistant text to remain visible")
    }
    XCTAssertEqual(text, "I started a background agent for that.")
    guard case .toolCalls(_, let calls) = groups[1] else {
      return XCTFail("expected a spawned-agent link group")
    }
    XCTAssertEqual(calls.count, 1)
    XCTAssertEqual(calls.spawnedAgentIDs, [subagentID])
  }

  func testMainChatKeepsOnlyInFlightNonAgentToolsWhileStreaming() {
    let groups = ContentBlockGroup.visibleChatGroups(
      [
        .toolCall(id: "tool_1", name: "search_conversations", status: .completed, output: "done"),
        .toolCall(id: "tool_2", name: "execute_sql", status: .running, output: nil),
      ],
      isStreaming: true
    )

    XCTAssertEqual(groups.count, 1)
    guard case .toolCalls(_, let calls) = groups[0],
          case .toolCall(_, let name, let status, _, _, _) = calls[0]
    else {
      return XCTFail("expected only the active progress tool")
    }
    XCTAssertEqual(calls.count, 1)
    XCTAssertEqual(name, "execute_sql")
    XCTAssertEqual(status, .running)
  }

  func testBackgroundAgentSummaryParsesLinkedAndLegacyCompletionText() {
    let subagentID = UUID()
    let linked = BackgroundAgentSummary.parse(
      "[Background agent id=\(subagentID.uuidString) — sleep for one second] Done."
    )

    XCTAssertEqual(linked?.agentID, subagentID)
    XCTAssertEqual(linked?.prompt, "sleep for one second")
    XCTAssertEqual(linked?.output, "Done.")

    let legacy = BackgroundAgentSummary.parse(
      "[Background agent — tell a joke] Why don't scientists trust atoms?"
    )

    XCTAssertNil(legacy?.agentID)
    XCTAssertEqual(legacy?.prompt, "tell a joke")
    XCTAssertEqual(legacy?.output, "Why don't scientists trust atoms?")
  }

  func testAgentCompletionBlockExposesOpenRefAndStaysVisible() {
    let pillId = UUID()
    let block = ChatContentBlock.agentCompletion(
      id: "completion-1",
      pillId: pillId,
      sessionId: "sess-1",
      runId: "run-1",
      title: "Background agent",
      promptSnippet: "sleep",
      output: "Done.",
      status: "completed"
    )

    XCTAssertEqual(
      block.agentTimelineRef,
      AgentTimelineRef(pillId: pillId, sessionId: "sess-1", runId: "run-1")
    )
    XCTAssertEqual(
      AgentTimelineHydratePreference.make(pillId: pillId, sessionId: "sess-1", runId: "run-1").keys,
      [.runId("run-1"), .sessionId("sess-1"), .pillId(pillId)]
    )

    let groups = ContentBlockGroup.visibleChatGroups([block], isStreaming: false)
    XCTAssertEqual(groups.count, 1)
    guard case .agentCompletion(_, let visiblePill, let sessionId, let runId, _, _, let output, _) = groups[0]
    else {
      return XCTFail("expected agentCompletion to remain visible")
    }
    XCTAssertEqual(visiblePill, pillId)
    XCTAssertEqual(sessionId, "sess-1")
    XCTAssertEqual(runId, "run-1")
    XCTAssertEqual(output, "Done.")

    let message = ChatMessage(text: "Done.", sender: .ai, contentBlocks: [block])
    let record = TaskChatMessageRecord.from(message, taskId: "task-roundtrip")
    let restored = record.toChatMessage()
    XCTAssertEqual(restored.contentBlocks.count, 1)
    guard case .agentCompletion(_, let restoredPill, let restoredSession, let restoredRun, _, _, let restoredOutput, _) =
      restored.contentBlocks.first
    else {
      return XCTFail("agentCompletion must round-trip through contentBlocksJson")
    }
    XCTAssertEqual(restoredPill, pillId)
    XCTAssertEqual(restoredSession, "sess-1")
    XCTAssertEqual(restoredRun, "run-1")
    XCTAssertEqual(restoredOutput, "Done.")
  }

  func testSpawnToolOutputParsesSessionAndRunIds() {
    let pillId = UUID()
    let block = ChatContentBlock.toolCall(
      id: "tool_1",
      name: "spawn_agent",
      status: .completed,
      output: """
      Agent started as a floating agent pill.
      id: \(pillId.uuidString)
      sessionId: sess-abc
      runId: run-xyz
      title: Sleep Agent
      status: running
      """
    )

    XCTAssertEqual(block.spawnedAgentID, pillId)
    XCTAssertEqual(block.spawnedAgentSessionID, "sess-abc")
    XCTAssertEqual(block.spawnedAgentRunID, "run-xyz")
    XCTAssertEqual(
      block.agentOpenRef,
      AgentTimelineRef(pillId: pillId, sessionId: "sess-abc", runId: "run-xyz")
    )
  }

  func testHydratePreferencePrefersRunThenSessionThenPill() {
    let pillId = UUID()
    let preference = AgentTimelineHydratePreference.make(
      pillId: pillId,
      sessionId: " sess-1 ",
      runId: "run-1"
    )
    XCTAssertEqual(preference.keys, [
      .runId("run-1"),
      .sessionId("sess-1"),
      .pillId(pillId),
    ])

    let pillOnly = AgentTimelineHydratePreference.make(
      pillId: pillId,
      sessionId: nil,
      runId: "  "
    )
    XCTAssertEqual(pillOnly.keys, [.pillId(pillId)])

    // Behavioral: firstMatchingKey walks run → session → pill and stops early.
    XCTAssertEqual(
      preference.firstMatchingKey(
        runIdMatches: { $0 == "run-1" },
        sessionIdMatches: { _ in XCTFail("session should not be checked after run match"); return false },
        pillIdMatches: { _ in XCTFail("pill should not be checked after run match"); return false }
      ),
      .runId("run-1")
    )
    XCTAssertEqual(
      preference.firstMatchingKey(
        runIdMatches: { _ in false },
        sessionIdMatches: { $0 == "sess-1" },
        pillIdMatches: { _ in XCTFail("pill should not be checked after session match"); return false }
      ),
      .sessionId("sess-1")
    )
    XCTAssertEqual(
      preference.firstMatchingKey(
        runIdMatches: { _ in false },
        sessionIdMatches: { _ in false },
        pillIdMatches: { $0 == pillId }
      ),
      .pillId(pillId)
    )
  }

  @MainActor
  func testFindPillMatchesByHydratePreferenceOrder() {
    let runPill = AgentPill(id: UUID(), query: "by-run", model: "test")
    runPill.canonicalRunId = "run-match"
    runPill.canonicalSessionId = "sess-other"

    let sessionPill = AgentPill(id: UUID(), query: "by-session", model: "test")
    sessionPill.canonicalSessionId = "sess-match"

    let pillId = UUID()
    let idPill = AgentPill(id: pillId, query: "by-id", model: "test")

    let manager = AgentPillsManager.shared
    let previous = manager.pills
    defer { manager.replacePillsForTesting(previous) }
    manager.replacePillsForTesting([runPill, sessionPill, idPill])

    XCTAssertEqual(
      manager.findPill(
        matching: .make(pillId: pillId, sessionId: "sess-match", runId: "run-match")
      )?.id,
      runPill.id,
      "runId must win over sessionId and pillId"
    )
    XCTAssertEqual(
      manager.findPill(
        matching: .make(pillId: pillId, sessionId: "sess-match", runId: "missing-run")
      )?.id,
      sessionPill.id,
      "sessionId must win over pillId when run misses"
    )
    XCTAssertEqual(
      manager.findPill(
        matching: .make(pillId: pillId, sessionId: "missing-sess", runId: nil)
      )?.id,
      pillId
    )
    XCTAssertNil(
      manager.findPill(
        matching: .make(pillId: UUID(), sessionId: "nope", runId: "nope")
      )
    )
  }

  func testOpenFeedbackMarksUnavailableOnFailure() {
    XCTAssertTrue(AgentTimelineOpenFeedback.shouldShowUnavailable(succeeded: false))
    XCTAssertFalse(AgentTimelineOpenFeedback.shouldShowUnavailable(succeeded: true))
  }

  func testCanonicalSurfacesBindSharedProviderMessages() throws {
    // Mechanical single-provider UI binding check (INV-6 rule 1). Full UI
    // rendering is covered by e2e; this fails if Main/Home stop binding the
    // shared ChatProvider timeline or reintroduce transcript filtering.
    let root = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()

    let chatPage = try String(
      contentsOf: root.appendingPathComponent("Sources/MainWindow/Pages/ChatPage.swift"),
      encoding: .utf8)
    XCTAssertTrue(
      chatPage.contains("messages: chatProvider.messages,"),
      "main Chat must bind the shared ChatProvider timeline"
    )
    XCTAssertFalse(
      chatPage.contains("transcriptMessages"),
      "main Chat must not filter notch/PTT turns out of history"
    )
    XCTAssertTrue(
      chatPage.contains("openAgentChatFromTimeline(agentID: agentID, completion: completion)"),
      "main Chat must open spawned-agent links from the timeline with open result feedback"
    )
    XCTAssertTrue(
      chatPage.contains("openAgentChatFromTimeline(ref: ref, completion: completion)"),
      "main Chat must open structured agent refs with open result feedback"
    )

    let dashboard = try String(
      contentsOf: root.appendingPathComponent("Sources/MainWindow/Pages/DashboardPage.swift"),
      encoding: .utf8)
    XCTAssertGreaterThanOrEqual(
      dashboard.components(separatedBy: "messages: chatProvider.messages,").count - 1,
      2,
      "Home chat surfaces must bind the shared ChatProvider timeline"
    )
    XCTAssertFalse(
      dashboard.contains("transcriptMessages"),
      "Home chat must not filter notch/PTT turns out of history"
    )

    let provider = try String(
      contentsOf: root.appendingPathComponent("Sources/Providers/ChatProvider.swift"),
      encoding: .utf8)
    XCTAssertFalse(
      provider.contains("func transcriptMessages"),
      "ChatProvider must not expose a split transcript filter API"
    )
  }
}

private extension Array where Element == ChatContentBlock {
  var spawnedAgentIDs: [UUID] {
    compactMap { block in
      block.spawnedAgentID
    }
  }
}
