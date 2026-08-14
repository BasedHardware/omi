import XCTest

@testable import Omi_Computer

final class ProactiveLaneClientTests: XCTestCase {
  func testEnvelopeParsingPreservesGatewayAccounting() throws {
    let data = try JSONSerialization.data(withJSONObject: [
      "operation": "proactive_reasoning",
      "lane": "omi:auto:desktop-proactive-reasoning",
      "provider_model": "gpt-5.6-luna",
      "usage": ["cached_tokens": 900, "cache_write_tokens": 0],
      "cache_write": false,
      "fallback_class": "unknown",
      "response": ["choices": [["message": ["content": "{\"decision\":\"silence\"}"]]]],
    ])
    let parsed = try ProactiveLaneClient.parseEnvelope(data)
    XCTAssertEqual(parsed.usage.cachedTokens, 900)
    XCTAssertEqual(parsed.lane, "omi:auto:desktop-proactive-reasoning")
    XCTAssertEqual(parsed.content, "{\"decision\":\"silence\"}")
  }

  func testTelemetryProviderModelIsBounded() {
    XCTAssertEqual(ContextProactivityTelemetry.boundedProviderModel("gpt-5.6-luna"), "gpt-5.6-luna")
    XCTAssertEqual(ContextProactivityTelemetry.boundedProviderModel("attacker-controlled-model"), "other")
  }

  func testClientErrorsExposeOnlyStableSafeClassifications() {
    XCTAssertEqual(ProactiveLaneClientError.invalidResponse.localizedDescription, "proactive_invalid_response")
    XCTAssertEqual(
      ProactiveLaneClientError.http(status: 429, retryAfterSeconds: nil).localizedDescription,
      "proactive_http_error status=429")
    XCTAssertEqual(ProactiveLaneClientError.ownerChanged.localizedDescription, "proactive_owner_changed")
    XCTAssertEqual(
      ProactiveLaneClientError.quotaCooldown(retryAfterSeconds: 12).localizedDescription,
      "proactive_quota_cooldown status=429")
  }

  func testGarbageEnvelopeThrowsInvalidResponseNotARawSerializationError() {
    do {
      _ = try ProactiveLaneClient.parseEnvelope(Data("not-json".utf8))
      XCTFail("expected invalid_response")
    } catch ProactiveLaneClientError.invalidResponse {
      // Expected: envelope parse failures are a bounded class, not a Cocoa error.
    } catch {
      XCTFail("unexpected error: \(error)")
    }
  }

  func testRetryAfterHeaderIsParsedAsSeconds() throws {
    let url = try XCTUnwrap(URL(string: "https://proactive.test/v1/desktop/proactivity/completions"))
    let response = try XCTUnwrap(
      HTTPURLResponse(
        url: url,
        statusCode: 429,
        httpVersion: nil,
        headerFields: ["Retry-After": " 45 "]))
    XCTAssertEqual(ProactiveLaneClient.parseRetryAfterSeconds(from: response), 45)
  }

