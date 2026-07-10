import XCTest

@testable import Omi_Computer

@MainActor
final class KernelTurnRecordedProjectionTests: XCTestCase {

  func testApplyKernelTurnRecordedAppendsMainChatMessages() {
    let provider = ChatProvider()
    let projection = provider.kernelTurnProjection
    let surface = provider.mainChatSurfaceReference()
    projection.apply(
      .init(
        conversationId: "conv-1",
        surfaceKind: surface.surfaceKind,
        externalRefKind: surface.externalRefKind,
        externalRefId: surface.externalRefId,
        userText: "PTT question",
        assistantText: "PTT answer",
        origin: "realtime_voice",
        interrupted: false,
        idempotencyKey: "turn-1",
        userTurnId: "user-turn-1",
        assistantTurnId: "assistant-turn-1"
      )
    )

    XCTAssertEqual(provider.messages.filter { $0.sender == .user }.map(\.text), ["PTT question"])
    XCTAssertEqual(provider.messages.filter { $0.sender == .ai }.map(\.text), ["PTT answer"])
    XCTAssertEqual(
      provider.messages.filter { $0.sender == .user }.compactMap(\.clientTurnId),
      ["turn-1"]
    )
  }

  func testApplyKernelTurnRecordedDedupesByIdempotencyKey() {
    let provider = ChatProvider()
    let projection = provider.kernelTurnProjection
    let surface = provider.mainChatSurfaceReference()
    let turn = AgentRuntimeProcess.KernelTurnRecorded(
      conversationId: "conv-1",
      surfaceKind: surface.surfaceKind,
      externalRefKind: surface.externalRefKind,
      externalRefId: surface.externalRefId,
      userText: "Once",
      assistantText: "Twice",
      origin: "realtime_voice",
      interrupted: false,
      idempotencyKey: "dup-key",
      userTurnId: nil,
      assistantTurnId: nil
    )
    projection.apply(turn)
    projection.apply(turn)

    XCTAssertEqual(provider.messages.filter { $0.sender == .user }.count, 1)
    XCTAssertEqual(provider.messages.filter { $0.sender == .ai }.count, 1)
  }

  func testRapidPTTRoleProjectionsShowEveryUserTurnBeforeFinalReply() {
    let provider = ChatProvider()
    let projection = provider.kernelTurnProjection
    let surface = provider.mainChatSurfaceReference()

    for (index, text) in ["one two three", "A B C", "R G B"].enumerated() {
      projection.apply(
        .init(
          conversationId: "conv-rapid-ptt",
          surfaceKind: surface.surfaceKind,
          externalRefKind: surface.externalRefKind,
          externalRefId: surface.externalRefId,
          userText: text,
          assistantText: index == 2 ? "Red, green, blue." : "",
          origin: "realtime_voice",
          interrupted: index < 2,
          idempotencyKey: "realtime_voice:turn-\(index):user",
          userTurnId: "user-turn-\(index)",
          assistantTurnId: nil
        )
      )
    }

    XCTAssertEqual(provider.messages.map(\.sender), [.user, .user, .user, .ai])
    XCTAssertEqual(
      provider.messages.map(\.text),
      ["one two three", "A B C", "R G B", "Red, green, blue."]
    )
  }

