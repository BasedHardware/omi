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

    let first = provider.stageOptimisticTurn(
      continuityKey: key,
      userText: "",
      assistantText: summary,
      origin: "pill_completion",
      turnOwner: .mainChat,
      resources: [resource]
    )
    XCTAssertNotNil(first.assistant)
    XCTAssertEqual(first.assistant?.resources.count, 1)

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
    XCTAssertEqual(provider.messages.first(where: { $0.sender == .ai })?.resources.count, 1)
    XCTAssertFalse(provider.hasOptimisticTurn(continuityKey: key))
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