  func testExtractionSkipsNetworkDuringQuotaCooldownThenResumesAfterDeadline() async throws {
    ProactiveLaneURLStub.reset()
    let clock = ManualDateClock(Date(timeIntervalSince1970: 1_800_000_000))
    let client = ProactiveLaneClient(
      session: makeStubSession(),
      baseURL: { "https://proactive.test" },
      authorization: { "Bearer test" },
      now: { clock.now })

    ProactiveLaneURLStub.enqueue(
      statusCode: 429,
      body: Data(#"{"detail":"Proactive request limit exceeded"}"#.utf8),
      headers: ["Retry-After": "120"])

    do {
      _ = try await completeExtraction(on: client)
      XCTFail("expected the first extraction attempt to throw 429")
    } catch ProactiveLaneClientError.http(let status, let retryAfter) {
      XCTAssertEqual(status, 429)
      XCTAssertEqual(retryAfter, 120)
    }
    XCTAssertEqual(ProactiveLaneURLStub.requestCount, 1)

    clock.advance(by: 10)
    do {
      _ = try await completeExtraction(on: client)
      XCTFail("expected the in-window extraction attempt to skip the network")
    } catch ProactiveLaneClientError.quotaCooldown(let retryAfter) {
      XCTAssertEqual(retryAfter, 110)
    }
    XCTAssertEqual(
      ProactiveLaneURLStub.requestCount, 1,
      "an extraction attempt before Retry-After must not hit the network")

    clock.advance(by: 111)
    ProactiveLaneURLStub.enqueue(
      statusCode: 200,
      body: try successEnvelope(operation: ModelQoS.Proactivity.extractionOperation))

    let result = try await completeExtraction(on: client)
    XCTAssertEqual(result.operation, ModelQoS.Proactivity.extractionOperation)
    XCTAssertEqual(ProactiveLaneURLStub.requestCount, 2)
  }

  func testMissingRetryAfterUsesConservativeDefaultCooldown() async throws {
    ProactiveLaneURLStub.reset()
    let clock = ManualDateClock(Date(timeIntervalSince1970: 1_800_000_000))
    let client = ProactiveLaneClient(
      session: makeStubSession(),
      baseURL: { "https://proactive.test" },
      authorization: { "Bearer test" },
      now: { clock.now })

    ProactiveLaneURLStub.enqueue(statusCode: 429, body: Data(), headers: [:])
    do {
      _ = try await completeExtraction(on: client)
      XCTFail("expected 429")
    } catch ProactiveLaneClientError.http(let status, let retryAfter) {
      XCTAssertEqual(status, 429)
      XCTAssertNil(retryAfter)
    }
    XCTAssertEqual(ProactiveLaneURLStub.requestCount, 1)

    clock.advance(by: TimeInterval(ProactiveLaneClient.defaultQuotaCooldownSeconds - 1))
    do {
      _ = try await completeExtraction(on: client)
      XCTFail("expected cooldown skip")
    } catch ProactiveLaneClientError.quotaCooldown(_) {
      // Expected: a missing Retry-After still arms the conservative default.
    }
    XCTAssertEqual(ProactiveLaneURLStub.requestCount, 1)
  }

  func testExtractionQuotaCooldownDoesNotSuppressReasoning() async throws {
    ProactiveLaneURLStub.reset()
    let clock = ManualDateClock(Date(timeIntervalSince1970: 1_800_000_000))
    let client = ProactiveLaneClient(
      session: makeStubSession(),
      baseURL: { "https://proactive.test" },
      authorization: { "Bearer test" },
      now: { clock.now })

    ProactiveLaneURLStub.enqueue(
      statusCode: 429,
      body: Data(#"{"detail":"Proactive request limit exceeded"}"#.utf8),
      headers: ["Retry-After": "120"])
    do {
      _ = try await completeExtraction(on: client)
      XCTFail("expected extraction 429")
    } catch ProactiveLaneClientError.http(let status, _) {
      XCTAssertEqual(status, 429)
    }
    XCTAssertEqual(ProactiveLaneURLStub.requestedOperations, [ModelQoS.Proactivity.extractionOperation])

    ProactiveLaneURLStub.enqueue(
      statusCode: 200,
      body: try successEnvelope(operation: ModelQoS.Proactivity.reasoningOperation))
    let reasoning = try await completeReasoning(on: client)
    XCTAssertEqual(reasoning.operation, ModelQoS.Proactivity.reasoningOperation)
    XCTAssertEqual(
      ProactiveLaneURLStub.requestedOperations,
      [ModelQoS.Proactivity.extractionOperation, ModelQoS.Proactivity.reasoningOperation],
      "reasoning must still reach the network after an extraction 429")

    do {
      _ = try await completeExtraction(on: client)
      XCTFail("expected extraction to remain in cooldown")
    } catch ProactiveLaneClientError.quotaCooldown(_) {
      // Extraction stays suppressed in its own window.
    }
    XCTAssertEqual(
      ProactiveLaneURLStub.requestedOperations,
      [ModelQoS.Proactivity.extractionOperation, ModelQoS.Proactivity.reasoningOperation],
      "a later extraction attempt in the same window must not hit the network")
  }

  func testRetryAfterAboveADayIsClampedToOneHour() async throws {
    ProactiveLaneURLStub.reset()
    let clock = ManualDateClock(Date(timeIntervalSince1970: 1_800_000_000))
    let client = ProactiveLaneClient(
      session: makeStubSession(),
      baseURL: { "https://proactive.test" },
      authorization: { "Bearer test" },
      now: { clock.now })

    ProactiveLaneURLStub.enqueue(
      statusCode: 429,
      body: Data(),
      headers: ["Retry-After": "86400"])
    do {
      _ = try await completeExtraction(on: client)
      XCTFail("expected 429")
    } catch ProactiveLaneClientError.http(let status, let retryAfter) {
      XCTAssertEqual(status, 429)
      XCTAssertEqual(retryAfter, 86400)
    }
    XCTAssertEqual(ProactiveLaneURLStub.requestCount, 1)

    clock.advance(by: TimeInterval(ProactiveLaneClient.maxQuotaCooldownSeconds - 1))
    do {
      _ = try await completeExtraction(on: client)
      XCTFail("expected the clamped hour cooldown to still skip the network")
    } catch ProactiveLaneClientError.quotaCooldown(_) {
      // Still inside the 3600s ceiling.
    }
    XCTAssertEqual(ProactiveLaneURLStub.requestCount, 1)

    clock.advance(by: 2)
    ProactiveLaneURLStub.enqueue(
      statusCode: 200,
      body: try successEnvelope(operation: ModelQoS.Proactivity.extractionOperation))
    let result = try await completeExtraction(on: client)
    XCTAssertEqual(result.operation, ModelQoS.Proactivity.extractionOperation)
    XCTAssertEqual(ProactiveLaneURLStub.requestCount, 2)
  }

  func testTinyOrZeroRetryAfterArmsAtLeastTheFloor() async throws {
    ProactiveLaneURLStub.reset()
    let clock = ManualDateClock(Date(timeIntervalSince1970: 1_800_000_000))
    let client = ProactiveLaneClient(
      session: makeStubSession(),
      baseURL: { "https://proactive.test" },
      authorization: { "Bearer test" },
      now: { clock.now })

    ProactiveLaneURLStub.enqueue(
      statusCode: 429,
      body: Data(),
      headers: ["Retry-After": "1"])
    do {
      _ = try await completeExtraction(on: client)
      XCTFail("expected 429")
    } catch ProactiveLaneClientError.http(_, _) {
      // Server 429 with a sub-floor Retry-After.
    }
    XCTAssertEqual(ProactiveLaneURLStub.requestCount, 1)

    clock.advance(by: TimeInterval(ProactiveLaneClient.minQuotaCooldownSeconds - 1))
    do {
      _ = try await completeExtraction(on: client)
      XCTFail("expected the 60s floor to still skip the network")
    } catch ProactiveLaneClientError.quotaCooldown(_) {
      // Tiny Retry-After is raised to the 60s floor.
    }
    XCTAssertEqual(ProactiveLaneURLStub.requestCount, 1)

    clock.advance(by: 2)
    ProactiveLaneURLStub.enqueue(
      statusCode: 200,
      body: try successEnvelope(operation: ModelQoS.Proactivity.extractionOperation))
    _ = try await completeExtraction(on: client)
    XCTAssertEqual(ProactiveLaneURLStub.requestCount, 2)

    ProactiveLaneURLStub.enqueue(statusCode: 429, body: Data(), headers: ["Retry-After": "0"])
    do {
      _ = try await completeReasoning(on: client)
      XCTFail("expected 429")
    } catch ProactiveLaneClientError.http(_, _) {
      // Zero Retry-After falls through to the conservative default.
    }
    clock.advance(by: TimeInterval(ProactiveLaneClient.minQuotaCooldownSeconds - 1))
    do {
      _ = try await completeReasoning(on: client)
      XCTFail("expected at least the 60s floor")
    } catch ProactiveLaneClientError.quotaCooldown(_) {
      // Zero/absent Retry-After must not arm a sub-floor cooldown.
    }
    XCTAssertEqual(ProactiveLaneURLStub.requestCount, 3)
  }

  private func completeExtraction(on client: ProactiveLaneClient) async throws -> ProactiveLaneResult {
    try await complete(operation: ModelQoS.Proactivity.extractionOperation, prompt: "extract", on: client)
  }

  private func completeReasoning(on client: ProactiveLaneClient) async throws -> ProactiveLaneResult {
    try await complete(operation: ModelQoS.Proactivity.reasoningOperation, prompt: "reason", on: client)
  }

  func testLaterShorterRetryWindowDoesNotShortenActiveCooldown() async throws {
    ProactiveLaneURLStub.reset()
    let clock = ManualDateClock(Date(timeIntervalSince1970: 1_800_000_000))
    let client = ProactiveLaneClient(
      session: makeStubSession(),
      baseURL: { "https://proactive.test" },
      authorization: { "Bearer test" },
      now: { clock.now })

    // First 429 arms a long cooldown (300s).
    ProactiveLaneURLStub.enqueue(
      statusCode: 429, body: Data(), headers: ["Retry-After": "300"])
    do {
      _ = try await completeExtraction(on: client)
      XCTFail("expected 429")
    } catch ProactiveLaneClientError.http(_, _) {}

    // A second overlapping 429 with a much shorter window must not shorten it.
    ProactiveLaneURLStub.enqueue(
      statusCode: 429, body: Data(), headers: ["Retry-After": "60"])
    do {
      _ = try await completeExtraction(on: client)
      XCTFail("expected quota cooldown")
    } catch ProactiveLaneClientError.quotaCooldown(_) {}

    XCTAssertEqual(ProactiveLaneURLStub.requestCount, 2)

    // Advance 70s — past the short window but inside the long one.
    clock.advance(by: 70)
    do {
      _ = try await completeExtraction(on: client)
      XCTFail("expected quota cooldown — longer deadline must be preserved")
    } catch ProactiveLaneClientError.quotaCooldown(_) {}

    XCTAssertEqual(
      ProactiveLaneURLStub.requestCount, 2,
      "the later shorter Retry-After must not have shortened the active cooldown")
  }

  private func complete(
    operation: String,
    prompt: String,
    on client: ProactiveLaneClient
  ) async throws -> ProactiveLaneResult {
    try await client.complete(
      operation: operation,
      prompt: prompt,
      jsonSchema: ["type": "object"])
  }

  private func successEnvelope(operation: String) throws -> Data {
    try JSONSerialization.data(withJSONObject: [
      "operation": operation,
      "lane": "omi:auto:desktop-\(operation.replacingOccurrences(of: "_", with: "-"))",
      "provider_model": "gpt-5.6-luna",
      "usage": ["cached_tokens": 0, "cache_write_tokens": 0],
      "cache_write": false,
      "fallback_class": "unknown",
      "response": ["choices": [["message": ["content": "{\"narrative\":\"ok\",\"facts\":[]}"]]]],
    ])
  }

  private func makeStubSession() -> URLSession {
    let configuration = URLSessionConfiguration.ephemeral
    configuration.protocolClasses = [ProactiveLaneURLStub.self]
    configuration.requestCachePolicy = .reloadIgnoringLocalCacheData
    return URLSession(configuration: configuration)
  }
}

private final class ManualDateClock: @unchecked Sendable {
  private let lock = NSLock()
  private var date: Date

  init(_ date: Date) {
    self.date = date
  }

  var now: Date {
    lock.lock()
    defer { lock.unlock() }
    return date
  }

  func advance(by interval: TimeInterval) {
    lock.lock()
    date = date.addingTimeInterval(interval)
    lock.unlock()
  }
}

private final class ProactiveLaneURLStub: URLProtocol, @unchecked Sendable {
  struct StubResponse {
    let statusCode: Int
    let body: Data
    let headers: [String: String]
  }

  private static let lock = NSLock()
  private nonisolated(unsafe) static var responses: [StubResponse] = []
  private nonisolated(unsafe) static var served = 0
  private nonisolated(unsafe) static var operations: [String] = []

  static var requestCount: Int {
    lock.lock()
    defer { lock.unlock() }
    return served
  }

  static var requestedOperations: [String] {
    lock.lock()
    defer { lock.unlock() }
    return operations
  }

  static func reset() {
    lock.lock()
    responses = []
    served = 0
    operations = []
    lock.unlock()
  }

  static func enqueue(statusCode: Int, body: Data, headers: [String: String] = [:]) {
    lock.lock()
    responses.append(StubResponse(statusCode: statusCode, body: body, headers: headers))
    lock.unlock()
  }

  override class func canInit(with request: URLRequest) -> Bool { true }
  override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

  override func startLoading() {
    guard let url = request.url else {
      client?.urlProtocol(self, didFailWithError: URLError(.badURL))
      return
    }
    let operation = Self.operation(from: request)
    Self.lock.lock()
    Self.operations.append(operation)
    let stub = Self.responses.isEmpty ? nil : Self.responses.removeFirst()
    Self.served += 1
    Self.lock.unlock()
    guard let stub else {
      client?.urlProtocol(self, didFailWithError: URLError(.cannotConnectToHost))
      return
    }
    guard
      let response = HTTPURLResponse(
        url: url, statusCode: stub.statusCode, httpVersion: nil, headerFields: stub.headers)
    else {
      client?.urlProtocol(self, didFailWithError: URLError(.badServerResponse))
      return
    }
    client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
    client?.urlProtocol(self, didLoad: stub.body)
    client?.urlProtocolDidFinishLoading(self)
  }

  override func stopLoading() {}

  private static func operation(from request: URLRequest) -> String {
    guard let data = bodyData(from: request),
      let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
      let operation = object["operation"] as? String
    else { return "" }
    return operation
  }

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
