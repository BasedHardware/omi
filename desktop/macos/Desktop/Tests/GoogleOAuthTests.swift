import CryptoKit
import XCTest

@testable import Omi_Computer

final class MockURLProtocol: URLProtocol, @unchecked Sendable {
  nonisolated(unsafe) static var handler: ((URLRequest) throws -> (HTTPURLResponse, Data))?

  override class func canInit(with request: URLRequest) -> Bool { true }
  override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

  override func startLoading() {
    guard let handler = Self.handler else {
      client?.urlProtocol(self, didFailWithError: URLError(.unsupportedURL))
      return
    }
    do {
      let (response, data) = try handler(request)
      client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
      client?.urlProtocol(self, didLoad: data)
      client?.urlProtocolDidFinishLoading(self)
    } catch {
      client?.urlProtocol(self, didFailWithError: error)
    }
  }

  override func stopLoading() {}

  static func body(of request: URLRequest) -> Data {
    if let body = request.httpBody { return body }
    guard let stream = request.httpBodyStream else { return Data() }
    stream.open()
    defer { stream.close() }
    var data = Data()
    let buffer = UnsafeMutablePointer<UInt8>.allocate(capacity: 4096)
    defer { buffer.deallocate() }
    while stream.hasBytesAvailable {
      let read = stream.read(buffer, maxLength: 4096)
      if read <= 0 { break }
      data.append(buffer, count: read)
    }
    return data
  }
}

final class VolatileGoogleOAuthStore: GoogleOAuthStoring {
  private var storedValues: [GoogleOAuthConnection] = []
  private let lock = NSLock()
  var values: [GoogleOAuthConnection] {
    get {
      lock.lock()
      defer { lock.unlock() }
      return storedValues
    }
    set {
      lock.lock()
      defer { lock.unlock() }
      storedValues = newValue
    }
  }

  func readAll() -> [GoogleOAuthConnection] {
    lock.lock()
    defer { lock.unlock() }
    return storedValues
  }
  func write(_ connections: [GoogleOAuthConnection]) -> Bool {
    lock.lock()
    defer { lock.unlock() }
    storedValues = connections
    return true
  }
}

private func mockSession() -> URLSession {
  let config = URLSessionConfiguration.ephemeral
  config.protocolClasses = [MockURLProtocol.self]
  return URLSession(configuration: config)
}

private func jsonResponse(_ object: [String: Any], status: Int = 200) -> (HTTPURLResponse, Data) {
  // swiftlint:disable:next force_try — fixed JSON fixture cannot fail
  // swiftlint:disable:next force_try — fixed JSON fixture cannot fail
  let data = try! JSONSerialization.data(withJSONObject: object)
  let response = HTTPURLResponse(
    url: URL(string: "https://example.test")!, statusCode: status,
    // swiftlint:disable:next force_unwrapping — fixed literal and parameters cannot fail
    httpVersion: nil, headerFields: nil)!
  return (response, data)
}

private func connection(
  accessToken: String = "access-1",
  expiresAt: Date = Date(timeIntervalSince1970: 2_000_000_000),
  refreshToken: String? = "refresh-1",
  account: String? = nil,
  needsReconnect: Bool = false
) -> GoogleOAuthConnection {
  GoogleOAuthConnection(
    accessToken: accessToken,
    expiresAt: expiresAt,
    grantedScopes: GoogleOAuth.scopes,
    refreshToken: refreshToken,
    account: account,
    needsReconnect: needsReconnect
  )
}

final class GoogleOAuthTests: XCTestCase {
  override func setUp() {
    super.setUp()
    GoogleOAuth.clientId = nil
    GoogleOAuth.clientSecret = nil
    MockURLProtocol.handler = nil
  }

