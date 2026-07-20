import XCTest

@testable import Omi_Computer

/// Regression coverage for two chat write-path defects on the kernel journal
/// projection path (INV-6):
///
///  1. `ChatJournalWriteCoordinator` permanently blocked *every* journal write
///     for a turn once it terminalized (the `terminalizingMessageIDs` set is
///     only cleared on auth change). Streaming coalesces must stay blocked — they
///     would regress a terminalized turn back to `streaming` — but durable
///     content mutations (discovery cards, tool-call finalization, orphan
///     finalization, kernel resource refreshes) carry no streaming status and
///     were silently dropped for the rest of the session.
///
///  2. `ChatProvider.projectJournalTurn` replaced a row wholesale on every
///     journal replay, preserving only `rating`. Fields the journal never
///     persists and `KernelJournalTurn.chatMessage()` cannot reconstruct —
///     `metadata` (model/token/cost stats shown in the message footer) and
///     `notificationScreenshot` — were clobbered the instant a completed turn
///     was refreshed, so the footer stats vanished from the just-answered turn.
@MainActor
final class ChatJournalWritePathTests: XCTestCase {

  // MARK: - Bug 1: terminalization gate only supersedes streaming writes

  func testStreamingWriteIsSupersededAfterTerminalization() async {
    let coordinator = ChatJournalWriteCoordinator()
    let messageID = "assistant-turn-1"

    XCTAssertTrue(
      coordinator.schedule(messageID: messageID, supersededByTerminalization: true) {},
      "A streaming write should be accepted before terminalization")

    let didBegin = await coordinator.beginTerminalization(messageID: messageID)
    XCTAssertTrue(didBegin)

    XCTAssertFalse(
      coordinator.schedule(messageID: messageID, supersededByTerminalization: true) {},
      "A streaming coalesce must be refused once the turn is terminalizing — it would regress the terminal status")
  }

  func testDurableWriteRemainsJournalableAfterTerminalization() async {
    let coordinator = ChatJournalWriteCoordinator()
    let messageID = "assistant-turn-2"

    let didBegin = await coordinator.beginTerminalization(messageID: messageID)
    XCTAssertTrue(didBegin)

    let ran = expectation(description: "durable post-terminal operation executes")
    let accepted = coordinator.schedule(messageID: messageID, supersededByTerminalization: false) {
      ran.fulfill()
    }

    XCTAssertTrue(
      accepted,
      "A durable (non-streaming) content update must remain journalable after terminalization — "
        + "discovery cards, tool-call finalization and resource refreshes depend on it")
    await fulfillment(of: [ran], timeout: 2.0)
  }

  func testPostTerminalArtifactDeliveryProjectsReadyResourceCard() async throws {
    let provider = ChatProvider()
    let surface = provider.mainChatSurfaceReference()
    let coordinator = ChatJournalWriteCoordinator()
    let messageID = "assistant-post-terminal-artifact"
    let artifactURL = FileManager.default.temporaryDirectory
      .appendingPathComponent("post-terminal-artifact-\(UUID().uuidString).html")
    try "<h1>Artifact card</h1>".write(to: artifactURL, atomically: true, encoding: .utf8)
    defer { try? FileManager.default.removeItem(at: artifactURL) }

    let resource = ChatResource.localGeneratedFile(
      id: "artifact:post-terminal",
      title: "post-terminal-artifact.html",
      subtitle: "text/html",
      mimeType: "text/html",
      uri: artifactURL.absoluteString
    )
    let resourcePayload = KernelJournalTurnWrite.jsonArray(
      try XCTUnwrap(ChatResource.encodeResourcesForPersistence([resource])))
    let terminalTurn = try makeTurn(
      surface: surface,
      turnId: messageID,
      turnSeq: 1,
      content: "Artifact ready",
      status: .completed,
      resources: resourcePayload
    )

    provider.projectJournalTurn(
      try makeTurn(
        surface: surface,
        turnId: messageID,
        turnSeq: 1,
        content: "Building the artifact",
        status: .streaming
      ))
    let didBegin = await coordinator.beginTerminalization(messageID: messageID)
    XCTAssertTrue(didBegin)

    let projected = expectation(description: "post-terminal artifact is projected")
    let accepted = coordinator.schedule(
      messageID: messageID,
      supersededByTerminalization: false
    ) {
      provider.projectJournalTurn(terminalTurn)
      projected.fulfill()
    }

    XCTAssertTrue(accepted, "A post-terminal artifact delivery must not be dropped")
    await fulfillment(of: [projected], timeout: 2.0)

    let message = try XCTUnwrap(provider.messages.first { $0.id == messageID })
    XCTAssertEqual(message.journalStatus, .completed)
    XCTAssertEqual(message.displayResources, [resource])
    XCTAssertEqual(message.displayResources.first?.state, .ready)
  }

