import ContextCore
import Foundation

/// HTTP admission gate between Sentry's transport and the network.
///
/// Sentry is configured (`SentrySDKReporting`) with a dedicated `URLSession` built here whose
/// entire protocol stack is this `URLProtocol`. That is a supported public seam:
/// `SentryOptions.urlSession` exists for exactly this ("configure a custom NSURLSession"), and
/// `SentryTransportFactory` hands that session to every outgoing request — envelope sends,
/// cached-envelope drains, reachability retries (sentry-cocoa 8.58.0).
///
/// Contract:
/// - Once ``enterAirgap()`` runs, **no new HTTP request may start for the rest of the process** —
///   queued SDK sends, retries, and every redirect hop included. Requests admitted *before*
///   entry may still complete or be cancelled; ``Decision`` keeps that distinction explicit.
/// - Admission re-reads live `NetworkEgress` suppression at decision time instead of trusting an
///   asynchronously delivered observer flag.
/// - The backing forwarder session never follows a redirect itself (``RedirectFollowerStopper``
///   vetoes it): the gate resolves the `Location` and hands the redirected request back through
///   the gated session (`urlProtocol(wasRedirectedTo:)`), so **every hop crosses admission
///   again**. Auth-ish headers never survive a redirect; a cross-host redirect strips all headers.
/// - No telemetry callback runs while a gate lock is held — nothing can re-enter telemetry from
///   inside a critical section here.
final class ContextSentryGate: URLProtocol {

    enum Decision: String, Equatable {
        /// Started before Airgap entry; may complete or be cancelled by the SDK.
        case admittedBeforeEntry
        /// Arrived after entry; refused, and never handed to a backing session.
        case refusedAfterEntry
        /// Arrived before entry but live ExclusionEngine state suppresses reporting.
        case refusedByLiveSuppression
    }

    // MARK: The one-way entry flag

    private static let entryLock = NSLock()
    private static var hasEnteredAirgap = false

    #if DEBUG
    /// Test seam for the entry flag, following the same shape as `NetworkEgress.observer`:
    /// `nil` (production) means the real one-way flag decides. Tests set `false` to model an
    /// open gate without mutating process-global state, and must clear it again.
    nonisolated(unsafe) static var entryOverride: Bool?

    /// Reads the real, one-way flag for tests. `enterAirgap()` cannot be un-done, so this is the
    /// accessor the permanence test asserts against.
    static func hasProcessEnteredAirgapForTests() -> Bool {
        entryLock.lock(); defer { entryLock.unlock() }
        return hasEnteredAirgap
    }
    #endif

    static var isClosed: Bool {
        entryLock.lock(); defer { entryLock.unlock() }
        #if DEBUG
        if let entryOverride { return entryOverride }
        #endif
        return hasEnteredAirgap
    }

    /// Permanently closes admission for this process. Infallible — memory only — so Airgap entry
    /// never depends on any I/O succeeding. Resume happens only on a fresh launch, which is the
    /// only place `ContextSentry.start` re-arms reporting.
    static func enterAirgap() {
        entryLock.lock()
        hasEnteredAirgap = true
        entryLock.unlock()
    }

    /// Live suppression source; injectable for tests. Defaults to the real ExclusionEngine-backed
    /// state, so admission always reflects current policy rather than a cached observer copy.
    nonisolated(unsafe) static var liveSuppression: () -> Bool = {
        NetworkEgress.isSuppressed(.crashReporting)
    }

    #if DEBUG
    /// Test seam for the backing forwarder: lets the real gate code forward into a canned
    /// protocol instead of the network. `nil` (production) builds the real session. Tests must
    /// clear it again.
    nonisolated(unsafe) static var forwarderOverride:
        ((URLSessionConfiguration) -> URLSession)?

    /// Clears every test seam this type owns. Called from test `setUp`/`tearDown`.
    static func resetTestSeams() {
        entryOverride = nil
        forwarderOverride = nil
        liveSuppression = { NetworkEgress.isSuppressed(.crashReporting) }
        recorderLock.lock()
        recordedDecisions = []
        recorderLock.unlock()
    }

    private static let recorderLock = NSLock()
    private static var recordedDecisions: [(url: URL, decision: Decision)] = []
    static func recordedAdmissionDecisions() -> [(url: URL, decision: Decision)] {
        recorderLock.lock(); defer { recorderLock.unlock() }
        return recordedDecisions
    }
    #endif