  func testPkceChallengeIsUnpaddedBase64UrlSha256() throws {
    let verifier = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-._~"
    let expected = Data(SHA256.hash(data: Data(verifier.utf8)))
      .base64EncodedString()
      .replacingOccurrences(of: "+", with: "-")
      .replacingOccurrences(of: "/", with: "_")
      .replacingOccurrences(of: "=", with: "")
    XCTAssertEqual(PkcePair.challenge(from: verifier), expected)
    let pair = try PkcePair.generate()
    XCTAssertEqual(pair.verifier.count, 64)
    XCTAssertEqual(pair.challenge, PkcePair.challenge(from: pair.verifier))
    XCTAssertFalse(pair.verifier.contains("="))
  }

  func testAuthorizationURLCarriesChallengeAndNeverTheVerifier() {
    // swiftlint:disable:next force_unwrapping — fixed literal cannot fail
    let uri = URL(string: "http://127.0.0.1:51234/oauth/callback")!
    let url = GoogleOAuthConnectionManager.authorizationURL(
      clientId: "client-abc",
      redirectUri: uri,
      challenge: "challenge-1",
      state: "state-1"
    )
    // swiftlint:disable:next force_unwrapping — built from fixed components cannot fail
    let query = URLComponents(url: url, resolvingAgainstBaseURL: false)!.queryItems ?? []
    let params = Dictionary(uniqueKeysWithValues: query.map { ($0.name, $0.value ?? "") })
    XCTAssertEqual(params["response_type"], "code")
    XCTAssertEqual(params["client_id"], "client-abc")
    XCTAssertEqual(params["code_challenge"], "challenge-1")
    XCTAssertEqual(params["code_challenge_method"], "S256")
    XCTAssertEqual(params["state"], "state-1")
    XCTAssertEqual(params["access_type"], "offline")
    XCTAssertTrue((params["scope"] ?? "").contains("gmail.readonly"))
    XCTAssertTrue((params["scope"] ?? "").contains("calendar.readonly"))
    XCTAssertFalse((params["scope"] ?? "").contains("gmail.modify"))
    XCTAssertFalse(url.absoluteString.contains("verifier"))
  }

  func testCodeFromRedirectValidatesState() {
    // swiftlint:disable:next force_unwrapping — fixed literal cannot fail
    let uri = URL(string: "http://127.0.0.1:51234/oauth/callback?code=c&state=state-1")!
    XCTAssertEqual(
      GoogleOAuthConnectionManager.code(from: uri, expectedState: "state-1"), "c")
    XCTAssertNil(
      GoogleOAuthConnectionManager.code(
        // swiftlint:disable:next force_unwrapping — fixed literal cannot fail
        from: URL(string: "http://127.0.0.1:51234/oauth/callback?code=c&state=other")!,
        expectedState: "state-1"))
    XCTAssertNil(
      GoogleOAuthConnectionManager.code(
        // swiftlint:disable:next force_unwrapping — fixed literal cannot fail
        from: URL(string: "http://127.0.0.1:51234/oauth/callback?error=access_denied&state=state-1")!,
        expectedState: "state-1"))
  }

  func testRedirectURLFromRequestHead() {
    let head =
      "GET /oauth/callback?code=c&state=state-1 HTTP/1.1\r\nHost: 127.0.0.1\r\n\r\n"
    let url = LoopbackRedirectServer.redirectURL(fromRequestHead: head)
    XCTAssertEqual(url?.path, "/oauth/callback")
    XCTAssertEqual(url?.query, "code=c&state=state-1")
    XCTAssertNil(LoopbackRedirectServer.redirectURL(fromRequestHead: "POST / HTTP/1.1\r\n\r\n"))
  }

  func testCalendarEventUntitledFallbackAndFractionalSeconds() {
    let dict: [String: Any] = [
      "id": "ev-frac",
      "start": ["dateTime": "2026-03-20T09:00:00.123Z"],
      "end": ["dateTime": "2026-03-20T09:30:00Z"],
    ]
    let event = GoogleOAuthCalendarReader.parseEvent(dict)
    XCTAssertEqual(event?.id, "ev-frac")
    // Missing summary falls back to "Untitled" instead of dropping the event.
    XCTAssertEqual(event?.summary, "Untitled")
    // Fractional-second dateTime still parses to a wall-clock time.
    XCTAssertEqual(event?.startTime, "2026-03-20T09:00:00Z")
    XCTAssertEqual(event?.endTime, "2026-03-20T09:30:00Z")
  }

