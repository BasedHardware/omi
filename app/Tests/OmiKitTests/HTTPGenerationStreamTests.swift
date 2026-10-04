#if !SKIP && !canImport(FoundationNetworking)
  import Foundation
  import XCTest
  @testable import OmiKit

  /// URLProtocol is the only network endpoint; no sockets, accounts or devices.
  final class HTTPGenerationStreamTests: XCTestCase {
    private func backend() async -> (HTTPBackendTransport, URLSession) {
      let configuration = URLSessionConfiguration.ephemeral
      configuration.protocolClasses = [GenerationURLProtocol.self]
      let session = URLSession(configuration: configuration)
      let credentials = InMemoryCredentialStore()
      await credentials.store(StoredSession(idToken: "synthetic", refreshToken: "synthetic"))
      return (
        HTTPBackendTransport(
          session: session, credentials: credentials,
          planeSelection: .init(storedPlane: "new", stampedValid: true),
          originOverride: "https://stream.example.test"), session
      )
    }

    func testUnicodeFrameArrivesBeforeEOFAndTerminalBodyIsPreserved() async throws {
      let (backend, session) = await backend()
      defer { session.invalidateAndCancel() }
      let reached = expectation(description: "request received")
      let firstFrame = expectation(description: "parsed delta delivered before EOF")
      let completed = expectation(description: "stream completed")
      let holder = StreamFixtureState()
      GenerationURLProtocol.handler = { stream in
        XCTAssertEqual(
          stream.request.value(forHTTPHeaderField: "authorization"), "Bearer synthetic")
        XCTAssertEqual(stream.request.value(forHTTPHeaderField: "last-event-id"), "event-1")
        holder.setStream(stream)
        stream.respond(status: 200, headers: ["Content-Type": "text/event-stream; charset=utf-8"])
        reached.fulfill()
      }
      let task = Task {
        defer { completed.fulfill() }
        return try await backend.generationEvents(
          generationId: "generation-1", lastEventId: "event-1"
        ) { frame in
          holder.append(frame)
          if holder.events.count == 1 { firstFrame.fulfill() }
        }
      }
      await fulfillment(of: [reached], timeout: 2)
      let stream = try XCTUnwrap(holder.stream)
      let frame = "id: event-2\nevent: delta\ndata: {\"kind\":\"delta\",\"text\":\"你好 Café 👋\"}\n\n"
      // Exercise byte-split UTF-8 and wire CR/BOM normalization with the real parser.
      let wireFrame = "\u{FEFF}" + frame.replacingOccurrences(of: "\n", with: "\r")
      for byte in wireFrame.utf8 { stream.emit(Data([byte])) }
      await fulfillment(of: [firstFrame], timeout: 2)
      XCTAssertNil(holder.parseError)
      XCTAssertEqual(holder.frames, [frame])
      XCTAssertEqual(
        holder.events, [ParsedGenerationEvent(id: "event-2", frame: .delta(text: "你好 Café 👋"))])
      let terminal =
        "id: event-3\nevent: cancelled\ndata: {\"kind\":\"cancelled\",\"message\":null}\n\n"
      stream.emit(Data(terminal.utf8))
      stream.finish()
      let completion = await XCTWaiter.fulfillment(of: [completed], timeout: 2)
      guard completion == .completed else {
        task.cancel()
        session.invalidateAndCancel()
        XCTFail("Stream did not complete after EOF")
        return
      }
      let response = try await task.value
      XCTAssertEqual(response.body, frame + terminal)
      XCTAssertEqual(holder.frames, [frame, terminal])
      XCTAssertNil(holder.parseError)
      var terminalParser = IncrementalChatGenerationParser()
      let events = try terminalParser.push(try XCTUnwrap(response.body))
      XCTAssertEqual(events.last?.frame, .cancelled(message: nil))
      XCTAssertEqual(try terminalParser.finish(), [])
    }

    func testExplicitCancellationStopsARequestWaitingForHeaders() async throws {
      let (backend, session) = await backend()
      defer { session.invalidateAndCancel() }
      let reached = expectation(description: "request started without headers")
      let stopped = expectation(description: "underlying request stopped")
      let completed = expectation(description: "cancelled call completed")
      GenerationURLProtocol.handler = { stream in
        stream.onStop = { stopped.fulfill() }
        reached.fulfill()
      }
      let task = Task {
        defer { completed.fulfill() }
        do {
          _ = try await backend.generationEvents(generationId: "pending", lastEventId: nil) { _ in
            XCTFail("Cancelled response must not deliver a frame")
          }
          XCTFail("Expected cancellation")
        } catch { XCTAssertEqual(error as? TransportFailure, .cancelled) }
      }
      await fulfillment(of: [reached], timeout: 2)
      await backend.cancelGenerationEvents(generationId: "pending")
      // Check bounded completion before any join: a cancellation regression
      // fails this test instead of leaving it blocked on task.value forever.
      let completion = await XCTWaiter.fulfillment(of: [stopped, completed], timeout: 2)
      task.cancel()
      session.invalidateAndCancel()
      XCTAssertEqual(completion, .completed)
    }

    func testHTTPFailureNeverPublishesFramesAndRetainsRetryAfter() async throws {
      let (backend, session) = await backend()
      defer { session.invalidateAndCancel() }
      GenerationURLProtocol.handler = { stream in
        stream.respond(status: 429, headers: ["Retry-After": "7"])
        stream.emit(Data("{\"error\":\"rate_limited\"}".utf8))
        stream.finish()
      }
      let response = try await backend.generationEvents(generationId: "limited", lastEventId: nil) {
        _ in
        XCTFail("HTTP failure body is not an SSE event")
      }
      XCTAssertEqual(response.status, 429)
      XCTAssertEqual(response.retryAfterSeconds, 7)
      XCTAssertEqual(response.body, "{\"error\":\"rate_limited\"}")
    }
  }

  private final class StreamFixtureState: @unchecked Sendable {
    private let lock = NSLock()
    private var storedStream: GenerationURLProtocol?
    private var storedFrames = [String]()
    private var parser = IncrementalChatGenerationParser()
    private var storedEvents = [ParsedGenerationEvent]()
    private var storedParseError: String?
    var stream: GenerationURLProtocol? { lock.withLock { storedStream } }
    var frames: [String] { lock.withLock { storedFrames } }
    func setStream(_ value: GenerationURLProtocol) { lock.withLock { storedStream = value } }
    var events: [ParsedGenerationEvent] { lock.withLock { storedEvents } }
    var parseError: String? { lock.withLock { storedParseError } }
    func append(_ value: String) {
      lock.withLock {
        storedFrames.append(value)
        do { storedEvents += try parser.push(value) } catch {
          storedParseError = String(describing: error)
        }
      }
    }
  }

  private final class GenerationURLProtocol: URLProtocol, @unchecked Sendable {
    nonisolated(unsafe) static var handler: (@Sendable (GenerationURLProtocol) -> Void)?
    private let stopLock = NSLock()
    private var storedOnStop: (@Sendable () -> Void)?
    var onStop: (@Sendable () -> Void)? {
      get { stopLock.withLock { storedOnStop } }
      set { stopLock.withLock { storedOnStop = newValue } }
    }
    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() { Self.handler?(self) }
    override func stopLoading() { onStop?() }
    func respond(status: Int, headers: [String: String] = [:]) {
      client?.urlProtocol(
        self,
        didReceive: HTTPURLResponse(
          url: request.url!, statusCode: status,
          httpVersion: "HTTP/1.1", headerFields: headers)!, cacheStoragePolicy: .notAllowed)
    }
    func emit(_ data: Data) { client?.urlProtocol(self, didLoad: data) }
    func finish() { client?.urlProtocolDidFinishLoading(self) }
  }
#endif
