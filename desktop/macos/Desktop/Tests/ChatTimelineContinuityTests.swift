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

  func testAgentIdentityBlocksSurviveSaveMessageMetadataRoundTrip() {
    let pillId = UUID()
    let spawn = ChatContentBlock.agentSpawn(
      id: "spawn-1",
      pillId: pillId,
      sessionId: "sess-spawn",
      runId: "run-spawn",
      title: "Sleep Agent",
      objective: "sleep five seconds"
    )
    let completion = ChatContentBlock.agentCompletion(
      id: "completion-1",
      pillId: pillId,
      sessionId: "sess-spawn",
      runId: "run-spawn",
      title: "Sleep Agent",
      promptSnippet: "sleep five seconds",
      output: "Done.",
      status: "completed"
    )

    let metadata = ChatContentBlockCodec.mergeIntoMessageMetadata(
      nil,
      contentBlocks: [spawn, completion]
    )
    XCTAssertNotNil(metadata)
    XCTAssertTrue(metadata?.contains(ChatContentBlockCodec.messageMetadataKey) == true)

    let restored = ChatContentBlockCodec.decodeFromMessageMetadata(metadata)
    XCTAssertEqual(restored.count, 2)
    guard case .agentSpawn(_, let spawnPill, let spawnSession, let spawnRun, let title, let objective) =
      restored[0]
    else {
      return XCTFail("expected agentSpawn in metadata round-trip")
    }
    XCTAssertEqual(spawnPill, pillId)
    XCTAssertEqual(spawnSession, "sess-spawn")
    XCTAssertEqual(spawnRun, "run-spawn")
    XCTAssertEqual(title, "Sleep Agent")
    XCTAssertEqual(objective, "sleep five seconds")

    guard case .agentCompletion(_, let donePill, _, let doneRun, _, _, let output, _) = restored[1]
    else {
      return XCTFail("expected agentCompletion in metadata round-trip")
    }
    XCTAssertEqual(donePill, pillId)
    XCTAssertEqual(doneRun, "run-spawn")
    XCTAssertEqual(output, "Done.")

    // Reload path used by ChatMessage(from:): hydrate content_blocks from metadata.
    let hydrated = ChatMessage(
      id: "server-msg-1",
      text: "Done.",
      sender: .ai,
      contentBlocks: ChatContentBlockCodec.decodeFromMessageMetadata(metadata)
    )
    XCTAssertEqual(hydrated.contentBlocks.count, 2)
    XCTAssertEqual(hydrated.contentBlocks.spawnedAgentIDs, [pillId, pillId])
  }

  func testMaterializeAgentSpawnBlockFromSpawnToolResult() {
    let pillId = UUID()
    var blocks: [ChatContentBlock] = [
      .toolCall(
        id: "tool_1",
        name: "spawn_agent",
        status: .completed,
        toolUseId: "tu-1",
        input: ToolCallInput(summary: "Sleep Agent", details: "sleep five seconds"),
        output: """
        Agent started as a floating agent pill.
        id: \(pillId.uuidString)
        sessionId: sess-abc
        runId: run-xyz
        title: Sleep Agent
        status: running
        """
      )
    ]

    ChatProvider.materializeAgentSpawnBlockIfNeeded(
      in: &blocks,
      toolUseId: "tu-1",
      toolName: "spawn_agent"
    )
    XCTAssertEqual(blocks.count, 2)
    guard case .agentSpawn(_, let spawnPill, let sessionId, let runId, let title, let objective) =
      blocks[1]
    else {
      return XCTFail("spawn_agent tool result must emit .agentSpawn")
    }
    XCTAssertEqual(spawnPill, pillId)
    XCTAssertEqual(sessionId, "sess-abc")
    XCTAssertEqual(runId, "run-xyz")
    XCTAssertEqual(title, "Sleep Agent")
    XCTAssertEqual(objective, "sleep five seconds")

    // Idempotent on repeat apply.
    ChatProvider.materializeAgentSpawnBlockIfNeeded(
      in: &blocks,
      toolUseId: "tu-1",
      toolName: "spawn_agent"
    )
    XCTAssertEqual(blocks.count, 2)

    // Structured spawn card is the single visible entrypoint (tool link hidden).
    let groups = ContentBlockGroup.visibleChatGroups(blocks, isStreaming: false)
    XCTAssertEqual(groups.count, 1)
    guard case .agentSpawn(_, let visiblePill, _, let visibleRun, _, _) = groups[0] else {
      return XCTFail("expected only agentSpawn card after materialize, got \(groups)")
    }
    XCTAssertEqual(visiblePill, pillId)
    XCTAssertEqual(visibleRun, "run-xyz")
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

  func testLinkOutHiddenWhenUnavailableOrMissingOpenAction() {
    XCTAssertTrue(
      AgentTimelineOpenFeedback.shouldShowLinkOut(
        hasResolvableAgent: true,
        hasOpenAction: true,
        showUnavailable: false
      )
    )
    XCTAssertFalse(
      AgentTimelineOpenFeedback.shouldShowLinkOut(
        hasResolvableAgent: true,
        hasOpenAction: true,
        showUnavailable: true
      ),
      "hide link-out after open failed / unavailable"
    )
    XCTAssertFalse(
      AgentTimelineOpenFeedback.shouldShowLinkOut(
        hasResolvableAgent: false,
        hasOpenAction: true,
        showUnavailable: false
      )
    )
    XCTAssertFalse(
      AgentTimelineOpenFeedback.shouldShowLinkOut(
        hasResolvableAgent: true,
        hasOpenAction: false,
        showUnavailable: false
      )
    )
  }

  func testBackgroundAgentCardsSeparateExpandFromLinkOut() throws {
    let root = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
    let chatBubbleSource = try String(
      contentsOf: root.appendingPathComponent("Sources/MainWindow/Components/ChatBubble.swift"),
      encoding: .utf8
    )

    XCTAssertTrue(
      chatBubbleSource.contains("SelectableMarkdown(text: summary.output, sender: .ai)"),
      "background agent summary body must render markdown"
    )
    XCTAssertTrue(
      chatBubbleSource.contains("SelectableMarkdown(text: output, sender: .ai)"),
      "agent completion body must render markdown"
    )
    XCTAssertTrue(chatBubbleSource.contains("Text(\"Collapse\")"))
    XCTAssertTrue(
      chatBubbleSource.contains("AgentTimelineOpenFeedback.shouldShowLinkOut("),
      "cards must gate link-out with shared policy"
    )
    XCTAssertFalse(
      chatBubbleSource.contains(
        "Image(systemName: summary.agentID != nil && onOpenAgent != nil ? \"arrow.up.forward.app\""
      ),
      "header must not replace expand chevron with link-out"
    )
    XCTAssertFalse(
      chatBubbleSource.contains(
        "Image(systemName: ref.hasIdentity && onOpen != nil ? \"arrow.up.forward.app\""
      ),
      "completion header must not replace expand chevron with link-out"
    )
    XCTAssertFalse(
      chatBubbleSource.contains(
        "Image(systemName: canOpenSpawnedAgent ? \"arrow.up.forward.app\" : (isExpanded ? \"chevron.up\" : \"chevron.down\")"
      ),
      "tool-call headers must keep expand chevron separate from link-out"
    )
  }

  func testChatSelectionDoesNotWrapStackChromeInSelectionOverlay() throws {
    // Mechanical guard for the omi-chat-continuity main-thread freeze:
    // ChatMessagesView used to apply `.textSelection(.enabled)` on the LazyVStack,
    // wrapping every agent-card header Text in SelectionOverlay and thrashing
    // GraphHost via setFont → invalidateIntrinsicContentSize.
    let root = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()

    let messagesSource = try String(
      contentsOf: root.appendingPathComponent("Sources/MainWindow/Components/ChatMessagesView.swift"),
      encoding: .utf8
    )
    let markdownSource = try String(
      contentsOf: root.appendingPathComponent("Sources/MainWindow/Components/SelectableMarkdown.swift"),
      encoding: .utf8
    )
    let bubbleSource = try String(
      contentsOf: root.appendingPathComponent("Sources/MainWindow/Components/ChatBubble.swift"),
      encoding: .utf8
    )

    XCTAssertFalse(
      messagesSource.contains(".textSelection(.enabled)"),
      "chat message stack must not enable selection on chrome Text views"
    )
    XCTAssertTrue(
      markdownSource.contains(".textSelection(.enabled)"),
      "SelectableMarkdown must opt message bodies into selection"
    )
    XCTAssertTrue(
      bubbleSource.contains(".textSelection(.disabled)"),
      "agent card headers must disable SelectionOverlay on truncated snippets"
    )
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

    let floatingState = try String(
      contentsOf: root.appendingPathComponent("Sources/FloatingControlBar/FloatingControlBarState.swift"),
      encoding: .utf8)
    XCTAssertTrue(
      floatingState.contains("struct FloatingChatViewport"),
      "floating bar must keep a viewport cursor over ChatProvider.messages"
    )
    XCTAssertTrue(
      floatingState.contains("func currentAIMessage(from provider: ChatProvider?)"),
      "floating answer must resolve from provider messages by id"
    )
    XCTAssertTrue(
      floatingState.contains("if let answerId = chatViewport.answerMessageId,"),
      "currentAIMessage must prefer provider-bound answerMessageId over localAnswerOverride"
    )
    let answerIdPreferIndex = floatingState.range(of: "if let answerId = chatViewport.answerMessageId,")?.lowerBound
    let overrideFallbackIndex = floatingState.range(of: "if let localAnswerOverride { return localAnswerOverride }")?.lowerBound
    XCTAssertNotNil(answerIdPreferIndex)
    XCTAssertNotNil(overrideFallbackIndex)
    if let answerIdPreferIndex, let overrideFallbackIndex {
      XCTAssertLessThan(
        answerIdPreferIndex,
        overrideFallbackIndex,
        "provider-bound answer must be checked before localAnswerOverride"
      )
    }
    XCTAssertFalse(
      floatingState.contains("@Published var chatHistory"),
      "floating bar must not own a durable chatHistory transcript array"
    )
    XCTAssertFalse(
      floatingState.contains("@Published var currentAIMessage"),
      "floating bar must not store currentAIMessage as content ownership"
    )

    let provider = try String(
      contentsOf: root.appendingPathComponent("Sources/Providers/ChatProvider.swift"),
      encoding: .utf8)
    XCTAssertFalse(
      provider.contains("func transcriptMessages"),
      "ChatProvider must not expose a split transcript filter API"
    )
  }

  /// INV-6: collapsed agent-card / list preview = prompt/objective, not response output.
  func testAgentPreviewTextPrefersPromptOverOutput() {
    XCTAssertEqual(
      ChatContinuityInvariants.agentPreviewText(prompt: "sleep five seconds", output: "Done."),
      "sleep five seconds"
    )
    XCTAssertEqual(
      ChatContinuityInvariants.agentPreviewText(prompt: "  ", output: "Done."),
      "Done."
    )
    XCTAssertEqual(
      ChatContinuityInvariants.agentPreviewText(prompt: "", output: "  only output  "),
      "only output"
    )
  }

  func testAgentCompletionCardsUsePromptPreviewHelper() throws {
    let root = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
    let bubble = try String(
      contentsOf: root.appendingPathComponent("Sources/MainWindow/Components/ChatBubble.swift"),
      encoding: .utf8
    )
    let floating = try String(
      contentsOf: root.appendingPathComponent("Sources/FloatingControlBar/FloatingControlBarView.swift"),
      encoding: .utf8
    )

    XCTAssertTrue(
      bubble.contains("ChatContinuityInvariants.agentPreviewText(prompt: promptSnippet, output: output)"),
      "AgentCompletionCard header must preview promptSnippet, not raw output"
    )
    XCTAssertTrue(
      bubble.contains("ChatContinuityInvariants.agentPreviewText(prompt: summary.prompt, output: summary.output)"),
      "BackgroundAgentCard header must preview prompt, not raw output"
    )
    XCTAssertTrue(
      floating.contains("ChatContinuityInvariants.agentPreviewText(")
        && floating.contains("prompt: pill.query")
        && floating.contains("output: pill.latestActivity"),
      "agent list rows must preview query/objective via agentPreviewText"
    )

    let aiResponse = try String(
      contentsOf: root.appendingPathComponent("Sources/FloatingControlBar/AIResponseView.swift"),
      encoding: .utf8
    )
    XCTAssertTrue(
      aiResponse.contains("AgentCompletionCard("),
      "notch must render AgentCompletionCard so artifacts stay attached to the turn"
    )
    XCTAssertFalse(
      aiResponse.contains("case .agentSpawn, .agentCompletion:\n                    EmptyView()"),
      "notch must not EmptyView agentCompletion while still showing resources"
    )
  }

  /// INV-6: floating resource strips bind per-message displayResources only —
  /// never flatMap the whole provider timeline (orphan historical artifacts).
  func testFloatingResourceStripsBindPerMessageNotProviderWide() throws {
    let root = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
    let aiResponse = try String(
      contentsOf: root.appendingPathComponent("Sources/FloatingControlBar/AIResponseView.swift"),
      encoding: .utf8
    )
    let floatingView = try String(
      contentsOf: root.appendingPathComponent("Sources/FloatingControlBar/FloatingControlBarView.swift"),
      encoding: .utf8
    )
    let floatingState = try String(
      contentsOf: root.appendingPathComponent("Sources/FloatingControlBar/FloatingControlBarState.swift"),
      encoding: .utf8
    )

    XCTAssertTrue(aiResponse.contains("resources: message.displayResources"))
    XCTAssertTrue(floatingView.contains("resources: message.displayResources"))
    XCTAssertFalse(
      aiResponse.contains("provider.messages") && aiResponse.contains(".resources"),
      "AIResponseView must not read provider-wide resources"
    )
    XCTAssertTrue(
      floatingState.contains("func viewportDisplayResources(from provider: ChatProvider?)"),
      "viewport orphan filter helper must remain available for aggregate strips"
    )
    XCTAssertTrue(
      floatingState.contains("ChatContinuityInvariants.resourcesBelongingToMessages"),
      "viewportDisplayResources must filter by viewport message ids"
    )
  }

  /// INV-6 forbidden dual-write / multi-handler patterns — mechanical tripwires.
  func testForbiddenContinuityPatternsAbsentFromWritePath() throws {
    let root = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()

    let hub = try String(
      contentsOf: root.appendingPathComponent("Sources/FloatingControlBar/RealtimeHubController.swift"),
      encoding: .utf8
    )
    let runtime = try String(
      contentsOf: root.appendingPathComponent("Sources/Chat/AgentRuntimeProcess.swift"),
      encoding: .utf8
    )
    let bridge = try String(
      contentsOf: root.appendingPathComponent("Sources/Chat/AgentBridge.swift"),
      encoding: .utf8
    )
    let floatingState = try String(
      contentsOf: root.appendingPathComponent("Sources/FloatingControlBar/FloatingControlBarState.swift"),
      encoding: .utf8
    )
    let provider = try String(
      contentsOf: root.appendingPathComponent("Sources/Providers/ChatProvider.swift"),
      encoding: .utf8
    )
    let window = try String(
      contentsOf: root.appendingPathComponent("Sources/FloatingControlBar/FloatingControlBarWindow.swift"),
      encoding: .utf8
    )

    XCTAssertTrue(hub.contains("ChatProvider.mainInstance"))
    XCTAssertFalse(hub.contains("warmProvider = ChatProvider()"))
    XCTAssertFalse(hub.contains("private var warmProvider"))
    XCTAssertFalse(
      hub.contains("ChatProvider()"),
      "speculative warm must not construct a second ChatProvider"
    )

    XCTAssertFalse(runtime.contains("addTurnRecordedHandler"))
    XCTAssertFalse(bridge.contains("addTurnRecordedHandler"))
    XCTAssertTrue(runtime.contains("func setTurnRecordedHandler"))
    XCTAssertTrue(bridge.contains("Single-slot replace"))

    for source in [hub, runtime, bridge, floatingState, provider, window] {
      XCTAssertFalse(
        source.contains("suppressNextRecordedTurn"),
        "dual-write bandage suppressNextRecordedTurn is forbidden"
      )
    }

    XCTAssertFalse(floatingState.contains("@Published var chatHistory"))
  }
}

private extension Array where Element == ChatContentBlock {
  var spawnedAgentIDs: [UUID] {
    compactMap { block in
      block.spawnedAgentID
    }
  }
}