  func testMissingRequiredScopesAreReportedBeforePersistence() {
    XCTAssertEqual(
      GoogleOAuthConnectionManager.missingRequiredScopes(["openid"]),
      [
        "https://www.googleapis.com/auth/calendar.readonly",
        "https://www.googleapis.com/auth/gmail.readonly",
      ]
    )
    XCTAssertEqual(
      GoogleOAuthConnectionManager.missingRequiredScopes(GoogleOAuth.scopes), [])
  }

  func testOAuthStoreAccountChangesWithSignedInOmiUser() {
    let defaults = UserDefaults.standard
    let original = defaults.string(forKey: DefaultsKey.authUserId.rawValue)
    defer {
      defaults.set(original, forKey: DefaultsKey.authUserId.rawValue)
    }
    defaults.set("omi-user-a", forKey: DefaultsKey.authUserId.rawValue)
    let first = GoogleOAuthStore.account
    defaults.set("omi-user-b", forKey: DefaultsKey.authUserId.rawValue)
    let second = GoogleOAuthStore.account
    XCTAssertNotEqual(first, second)
    XCTAssertTrue(first.hasSuffix("omi-user-a"))
    XCTAssertTrue(second.hasSuffix("omi-user-b"))
  }

  func testExchangeWithoutVerifiedAccountFails() async throws {
    MockURLProtocol.handler = { request in
      if request.url?.host?.contains("openidconnect") == true {
        // userinfo returns no email — the exchange must not produce a grant
        // that would be keyed on a nil account.
        return jsonResponse([:], status: 200)
      }
      return jsonResponse(["access_token": "at", "expires_in": 3600])
    }
    let client = GoogleOAuthTokenClient(session: mockSession())
    let value = try await client.exchangeCode(
      code: "code-1", verifier: String(repeating: "v", count: 64), redirectUri: "http://127.0.0.1:1/x",
      clientId: "client-abc")
    XCTAssertNil(value.account)
  }

  func testManagerUpsertReportsWriteFailure() {
    struct FailingStore: GoogleOAuthStoring {
      func readAll() -> [GoogleOAuthConnection] { [] }
      func write(_ connections: [GoogleOAuthConnection]) -> Bool { false }
    }
    let manager = GoogleOAuthConnectionManager(
      store: FailingStore(), tokenClient: GoogleOAuthTokenClient(session: mockSession()))
    XCTAssertFalse(manager.upsert(connection(account: "a@b.co")))
  }

  func testRandomStateIsNonEmpty() throws {
    let state = try GoogleOAuthConnectionManager.randomState()
    XCTAssertFalse(state.isEmpty)
  }

  func testExchangeSendsCodeVerifierAndNamesAccount() async throws {
    MockURLProtocol.handler = { request in
      if request.url?.host?.contains("openidconnect") == true {
        return jsonResponse(["email": "work@corp.com", "email_verified": true, "name": "Work"])
      }
      let body = String(data: MockURLProtocol.body(of: request), encoding: .utf8) ?? ""
      XCTAssertTrue(body.contains("grant_type=authorization_code"))
      XCTAssertTrue(body.contains("code_verifier="))
      XCTAssertFalse(body.contains("client_secret"))
      return jsonResponse([
        "access_token": "at",
        "refresh_token": "rt",
        "expires_in": 3600,
        "scope": "https://www.googleapis.com/auth/gmail.readonly",
      ])
    }
    let client = GoogleOAuthTokenClient(session: mockSession())
    let value = try await client.exchangeCode(
      code: "code-1", verifier: String(repeating: "v", count: 64), redirectUri: "http://127.0.0.1:1/x",
      clientId: "client-abc")
    XCTAssertEqual(value.accessToken, "at")
    XCTAssertEqual(value.refreshToken, "rt")
    XCTAssertEqual(value.account, "work@corp.com")
    XCTAssertEqual(value.grantedScopes, ["https://www.googleapis.com/auth/gmail.readonly"])
  }

