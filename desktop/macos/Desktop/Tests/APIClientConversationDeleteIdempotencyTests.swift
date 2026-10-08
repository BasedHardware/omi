import XCTest

@testable import Omi_Computer

private final class ConversationDeleteStatusStub: URLProtocol, @unchecked Sendable {
  private static let lock = NSLock()
  private nonisolated(unsafe) static var deleteStatus = 200
  private nonisolated(unsafe) static var count = 2
  private nonisolated(unsafe) static var requests: [URLRequest] = []

  static func configure(deleteStatus: Int, count: Int = 2) {
    lock.withLock {
      Self.deleteStatus = deleteStatus
      Self.count = count
    }
  }

  static func reset() {
    lock.withLock {
      deleteStatus = 200
      count = 2
      requests = []
    }
  }

  static var observed: [URLRequest] {
    lock.withLock { requests }
  }

  override class func canInit(with request: URLRequest) -> Bool { true }
  override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

  override func startLoading() {
    let (status, payload) = Self.lock.withLock {
      Self.requests.append(request)
      if request.url?.path == "/v1/conversations/count" {
        return (200, Data("{\"count\":\(Self.count)}".utf8))
      }
      let status = Self.deleteStatus
      return (status, status == 204 ? Data() : Data("{\"detail\":\"Conversation not found\"}".utf8))
    }
    guard let url = request.url,
      let response = HTTPURLResponse(
        url: url,
        statusCode: status,
        httpVersion: nil,
        headerFields: ["Content-Type": "application/json"]
      )
    else {
      client?.urlProtocol(self, didFailWithError: URLError(.badServerResponse))
      return
    }
    client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
    client?.urlProtocol(self, didLoad: payload)
    client?.urlProtocolDidFinishLoading(self)
  }

  override func stopLoading() {}
}

final class APIClientConversationDeleteIdempotencyTests: XCTestCase {
  override func setUp() {
    super.setUp()
    ConversationDeleteStatusStub.reset()
  }

  override func tearDown() {
    ConversationDeleteStatusStub.reset()
    super.tearDown()
  }

  private func makeClient() async -> APIClient {
    let configuration = URLSessionConfiguration.ephemeral
    configuration.protocolClasses = [ConversationDeleteStatusStub.self]
    let client = APIClient(session: URLSession(configuration: configuration))
    await client.setTestAuthHeader("Bearer test-token")
    return client
  }

  func testDeleteTreatsAlreadyAbsentConversationAsSuccessAndKeepsCascade() async throws {
    let client = await makeClient()
    ConversationDeleteStatusStub.configure(deleteStatus: 404)

    try await client.deleteConversation(id: "orphaned-conversation")

    let request = try XCTUnwrap(ConversationDeleteStatusStub.observed.first)
    XCTAssertEqual(request.httpMethod, "DELETE")
    XCTAssertEqual(request.url?.path, "/v1/conversations/orphaned-conversation")
    let components = try XCTUnwrap(URLComponents(url: XCTUnwrap(request.url), resolvingAgainstBaseURL: false))
    XCTAssertEqual(components.queryItems, [URLQueryItem(name: "cascade", value: "true")])
    XCTAssertEqual(ConversationDeleteStatusStub.observed.count, 1)
  }

  func testDeleteSucceedsWithBothReleasedSuccessStatuses() async throws {
    let client = await makeClient()

    for status in [200, 204] {
      ConversationDeleteStatusStub.configure(deleteStatus: status)
      try await client.deleteConversation(id: "live-conversation")
    }

    XCTAssertEqual(ConversationDeleteStatusStub.observed.count, 2)
  }

  func testDeleteStillFailsOnForbiddenConflictGoneAndServerErrors() async throws {
    let client = await makeClient()

    for status in [403, 409, 410, 500, 503] {
      ConversationDeleteStatusStub.configure(deleteStatus: status)
      do {
        try await client.deleteConversation(id: "retained-conversation")
        XCTFail("HTTP \(status) must remain a failed deletion")
      } catch APIError.httpError(let statusCode, _) {
        XCTAssertEqual(statusCode, status)
      }
    }
  }

  func testAlreadyAbsentDeleteInvalidatesCachedConversationCount() async throws {
    let client = await makeClient()
    ConversationDeleteStatusStub.configure(deleteStatus: 404, count: 2)
    let before = try await client.getConversationsCount()
    XCTAssertEqual(before, 2)

    try await client.deleteConversation(id: "orphaned-conversation")
    ConversationDeleteStatusStub.configure(deleteStatus: 404, count: 1)
    let after = try await client.getConversationsCount()

    XCTAssertEqual(after, 1)
    XCTAssertEqual(ConversationDeleteStatusStub.observed.filter { $0.url?.path == "/v1/conversations/count" }.count, 2)
  }

  func testGenericDeleteStillRejectsNotFound() async throws {
    let client = await makeClient()
    ConversationDeleteStatusStub.configure(deleteStatus: 404)

    do {
      try await client.delete("v1/unrelated-resource")
      XCTFail("Only conversation deletion may settle an already absent conversation")
    } catch APIError.httpError(let statusCode, _) {
      XCTAssertEqual(statusCode, 404)
    }
  }
}