  func testDurableAndStreamingWritesAreBothAcceptedBeforeTerminalization() {
    let coordinator = ChatJournalWriteCoordinator()
    let messageID = "assistant-turn-3"
    XCTAssertTrue(coordinator.schedule(messageID: messageID, supersededByTerminalization: true) {})
    XCTAssertTrue(coordinator.schedule(messageID: messageID, supersededByTerminalization: false) {})
  }

  func testTerminalizationRetriesOneFailedIdempotentProjection() async {
    let coordinator = ChatJournalWriteCoordinator()
    var attempts = 0

    let accepted = await coordinator.retryTerminalization {
      attempts += 1
      return attempts == 2
    }

    XCTAssertTrue(accepted)
    XCTAssertEqual(attempts, 2, "Terminalization retries exactly once after a transient failure")
  }

  func testTerminalizationRetryIsBounded() async {
    let coordinator = ChatJournalWriteCoordinator()
    var attempts = 0

    let accepted = await coordinator.retryTerminalization {
      attempts += 1
      return false
    }

    XCTAssertFalse(accepted)
    XCTAssertEqual(attempts, 2, "A persistent journal failure must not retry indefinitely")
  }

  func testAcceptedTerminalPayloadWinsOverStaleStreamingProjection() {
    let full = "RELAUNCH-PERSIST-1784573311"
    let retainedResource = ChatResource.localGeneratedFile(
      id: "artifact:relaunch",
      title: "durable-result.txt",
      subtitle: "text/plain",
      mimeType: "text/plain",
      uri: "file:///tmp/durable-result.txt")
    let staleStreamingMessage = ChatMessage(
      id: "attempt-relaunch-assistant",
      text: "RELAUNCH-PERSIST-1",
      sender: .ai,
      isStreaming: true,
      contentBlocks: [
        .text(id: "attempt-relaunch-assistant:stream", text: "RELAUNCH-PERSIST-1"),
        .thinking(id: "attempt-relaunch-assistant:thinking", text: "Retain this non-text block"),
      ],
      resources: [retainedResource]
    )

    let terminalText = KernelTurnProjection.acceptedTerminalContent(
      message: staleStreamingMessage,
      acceptedContent: full)
    let blocks = KernelTurnProjection.acceptedTerminalContentBlocks(
      message: staleStreamingMessage,
      acceptedContent: full
    )
    XCTAssertEqual(
      terminalText, full, "The accepted agent result, not a stale UI buffer, is canonical terminal content")
    XCTAssertEqual(blocks.count, 2)
    guard case .text(let id, let text) = blocks[0] else {
      return XCTFail("Terminal payload must start with one authoritative text block")
    }
    XCTAssertEqual(id, "attempt-relaunch-assistant:terminal")
    XCTAssertEqual(text, full)
    guard case .thinking(let thinkingID, let thinkingText) = blocks[1] else {
      return XCTFail("Terminal payload must retain non-text streaming blocks")
    }
    XCTAssertEqual(thinkingID, "attempt-relaunch-assistant:thinking")
    XCTAssertEqual(thinkingText, "Retain this non-text block")
    XCTAssertEqual(staleStreamingMessage.displayResources, [retainedResource])
  }

  func testEmptyAcceptedContentKeepsTheIntentionalStreamingProjection() {
    let message = ChatMessage(
      id: "attempt-empty-terminal",
      text: "intentional partial response",
      sender: .ai,
      isStreaming: true,
      contentBlocks: [.text(id: "attempt-empty-terminal:stream", text: "intentional partial response")]
    )

    XCTAssertEqual(
      KernelTurnProjection.acceptedTerminalContent(message: message, acceptedContent: ""),
      "intentional partial response")
    let blocks = KernelTurnProjection.acceptedTerminalContentBlocks(message: message, acceptedContent: "")
    guard let first = blocks.first, case .text(let id, let text) = first else {
      return XCTFail("An intentional empty result must keep the current structured projection")
    }
    XCTAssertEqual(id, "attempt-empty-terminal:stream")
    XCTAssertEqual(text, "intentional partial response")
  }