  func testExchangeSendsClientSecretWhenConfigured() async throws {
    GoogleOAuth.clientSecret = "secret-1"
    MockURLProtocol.handler = { request in
      if request.url?.host?.contains("openidconnect") == true {
        return jsonResponse([:])
      }
      let body = String(data: MockURLProtocol.body(of: request), encoding: .utf8) ?? ""
      XCTAssertTrue(body.contains("client_secret=secret-1"))
      return jsonResponse(["access_token": "at", "expires_in": 3600])
    }
    let client = GoogleOAuthTokenClient(session: mockSession())
    let value = try await client.exchangeCode(
      code: "code-1", verifier: String(repeating: "v", count: 64), redirectUri: "http://127.0.0.1:1/x",
      clientId: "client-abc")
    XCTAssertEqual(value.accessToken, "at")
  }

  func testRefreshInvalidGrantSurfacesAsReconnect() async {
    MockURLProtocol.handler = { _ in
      jsonResponse(["error": "invalid_grant", "error_description": "bad"], status: 400)
    }
    let client = GoogleOAuthTokenClient(session: mockSession())
    do {
      _ = try await client.refresh(connection(expiresAt: Date()), clientId: "client-abc")
      XCTFail("expected invalid grant")
    } catch let error as GoogleOAuthError {
      XCTAssertEqual(error.errorDescription, GoogleOAuthError.invalidGrant.errorDescription)
    } catch {
      XCTFail("unexpected error \(error)")
    }
  }

  func testManagerKeepsOneGrantPerAccount() {
    let store = VolatileGoogleOAuthStore()
    let manager = GoogleOAuthConnectionManager(
      store: store, tokenClient: GoogleOAuthTokenClient(session: mockSession()))
    XCTAssertTrue(
      manager.upsert(connection(accessToken: "access-1", account: "junk@gmail.com")))
    XCTAssertTrue(
      manager.upsert(connection(accessToken: "access-2", account: "work@corp.com")))
    XCTAssertEqual(store.readAll().count, 2)
    XCTAssertTrue(
      manager.upsert(connection(accessToken: "access-3", account: "junk@gmail.com")))
    XCTAssertEqual(store.readAll().count, 2)
    XCTAssertEqual(
      store.readAll().first { $0.account == "junk@gmail.com" }?.accessToken, "access-3")
  }

  func testAccessTokenUsesUnexpiredGrantWithoutNetwork() async throws {
    let store = VolatileGoogleOAuthStore()
    store.values = [connection(accessToken: "work-token", account: "work@corp.com")]
    let manager = GoogleOAuthConnectionManager(
      store: store, tokenClient: GoogleOAuthTokenClient(session: mockSession()))
    MockURLProtocol.handler = { _ in
      XCTFail("no network expected")
      return jsonResponse([:])
    }
    let token = try await manager.accessToken(account: "work@corp.com")
    XCTAssertEqual(token, "work-token")
  }

  func testAccessTokenRejectsStaleGrant() async {
    let store = VolatileGoogleOAuthStore()
    store.values = [connection(account: "old@corp.com", needsReconnect: true)]
    let manager = GoogleOAuthConnectionManager(
      store: store, tokenClient: GoogleOAuthTokenClient(session: mockSession()))
    do {
      _ = try await manager.accessToken(account: "old@corp.com")
      XCTFail("expected reconnect")
    } catch let error as GoogleOAuthError {
      XCTAssertEqual(error.errorDescription, GoogleOAuthError.reconnectRequired.errorDescription)
    } catch {
      XCTFail("unexpected error \(error)")
    }
  }

