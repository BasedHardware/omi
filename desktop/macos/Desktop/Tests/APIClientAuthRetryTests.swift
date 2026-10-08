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

    static func reset() {
      lock.lock()
      deleteAttempts = 0
      alwaysUnauthorized = false
      forcedStatus = nil
      forcedBody = Data()
      successfulStatus = 204
      successfulBody = Data()
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
      Self.lock.lock()
      Self.deleteAttempts += 1
      let attempt = Self.deleteAttempts
      let status = Self.forcedStatus ?? (Self.alwaysUnauthorized || attempt == 1 ? 401 : Self.successfulStatus)
      let body =
        Self.forcedStatus == nil && !Self.alwaysUnauthorized && attempt > 1
        ? Self.successfulBody
        : Self.forcedBody
      Self.lock.unlock()

      guard let url = request.url,
        let response = HTTPURLResponse(
          url: url,
          statusCode: status,
          httpVersion: nil,
          headerFields: nil
        )
      else { return }
      client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
      client?.urlProtocol(self, didLoad: body)
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

  private final class SuspendedConversationAuthURLStub: URLProtocol, @unchecked Sendable {
    private static let lock = NSLock()
    private nonisolated(unsafe) static var requests: [URLRequest] = []
    private nonisolated(unsafe) static var pending: SuspendedConversationAuthURLStub?
    private nonisolated(unsafe) static var waiters: [CheckedContinuation<Void, Never>] = []

    static func reset() {
      lock.withLock {
        requests = []
        pending = nil
        waiters = []
      }
    }

    static var observed: [URLRequest] { lock.withLock { requests } }

    static func waitUntilStarted() async {
      await withCheckedContinuation { continuation in
        let started = lock.withLock {
          if !requests.isEmpty { return true }
          waiters.append(continuation)
          return false
        }
        if started { continuation.resume() }
      }
    }

    static func releaseUnauthorized() {
      let request = lock.withLock { () -> SuspendedConversationAuthURLStub? in
        defer { pending = nil }
        return pending
      }
      request?.respond(status: 401)
    }

    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

    override func startLoading() {
      let (isFirst, ready) = Self.lock.withLock {
        Self.requests.append(request)
        let isFirst = Self.requests.count == 1
        if isFirst { Self.pending = self }
        let ready = Self.waiters
        Self.waiters = []
        return (isFirst, ready)
      }
      for waiter in ready { waiter.resume() }
      if !isFirst { respond(status: 200) }
    }

    override func stopLoading() {}

    private func respond(status: Int) {
      guard let url = request.url,
        let response = HTTPURLResponse(
          url: url, statusCode: status, httpVersion: nil,
          headerFields: ["Content-Type": "application/json"])
      else { return }
      client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
      client?.urlProtocol(self, didLoad: Data(#"{"id":"synthetic-created","status":"completed"}"#.utf8))
      client?.urlProtocolDidFinishLoading(self)
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
      SuspendedConversationAuthURLStub.reset()
    }

    override func tearDown() async throws {
      SuspendedOwnerBoundURLStub.release()
      SuspendedConversationAuthURLStub.releaseUnauthorized()
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

    func testDefaultConversationDeleteCannotRetryUnderTheNextOwnerAfter401() async throws {
      try await assertConversationRequestCannotRebind(upload: false)
    }

    func testDefaultTranscriptUploadCannotRetryUnderTheNextOwnerAfter401() async throws {
      try await assertConversationRequestCannotRebind(upload: true)
    }

    func testConversationMutationsRefreshOnlyTheCapturedOwnersCredential() async throws {
      setenv("FIREBASE_API_KEY", "test-key", 1)
      defer { unsetenv("FIREBASE_API_KEY") }
      try await configureConversationSession(ownerID: "conversation-owner-a")
      let snapshot = try XCTUnwrap(
        RuntimeOwnerIdentity.captureAuthorizationSnapshot(expectedOwnerID: "conversation-owner-a"))
      for upload in [false, true] {
        SuspendedConversationAuthURLStub.reset()
        let client = makeConversationAuthClient()
        let operation = Task {
          if upload {
            _ = try await client.createConversationFromSegments(
              self.syntheticConversationUpload(), expectedOwnerID: "conversation-owner-a",
              authorizationSnapshot: snapshot)
          } else {
            try await client.deleteConversation(
              id: "owner-a-recording", expectedOwnerID: "conversation-owner-a", authorizationSnapshot: snapshot)
          }
        }
        await SuspendedConversationAuthURLStub.waitUntilStarted()
        SuspendedConversationAuthURLStub.releaseUnauthorized()
        try await operation.value
        let observed = SuspendedConversationAuthURLStub.observed
        XCTAssertEqual(observed.count, 2)
        XCTAssertEqual(observed.compactMap(\.httpMethod), [upload ? "POST" : "DELETE", upload ? "POST" : "DELETE"])
        let tokenOwners = observed.compactMap { request in
          request.value(forHTTPHeaderField: "Authorization")
            .flatMap { AuthService.tokenOwnerId(from: String($0.dropFirst("Bearer ".count))) }
        }
        XCTAssertEqual(tokenOwners, ["conversation-owner-a", "conversation-owner-a"])
        if upload { XCTAssertEqual(observed.first?.timeoutInterval, 180) }
      }
    }

    func testConversationMutationsRejectMismatchedOwnerAndSnapshotBeforeTransport() async throws {
      try await configureConversationSession(ownerID: "conversation-owner-a")
      let snapshot = try XCTUnwrap(
        RuntimeOwnerIdentity.captureAuthorizationSnapshot(expectedOwnerID: "conversation-owner-a"))
      let client = makeConversationAuthClient()
      for upload in [false, true] {
        do {
          if upload {
            _ = try await client.createConversationFromSegments(
              syntheticConversationUpload(), expectedOwnerID: "conversation-owner-b", authorizationSnapshot: snapshot)
          } else {
            try await client.deleteConversation(
              id: "owner-a-recording", expectedOwnerID: "conversation-owner-b", authorizationSnapshot: snapshot)
          }
          XCTFail("The explicit owner and immutable snapshot cannot disagree")
        } catch AuthError.userChangedDuringRequest {
          // Rejection occurs before any token lookup or network request.
        }
      }
      XCTAssertTrue(SuspendedConversationAuthURLStub.observed.isEmpty)
    }

    func testConversationMutationsRejectAnExpiredSnapshotBeforeTransport() async throws {
      try await configureConversationSession(ownerID: "conversation-owner-a")
      let snapshot = try XCTUnwrap(
        RuntimeOwnerIdentity.captureAuthorizationSnapshot(expectedOwnerID: "conversation-owner-a"))
      try await configureConversationSession(ownerID: "conversation-owner-b")
      let client = makeConversationAuthClient()
      for upload in [false, true] {
        do {
          if upload {
            _ = try await client.createConversationFromSegments(
              syntheticConversationUpload(), expectedOwnerID: "conversation-owner-a", authorizationSnapshot: snapshot)
          } else {
            try await client.deleteConversation(
              id: "owner-a-recording", expectedOwnerID: "conversation-owner-a", authorizationSnapshot: snapshot)
          }
          XCTFail("Delayed owner A work cannot start under owner B")
        } catch AuthError.userChangedDuringRequest {
          // A caller's captured authority must survive the API wrapper unchanged.
        }
      }
      XCTAssertTrue(SuspendedConversationAuthURLStub.observed.isEmpty)
    }

    func testDefaultConversationMutationSnapshotRejectsSameOwnerSessionReplacementAfter401() async throws {
      for upload in [false, true] {
        SuspendedConversationAuthURLStub.reset()
        try await configureConversationSession(ownerID: "conversation-owner-a")
        let client = makeConversationAuthClient()
        let operation = Task { () -> Result<Void, Error> in
          do {
            if upload {
              _ = try await client.createConversationFromSegments(self.syntheticConversationUpload())
            } else {
              try await client.deleteConversation(id: "owner-a-recording")
            }
            return .success(())
          } catch {
            return .failure(error)
          }
        }
        await SuspendedConversationAuthURLStub.waitUntilStarted()
        await transitionOwnerForAuthTest(to: nil)
        try await configureConversationSession(ownerID: "conversation-owner-a")
        SuspendedConversationAuthURLStub.releaseUnauthorized()
        switch await operation.value {
        case .failure(AuthError.userChangedDuringRequest):
          break
        case .failure(let error):
          XCTFail("Expected rejection of the previous session generation, got \(error)")
        case .success:
          XCTFail("Signing back into the same owner cannot authorize an old conversation request")
        }
        XCTAssertEqual(SuspendedConversationAuthURLStub.observed.count, 1)
      }
    }

    func testHeaderOnlyTranscriptUploadFixtureDoesNotRequireAnAuthenticatedOwner() async throws {
      AuthRetryURLStub.returnStatus(200, body: #"{"id":"fixture-created","status":"completed"}"#)
      let config = URLSessionConfiguration.ephemeral
      config.protocolClasses = [AuthRetryURLStub.self]
      let client = APIClient(session: URLSession(configuration: config))
      await client.setTestAuthHeader("Bearer injected-test-token")

      let created = try await client.createConversationFromSegments(syntheticConversationUpload())

      XCTAssertEqual(created.id, "fixture-created")
      XCTAssertEqual(AuthRetryURLStub.attempts, 1)
    }

    private func makeConversationAuthClient() -> APIClient {
      let config = URLSessionConfiguration.ephemeral
      config.protocolClasses = [SuspendedConversationAuthURLStub.self]
      return APIClient(session: URLSession(configuration: config))
    }

    private func assertConversationRequestCannotRebind(upload: Bool) async throws {
      setenv("FIREBASE_API_KEY", "test-key", 1)
      defer { unsetenv("FIREBASE_API_KEY") }
      try await configureConversationSession(ownerID: "conversation-owner-a")
      let config = URLSessionConfiguration.ephemeral
      config.protocolClasses = [SuspendedConversationAuthURLStub.self]
      let client = APIClient(session: URLSession(configuration: config))
      let operation = Task { () -> Result<Void, Error> in
        do {
          if upload {
            _ = try await client.createConversationFromSegments(self.syntheticConversationUpload())
          } else {
            try await client.deleteConversation(id: "owner-a-recording")
          }
          return .success(())
        } catch {
          return .failure(error)
        }
      }
      await SuspendedConversationAuthURLStub.waitUntilStarted()
      try await configureConversationSession(ownerID: "conversation-owner-b")
      SuspendedConversationAuthURLStub.releaseUnauthorized()

      switch await operation.value {
      case .success:
        XCTFail("Owner A's conversation request must not be retried with owner B's credential")
      case .failure(AuthError.userChangedDuringRequest):
        break
      case .failure(let error):
        XCTFail("Expected an owner-change rejection, got \(error)")
      }
      let observed = SuspendedConversationAuthURLStub.observed
      XCTAssertEqual(observed.count, 1)
      XCTAssertEqual(observed.first?.httpMethod, upload ? "POST" : "DELETE")
      XCTAssertEqual(
        observed.first?.url?.path,
        upload ? "/v1/conversations/from-segments" : "/v1/conversations/owner-a-recording")
      let tokenOwners = observed.compactMap { request in
        request.value(forHTTPHeaderField: "Authorization")
          .flatMap { AuthService.tokenOwnerId(from: String($0.dropFirst("Bearer ".count))) }
      }
      XCTAssertEqual(tokenOwners, ["conversation-owner-a"])
    }

    private func configureConversationSession(ownerID: String) async throws {
      try configureRefreshableSession()
      let token = conversationToken(ownerID: ownerID)
      try AuthService.shared.saveTokens(
        idToken: token, refreshToken: "synthetic-refresh", expiresIn: 3600, userId: ownerID)
      await transitionOwnerForAuthTest(to: ownerID)
      AuthService.shared.tokenRefreshHooks = AuthService.TokenRefreshHooks(
        dataForRequest: { _ in
          let body = try JSONSerialization.data(withJSONObject: [
            "id_token": token,
            "refresh_token": "synthetic-refreshed",
            "expires_in": "3600",
            "user_id": ownerID,
          ])
          let response = try XCTUnwrap(
            HTTPURLResponse(
              url: URL(string: "https://securetoken.googleapis.com/v1/token")!, statusCode: 200,
              httpVersion: nil, headerFields: nil))
          return (body, response)
        })
    }

    private func conversationToken(ownerID: String) -> String {
      let payload = Data("{\"sub\":\"\(ownerID)\"}".utf8).base64EncodedString()
        .replacingOccurrences(of: "+", with: "-")
        .replacingOccurrences(of: "/", with: "_")
        .replacingOccurrences(of: "=", with: "")
      return "e30.\(payload).synthetic"
    }

    private func syntheticConversationUpload() -> APIClient.CreateConversationFromSegmentsRequest {
      .init(
        transcript_segments: [
          .init(
            text: "Owner A synthetic transcript", speaker: "SPEAKER_00", speaker_id: 0,
            is_user: false, person_id: nil, start: 0, end: 1)
        ],
        source: "desktop", started_at: nil, finished_at: nil, language: "en",
        client_conversation_id: "owner-a-client-session", conversation_role: "ambient",
        conversation_finalization_reason: nil, client_processing: nil, captureEvidence: nil)
    }

    func testFeatureVoidRoutesUseShared401Recovery() async throws {
      let config = URLSessionConfiguration.ephemeral
      config.protocolClasses = [AuthRetryURLStub.self]
      let client = APIClient(session: URLSession(configuration: config))
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
          ownerDidChange: {},
          { defaults in
            defaults.removeObject(forKey: .automationOwnerOverride)
            if let ownerID {
              defaults.set(ownerID, forKey: .authUserId)
            } else {
              defaults.removeObject(forKey: .authUserId)
            }
          }
        )
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