  // MARK: - Bug 2: projection preserves local-only fields across replay

  func testProjectionPreservesLocalOnlyFieldsAcrossTerminalReplay() throws {
    let provider = ChatProvider()
    let surface = provider.mainChatSurfaceReference()

    // A completed turn lands from the kernel journal.
    provider.projectJournalTurn(
      try makeTurn(surface: surface, turnId: "assistant-1", turnSeq: 1, content: "Draft answer"))
    XCTAssertEqual(provider.messages.count, 1)

    // The query-completion handler attaches local-only state the journal never
    // persists: model/token/cost metadata, a user rating, a screenshot.
    let index = try XCTUnwrap(provider.messages.firstIndex { $0.id == "assistant-1" })
    provider.messages[index].metadata = MessageMetadata(
      model: "claude-sonnet",
      inputTokens: 100,
      outputTokens: 42,
      cacheReadTokens: nil,
      cacheWriteTokens: nil,
      costUsd: 0.0123,
      systemPrompt: nil,
      hasScreenshot: false,
      screenshotSizeBytes: nil,
      toolNames: ["execute_sql"],
      sqlRowsReturned: 7,
      sqlQueryCount: 2
    )
    provider.messages[index].rating = 1
    let screenshot = Data([0x0A, 0x0B, 0x0C])
    provider.messages[index].notificationScreenshot = screenshot

    // Terminalization refreshes the journal, replaying the same turn. The kernel
    // is authority for content, so the text updates...
    provider.projectJournalTurn(
      try makeTurn(surface: surface, turnId: "assistant-1", turnSeq: 1, content: "Final answer"))

    XCTAssertEqual(provider.messages.count, 1)
    let refreshed = try XCTUnwrap(provider.messages.first { $0.id == "assistant-1" })
    XCTAssertEqual(refreshed.text, "Final answer")

    // ...but the local-only fields must survive the wholesale row replace.
    XCTAssertEqual(refreshed.metadata?.model, "claude-sonnet")
    XCTAssertEqual(refreshed.metadata?.outputTokens, 42)
    XCTAssertEqual(refreshed.metadata?.sqlRowsReturned, 7)
    XCTAssertEqual(refreshed.rating, 1)
    XCTAssertEqual(refreshed.notificationScreenshot, screenshot)
  }

  func testProjectionCarryingHelperPrefersProjectedFieldWhenPresent() {
    // If the journal ever starts carrying one of these fields, the projected
    // (kernel-authoritative) value must win over the local carry-forward.
    let existing = ChatMessage(id: "m", text: "old", sender: .ai, rating: -1)
    var projected = ChatMessage(id: "m", text: "new", sender: .ai)
    projected.rating = 1

    let merged = ChatProvider.carryingLocalOnlyFields(projected, from: existing)
    XCTAssertEqual(merged.rating, 1, "A non-nil projected rating wins over the local value")

    let carried = ChatProvider.carryingLocalOnlyFields(
      ChatMessage(id: "m", text: "new", sender: .ai), from: existing)
    XCTAssertEqual(carried.rating, -1, "A nil projected rating falls back to the local value")
  }

  // MARK: - Helpers

  private func makeTurn(
    surface: AgentSurfaceReference,
    turnId: String,
    turnSeq: Int,
    role: String = "assistant",
    content: String,
    status: KernelJournalTurnStatus = .completed,
    resources: [Any] = []
  ) throws -> KernelJournalTurn {
    try XCTUnwrap(
      KernelJournalTurn(dictionary: [
        "conversationId": "conversation-1",
        "turnId": turnId,
        "turnSeq": turnSeq,
        "conversationGeneration": 1,
        "generationBaseTurnSeq": 0,
        "producerId": "producer:\(turnId)",
        "payloadHash": "sha256:\(turnId)",
        "role": role,
        "surfaceKind": surface.surfaceKind,
        "externalRefKind": surface.externalRefKind,
        "externalRefId": surface.externalRefId,
        "content": content,
        "origin": "test",
        "status": status.rawValue,
        "contentBlocks": [],
        "resources": resources,
        "metadataJson": "{}",
        "createdAtMs": 1_700_000_000_000 + turnSeq,
        "updatedAtMs": 1_700_000_000_000 + turnSeq,
      ]))
  }
}
