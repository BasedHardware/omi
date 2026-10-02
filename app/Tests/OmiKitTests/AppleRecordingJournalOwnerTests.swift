#if !SKIP && canImport(Security)
import Foundation
import XCTest
@testable import OmiKit

/// No production Keychain object is created by this suite. URLProtocol prevents
/// all requests (including Firebase refresh/redemption) from reaching a server.
final class AppleRecordingJournalOwnerTests: XCTestCase {
    private let origin = "https://api.example.test"
    private let key = String(repeating: "a", count: 64)
    private var receipt: String { "capture1.\(key).\(String(repeating: "b", count: 64))" }
    private var payload: String {
        "{\"ownership\":{\"ownerKey\":\"capture-owner-v1:\(key)\",\"receipt\":\"\(receipt)\"}}"
    }
    private func login(_ uid: String = "A") -> StoredSession {
        StoredSession(idToken: "synthetic-\(uid)", refreshToken: "synthetic-refresh",
            expiresAtMs: Int64(Date().timeIntervalSince1970 * 1000) + 3_600_000,
            uid: uid, firebaseApiKey: "synthetic", loginGeneration: UUID().uuidString.lowercased())
    }
    private func setup(_ store: MockSecureSessionStore) -> (HTTPBackendTransport, URLSession) {
        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [OwnerURLProtocol.self]
        let session = URLSession(configuration: config)
        return (HTTPBackendTransport(session: session, credentials: store,
            planeSelection: .init(storedPlane: "new", stampedValid: true), originOverride: origin), session)
    }
    private func fails(_ operation: () async throws -> Void) async -> Error? {
        do { try await operation(); XCTFail("Expected failure"); return nil } catch { return error }
    }
    func testOwnershipPersistedAndRequestUsesReceiptBearerAndHeaders() async throws {
        let store = MockSecureSessionStore(login())
        let (backend, session) = setup(store)
        defer { session.invalidateAndCancel() }
        OwnerURLProtocol.handle = { [payload] request in
            XCTAssertEqual(request.value(forHTTPHeaderField: "authorization"), "Bearer synthetic-A")
            return (200, payload)
        }
        let resolved = try await AppleRecordingJournalOwnerProvider(transport: backend)
            .freshRecordingJournalOwner()
        let owner = try XCTUnwrap(resolved)
        XCTAssertEqual(try store.secureSnapshot().session?.recordingOwner?.receipt, receipt)
        OwnerURLProtocol.handle = { [receipt] request in
            XCTAssertEqual(request.url?.host, "api.example.test")
            XCTAssertEqual(request.value(forHTTPHeaderField: "x-omi-capture-ownership"), receipt)
            XCTAssertEqual(request.value(forHTTPHeaderField: "authorization"), "Bearer synthetic-A")
            XCTAssertEqual(request.value(forHTTPHeaderField: "idempotency-key"), "synthetic-write")
            return (200, "{}")
        }
        _ = try await backend.requestRecordingJournal(BackendRequest(method: .POST,
            path: "/v1/device-sessions", headers: ["authorization": "bad",
                "x-omi-capture-ownership": "bad", "idempotency-key": "synthetic-write"]), owner: owner)
    }
    func testWorkerDenialNeverUsesCacheAndOnlyConnectivityPermitsLocalCache() async throws {
        let store = MockSecureSessionStore(login())
        let (backend, session) = setup(store); defer { session.invalidateAndCancel() }
        let provider = AppleRecordingJournalOwnerProvider(transport: backend)
        OwnerURLProtocol.handle = { [payload] _ in (200, payload) }
        let owner = try await provider.currentRecordingJournalOwner()
        OwnerURLProtocol.handle = { _ in (503, "{\"error\":{\"code\":\"capture_ownership_unavailable\"}}") }
        let denied = await fails { _ = try await provider.currentRecordingJournalOwner() }
        XCTAssertEqual((denied as? ChatBackendError)?.backendCode, "capture_ownership_unavailable")
        for code in [URLError.timedOut, .cannotFindHost, .notConnectedToInternet] {
            OwnerURLProtocol.handle = { _ in throw URLError(code) }
            let cached = try await provider.currentRecordingJournalOwner()
            XCTAssertEqual(cached, owner)
            _ = await fails { _ = try await provider.freshRecordingJournalOwner() }
        }
        for code in [URLError.secureConnectionFailed, .cancelled] {
            OwnerURLProtocol.handle = { _ in throw URLError(code) }
            _ = await fails { _ = try await provider.currentRecordingJournalOwner() }
        }
    }
    func testLogoutDuringOwnerResponseCannotPublishAndNextLoginWorks() async throws {
        let store = MockSecureSessionStore(login())
        let (backend, session) = setup(store); defer { session.invalidateAndCancel() }
        let provider = AppleRecordingJournalOwnerProvider(transport: backend)
        OwnerURLProtocol.handle = { [payload] _ in
            try store.clearSecureSession()
            return (200, payload)
        }
        _ = await fails { _ = try await provider.currentRecordingJournalOwner() }
        XCTAssertNil(try store.secureSnapshot().session)
        try store.replaceSession(login("B"), expecting: store.secureSnapshot().revision)
        OwnerURLProtocol.handle = { [payload] _ in (200, payload) }
        let owner = try await provider.currentRecordingJournalOwner()
        XCTAssertNotNil(owner)
    }
    func testAccountSwitchAndSameAccountNewLoginRejectOldRequest() async throws {
        let store = MockSecureSessionStore(login())
        let (backend, session) = setup(store); defer { session.invalidateAndCancel() }
        let provider = AppleRecordingJournalOwnerProvider(transport: backend)
        OwnerURLProtocol.handle = { [payload] _ in (200, payload) }
        let resolved = try await provider.currentRecordingJournalOwner()
        let initial = try XCTUnwrap(resolved)
        for uid in ["B", "A"] {
            try store.replaceSession(login(uid), expecting: store.secureSnapshot().revision)
            let resolved = try await provider.currentRecordingJournalOwner()
            let newOwner = try XCTUnwrap(resolved)
            XCTAssertNotEqual(newOwner.loginGeneration, initial.loginGeneration)
            _ = await fails { _ = try await backend.requestRecordingJournal(
                BackendRequest(method: .POST, path: "/v1/device-sessions"), owner: initial) }
        }
    }
    func testSecureWriteFailureAndMismatchedReceiptFailClosed() async throws {
        let store = MockSecureSessionStore(login())
        let (backend, session) = setup(store); defer { session.invalidateAndCancel() }
        let provider = AppleRecordingJournalOwnerProvider(transport: backend)
        OwnerURLProtocol.handle = { [payload] _ in (200, payload) }
        store.failWrites = true
        _ = await fails { _ = try await provider.currentRecordingJournalOwner() }
        XCTAssertNil(try store.secureSnapshot().session?.recordingOwner)
        store.failWrites = false
        OwnerURLProtocol.handle = { [payload, key] _ in
            (200, payload.replacingOccurrences(of: "capture1.\(key)", with: "capture1.\(String(repeating: "c", count: 64))"))
        }
        _ = await fails { _ = try await provider.currentRecordingJournalOwner() }
        XCTAssertNil(try store.secureSnapshot().session?.recordingOwner)
    }
    func testRefreshPreservesGenerationAndDelayedRefreshCannotUndoLogout() async throws {
        var stored = login(); stored.expiresAtMs = 0
        let store = MockSecureSessionStore(stored)
        let (_, session) = setup(store); defer { session.invalidateAndCancel() }
        let auth = OmiAuthSession(config: .init(firebaseApiKey: "synthetic"), credentials: store,
            urlSession: session)
        OwnerURLProtocol.handle = { _ in (200,
            "{\"id_token\":\"fresh\",\"refresh_token\":\"fresh-refresh\",\"user_id\":\"A\",\"expires_in\":3600}") }
        let refreshed = await auth.resolveBearerToken()
        XCTAssertEqual(refreshed, "fresh")
        XCTAssertEqual(try store.secureSnapshot().session?.loginGeneration, stored.loginGeneration)
        try store.replaceSession(stored, expecting: store.secureSnapshot().revision)
        OwnerURLProtocol.handle = { _ in
            try store.clearSecureSession()
            return (200, "{\"id_token\":\"late\",\"refresh_token\":\"late\",\"user_id\":\"A\"}")
        }
        let late = await auth.resolveBearerToken()
        XCTAssertNil(late)
        XCTAssertNil(try store.secureSnapshot().session)
    }
    func testDelayedReplayResponseIsFencedAfterLogout() async throws {
        let store = MockSecureSessionStore(login())
        let (backend, session) = setup(store); defer { session.invalidateAndCancel() }
        OwnerURLProtocol.handle = { [payload] _ in (200, payload) }
        let resolved = try await AppleRecordingJournalOwnerProvider(transport: backend)
            .freshRecordingJournalOwner()
        let owner = try XCTUnwrap(resolved)
        OwnerURLProtocol.handle = { _ in try store.clearSecureSession(); return (200, "{}") }
        _ = await fails { _ = try await backend.requestRecordingJournal(
            BackendRequest(method: .POST, path: "/v1/device-sessions"), owner: owner) }
    }
    func testExplicitRedemptionCreatesGenerationAndSignOutFencesDelayedRedemption() async throws {
        let store = MockSecureSessionStore(login())
        let (_, session) = setup(store); defer { session.invalidateAndCancel() }
        let auth = OmiAuthSession(config: .init(firebaseApiKey: "synthetic"), credentials: store,
            urlSession: session)
        let response = "{\"idToken\":\"redeemed\",\"refreshToken\":\"refresh\",\"localId\":\"A\"}"
        let initial = try store.secureSnapshot().session?.loginGeneration
        OwnerURLProtocol.handle = { _ in (200, response) }
        let first = await auth.redeemCustomToken("synthetic", pinPlane: nil)
        XCTAssertTrue(first)
        let secondGeneration = try store.secureSnapshot().session?.loginGeneration
        XCTAssertNotEqual(secondGeneration, initial)
        let second = await auth.redeemCustomToken("synthetic", pinPlane: nil)
        XCTAssertTrue(second)
        XCTAssertNotEqual(try store.secureSnapshot().session?.loginGeneration, secondGeneration)
        let reached = expectation(description: "redemption response held")
        let release = DispatchSemaphore(value: 0)
        OwnerURLProtocol.handle = { _ in
            reached.fulfill()
            guard release.wait(timeout: .now() + 5) == .success else { throw URLError(.timedOut) }
            return (200, response)
        }
        let pending = Task { await auth.redeemCustomToken("synthetic", pinPlane: nil) }
        await fulfillment(of: [reached], timeout: 5)
        _ = try await auth.signOut()
        release.signal()
        let late = await pending.value
        XCTAssertFalse(late)
        XCTAssertNil(try store.secureSnapshot().session)
        OwnerURLProtocol.handle = { _ in (200, response) }
        let next = await auth.redeemCustomToken("synthetic", pinPlane: nil)
        XCTAssertTrue(next)
    }

