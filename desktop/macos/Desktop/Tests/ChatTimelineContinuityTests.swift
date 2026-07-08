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
      chatPage.contains("openAgentChatFromTimeline(agentID:"),
      "main Chat must open spawned-agent links from the timeline"
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
