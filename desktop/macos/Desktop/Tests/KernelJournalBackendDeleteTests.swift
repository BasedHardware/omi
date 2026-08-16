import XCTest

@testable import Omi_Computer

private actor KernelJournalBarrierProbe {
  private var values: Set<String> = []

  func mark(_ value: String) {
    values.insert(value)
  }

  func contains(_ value: String) -> Bool {
    values.contains(value)
  }
}

final class KernelJournalBackendDeleteTests: XCTestCase {
  private let validPayload: [String: Any] = [
    "ownerId": "owner-1",
    "operationId": "delete:conversation-1:2",
    "conversationId": "conversation-1",
    "conversationGeneration": 2,
    "attemptCount": 1,
    "deliveryGeneration": 3,
    "payloadHash": "sha256:payload",
    "targetKind": "messages",
    "targetId": "task-app",
  ]

  func testDeleteRequestRequiresExactClaimAndValidTarget() throws {
    let request = try XCTUnwrap(
      KernelJournalBackendSyncDriver.DeleteRequest(payload: validPayload))
    XCTAssertEqual(request.ownerId, "owner-1")
    XCTAssertEqual(request.operationId, "delete:conversation-1:2")
    XCTAssertEqual(request.targetKind, .messages)
    XCTAssertEqual(request.targetId, "task-app")

    var missingClaim = validPayload
    missingClaim.removeValue(forKey: "payloadHash")
    XCTAssertNil(KernelJournalBackendSyncDriver.DeleteRequest(payload: missingClaim))

    var missingSession = validPayload
    missingSession["targetKind"] = "chat_session"
    missingSession["targetId"] = NSNull()
    XCTAssertNil(KernelJournalBackendSyncDriver.DeleteRequest(payload: missingSession))

    var unknownTarget = validPayload
    unknownTarget["targetKind"] = "conversation"
    XCTAssertNil(KernelJournalBackendSyncDriver.DeleteRequest(payload: unknownTarget))
  }

  func testDeleteRejectsOwnerChangeBeforeHTTP() async throws {
    var payload = validPayload
    payload["ownerId"] = "impossible-owner-\(UUID().uuidString)"
    let request = try XCTUnwrap(
      KernelJournalBackendSyncDriver.DeleteRequest(payload: payload))

    do {
      try await KernelJournalBackendSyncDriver.shared.delete(request)
      XCTFail("owner mismatch must fail before backend DELETE")
    } catch {
      XCTAssertEqual(
        KernelJournalBackendSyncDriver.boundedDeleteErrorCode(for: error),
        "backend_sync_owner_changed")
    }
  }

  func testDeleteUsesBoundedPermanentAndTransientErrorCodes() {
    XCTAssertEqual(
      KernelJournalBackendSyncDriver.boundedDeleteErrorCode(
        for: APIError.httpError(statusCode: 422, detail: "payload rejected")),
      "backend_delete_http_4xx"
    )
    for statusCode in [408, 425, 429] {
      XCTAssertEqual(
        KernelJournalBackendSyncDriver.boundedDeleteErrorCode(
          for: APIError.httpError(statusCode: statusCode, detail: "retry")),
        "backend_sync_http_retryable"
      )
    }
    XCTAssertEqual(
      KernelJournalBackendSyncDriver.boundedDeleteErrorCode(
        for: URLError(.networkConnectionLost)),
      "backend_delete_failed"
    )
  }

  func testConversationBarrierOrdersOldSyncDeleteAndNewSync() async throws {
    let barrier = KernelJournalConversationBarrier()
    let probe = KernelJournalBarrierProbe()
    let conversationId = "conversation-1"

    // Model an old-generation POST already in URLSession when clear is
    // requested. DELETE must wait for it to settle.
    await barrier.beginSync(conversationId: conversationId)
    let firstDelete = Task {
      await barrier.beginDelete(conversationId: conversationId)
      await probe.mark("first-delete")
    }
    let waitingForOldSync = await waitForBarrier(barrier, conversationId: conversationId) {
      $0.isDeleting && $0.activeSyncCount == 1 && $0.syncDrainWaiterCount == 1
    }
    XCTAssertTrue(waitingForOldSync)
    let firstDeleteStartedEarly = await probe.contains("first-delete")
    XCTAssertFalse(firstDeleteStartedEarly)

    await barrier.endSync(conversationId: conversationId)
    await firstDelete.value
    let firstDeleteStarted = await probe.contains("first-delete")
    XCTAssertTrue(firstDeleteStarted)

    // Once DELETE owns the barrier, both a new-generation POST and a second
    // DELETE queue. Deletes retain priority so a POST can never slip between
    // two destructive generations.
    let newSync = Task {
      await barrier.beginSync(conversationId: conversationId)
      await probe.mark("new-sync")
    }
    let secondDelete = Task {
      await barrier.beginDelete(conversationId: conversationId)
      await probe.mark("second-delete")
    }
    let bothQueuedBehindDelete = await waitForBarrier(barrier, conversationId: conversationId) {
      $0.isDeleting && $0.queuedSyncCount == 1 && $0.queuedDeleteCount == 1
    }
    XCTAssertTrue(bothQueuedBehindDelete)
    let newSyncStartedEarly = await probe.contains("new-sync")
    let secondDeleteStartedEarly = await probe.contains("second-delete")
    XCTAssertFalse(newSyncStartedEarly)
    XCTAssertFalse(secondDeleteStartedEarly)

    await barrier.endDelete(conversationId: conversationId)
    await secondDelete.value
    let secondDeleteStarted = await probe.contains("second-delete")
    let newSyncStartedBetweenDeletes = await probe.contains("new-sync")
    XCTAssertTrue(secondDeleteStarted)
    XCTAssertFalse(newSyncStartedBetweenDeletes)

    await barrier.endDelete(conversationId: conversationId)
    await newSync.value
    let newSyncStarted = await probe.contains("new-sync")
    XCTAssertTrue(newSyncStarted)
    await barrier.endSync(conversationId: conversationId)
  }

  private func waitForBarrier(
    _ barrier: KernelJournalConversationBarrier,
    conversationId: String,
    predicate: (KernelJournalConversationBarrier.Snapshot) -> Bool
  ) async -> Bool {
    for _ in 0..<1_000 {
      let snapshot = await barrier.snapshot(conversationId: conversationId)
      if predicate(snapshot) { return true }
      await Task.yield()
    }
    return false
  }
}
