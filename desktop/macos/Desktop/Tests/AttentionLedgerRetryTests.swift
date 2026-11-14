import Foundation
import XCTest

@testable import Omi_Computer

/// Exercises ledger retry state through the production API and HTTP transport.
/// Every request is intercepted on a loopback fixture, without contacting a service.
@MainActor
final class AttentionLedgerRetryTests: XCTestCase {
  private func item(
    kind: String = "conversation_notes_failed_with_outputs", state: String = "none", operation: String? = nil
  ) -> AttentionLedgerItem {
    AttentionLedgerItem(
      id: "notes/one", kind: kind, conversationId: "conversation", retryable: true,
      retry: AttentionLedgerRetry(state: state, operationId: operation))
  }

  private func makeClient() async -> (APIClient, URLSession) {
    let configuration = URLSessionConfiguration.ephemeral
    configuration.protocolClasses = [LedgerRetryProtocol.self]
    let session = URLSession(configuration: configuration)
    let client = APIClient(session: session)
    await client.setTestAuthHeader("Bearer fixture")
    return (client, session)
  }

  func testNotesAndSummaryRetriesSendKeyOnItemEndpoint() async throws {
    for kind in ["conversation_notes_failed_with_outputs", "conversation_summary_failed"] {
      LedgerRetryProtocol.configure([.reply(200, "in_progress", "operation")])
      let (client, session) = await makeClient()
      defer { session.invalidateAndCancel() }
      let row = item(kind: kind)
      let store = AttentionLedgerStore(
        load: { AttentionLedgerPage(items: [row]) },
        retry: { id, key in
          try await client.retryAttentionLedger(id, idempotencyKey: key, customBaseURL: "http://127.0.0.1:9876/")
        }, owner: { "fixture" })
      await store.refresh()
      await store.retry(row)
      let request = try XCTUnwrap(LedgerRetryProtocol.requests.first)
      XCTAssertEqual(request.httpMethod, "POST")
      XCTAssertEqual(request.url?.absoluteString, "http://127.0.0.1:9876/v1/attention-items/notes%2Fone/retry")
      XCTAssertNotNil(UUID(uuidString: try XCTUnwrap(request.value(forHTTPHeaderField: "Idempotency-Key"))))
      XCTAssertTrue(store.rows.isEmpty)
    }
  }

  func testTransportErrorReplaysSameKeyAndAcceptedOperationClearsIt() async throws {
    LedgerRetryProtocol.configure([
      .offline, .reply(200, "in_progress", "first-operation"), .reply(200, "succeeded", "next-operation"),
    ])
    let (client, session) = await makeClient()
    defer { session.invalidateAndCancel() }
    var row = item()
    let store = AttentionLedgerStore(
      load: { AttentionLedgerPage(items: [row]) },
      retry: { id, key in
        try await client.retryAttentionLedger(id, idempotencyKey: key, customBaseURL: "http://127.0.0.1:9876/")
      }, owner: { "fixture" })
    await store.refresh()
    await store.retry(row)
    XCTAssertEqual(store.rows.map(\.id), [row.id])
    XCTAssertTrue(store.errors.contains(row.id))
    await store.retry(row)
    XCTAssertTrue(store.rows.isEmpty)
    // An acknowledged operation that later fails permits a new paid attempt.
    row = item(state: "failed", operation: "first-operation")
    await store.refresh()
    XCTAssertEqual(store.rows.count, 1)
    await store.retry(row)
    let keys = LedgerRetryProtocol.requests.map { $0.value(forHTTPHeaderField: "Idempotency-Key") }
    XCTAssertEqual(keys.count, 3)
    XCTAssertNotNil(keys.first ?? nil)
    XCTAssertEqual(keys[0], keys[1])
    XCTAssertNotEqual(keys[1], keys[2])
    XCTAssertTrue(store.rows.isEmpty)
  }

