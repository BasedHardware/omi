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
///   queued SDK sends, retries, and redirects included. The entry check and the backing task's
///   resume run under the same lock `enterAirgap()` takes, so a request arriving concurrently
///   with the Airgap switch is ordered entirely before it (admitted) or entirely after it
///   (refused); nothing straddles entry. Requests admitted *before* entry may still complete or
///   be cancelled; ``Decision`` keeps that distinction explicit.
/// - Admission reads live `NetworkEgress` suppression at decision time instead of trusting an
///   asynchronously delivered observer flag.
/// - Redirects are refused, never followed: Sentry's DSN endpoint does not redirect, and a
///   redirect is a destination the sender did not choose. The backing session's delegate vetoes
///   redirect following (`RedirectFollowerStopper`), and a 3xx that arrives anyway fails the
///   send without contacting the redirect target.
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
        case cancelledBeforeAdmission
    }

    // MARK: The one-way entry flag

    /// Serializes ``enterAirgap`` against the whole admission region — entry check *and* backing
    /// resume — so a request arriving concurrently with the Airgap switch is strictly ordered
    /// against it. Lock order: `admissionLock` → a protocol instance's `stateLock`. Never held
    /// across a client or telemetry callback.
    private static let admissionLock = NSLock()
    private static var hasEnteredAirgap = false

    static var isClosed: Bool {
        admissionLock.lock(); defer { admissionLock.unlock() }
        return hasEnteredAirgap
    }

    /// Permanently closes admission for this process. Infallible — memory only — so Airgap entry
    /// never depends on any I/O succeeding. Resume happens only on a fresh launch, which is the
    /// only place `ContextSentry.start` re-arms reporting.
    static func enterAirgap() {
        admissionLock.lock()
        hasEnteredAirgap = true
        admissionLock.unlock()
    }

    /// Live suppression source; injectable for tests. Defaults to the real ExclusionEngine-backed
    /// state, so admission always reflects current policy rather than a cached observer copy.
    nonisolated(unsafe) static var liveSuppression: () -> Bool = {
        NetworkEgress.isSuppressed(.crashReporting)
    }

    #if DEBUG
    /// Test seam for the backing forwarder: lets the real gate code forward into a canned
    /// protocol instead of the network. `nil` (production) builds the real session. The session
    /// it returns must carry ``RedirectFollowerStopper`` as its delegate, exactly as production's
    /// does.
    nonisolated(unsafe) static var forwarderOverride:
        ((URLSessionConfiguration) -> URLSession)?

    /// Clears every test seam this type owns, **modeled as a fresh process**: the one-way entry
    /// flag returns to `false` (under the admission lock), injected seams are removed, and the
    /// decision record is emptied. Test suites call this in `setUp`/`tearDown` and between
    /// modeled processes; it is the only way a closed gate re-opens.
    static func resetTestSeams() {
        admissionLock.lock()
        hasEnteredAirgap = false
        admissionLock.unlock()
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
    /// A `URLSession` follows redirects itself and delivers only the final response — the outer
    /// protocol stack never sees the hop, which would let a redirect leave the audited path
    /// entirely. Completing with `nil` is the documented way to refuse: the task then finishes
    /// with the 3xx response, and ``deliverForwarded`` fails the send without contacting the
    /// redirect target.
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

    // MARK: Admission

    /// Serializes ``stopLoading`` against the resume below: once `stopped` is set, no task this
    /// protocol instance created can be resumed afterwards.
    private let stateLock = NSLock()
    private var forwarderTask: URLSessionDataTask?
    private var stopped = false

    override func startLoading() {
        // Prepare a suspended task outside the locks. Session construction and test factories
        // must not run inside admission. The production suppression source is a plain read;
        // ExclusionEngine releases its lock before calling observers that close this gate.
        let task = Self.forwarderSession().dataTask(with: request) {
            [weak self] data, response, error in
            self?.deliverForwarded(data: data, response: response, error: error)
        }
        let decision: Decision
        Self.admissionLock.lock()
        stateLock.lock()
        if stopped {
            decision = .cancelledBeforeAdmission
        } else if Self.hasEnteredAirgap {
            decision = .refusedAfterEntry
        } else if Self.liveSuppression() {
            decision = .refusedByLiveSuppression
        } else {
            decision = .admittedBeforeEntry
            forwarderTask = task
        }
        // This only appends to a DEBUG array; it invokes no telemetry or client callbacks.
        record(decision)
        if decision == .admittedBeforeEntry {
            task.resume()
        } else {
            stopped = true // suppress the cancelled backing task's completion
        }
        stateLock.unlock()
        Self.admissionLock.unlock()

        switch decision {
        case .admittedBeforeEntry:
            break
        case .cancelledBeforeAdmission:
            task.cancel()
        case .refusedAfterEntry, .refusedByLiveSuppression:
            task.cancel()
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
        stateLock.lock()
        stopped = true
        let task = forwarderTask
        forwarderTask = nil
        stateLock.unlock()
        task?.cancel()
    }

    #if DEBUG
    private func record(_ decision: Decision) {
        Self.recorderLock.lock(); defer { Self.recorderLock.unlock() }
        Self.recordedDecisions.append(
            (request.url ?? URL(string: "https://unknown.invalid")!, decision))
    }
    #else
    private func record(_ decision: Decision) {}
    #endif

    // MARK: Forwarding

    /// One backing session for the process: `URLSession` retains its delegate until invalidated,
    /// so a per-request session would leak on every send. The session is thread-safe; its only
    /// behavior is `RedirectFollowerStopper`'s redirect veto.
    private static let backingForwarderSession: URLSession = makeBackingForwarderSession()

    private static func forwarderSession() -> URLSession {
        #if DEBUG
        if let override = Self.forwarderOverride {
            return override(URLSessionConfiguration.ephemeral)
        }
        #endif
        return backingForwarderSession
    }

    private func deliverForwarded(data: Data?, response: URLResponse?, error: Error?) {
        stateLock.lock()
        let shouldDeliver = !stopped
        stateLock.unlock()
        guard shouldDeliver else { return }
        if let error {
            client?.urlProtocol(self, didFailWithError: error)
            return
        }
        guard let http = response as? HTTPURLResponse else {
            client?.urlProtocol(
                self,
                didFailWithError: NSError(
                    domain: NSURLErrorDomain, code: NSURLErrorBadServerResponse))
            return
        }
        if (300..<400).contains(http.statusCode) {
            // Refused, never followed (see the type docs): the send fails here, and the redirect
            // target — wherever it points — is never contacted.
            client?.urlProtocol(
                self,
                didFailWithError: NSError(
                    domain: NSURLErrorDomain, code: NSURLErrorBadServerResponse,
                    userInfo: [
                        NSLocalizedDescriptionKey:
                            "Context Sentry forwarder refused redirect \(http.statusCode)"
                    ]))
            return
        }
        // Order matters: the client requires the response before any body bytes.
        client?.urlProtocol(self, didReceive: http, cacheStoragePolicy: .notAllowed)
        if let data { client?.urlProtocol(self, didLoad: data) }
        client?.urlProtocolDidFinishLoading(self)
    }

    private static func makeBackingForwarderSession() -> URLSession {
        let configuration = URLSessionConfiguration.ephemeral
        // No protocol classes: any protocol here would be another interception layer inside the
        // forwarding path, and recursive interception is what this design must avoid. The
        // delegate exists to refuse redirects (see `RedirectFollowerStopper`), nothing else.
        return URLSession(
            configuration: configuration, delegate: RedirectFollowerStopper(), delegateQueue: nil)
    }
}
