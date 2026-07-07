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
}
