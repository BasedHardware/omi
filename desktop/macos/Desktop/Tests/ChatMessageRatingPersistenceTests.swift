import XCTest

@testable import Omi_Computer

@MainActor
final class ChatMessageRatingPersistenceTests: XCTestCase {

  func testFinishedUnsyncedReplyWaitsForJournalSync() {
    let message = ChatMessage(
      id: "live-tail",
      text: "Done.",
      sender: .ai,
      isStreaming: false,
      isSynced: false,
      journalStatus: .completed)

    XCTAssertEqual(ChatMessageRatingPersistence.of(message), .waitForSync)
    XCTAssertEqual(ChatBubbleMetadataBand.of(message), .actions)
  }

  func testSyncedReplyPersistsImmediately() {
    let message = ChatMessage(
      id: "synced",
      text: "Done.",
      sender: .ai,
      isStreaming: false,
      isSynced: true,
      journalStatus: .completed)

    XCTAssertEqual(ChatMessageRatingPersistence.of(message), .persistNow)
  }

  func testFailedJournalStaysLocalOnly() {
    let message = ChatMessage(
      id: "failed-tail",
      text: "Partial answer.",
      sender: .ai,
      isStreaming: false,
      isSynced: false,
      journalStatus: .failed)

    XCTAssertEqual(ChatMessageRatingPersistence.of(message), .localOnly)
    XCTAssertEqual(ChatBubbleMetadataBand.of(message), .actions)
  }

  func testQueueLastWriteWinsUntilDrain() {
    var queue = ChatMessageRatingQueue()
    let unsynced = ChatMessage(id: "m1", text: "Done.", sender: .ai, isSynced: false)
    queue.enqueue(messageId: "m1", rating: 1)
    queue.enqueue(messageId: "m1", rating: -1)

    XCTAssertTrue(queue.contains("m1"))
    XCTAssertTrue(queue.drain(using: [unsynced]).isEmpty, "Unsynced rows must stay queued")
    XCTAssertTrue(queue.contains("m1"))

    let synced = ChatMessage(id: "m1", text: "Done.", sender: .ai, isSynced: true)
    let ready = queue.drain(using: [synced])
    XCTAssertEqual(ready.count, 1)
    XCTAssertEqual(ready.first?.messageId, "m1")
    XCTAssertEqual(ready.first?.rating, -1)
    XCTAssertTrue(queue.isEmpty)
  }

  func testQueuedRatingCarriesReasonThroughSync() {
    var queue = ChatMessageRatingQueue()
    queue.enqueue(messageId: "m1", rating: -1, reason: .alreadyDone)
    let synced = ChatMessage(id: "m1", text: "Done.", sender: .ai, isSynced: true)
    let ready = queue.drain(using: [synced])
    XCTAssertEqual(ready.first?.reason, .alreadyDone)
  }

  func testQueuedVoiceRatingKeepsItsSurfaceThroughSync() {
    // A floating-bar thumb on an unsynced reply waits in the queue; when it
    // drains after sync it must still identify as a voice rating — silently
    // defaulting to text at flush time corrupts the text/voice ratio split.
    var queue = ChatMessageRatingQueue()
    queue.enqueue(messageId: "m1", rating: 1, surface: "voice")

    let unsynced = ChatMessage(id: "m1", text: "Done.", sender: .ai, isSynced: false)
    XCTAssertTrue(queue.drain(using: [unsynced]).isEmpty)

    let synced = ChatMessage(id: "m1", text: "Done.", sender: .ai, isSynced: true)
    let ready = queue.drain(using: [synced])
    XCTAssertEqual(ready.count, 1)
    XCTAssertEqual(ready.first?.surface, "voice")
    XCTAssertEqual(ready.first?.rating, 1)
  }

