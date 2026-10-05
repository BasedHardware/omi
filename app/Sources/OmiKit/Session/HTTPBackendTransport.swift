import Foundation
#if !SKIP
#if canImport(FoundationNetworking)
import FoundationNetworking
#endif
#endif

// URLSession-based `BackendTransport`. Policy (the C++ middleware) owns the
// timeout table, capture-path classification, and hostname classes; this
// transport consults it and never re-derives any rule. Credentials are
// injected from `CredentialStoring`; a 401 invalidates the session through
// the `sessionInvalidated` stream.

public actor HTTPBackendTransport: BackendTransport {
    private let session: URLSession
    private let credentials: CredentialStoring
    private let originOverride: String?
    private let bearerResolver: (@Sendable () async -> String?)?
    private let planeStore: SoftwarePlaneStoring?
    private var planeStoreRevision: String?
    private var planeRevision = UUID().uuidString
    private var storedPlane: String?
    private var stampedValid: Bool
    private var planeLocked: Bool
    private let invalidation: InvalidationBox
    #if !SKIP
    private var generationRequests = [String: (id: String, task: Task<BackendResponse, Error>)]()
    #endif

    private final class InvalidationBox: @unchecked Sendable {
        let continuation: AsyncStream<Void>.Continuation
        let stream: AsyncStream<Void>
        private let lock = NSLock()

        init() {
            var captured: AsyncStream<Void>.Continuation!
            self.stream = AsyncStream { continuation in
                captured = continuation
            }
            self.continuation = captured
        }
    }

    public struct PlaneSelection: Sendable {
        /// Persisted software-plane value (`omi.backend.softwarePlane`).
        public var storedPlane: String?
        /// True when a stamped, validated v5 origin exists.
        public var stampedValid: Bool
        public var allowPlaneSwitch: Bool

        public init(storedPlane: String?, stampedValid: Bool, allowPlaneSwitch: Bool = true) {
            self.storedPlane = storedPlane
            self.stampedValid = stampedValid
            self.allowPlaneSwitch = allowPlaneSwitch
        }
    }

    public init(
        session: URLSession = {
            let configuration = URLSessionConfiguration.ephemeral
            #if !SKIP
            configuration.httpCookieStorage = nil
            #endif
            return URLSession(configuration: configuration)
        }(),
        credentials: CredentialStoring,
        planeSelection: PlaneSelection,
        originOverride: String? = nil,
        bearerResolver: (@Sendable () async -> String?)? = nil,
        planeStore: SoftwarePlaneStoring? = nil
    ) {
        self.session = session
        self.credentials = credentials
        self.originOverride = originOverride
        self.bearerResolver = bearerResolver
        self.planeStore = planeStore
        if let planeStore {
            let selected = planeStore.softwarePlaneSnapshot()
            self.storedPlane = selected.storedPlane
            self.planeStoreRevision = selected.revision
        } else { self.storedPlane = planeSelection.storedPlane }
        self.stampedValid = planeSelection.stampedValid
        self.planeLocked = !planeSelection.allowPlaneSwitch
        self.invalidation = InvalidationBox()
    }

    public var sessionInvalidated: AsyncStream<Void> {
        invalidation.stream
    }

    // MARK: Plane and contract

    private func isNewPlane() -> Bool {
        synchronizePlaneSelection()
        return Policy.softwarePlaneIsNew(stored: storedPlane, stampedValid: stampedValid)
    }

    private func synchronizePlaneSelection() {
        if let planeStore {
            let selected = planeStore.softwarePlaneSnapshot()
            changePlane(to: selected.storedPlane, selectionRevision: selected.revision)
        }
    }

    private func isPlaneCurrent(_ revision: String) -> Bool {
        synchronizePlaneSelection()
        return revision == planeRevision
    }

    private func changePlane(to selected: String?, selectionRevision: String? = nil) {
        guard storedPlane != selected || planeStoreRevision != selectionRevision else { return }
        storedPlane = selected
        planeStoreRevision = selectionRevision
        planeRevision = UUID().uuidString
        #if !SKIP
        for request in generationRequests.values { request.task.cancel() }
        #endif
    }

    public func apiContract() async -> APIContract? {
        isNewPlane() ? .canonical : .omi
    }

    public func softwarePlane() async -> SoftwarePlane? {
        isNewPlane() ? .new : .old
    }

    @discardableResult
    public func setSoftwarePlane(_ plane: SoftwarePlane) async -> SoftwarePlane? {
        guard !planeLocked else { return await softwarePlane() }
        planeStore?.storeSoftwarePlane(plane)
        if planeStore != nil { synchronizePlaneSelection() }
        else { changePlane(to: plane.rawValue) }
        return await softwarePlane()
    }

    public func stampedBackendOrigin() async -> String? {
        originOverride
    }

    // MARK: Requests

    private func resolveURL(path: String) throws -> URL {
        let origin = isNewPlane() ? originOverride : CLOUD_BACKEND_ORIGIN
        return try makeURL(path: path, origin: origin)
    }

    private func makeURL(path: String, origin: String?) throws -> URL {
        guard var origin else {
            throw TransportFailure.unconfigured
        }
        while origin.hasSuffix("/") { origin.removeLast() }
        guard let url = URL(string: origin + path) else {
            throw TransportFailure.unconfigured
        }
        return url
    }

    public func request(_ request: BackendRequest) async throws -> BackendResponse {
        synchronizePlaneSelection()
        let revision = planeRevision
        let contract: APIContract = isNewPlane() ? .canonical : .omi
        if let expected = request.expectedApiContract, expected != contract {
            throw TransportFailure.unconfigured
        }
        let url = try resolveURL(path: request.path)
        let token: String?
        if let bearerResolver { token = await bearerResolver() }
        else { token = await credentials.load()?.idToken }
        guard isPlaneCurrent(revision) else { throw TransportFailure.unconfigured }
        guard let token, !token.isEmpty else { throw TransportFailure.unauthorized }
        return try await execute(makeRequest(request, url: url, token: token),
            id: request.id, capturePath: Policy.isCapturePath(request.path), expectedPlane: revision)
    }

    private func makeRequest(_ request: BackendRequest, url: URL, token: String) -> URLRequest {
        var result = URLRequest(url: url)
        result.httpMethod = request.method.rawValue
        result.timeoutInterval = Double(Policy.requestTimeoutSeconds(
            method: request.method.rawValue, path: Policy.routeStrip(request.path) ?? request.path))
        result.httpBody = request.body.map { Data($0.utf8) }
        result.setValue("application/json", forHTTPHeaderField: "content-type")
        for (name, value) in request.headers {
            // These fields belong exclusively to the native authenticated path.
            if !["authorization", "host", "x-omi-capture-ownership"].contains(name.lowercased()) {
                result.setValue(value, forHTTPHeaderField: name)
            }
        }
        result.setValue("Bearer \(token)", forHTTPHeaderField: "authorization")
        return result
    }

    private func execute(
        _ urlRequest: URLRequest, id: String, capturePath: Bool,
        ownershipProbe: Bool = false, invalidateOn401: Bool = true,
        expectedPlane: String? = nil
    ) async throws -> BackendResponse {
        let data: Data
        let response: URLResponse
        do {
            #if !SKIP
            (data, response) = try await session.data(for: urlRequest, delegate: RefuseBackendRedirects())
            #else
            (data, response) = try await session.data(for: urlRequest)
            #endif
        } catch is CancellationError {
            throw TransportFailure.cancelled
        } catch {
            #if !SKIP && canImport(Security)
            if let error = error as? URLError {
                if error.code == .cancelled { throw TransportFailure.cancelled }
                if ownershipProbe && [.cannotFindHost, .dnsLookupFailed, .cannotConnectToHost,
                    .notConnectedToInternet, .timedOut].contains(error.code) {
                    throw OwnershipConnectivityFailure.unavailable
                }
            }
            #endif
            throw TransportFailure.transportFailed
        }
        if let expectedPlane, !isPlaneCurrent(expectedPlane) {
            throw TransportFailure.unconfigured
        }
        guard let http = response as? HTTPURLResponse else {
            throw TransportFailure.transportFailed
        }
        let status = http.statusCode
        if status == 401 {
            // The configured session is no longer authorized; surface
            // invalidation to the Authenticating owner.
            if invalidateOn401 { invalidation.continuation.yield() }
            throw TransportFailure.unauthorized
        }
        var retryAfterSeconds: Int?
        for header in http.allHeaderFields {
            if let name = header.key as? String, name.lowercased() == "retry-after",
                let value = header.value as? String, let seconds = Int(value)
            {
                retryAfterSeconds = seconds
            }
        }
        return BackendResponse(
            id: id, status: status, body: String(decoding: data, as: UTF8.self),
            retryAfterSeconds: retryAfterSeconds)
    }

    // MARK: Generation SSE

    public func generationEvents(
        generationId: String,
        lastEventId: String?,
        onFrame: @escaping @Sendable (String) -> Void
    ) async throws -> BackendResponse {
        // Apply a completed login pin before registering this new request, so
        // retiring requests from the preceding plane cannot cancel it.
        synchronizePlaneSelection()
        #if !SKIP
        // Registration precedes the first suspension, so cancellation works
        // even while headers or credentials are still pending.
        generationRequests[generationId]?.task.cancel()
        let requestId = UUID().uuidString
        let task = Task {
            try await self.receiveGenerationEvents(
                generationId: generationId, lastEventId: lastEventId, onFrame: onFrame)
        }
        generationRequests[generationId] = (requestId, task)
        defer {
            if generationRequests[generationId]?.id == requestId {
                generationRequests.removeValue(forKey: generationId)
            }
        }
        return try await withTaskCancellationHandler {
            try await task.value
        } onCancel: {
            task.cancel()
        }
        #else
        return try await receiveGenerationEvents(
            generationId: generationId, lastEventId: lastEventId, onFrame: onFrame)
        #endif
    }

    private func receiveGenerationEvents(
        generationId: String, lastEventId: String?,
        onFrame: @escaping @Sendable (String) -> Void
    ) async throws -> BackendResponse {
        let path = "/v1/chat-generations/\(encodeQueryComponent(generationId))/events"
        var urlRequest = URLRequest(url: try resolveURL(path: path))
        urlRequest.httpMethod = "GET"
        urlRequest.timeoutInterval = Double(Policy.requestTimeoutSeconds(method: "GET", path: "/v1/chat-generations"))
        if let lastEventId {
            urlRequest.setValue(lastEventId, forHTTPHeaderField: "last-event-id")
        }
        let revision = planeRevision
        let token: String?
        if let bearerResolver { token = await bearerResolver() }
        else { token = await credentials.load()?.idToken }
        guard isPlaneCurrent(revision), let token, !token.isEmpty else {
            throw TransportFailure.unauthorized
        }
        urlRequest.setValue("Bearer \(token)", forHTTPHeaderField: "authorization")
        urlRequest.setValue("text/event-stream", forHTTPHeaderField: "accept")
        var data = Data()
        var streamBody = ""
        let http: HTTPURLResponse
        var decoder = SSEFrameDecoder()
        do {
            #if !SKIP && !canImport(FoundationNetworking)
            try Task.checkCancellation()
            let (bytes, response) = try await session.bytes(
                for: urlRequest, delegate: RefuseBackendRedirects())
            defer { bytes.task.cancel() }
            guard let response = response as? HTTPURLResponse else {
                throw TransportFailure.transportFailed
            }
            http = response
            try Task.checkCancellation()
            for try await byte in bytes {
                try Task.checkCancellation()
                guard isPlaneCurrent(revision) else { throw TransportFailure.cancelled }
                if http.statusCode == 200, let frame = decoder.append(byte) {
                    let chunk = frame + "\n\n"
                    streamBody += chunk
                    onFrame(chunk)
                } else if http.statusCode != 200 {
                    data.append(byte)
                }
            }
            try Task.checkCancellation()
            if http.statusCode == 200, let frame = decoder.finish() {
                let chunk = frame + "\n\n"
                streamBody += chunk
                onFrame(chunk)
            }
            #else
            // Skip/FoundationNetworking do not expose Apple's AsyncBytes API.
            // Preserve their existing response path with the shared UTF-8 decoder.
            let response: URLResponse
            #if !SKIP
            (data, response) = try await session.data(for: urlRequest, delegate: RefuseBackendRedirects())
            #else
            (data, response) = try await session.data(for: urlRequest)
            #endif
            guard let response = response as? HTTPURLResponse else {
                throw TransportFailure.transportFailed
            }
            http = response
            guard isPlaneCurrent(revision) else { throw TransportFailure.cancelled }
            if http.statusCode == 200 {
                for byte in [UInt8](data) {
                    #if !SKIP
                    try Task.checkCancellation()
                    #endif
                    guard isPlaneCurrent(revision) else { throw TransportFailure.cancelled }
                    if let frame = decoder.append(byte) {
                        let chunk = frame + "\n\n"
                        streamBody += chunk
                        onFrame(chunk)
                    }
                }
                if let frame = decoder.finish() {
                    let chunk = frame + "\n\n"
                    streamBody += chunk
                    onFrame(chunk)
                }
            }
            #endif
        } catch is CancellationError {
            throw TransportFailure.cancelled
        } catch {
            #if !SKIP
            if (error as? URLError)?.code == .cancelled || Task.isCancelled {
                throw TransportFailure.cancelled
            }
            #endif
            if let failure = error as? TransportFailure { throw failure }
            throw TransportFailure.transportFailed
        }
        guard isPlaneCurrent(revision) else { throw TransportFailure.cancelled }
        if http.statusCode == 401 {
            invalidation.continuation.yield()
            throw TransportFailure.unauthorized
        }
        var retryAfter: Int?
        for header in http.allHeaderFields {
            if let name = header.key as? String, name.lowercased() == "retry-after",
                let value = header.value as? String { retryAfter = Int(value) }
        }
        return BackendResponse(
            id: generationId, status: http.statusCode,
            body: http.statusCode == 200 ? streamBody : String(decoding: data, as: UTF8.self),
            retryAfterSeconds: retryAfter)
    }

    public func cancelGenerationEvents(generationId: String) async {
        #if !SKIP
        generationRequests[generationId]?.task.cancel()
        #endif
    }

    // MARK: Write identity

    public func createWriteId() async throws -> String {
        guard let entropy = Policy.authRandomBytes(WRITE_ID_ENTROPY_BYTES),
            let writeId = mintWriteId(entropy)
        else {
            throw TransportFailure.unconfigured
        }
        return writeId
    }

    public func createRecordingId() async throws -> String {
        let id = UUID().uuidString.lowercased()
        guard Policy.recordingUUIDValid(id) else {
            throw TransportFailure.unconfigured
        }
        return id
    }

}