  /// INV-6: one turn_recorded UI apply gate. Warm/restart re-attach replaces the
  /// single handler slot; one dispatched turn_recorded yields one message pair.
  func testTurnRecordedHandlerReplacePreventsWarmDuplicateFanout() async {
    final class FanoutBox: @unchecked Sendable {
      private let lock = NSLock()
      private var turns: [AgentRuntimeProcess.KernelTurnRecorded] = []

      func note(_ turn: AgentRuntimeProcess.KernelTurnRecorded) {
        lock.lock()
        turns.append(turn)
        lock.unlock()
      }

      var count: Int {
        lock.lock()
        defer { lock.unlock() }
        return turns.count
      }

      var last: AgentRuntimeProcess.KernelTurnRecorded? {
        lock.lock()
        defer { lock.unlock() }
        return turns.last
      }
    }

    let runtime = AgentRuntimeProcess()
    let bridge = AgentBridge(runtime: runtime)
    let main = ChatProvider()
    ChatProvider.mainInstance = main
    defer { ChatProvider.mainInstance = nil }
    let fanout = FanoutBox()

    let surface = main.mainChatSurfaceReference()
    let turn = AgentRuntimeProcess.KernelTurnRecorded(
      conversationId: "conv-warm",
      surfaceKind: surface.surfaceKind,
      externalRefKind: surface.externalRefKind,
      externalRefId: surface.externalRefId,
      userText: "PTT after warm",
      assistantText: "Single answer",
      origin: "realtime_voice",
      interrupted: false,
      idempotencyKey: "warm-dup-key",
      userTurnId: "u1",
      assistantTurnId: "a1"
    )

    // Main attach, then speculative-warm re-attach on the same mainInstance.
    // Pre-fix append API would leave two handlers; replace keeps one slot.
    await bridge.setTurnRecordedHandler { fanout.note($0) }
    await bridge.setTurnRecordedHandler { fanout.note($0) }
    let handlerCount = await runtime.turnRecordedHandlerCount()
    XCTAssertEqual(handlerCount, 1)

    await runtime.dispatchTurnRecordedForTesting(turn)
    XCTAssertEqual(fanout.count, 1, "single handler slot must not fan out twice")
    guard let delivered = fanout.last else {
      return XCTFail("expected one delivered turn_recorded")
    }
    main.kernelTurnProjection.apply(delivered)
    XCTAssertEqual(main.messages.filter { $0.sender == .user }.count, 1)
    XCTAssertEqual(main.messages.filter { $0.sender == .ai }.count, 1)
    XCTAssertEqual(main.messages.filter { $0.sender == .user }.map(\.text), ["PTT after warm"])
    XCTAssertEqual(main.messages.filter { $0.sender == .ai }.map(\.text), ["Single answer"])

    // Same key through the single gate again must not append a second pair.
    await runtime.dispatchTurnRecordedForTesting(turn)
    XCTAssertEqual(fanout.count, 2)
    if let again = fanout.last {
      main.kernelTurnProjection.apply(again)
    }
    XCTAssertEqual(main.messages.filter { $0.sender == .user }.count, 1)
    XCTAssertEqual(main.messages.filter { $0.sender == .ai }.count, 1)
  }

  func testApplyKernelTurnRecordedIgnoresOtherSurfaces() {
    let provider = ChatProvider()
    provider.kernelTurnProjection.apply(
      .init(
        conversationId: "conv-1",
        surfaceKind: "floating_chat",
        externalRefKind: "chat",
        externalRefId: "default",
        userText: "wrong surface",
        assistantText: "ignored",
        origin: "realtime_voice",
        interrupted: false,
        idempotencyKey: nil,
        userTurnId: nil,
        assistantTurnId: nil
      )
    )

    XCTAssertTrue(provider.messages.isEmpty)
  }

