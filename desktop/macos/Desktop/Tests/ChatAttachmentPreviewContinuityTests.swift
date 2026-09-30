import XCTest

@testable import Omi_Computer

/// The sent attachment tile renders its image from, in order: in-memory bytes,
/// the original picked file, the server thumbnail (`ChatResourceCard.resourceImage`).
/// The kernel journal persists resource metadata only, so a journaled user row
/// arrives without the bytes the pick loaded — and a file picked out of an
/// app-owned temp export (a Quick Look frame, a pasted screenshot's staging
/// file) can disappear moments later, collapsing the tile to the gray
/// placeholder. These tests pin the bytes to the admitted row and its echoes.
@MainActor
final class ChatAttachmentPreviewContinuityTests: XCTestCase {

  /// The reported bug: attach a screenshot, send it, and the sent tile goes
  /// blank once the picked temp file is purged. The admitted turn must keep
  /// rendering from the bytes the pick already loaded.
  func testAdmittedAttachmentTurnKeepsImageBytesWhenPickedFileDisappears() async throws {
    let provider = ChatProvider()
    let surface = provider.mainChatSurfaceReference()

    // A picked screenshot living in a temp export, with the bytes the pick read.
    let pickedFile = FileManager.default.temporaryDirectory
      .appendingPathComponent("frame-\(UUID().uuidString).jpg")
    let imageBytes = Data([0xFF, 0xD8, 0xFF, 0xE0, 0x00, 0x01])
    try imageBytes.write(to: pickedFile)
    // The Quick Look scratch purge removes the export while the chat keeps the row.
    try FileManager.default.removeItem(at: pickedFile)
    XCTAssertFalse(FileManager.default.fileExists(atPath: pickedFile.path))

    let attachment = ChatAttachment(
      id: "local-1",
      fileName: pickedFile.lastPathComponent,
      mimeType: "image/jpeg",
      data: imageBytes,
      serverId: "file-1",
      localFileURL: pickedFile,
      state: .uploaded
    )
    let userMessage = ChatMessage(
      id: "turn-user",
      clientTurnId: "attempt-1",
      text: "look at this",
      sender: .user,
      attachments: [attachment],
      resources: ChatResource.userMessageResources(attachments: [attachment], references: [])
    )
    let assistantMessage = ChatMessage(
      id: "turn-assistant",
      clientTurnId: "attempt-1",
      text: "",
      sender: .ai,
      isStreaming: true
    )

    // The kernel admits the exchange and publishes the rows back from its
    // journal — the same encode the write path performs, which drops image bytes.
    let echoed: [KernelJournalTurn] = [
      try makeTurn(
        surface: surface,
        turnId: userMessage.id,
        turnSeq: 1,
        role: "user",
        content: userMessage.text,
        status: .completed,
        resourcesJSON: userMessage.journalWrite(
          origin: "typed",
          status: .completed,
          continuityKey: "attempt-1"
        ).resourcesJSON),
      try makeTurn(
        surface: surface,
        turnId: assistantMessage.id,
        turnSeq: 2,
        role: "assistant",
        content: assistantMessage.text,
        status: .streaming,
        resourcesJSON: "[]"),
    ]
    let admitted = await provider.admitStreamingJournalExchange(
      userMessage: userMessage,
      assistantMessage: assistantMessage
    ) { _ in
      for turn in echoed {
        provider.projectJournalTurn(turn)
      }
      return echoed
    }

    XCTAssertTrue(admitted, "The exchange must be admitted for the row to exist at all")
    let userRow = try XCTUnwrap(provider.messages.first { $0.id == "turn-user" })
    let resource = try XCTUnwrap(userRow.displayResources.first)
    XCTAssertEqual(
      resource.imageData, imageBytes,
      "The sent tile must render from the picked bytes once the temp file is gone")
  }

