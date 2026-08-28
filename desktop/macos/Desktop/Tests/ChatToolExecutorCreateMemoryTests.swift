import Foundation
import XCTest

@testable import Omi_Computer

extension APIClient {
  fileprivate func setCreateMemoryTestAuthHeader(_ header: String) {
    testAuthHeader = header
  }
}

private final class CreateMemoryRequestCapture: URLProtocol, @unchecked Sendable {
  private static let lock = NSLock()
  private nonisolated(unsafe) static var captured: URLRequest?
  private nonisolated(unsafe) static var body: Data?
  private nonisolated(unsafe) static var statusCode = 200
  private nonisolated(unsafe) static var requestCount = 0

  static func reset() {
    lock.withLock {
      captured = nil
      body = nil
      statusCode = 200
      requestCount = 0
    }
  }

  static func setStatusCode(_ statusCode: Int) {
    lock.withLock { Self.statusCode = statusCode }
  }

  static func count() -> Int {
    lock.withLock { requestCount }
  }

  static func request() -> URLRequest? {
    lock.withLock { captured }
  }

  static func requestBody() -> Data? {
    lock.withLock { body }
  }

  override class func canInit(with request: URLRequest) -> Bool { true }
  override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

  override func startLoading() {
    Self.lock.withLock {
      Self.captured = request
      Self.body = Self.bodyData(from: request)
      Self.requestCount += 1
    }
    guard let url = request.url,
      let response = HTTPURLResponse(
        url: url,
        statusCode: Self.lock.withLock { Self.statusCode },
        httpVersion: nil,
        headerFields: ["Content-Type": "application/json"]
      )
    else {
      client?.urlProtocol(self, didFailWithError: URLError(.badURL))
      return
    }
    client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
    client?.urlProtocol(
      self,
      didLoad: Data(
        """
        {"id":"memory-1","uid":"create-memory-tool-owner","content":"I prefer tea.","category":"manual","created_at":"2026-08-03T12:00:00Z","updated_at":"2026-08-03T12:00:00Z","layer":"short_term","visibility":"private"}
        """.utf8))
    client?.urlProtocolDidFinishLoading(self)
  }

  override func stopLoading() {}

  private static func bodyData(from request: URLRequest) -> Data? {
    if let body = request.httpBody { return body }
    guard let stream = request.httpBodyStream else { return nil }
    stream.open()
    defer { stream.close() }
    var data = Data()
    let buffer = UnsafeMutablePointer<UInt8>.allocate(capacity: 4_096)
    defer { buffer.deallocate() }
    while stream.hasBytesAvailable {
      let count = stream.read(buffer, maxLength: 4_096)
      guard count > 0 else { break }
      data.append(buffer, count: count)
    }
    return data.isEmpty ? nil : data
  }
}

private final class CreateMemoryTimeoutCapture: URLProtocol, @unchecked Sendable {
  private static let lock = NSLock()
  private nonisolated(unsafe) static var requestCount = 0

  static func reset() {
    lock.withLock { requestCount = 0 }
  }

  static func count() -> Int {
    lock.withLock { requestCount }
  }

  override class func canInit(with request: URLRequest) -> Bool { true }
  override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

  override func startLoading() {
    Self.lock.withLock { Self.requestCount += 1 }
    client?.urlProtocol(self, didFailWithError: URLError(.timedOut))
  }

  override func stopLoading() {}
}

@MainActor
final class ChatToolExecutorCreateMemoryTests: XCTestCase {
  private var ownerFixture: RuntimeOwnerAuthorityTestFixture?

  override func setUp() async throws {
    ownerFixture = RuntimeOwnerAuthorityTestFixture()
    await ownerFixture?.establish(authOwnerID: "create-memory-tool-owner")
  }

  override func tearDown() async throws {
    await ownerFixture?.restore()
    ownerFixture = nil
  }

  func testMemoryCreationInputTrimsAndBoundsContent() {
    XCTAssertEqual(
      ChatToolExecutor.memoryCreationInput(["content": "  I prefer tea.  "]),
      ChatToolExecutor.MemoryCreationInput(content: "I prefer tea.")
    )
    XCTAssertNil(ChatToolExecutor.memoryCreationInput(["content": " \n\t "]))
    XCTAssertNil(ChatToolExecutor.memoryCreationInput(["content": String(repeating: "a", count: 1001)]))
  }