  func testStageOptimisticThenApplyPromotesInPlaceWithoutDuplicate() {
    let provider = ChatProvider()
    let projection = provider.kernelTurnProjection
    let surface = provider.mainChatSurfaceReference()
    let key = "floating_resolver:exchange-1:spawn"
    let blocks: [ChatContentBlock] = [
      .text(id: "block-1", text: "spawned"),
    ]

    let staged = provider.stageOptimisticTurn(
      continuityKey: key,
      userText: "Start a background agent",
      assistantText: "On it — spawning now.",
      origin: "floating_resolver",
      turnOwner: .floatingDefault,
      contentBlocks: blocks
    )
    XCTAssertNotNil(staged.user)
    XCTAssertNotNil(staged.assistant)
    XCTAssertEqual(staged.assistant?.contentBlocks.count, 1)
    XCTAssertTrue(provider.hasOptimisticTurn(continuityKey: key))

    projection.apply(
      .init(
        conversationId: "conv-1",
        surfaceKind: surface.surfaceKind,
        externalRefKind: surface.externalRefKind,
        externalRefId: surface.externalRefId,
        userText: "Start a background agent",
        assistantText: "On it — spawning now.",
        origin: "floating_resolver",
        interrupted: false,
        idempotencyKey: key,
        userTurnId: nil,
        assistantTurnId: nil
      )
    )

    XCTAssertEqual(provider.messages.filter { $0.sender == .user }.count, 1)
    XCTAssertEqual(provider.messages.filter { $0.sender == .ai }.count, 1)
    XCTAssertEqual(
      provider.messages.filter { $0.sender == .user }.map(\.text),
      ["Start a background agent"]
    )
    XCTAssertEqual(
      provider.messages.filter { $0.sender == .ai }.map(\.text),
      ["On it — spawning now."]
    )
    XCTAssertEqual(provider.messages.first(where: { $0.sender == .ai })?.contentBlocks.count, 1)
    XCTAssertFalse(provider.hasOptimisticTurn(continuityKey: key))

    // Second apply of the same committed key must not append again.
    projection.apply(
      .init(
        conversationId: "conv-1",
        surfaceKind: surface.surfaceKind,
        externalRefKind: surface.externalRefKind,
        externalRefId: surface.externalRefId,
        userText: "Start a background agent",
        assistantText: "On it — spawning now.",
        origin: "floating_resolver",
        interrupted: false,
        idempotencyKey: key,
        userTurnId: nil,
        assistantTurnId: nil
      )
    )
    XCTAssertEqual(provider.messages.filter { $0.sender == .user }.count, 1)
    XCTAssertEqual(provider.messages.filter { $0.sender == .ai }.count, 1)
  }

  func testPillCompletionKeyCoalescesSecondStageWithoutDuplicate() {
    let provider = ChatProvider()
    let projection = provider.kernelTurnProjection
    let surface = provider.mainChatSurfaceReference()
    let key = "pill_completion:run-42"
    let pillID = UUID()
    let summary = "[Background agent id=\(pillID.uuidString) — sleep] Done."
    let resource = ChatResource.localGeneratedFile(
      id: "res-1",
      title: "out.txt",
      subtitle: "text/plain",
      mimeType: "text/plain",
      uri: "file:///tmp/out.txt"
    )
    let lateResource = ChatResource.localGeneratedFile(
      id: "res-2",
      title: "late.txt",
      subtitle: "text/plain",
      mimeType: "text/plain",
      uri: "file:///tmp/late.txt"
    )
    let completionBlock = ChatContentBlock.agentCompletion(
      id: "completion-block",
      pillId: pillID,
      sessionId: "sess-42",
      runId: "run-42",
      title: "Background agent",
      promptSnippet: "sleep",
      output: "Done.",
      status: "completed"
    )

    let first = provider.stageOptimisticTurn(
      continuityKey: key,
      userText: "",
      assistantText: summary,
      origin: "pill_completion",
      turnOwner: .mainChat,
      contentBlocks: [completionBlock],
      resources: [resource]
    )
    XCTAssertNotNil(first.assistant)
    XCTAssertEqual(first.assistant?.resources.count, 1)
    XCTAssertEqual(first.assistant?.contentBlocks.count, 1)
    guard case .agentCompletion(_, let stagedPill, let stagedSession, let stagedRun, _, _, _, _) =
      first.assistant?.contentBlocks.first
    else {
      return XCTFail("expected staged agentCompletion block")
    }
    XCTAssertEqual(stagedPill, pillID)
    XCTAssertEqual(stagedSession, "sess-42")
    XCTAssertEqual(stagedRun, "run-42")

    // Terminal / late-artifact path reuses the same key and merges onto the
    // producing message (no second assistant turn).
    let second = provider.stageOptimisticTurn(
      continuityKey: key,
      userText: "",
      assistantText: summary,
      origin: "pill_completion",
      turnOwner: .mainChat,
      resources: [lateResource]
    )
    XCTAssertEqual(second.assistant?.id, first.assistant?.id)
    XCTAssertEqual(provider.messages.filter { $0.sender == .ai }.count, 1)
    XCTAssertEqual(
      Set(provider.messages.first(where: { $0.sender == .ai })?.resources.map(\.id) ?? []),
      Set(["res-1", "res-2"])
    )

    projection.apply(
      .init(
        conversationId: "conv-1",
        surfaceKind: surface.surfaceKind,
        externalRefKind: surface.externalRefKind,
        externalRefId: surface.externalRefId,
        userText: "",
        assistantText: summary,
        origin: "pill_completion",
        interrupted: false,
        idempotencyKey: key,
        userTurnId: nil,
        assistantTurnId: nil
      )
    )
    XCTAssertEqual(provider.messages.filter { $0.sender == .ai }.count, 1)
    let promoted = provider.messages.first(where: { $0.sender == .ai })
    XCTAssertEqual(Set(promoted?.resources.map(\.id) ?? []), Set(["res-1", "res-2"]))
    XCTAssertEqual(promoted?.contentBlocks.count, 1)
    guard case .agentCompletion(_, let promotedPill, _, let promotedRun, _, _, _, _) =
      promoted?.contentBlocks.first
    else {
      return XCTFail("promote must keep agentCompletion block")
    }
    XCTAssertEqual(promotedPill, pillID)
    XCTAssertEqual(promotedRun, "run-42")
    XCTAssertFalse(provider.hasOptimisticTurn(continuityKey: key))
  }

