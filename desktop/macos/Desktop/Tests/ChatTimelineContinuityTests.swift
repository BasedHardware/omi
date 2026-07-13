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

  func testLifecycleProjectionHidesDuplicateSpawnProseAndRetainsCanonicalRunIdentity() {
    let pillID = UUID()
    let runID = "run_5f35b43bf8a646f29b548a1306cf663f"
    let spawnProse = """
    Subagent spawned! It's running as a floating pill titled \"Sleep 5 seconds\" (\(runID)).
    It'll execute sleep 5 and report back once complete.
    """
    let canonical = ChatMessage(
      id: "spawn-message",
      text: spawnProse,
      sender: .ai,
      contentBlocks: [
        .text(id: "assistant-spawn-prose", text: spawnProse),
        .agentSpawn(
          id: "spawn-block",
          pillId: pillID,
          sessionId: "session_123",
          runId: runID,
          title: "Sleep 5 seconds",
          objective: "Sleep for 5 seconds, then report completion."
        ),
      ]
    )

    let projected = AgentLifecycleDisplayProjection.project([canonical])

    // Projection must not mutate durable lifecycle facts used by recovery and
    // notch-pill linking.
    XCTAssertEqual(canonical.text, spawnProse)
    guard case .text(_, let canonicalProse) = canonical.contentBlocks[0],
          case .agentSpawn(_, let canonicalPillID, let canonicalSessionID, let canonicalRunID, _, _) =
            canonical.contentBlocks[1]
    else {
      return XCTFail("expected canonical spawn prose and structured receipt")
    }
    XCTAssertEqual(canonicalProse, spawnProse)
    XCTAssertEqual(canonicalPillID, pillID)
    XCTAssertEqual(canonicalSessionID, "session_123")
    XCTAssertEqual(canonicalRunID, runID)

    XCTAssertEqual(projected.count, 1)
    XCTAssertTrue(projected[0].text.isEmpty)
    XCTAssertFalse(projected[0].copyableText.contains(runID))
    let visibleGroups = ContentBlockGroup.visibleChatGroups(
      projected[0].contentBlocks,
      isStreaming: false
    )
    XCTAssertEqual(visibleGroups.count, 1)
    guard case .agentSpawn(_, let renderedPillID, let renderedSessionID, let renderedRunID, _, _) = visibleGroups[0]
    else {
      return XCTFail("only the structured spawn card should remain visible")
    }
    XCTAssertEqual(renderedPillID, pillID)
    XCTAssertEqual(renderedSessionID, "session_123")
    XCTAssertEqual(renderedRunID, runID)
  }

  func testLifecycleProjectionRedactsOnlyKnownIdentifiersFromNonLaunchAssistantText() {
    let runID = "run_internal_123"
    let userSuppliedCode = "run_public_example"
    let canonical = ChatMessage(
      text: "The lifecycle handle is \(runID); keep \(userSuppliedCode) unchanged.",
      sender: .ai,
      contentBlocks: [
        .agentCompletion(
          id: "completion-block",
          pillId: nil,
          sessionId: nil,
          runId: runID,
          title: "Background agent",
          promptSnippet: "",
          output: "Done.",
          status: "completed"
        ),
      ]
    )

    let projected = AgentLifecycleDisplayProjection.project([canonical])

    XCTAssertFalse(projected[0].text.contains(runID))
    XCTAssertTrue(projected[0].text.contains(userSuppliedCode))
    XCTAssertEqual(canonical.text, "The lifecycle handle is \(runID); keep \(userSuppliedCode) unchanged.")
  }

  func testLifecycleProjectionHidesDuplicateSpawnProseWithoutLegacyIdentifiers() {
    let spawnProse = "Subagent spawned! It is running as a floating pill titled Sleep 5 seconds."
    let canonical = ChatMessage(
      text: spawnProse,
      sender: .ai,
      contentBlocks: [
        .text(id: "assistant-spawn-prose", text: spawnProse),
        .agentSpawn(
          id: "legacy-spawn-block",
          pillId: nil,
          sessionId: "",
          runId: "",
          title: "Sleep 5 seconds",
          objective: "Sleep for 5 seconds, then report completion."
        ),
      ]
    )

    let projected = AgentLifecycleDisplayProjection.project([canonical])

    XCTAssertEqual(projected.count, 1)
    XCTAssertTrue(projected[0].text.isEmpty)
    let visibleGroups = ContentBlockGroup.visibleChatGroups(
      projected[0].contentBlocks,
      isStreaming: false
    )
    XCTAssertEqual(visibleGroups.count, 1)
    guard case .agentSpawn = visibleGroups[0] else {
      return XCTFail("expected only the structured legacy spawn card")
    }
  }

  func testLifecycleProjectionPreservesAResultSharingSpawnAnnouncementParagraph() {
    let runID = "run_abc123"
    let combinedProse =
      "Subagent spawned as a floating pill (\(runID)). Result: the requested task completed."
    let canonical = ChatMessage(
      text: combinedProse,
      sender: .ai,
      contentBlocks: [
        .text(id: "assistant-combined-prose", text: combinedProse),
        .agentSpawn(
          id: "spawn-block",
          pillId: nil,
          sessionId: "",
          runId: runID,
          title: "Background task",
          objective: "Complete the requested task."
        ),
      ]
    )

    let projected = AgentLifecycleDisplayProjection.project([canonical])

    XCTAssertTrue(projected[0].text.contains("Result: the requested task completed."))
    XCTAssertFalse(projected[0].text.localizedCaseInsensitiveContains(runID))
  }

  func testLifecycleProjectionRedactsKnownUUIDIdentifierCaseInsensitively() {
    let pillID = UUID()
    let lowercasedPillID = pillID.uuidString.lowercased()
    let canonical = ChatMessage(
      text: "The internal pill handle is \(lowercasedPillID).",
      sender: .ai,
      contentBlocks: [
        .agentCompletion(
          id: "completion-block",
          pillId: pillID,
          sessionId: nil,
          runId: nil,
          title: "Background task",
          promptSnippet: "",
          output: "Done.",
          status: "completed"
        ),
      ]
    )

    let projected = AgentLifecycleDisplayProjection.project([canonical])

    XCTAssertFalse(projected[0].text.localizedCaseInsensitiveContains(lowercasedPillID))
  }

  func testMainChatKeepsOnlyInFlightNonAgentToolsAfterAssistantTextSettles() {
    let groups = ContentBlockGroup.visibleChatGroups(
      [
        .toolCall(id: "tool_1", name: "search_conversations", status: .completed, output: "done"),
        .toolCall(id: "tool_2", name: "execute_sql", status: .running, output: nil),
      ],
      // A tool can still be executing after an assistant's explanatory text
      // has settled. Both chat surfaces must keep the truthful active row.
      isStreaming: false
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

  func testMainChatKeepsActiveToolProgressAlongsideUnmaterializedSpawnLink() {
    let subagentID = UUID()
    let groups = ContentBlockGroup.visibleChatGroups(
      [
        .toolCall(
          id: "spawn_1",
          name: "spawn_agent",
          status: .completed,
          output: "Started agent\nID: \(subagentID.uuidString)"
        ),
        .toolCall(id: "web_1", name: "WebSearch", status: .running, output: nil),
      ],
      isStreaming: false
    )

    XCTAssertEqual(groups.count, 1)
    guard case .toolCalls(_, let calls) = groups[0] else {
      return XCTFail("expected one mixed lifecycle tool group")
    }
    XCTAssertEqual(calls.map(\.id), ["spawn_1", "web_1"])
  }

  func testMainChatHidesToolProgressWhenItsLifecycleBecomesTerminal() {
    let groups = ContentBlockGroup.visibleChatGroups(
      [
        .toolCall(id: "tool_1", name: "WebSearch", status: .completed, output: "done"),
        .toolCall(id: "tool_2", name: "WebFetch", status: .failed, output: nil),
      ],
      isStreaming: false
    )

    XCTAssertTrue(groups.isEmpty)
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

  func testAgentLifecycleDisplayProjectionShowsOneTerminalCardAndKeepsCompletionResources() {
    let pillID = UUID()
    let spawn = ChatMessage(
      id: "spawn-message",
      text: "I started a background agent.",
      sender: .ai,
      contentBlocks: [
        .agentSpawn(
          id: "spawn-block",
          pillId: pillID,
          sessionId: "session-1",
          runId: "run-1",
          title: "Research Notes",
          objective: "Research the release notes"
        ),
      ]
    )
    let artifact = ChatResource.localGeneratedFile(
      id: "artifact-1",
      title: "notes.md",
      subtitle: "text/markdown",
      mimeType: "text/markdown",
      uri: "file:///tmp/notes.md"
    )
    let completion = ChatMessage(
      id: "completion-message",
      text: "[Background agent id=\(pillID.uuidString)] Done.",
      sender: .ai,
      contentBlocks: [
        .agentCompletion(
          id: "completion-block",
          pillId: pillID,
          sessionId: "session-1",
          runId: "run-1",
          title: "Research Notes",
          promptSnippet: "Research the release notes",
          output: "Done.",
          status: "completed"
        ),
      ],
      resources: [artifact]
    )

    let canonical = [spawn, completion]
    let projected = AgentLifecycleDisplayProjection.project(canonical)

    // The canonical transcript retains separate lifecycle facts; only the
    // display projection collapses the terminal completion into the spawn row.
    XCTAssertEqual(canonical.count, 2)
    XCTAssertTrue(canonical[0].resources.isEmpty)
    XCTAssertEqual(canonical[1].resources.map(\.id), ["artifact-1"])
    guard case .agentSpawn = canonical[0].contentBlocks.first,
          case .agentCompletion = canonical[1].contentBlocks.first
    else {
      return XCTFail("the projection must not mutate canonical lifecycle blocks")
    }
    XCTAssertEqual(projected.count, 1)
    XCTAssertEqual(projected[0].id, "spawn-message")
    XCTAssertEqual(projected[0].resources.map(\.id), ["artifact-1"])
    guard case .agentCompletion(_, let renderedPill, _, let renderedRun, _, _, let output, _) =
      projected[0].contentBlocks.first
    else {
      return XCTFail("matched lifecycle must render its terminal completion in the spawn row")
    }
    XCTAssertEqual(renderedPill, pillID)
    XCTAssertEqual(renderedRun, "run-1")
    XCTAssertEqual(output, "Done.")
  }

  func testAgentLifecycleDisplayProjectionPreservesTerminalStateForSameRowLifecycle() {
    let pillID = UUID()
    let sameRowLifecycle = ChatMessage(
      id: "same-row-lifecycle",
      text: "",
      sender: .ai,
      contentBlocks: [
        .agentSpawn(
          id: "spawn-block",
          pillId: pillID,
          sessionId: "session-1",
          runId: "run-1",
          title: "Research Agent",
          objective: "Research the release notes"
        ),
        .agentCompletion(
          id: "completion-block",
          pillId: pillID,
          sessionId: "session-1",
          runId: "run-1",
          title: "Research Agent",
          promptSnippet: "Research the release notes",
          output: "Final release-note summary",
          status: "completed"
        ),
      ]
    )

    let projected = AgentLifecycleDisplayProjection.project([sameRowLifecycle])

    // The structured canonical event still records both lifecycle facts.
    XCTAssertEqual(sameRowLifecycle.contentBlocks.count, 2)
    guard case .agentSpawn = sameRowLifecycle.contentBlocks[0],
          case .agentCompletion = sameRowLifecycle.contentBlocks[1]
    else {
      return XCTFail("same-row canonical lifecycle facts must remain intact")
    }

    XCTAssertEqual(projected.count, 1)
    XCTAssertEqual(projected[0].contentBlocks.count, 1)
    guard case .agentCompletion(_, let renderedPill, _, let renderedRun, _, _, let output, _) =
      projected[0].contentBlocks[0]
    else {
      return XCTFail("same-row lifecycle must render the terminal card")
    }
    XCTAssertEqual(renderedPill, pillID)
    XCTAssertEqual(renderedRun, "run-1")
    XCTAssertEqual(output, "Final release-note summary")
  }

  func testAgentLifecycleDisplayProjectionHidesRawSpawnToolAfterTerminalTransition() {
    let pillID = UUID()
    let lifecycle = ChatMessage(
      id: "same-row-lifecycle",
      text: "",
      sender: .ai,
      contentBlocks: [
        .toolCall(
          id: "spawn-tool",
          name: "spawn_agent",
          status: .completed,
          output: """
          id: \(pillID.uuidString)
          runId: run-1
          """
        ),
        .agentSpawn(
          id: "spawn-block",
          pillId: pillID,
          sessionId: "session-1",
          runId: "run-1",
          title: "Research Agent",
          objective: "Research the release notes"
        ),
        .agentCompletion(
          id: "completion-block",
          pillId: pillID,
          sessionId: "session-1",
          runId: "run-1",
          title: "Research Agent",
          promptSnippet: "Research the release notes",
          output: "Final release-note summary",
          status: "completed"
        ),
      ]
    )

    let projected = AgentLifecycleDisplayProjection.project([lifecycle])
    XCTAssertEqual(projected.count, 1)
    XCTAssertEqual(projected[0].id, lifecycle.id)

    // The main chat and floating chat both use this shared group projection.
    let visible = ContentBlockGroup.visibleChatGroups(
      projected[0].contentBlocks,
      isStreaming: false
    )
    XCTAssertEqual(visible.count, 1)
    guard case .agentCompletion(_, let visiblePillID, _, let visibleRunID, _, _, _, _) = visible[0] else {
      return XCTFail("a terminal run must replace both its starting tool and spawn card")
    }
    XCTAssertEqual(visiblePillID, pillID)
    XCTAssertEqual(visibleRunID, "run-1")
  }

  func testAgentLifecycleDisplayProjectionUsesRunBeforePillAndFallsBackForLegacyCompletion() {
    let pillID = UUID()
    let runBoundSpawn = ChatMessage(
      id: "run-bound-spawn",
      text: "",
      sender: .ai,
      contentBlocks: [
        .agentSpawn(
          id: "spawn-run-bound",
          pillId: pillID,
          sessionId: "session-1",
          runId: "run-1",
          title: "First Agent",
          objective: "First objective"
        ),
      ]
    )
    let conflictingCompletion = ChatMessage(
      id: "conflicting-completion",
      text: "",
      sender: .ai,
      contentBlocks: [
        .agentCompletion(
          id: "completion-run-2",
          pillId: pillID,
          sessionId: "session-1",
          runId: "run-2",
          title: "Second Agent",
          promptSnippet: "Second objective",
          output: "Done.",
          status: "completed"
        ),
      ]
    )
    XCTAssertEqual(
      AgentLifecycleDisplayProjection.project([runBoundSpawn, conflictingCompletion]).count,
      2,
      "a run-identified completion must not collapse onto a different run that shares a pill id"
    )

    let legacySpawn = ChatMessage(
      id: "legacy-spawn",
      text: "",
      sender: .ai,
      contentBlocks: [
        .agentSpawn(
          id: "legacy-spawn-block",
          pillId: pillID,
          sessionId: "",
          runId: "",
          title: "Legacy Agent",
          objective: "Legacy objective"
        ),
      ]
    )
    let legacyCompletion = ChatMessage(
      id: "legacy-completion",
      text: "",
      sender: .ai,
      contentBlocks: [
        .agentCompletion(
          id: "legacy-completion-block",
          pillId: pillID,
          sessionId: nil,
          runId: nil,
          title: "Legacy Agent",
          promptSnippet: "Legacy objective",
          output: "Done.",
          status: "completed"
        ),
      ]
    )
    XCTAssertEqual(
      AgentLifecycleDisplayProjection.project([legacySpawn, legacyCompletion]).count,
      1,
      "legacy completion without a run id may fall back to the pill identity"
    )
  }

  func testAgentLifecycleDisplayProjectionCoalescesDuplicateTerminalCompletions() {
    let pillID = UUID()
    let spawn = ChatMessage(
      id: "spawn-message",
      text: "",
      sender: .ai,
      contentBlocks: [
        .agentSpawn(
          id: "spawn-block",
          pillId: pillID,
          sessionId: "session-1",
          runId: "run-1",
          title: "Agent",
          objective: "Objective"
        ),
      ]
    )
    func completion(id: String, output: String, resourceID: String) -> ChatMessage {
      ChatMessage(
        id: id,
        text: "",
        sender: .ai,
        contentBlocks: [
          .agentCompletion(
            id: "\(id)-block",
            pillId: pillID,
            sessionId: "session-1",
            runId: "run-1",
            title: "Agent",
            promptSnippet: "Objective",
            output: output,
            status: "completed"
          ),
        ],
        resources: [
          .localGeneratedFile(
            id: resourceID,
            title: "\(resourceID).txt",
            subtitle: "text/plain",
            mimeType: "text/plain",
            uri: "file:///tmp/\(resourceID).txt"
          ),
        ]
      )
    }

    let projected = AgentLifecycleDisplayProjection.project([
      spawn,
      completion(id: "completion-1", output: "Initial result", resourceID: "artifact-1"),
      completion(id: "completion-2", output: "Final result", resourceID: "artifact-2"),
    ])

    XCTAssertEqual(projected.count, 1)
    XCTAssertEqual(Set(projected[0].resources.map(\.id)), Set(["artifact-1", "artifact-2"]))
    guard case .agentCompletion(_, _, _, _, _, _, let output, _) = projected[0].contentBlocks.first else {
      return XCTFail("expected terminal agent card")
    }
    XCTAssertEqual(output, "Final result")
  }

  func testAgentLifecycleDisplayProjectionRemovesMatchedCardFromMixedCompletionMessage() {
    let pillID = UUID()
    let spawn = ChatMessage(
      id: "spawn-message",
      text: "",
      sender: .ai,
      contentBlocks: [
        .agentSpawn(
          id: "spawn-block",
          pillId: pillID,
          sessionId: "session-1",
          runId: "run-1",
          title: "Agent",
          objective: "Objective"
        ),
      ]
    )
    let artifact = ChatResource.localGeneratedFile(
      id: "artifact-1",
      title: "result.md",
      subtitle: "text/markdown",
      mimeType: "text/markdown",
      uri: "file:///tmp/result.md"
    )
    let mixedCompletion = ChatMessage(
      id: "mixed-completion-message",
      text: "The surrounding response remains visible.",
      sender: .ai,
      contentBlocks: [
        .agentCompletion(
          id: "completion-block",
          pillId: pillID,
          sessionId: "session-1",
          runId: "run-1",
          title: "Agent",
          promptSnippet: "Objective",
          output: "Done.",
          status: "completed"
        ),
        .text(id: "surrounding-text", text: "The surrounding response remains visible."),
        .toolCall(
          id: "surrounding-tool",
          name: "search_notes",
          status: .completed,
          output: "Found one related note."
        ),
      ],
      resources: [artifact]
    )

    let projected = AgentLifecycleDisplayProjection.project([spawn, mixedCompletion])

    XCTAssertEqual(projected.count, 2, "the non-agent portion of a mixed completion stays visible")
    XCTAssertEqual(
      projected.flatMap(\.contentBlocks).filter { block in
        if case .agentCompletion = block { return true }
        return false
      }.count,
      1,
      "the lifecycle must render exactly one terminal agent card"
    )
    XCTAssertEqual(projected[0].resources.map(\.id), ["artifact-1"])
    XCTAssertEqual(projected[1].resources.map(\.id), ["artifact-1"])
    XCTAssertEqual(projected[1].contentBlocks.count, 2)
    guard case .text(_, let text) = projected[1].contentBlocks[0] else {
      return XCTFail("the mixed completion's ordinary content must remain")
    }
    XCTAssertEqual(text, "The surrounding response remains visible.")
    guard case .toolCall(_, let name, let status, _, _, let output) = projected[1].contentBlocks[1] else {
      return XCTFail("the mixed completion's ordinary tool block must remain")
    }
    XCTAssertEqual(name, "search_notes")
    XCTAssertEqual(status, .completed)
    XCTAssertEqual(output, "Found one related note.")
  }

  func testAgentLifecycleDisplayProjectionRetainsUnmatchedCompletionInMixedSourceMessage() {
    let pillID = UUID()
    let spawn = ChatMessage(
      id: "spawn-message",
      text: "",
      sender: .ai,
      contentBlocks: [
        .agentSpawn(
          id: "spawn-block",
          pillId: pillID,
          sessionId: "session-1",
          runId: "run-1",
          title: "First Agent",
          objective: "First objective"
        ),
      ]
    )
    let mixedCompletions = ChatMessage(
      id: "mixed-completions-message",
      text: "A separate agent is still available.",
      sender: .ai,
      contentBlocks: [
        .agentCompletion(
          id: "matching-completion",
          pillId: pillID,
          sessionId: "session-1",
          runId: "run-1",
          title: "First Agent",
          promptSnippet: "First objective",
          output: "First result",
          status: "completed"
        ),
        .agentCompletion(
          id: "unmatched-completion",
          pillId: pillID,
          sessionId: "session-1",
          runId: "run-2",
          title: "Second Agent",
          promptSnippet: "Second objective",
          output: "Second result",
          status: "completed"
        ),
        .text(id: "surrounding-text", text: "A separate agent is still available."),
      ]
    )

    let projected = AgentLifecycleDisplayProjection.project([spawn, mixedCompletions])

    XCTAssertEqual(projected.count, 2)
    guard case .agentCompletion(_, _, _, let renderedRun, _, _, let renderedOutput, _) =
      projected[0].contentBlocks.first
    else {
      return XCTFail("the matching completion must replace the spawn row")
    }
    XCTAssertEqual(renderedRun, "run-1")
    XCTAssertEqual(renderedOutput, "First result")
    XCTAssertEqual(projected[1].contentBlocks.count, 2)
    guard case .agentCompletion(_, _, _, let retainedRun, _, _, let retainedOutput, _) =
      projected[1].contentBlocks[0]
    else {
      return XCTFail("an unmatched completion must remain in its source row")
    }
    XCTAssertEqual(retainedRun, "run-2")
    XCTAssertEqual(retainedOutput, "Second result")
    XCTAssertEqual(
      projected.flatMap(\.contentBlocks).filter { block in
        if case .agentCompletion = block { return true }
        return false
      }.count,
      2,
      "one terminal card must remain for each distinct run"
    )
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

    let projection = ChatProvider.materializeAgentSpawnBlockIfNeeded(
        in: &blocks,
        toolUseId: "tu-1",
        toolName: "spawn_agent"
    )
    XCTAssertEqual(
      projection,
      ChatProvider.SpawnedAgentPillProjection(
        pillID: pillId,
        sessionID: "sess-abc",
        runID: "run-xyz",
        title: "Sleep Agent",
        objective: "sleep five seconds"
      )
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

  func testMaterializeAgentSpawnBlockFromCanonicalProductionJSONResult() throws {
    let pillId = UUID(uuidString: "C7CBA329-65C4-4A5C-96A6-1A0A5FEECC48")!
    // Exact compact response shape returned by control-tools.ts stringifyToolResult.
    let output = #"{"ok":true,"routeDecision":{"effect":"spawn_background_agent"},"requestedAgentCount":1,"agents":[{"kind":"background","delegation":null,"session":{"sessionId":"sess-prod","ownerId":"owner-1","title":"Memory Insight","surfaceKind":"floating_agent","externalRefKind":"pill","externalRefId":"C7CBA329-65C4-4A5C-96A6-1A0A5FEECC48","metadata":{}},"run":{"runId":"run-prod","sessionId":"sess-prod"},"attempt":null}],"delegation":null,"session":{"sessionId":"sess-prod","ownerId":"owner-1","title":"Memory Insight","surfaceKind":"floating_agent","externalRefKind":"pill","externalRefId":"C7CBA329-65C4-4A5C-96A6-1A0A5FEECC48","metadata":{}},"run":{"runId":"run-prod","sessionId":"sess-prod"},"attempt":null}"#
    var blocks: [ChatContentBlock] = [
      .toolCall(
        id: "tool-prod",
        name: "spawn_agent",
        status: .completed,
        toolUseId: "tu-prod",
        input: ToolCallInput(summary: "Memory Insight", details: "look through today's memories"),
        output: output
      )
    ]

    ChatProvider.materializeAgentSpawnBlockIfNeeded(
      in: &blocks,
      toolUseId: "tu-prod",
      toolName: "spawn_agent"
    )

    XCTAssertEqual(blocks.count, 2)
    guard case .agentSpawn(let blockId, let actualPill, let sessionId, let runId, let title, let objective) = blocks[1]
    else { return XCTFail("canonical production result must materialize agentSpawn") }
    XCTAssertEqual(blockId, "agent_spawn_run-prod")
    XCTAssertEqual(actualPill, pillId)
    XCTAssertEqual(sessionId, "sess-prod")
    XCTAssertEqual(runId, "run-prod")
    XCTAssertEqual(title, "Memory Insight")
    XCTAssertEqual(objective, "look through today's memories")

    ChatProvider.materializeAgentSpawnBlockIfNeeded(
      in: &blocks,
      toolUseId: "tu-prod",
      toolName: "spawn_agent"
    )
    XCTAssertEqual(blocks.count, 2)
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
    let defaults = UserDefaults.standard
    let previousAuthOwner = defaults.object(forKey: .authUserId)
    let previousAutomationOwner = defaults.object(forKey: .automationOwnerOverride)
    let ownerID = "timeline-hydrate-owner"
    defaults.removeObject(forKey: .automationOwnerOverride)
    defaults.set(ownerID, forKey: .authUserId)

    let runPill = AgentPill(
      id: UUID(), query: "by-run", model: "test", ownerID: ownerID)
    runPill.canonicalRunId = "run-match"
    runPill.canonicalSessionId = "sess-other"

    let sessionPill = AgentPill(
      id: UUID(), query: "by-session", model: "test", ownerID: ownerID)
    sessionPill.canonicalSessionId = "sess-match"

    let pillId = UUID()
    let idPill = AgentPill(
      id: pillId, query: "by-id", model: "test", ownerID: ownerID)

    let manager = AgentPillsManager.shared
    let previous = manager.pills
    defer {
      if let previousAuthOwner {
        defaults.set(previousAuthOwner, forKey: .authUserId)
      } else {
        defaults.removeObject(forKey: .authUserId)
      }
      if let previousAutomationOwner {
        defaults.set(previousAutomationOwner, forKey: .automationOwnerOverride)
      } else {
        defaults.removeObject(forKey: .automationOwnerOverride)
      }
      manager.replacePillsForTesting(previous)
    }
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

    XCTAssertFalse(
      hub.contains("ChatProvider.mainInstance"),
      "realtime transport must project through the journal-facing manager, not reach into ChatProvider"
    )
    XCTAssertFalse(hub.contains("warmProvider = ChatProvider()"))
    XCTAssertFalse(hub.contains("private var warmProvider"))
    XCTAssertFalse(
      hub.contains("ChatProvider()"),
      "speculative warm must not construct a second ChatProvider"
    )

    XCTAssertFalse(runtime.contains("turn_recorded"))
    XCTAssertFalse(bridge.contains("setTurnRecordedHandler"))
    XCTAssertTrue(runtime.contains("func setJournalTurnChangedHandler"))
    XCTAssertTrue(bridge.contains("func setJournalTurnChangedHandler"))

    for source in [hub, runtime, bridge, floatingState, provider, window] {
      XCTAssertFalse(
        source.contains("suppressNextRecordedTurn"),
        "dual-write bandage suppressNextRecordedTurn is forbidden"
      )
    }

    XCTAssertFalse(floatingState.contains("@Published var chatHistory"))
  }

  /// INV-6 single ChatProvider lifecycle — only ViewModelContainer may construct production instances.
  func testProductionSourcesOnlyConstructChatProviderInViewModelContainer() throws {
    let violations = try productionChatProviderConstructorViolations()
    XCTAssertTrue(
      violations.isEmpty,
      """
      Production Sources must not call ChatProvider() outside ViewModelContainer \
      (SwiftUI #Preview blocks and ViewExporter are excluded).
      Violations:
      \(violations.sorted().joined(separator: "\n"))
      """
    )

    let schedulerSource = try String(
      contentsOf: sourcesRoot().appendingPathComponent("Services/RecurringTaskScheduler.swift"),
      encoding: .utf8
    )
    XCTAssertTrue(schedulerSource.contains("configure(taskChatCoordinator:"))
    XCTAssertFalse(
      schedulerSource.contains("ChatProvider()"),
      "RecurringTaskScheduler must reuse the shared TaskChatCoordinator"
    )
  }

  private func sourcesRoot() -> URL {
    URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources")
  }

  private func productionChatProviderConstructorViolations() throws -> [String] {
    let allowedFiles: Set<String> = [
      "ViewModelContainer.swift",
      "ViewExporter.swift",
    ]
    let root = sourcesRoot()
    let paths = try FileManager.default.subpathsOfDirectory(atPath: root.path)
      .filter { $0.hasSuffix(".swift") }
      .sorted()

    var violations: [String] = []
    for path in paths {
      let fileName = (path as NSString).lastPathComponent
      if allowedFiles.contains(fileName) {
        continue
      }

      let text = try String(contentsOf: root.appendingPathComponent(path), encoding: .utf8)
      var inPreviewOnlyBlock = false
      var previewDepth = 0

      for (index, line) in text.components(separatedBy: .newlines).enumerated() {
        let trimmed = line.trimmingCharacters(in: .whitespaces)
        if trimmed.hasPrefix("#if canImport(PreviewsMacros)") {
          previewDepth += 1
        }
        if previewDepth > 0 {
          inPreviewOnlyBlock = true
        }
        if trimmed.hasPrefix("#endif") {
          previewDepth = max(0, previewDepth - 1)
          if previewDepth == 0 {
            inPreviewOnlyBlock = false
          }
        }

        guard line.contains("ChatProvider()"), !inPreviewOnlyBlock else { continue }
        violations.append("\(path):\(index + 1): \(trimmed)")
      }
    }
    return violations
  }
}

private extension Array where Element == ChatContentBlock {
  var spawnedAgentIDs: [UUID] {
    compactMap { block in
      block.spawnedAgentID
    }
  }
}
