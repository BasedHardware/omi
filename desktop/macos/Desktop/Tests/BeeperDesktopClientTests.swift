import XCTest

@testable import Omi_Computer

/// Hermetic transport stub: answers Beeper REST requests from recorded
/// fixtures keyed by "METHOD path". No live Beeper install involved.
final class BeeperStubURLProtocol: URLProtocol {
  struct Stub {
    var statusCode: Int
    var body: Data
  }

  nonisolated(unsafe) static var stubs: [String: Stub] = [:]
  nonisolated(unsafe) static var recordedRequests: [(method: String, url: URL, body: Data?)] = []

  static func reset() {
    stubs = [:]
    recordedRequests = []
  }

  static func key(_ method: String, _ path: String) -> String { "\(method) \(path)" }

  override class func canInit(with request: URLRequest) -> Bool { true }
  override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

  override func startLoading() {
    let method = request.httpMethod ?? "GET"
    let url = request.url!
    let bodyData = request.httpBody ?? request.httpBodyStream.map { stream -> Data in
      stream.open()
      defer { stream.close() }
      var data = Data()
      var buffer = [UInt8](repeating: 0, count: 4096)
      while stream.hasBytesAvailable {
        let read = stream.read(&buffer, maxLength: buffer.count)
        guard read > 0 else { break }
        data.append(buffer, count: read)
      }
      return data
    }
    Self.recordedRequests.append((method, url, bodyData))
    let stub = Self.stubs[Self.key(method, url.path)]
      ?? Stub(statusCode: 404, body: Data(#"{"error":{"code":"NOT_FOUND"}}"#.utf8))
    let response = HTTPURLResponse(
      url: url, statusCode: stub.statusCode, httpVersion: "HTTP/1.1", headerFields: nil)!
    client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
    client?.urlProtocol(self, didLoad: stub.body)
    client?.urlProtocolDidFinishLoading(self)
  }

  override func stopLoading() {}
}

final class BeeperDesktopClientTests: XCTestCase {
  private func makeClient(token: String = "test-token") -> BeeperDesktopClient {
    let config = URLSessionConfiguration.ephemeral
    config.protocolClasses = [BeeperStubURLProtocol.self]
    return BeeperDesktopClient(
      accessToken: token,
      session: URLSession(configuration: config))
  }

  override func setUp() {
    super.setUp()
    BeeperStubURLProtocol.reset()
  }

  func testProbeAndAccountsDecodeAndCarryBearerToken() async throws {
    BeeperStubURLProtocol.stubs[BeeperStubURLProtocol.key("GET", "/v1/info")] =
      .init(statusCode: 200, body: Data("{}".utf8))
    BeeperStubURLProtocol.stubs[BeeperStubURLProtocol.key("GET", "/v1/accounts")] = .init(
      statusCode: 200,
      body: Data(
        #"[{"accountID":"local-whatsapp_ba_x","network":"WhatsApp","user":{"id":"@me:beeper.com","isSelf":true}}]"#
          .utf8))

    let client = makeClient()
    _ = try await client.probeInfo()
    let accounts = try await client.listAccounts()

    XCTAssertEqual(accounts.count, 1)
    XCTAssertEqual(accounts.first?.displayNetwork, "WhatsApp")
  }

  func testSendMessagePostsTextAndDecodesPendingID() async throws {
    BeeperStubURLProtocol.stubs[BeeperStubURLProtocol.key("POST", "/v1/chats/chat-1/messages")] = .init(
      statusCode: 200,
      body: Data(#"{"chatID":"chat-1","pendingMessageID":"pending-9"}"#.utf8))

    let response = try await makeClient().sendMessage(chatID: "chat-1", text: "see you at 7")

    XCTAssertEqual(response.pendingMessageID, "pending-9")
    let sent = BeeperStubURLProtocol.recordedRequests.first { $0.method == "POST" }
    XCTAssertNotNil(sent)
    let payload = try JSONSerialization.jsonObject(with: sent?.body ?? Data()) as? [String: Any]
    XCTAssertEqual(payload?["text"] as? String, "see you at 7")
  }

  func testHTTP401SurfacesAsTypedHTTPError() async {
    BeeperStubURLProtocol.stubs[BeeperStubURLProtocol.key("GET", "/v1/info")] = .init(
      statusCode: 401, body: Data(#"{"error":{"code":"UNAUTHORIZED","message":"bad token"}}"#.utf8))

    do {
      _ = try await makeClient().probeInfo()
      XCTFail("expected 401 to throw")
    } catch let BeeperClientError.httpError(statusCode, code) {
      XCTAssertEqual(statusCode, 401)
      XCTAssertEqual(code, "UNAUTHORIZED")
    } catch {
      XCTFail("unexpected error \(error)")
    }
  }

  func testEmptyTokenFailsClosedWithoutNetworkCall() async {
    do {
      _ = try await makeClient(token: "   ").probeInfo()
      XCTFail("expected notConfigured")
    } catch BeeperClientError.notConfigured {
      XCTAssertTrue(BeeperStubURLProtocol.recordedRequests.isEmpty)
    } catch {
      XCTFail("unexpected error \(error)")
    }
  }

  func testMessagesPageAndLiveEventDecodeFromWireShapes() throws {
    let page = try JSONDecoder().decode(
      BeeperCursorPage<BeeperMessage>.self,
      from: Data(
        #"{"items":[{"id":"m1","chatID":"c1","senderID":"@a","sortKey":"1","timestamp":"2026-07-15T01:00:00Z","text":"hey! how was Korea?","type":"TEXT","isSender":false,"senderName":"Alice"}],"hasMore":false,"oldestCursor":null,"newestCursor":null}"#
          .utf8))
    XCTAssertEqual(page.items.first?.senderName, "Alice")

    let event = BeeperDesktopClient.decodeLiveEvent(
      #"{"type":"message.upserted","seq":4,"ts":1739320000000,"chatID":"c1","ids":["m1"],"entries":[{"id":"m1","text":"hello","type":"TEXT","isSender":false,"timestamp":"2026-07-15T01:00:00Z"}]}"#)
    XCTAssertEqual(event?.type, "message.upserted")
    XCTAssertEqual(event?.entries?.first?.text, "hello")
  }

  func testDiscoverBaseURLAdoptsPortFromPublicInfo() async {
    // /v1/info is public and reports the authoritative base_url; the client
    // must adopt it so a Beeper port change (23373 -> 23374) self-corrects.
    BeeperStubURLProtocol.stubs[BeeperStubURLProtocol.key("GET", "/v1/info")] = .init(
      statusCode: 200,
      body: Data(#"{"server":{"base_url":"http://127.0.0.1:23374","port":23374}}"#.utf8))
    let config = URLSessionConfiguration.ephemeral
    config.protocolClasses = [BeeperStubURLProtocol.self]
    let discovered = await BeeperDesktopClient.discoverBaseURL(
      session: URLSession(configuration: config))
    XCTAssertEqual(discovered?.absoluteString, "http://127.0.0.1:23374")
  }

  func testSubscriptionPayloadMatchesWireContract() throws {
    let payload = try BeeperDesktopClient.subscriptionsSetPayload(chatIDs: ["*"], requestID: "r1")
    let object = try JSONSerialization.jsonObject(with: Data(payload.utf8)) as? [String: Any]
    XCTAssertEqual(object?["type"] as? String, "subscriptions.set")
    XCTAssertEqual(object?["requestID"] as? String, "r1")
    XCTAssertEqual(object?["chatIDs"] as? [String], ["*"])
  }
}

final class AICloneInboundFilterTests: XCTestCase {
  private func message(
    id: String = "m1",
    text: String? = "hello",
    isSender: Bool = false,
    timestamp: String
  ) -> BeeperMessage {
    BeeperMessage(
      id: id, accountID: "a", chatID: "c", senderID: "@x", senderName: "Alice",
      sortKey: "1", timestamp: timestamp, text: text, type: "TEXT",
      isSender: isSender, isUnread: true, isDeleted: false)
  }

  func testHistoryBackfillOlderThanListeningSessionNeverTriggers() {
    let since = Date()
    let old = message(timestamp: "2020-01-01T00:00:00Z")
    XCTAssertNil(AICloneService.latestActionableInbound(entries: [old], since: since))
  }

  func testOwnEchoedMessagesNeverTrigger() {
    let since = Date(timeIntervalSince1970: 0)
    let mine = message(isSender: true, timestamp: "2026-07-15T01:00:00Z")
    XCTAssertNil(AICloneService.latestActionableInbound(entries: [mine], since: since))
  }

  func testFreshInboundTextTriggersAndNewestWins() {
    let since = Date(timeIntervalSince1970: 0)
    let first = message(id: "m1", text: "hi", timestamp: "2026-07-15T01:00:00Z")
    let second = message(id: "m2", text: "you there?", timestamp: "2026-07-15T01:00:05Z")
    let picked = AICloneService.latestActionableInbound(entries: [first, second], since: since)
    XCTAssertEqual(picked?.id, "m2")
  }
}

final class AICloneBenchmarkTests: XCTestCase {
  private func msg(_ id: String, _ text: String, mine: Bool, sender: String? = nil) -> BeeperMessage {
    BeeperMessage(
      id: id, accountID: "a", chatID: "c", senderID: "@x",
      senderName: mine ? nil : (sender ?? "Alice"),
      sortKey: id, timestamp: "2026-07-15T01:00:00Z", text: text, type: "TEXT",
      isSender: mine, isUnread: false, isDeleted: false)
  }

  func testSamplesPairInboundWithUsersRealReply() {
    let history = [
      msg("1", "hey, how was Korea?", mine: false),
      msg("2", "so good — Seoul food is unreal", mine: true),
      msg("3", "haha nice. dinner friday?", mine: false),
      msg("4", "yes! 7pm?", mine: true),
    ]
    let samples = AICloneBenchmark.samples(from: history)
    XCTAssertEqual(samples.count, 2)
    XCTAssertEqual(samples[0].inboundText, "hey, how was Korea?")
    XCTAssertEqual(samples[0].actualReply, "so good — Seoul food is unreal")
    XCTAssertEqual(samples[1].inboundText, "haha nice. dinner friday?")
    XCTAssertEqual(samples[1].priorThreadLines.count, 2)
  }

  func testConsecutiveOwnMessagesProduceNoSample() {
    let history = [
      msg("1", "reminder to self", mine: true),
      msg("2", "and another", mine: true),
    ]
    XCTAssertTrue(AICloneBenchmark.samples(from: history).isEmpty)
  }

  func testJudgeScoreParsingClampsAndTolerantOfProse() {
    XCTAssertEqual(AICloneBenchmark.parseJudgeScore(#"{"score": 87}"#), 87)
    XCTAssertEqual(AICloneBenchmark.parseJudgeScore(#"Sure: {"score": 250}"#), 100)
    XCTAssertNil(AICloneBenchmark.parseJudgeScore("no json here"))
  }
}
