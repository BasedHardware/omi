import Foundation

// The authenticated backend transport seam. In the React Native tree this
// was the JS/native boundary (`OmiBackend` in `omiNativeTypes.ts`); in the
// Swift app the transport is a protocol implemented per platform, with
// credentials held natively (Keychain / Windows credential store / Android
// Keystore) and the shared C++ middleware (`native-core/`) consulted for
// policy. Session/auth implementations live in the Backend area.

public enum HTTPMethod: String, Sendable, Hashable {
    case GET
    case POST
    case PATCH
    case DELETE
}

public enum SoftwarePlane: String, Sendable, Hashable {
    case old
    case new
}

public enum APIContract: String, Sendable, Hashable {
    case omi
    case canonical
}

public struct BackendRequest: Sendable, Hashable {
    public var id: String
    public var expectedApiContract: APIContract?
    public var method: HTTPMethod
    public var path: String
    public var headers: [String: String]
    public var body: String?

    public init(
        id: String = UUID().uuidString.lowercased(),
        expectedApiContract: APIContract? = nil,
        method: HTTPMethod,
        path: String,
        headers: [String: String] = [:],
        body: String? = nil
    ) {
        self.id = id
        self.expectedApiContract = expectedApiContract
        self.method = method
        self.path = path
        self.headers = headers
        self.body = body
    }
}

public struct BackendResponse: Sendable, Hashable {
    public var id: String
    public var status: Int
    public var body: String?
    public var retryAfterSeconds: Int?

    public init(
        id: String, status: Int, body: String?, retryAfterSeconds: Int? = nil
    ) {
        self.id = id
        self.status = status
        self.body = body
        self.retryAfterSeconds = retryAfterSeconds
    }
}

/// Core authenticated transport. Implementations must inject credentials
/// themselves — callers never see or hold session tokens.
public protocol BackendTransport: Sendable {
    func request(_ request: BackendRequest) async throws -> BackendResponse
    /// Server-sent generation events for a chat generation; `onFrame` is
    /// called per SSE frame. Resolves with the terminal HTTP response.
    func generationEvents(
        generationId: String,
        lastEventId: String?,
        onFrame: @escaping @Sendable (_ frame: String) -> Void
    ) async throws -> BackendResponse
    func cancelGenerationEvents(generationId: String) async
    func createWriteId() async throws -> String
    func createRecordingId() async throws -> String
    /// Reports the API contract the transport is configured for, when known.
    func apiContract() async -> APIContract?
    func softwarePlane() async -> SoftwarePlane?
    @discardableResult
    func setSoftwarePlane(_ plane: SoftwarePlane) async -> SoftwarePlane?
    func stampedBackendOrigin() async -> String?
}

/// Optional journal storage capability, mirroring the TS
/// `hasRecordingJournal` feature probe: `transport as? RecordingJournalStoring`.
public protocol RecordingJournalStoring: Sendable {
    func createRecordingJournal(
        _ input: RecordingJournalInput
    ) async throws -> RecordingJournalRecord
    func listRecordingJournals() async throws -> [RecordingJournalRecord]
    func readRecordingJournal(handle: String) async throws -> RecordingJournalRecord
    @discardableResult
    func appendRecordingJournal(handle: String, entry: String) async throws -> Int
    /// Performs a backend request from inside the journal ownership context.
    func requestRecordingJournal(
        handle: String, request: BackendRequest
    ) async throws -> BackendResponse
    func removeRecordingJournal(handle: String) async
}

public func hasRecordingJournal(_ transport: BackendTransport) -> Bool {
    transport is RecordingJournalStoring
}

/// Session/auth surface (port of the `OmiAuth` native module contract).
public struct DesktopHandoff: Sendable, Hashable {
    public var code: String
    public var expiresAt: Int64
    public var browserUrl: String

    public init(code: String, expiresAt: Int64, browserUrl: String) {
        self.code = code
        self.expiresAt = expiresAt
        self.browserUrl = browserUrl
    }
}

public protocol Authenticating: Sendable {
    func signIn() async throws -> Bool
    func cancelSignIn() async
    func signOut() async throws -> Bool
    /// Emitted while a desktop-auth handoff sign-in waits for the browser.
    var desktopHandoffs: AsyncStream<DesktopHandoff> { get }
    /// Fired when the backend invalidates the active session.
    var sessionInvalidated: AsyncStream<Void> { get }
}

/// Optional session probe (the TS `OmiAuth.hasSession` capability).
/// Authenticators without it get the optimistic default in the session
/// gate; `OmiAuthSession` implements the real cloud check.
public protocol SessionProbeCapable: Authenticating {
    func hasCloudSession() async -> Bool
}