  func testAccessTokenRefreshesExpiredGrant() async throws {
    let store = VolatileGoogleOAuthStore()
    store.values = [
      connection(accessToken: "old", expiresAt: Date(timeIntervalSince1970: 1_000), account: "a@b.co")
    ]
    GoogleOAuth.clientId = "client-abc"
    MockURLProtocol.handler = { request in
      XCTAssertEqual(request.url, GoogleOAuth.tokenEndpoint)
      return jsonResponse(["access_token": "fresh", "expires_in": 3600])
    }
    let manager = GoogleOAuthConnectionManager(
      store: store, tokenClient: GoogleOAuthTokenClient(session: mockSession()))
    let token = try await manager.accessToken(account: "a@b.co")
    XCTAssertEqual(token, "fresh")
    XCTAssertEqual(store.readAll().first?.accessToken, "fresh")
  }

  func testDisconnectRemovesOnlyNamedAccount() async {
    let store = VolatileGoogleOAuthStore()
    store.values = [
      connection(account: "junk@gmail.com"),
      connection(refreshToken: "refresh-2", account: "work@corp.com"),
    ]
    MockURLProtocol.handler = { _ in jsonResponse([:]) }
    let manager = GoogleOAuthConnectionManager(
      store: store, tokenClient: GoogleOAuthTokenClient(session: mockSession()))
    try? await manager.disconnect(account: "work@corp.com")
    XCTAssertEqual(store.readAll().count, 1)
    XCTAssertEqual(store.readAll().first?.account, "junk@gmail.com")
  }

  func testDisconnectDoesNotRemoveReplacementGrant() {
    let store = VolatileGoogleOAuthStore()
    let old = connection(accessToken: "old", account: "work@corp.com")
    let replacement = connection(accessToken: "new", account: "work@corp.com")
    store.values = [old]
    let manager = GoogleOAuthConnectionManager(
      store: store, tokenClient: GoogleOAuthTokenClient(session: mockSession()))
    store.values = [replacement]
    XCTAssertTrue(manager.remove(account: replacement.account, expected: old))
    XCTAssertEqual(store.readAll().first?.accessToken, "new")
  }

  func testGmailParseMessage() {
    let body: [String: Any] = [
      "id": "msg-1",
      "snippet": "re: launch",
      "internalDate": "1730000000000",
      "labelIds": ["INBOX", "UNREAD"],
      "payload": [
        "headers": [
          ["name": "Subject", "value": "Launch notes"],
          ["name": "From", "value": "a@b.co"],
        ]
      ],
    ]
    let email = GoogleOAuthGmailReader.parseMessage(body)
    XCTAssertEqual(email?.id, "msg-1")
    XCTAssertEqual(email?.subject, "Launch notes")
    XCTAssertEqual(email?.from, "a@b.co")
    XCTAssertEqual(email?.isUnread, true)
    XCTAssertEqual(email?.date, Date(timeIntervalSince1970: 1_730_000_000))
  }

  func testCalendarParseEvent() {
    let dict: [String: Any] = [
      "id": "ev-1",
      "summary": "Standup",
      "start": ["dateTime": "2026-03-20T09:00:00Z"],
      "end": ["dateTime": "2026-03-20T09:30:00Z"],
      "attendees": [
        ["displayName": "Kim", "email": "kim@b.co"],
        ["email": "no-name@b.co"],
        ["displayName": "Self", "email": "me@b.co", "self": true],
      ],
      "location": "Room 1",
      "description": "notes",
    ]
    let event = GoogleOAuthCalendarReader.parseEvent(dict)
    XCTAssertEqual(event?.id, "ev-1")
    XCTAssertEqual(event?.summary, "Standup")
    XCTAssertEqual(event?.startTime, "2026-03-20T09:00:00Z")
    XCTAssertEqual(event?.attendees, ["Kim", "no-name@b.co"])
    XCTAssertEqual(event?.location, "Room 1")
    XCTAssertEqual(event?.isAllDay, false)
  }

