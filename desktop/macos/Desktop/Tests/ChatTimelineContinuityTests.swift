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

  func testSourceInvariantAllChatSurfacesRenderCanonicalProviderMessages() throws {
    let root = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()

    let chatPage = try String(
      contentsOf: root.appendingPathComponent("Sources/MainWindow/Pages/ChatPage.swift"),
      encoding: .utf8)
    XCTAssertTrue(
      chatPage.contains("messages: chatProvider.messages,"),
      "main Chat page must render every Omi chat turn, including notch turns and subagent links"
    )
    XCTAssertFalse(
      chatPage.contains("transcriptMessages"),
      "main Chat page must not filter notch/PTT turns out of history"
    )
    XCTAssertTrue(
      chatPage.contains("FloatingControlBarManager.shared.openAgentChatFromTimeline(agentID: agentID)"),
      "main Chat page must open spawned-agent links from tool rows"
    )

    let dashboard = try String(
      contentsOf: root.appendingPathComponent("Sources/MainWindow/Pages/DashboardPage.swift"),
      encoding: .utf8)
    XCTAssertEqual(
      dashboard.components(separatedBy: "messages: chatProvider.messages,").count - 1,
      2,
      "both dashboard Home chat surfaces must render the canonical provider timeline"
    )
    XCTAssertFalse(
      dashboard.contains("transcriptMessages"),
      "Home chat must not filter notch/PTT turns out of history"
    )
    XCTAssertEqual(
      dashboard.components(separatedBy: "FloatingControlBarManager.shared.openAgentChatFromTimeline(agentID: agentID)").count - 1,
      2,
      "both dashboard Home chat surfaces must open spawned-agent links from tool rows"
    )

    let provider = try String(
      contentsOf: root.appendingPathComponent("Sources/Providers/ChatProvider.swift"),
      encoding: .utf8)
    XCTAssertFalse(
      provider.contains("transcriptMessages"),
      "ChatProvider must not expose split transcript filtering for main vs notch chat"
    )
    XCTAssertTrue(
      provider.contains("automationFloatingChatSnapshot(limit: Int) -> [String: String]"),
      "floating-bar harness snapshot must stay available"
    )
    XCTAssertTrue(
      provider.contains("automationChatSnapshot(limit: limit)"),
      "main and floating snapshots must read the same canonical timeline"
    )

    let floating = try String(
      contentsOf: root.appendingPathComponent("Sources/FloatingControlBar/FloatingControlBarWindow.swift"),
      encoding: .utf8)
    let chatBubble = try String(
      contentsOf: root.appendingPathComponent("Sources/MainWindow/Components/ChatBubble.swift"),
      encoding: .utf8)
    let floatingView = try String(
      contentsOf: root.appendingPathComponent("Sources/FloatingControlBar/FloatingControlBarView.swift"),
      encoding: .utf8)
    XCTAssertTrue(
      floating.contains("return provider.automationFloatingChatSnapshot(limit: limit)"),
      "notch harness should still inspect floating chat through its named surface action"
    )
    XCTAssertTrue(
      floating.contains("func openAgentChatFromTimeline(agentID: UUID)"),
      "main chat needs a manager entrypoint to open spawned-agent links in the floating surface"
    )
    XCTAssertTrue(
      chatBubble.contains("ContentBlockGroup.visibleChatGroups("),
      "main chat bubbles must filter completed implementation-only tool logs"
    )
    XCTAssertTrue(
      chatBubble.contains("return .toolCalls(id: id, calls: spawnedAgentCalls)"),
      "main chat bubbles must still render spawned-agent links after the final answer"
    )
    XCTAssertTrue(
      chatBubble.contains("ToolCallsGroup(calls: calls, onCancel: onCancelTurn, onOpenAgent: onOpenAgent)"),
      "main chat bubbles must pass spawned-agent link callbacks into visible tool-call groups"
    )
    XCTAssertTrue(
      floatingView.contains("onOpenAgent: { agentID in"),
      "notch response view must keep opening spawned-agent links"
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
