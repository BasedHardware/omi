import XCTest
@testable import Omi_Computer

private final class ConversationCountURLStub: URLProtocol, @unchecked Sendable {
  private static let lock = NSLock()
  private static var _requests: [(method: String, path: String)] = []

  static var requests: [(method: String, path: String)] {
    lock.lock()
    defer { lock.unlock() }
    return _requests
  }

  static func reset() {
    lock.lock()
    _requests = []
    lock.unlock()
  }

  override class func canInit(with request: URLRequest) -> Bool { true }
  override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

  override func startLoading() {
    let method = request.httpMethod ?? "GET"
    let path = request.url?.path ?? ""
    Self.lock.lock()
    Self._requests.append((method: method, path: path))
    Self.lock.unlock()

    let (status, body): (Int, Data) = switch (method, path) {
    case ("GET", "/v1/conversations/count"):
      (200, Data(#"{"count":4}"#.utf8))
    case ("POST", "/v1/conversations/merge"):
      (200, Data(#"{"status":"ok","message":"merged","conversation_ids":[]}"#.utf8))
    default:
      (204, Data())
    }
    let response = HTTPURLResponse(
      url: request.url!, statusCode: status, httpVersion: nil, headerFields: nil)!
    client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
    client?.urlProtocol(self, didLoad: body)
    client?.urlProtocolDidFinishLoading(self)
  }

  override func stopLoading() {}
}

final class APIClientConversationCountTests: XCTestCase {
  override func setUp() {
    super.setUp()
    ConversationCountURLStub.reset()
    setenv("OMI_PYTHON_API_URL", "http://conversation-count-test:9001", 1)
  }

  override func tearDown() {
    unsetenv("OMI_PYTHON_API_URL")
    ConversationCountURLStub.reset()
    super.tearDown()
  }

  func testCreateConversationFromSegmentsResponseDefaultsOptionalFields() throws {
    let response = try JSONDecoder().decode(
      APIClient.CreateConversationFromSegmentsResponse.self,
      from: Data(#"{"id":"conversation-1"}"#.utf8)
    )

    XCTAssertEqual(response.id, "conversation-1")
    XCTAssertEqual(response.status, "processing")
    XCTAssertFalse(response.discarded)
  }

  func testConversationCountEndpointIncludesVisibleFilters() throws {
    let formatter = ISO8601DateFormatter()
    let start = try XCTUnwrap(formatter.date(from: "2026-06-01T00:00:00Z"))
    let end = try XCTUnwrap(formatter.date(from: "2026-06-02T00:00:00Z"))

    let endpoint = APIClient.conversationsCountEndpoint(
      includeDiscarded: false,
      statuses: [.completed, .processing],
      startDate: start,
      endDate: end,
      folderId: "folder-a",
      starred: true
    )

    XCTAssertTrue(endpoint.hasPrefix("v1/conversations/count?"))
    XCTAssertTrue(endpoint.contains("include_discarded=false"))
    XCTAssertTrue(endpoint.contains("statuses=completed,processing"))
    XCTAssertTrue(endpoint.contains("start_date=2026-06-01T00:00:00Z"))
    XCTAssertTrue(endpoint.contains("end_date=2026-06-02T00:00:00Z"))
    XCTAssertTrue(endpoint.contains("folder_id=folder-a"))
    XCTAssertTrue(endpoint.contains("starred=true"))
  }

  func testConversationCountEndpointDistinguishesFilterCacheKeys() {
    let unfiltered = APIClient.conversationsCountEndpoint(includeDiscarded: false)
    let folderFiltered = APIClient.conversationsCountEndpoint(
      includeDiscarded: false,
      folderId: "folder-a"
    )
    let starredFalse = APIClient.conversationsCountEndpoint(
      includeDiscarded: false,
      starred: false
    )

    XCTAssertNotEqual(unfiltered, folderFiltered)
    XCTAssertNotEqual(unfiltered, starredFalse)
    XCTAssertTrue(starredFalse.contains("starred=false"))
  }

  func testConversationFilterQueryItemsAreSharedByListAndCount() throws {
    let formatter = ISO8601DateFormatter()
    let start = try XCTUnwrap(formatter.date(from: "2026-06-01T00:00:00Z"))

    let queryItems = APIClient.conversationFilterQueryItems(
      statuses: [.completed],
      includeDiscarded: true,
      startDate: start,
      folderId: "folder-a",
      starred: false
    )

    XCTAssertEqual(queryItems, [
      "include_discarded=true",
      "statuses=completed",
      "start_date=2026-06-01T00:00:00Z",
      "folder_id=folder-a",
      "starred=false",
    ])
  }

  func testConversationMutationsInvalidateCountCache() async throws {
    let configuration = URLSessionConfiguration.ephemeral
    configuration.protocolClasses = [ConversationCountURLStub.self]
    let client = APIClient(session: URLSession(configuration: configuration))
    await client.setTestAuthHeader("Bearer test-token")

    let initialCount = try await client.getConversationsCount()
    XCTAssertEqual(initialCount, 4)
    let cachedCount = try await client.getConversationsCount()
    XCTAssertEqual(cachedCount, 4)
    try await client.deleteConversation(id: "conversation-1")
    let countAfterDelete = try await client.getConversationsCount()
    XCTAssertEqual(countAfterDelete, 4)
    _ = try await client.mergeConversations(ids: ["conversation-1"])
    let countAfterMerge = try await client.getConversationsCount()
    XCTAssertEqual(countAfterMerge, 4)

    XCTAssertEqual(
      ConversationCountURLStub.requests.map { "\($0.method) \($0.path)" },
      [
        "GET /v1/conversations/count",
        "DELETE /v1/conversations/conversation-1",
        "GET /v1/conversations/count",
        "POST /v1/conversations/merge",
        "GET /v1/conversations/count",
      ]
    )
  }
}
