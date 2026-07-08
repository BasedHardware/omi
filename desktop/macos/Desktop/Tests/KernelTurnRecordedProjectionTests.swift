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

    // Terminal path reuses the same key (artifact already staged).
    let second = provider.stageOptimisticTurn(
      continuityKey: key,
      userText: "",
      assistantText: summary,
      origin: "pill_completion",
      turnOwner: .mainChat
    )
    XCTAssertEqual(second.assistant?.id, first.assistant?.id)
    XCTAssertEqual(provider.messages.filter { $0.sender == .ai }.count, 1)
    XCTAssertEqual(provider.messages.first(where: { $0.sender == .ai })?.resources.count, 1)

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
    XCTAssertEqual(promoted?.resources.count, 1)
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