    func testLogoutDuringGenerationMigrationCannotRestoreOldSession() async throws {
        var stored = login(); stored.loginGeneration = nil
        let store = MockSecureSessionStore(stored)
        let (backend, session) = setup(store); defer { session.invalidateAndCancel() }
        store.afterReplace = { try store.clearSecureSession() }
        OwnerURLProtocol.handle = { _ in
            XCTFail("Migration race must be rejected before ownership dispatch")
            return (200, "{}")
        }
        _ = await fails { _ = try await AppleRecordingJournalOwnerProvider(transport: backend)
            .currentRecordingJournalOwner() }
        XCTAssertNil(try store.secureSnapshot().session)
    }

    func testLegacyUIDMigrationAndNonNilMismatch() async throws {
        var stored = login(); stored.uid = nil; stored.expiresAtMs = 0
        let store = MockSecureSessionStore(stored)
        let (_, session) = setup(store); defer { session.invalidateAndCancel() }
        let auth = OmiAuthSession(config: .init(firebaseApiKey: "synthetic"), credentials: store,
            urlSession: session)
        OwnerURLProtocol.handle = { _ in (200,
            "{\"id_token\":\"fresh\",\"refresh_token\":\"refresh\",\"user_id\":\"A\"}") }
        let migrated = await auth.resolveBearerToken()
        XCTAssertEqual(migrated, "fresh")
        XCTAssertEqual(try store.secureSnapshot().session?.uid, "A")
        stored.uid = "B"
        try store.replaceSession(stored, expecting: store.secureSnapshot().revision)
        let mismatched = await auth.resolveBearerToken()
        XCTAssertNil(mismatched)
        XCTAssertEqual(try store.secureSnapshot().session?.uid, "B")
    }