  func testGmailReaderPaginatesAndSkipsDeletedMessages() async throws {
    let lock = NSLock()
    var detailPaths: [String] = []
    MockURLProtocol.handler = { request in
      let path = request.url?.path ?? ""
      if path.hasSuffix("/msg-2") {
        return jsonResponse(["error": ["code": 404]], status: 404)
      }
      if path.hasSuffix("/msg-1") {
        lock.lock()
        detailPaths.append(path)
        lock.unlock()
        return jsonResponse([
          "id": "msg-1",
          "internalDate": "1730000000000",
          "payload": ["headers": [["name": "FROM", "value": "a@b.co"]]],
        ])
      }
      guard let url = request.url else { throw URLError(.badURL) }
      let pageToken = URLComponents(url: url, resolvingAgainstBaseURL: false)?.queryItems?
        .first(where: { $0.name == "pageToken" })?.value
      if pageToken == nil {
        return jsonResponse(["messages": [["id": "msg-1"]], "nextPageToken": "page-2"])
      }
      return jsonResponse(["messages": [["id": "msg-2"]]])
    }
    let emails = try await GoogleOAuthGmailReader.readRecentEmails(
      token: "token", maxResults: 2, session: mockSession())
    XCTAssertEqual(emails.map(\.id), ["msg-1"])
    XCTAssertEqual(emails.first?.from, "a@b.co")
    XCTAssertEqual(detailPaths.count, 1)
  }

  func testCalendarReaderPaginatesAndPreservesUntitledEvents() async throws {
    MockURLProtocol.handler = { request in
      guard let url = request.url else { throw URLError(.badURL) }
      let pageToken = URLComponents(url: url, resolvingAgainstBaseURL: false)?.queryItems?
        .first(where: { $0.name == "pageToken" })?.value
      if pageToken == nil {
        return jsonResponse([
          "items": [
            [
              "id": "event-1",
              "summary": "First",
              "start": ["dateTime": "2026-08-02T09:00:00Z"],
              "end": ["dateTime": "2026-08-02T09:30:00Z"],
            ]
          ],
          "nextPageToken": "page-2",
        ])
      }
      return jsonResponse([
        "items": [
          [
            "id": "event-2",
            "start": ["dateTime": "2026-08-02T10:00:00Z"],
            "end": ["dateTime": "2026-08-02T10:30:00Z"],
          ]
        ]
      ])
    }
    let events = try await GoogleOAuthCalendarReader.readEvents(
      token: "token", daysBack: 1, daysForward: 1, maxResults: 2, session: mockSession())
    XCTAssertEqual(Set(events.map(\.id)), Set(["event-1", "event-2"]))
    XCTAssertEqual(events.first(where: { $0.id == "event-2" })?.summary, "Untitled")
  }

  func testCalendarParseAllDayEvent() {
    let dict: [String: Any] = [
      "id": "ev-2",
      "summary": "Holiday",
      "start": ["date": "2026-12-25"],
      "end": ["date": "2026-12-26"],
    ]
    let event = GoogleOAuthCalendarReader.parseEvent(dict)
    XCTAssertEqual(event?.isAllDay, true)
    XCTAssertEqual(event?.startTime, "2026-12-25")
  }

  func testGmailRead401SurfacesReconnect() async {
    MockURLProtocol.handler = { _ in
      jsonResponse(["error": "invalid_token"], status: 401)
    }
    do {
      _ = try await GoogleOAuthGmailReader.readRecentEmails(
        token: "dead", session: mockSession())
      XCTFail("expected reconnect")
    } catch let error as GoogleOAuthReaderError {
      XCTAssertEqual(
        error.errorDescription, GoogleOAuthReaderError.reconnectRequired.errorDescription)
    } catch {
      XCTFail("unexpected error \(error)")
    }
  }
}
