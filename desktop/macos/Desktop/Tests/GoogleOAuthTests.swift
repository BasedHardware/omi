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
  var values: [GoogleOAuthConnection] = []
  func readAll() -> [GoogleOAuthConnection] { values }
  func write(_ connections: [GoogleOAuthConnection]) { values = connections }
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

  func testPkceChallengeIsUnpaddedBase64UrlSha256() {
    let verifier = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-._~"
    let expected = Data(SHA256.hash(data: Data(verifier.utf8)))
      .base64EncodedString()
      .replacingOccurrences(of: "+", with: "-")
      .replacingOccurrences(of: "/", with: "_")
      .replacingOccurrences(of: "=", with: "")
    XCTAssertEqual(PkcePair.challenge(from: verifier), expected)
    let pair = PkcePair.generate()
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

  func testExchangeSendsCodeVerifierAndNamesAccount() async throws {
    MockURLProtocol.handler = { request in
      if request.url?.host?.contains("openidconnect") == true {
        return jsonResponse(["email": "work@corp.com", "name": "Work"])
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
    manager.upsert(connection(accessToken: "access-1", account: "junk@gmail.com"))
    manager.upsert(connection(accessToken: "access-2", account: "work@corp.com"))
    XCTAssertEqual(store.readAll().count, 2)
    manager.upsert(connection(accessToken: "access-3", account: "junk@gmail.com"))
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
