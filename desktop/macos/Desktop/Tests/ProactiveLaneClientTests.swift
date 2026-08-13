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
      headers: ["Retry-After": "30"])

    do {
      _ = try await completeExtraction(on: client)
      XCTFail("expected the first extraction attempt to throw 429")
    } catch ProactiveLaneClientError.http(let status, let retryAfter) {
      XCTAssertEqual(status, 429)
      XCTAssertEqual(retryAfter, 30)
    }
    XCTAssertEqual(ProactiveLaneURLStub.requestCount, 1)

    clock.advance(by: 10)
    do {
      _ = try await completeExtraction(on: client)
      XCTFail("expected the in-window extraction attempt to skip the network")
    } catch ProactiveLaneClientError.http(let status, let retryAfter) {
      XCTAssertEqual(status, 429)
      XCTAssertEqual(retryAfter, 20)
    }
    XCTAssertEqual(
      ProactiveLaneURLStub.requestCount, 1,
      "an extraction attempt before Retry-After must not hit the network")

    clock.advance(by: 21)
    ProactiveLaneURLStub.enqueue(
      statusCode: 200,
      body: try JSONSerialization.data(withJSONObject: [
        "operation": ModelQoS.Proactivity.extractionOperation,
        "lane": "omi:auto:desktop-proactive-extraction",
        "provider_model": "gpt-5.6-luna",
        "usage": ["cached_tokens": 0, "cache_write_tokens": 0],
        "cache_write": false,
        "fallback_class": "unknown",
        "response": ["choices": [["message": ["content": "{\"narrative\":\"ok\",\"facts\":[]}"]]]],
      ]))

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
    } catch ProactiveLaneClientError.http(let status, _) {
      XCTAssertEqual(status, 429)
    }
    XCTAssertEqual(ProactiveLaneURLStub.requestCount, 1)
  }

  private func completeExtraction(on client: ProactiveLaneClient) async throws -> ProactiveLaneResult {
    try await client.complete(
      operation: ModelQoS.Proactivity.extractionOperation,
      prompt: "extract",
      jsonSchema: ["type": "object"])
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

  static var requestCount: Int {
    lock.lock()
    defer { lock.unlock() }
    return served
  }

  static func reset() {
    lock.lock()
    responses = []
    served = 0
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
    Self.lock.lock()
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
}