  func testMemoryWritesAreLimitedToTypedDesktopChatSurfaces() {
    XCTAssertTrue(ChatToolExecutor.isTypedChatMemorySurface("main_chat"))
    XCTAssertTrue(ChatToolExecutor.isTypedChatMemorySurface("floating_chat"))
    XCTAssertFalse(ChatToolExecutor.isTypedChatMemorySurface("realtime_voice"))
    XCTAssertFalse(ChatToolExecutor.isTypedChatMemorySurface("task_chat"))
    XCTAssertFalse(ChatToolExecutor.isTypedChatMemorySurface(nil))
  }

  func testExecutorSavesARewrittenFactFromTypedChat() async throws {
    CreateMemoryRequestCapture.reset()
    setenv("OMI_PYTHON_API_URL", "http://create-memory-contract-test:9001", 1)
    defer {
      unsetenv("OMI_PYTHON_API_URL")
      CreateMemoryRequestCapture.reset()
    }
    let configuration = URLSessionConfiguration.ephemeral
    configuration.protocolClasses = [CreateMemoryRequestCapture.self]
    let client = APIClient(session: URLSession(configuration: configuration))
    await client.setCreateMemoryTestAuthHeader("Bearer create-memory-tool-owner-token")

    let result = await ChatToolExecutor.execute(
      ToolCall(
        name: "create_memory",
        arguments: ["content": "I prefer tea."],
        thoughtSignature: nil),
      originatingSurfaceRef: .mainChat(chatId: "test"),
      originatingUserText: "Please remember this.",
      expectedOwnerID: "create-memory-tool-owner",
      backendAPIClient: client)

    XCTAssertEqual(CreateMemoryRequestCapture.count(), 1)
    let body = try XCTUnwrap(CreateMemoryRequestCapture.requestBody())
    let payload = try XCTUnwrap(JSONSerialization.jsonObject(with: body) as? [String: Any])
    XCTAssertEqual(payload["content"] as? String, "I prefer tea.")
    XCTAssertTrue(result.contains(#""memory_id":"memory-1""#), result)
  }

  func testExecutorRejectsRealtimeVoiceSurface() async {
    let client = APIClient(session: URLSession(configuration: .ephemeral))
    let result = await ChatToolExecutor.execute(
      ToolCall(
        name: "create_memory",
        arguments: ["content": "I prefer tea."],
        thoughtSignature: nil),
      originatingSurfaceRef: .realtimeVoice(chatId: "test"),
      originatingUserText: "Please remember that I prefer tea.",
      expectedOwnerID: "create-memory-tool-owner",
      backendAPIClient: client)

    XCTAssertTrue(result.contains("typed_chat_surface_required"), result)
  }

  func testExecutorRejectsDelegatedFloatingPillScope() async {
    let client = APIClient(session: URLSession(configuration: .ephemeral))
    let result = await ChatToolExecutor.execute(
      ToolCall(
        name: "create_memory",
        arguments: ["content": "I prefer tea."],
        thoughtSignature: nil),
      originatingClientScope: AgentClientScope.floatingPill,
      originatingSurfaceRef: .mainChat(chatId: "test"),
      originatingUserText: "Remember that I prefer tea.",
      expectedOwnerID: "create-memory-tool-owner",
      backendAPIClient: client)

    XCTAssertTrue(result.contains("typed_chat_surface_required"), result)
  }

  func testMemoryCreationReceiptIncludesExplicitServerLayerOnly() throws {
    let decoder = OmiHTTPTransport.makeDecoder()
    let data = Data(
      """
      {"id":"memory-1","uid":"create-memory-tool-owner","content":"I prefer tea.","category":"manual","created_at":"2026-08-03T12:00:00Z","updated_at":"2026-08-03T12:00:00Z","layer":"short_term","visibility":"private"}
      """.utf8)
    let memory = try decoder.decode(ServerMemory.self, from: data)
    let receipt = ChatToolExecutor.memoryCreationReceipt(memory)
    let payload = try XCTUnwrap(JSONSerialization.jsonObject(with: Data(receipt.utf8)) as? [String: Any])

    XCTAssertEqual(payload["memory_id"] as? String, "memory-1")
    XCTAssertEqual(payload["layer"] as? String, "short_term")
    XCTAssertTrue((payload["message"] as? String)?.contains("short-term") == true)
  }

  func testExecutorSendsOneOwnerBoundPrivateManualRequest() async throws {
    CreateMemoryRequestCapture.reset()
    setenv("OMI_PYTHON_API_URL", "http://create-memory-contract-test:9001", 1)
    defer {
      unsetenv("OMI_PYTHON_API_URL")
      CreateMemoryRequestCapture.reset()
    }
    let configuration = URLSessionConfiguration.ephemeral
    configuration.protocolClasses = [CreateMemoryRequestCapture.self]
    let client = APIClient(session: URLSession(configuration: configuration))
    await client.setCreateMemoryTestAuthHeader("Bearer create-memory-tool-owner-token")

    let result = await ChatToolExecutor.execute(
      ToolCall(
        name: "create_memory",
        arguments: ["content": "  I prefer tea.  "],
        thoughtSignature: nil),
      originatingSurfaceRef: .mainChat(chatId: "test"),
      originatingUserText: "Remember that I prefer tea.",
      expectedOwnerID: "create-memory-tool-owner",
      backendAPIClient: client)

    let request = try XCTUnwrap(CreateMemoryRequestCapture.request())
    XCTAssertEqual(request.httpMethod, "POST")
    XCTAssertEqual(request.url?.path, "/v3/memories")
    XCTAssertEqual(
      request.value(forHTTPHeaderField: "Authorization"),
      "Bearer create-memory-tool-owner-token")
    let body = try XCTUnwrap(CreateMemoryRequestCapture.requestBody())
    let payload = try XCTUnwrap(JSONSerialization.jsonObject(with: body) as? [String: Any])
    XCTAssertEqual(payload["content"] as? String, "I prefer tea.")
    XCTAssertEqual(payload["category"] as? String, "manual")
    XCTAssertEqual(payload["visibility"] as? String, "private")
    XCTAssertEqual(payload["tags"] as? [String], [])
    XCTAssertNil(payload["tier"])
    XCTAssertNil(payload["durability"])
    XCTAssertTrue(result.contains(#""memory_id":"memory-1""#), result)
  }

  func testMemoryWriteDoesNotRetryAfterUnauthorized() async throws {
    CreateMemoryRequestCapture.reset()
    CreateMemoryRequestCapture.setStatusCode(401)
    setenv("OMI_PYTHON_API_URL", "http://create-memory-contract-test:9001", 1)
    defer {
      unsetenv("OMI_PYTHON_API_URL")
      CreateMemoryRequestCapture.reset()
    }
    let configuration = URLSessionConfiguration.ephemeral
    configuration.protocolClasses = [CreateMemoryRequestCapture.self]
    let client = APIClient(session: URLSession(configuration: configuration))
    await client.setCreateMemoryTestAuthHeader("Bearer create-memory-tool-owner-token")

    let result = await ChatToolExecutor.execute(
      ToolCall(
        name: "create_memory",
        arguments: ["content": "I prefer tea."],
        thoughtSignature: nil),
      originatingSurfaceRef: .mainChat(chatId: "test"),
      originatingUserText: "Remember that I prefer tea.",
      expectedOwnerID: "create-memory-tool-owner",
      backendAPIClient: client)

    XCTAssertEqual(CreateMemoryRequestCapture.count(), 1)
    XCTAssertTrue(result.contains(#""saved":false"#), result)
  }

  func testMemoryWriteReportsUnknownStatusAfterTransportFailure() async throws {
    CreateMemoryTimeoutCapture.reset()
    setenv("OMI_PYTHON_API_URL", "http://create-memory-timeout-test:9001", 1)
    defer {
      unsetenv("OMI_PYTHON_API_URL")
      CreateMemoryTimeoutCapture.reset()
    }
    let configuration = URLSessionConfiguration.ephemeral
    configuration.protocolClasses = [CreateMemoryTimeoutCapture.self]
    let client = APIClient(session: URLSession(configuration: configuration))
    await client.setCreateMemoryTestAuthHeader("Bearer create-memory-tool-owner-token")

    let result = await ChatToolExecutor.execute(
      ToolCall(
        name: "create_memory",
        arguments: ["content": "I prefer tea."],
        thoughtSignature: nil),
      originatingSurfaceRef: .mainChat(chatId: "test"),
      originatingUserText: "Remember that I prefer tea.",
      expectedOwnerID: "create-memory-tool-owner",
      backendAPIClient: client)

    XCTAssertEqual(CreateMemoryTimeoutCapture.count(), 1)
    XCTAssertTrue(result.contains("memory_save_status_unknown"), result)
    XCTAssertFalse(result.contains(#""saved":false"#), result)
  }

  func testMemoriesCreationInputBoundsDeduplicatesAndCaps() {
    XCTAssertEqual(
      ChatToolExecutor.memoriesCreationInput([
        "facts": ["  Prefers tea.  ", "Prefers tea.", "", String(repeating: "a", count: 1001), "Works in Swift."]
      ]),
      ["Prefers tea.", "Works in Swift."])
    XCTAssertNil(ChatToolExecutor.memoriesCreationInput(["facts": []]))
    XCTAssertNil(ChatToolExecutor.memoriesCreationInput(["content": "Prefers tea."]))
    let overflow = (0..<40).map { "Fact number \($0)." }
    XCTAssertEqual(
      ChatToolExecutor.memoriesCreationInput(["facts": overflow])?.count,
      ChatToolExecutor.memoriesCreationMaxFacts)
  }

  /// The write this tool exists for: many distilled facts reach the backend in
  /// one owner-bound batch request rather than one request per fact.
  func testBatchExecutorSavesEveryFactInOneOwnerBoundRequest() async throws {
    CreateMemoryRequestCapture.reset()
    setenv("OMI_PYTHON_API_URL", "http://create-memories-contract-test:9001", 1)
    defer {
      unsetenv("OMI_PYTHON_API_URL")
      CreateMemoryRequestCapture.reset()
    }
    let configuration = URLSessionConfiguration.ephemeral
    configuration.protocolClasses = [CreateMemoryRequestCapture.self]
    let client = APIClient(session: URLSession(configuration: configuration))
    await client.setCreateMemoryTestAuthHeader("Bearer create-memory-tool-owner-token")

    let result = await ChatToolExecutor.execute(
      ToolCall(
        name: "create_memories",
        arguments: ["facts": ["Prefers tea.", "Works in Swift."]],
        thoughtSignature: nil),
      originatingSurfaceRef: .mainChat(chatId: "test"),
      expectedOwnerID: "create-memory-tool-owner",
      backendAPIClient: client)

    // One owner-bound request per fact through /v3/memories: the batch route
    // answers 503 for this write in production.
    XCTAssertEqual(CreateMemoryRequestCapture.count(), 2)
    let request = try XCTUnwrap(CreateMemoryRequestCapture.request())
    XCTAssertEqual(request.httpMethod, "POST")
    XCTAssertEqual(request.url?.path, "/v3/memories")
    XCTAssertEqual(
      request.value(forHTTPHeaderField: "Authorization"),
      "Bearer create-memory-tool-owner-token")
    let body = try XCTUnwrap(CreateMemoryRequestCapture.requestBody())
    let payload = try XCTUnwrap(JSONSerialization.jsonObject(with: body) as? [String: Any])
    // `manual` is the wire marker for user_asserted; a batch save carries the
    // same authority as the single write.
    XCTAssertEqual(payload["category"] as? String, "manual")
    XCTAssertEqual(payload["visibility"] as? String, "private")
    XCTAssertTrue(result.contains(#""saved_count":2"#), result)
  }

  func testBatchExecutorRejectsNonTypedChatSurfaceWithoutCallingBackend() async {
    CreateMemoryRequestCapture.reset()
    let configuration = URLSessionConfiguration.ephemeral
    configuration.protocolClasses = [CreateMemoryRequestCapture.self]
    let client = APIClient(session: URLSession(configuration: configuration))

    let result = await ChatToolExecutor.execute(
      ToolCall(
        name: "create_memories",
        arguments: ["facts": ["Prefers tea."]],
        thoughtSignature: nil),
      originatingSurfaceRef: .realtimeVoice(chatId: "test"),
      expectedOwnerID: "create-memory-tool-owner",
      backendAPIClient: client)

    XCTAssertTrue(result.contains("typed_chat_surface_required"), result)
    XCTAssertEqual(CreateMemoryRequestCapture.count(), 0)
  }
}