  func testNotRetryableConfirmationClearsKeyAndRetainsErrorRow() async throws {
    LedgerRetryProtocol.configure([.reply(409, "not_retryable", nil), .reply(200, "in_progress", "operation")])
    let (client, session) = await makeClient()
    defer { session.invalidateAndCancel() }
    let row = item()
    let store = AttentionLedgerStore(
      load: { AttentionLedgerPage(items: [row]) },
      retry: { id, key in
        try await client.retryAttentionLedger(id, idempotencyKey: key, customBaseURL: "http://127.0.0.1:9876/")
      }, owner: { "fixture" })
    await store.refresh()
    await store.retry(row)
    XCTAssertEqual(store.rows.map(\.id), [row.id])
    XCTAssertTrue(store.errors.contains(row.id))
    XCTAssertTrue(store.rows[0].canRetry)
    await store.retry(row)
    let requests = LedgerRetryProtocol.requests
    XCTAssertEqual(requests.count, 2)
    XCTAssertNotEqual(
      requests[0].value(forHTTPHeaderField: "Idempotency-Key"), requests[1].value(forHTTPHeaderField: "Idempotency-Key")
    )
    XCTAssertTrue(store.rows.isEmpty)
  }

  func testConfirmedFailureAndAccountResetStartFreshKeys() async {
    var keys: [String] = []
    let row = item()
    let store = AttentionLedgerStore(
      load: { AttentionLedgerPage(items: [row]) },
      retry: { _, key in
        keys.append(key)
        if keys.count == 1 { return AttentionLedgerRetry(state: "failed", operationId: "failed-operation") }
        throw URLError(.networkConnectionLost)
      }, owner: { "fixture" })
    await store.refresh()
    await store.retry(row)
    await store.retry(row)
    await store.retry(row)
    store.reset()
    await store.refresh()
    await store.retry(row)
    XCTAssertEqual(keys.count, 4)
    XCTAssertNotEqual(keys[0], keys[1], "Confirmed failure permits a new attempt")
    XCTAssertEqual(keys[1], keys[2], "Ambiguous transport errors must replay")
    XCTAssertNotEqual(keys[2], keys[3], "Account reset must discard old retry keys")
  }
}

/// Supplies ordered transport outcomes and captures real headers from a private session.
/// The lock isolates callback-executor access to this test's HTTP fixture.
private final class LedgerRetryProtocol: URLProtocol, @unchecked Sendable {
  enum Outcome {
    case offline
    case reply(Int, String, String?)
  }
  private static let lock = NSLock()
  private nonisolated(unsafe) static var outcomes: [Outcome] = []
  private nonisolated(unsafe) static var captured: [URLRequest] = []

  static func configure(_ replies: [Outcome]) {
    lock.lock()
    defer { lock.unlock() }
    outcomes = replies
    captured = []
  }
  static var requests: [URLRequest] {
    lock.lock()
    defer { lock.unlock() }
    return captured
  }
  private static func capture(_ request: URLRequest) -> Outcome {
    lock.lock()
    defer { lock.unlock() }
    captured.append(request)
    return outcomes.isEmpty ? .offline : outcomes.removeFirst()
  }
  override class func canInit(with request: URLRequest) -> Bool { true }
  override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
  override func stopLoading() {}
  override func startLoading() {
    switch Self.capture(request) {
    case .offline:
      client?.urlProtocol(self, didFailWithError: URLError(.networkConnectionLost))
    case .reply(let code, let state, let operation):
      var payload = ["state": state]
      if let operation { payload["operation_id"] = operation }
      guard let url = request.url,
        let response = HTTPURLResponse(url: url, statusCode: code, httpVersion: nil, headerFields: nil),
        let data = try? JSONSerialization.data(withJSONObject: payload)
      else {
        client?.urlProtocol(self, didFailWithError: URLError(.badServerResponse))
        return
      }
      client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
      client?.urlProtocol(self, didLoad: data)
      client?.urlProtocolDidFinishLoading(self)
    }
  }
}