  func testKernelOnlyPillCompletionMaterializesAgentCompletionBlock() {
    let provider = ChatProvider()
    let projection = provider.kernelTurnProjection
    let surface = provider.mainChatSurfaceReference()
    let pillID = UUID()
    let key = "pill_completion:run-kernel-only"
    let summary = "[Background agent id=\(pillID.uuidString) — research] Finished."

    projection.apply(
      .init(
        conversationId: "conv-1",
        surfaceKind: surface.surfaceKind,
        externalRefKind: surface.externalRefKind,
        externalRefId: surface.externalRefId,
        userText: "",
        assistantText: summary,
        origin: "pill_completion",
        interrupted: false,
        idempotencyKey: key,
        userTurnId: nil,
        assistantTurnId: nil
      )
    )

    let assistant = provider.messages.first(where: { $0.sender == .ai })
    XCTAssertEqual(assistant?.text, summary)
    XCTAssertEqual(assistant?.contentBlocks.count, 1)
    guard case .agentCompletion(_, let blockPill, _, let runId, _, let prompt, let output, let status) =
      assistant?.contentBlocks.first
    else {
      return XCTFail("kernel-only pill_completion must attach agentCompletion")
    }
    XCTAssertEqual(blockPill, pillID)
    XCTAssertEqual(runId, "run-kernel-only")
    XCTAssertEqual(prompt, "research")
    XCTAssertEqual(output, "Finished.")
    XCTAssertEqual(status, "completed")
  }

  func testApplyWithoutOptimisticStillAppendsVoicePath() {
    let provider = ChatProvider()
    let projection = provider.kernelTurnProjection
    let surface = provider.mainChatSurfaceReference()

    projection.apply(
      .init(
        conversationId: "conv-1",
        surfaceKind: surface.surfaceKind,
        externalRefKind: surface.externalRefKind,
        externalRefId: surface.externalRefId,
        userText: "voice question",
        assistantText: "voice answer",
        origin: "realtime_voice",
        interrupted: false,
        idempotencyKey: "voice-turn-1",
        userTurnId: nil,
        assistantTurnId: nil
      )
    )

    XCTAssertEqual(provider.messages.filter { $0.sender == .user }.map(\.text), ["voice question"])
    XCTAssertEqual(provider.messages.filter { $0.sender == .ai }.map(\.text), ["voice answer"])
    XCTAssertEqual(
      provider.messages.compactMap(\.clientTurnId),
      ["voice-turn-1", "voice-turn-1"]
    )
  }