  /// A later journal echo still owns every field it persists (a refreshed
  /// thumbnail wins) while the bytes the journal cannot carry survive the replace.
  func testJournalEchoRefreshesThumbnailButKeepsCarriedImageBytes() async throws {
    let provider = ChatProvider()
    let surface = provider.mainChatSurfaceReference()
    let pickedFile = FileManager.default.temporaryDirectory
      .appendingPathComponent("kept-frame-\(UUID().uuidString).jpg")
    let imageBytes = Data([0xFF, 0xD8, 0xFF, 0xE0, 0x02])
    try imageBytes.write(to: pickedFile)
    defer { try? FileManager.default.removeItem(at: pickedFile) }

    let resource = ChatResource(
      id: "attachment:file-1",
      origin: .userAttachment,
      title: "frame-3e8b6ff8-AC51-A8890605A5B5.jpg",
      subtitle: "image/jpeg",
      mimeType: "image/jpeg",
      thumbnailURL: "https://example.com/thumb-1.jpg",
      imageData: imageBytes,
      uri: pickedFile.absoluteString,
      artifactId: nil,
      sessionId: nil,
      runId: nil,
      state: .ready
    )
    let userMessage = ChatMessage(
      id: "turn-user",
      clientTurnId: "attempt-2",
      text: "look",
      sender: .user,
      resources: [resource]
    )
    let assistantMessage = ChatMessage(
      id: "turn-assistant",
      clientTurnId: "attempt-2",
      text: "",
      sender: .ai,
      isStreaming: true
    )

    let echoed: [KernelJournalTurn] = [
      try makeTurn(
        surface: surface,
        turnId: userMessage.id,
        turnSeq: 1,
        role: "user",
        content: userMessage.text,
        status: .completed,
        resourcesJSON: ChatResource.encodeResourcesForPersistence(userMessage.displayResources)
          ?? "[]"),
      try makeTurn(
        surface: surface,
        turnId: assistantMessage.id,
        turnSeq: 2,
        role: "assistant",
        content: assistantMessage.text,
        status: .streaming,
        resourcesJSON: "[]"),
    ]
    let admitted = await provider.admitStreamingJournalExchange(
      userMessage: userMessage,
      assistantMessage: assistantMessage
    ) { _ in
      for turn in echoed {
        provider.projectJournalTurn(turn)
      }
      return echoed
    }
    XCTAssertTrue(admitted)

    // The kernel later replays the user turn having refreshed the thumbnail.
    let refreshed = ChatResource(
      id: resource.id,
      origin: resource.origin,
      title: resource.title,
      subtitle: resource.subtitle,
      mimeType: resource.mimeType,
      thumbnailURL: "https://example.com/thumb-2.jpg",
      imageData: nil,
      uri: resource.uri,
      artifactId: nil,
      sessionId: nil,
      runId: nil,
      state: resource.state
    )
    provider.projectJournalTurn(
      try makeTurn(
        surface: surface,
        turnId: "turn-user",
        turnSeq: 3,
        role: "user",
        content: "look",
        status: .completed,
        resourcesJSON: ChatResource.encodeResourcesForPersistence([refreshed]) ?? "[]"))

    let userRow = try XCTUnwrap(provider.messages.first { $0.id == "turn-user" })
    let echoedResource = try XCTUnwrap(userRow.displayResources.first)
    XCTAssertEqual(
      echoedResource.thumbnailURL, "https://example.com/thumb-2.jpg",
      "The journal owns the thumbnail and its refreshed value must win")
    XCTAssertEqual(
      echoedResource.imageData, imageBytes,
      "The echo must not strip the bytes the journal never persisted")
  }

  /// Byte carry is id-matched and never overrides bytes the row already has.
  func testCarryingImageDataOnlyFillsMissingBytesForMatchingIDs() {
    let bytes = Data([0xFF, 0xD8, 0xFF])
    let local = ChatResource(
      id: "attachment:file-1", origin: .userAttachment, title: "a.jpg", subtitle: nil,
      mimeType: "image/jpeg", thumbnailURL: nil, imageData: bytes, uri: nil,
      artifactId: nil, sessionId: nil, runId: nil, state: .ready)
    let replayed = ChatResource(
      id: "attachment:file-1", origin: .userAttachment, title: "a.jpg", subtitle: nil,
      mimeType: "image/jpeg", thumbnailURL: nil, imageData: nil, uri: nil,
      artifactId: nil, sessionId: nil, runId: nil, state: .ready)
    let otherID = ChatResource(
      id: "attachment:file-2", origin: .userAttachment, title: "b.jpg", subtitle: nil,
      mimeType: "image/jpeg", thumbnailURL: nil, imageData: nil, uri: nil,
      artifactId: nil, sessionId: nil, runId: nil, state: .ready)
    let ownBytes = Data([0x89, 0x50])
    let selfSufficient = ChatResource(
      id: "attachment:file-1", origin: .userAttachment, title: "a.jpg", subtitle: nil,
      mimeType: "image/jpeg", thumbnailURL: nil, imageData: ownBytes, uri: nil,
      artifactId: nil, sessionId: nil, runId: nil, state: .ready)

    let carried = ChatResource.carryingImageData([replayed, otherID, selfSufficient], from: [local])

    XCTAssertEqual(carried[0].imageData, bytes, "A matching id with missing bytes is filled")
    XCTAssertNil(carried[1].imageData, "A resource the local row never had gains nothing")
    XCTAssertEqual(carried[2].imageData, ownBytes, "Bytes the row already has are not overridden")
  }

  // MARK: - Journal turn builder (the dictionary the kernel bridge returns)

  private func makeTurn(
    surface: AgentSurfaceReference,
    turnId: String,
    turnSeq: Int,
    role: String,
    content: String,
    status: KernelJournalTurnStatus,
    resourcesJSON: String
  ) throws -> KernelJournalTurn {
    try XCTUnwrap(
      KernelJournalTurn(dictionary: [
        "conversationId": "conversation-1",
        "turnId": turnId,
        "turnSeq": turnSeq,
        "conversationGeneration": 1,
        "generationBaseTurnSeq": 0,
        "producerId": "producer:\(turnId):\(turnSeq)",
        "payloadHash": "sha256:\(turnId):\(turnSeq)",
        "role": role,
        "surfaceKind": surface.surfaceKind,
        "externalRefKind": surface.externalRefKind,
        "externalRefId": surface.externalRefId,
        "content": content,
        "origin": "typed",
        "status": status.rawValue,
        "contentBlocks": [],
        "resources": KernelJournalTurnWrite.jsonArray(resourcesJSON),
        "metadataJson": "{}",
        "createdAtMs": 1_700_000_000_000 + turnSeq,
        "updatedAtMs": 1_700_000_000_000 + turnSeq,
      ]))
  }
}