  func testQueuedRatingKeepsItsReasonThroughSync() {
    // Same failure mode as the surface test above, one field over: a
    // thumbs-down given on a reply that has not synced yet waits in the queue,
    // and the reason must survive the drain. Dropping it at flush would send a
    // reasonless rating, and the daily report would file the user's answer
    // under "not_captured" — indistinguishable from never having asked.
    var queue = ChatMessageRatingQueue()
    queue.enqueue(
      messageId: "m1", rating: -1, surface: "text", reason: .incorrectOrHallucination)

    let unsynced = ChatMessage(id: "m1", text: "Done.", sender: .ai, isSynced: false)
    XCTAssertTrue(queue.drain(using: [unsynced]).isEmpty)

    let synced = ChatMessage(id: "m1", text: "Done.", sender: .ai, isSynced: true)
    let ready = queue.drain(using: [synced])
    XCTAssertEqual(ready.count, 1)
    XCTAssertEqual(ready.first?.reason, .incorrectOrHallucination)
    XCTAssertEqual(ready.first?.rating, -1)
  }

  func testQueueDefaultsToNoReason() {
    var queue = ChatMessageRatingQueue()
    queue.enqueue(messageId: "m1", rating: -1)
    let synced = ChatMessage(id: "m1", text: "Done.", sender: .ai, isSynced: true)
    XCTAssertNil(queue.drain(using: [synced]).first?.reason)
  }

  func testQueueDefaultsToTextSurface() {
    var queue = ChatMessageRatingQueue()
    queue.enqueue(messageId: "m1", rating: -1)
    let synced = ChatMessage(id: "m1", text: "Done.", sender: .ai, isSynced: true)
    XCTAssertEqual(queue.drain(using: [synced]).first?.surface, "text")
  }

  func testQueueDrainsClearedRatingAfterSync() {
    var queue = ChatMessageRatingQueue()
    queue.enqueue(messageId: "m1", rating: 1)
    queue.enqueue(messageId: "m1", rating: nil)

    XCTAssertTrue(queue.contains("m1"))
    let unsynced = ChatMessage(id: "m1", text: "Done.", sender: .ai, isSynced: false)
    XCTAssertTrue(queue.drain(using: [unsynced]).isEmpty)

    let synced = ChatMessage(id: "m1", text: "Done.", sender: .ai, isSynced: true)
    let ready = queue.drain(using: [synced])
    XCTAssertEqual(ready.count, 1)
    XCTAssertEqual(ready.first?.messageId, "m1")
    XCTAssertNil(ready.first?.rating)
    XCTAssertTrue(queue.isEmpty)
  }

  func testProactiveNotificationRatingResolvesToNotificationSurface() {
    // A thumb on a proactive-notification message (focus/insight/task/memory
    // card in the transcript) rates the notification, not a general Omi
    // answer — it must report source="notification" so the admin response
    // quality % can exclude it, no matter which surface the caller passed.
    let notification = ChatMessage(
      id: "n1",
      clientTurnId: ChatContinuityInvariants.proactiveNotificationContinuityKey(
        id: UUID(), kind: .insight),
      text: "You seem distracted.",
      sender: .ai,
      isSynced: true)
    XCTAssertEqual(
      ChatProvider.ratingSurface(for: notification, requested: "text"), "notification")
    XCTAssertEqual(
      ChatProvider.ratingSurface(for: notification, requested: "voice"), "notification")

    let answer = ChatMessage(id: "a1", text: "Done.", sender: .ai, isSynced: true)
    XCTAssertEqual(ChatProvider.ratingSurface(for: answer, requested: "text"), "text")
    XCTAssertEqual(ChatProvider.ratingSurface(for: nil, requested: "voice"), "voice")
  }

  func testUnsyncedProactiveRatingKeepsNotificationSurfaceThroughFlush() async {
    // Real deferred path: a thumb on an UNSYNCED proactive-notification
    // message goes rateMessage → queue → post-sync drain. The resolved
    // "notification" surface must be what drains — not the caller's "text".
    let provider = ChatProvider()
    let messageId = "proactive-live"
    let unsynced = ChatMessage(
      id: messageId,
      clientTurnId: ChatContinuityInvariants.proactiveNotificationContinuityKey(
        id: UUID(), kind: .task),
      text: "You said you'd email Alex today.",
      sender: .ai,
      isStreaming: false,
      isSynced: false,
      journalStatus: .completed)
    provider.messages = [unsynced]

    await provider.rateMessage(messageId, rating: -1, surface: "text")
    XCTAssertTrue(provider.pendingMessageRatings.contains(messageId))

    provider.messages[0].isSynced = true
    let ready = provider.pendingMessageRatings.drain(using: provider.messages)
    XCTAssertEqual(ready.count, 1)
    XCTAssertEqual(ready.first?.surface, "notification")
    XCTAssertEqual(ready.first?.rating, -1)
  }