  /// Proactive notifications stage under `notification:<uuid>` (same stage/promote
  /// path as other surface turns) — not a separate appendAssistantMessage writer.
  func testNotificationContinuityKeyStagesAndPromotesWithoutDoubleAppend() {
    let provider = ChatProvider()
    let projection = provider.kernelTurnProjection
    let surface = provider.mainChatSurfaceReference()
    let notificationId = UUID()
    let key = "notification:\(notificationId.uuidString)"
    let text = "Heads up: calendar conflict"

    let staged = provider.stageOptimisticTurn(
      continuityKey: key,
      userText: "",
      assistantText: text,
      origin: "proactive_notification",
      turnOwner: .mainChat
    )
    XCTAssertNotNil(staged.assistant)
    XCTAssertNil(staged.user)
    XCTAssertTrue(provider.hasOptimisticTurn(continuityKey: key))
    XCTAssertEqual(provider.messages.filter { $0.sender == .ai }.count, 1)
    XCTAssertEqual(provider.messages.first?.clientTurnId, key)

    projection.apply(
      .init(
        conversationId: "conv-1",
        surfaceKind: surface.surfaceKind,
        externalRefKind: surface.externalRefKind,
        externalRefId: surface.externalRefId,
        userText: "",
        assistantText: text,
        origin: "proactive_notification",
        interrupted: false,
        idempotencyKey: key,
        userTurnId: nil,
        assistantTurnId: "assistant-notif-1"
      )
    )

    XCTAssertFalse(provider.hasOptimisticTurn(continuityKey: key))
    XCTAssertEqual(provider.messages.filter { $0.sender == .ai }.count, 1)
    XCTAssertEqual(provider.messages.first?.id, staged.assistant?.id)
    XCTAssertEqual(provider.messages.first?.text, text)
  }

  /// INV-6: never dedupe by text — identical user+assistant copy with different
  /// continuity keys must produce two distinct pairs on the timeline.
  func testSameTextDifferentContinuityKeysKeepsTwoPairs() {
    let provider = ChatProvider()
    let projection = provider.kernelTurnProjection
    let surface = provider.mainChatSurfaceReference()
    let userText = "same question"
    let assistantText = "same answer"

    let first = provider.stageOptimisticTurn(
      continuityKey: "key-a",
      userText: userText,
      assistantText: assistantText,
      origin: "realtime_voice",
      turnOwner: .mainChat
    )
    let second = provider.stageOptimisticTurn(
      continuityKey: "key-b",
      userText: userText,
      assistantText: assistantText,
      origin: "realtime_voice",
      turnOwner: .mainChat
    )
    XCTAssertNotEqual(first.user?.id, second.user?.id)
    XCTAssertNotEqual(first.assistant?.id, second.assistant?.id)
    XCTAssertEqual(provider.messages.filter { $0.sender == .user }.count, 2)
    XCTAssertEqual(provider.messages.filter { $0.sender == .ai }.count, 2)

    projection.apply(
      .init(
        conversationId: "conv-1",
        surfaceKind: surface.surfaceKind,
        externalRefKind: surface.externalRefKind,
        externalRefId: surface.externalRefId,
        userText: userText,
        assistantText: assistantText,
        origin: "realtime_voice",
        interrupted: false,
        idempotencyKey: "key-a",
        userTurnId: nil,
        assistantTurnId: nil
      )
    )
    projection.apply(
      .init(
        conversationId: "conv-1",
        surfaceKind: surface.surfaceKind,
        externalRefKind: surface.externalRefKind,
        externalRefId: surface.externalRefId,
        userText: userText,
        assistantText: assistantText,
        origin: "realtime_voice",
        interrupted: false,
        idempotencyKey: "key-b",
        userTurnId: nil,
        assistantTurnId: nil
      )
    )

    let users = provider.messages.filter { $0.sender == .user }
    let assistants = provider.messages.filter { $0.sender == .ai }
    XCTAssertEqual(users.count, 2)
    XCTAssertEqual(assistants.count, 2)
    XCTAssertEqual(users.map(\.text), [userText, userText])
    XCTAssertEqual(assistants.map(\.text), [assistantText, assistantText])
    XCTAssertEqual(Set(users.compactMap(\.clientTurnId)), Set(["key-a", "key-b"]))
    XCTAssertEqual(Set(assistants.compactMap(\.clientTurnId)), Set(["key-a", "key-b"]))
  }