    func testComposedJournalIsolationVaultFailureAndFreshReplay() async throws {
        let store = MockSecureSessionStore(login())
        let (backend, session) = setup(store); defer { session.invalidateAndCancel() }
        let provider = AppleRecordingJournalOwnerProvider(transport: backend)
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: root) }
        let vault = SyntheticRecordingJournalVault()
        let adapter = EncryptedRecordingJournalTransport(backend: backend, ownerProvider: provider,
            vault: vault, files: POSIXAtomicRecordingJournalFiles(), root: root)
        OwnerURLProtocol.handle = { [payload] _ in (200, payload) }
        let input = RecordingJournalInput(captureId: UUID().uuidString.lowercased(),
            capturedAtMs: 123, deviceId: "device-1", deviceName: "Synthetic", codec: 21)
        let journal = try await adapter.createRecordingJournal(input)
        let failedVault = EncryptedRecordingJournalTransport(backend: backend, ownerProvider: provider,
            vault: UnavailableRecordingJournalVault(), files: POSIXAtomicRecordingJournalFiles(), root: root)
        _ = await fails { _ = try await failedVault.readRecordingJournal(handle: journal.handle) }
        let retained = try await adapter.readRecordingJournal(handle: journal.handle)
        XCTAssertEqual(retained.captureId, input.captureId)
        OwnerURLProtocol.handle = { request in
            XCTAssertEqual(request.httpMethod, "GET", "Replay must not dispatch during an ownership outage")
            throw URLError(.notConnectedToInternet)
        }
        let cached = try await adapter.readRecordingJournal(handle: journal.handle)
        XCTAssertEqual(cached.captureId, input.captureId)
        _ = await fails { _ = try await adapter.requestRecordingJournal(handle: journal.handle,
            request: BackendRequest(method: .POST, path: "/v1/device-sessions")) }
        let auth = OmiAuthSession(config: .init(firebaseApiKey: "synthetic"), credentials: store,
            urlSession: session)
        _ = try await auth.signOut()
        _ = await fails { _ = try await adapter.readRecordingJournal(handle: journal.handle) }
        try store.replaceSession(login(), expecting: store.secureSnapshot().revision)
        OwnerURLProtocol.handle = { [payload] _ in (200, payload) }
        let next = try await adapter.listRecordingJournals()
        XCTAssertTrue(next.isEmpty)
        _ = await fails { _ = try await adapter.readRecordingJournal(handle: journal.handle) }
        let newJournal = try await adapter.createRecordingJournal(input)
        XCTAssertEqual(newJournal.captureId, input.captureId)
        let partitions = try POSIXAtomicRecordingJournalFiles().listPartitionDirectories(in: root)
        XCTAssertEqual(partitions.count, 2)
    }

}