  func testQueueDropsFailedJournalWithoutPersist() {
    var queue = ChatMessageRatingQueue()
    queue.enqueue(messageId: "m1", rating: 1)
    let failed = ChatMessage(
      id: "m1",
      text: "Partial answer.",
      sender: .ai,
      isSynced: false,
      journalStatus: .failed)

    XCTAssertTrue(queue.drain(using: [failed]).isEmpty)
    XCTAssertTrue(queue.isEmpty)
  }

  func testUnsyncedReplyQueuesRatingUntilJournalRemoteIdLands() async throws {
    let provider = ChatProvider()
    let surface = provider.mainChatSurfaceReference()
    let messageId = "assistant-live-rating"
    let persisted = expectation(description: "queued rating PATCHes after journal remote id")
    provider.persistMessageRatingHandler = { persistedId, rating in
      XCTAssertEqual(persistedId, messageId)
      XCTAssertEqual(rating, 1)
      persisted.fulfill()
    }
    provider.messages = [
      ChatMessage(
        id: messageId,
        text: "I'll look that up.",
        sender: .ai,
        isStreaming: false,
        isSynced: false,
        journalStatus: .completed)
    ]

    XCTAssertEqual(provider.queueMessageRating(messageId, rating: 1), .waitForSync)
    XCTAssertEqual(provider.messages.first?.rating, 1)
    XCTAssertTrue(provider.pendingMessageRatings.contains(messageId))

    provider.projectJournalTurn(
      try makeTurn(surface: surface, turnId: messageId, content: "I'll look that up.", remoteId: "srv-42"))

    await fulfillment(of: [persisted], timeout: 1.0)
    XCTAssertEqual(provider.messages.first?.rating, 1)
    XCTAssertFalse(provider.pendingMessageRatings.contains(messageId))
  }

  func testFailedJournalKeepsLocalRatingWithoutPatch() async throws {
    let provider = ChatProvider()
    let surface = provider.mainChatSurfaceReference()
    let messageId = "assistant-failed-rating"
    let persisted = expectation(description: "failed journal must not PATCH")
    persisted.isInverted = true
    provider.persistMessageRatingHandler = { _, _ in
      persisted.fulfill()
    }
    provider.messages = [
      ChatMessage(
        id: messageId,
        text: "Partial answer.",
        sender: .ai,
        isStreaming: false,
        isSynced: false,
        journalStatus: .completed)
    ]

    XCTAssertEqual(provider.queueMessageRating(messageId, rating: -1), .waitForSync)

    provider.projectJournalTurn(
      try makeTurn(
        surface: surface,
        turnId: messageId,
        content: "Partial answer.",
        status: .failed))

    await fulfillment(of: [persisted], timeout: 0.2)
    XCTAssertEqual(provider.messages.first?.rating, -1)
    XCTAssertFalse(provider.pendingMessageRatings.contains(messageId))
  }