  /// P1: user-only first stage must still accept a later assistant payload for the
  /// same continuity key (create the missing assistant message instead of dropping it).
  func testRestageCreatesMissingAssistantAfterUserOnlyStage() {
    let provider = ChatProvider()
    let key = "voice-user-first"

    let first = provider.stageOptimisticTurn(
      continuityKey: key,
      userText: "user only first",
      assistantText: "",
      origin: "realtime_voice",
      turnOwner: .mainChat
    )
    XCTAssertNotNil(first.user)
    XCTAssertNil(first.assistant)
    XCTAssertEqual(provider.messages.filter { $0.sender == .user }.count, 1)
    XCTAssertEqual(provider.messages.filter { $0.sender == .ai }.count, 0)

    let second = provider.stageOptimisticTurn(
      continuityKey: key,
      userText: "user only first",
      assistantText: "assistant arrives later",
      origin: "realtime_voice",
      turnOwner: .mainChat
    )
    XCTAssertEqual(first.user?.id, second.user?.id)
    XCTAssertNotNil(second.assistant)
    XCTAssertEqual(second.assistant?.text, "assistant arrives later")
    XCTAssertEqual(provider.messages.filter { $0.sender == .user }.count, 1)
    XCTAssertEqual(provider.messages.filter { $0.sender == .ai }.count, 1)
    XCTAssertEqual(provider.messages.first(where: { $0.sender == .ai })?.clientTurnId, key)
  }

  func testEmptyIdempotencyKeyStillAppends() {
    let provider = ChatProvider()
    let projection = provider.kernelTurnProjection
    let surface = provider.mainChatSurfaceReference()

    projection.apply(
      .init(
        conversationId: "conv-1",
        surfaceKind: surface.surfaceKind,
        externalRefKind: surface.externalRefKind,
        externalRefId: surface.externalRefId,
        userText: "empty key turn",
        assistantText: "should append",
        origin: "realtime_voice",
        interrupted: false,
        idempotencyKey: nil,
        userTurnId: nil,
        assistantTurnId: nil
      )
    )

    XCTAssertEqual(provider.messages.filter { $0.sender == .user }.map(\.text), ["empty key turn"])
    XCTAssertEqual(provider.messages.filter { $0.sender == .ai }.map(\.text), ["should append"])
  }

  func testMainAndFloatingAutomationSnapshotsAliasSameTimeline() throws {
    let provider = ChatProvider()
    _ = provider.recordCompletedTurn(
      userText: "main question",
      assistantText: "main answer",
      logLabel: "main"
    )
    _ = provider.recordCompletedTurn(
      userText: "notch question",
      assistantText: "notch answer",
      logLabel: "floating"
    )

    let main = provider.automationMainChatSnapshot(limit: 20)
    let floating = provider.automationFloatingChatSnapshot(limit: 20)

    XCTAssertEqual(main["message_count"], "4")
    XCTAssertEqual(main["message_count"], floating["message_count"])
    XCTAssertEqual(main["is_sending"], floating["is_sending"])
    XCTAssertEqual(main["runtime_chat_id"], floating["runtime_chat_id"])

    let mainRows = try Self.decodeSnapshotRows(main["messages_json"])
    let floatingRows = try Self.decodeSnapshotRows(floating["messages_json"])
    XCTAssertEqual(mainRows, floatingRows)
    XCTAssertEqual(mainRows.map { $0["text"] }, [
      "main question", "main answer", "notch question", "notch answer",
    ])
  }