    // MARK: The gated session Sentry is given

    /// The session handed to Sentry via `Options.urlSession`.
    static func makeSentrySession() -> URLSession {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [ContextSentryGate.self]
        configuration.timeoutIntervalForRequest = 15
        configuration.timeoutIntervalForResource = 30
        configuration.waitsForConnectivity = false
        return URLSession(configuration: configuration)
    }

    // MARK: URLProtocol plumbing

    override class func canInit(with request: URLRequest) -> Bool {
        request.url?.scheme == "https" || request.url?.scheme == "http"
    }

    override class func canonicalRequest(for request: URLRequest) -> URLRequest {
        request
    }

    /// Vetoes redirect following in the backing forwarder session.
    ///
    /// A completion-handler `URLSession` with no protocol classes follows redirects itself and
    /// delivers only the final response — the outer protocol stack never sees the hop, which
    /// would let a redirect bypass admission entirely. Completing with `nil` is the documented
    /// way to refuse: the task then finishes with the 3xx response itself, which is exactly what
    /// the gate's completion handler needs in order to re-admit the hop.
    final class RedirectFollowerStopper: NSObject, URLSessionTaskDelegate {
        func urlSession(
            _ session: URLSession,
            task: URLSessionTask,
            willPerformHTTPRedirection response: HTTPURLResponse,
            newRequest request: URLRequest,
            completionHandler: @escaping (URLRequest?) -> Void
        ) {
            completionHandler(nil)
        }
    }

    init(
        request: URLRequest,
        cachedResponse: CachedURLResponse?,
        client: URLProtocolClient?
    ) {
        super.init(request: request, cachedResponse: cachedResponse, client: client)
    }

    // MARK: Admission

    private func admit() -> Decision {
        // The decision reads the same lock-protected flag ``enterAirgap`` writes, so a request
        // arriving concurrently with entry is strictly ordered: it is either admitted-before or
        // refused-after, never both or in-between. No telemetry runs inside the critical section.
        if Self.isClosed { return .refusedAfterEntry }
        if Self.liveSuppression() { return .refusedByLiveSuppression }
        return .admittedBeforeEntry
    }

    override func startLoading() {
        let decision = admit()
        record(decision)
        switch decision {
        case .admittedBeforeEntry:
            forwardAdmitted(request)
        case .refusedAfterEntry, .refusedByLiveSuppression:
            client?.urlProtocol(
                self,
                didFailWithError: NSError(
                    domain: NSURLErrorDomain,
                    code: NSURLErrorNotConnectedToInternet,
                    userInfo: [NSLocalizedDescriptionKey: "Context Sentry admission refused"]
                )
            )
        }
    }

    override func stopLoading() {
        forwarderTask?.cancel()
    }

    #if DEBUG
    private func record(_ decision: Decision) {
        recorderLock.lock(); defer { recorderLock.unlock() }
        recordedDecisions.append((request.url ?? URL(string: "https://unknown.invalid")!, decision))
    }
    #else
    private func record(_ decision: Decision) {}
    #endif

    // MARK: Forwarding

    private var forwarderTask: URLSessionDataTask?

    /// One backing session for the process: `URLSession` retains its delegate until invalidated,
    /// so a per-request session would leak on every send. The session is thread-safe; its only
    /// behavior is `RedirectFollowerStopper`'s redirect veto.
    private static let backingForwarderSession: URLSession = makeBackingForwarderSession()