private final class MockSecureSessionStore: SecureSessionCredentialStoring, @unchecked Sendable {
    private let lock = NSLock()
    private var value: StoredSession?
    private var revision = UUID().uuidString
    var failWrites = false
    var afterReplace: (@Sendable () throws -> Void)?
    init(_ value: StoredSession?) { self.value = value }
    func secureSnapshot() throws -> SecureSessionSnapshot {
        lock.withLock { SecureSessionSnapshot(revision: revision, session: value) }
    }
    func replaceSession(_ session: StoredSession?, expecting expected: String) throws {
        try lock.withLock {
            guard expected == revision else { throw SecureSessionError.changed }
            guard !failWrites else { throw SecureSessionError.unavailable }
            revision = UUID().uuidString; value = session
        }
        try afterReplace?()
    }
    func clearSecureSession() throws { lock.withLock { revision = UUID().uuidString; value = nil } }
    func load() async -> StoredSession? { try? secureSnapshot().session }
    func store(_ session: StoredSession) async {
        try? replaceSession(session, expecting: secureSnapshot().revision)
    }
    func clear() async { try? clearSecureSession() }
}

private final class OwnerURLProtocol: URLProtocol, @unchecked Sendable {
    nonisolated(unsafe) static var handle: (@Sendable (URLRequest) throws -> (Int, String))?
    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        do {
            let (status, body) = try Self.handle!(request)
            let response = HTTPURLResponse(url: request.url!, statusCode: status,
                httpVersion: "HTTP/1.1", headerFields: nil)!
            client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
            client?.urlProtocol(self, didLoad: Data(body.utf8))
            client?.urlProtocolDidFinishLoading(self)
        } catch { client?.urlProtocol(self, didFailWithError: error) }
    }
    override func stopLoading() {}
}
#endif
