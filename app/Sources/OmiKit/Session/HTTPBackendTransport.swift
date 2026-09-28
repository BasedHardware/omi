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
    private var storedPlane: String?
    private var stampedValid: Bool
    private var planeLocked: Bool
    private let invalidation: InvalidationBox

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
            configuration.httpCookieStorage = nil
            return URLSession(configuration: configuration)
        }(),
        credentials: CredentialStoring,
        planeSelection: PlaneSelection,
        originOverride: String? = nil
    ) {
        self.session = session
        self.credentials = credentials
        self.originOverride = originOverride
        self.storedPlane = planeSelection.storedPlane
        self.stampedValid = planeSelection.stampedValid
        self.planeLocked = !planeSelection.allowPlaneSwitch
        self.invalidation = InvalidationBox()
    }

    public var sessionInvalidated: AsyncStream<Void> {
        invalidation.stream
    }

    // MARK: Plane and contract

    private func isNewPlane() -> Bool {
        Policy.softwarePlaneIsNew(stored: storedPlane, stampedValid: stampedValid)
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
        storedPlane = plane.rawValue
        return await softwarePlane()
    }

    public func stampedBackendOrigin() async -> String? {
        originOverride
    }

    // MARK: Requests

    private func resolveURL(path: String) throws -> URL {
        let origin =
            originOverride
            ?? (isNewPlane() ? nil : CLOUD_BACKEND_ORIGIN)
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
        // Policy owns the timeout table (transcribe POST → 150s, else 60s).
        let timeout = Policy.requestTimeoutSeconds(
            method: request.method.rawValue, path: Policy.routeStrip(request.path) ?? request.path)
        var urlRequest = URLRequest(url: try resolveURL(path: request.path))
        urlRequest.httpMethod = request.method.rawValue
        urlRequest.timeoutInterval = Double(timeout)
        if let body = request.body {
            urlRequest.httpBody = Data(body.utf8)
        }
        urlRequest.setValue("application/json", forHTTPHeaderField: "content-type")
        if let token = await credentials.load()?.idToken {
            urlRequest.setValue("Bearer \(token)", forHTTPHeaderField: "authorization")
        }
        return try await execute(urlRequest, id: request.id, capturePath: Policy.isCapturePath(request.path))
    }

    private func execute(
        _ urlRequest: URLRequest, id: String, capturePath: Bool
    ) async throws -> BackendResponse {
        let data: Data
        let response: URLResponse
        do {
            (data, response) = try await session.data(for: urlRequest)
        } catch is CancellationError {
            throw TransportFailure.cancelled
        } catch {
            throw TransportFailure.transportFailed
        }
        guard let http = response as? HTTPURLResponse else {
            throw TransportFailure.transportFailed
        }
        let status = http.statusCode
        if status == 401 {
            // The configured session is no longer authorized; surface
            // invalidation to the Authenticating owner.
            invalidation.continuation.yield()
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
        let path = "/v1/chat-generations/\(encodeQueryComponent(generationId))/events"
        var urlRequest = URLRequest(url: try resolveURL(path: path))
        urlRequest.httpMethod = "GET"
        urlRequest.timeoutInterval = Double(Policy.requestTimeoutSeconds(method: "GET", path: "/v1/chat-generations"))
        if let lastEventId {
            urlRequest.setValue(lastEventId, forHTTPHeaderField: "last-event-id")
        }
        if let token = await credentials.load()?.idToken {
            urlRequest.setValue("Bearer \(token)", forHTTPHeaderField: "authorization")
        }
        let data: Data
        let response: URLResponse
        do {
            (data, response) = try await session.data(for: urlRequest)
        } catch is CancellationError {
            throw TransportFailure.cancelled
        } catch {
            throw TransportFailure.transportFailed
        }
        guard let http = response as? HTTPURLResponse else {
            throw TransportFailure.transportFailed
        }
        if http.statusCode == 401 {
            invalidation.continuation.yield()
            throw TransportFailure.unauthorized
        }
        if http.statusCode == 200 {
            // Deliver each SSE frame (blank-line delimited) as a string, the
            // same chunking the native bridge used on the JS boundary.
            var frames = [String]()
            var current = ""
            for byte in [UInt8](data) {
                current.append(Character(Unicode.Scalar(byte)))
                if current.hasSuffix("\n\n") {
                    frames.append(String(current.dropLast(2)))
                    current = ""
                }
            }
            if !current.isEmpty { frames.append(current) }
            for frame in frames { onFrame(frame) }
        }
        return BackendResponse(
            id: generationId, status: http.statusCode,
            body: String(decoding: data, as: UTF8.self),
            retryAfterSeconds: nil)
    }

    public func cancelGenerationEvents(generationId: String) async {
        // URLSession requests cannot be selectively torn down here; the
        // platform hosts wrap task cancellation around the stream call.
    }

    // MARK: Write identity

    public func createWriteId() async throws -> String {
        var entropy = [UInt8](repeating: 0, count: WRITE_ID_ENTROPY_BYTES)
        for index in entropy.indices {
            entropy[index] = UInt8.random(in: 0...255)
        }
        guard let writeId = mintWriteId(entropy) else {
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