#if !SKIP
/// A backend response cannot redirect the native bearer or ownership receipt.
private final class RefuseBackendRedirects: NSObject, URLSessionTaskDelegate, @unchecked Sendable {
    func urlSession(_ session: URLSession, task: URLSessionTask,
        willPerformHTTPRedirection response: HTTPURLResponse, newRequest request: URLRequest,
        completionHandler: @escaping @Sendable (URLRequest?) -> Void) {
        completionHandler(nil)
    }
}
#endif

#if !SKIP && canImport(Security)
private enum OwnershipConnectivityFailure: Error { case unavailable }

/// Production provider shares the transport's authenticated session and origin.
public struct AppleRecordingJournalOwnerProvider: RecordingJournalOwnerContextProviding {
    private let transport: HTTPBackendTransport
    public init(transport: HTTPBackendTransport) { self.transport = transport }
    public func currentRecordingJournalOwner() async throws -> RecordingJournalOwnerContext? {
        try await transport.recordingOwner(allowCached: true)
    }
    public func freshRecordingJournalOwner() async throws -> RecordingJournalOwnerContext? {
        try await transport.recordingOwner(allowCached: false)
    }
}

extension HTTPBackendTransport: RecordingJournalOwnerRequesting {
    fileprivate func recordingOwner(allowCached: Bool) async throws -> RecordingJournalOwnerContext? {
        guard isNewPlane(), let origin = originOverride,
            let secure = credentials as? SecureSessionCredentialStoring
        else { throw EncryptedRecordingJournalError.ownerUnavailable }
        let plane = planeRevision
        let beforeRefresh = try secure.secureSnapshot()
        guard beforeRefresh.session != nil else { return nil }
        if let bearerResolver { _ = await bearerResolver() }
        guard isPlaneCurrent(plane) else { throw EncryptedRecordingJournalError.ownerChanged }
        var snapshot = try secure.secureSnapshot()
        guard var stored = snapshot.session,
            stored.loginGeneration == beforeRefresh.session?.loginGeneration,
            stored.uid == beforeRefresh.session?.uid
        else { throw EncryptedRecordingJournalError.ownerChanged }
        // Migrate an existing secure login exactly once. No plaintext host can
        // acquire this capability or persist this identity.
        if stored.loginGeneration == nil {
            stored.loginGeneration = UUID().uuidString.lowercased()
            stored.recordingOwner = nil
            try secure.replaceSession(stored, expecting: snapshot.revision)
            snapshot = try secure.secureSnapshot()
            guard snapshot.session == stored else {
                throw EncryptedRecordingJournalError.ownerChanged
            }
        }
        guard !stored.idToken.isEmpty,
            allowCached || stored.expiresAtMs > Int64(Date().timeIntervalSince1970 * 1000)
        else { throw EncryptedRecordingJournalError.ownerUnavailable }
        let request = BackendRequest(expectedApiContract: .canonical, method: .GET,
            path: "/v1/device-sessions/ownership")
        let response: BackendResponse
        do {
            response = try await execute(makeRequest(request,
                url: try makeURL(path: request.path, origin: origin), token: stored.idToken),
                id: request.id, capturePath: false, ownershipProbe: true, invalidateOn401: false)
        } catch {
            guard isPlaneCurrent(plane),
                try secure.secureSnapshot().revision == snapshot.revision
            else { throw EncryptedRecordingJournalError.ownerChanged }
            if error is OwnershipConnectivityFailure, allowCached,
                let owner = stored.recordingOwner, owner.backendOrigin == origin {
                return try ownerContext(stored, origin: origin)
            }
            throw error
        }
        guard isPlaneCurrent(plane),
            try secure.secureSnapshot().revision == snapshot.revision
        else { throw EncryptedRecordingJournalError.ownerChanged }
        guard (200..<300).contains(response.status),
            let body = JSON.parseOrNull(response.body),
            let owner = body["ownership"],
            let key = owner["ownerKey"]?.stringValue,
            let receipt = owner["receipt"]?.stringValue
        else {
            let code = JSON.parseOrNull(response.body)?["error"]?["code"]?.stringValue
                ?? JSON.parseOrNull(response.body)?["code"]?.stringValue ?? "ownership_unavailable"
            throw ChatBackendError(status: response.status, backendCode: code,
                retryable: response.status == 408 || response.status == 429 || response.status >= 500,
                action: "recording_ownership", retryAfterSeconds: response.retryAfterSeconds)
        }
        stored.recordingOwner = StoredRecordingOwner(backendOrigin: origin, ownerKey: key, receipt: receipt)
        let context = try ownerContext(stored, origin: origin)
        // Validate before persisting; success (including changed owner) replaces
        // the cached assertion only for the exact request session.
        try secure.replaceSession(stored, expecting: snapshot.revision)
        return context
    }

