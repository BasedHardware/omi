import XCTest

@testable import Omi_Computer

private final class ChatProviderCapture: URLProtocol, @unchecked Sendable {
  private static let lock = NSLock()
  private static var _requests: [URLRequest] = []
  private static var _bodies: [Data] = []
  private static var responseModel = "stub-model"

  static var bodies: [Data] {
    lock.lock()
    defer { lock.unlock() }
    return _bodies
  }

  static var requests: [URLRequest] {
    lock.lock()
    defer { lock.unlock() }
    return _requests
  }

  static func reset(model: String = "stub-model") {
    lock.lock()
    _requests.removeAll()
    _bodies.removeAll()
    responseModel = model
    lock.unlock()
  }

  private static func record(request: URLRequest, body: Data) {
    lock.lock()
    _requests.append(request)
    _bodies.append(body)
    lock.unlock()
  }

  private static func bodyData(from request: URLRequest) -> Data {
    if let body = request.httpBody {
      return body
    }
    guard let stream = request.httpBodyStream else {
      return Data()
    }
    stream.open()
    defer { stream.close() }

    var data = Data()
    let bufferSize = 4096
    let buffer = UnsafeMutablePointer<UInt8>.allocate(capacity: bufferSize)
    defer { buffer.deallocate() }
    while stream.hasBytesAvailable {
      let count = stream.read(buffer, maxLength: bufferSize)
      if count > 0 {
        data.append(buffer, count: count)
      } else {
        break
      }
    }
    return data
  }

  override class func canInit(with request: URLRequest) -> Bool { true }
  override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

  override func startLoading() {
    let body = Self.bodyData(from: request)
    Self.record(request: request, body: body)
    let model = Self.responseModel
    let response = HTTPURLResponse(
      url: request.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!
    let payload = Data(
      """
      {"model":"\(model)","choices":[{"message":{"content":"answer"}}],"usage":{"prompt_tokens":7,"completion_tokens":3}}
      """.utf8)
    client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
    client?.urlProtocol(self, didLoad: payload)
    client?.urlProtocolDidFinishLoading(self)
  }

  override func stopLoading() {}
}

final class HybridChatClientTests: XCTestCase {
  override func setUp() {
    super.setUp()
    ChatProviderCapture.reset()
  }

  func testChatSlotResolutionBuildsProviderConfig() {
    let response = slotResolution(
      accountID: "local-a",
      baseURL: "http://127.0.0.1:11434/v1",
      model: "llama3.2"
    )

    let config = HybridChatClient.resolveEffectiveChatConfig(from: response)

    XCTAssertEqual(config?.baseURL, "http://127.0.0.1:11434/v1")
    XCTAssertEqual(config?.model, "llama3.2")
    XCTAssertEqual(config?.providerAccountID, "local-a")
    XCTAssertEqual(config?.slotSource, "provider_policy")
  }

  func testRequestBodyUsesSelectedChatSlotModel() async throws {
    let session = capturedSession()
    let response = slotResolution(
      accountID: "local-chat",
      baseURL: "http://127.0.0.1:11434/v1",
      model: "selected-model"
    )

    let result = try await HybridChatClient.complete(
      systemPrompt: "system",
      conversationMessages: [(role: "assistant", text: "prior")],
      userMessage: "hello",
      slotResolution: response,
      session: session
    )

    let body = try XCTUnwrap(ChatProviderCapture.bodies.first)
    let json = try JSONSerialization.jsonObject(with: body) as? [String: Any]
    XCTAssertEqual(json?["model"] as? String, "selected-model")
    XCTAssertEqual(result.providerAccountID, "local-chat")
    XCTAssertEqual(result.model, "stub-model")
  }

  func testProviderAccountSwitchChangesRequestTargetAndModel() async throws {
    let session = capturedSession()

    _ = try await HybridChatClient.complete(
      systemPrompt: "system",
      conversationMessages: [],
      userMessage: "one",
      slotResolution: slotResolution(
        accountID: "provider-a",
        baseURL: "http://127.0.0.1:11434/v1",
        model: "model-a"
      ),
      session: session
    )
    _ = try await HybridChatClient.complete(
      systemPrompt: "system",
      conversationMessages: [],
      userMessage: "two",
      slotResolution: slotResolution(
        accountID: "provider-b",
        baseURL: "http://localhost:43210/v1",
        model: "model-b"
      ),
      session: session
    )

    let requests = ChatProviderCapture.requests
    XCTAssertEqual(requests.map { $0.url?.absoluteString }, [
      "http://127.0.0.1:11434/v1/chat/completions",
      "http://localhost:43210/v1/chat/completions",
    ])
    let models = try ChatProviderCapture.bodies.map { body in
      let json = try XCTUnwrap(JSONSerialization.jsonObject(with: body) as? [String: Any])
      return json["model"] as? String
    }
    XCTAssertEqual(models, ["model-a", "model-b"])
  }

  func testMissingChatSlotReasonIsSurfaced() async {
    let response = HybridProviderPolicy.SlotResolutionResponse(
      resolved: nil,
      resolution: HybridProviderPolicy.SlotResolution(
        slot: "chat",
        ok: false,
        resolved: nil,
        reason: "model slot chat selects gpt-5.4-mini but no provider account is configured"
      )
    )

    do {
      _ = try await HybridChatClient.complete(
        systemPrompt: "system",
        conversationMessages: [],
        userMessage: "hello",
        slotResolution: response,
        session: capturedSession()
      )
      XCTFail("expected missing provider error")
    } catch {
      XCTAssertTrue(error.localizedDescription.contains("no provider account"))
      XCTAssertTrue(ChatProviderCapture.requests.isEmpty)
    }
  }

  func testLocalDaemonChatDoesNotUseOmiHostedEndpoints() async throws {
    _ = try await HybridChatClient.complete(
      systemPrompt: "system",
      conversationMessages: [],
      userMessage: "hello",
      slotResolution: slotResolution(
        accountID: "local-only",
        baseURL: "http://127.0.0.1:9999/v1",
        model: "local-model"
      ),
      session: capturedSession()
    )

    let url = try XCTUnwrap(ChatProviderCapture.requests.first?.url?.absoluteString)
    XCTAssertTrue(url.hasPrefix("http://127.0.0.1:9999/v1/chat/completions"))
    XCTAssertFalse(url.contains("omi.me"))
    XCTAssertFalse(url.contains("omiapi.com"))
  }

  private func capturedSession() -> URLSession {
    let config = URLSessionConfiguration.ephemeral
    config.protocolClasses = [ChatProviderCapture.self]
    return URLSession(configuration: config)
  }

  private func slotResolution(
    accountID: String,
    baseURL: String,
    model: String
  ) -> HybridProviderPolicy.SlotResolutionResponse {
    let account = HybridProviderPolicy.ProviderAccount(
      id: accountID,
      kind: "openai_compatible",
      baseURL: baseURL,
      apiKey: "test-key"
    )
    let resolved = HybridProviderPolicy.ResolvedSlot(
      slot: "chat",
      providerAccount: account,
      modelID: model,
      source: "provider_policy"
    )
    let resolution = HybridProviderPolicy.SlotResolution(
      slot: "chat",
      ok: true,
      resolved: resolved,
      reason: "chat resolved to \(model) from provider_policy"
    )
    return HybridProviderPolicy.SlotResolutionResponse(resolved: resolved, resolution: resolution)
  }
}
