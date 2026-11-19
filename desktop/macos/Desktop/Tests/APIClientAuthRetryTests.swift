import XCTest

@testable import Omi_Computer

#if DEBUG
  // omi-release-compile: this suite drives DEBUG-only test seams; the release-mode
  // notification regression step must compile the bundle without them.

  private final class AuthRetryURLStub: URLProtocol, @unchecked Sendable {
    private static let lock = NSLock()
    private nonisolated(unsafe) static var deleteAttempts = 0
    private nonisolated(unsafe) static var alwaysUnauthorized = false
    private nonisolated(unsafe) static var forcedStatus: Int?
    private nonisolated(unsafe) static var forcedBody = Data()
    private nonisolated(unsafe) static var successfulStatus = 204
    private nonisolated(unsafe) static var successfulBody = Data()
    private nonisolated(unsafe) static var received: URLRequest?
    private nonisolated(unsafe) static var receivedBody: Data?
    private nonisolated(unsafe) static var responseOverride: (@Sendable (URLRequest) -> (Int, Data))?

    static var lastRequest: URLRequest? { lock.withLock { received } }
    static var lastBody: Data? { lock.withLock { receivedBody } }
    static func respond(_ response: @escaping @Sendable (URLRequest) -> (Int, Data)) {
      lock.withLock { responseOverride = response }
    }

    static func reset() {
      lock.lock()
      deleteAttempts = 0
      alwaysUnauthorized = false
      forcedStatus = nil
      forcedBody = Data()
      successfulStatus = 204
      successfulBody = Data()
      received = nil
      receivedBody = nil
      responseOverride = nil
      lock.unlock()
    }

    static func returnUnauthorizedForEveryAttempt(body: String = "") {
      lock.lock()
      alwaysUnauthorized = true
      forcedBody = Data(body.utf8)
      lock.unlock()
    }

    static func returnStatus(_ status: Int, body: String = "") {
      lock.lock()
      forcedStatus = status
      forcedBody = Data(body.utf8)
      lock.unlock()
    }

    static func returnSuccessAfterInitialUnauthorized(status: Int, body: String = "") {
      lock.lock()
      successfulStatus = status
      successfulBody = Data(body.utf8)
      lock.unlock()
    }

    static var attempts: Int {
      lock.lock()
      defer { lock.unlock() }
      return deleteAttempts
    }

    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

    override func startLoading() {
      var requestBody = request.httpBody
      if requestBody == nil, let stream = request.httpBodyStream {
        stream.open()
        defer { stream.close() }
        var data = Data()
        var buffer = [UInt8](repeating: 0, count: 4096)
        while true {
          let count = stream.read(&buffer, maxLength: buffer.count)
          guard count > 0 else { break }
          data.append(buffer, count: count)
        }
        requestBody = data
      }
      Self.lock.lock()
      Self.received = request
      Self.receivedBody = requestBody
      Self.deleteAttempts += 1
      let attempt = Self.deleteAttempts
      let status = Self.forcedStatus ?? (Self.alwaysUnauthorized || attempt == 1 ? 401 : Self.successfulStatus)
      let body =
        Self.forcedStatus == nil && !Self.alwaysUnauthorized && attempt > 1
        ? Self.successfulBody
        : Self.forcedBody
      let override = Self.responseOverride
      Self.lock.unlock()
      let (responseStatus, responseBody) = override?(request) ?? (status, body)

      guard let url = request.url,
        let response = HTTPURLResponse(
          url: url,
          statusCode: responseStatus,
          httpVersion: nil,
          headerFields: nil
        )
      else { return }
      client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
      client?.urlProtocol(self, didLoad: responseBody)
      client?.urlProtocolDidFinishLoading(self)
    }

    override func stopLoading() {}
  }

  private final class SuspendedOwnerBoundURLStub: URLProtocol, @unchecked Sendable {
    private static let lock = NSLock()
    private nonisolated(unsafe) static var pending: SuspendedOwnerBoundURLStub?
    private nonisolated(unsafe) static var started = false

    static func reset() {
      lock.withLock {
        pending = nil
        started = false
      }
    }

    static func waitUntilStarted() async {
      while !lock.withLock({ started }) { await Task.yield() }
    }

    static var hasStarted: Bool { lock.withLock { started } }

    static func release() {
      let request = lock.withLock { () -> SuspendedOwnerBoundURLStub? in
        defer { pending = nil }
        return pending
      }
      request?.respond()
    }

    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

    override func startLoading() {
      Self.lock.withLock {
        Self.pending = self
        Self.started = true
      }
    }

    override func stopLoading() {}

    private func respond() {
      guard let url = request.url,
        let response = HTTPURLResponse(
          url: url,
          statusCode: 200,
          httpVersion: nil,
          headerFields: nil
        )
      else { return }
      client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
      client?.urlProtocol(self, didLoad: Data(#"{"ok":true}"#.utf8))
      client?.urlProtocolDidFinishLoading(self)
    }
  }

  extension APIClient {
    fileprivate func useSyntheticCalendarTestDeviceIdentity() {
      transport.testDeviceIdHash = "20195001"
    }
  }

  @MainActor
  final class APIClientAuthRetryTests: XCTestCase {
    override func setUp() async throws {
      // Prior test bundles may leave the process-wide authorization authority
      // bootstrapped at another owner (or deliberately revoked after a raw
      // mismatch). Establish this test's signed-out baseline through the same
      // completed transition boundary used in production.
      await establishOwnerForAuthTest(nil)
      AuthRetryURLStub.reset()
      DesktopDiagnosticsManager.shared.resetForTests()
      SuspendedOwnerBoundURLStub.reset()
    }

    override func tearDown() async throws {
      SuspendedOwnerBoundURLStub.release()
      DesktopDiagnosticsManager.shared.resetForTests()
      let auth = AuthService.shared
      await auth.invalidateSession(reason: .manual)
      auth.tokenStorageHooks = .live
      auth.tokenRefreshHooks = .live
      await establishOwnerForAuthTest(nil)
    }

    func testDeleteRetriesOnceAfter401() async throws {
      let config = URLSessionConfiguration.ephemeral
      config.protocolClasses = [AuthRetryURLStub.self]
      let client = APIClient(session: URLSession(configuration: config))
      await client.useSyntheticCalendarTestDeviceIdentity()

      try configureRefreshableSession()

      setenv("FIREBASE_API_KEY", "test-key", 1)
      defer { unsetenv("FIREBASE_API_KEY") }

      try await client.delete("v1/test-delete")

      XCTAssertEqual(AuthRetryURLStub.attempts, 2)

      let snapshot = try latestHealthSnapshot()
      XCTAssertEqual(snapshot["event"] as? String, "fallback_triggered")
      XCTAssertEqual(snapshot["area"] as? String, "api_auth")
      XCTAssertEqual(snapshot["outcome"] as? String, "recovered")
      XCTAssertEqual(snapshot["retry_outcome"] as? String, "succeeded")
    }

    func testGoogleCalendarSelectionRoundTripKeepsReadSelectionSeparateFromWrites() async throws {
      try configureRefreshableSession()
      await establishOwnerForAuthTest("user-1")
      let snapshot = try XCTUnwrap(RuntimeOwnerIdentity.captureAuthorizationSnapshot(expectedOwnerID: "user-1"))
      let config = URLSessionConfiguration.ephemeral
      config.protocolClasses = [AuthRetryURLStub.self]
      let client = APIClient(session: URLSession(configuration: config))
      await client.useSyntheticCalendarTestDeviceIdentity()
      await client.setTestAuthHeader("Bearer synthetic-token")
      let body = """
        {"account_id":"personal@example.test","calendars":[
          {"id":"personal@example.test","name":"Personal","primary":true,"available":true},
          {"id":"team","name":"Team","primary":false,"available":true}
        ],"selected_ids":["team"],"write_calendar_id":"primary"}
        """
      AuthRetryURLStub.returnStatus(200, body: body)
      let loaded = try await client.googleCalendarSelection(authorizationSnapshot: snapshot)
      XCTAssertEqual(loaded.selectedIDs, ["team"])
      XCTAssertEqual(AuthRetryURLStub.lastRequest?.httpMethod, "GET")
      XCTAssertEqual(AuthRetryURLStub.lastRequest?.url?.path, "/v1/calendar/google/calendars")
      let saved = try await client.saveGoogleCalendarSelection(
        accountID: loaded.accountID, selectedIDs: ["team"], authorizationSnapshot: snapshot)
      XCTAssertEqual(saved.selectedIDs, ["team"])
      let sent = try XCTUnwrap(AuthRetryURLStub.lastRequest)
      XCTAssertEqual(sent.httpMethod, "PUT")
      let payload = try XCTUnwrap(
        try JSONSerialization.jsonObject(with: XCTUnwrap(AuthRetryURLStub.lastBody)) as? [String: Any])
      XCTAssertEqual(payload["account_id"] as? String, "personal@example.test")
      XCTAssertEqual(payload["selected_ids"] as? [String], ["team"])
      XCTAssertNil(payload["write_calendar_id"])

      let calls = AuthRetryURLStub.attempts
      await transitionOwnerForAuthTest(to: nil)
      await transitionOwnerForAuthTest(to: "user-1")
      do {
        _ = try await client.saveGoogleCalendarSelection(
          accountID: loaded.accountID, selectedIDs: ["team"], authorizationSnapshot: snapshot)
        XCTFail("A previous same-UID session must not save a selection")
      } catch {}
      XCTAssertEqual(AuthRetryURLStub.attempts, calls)
    }

    func testCalendarConnectionURLCannotUseAReplacementSession() async throws {
      try configureRefreshableSession()
      await establishOwnerForAuthTest("user-1")
      let snapshot = try XCTUnwrap(RuntimeOwnerIdentity.captureAuthorizationSnapshot(expectedOwnerID: "user-1"))
      let config = URLSessionConfiguration.ephemeral
      config.protocolClasses = [AuthRetryURLStub.self]
      let client = APIClient(session: URLSession(configuration: config))
      await client.useSyntheticCalendarTestDeviceIdentity()
      await client.setTestAuthHeader("Bearer synthetic-token")
      AuthRetryURLStub.returnStatus(
        200, body: "{\"auth_url\":\"https://accounts.google.com/o/oauth2/auth?state=synthetic\"}")
      let url = try await client.googleCalendarOAuthURL(authorizationSnapshot: snapshot)
      XCTAssertEqual(url.host, "accounts.google.com")
      XCTAssertEqual(AuthRetryURLStub.lastRequest?.url?.path, "/v1/integrations/google_calendar/oauth-url")
      let calls = AuthRetryURLStub.attempts
      await transitionOwnerForAuthTest(to: nil)
      await transitionOwnerForAuthTest(to: "user-1")
      do {
        _ = try await client.googleCalendarOAuthURL(authorizationSnapshot: snapshot)
        XCTFail("An old picker must not start a connection in a replacement session")
      } catch {}
      XCTAssertEqual(AuthRetryURLStub.attempts, calls)
    }

    func testCalendarReaderDoesNotBypassGrantFailuresThroughBrowserCookies() async throws {
      try configureRefreshableSession()
      await establishOwnerForAuthTest("user-1")
      let config = URLSessionConfiguration.ephemeral
      config.protocolClasses = [AuthRetryURLStub.self]
      let client = APIClient(session: URLSession(configuration: config))
      await client.useSyntheticCalendarTestDeviceIdentity()
      await client.setTestAuthHeader("Bearer synthetic-token")
      let reader = CalendarReaderService(calendarAPI: client)

      // Both a failed status lookup and a failed existing-grant event read must
      // stay on the backend boundary. Falling through would enter browser/
      // Keychain discovery and return CalendarReaderError instead.
      for failStatus in [true, false] {
        AuthRetryURLStub.reset()
        AuthRetryURLStub.respond { request in
          if failStatus || request.url?.path == "/v1/calendar/google/events" {
            return (403, Data("{}".utf8))
          }
          return (200, Data("{\"connected\":true}".utf8))
        }
        do {
          _ = try await reader.readEvents(daysBack: 1, daysForward: 1, maxResults: 1)
          XCTFail("A grant failure must propagate")
        } catch { XCTAssertTrue(error is APIError) }
        XCTAssertEqual(AuthRetryURLStub.attempts, failStatus ? 1 : 2)
      }
      AuthRetryURLStub.reset()
      AuthRetryURLStub.returnStatus(200, body: "{\"connected\":false,\"read_selection_configured\":false}")
      let absent = try await reader.readEventsViaGrant(daysBack: 1, daysForward: 1, maxResults: 1)
      XCTAssertNil(absent)
      XCTAssertEqual(AuthRetryURLStub.attempts, 1)

      for configured in [true, nil] as [Bool?] {
        AuthRetryURLStub.reset()
        let field = configured == true ? ",\"read_selection_configured\":true" : ""
        AuthRetryURLStub.returnStatus(200, body: "{\"connected\":false\(field)}")
        do {
          _ = try await reader.readEvents(daysBack: 1, daysForward: 1, maxResults: 1)
          XCTFail("A saved or unverifiable selection must never fall through to browser cookies")
        } catch {
          if configured == true {
            XCTAssertEqual(error as? CalendarReaderError, .savedSelectionNeedsGrant)
          } else {
            XCTAssertTrue(error is APIError)
          }
        }
        XCTAssertEqual(AuthRetryURLStub.attempts, 1)
      }
    }

    func testLegacyCalendarReadCannotPublishAfterSameUIDReauthentication() async throws {
      try configureRefreshableSession()
      await establishOwnerForAuthTest("user-1")
      let config = URLSessionConfiguration.ephemeral
      config.protocolClasses = [AuthRetryURLStub.self]
      let client = APIClient(session: URLSession(configuration: config))
      await client.useSyntheticCalendarTestDeviceIdentity()
      await client.setTestAuthHeader("Bearer synthetic-token")
      AuthRetryURLStub.returnStatus(200, body: "{\"connected\":false,\"read_selection_configured\":false}")
      let started = expectation(description: "Legacy read admitted")
      let release = AsyncStream<Void>.makeStream()
      let reader = CalendarReaderService(
        calendarAPI: client,
        legacyRead: { _, _ in
          started.fulfill()
          var iterator = release.stream.makeAsyncIterator()
          _ = await iterator.next()
          return []
        })
      let operation = Task { try await reader.readEvents() }
      let admitted = await XCTWaiter.fulfillment(of: [started], timeout: 2)
      XCTAssertEqual(admitted, .completed)
      await transitionOwnerForAuthTest(to: nil)
      await transitionOwnerForAuthTest(to: "user-1")
      release.continuation.yield(())
      release.continuation.finish()
      do {
        _ = try await operation.value
        XCTFail("A prior-session legacy read must not be published")
      } catch {
        guard case APIError.unauthorized = error else {
          return XCTFail("Expected owner authorization failure")
        }
      }
    }

    func testFeatureVoidRoutesUseShared401Recovery() async throws {
      let config = URLSessionConfiguration.ephemeral
      config.protocolClasses = [AuthRetryURLStub.self]
      let client = APIClient(session: URLSession(configuration: config))
      await client.useSyntheticCalendarTestDeviceIdentity()
      try configureRefreshableSession()
      setenv("FIREBASE_API_KEY", "test-key", 1)
      defer { unsetenv("FIREBASE_API_KEY") }

      try await client.setConversationVisibility(id: "conversation-1")
      XCTAssertEqual(AuthRetryURLStub.attempts, 2)

      AuthRetryURLStub.reset()
      try await client.assignSegmentsBulk(
        conversationId: "conversation-1",
        segmentIds: ["segment-1"],
        isUser: true,
        personId: nil
      )
      XCTAssertEqual(AuthRetryURLStub.attempts, 2)

      AuthRetryURLStub.reset()
      try await client.setRecordingPermission(enabled: true)
      XCTAssertEqual(AuthRetryURLStub.attempts, 2)

      AuthRetryURLStub.reset()
      try await client.setPrivateCloudSync(enabled: true)
      XCTAssertEqual(AuthRetryURLStub.attempts, 2)
    }

    func testGoalMutationsUseShared401Recovery() async throws {
      let config = URLSessionConfiguration.ephemeral
      config.protocolClasses = [AuthRetryURLStub.self]
      let client = APIClient(session: URLSession(configuration: config))
      await client.useSyntheticCalendarTestDeviceIdentity()
      try configureRefreshableSession()
      setenv("FIREBASE_API_KEY", "test-key", 1)
      defer { unsetenv("FIREBASE_API_KEY") }
      AuthRetryURLStub.returnSuccessAfterInitialUnauthorized(status: 200, body: "{}")

      _ = try await client.updateGoalProgress(goalId: "goal-1", currentValue: 2)
      XCTAssertEqual(AuthRetryURLStub.attempts, 2)

      AuthRetryURLStub.reset()
      AuthRetryURLStub.returnSuccessAfterInitialUnauthorized(status: 200, body: "{}")
      _ = try await client.completeGoal(id: "goal-1")
      XCTAssertEqual(AuthRetryURLStub.attempts, 2)
    }

    func testOwnerBoundResponseIsRejectedAfterSameUIDSessionGenerationChanges() async throws {
      struct Response: Decodable { let ok: Bool }
      let auth = AuthService.shared
      auth.tokenStorageHooks = AuthService.TokenStorageHooks(
        usesKeychainTokenStorage: { false },
        allowsUserDefaultsFallback: { true },
        readKeychainString: { _, _ in nil },
        writeKeychainString: { _, _, _ in true },
        deleteKeychainString: { _, _ in },
        recordsFallbackTelemetry: false
      )
      try auth.saveTokens(
        idToken: "id-token",
        refreshToken: "refresh-token",
        expiresIn: 3600,
        userId: "same-owner"
      )
      await transitionOwnerForAuthTest(to: "same-owner")
      let snapshot = try XCTUnwrap(
        RuntimeOwnerIdentity.captureAuthorizationSnapshot(expectedOwnerID: "same-owner"))

      let config = URLSessionConfiguration.ephemeral
      config.protocolClasses = [SuspendedOwnerBoundURLStub.self]
      let client = APIClient(session: URLSession(configuration: config))
      await client.useSyntheticCalendarTestDeviceIdentity()
      await client.setTestAuthHeader("Bearer id-token")
      let request = Task { () -> Result<Response, Error> in
        do {
          return .success(
            try await client.get(
              "v1/owner-bound",
              expectedOwnerId: "same-owner",
              authorizationSnapshot: snapshot
            ))
        } catch {
          return .failure(error)
        }
      }
      await SuspendedOwnerBoundURLStub.waitUntilStarted()
      await transitionOwnerForAuthTest(to: nil)
      await transitionOwnerForAuthTest(to: "same-owner")
      SuspendedOwnerBoundURLStub.release()

      switch await request.value {
      case .success:
        XCTFail("A response from the prior same-UID session must not decode")
      case .failure(let error):
        guard let authError = error as? AuthError else {
          return XCTFail("Expected same-UID generation rejection, got \(error)")
        }
        guard case .userChangedDuringRequest = authError else {
          return XCTFail("Expected same-UID generation rejection, got \(authError)")
        }
      }
    }

    func testSnapshotOwnerDrivesHeaderAuthAndRejectsMismatchedFirebaseCredentialBeforeSend() async throws {
      struct Response: Decodable { let ok: Bool }
      let auth = AuthService.shared
      auth.tokenStorageHooks = AuthService.TokenStorageHooks(
        usesKeychainTokenStorage: { false },
        allowsUserDefaultsFallback: { true },
        readKeychainString: { _, _ in nil },
        writeKeychainString: { _, _, _ in true },
        deleteKeychainString: { _, _ in },
        recordsFallbackTelemetry: false
      )
      try auth.saveTokens(
        idToken: "owner-a-token",
        refreshToken: "refresh-token",
        expiresIn: 3600,
        userId: "owner-a"
      )
      await transitionOwnerForAuthTest(to: "owner-b")
      let snapshot = try XCTUnwrap(
        RuntimeOwnerIdentity.captureAuthorizationSnapshot(expectedOwnerID: "owner-b"))

      let config = URLSessionConfiguration.ephemeral
      config.protocolClasses = [SuspendedOwnerBoundURLStub.self]
      let client = APIClient(session: URLSession(configuration: config))
      await client.useSyntheticCalendarTestDeviceIdentity()
      do {
        let _: Response = try await client.get(
          "v1/mismatched-owner",
          expectedOwnerId: "owner-b",
          authorizationSnapshot: snapshot
        )
        XCTFail("Snapshot owner B must not send owner A's Firebase credential")
      } catch AuthError.notSignedIn {
        // Expected: AuthService rejects and clears owner A's credential while
        // constructing an owner B header, before transport can start.
      } catch {
        XCTFail("Unexpected error: \(error)")
      }
      XCTAssertFalse(SuspendedOwnerBoundURLStub.hasStarted)
    }

    func testExplicitExpectedOwnerCannotDisagreeWithAuthorizationSnapshot() async throws {
      struct Response: Decodable { let ok: Bool }
      let auth = AuthService.shared
      auth.tokenStorageHooks = AuthService.TokenStorageHooks(
        usesKeychainTokenStorage: { false },
        allowsUserDefaultsFallback: { true },
        readKeychainString: { _, _ in nil },
        writeKeychainString: { _, _, _ in true },
        deleteKeychainString: { _, _ in },
        recordsFallbackTelemetry: false
      )
      try auth.saveTokens(
        idToken: "owner-b-token",
        refreshToken: "refresh-token",
        expiresIn: 3600,
        userId: "owner-b"
      )
      await transitionOwnerForAuthTest(to: "owner-b")
      let snapshot = try XCTUnwrap(
        RuntimeOwnerIdentity.captureAuthorizationSnapshot(expectedOwnerID: "owner-b"))

      let config = URLSessionConfiguration.ephemeral
      config.protocolClasses = [SuspendedOwnerBoundURLStub.self]
      let client = APIClient(session: URLSession(configuration: config))
      await client.useSyntheticCalendarTestDeviceIdentity()
      do {
        let _: Response = try await client.get(
          "v1/preflight-owner-mismatch",
          expectedOwnerId: "owner-a",
          authorizationSnapshot: snapshot
        )
        XCTFail("Mismatched dual owner authority must fail before token lookup or network I/O")
      } catch AuthError.userChangedDuringRequest {
        // Expected from the shared request-policy preflight.
      } catch {
        XCTFail("Unexpected error: \(error)")
      }
      XCTAssertFalse(SuspendedOwnerBoundURLStub.hasStarted)
    }

    private func transitionOwnerForAuthTest(to ownerID: String?) async {
      do {
        _ = try await RuntimeOwnerIdentity.performEffectiveOwnerTransition(
          plannedNextOwner: { _, _ in ownerID },
          quiesceVoice: { _, _ in },
          retargetLocalStorage: { _, _ in },
          ownerDidChange: {}
        ) { defaults in
          defaults.removeObject(forKey: .automationOwnerOverride)
          if let ownerID {
            defaults.set(ownerID, forKey: .authUserId)
          } else {
            defaults.removeObject(forKey: .authUserId)
          }
        }
      } catch {
        XCTFail("owner transition failed: \(error)")
      }
    }

    /// Cross a real owner boundary even when persisted defaults already equal the
    /// requested baseline. This repairs a deliberately revoked process-wide
    /// authority left by any preceding out-of-band mismatch test.
    private func establishOwnerForAuthTest(_ ownerID: String?) async {
      let bootstrapOwner = "api-client-auth-retry-bootstrap"
      if ownerID == bootstrapOwner {
        await transitionOwnerForAuthTest(to: nil)
      } else {
        await transitionOwnerForAuthTest(to: bootstrapOwner)
      }
      await transitionOwnerForAuthTest(to: ownerID)
    }

    func testTTSProvider401RetriesWithoutInvalidatingFirebaseSession() async throws {
      AuthRetryURLStub.returnUnauthorizedForEveryAttempt(
        body: "{\"error\":\"OpenAI TTS request failed: Incorrect API key provided\"}"
      )
      setenv("OMI_DESKTOP_API_URL", "http://rust-test:9002", 1)
      setenv("FIREBASE_API_KEY", "test-key", 1)
      defer {
        unsetenv("OMI_DESKTOP_API_URL")
        unsetenv("FIREBASE_API_KEY")
      }

      let config = URLSessionConfiguration.ephemeral
      config.protocolClasses = [AuthRetryURLStub.self]
      let client = APIClient(session: URLSession(configuration: config))
      await client.useSyntheticCalendarTestDeviceIdentity()

      let auth = AuthService.shared
      auth.tokenStorageHooks = AuthService.TokenStorageHooks(
        usesKeychainTokenStorage: { false },
        allowsUserDefaultsFallback: { true },
        readKeychainString: { _, _ in nil },
        writeKeychainString: { _, _, _ in true },
        deleteKeychainString: { _, _ in },
        recordsFallbackTelemetry: false
      )
      try auth.saveTokens(
        idToken: "id-token",
        refreshToken: "refresh-token",
        expiresIn: 3600,
        userId: "user-1"
      )
      UserDefaults.standard.set("user-1", forKey: .authUserId)
      auth.tokenRefreshHooks = AuthService.TokenRefreshHooks(
        dataForRequest: { _ in
          let body = Data(
            "{\"id_token\":\"new-id\",\"refresh_token\":\"new-refresh\",\"expires_in\":\"3600\",\"user_id\":\"user-1\"}"
              .utf8)
          let response = try XCTUnwrap(
            HTTPURLResponse(
              url: URL(string: "https://securetoken.googleapis.com/v1/token")!,
              statusCode: 200,
              httpVersion: nil,
              headerFields: nil
            ))
          return (body, response)
        }
      )

      do {
        _ = try await client.synthesizeSpeech(
          request: APIClient.TtsSynthesizeRequest(
            text: "Hello",
            voiceId: "onyx",
            instructions: nil
          )
        )
        XCTFail("Expected provider authorization failure")
      } catch let error as CredentialHealthError {
        XCTAssertEqual(
          error.failureClass,
          .providerAuthFailed(provider: .openai, mode: .managed)
        )
      }

      XCTAssertEqual(AuthRetryURLStub.attempts, 2)
      XCTAssertEqual(UserDefaults.standard.string(forKey: .authUserId), "user-1")
      let retainedToken = try await auth.getIdToken()
      XCTAssertEqual(retainedToken, "new-id")
      XCTAssertFalse(try healthSnapshots().contains { $0["area"] as? String == "api_auth" })
    }

    func testTTSBare401DoesNotRemapToProviderAuth() async throws {
      AuthRetryURLStub.returnUnauthorizedForEveryAttempt(body: "{\"error\":\"Unauthorized\"}")
      setenv("OMI_DESKTOP_API_URL", "http://rust-test:9002", 1)
      setenv("FIREBASE_API_KEY", "test-key", 1)
      defer {
        unsetenv("OMI_DESKTOP_API_URL")
        unsetenv("FIREBASE_API_KEY")
      }

      let config = URLSessionConfiguration.ephemeral
      config.protocolClasses = [AuthRetryURLStub.self]
      let client = APIClient(session: URLSession(configuration: config))
      await client.useSyntheticCalendarTestDeviceIdentity()

      let auth = AuthService.shared
      auth.tokenStorageHooks = AuthService.TokenStorageHooks(
        usesKeychainTokenStorage: { false },
        allowsUserDefaultsFallback: { true },
        readKeychainString: { _, _ in nil },
        writeKeychainString: { _, _, _ in true },
        deleteKeychainString: { _, _ in },
        recordsFallbackTelemetry: false
      )
      try auth.saveTokens(
        idToken: "id-token",
        refreshToken: "refresh-token",
        expiresIn: 3600,
        userId: "user-1"
      )
      UserDefaults.standard.set("user-1", forKey: .authUserId)
      auth.tokenRefreshHooks = AuthService.TokenRefreshHooks(
        dataForRequest: { _ in
          let body = Data(
            "{\"id_token\":\"new-id\",\"refresh_token\":\"new-refresh\",\"expires_in\":\"3600\",\"user_id\":\"user-1\"}"
              .utf8)
          let response = try XCTUnwrap(
            HTTPURLResponse(
              url: URL(string: "https://securetoken.googleapis.com/v1/token")!,
              statusCode: 200,
              httpVersion: nil,
              headerFields: nil
            ))
          return (body, response)
        }
      )

      do {
        _ = try await client.synthesizeSpeech(
          request: APIClient.TtsSynthesizeRequest(
            text: "Hello",
            voiceId: "onyx",
            instructions: nil
          )
        )
        XCTFail("Expected unauthorized failure")
      } catch APIError.unauthorized {
        // Bare/Firebase-shaped 401 must not become providerAuth (BYOK poison).
      } catch {
        XCTFail("Unexpected error: \(error)")
      }

      XCTAssertEqual(AuthRetryURLStub.attempts, 2)
      // Light invalidation intentionally preserves the owner so Claude/chat
      // sessions can rehydrate after re-auth (#13859). The credential, not the
      // owner identity, is what a persistent backend 401 must revoke.
      XCTAssertEqual(UserDefaults.standard.string(forKey: .authUserId), "user-1")
      XCTAssertNil(UserDefaults.standard.string(forKey: .authIdToken))
      XCTAssertEqual(AuthState.shared.sessionPhase, .needsReauth)
    }

    func testTTSProvider429ReturnsTypedQuotaFailure() async throws {
      AuthRetryURLStub.returnStatus(
        429,
        body: "{\"error\":\"OpenAI TTS request failed: upstream quota exhausted\"}"
      )
      setenv("OMI_DESKTOP_API_URL", "http://rust-test:9002", 1)
      defer { unsetenv("OMI_DESKTOP_API_URL") }

      let config = URLSessionConfiguration.ephemeral
      config.protocolClasses = [AuthRetryURLStub.self]
      let client = APIClient(session: URLSession(configuration: config))
      await client.useSyntheticCalendarTestDeviceIdentity()
      await client.setTestAuthHeader("Bearer test-token")

      do {
        _ = try await client.synthesizeSpeech(
          request: APIClient.TtsSynthesizeRequest(text: "Hello", voiceId: "onyx", instructions: nil)
        )
        XCTFail("Expected provider quota failure")
      } catch let error as CredentialHealthError {
        XCTAssertEqual(error.failureClass, .providerQuotaExceeded(provider: .openai))
      }

      XCTAssertEqual(AuthRetryURLStub.attempts, 1)
    }

    func testTTSLocal429RemainsBackendRateLimitFailure() async throws {
      AuthRetryURLStub.returnStatus(429, body: "{\"error\":\"TTS burst rate limit exceeded\"}")
      setenv("OMI_DESKTOP_API_URL", "http://rust-test:9002", 1)
      defer { unsetenv("OMI_DESKTOP_API_URL") }

      let config = URLSessionConfiguration.ephemeral
      config.protocolClasses = [AuthRetryURLStub.self]
      let client = APIClient(session: URLSession(configuration: config))
      await client.useSyntheticCalendarTestDeviceIdentity()
      await client.setTestAuthHeader("Bearer test-token")

      do {
        _ = try await client.synthesizeSpeech(
          request: APIClient.TtsSynthesizeRequest(text: "Hello", voiceId: "onyx", instructions: nil)
        )
        XCTFail("Expected local rate-limit failure")
      } catch APIError.httpError(let statusCode, let detail) {
        XCTAssertEqual(statusCode, 429)
        XCTAssertEqual(detail, "TTS burst rate limit exceeded")
      }

      XCTAssertEqual(AuthRetryURLStub.attempts, 1)
    }

    func testTTSStreamDeliversSuccessfulBodyChunks() async throws {
      AuthRetryURLStub.returnStatus(200, body: "streamed-audio")
      setenv("OMI_DESKTOP_API_URL", "http://rust-test:9002", 1)
      defer { unsetenv("OMI_DESKTOP_API_URL") }

      let config = URLSessionConfiguration.ephemeral
      config.protocolClasses = [AuthRetryURLStub.self]
      let client = APIClient(session: URLSession(configuration: config))
      await client.useSyntheticCalendarTestDeviceIdentity()
      await client.setTestAuthHeader("Bearer test-token")

      let stream = try await client.synthesizeSpeechStream(
        request: APIClient.TtsSynthesizeRequest(text: "Hello", voiceId: "onyx", instructions: nil)
      )
      var received = Data()
      for try await chunk in stream {
        received.append(chunk)
      }

      XCTAssertEqual(received, Data("streamed-audio".utf8))
      XCTAssertEqual(AuthRetryURLStub.attempts, 1)
    }

    private func configureRefreshableSession() throws {
      let auth = AuthService.shared
      auth.tokenStorageHooks = AuthService.TokenStorageHooks(
        usesKeychainTokenStorage: { false },
        allowsUserDefaultsFallback: { true },
        readKeychainString: { _, _ in nil },
        writeKeychainString: { _, _, _ in true },
        deleteKeychainString: { _, _ in },
        recordsFallbackTelemetry: false
      )
      try auth.saveTokens(
        idToken: "id-token",
        refreshToken: "refresh-token",
        expiresIn: 3600,
        userId: "user-1"
      )
      UserDefaults.standard.set("user-1", forKey: .authUserId)
      auth.tokenRefreshHooks = AuthService.TokenRefreshHooks(
        dataForRequest: { _ in
          let body = Data(
            "{\"id_token\":\"new-id\",\"refresh_token\":\"new-refresh\",\"expires_in\":\"3600\",\"user_id\":\"user-1\"}"
              .utf8)
          let response = try XCTUnwrap(
            HTTPURLResponse(
              url: URL(string: "https://securetoken.googleapis.com/v1/token")!,
              statusCode: 200,
              httpVersion: nil,
              headerFields: nil
            ))
          return (body, response)
        }
      )
    }

    private func latestHealthSnapshot() throws -> [String: Any] {
      try XCTUnwrap(healthSnapshots().last)
    }

    private func healthSnapshots() throws -> [[String: Any]] {
      let url = try XCTUnwrap(DesktopDiagnosticsManager.shared.writeDiagnosticsAttachment())
      defer { try? FileManager.default.removeItem(at: url) }
      let data = try Data(contentsOf: url)
      let root = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
      return try XCTUnwrap(root["snapshots"] as? [[String: Any]])
    }
  }
#endif