  /// INV-6: restaging the same pill_completion key must merge resources onto the
  /// producing assistant message — never invent a second artifact-only turn.
  func testRestagingSameContinuityKeyMergesResourcesOntoProducingMessage() {
    let provider = ChatProvider()
    let key = "pill_completion:run-merge"
    let completionBlock = ChatContentBlock.agentCompletion(
      id: "completion-merge",
      pillId: UUID(),
      sessionId: "sess-merge",
      runId: "run-merge",
      title: "Draft Example AGENTS.md",
      promptSnippet: "Draft Example AGENTS.md",
      output: "Done.",
      status: "completed"
    )
    let first = provider.stageOptimisticTurn(
      continuityKey: key,
      userText: "",
      assistantText: "[Background agent — Draft Example AGENTS.md] Done.",
      origin: "pill_completion",
      turnOwner: .mainChat,
      contentBlocks: [completionBlock]
    )
    XCTAssertEqual(provider.messages.filter { $0.sender == .ai }.count, 1)
    XCTAssertTrue(first.assistant?.resources.isEmpty ?? false)

    let resource = ChatResource.localGeneratedFile(
      id: "agents-md",
      title: "AGENTS.md",
      subtitle: "text/markdown",
      mimeType: "text/markdown",
      uri: "file:///tmp/AGENTS.md"
    )
    let second = provider.stageOptimisticTurn(
      continuityKey: key,
      userText: "",
      assistantText: "[Background agent — Draft Example AGENTS.md] Done.",
      origin: "pill_completion",
      turnOwner: .mainChat,
      contentBlocks: [completionBlock],
      resources: [resource]
    )

    let assistants = provider.messages.filter { $0.sender == .ai }
    XCTAssertEqual(assistants.count, 1)
    XCTAssertEqual(second.assistant?.id, first.assistant?.id)
    XCTAssertEqual(assistants.first?.resources.map(\.id), ["agents-md"])
    XCTAssertEqual(assistants.first?.contentBlocks.count, 1)
  }

  /// INV-6: resources stay on the producing assistant message through stage+promote;
  /// do not invent a second artifact-only turn for the same pill_completion key.
  func testResourcesStayOnProducingMessageThroughStageAndPromote() {
    let provider = ChatProvider()
    let projection = provider.kernelTurnProjection
    let surface = provider.mainChatSurfaceReference()
    let key = "pill_completion:run-resources"
    let resource = ChatResource.localGeneratedFile(
      id: "artifact-owned",
      title: "report.md",
      subtitle: "text/markdown",
      mimeType: "text/markdown",
      uri: "file:///tmp/report.md"
    )
    let completionBlock = ChatContentBlock.agentCompletion(
      id: "completion-res",
      pillId: UUID(),
      sessionId: "sess-res",
      runId: "run-resources",
      title: "Background agent",
      promptSnippet: "write report",
      output: "Done.",
      status: "completed"
    )

    let staged = provider.stageOptimisticTurn(
      continuityKey: key,
      userText: "",
      assistantText: "[Background agent — write report] Done.",
      origin: "pill_completion",
      turnOwner: .mainChat,
      contentBlocks: [completionBlock],
      resources: [resource]
    )
    XCTAssertEqual(provider.messages.filter { $0.sender == .ai }.count, 1)
    XCTAssertEqual(staged.assistant?.resources.map(\.id), ["artifact-owned"])
    XCTAssertEqual(
      ChatContinuityInvariants.resourcesBelongingToMessages(
        messages: provider.messages,
        messageIds: Set(provider.messages.map(\.id))
      ).map(\.id),
      ["artifact-owned"]
    )

    projection.apply(
      .init(
        conversationId: "conv-1",
        surfaceKind: surface.surfaceKind,
        externalRefKind: surface.externalRefKind,
        externalRefId: surface.externalRefId,
        userText: "",
        assistantText: "[Background agent — write report] Done.",
        origin: "pill_completion",
        interrupted: false,
        idempotencyKey: key,
        userTurnId: nil,
        assistantTurnId: nil
      )
    )

    let assistants = provider.messages.filter { $0.sender == .ai }
    XCTAssertEqual(assistants.count, 1)
    XCTAssertEqual(assistants.first?.id, staged.assistant?.id)
    XCTAssertEqual(assistants.first?.resources.map(\.id), ["artifact-owned"])
    // Orphan filter: resources for a non-viewport / unknown id must be empty.
    XCTAssertTrue(
      ChatContinuityInvariants.resourcesBelongingToMessages(
        messages: provider.messages,
        messageIds: ["not-a-message"]
      ).isEmpty
    )
  }

  private static func decodeSnapshotRows(_ json: String?) throws -> [[String: String]] {
    guard let json, let data = json.data(using: .utf8) else {
      throw NSError(domain: "KernelTurnRecordedProjectionTests", code: 1)
    }
    let rows = try JSONSerialization.jsonObject(with: data) as? [[String: String]]
    guard let rows else {
      throw NSError(domain: "KernelTurnRecordedProjectionTests", code: 2)
    }
    return rows
  }
}