    /// Completion-handler forwarding. The backing session's stack is empty (or, in tests, a
    /// canned protocol): nothing here can follow a redirect, because `RedirectFollowerStopper`
    /// refuses, so a 3xx response arrives *here* and the hop is handed back to the gated session.
    private func forwardAdmitted(_ original: URLRequest) {
        let session: URLSession
        #if DEBUG
        if let forwarderOverride {
            session = forwarderOverride(URLSessionConfiguration.ephemeral)
        } else {
            session = Self.backingForwarderSession
        }
        #else
        session = Self.backingForwarderSession
        #endif
        let task = session.dataTask(with: original) { [weak self] data, response, error in
            guard let self else { return }
            if let error {
                self.client?.urlProtocol(self, didFailWithError: error)
                return
            }
            guard let http = response as? HTTPURLResponse else {
                self.client?.urlProtocol(
                    self,
                    didFailWithError: NSError(
                        domain: NSURLErrorDomain, code: NSURLErrorBadServerResponse))
                return
            }
            if let location = http.value(forHTTPHeaderField: "Location"),
                (300..<400).contains(http.statusCode),
                let redirectURL = URL(string: location, relativeTo: original.url)
            {
                let redirected = Self.sanitizedRedirectRequest(
                    for: original, redirectTo: redirectURL.absoluteURL,
                    statusCode: http.statusCode)
                // The redirected request goes back through the OUTER gated session: URLSession
                // re-issues it via this protocol stack, so `startLoading` — and therefore
                // admission — runs for the hop as if it were a fresh request.
                self.client?.urlProtocol(self, wasRedirectedTo: redirected, redirectResponse: http)
                return
            }
            if let data { self.client?.urlProtocol(self, didLoad: data) }
            if let url = http.url,
                let stored = HTTPURLResponse(
                    url: url, statusCode: http.statusCode, httpVersion: "HTTP/1.1",
                    headerFields: http.allHeaderFields as? [String: String])
            {
                self.client?.urlProtocol(
                    self, didReceive: stored, cacheStoragePolicy: .notAllowed)
            }
            self.client?.urlProtocolDidFinishLoading(self)
        }
        forwarderTask = task
        task.resume()
    }

    private static func makeBackingForwarderSession() -> URLSession {
        let configuration = URLSessionConfiguration.ephemeral
        // No protocol classes: any protocol here would be another interception layer inside the
        // forwarding path, and recursive interception is what this design must avoid. The
        // delegate exists to refuse redirects (see `RedirectFollowerStopper`), nothing else.
        return URLSession(
            configuration: configuration, delegate: RedirectFollowerStopper(), delegateQueue: nil)
    }

    /// Builds the request for a redirect hop:
    /// - 301/302/303 after a body-carrying request are re-issued as `GET` without a body
    ///   (historical client behavior the DSN endpoint itself is never expected to exercise);
    ///   307/308 keep method and body — same host only.
    /// - `Authorization`, `X-Sentry-Auth` (the DSN auth header), and `Cookie` never cross a
    ///   redirect, to any host.
    /// - A cross-host redirect strips **every** header: only the URL and method survive.
    static func sanitizedRedirectRequest(
        for original: URLRequest,
        redirectTo: URL,
        statusCode: Int
    ) -> URLRequest {
        var redirected = URLRequest(url: redirectTo)
        let sameHost = original.url?.host == redirectTo.host
        let keepsMethodAndBody = (statusCode == 307 || statusCode == 308) && sameHost

        if keepsMethodAndBody {
            redirected.httpMethod = original.httpMethod
            redirected.httpBody = Self.bodyData(of: original)
        } else {
            // 301/302/303 re-issue as GET (dropping the body); 307/308 to a different host are
            // also downgraded to GET — carrying a body to a host the redirect chose is exactly
            // the disclosure this sanitizer exists to prevent.
            redirected.httpMethod = "GET"
        }

        // Same-host hops keep their other headers; auth-ish headers never cross a redirect, and
        // hop-specific fields are recomputed by the session.
        guard sameHost, let headers = original.allHTTPHeaderFields else { return redirected }
        for (field, value) in headers {
            let lowered = field.lowercased()
            if lowered == "authorization" || lowered == "x-sentry-auth" || lowered == "cookie"
                || lowered == "host" || lowered == "content-length"
            {
                continue
            }
            redirected.setValue(value, forHTTPHeaderField: field)
        }
        return redirected
    }

    /// Reads a request's body whether it arrived inline or as a stream. `URLSession` hands
    /// `URLProtocol` bodies as `httpBodyStream`, so a 307/308 body that is copied without this
    /// reads as nil and the hop goes out bodyless — a corruption, not a privacy choice.
    private static func bodyData(of request: URLRequest) -> Data? {
        if let body = request.httpBody { return body }
        guard let stream = request.httpBodyStream else { return nil }
        stream.open()
        defer { stream.close() }
        var data = Data()
        let bufferSize = 4096
        let buffer = UnsafeMutablePointer<UInt8>.allocate(capacity: bufferSize)
        defer { buffer.deallocate() }
        while stream.hasBytesAvailable {
            let read = stream.read(buffer, maxLength: bufferSize)
            if read <= 0 { break }
            data.append(buffer, count: read)
        }
        return data
    }
}
