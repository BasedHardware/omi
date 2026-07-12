import XCTest

@testable import Omi_Computer

final class KernelJournalBackendReconcileTests: XCTestCase {
  private let validPayload: [String: Any] = [
    "ownerId": "owner-1",
    "reconcileId": "reconcile-1",
    "conversationId": "conversation-1",
    "targetKind": "messages",
    "targetId": NSNull(),
    "frontierRemoteId": NSNull(),
    "pageCursor": "remote-100",
    "pageLimit": 100,
  ]

  func testRequestRequiresBoundedPageAndSessionTarget() throws {
    let request = try XCTUnwrap(
      KernelJournalBackendSyncDriver.ReconcileRequest(payload: validPayload))
    XCTAssertEqual(request.ownerId, "owner-1")
    XCTAssertEqual(request.pageCursor, "remote-100")
    XCTAssertEqual(request.pageLimit, 100)
    XCTAssertNil(request.targetId)

    var oversized = validPayload
    oversized["pageLimit"] = 101
    XCTAssertNil(KernelJournalBackendSyncDriver.ReconcileRequest(payload: oversized))

    var oversizedCursor = validPayload
    oversizedCursor["pageCursor"] = String(repeating: "x", count: 201)
    XCTAssertNil(KernelJournalBackendSyncDriver.ReconcileRequest(payload: oversizedCursor))

    var firstPage = validPayload
    firstPage["pageCursor"] = NSNull()
    XCTAssertNil(
      try XCTUnwrap(KernelJournalBackendSyncDriver.ReconcileRequest(payload: firstPage))
        .pageCursor)

    var missingSession = validPayload
    missingSession["targetKind"] = "chat_session"
    XCTAssertNil(KernelJournalBackendSyncDriver.ReconcileRequest(payload: missingSession))
  }

  func testReconcilePageDecodesCanonicalIdentityAndStructuredMetadata() throws {
    let data = Data(#"{"messages":[{"id":"remote-1","text":"I started an agent.","created_at":0,"sender":"ai","app_id":null,"session_id":"session-1","rating":null,"reported":false,"metadata":"{\"content_blocks\":[{\"type\":\"agent_spawn\"}]}","client_message_id":"turn-canonical"}],"next_cursor":"remote-1","has_more":true}"#.utf8)
    let page = try JSONDecoder().decode(DesktopMessageReconcilePage.self, from: data)

    XCTAssertEqual(page.nextCursor, "remote-1")
    XCTAssertTrue(page.hasMore)
    XCTAssertEqual(page.messages.count, 1)
    XCTAssertEqual(page.messages[0].clientMessageId, "turn-canonical")
    XCTAssertEqual(page.messages[0].sessionId, "session-1")
    XCTAssertEqual(
      page.messages[0].metadata,
      #"{"content_blocks":[{"type":"agent_spawn"}]}"#
    )
  }

  func testReconcileRejectsOwnerChangeBeforeHTTP() async throws {
    var payload = validPayload
    payload["ownerId"] = "impossible-owner-\(UUID().uuidString)"
    let request = try XCTUnwrap(
      KernelJournalBackendSyncDriver.ReconcileRequest(payload: payload))

    do {
      _ = try await KernelJournalBackendSyncDriver.shared.reconcile(request)
      XCTFail("owner mismatch must fail before backend GET")
    } catch {
      XCTAssertEqual(
        KernelJournalBackendSyncDriver.boundedReconcileErrorCode(for: error),
        "backend_sync_owner_changed")
    }
  }

  func testReconcileUsesBoundedPermanentAndTransientErrorCodes() {
    XCTAssertEqual(
      KernelJournalBackendSyncDriver.boundedReconcileErrorCode(
        for: APIError.httpError(statusCode: 422, detail: "payload rejected")),
      "backend_reconcile_http_4xx"
    )
    XCTAssertEqual(
      KernelJournalBackendSyncDriver.boundedReconcileErrorCode(
        for: APIError.httpError(statusCode: 429, detail: "retry")),
      "backend_reconcile_failed"
    )
  }
}
