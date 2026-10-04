#if !SKIP && canImport(Security)
  import Foundation
  import XCTest
  @testable import OmiKit

  /// Auth and the already-running transport share synthetic plane/credential stores.
  /// Every HTTP request is intercepted; production UserDefaults/Keychain are unused.
  final class HTTPSoftwarePlaneTests: XCTestCase {
    private func session() -> URLSession {
      let config = URLSessionConfiguration.ephemeral
      config.protocolClasses = [PlaneURLProtocol.self]
      return URLSession(configuration: config)
    }

    private func transport(
      _ session: URLSession, _ credentials: PlaneFixtureCredentials,
      _ planes: PlaneFixtureStore, locked: Bool = false,
      bearerResolver: (@Sendable () async -> String?)? = nil
    ) -> HTTPBackendTransport {
      HTTPBackendTransport(
        session: session, credentials: credentials,
        planeSelection: .init(storedPlane: "old", stampedValid: true, allowPlaneSwitch: !locked),
        originOverride: "https://plane.example.test", bearerResolver: bearerResolver,
        planeStore: planes)
    }

    func testSuccessfulLoginPinUpdatesExistingTransportAndRequestOrigin() async throws {
      let session = session()
      defer { session.invalidateAndCancel() }
      let credentials = PlaneFixtureCredentials()
      let planes = PlaneFixtureStore("old")
      let backend = transport(session, credentials, planes)
      let auth = OmiAuthSession(
        config: .init(firebaseApiKey: "synthetic"), credentials: credentials,
        urlSession: session, planeStore: planes)
      for (plane, expectedHost, expectedContract) in [
        ("new", "plane.example.test", APIContract.canonical),
        ("old", "api.omi.me", APIContract.omi),
      ] {
        PlaneURLProtocol.handle = { request in
          XCTAssertEqual(request.url?.host, "identitytoolkit.googleapis.com")
          return (
            200,
            "{\"idToken\":\"synthetic-token\",\"refreshToken\":\"synthetic-refresh\",\"localId\":\"A\"}"
          )
        }
        let signedIn = await auth.redeemCustomToken("synthetic-custom", pinPlane: plane)
        XCTAssertTrue(signedIn)
        let contract = await backend.apiContract()
        XCTAssertEqual(contract, expectedContract)
        XCTAssertEqual(planes.storedSoftwarePlane(), plane)
        PlaneURLProtocol.handle = { request in
          XCTAssertEqual(request.url?.host, expectedHost)
          XCTAssertEqual(
            request.value(forHTTPHeaderField: "authorization"), "Bearer synthetic-token")
          return (200, "{}")
        }
        _ = try await backend.request(
          BackendRequest(
            expectedApiContract: expectedContract,
            method: .GET, path: "/v1/tasks"))
      }
    }

    func testFirstDirectStreamAfterLoginPinUsesNewPlane() async throws {
      let session = session()
      defer { session.invalidateAndCancel() }
      let credentials = PlaneFixtureCredentials()
      let planes = PlaneFixtureStore("old")
      let backend = transport(session, credentials, planes, bearerResolver: { "synthetic" })
      let terminal =
        "id: event-1\nevent: cancelled\ndata: {\"kind\":\"cancelled\",\"message\":null}\n\n"
      PlaneURLProtocol.handle = { request in
        XCTAssertEqual(request.url?.host, "plane.example.test")
        return (200, terminal)
      }
      planes.storeSoftwarePlane(.new)
      // No apiContract()/request() call in between to refresh transport state.
      let response = try await backend.generationEvents(generationId: "after-pin", lastEventId: nil)
      { frame in
        XCTAssertEqual(frame, terminal)
      }
      XCTAssertEqual(response.status, 200)
      XCTAssertEqual(response.body, terminal)
    }

    func testFailedRedemptionAndSecureWriteNeverPinPlane() async throws {
      let session = session()
      defer { session.invalidateAndCancel() }
      let credentials = PlaneFixtureCredentials()
      let planes = PlaneFixtureStore("old")
      let backend = transport(session, credentials, planes)
      let auth = OmiAuthSession(
        config: .init(firebaseApiKey: "synthetic"), credentials: credentials,
        urlSession: session, planeStore: planes)
      PlaneURLProtocol.handle = { _ in (401, "{}") }
      let denied = await auth.redeemCustomToken("synthetic", pinPlane: "new")
      XCTAssertFalse(denied)
      credentials.failWrites = true
      PlaneURLProtocol.handle = { _ in
        (200, "{\"idToken\":\"synthetic\",\"refreshToken\":\"synthetic\",\"localId\":\"A\"}")
      }
      let unsaved = await auth.redeemCustomToken("synthetic", pinPlane: "new")
      XCTAssertFalse(unsaved)
      XCTAssertEqual(planes.storedSoftwarePlane(), "old")
      let contract = await backend.apiContract()
      XCTAssertEqual(contract, .omi)
      XCTAssertNil(try credentials.secureSnapshot().session)
    }

    func testRetiredRedemptionCannotPinPlane() async throws {
      let session = session()
      defer { session.invalidateAndCancel() }
      let credentials = PlaneFixtureCredentials()
      let planes = PlaneFixtureStore("old")
      let auth = OmiAuthSession(
        config: .init(firebaseApiKey: "synthetic"), credentials: credentials,
        urlSession: session, planeStore: planes)
      PlaneURLProtocol.handle = { _ in
        try credentials.clearSecureSession()
        return (200, "{\"idToken\":\"late\",\"refreshToken\":\"late\"}")
      }
      let signedIn = await auth.redeemCustomToken("synthetic", pinPlane: "new")
      XCTAssertFalse(signedIn)
      XCTAssertEqual(planes.storedSoftwarePlane(), "old")
    }

    func testPlaneChangeDuringBearerResolutionRejectsStaleOriginRequest() async throws {
      let session = session()
      defer { session.invalidateAndCancel() }
      let credentials = PlaneFixtureCredentials()
      let planes = PlaneFixtureStore("old")
      let backend = transport(
        session, credentials, planes,
        bearerResolver: {
          planes.storeSoftwarePlane(.new)
          return "synthetic"
        })
      PlaneURLProtocol.handle = { _ in
        XCTFail("Stale-origin request must not dispatch")
        return (200, "{}")
      }
      do {
        _ = try await backend.request(BackendRequest(method: .GET, path: "/v1/tasks"))
        XCTFail("Expected stale plane rejection")
      } catch { XCTAssertEqual(error as? TransportFailure, .unconfigured) }
      let plane = await backend.softwarePlane()
      XCTAssertEqual(plane, .new)
    }

    func testSamePlanePublicationAndABAChangeRetirePendingRequests() async throws {
      for selections in [[SoftwarePlane.old], [.new, .old]] {
        let session = session()
        defer { session.invalidateAndCancel() }
        let credentials = PlaneFixtureCredentials()
        let planes = PlaneFixtureStore("old")
        let backend = transport(
          session, credentials, planes,
          bearerResolver: {
            for selection in selections { planes.storeSoftwarePlane(selection) }
            return "new-login-token"
          })
        PlaneURLProtocol.handle = { _ in
          XCTFail("Retired snapshot must not dispatch even when plane text matches")
          return (200, "{}")
        }
        do {
          _ = try await backend.request(BackendRequest(method: .GET, path: "/v1/tasks"))
          XCTFail("Expected retired snapshot rejection")
        } catch { XCTAssertEqual(error as? TransportFailure, .unconfigured) }
      }
    }

    func testOldPlane401DoesNotInvalidateNewLogin() async throws {
      let session = session()
      defer { session.invalidateAndCancel() }
      let credentials = PlaneFixtureCredentials()
      let planes = PlaneFixtureStore("old")
      let backend = transport(session, credentials, planes, bearerResolver: { "synthetic" })
      let invalidated = expectation(description: "new login must remain valid")
      invalidated.isInverted = true
      let invalidations = await backend.sessionInvalidated
      let observer = Task {
        for await _ in invalidations { invalidated.fulfill() }
      }
      defer { observer.cancel() }
      PlaneURLProtocol.handle = { _ in
        planes.storeSoftwarePlane(.new)
        return (401, "{}")
      }
      do {
        _ = try await backend.request(BackendRequest(method: .GET, path: "/v1/tasks"))
        XCTFail("Expected stale response rejection")
      } catch { XCTAssertEqual(error as? TransportFailure, .unconfigured) }
      await fulfillment(of: [invalidated], timeout: 0.1)
    }

    func testManualSelectionPersistsButLockedSelectorCannotChangeIt() async throws {
      let session = session()
      defer { session.invalidateAndCancel() }
      let credentials = PlaneFixtureCredentials()
      let planes = PlaneFixtureStore("old")
      let backend = transport(session, credentials, planes)
      let selected = await backend.setSoftwarePlane(.new)
      XCTAssertEqual(selected, .new)
      XCTAssertEqual(planes.storedSoftwarePlane(), "new")
      let locked = transport(session, credentials, planes, locked: true)
      let rejected = await locked.setSoftwarePlane(.old)
      XCTAssertEqual(rejected, .new)
      XCTAssertEqual(planes.storedSoftwarePlane(), "new")
    }
  }

  private final class PlaneFixtureStore: SoftwarePlaneStoring, @unchecked Sendable {
    private let lock = NSLock()
    private var value: String?
    init(_ value: String?) { self.value = value }
    private var revision = UUID().uuidString
    func softwarePlaneSnapshot() -> SoftwarePlaneSnapshot {
      lock.withLock { SoftwarePlaneSnapshot(storedPlane: value, revision: revision) }
    }
    func storeSoftwarePlane(_ plane: SoftwarePlane) {
      lock.withLock {
        value = plane.rawValue
        revision = UUID().uuidString
      }
    }
    func commitSoftwarePlane(_ plane: SoftwarePlane, persistSession: () throws -> Void) throws {
      try lock.withLock {
        defer { revision = UUID().uuidString }
        try persistSession()
        value = plane.rawValue
      }
    }
  }

  private final class PlaneFixtureCredentials: SecureSessionCredentialStoring, @unchecked Sendable {
    private let lock = NSLock()
    private var value: StoredSession?
    private var revision = UUID().uuidString
    var failWrites = false
    func secureSnapshot() throws -> SecureSessionSnapshot {
      lock.withLock { SecureSessionSnapshot(revision: revision, session: value) }
    }
    func replaceSession(_ session: StoredSession?, expecting expected: String) throws {
      try lock.withLock {
        guard expected == revision else { throw SecureSessionError.changed }
        guard !failWrites else { throw SecureSessionError.unavailable }
        value = session
        revision = UUID().uuidString
      }
    }
    func clearSecureSession() throws {
      lock.withLock {
        value = nil
        revision = UUID().uuidString
      }
    }
    func load() async -> StoredSession? { try? secureSnapshot().session }
    func store(_ session: StoredSession) async {
      try? replaceSession(session, expecting: secureSnapshot().revision)
    }
    func clear() async { try? clearSecureSession() }
  }

  private final class PlaneURLProtocol: URLProtocol, @unchecked Sendable {
    nonisolated(unsafe) static var handle: (@Sendable (URLRequest) throws -> (Int, String))?
    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
      do {
        let (status, body) = try Self.handle!(request)
        client?.urlProtocol(
          self,
          didReceive: HTTPURLResponse(
            url: request.url!, statusCode: status,
            httpVersion: "HTTP/1.1", headerFields: nil)!, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: Data(body.utf8))
        client?.urlProtocolDidFinishLoading(self)
      } catch { client?.urlProtocol(self, didFailWithError: error) }
    }
    override func stopLoading() {}
  }
#endif
