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
      chatBubble.contains("ToolCallsGroup(calls: calls, onCancel: onCancelTurn, onOpenAgent: onOpenAgent)"),
      "main chat bubbles must pass spawned-agent link callbacks into tool-call groups"
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