  /// Thread 2 regression: a thumbs tap on the live tail is keyed by the local
  /// in-memory id, but journal projection replaces that row with the kernel
  /// turnId. The queued rating must survive the remap and PATCH with the
  /// projected (remote) id, not the stale local id.
  func testQueuedRatingSurvivesProjectionIdRemap() async throws {
    let provider = ChatProvider()
    let surface = provider.mainChatSurfaceReference()
    let localId = "live-tail-local"
    let remoteId = "srv-42"
    let persisted = expectation(description: "queued rating PATCHes with remote id after id remap")
    provider.persistMessageRatingHandler = { persistedId, rating in
      XCTAssertEqual(persistedId, remoteId, "drain must PATCH with the projected remote id")
      XCTAssertEqual(rating, 1)
      persisted.fulfill()
    }
    provider.messages = [
      ChatMessage(
        id: localId,
        clientTurnId: localId,
        text: "I'll look that up.",
        sender: .ai,
        isStreaming: false,
        isSynced: false,
        journalStatus: .completed)
    ]

    XCTAssertEqual(provider.queueMessageRating(localId, rating: 1), .waitForSync)

    // The journal turn has a *different* turnId from the live-tail id, with a
    // matching clientTurnId so projection remaps the row by continuity.
    var dictionary: [String: Any] = [
      "conversationId": "conversation-1",
      "turnId": remoteId,
      "turnSeq": 1,
      "conversationGeneration": 1,
      "generationBaseTurnSeq": 0,
      "producerId": "producer:\(remoteId)",
      "payloadHash": "sha256:\(remoteId)",
      "role": "assistant",
      "surfaceKind": surface.surfaceKind,
      "externalRefKind": surface.externalRefKind,
      "externalRefId": surface.externalRefId,
      "content": "I'll look that up.",
      "origin": "test",
      "status": KernelJournalTurnStatus.completed.rawValue,
      "contentBlocks": [],
      "resources": [],
      "metadataJson": "{\"continuityKey\":\"\(localId)\"}",
      "createdAtMs": 1_700_000_000_000,
      "updatedAtMs": 1_700_000_000_000,
    ]
    dictionary["remoteId"] = remoteId
    provider.projectJournalTurn(try XCTUnwrap(KernelJournalTurn(dictionary: dictionary)))

    await fulfillment(of: [persisted], timeout: 1.0)
    XCTAssertEqual(provider.messages.first?.id, remoteId)
    XCTAssertEqual(provider.messages.first?.rating, 1)
    XCTAssertFalse(provider.pendingMessageRatings.contains(localId))
  }

  /// Queue-level regression for the id-remap fix: drain must match by
  /// clientTurnId when the id has changed.
  func testQueueDrainsByClientTurnIdAfterIdRemap() {
    var queue = ChatMessageRatingQueue()
    let localId = "local-1"
    let remoteId = "remote-1"
    queue.enqueue(messageId: localId, rating: 1)

    // The message has been remapped: id=remoteId, clientTurnId=localId
    let remapped = ChatMessage(
      id: remoteId, clientTurnId: localId,
      text: "Done.", sender: .ai, isSynced: true)
    let ready = queue.drain(using: [remapped])
    XCTAssertEqual(ready.count, 1)
    XCTAssertEqual(ready.first?.messageId, remoteId, "drain must PATCH with the projected remote id")
    XCTAssertEqual(ready.first?.rating, 1)
    XCTAssertTrue(queue.isEmpty)
  }

  /// Thread 1 regression: a drained rating PATCH that is in flight when an
  /// owner transition fires must not write under the new session.
  func testPersistMessageRatingFencedByOwner() async {
    let provider = ChatProvider()
    let persisted = expectation(description: "owner-fenced PATCH is dropped")
    persisted.isInverted = true
    provider.persistMessageRatingHandler = { _, _ in
      persisted.fulfill()
    }
    // Simulate a PATCH whose captured owner no longer matches the current owner.
    await provider.persistMessageRating("m1", rating: 1, expectedOwner: "stale-owner")
    await fulfillment(of: [persisted], timeout: 0.2)
  }

  private func makeTurn(
    surface: AgentSurfaceReference,
    turnId: String,
    content: String,
    status: KernelJournalTurnStatus = .completed,
    remoteId: String? = nil
  ) throws -> KernelJournalTurn {
    var dictionary: [String: Any] = [
      "conversationId": "conversation-1",
      "turnId": turnId,
      "turnSeq": 1,
      "conversationGeneration": 1,
      "generationBaseTurnSeq": 0,
      "producerId": "producer:\(turnId)",
      "payloadHash": "sha256:\(turnId)",
      "role": "assistant",
      "surfaceKind": surface.surfaceKind,
      "externalRefKind": surface.externalRefKind,
      "externalRefId": surface.externalRefId,
      "content": content,
      "origin": "test",
      "status": status.rawValue,
      "contentBlocks": [],
      "resources": [],
      "metadataJson": "{}",
      "createdAtMs": 1_700_000_000_000,
      "updatedAtMs": 1_700_000_000_000,
    ]
    if let remoteId {
      dictionary["remoteId"] = remoteId
    }
    return try XCTUnwrap(KernelJournalTurn(dictionary: dictionary))
  }
}