    private func ownerContext(_ stored: StoredSession, origin: String) throws -> RecordingJournalOwnerContext {
        guard let owner = stored.recordingOwner, owner.backendOrigin == origin,
            let generation = stored.loginGeneration
        else { throw EncryptedRecordingJournalError.ownerUnavailable }
        let context = RecordingJournalOwnerContext(backendOrigin: origin,
            ownerKey: owner.ownerKey, loginGeneration: generation, ownershipReceipt: owner.receipt)
        try context.validate()
        return context
    }

    public func requestRecordingJournal(_ request: BackendRequest,
        owner: RecordingJournalOwnerContext) async throws -> BackendResponse {
        guard isNewPlane(), originOverride == owner.backendOrigin,
            let secure = credentials as? SecureSessionCredentialStoring,
            let stored = try secure.secureSnapshot().session,
            try ownerContext(stored, origin: owner.backendOrigin) == owner,
            stored.expiresAtMs > Int64(Date().timeIntervalSince1970 * 1000),
            request.expectedApiContract == nil || request.expectedApiContract == .canonical
        else { throw EncryptedRecordingJournalError.ownerChanged }
        let plane = planeRevision
        // No suspension between checking the session and constructing the full
        // request. Later account changes cannot substitute their bearer.
        var pinned = makeRequest(request,
            url: try makeURL(path: request.path, origin: owner.backendOrigin), token: stored.idToken)
        pinned.setValue(owner.ownershipReceipt, forHTTPHeaderField: "x-omi-capture-ownership")
        let response = try await execute(pinned, id: request.id, capturePath: true, invalidateOn401: false)
        guard isPlaneCurrent(plane), let current = try secure.secureSnapshot().session,
            try ownerContext(current, origin: owner.backendOrigin).hasSameIdentity(as: owner)
        else { throw EncryptedRecordingJournalError.ownerChanged }
        return response
    }
}
#endif
