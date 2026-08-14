import Foundation

/// Everything that can go wrong between here and `api.omi.me`.
///
/// Five cases, because callers only ever act on five things: send the user to sign in, tell them
/// Airgap Mode is why nothing happened, show what the server said, report that we cannot read the
/// server's answer, or try again later. Deliberately carries no token, no request body, and no
/// response body.
enum OmiAPIError: LocalizedError {
    case notSignedIn
    /// Airgap Mode is on, so the request was never made. Not a failure — a setting.
    ///
    /// Distinct from `.transport` on purpose: a caller with a durable queue must *keep* the work and
    /// retry later, and one that treated this as a hard error would drop it.
    case airgapMode
    /// Status code plus a short server-supplied detail — never the whole body.
    case http(Int, String)
    case decoding(String)
    case transport(String)

    var errorDescription: String? {
        switch self {
        case .notSignedIn:
            return "Sign in to Omi first — I have nothing to authenticate with."
        case .airgapMode:
            return NetworkEgress.explanation(.omiAPI)
        case .http(let status, let detail):
            return detail.isEmpty ? "The Omi backend returned HTTP \(status)." : detail
        case .decoding(let detail):
            return "The Omi backend sent something I couldn't read: \(detail)"
        case .transport(let detail):
            return "I couldn't reach the Omi backend: \(detail)"
        }
    }
}

/// The only way Context for Claude talks to the Omi backend.
///
/// One shared instance, one shared `URLSession`, one header set, one retry policy. The retry policy
/// is the reason this is centralised: Context for Claude runs all day, so a client that reacts to a 429 by
/// trying again immediately would keep a rate-limited backend rate-limited, and every future caller
/// added to this app would have to re-derive that restraint. Here it is derived once.
///
/// `@unchecked Sendable` is honest: every stored property is a `let` set in `init` and never
/// mutated. `URLSession` is thread-safe by contract; `JSONDecoder`/`JSONEncoder` are safe to use
/// concurrently as long as nothing reconfigures them after construction, which nothing here does.
final class OmiAPI: @unchecked Sendable {
    static let shared = OmiAPI()

    private let session: URLSession
    private let decoder: JSONDecoder
    private let encoder: JSONEncoder

    private static let logCategory = "api"

    private init() {
        let config = URLSessionConfiguration.default
        config.timeoutIntervalForRequest = 30
        // `waitsForConnectivity` parks a request until the Mac has a route instead of failing it —
        // exactly right for a laptop that closes and opens all day. The catch is that the wait is
        // bounded by the *resource* timeout, whose default is seven days, so it needs its own
        // ceiling or an offline call would never return to its caller.
        config.waitsForConnectivity = true
        config.timeoutIntervalForResource = 300
        // Responses are one person's conversations and memories. Nothing about them belongs in a
        // shared on-disk URL cache.
        config.urlCache = nil
        config.requestCachePolicy = .reloadIgnoringLocalCacheData
        session = URLSession(configuration: config)
        decoder = Self.makeDecoder()
        encoder = Self.makeEncoder()
    }

    // MARK: - Base URL

    /// `https://api.omi.me/` — override with `OMI_PYTHON_API_URL` for local DEBUG builds only.
    ///
    /// Resolved once at first use: the value is process-wide configuration, and re-reading the
    /// environment per request would let a mid-run `setenv` split one session's traffic across two
    /// backends. The override is ignored in release builds so a wrapper or launcher cannot redirect
    /// production traffic.
    static var baseURL: URL { resolvedBaseURL }

    static let productionBaseURL = URL(string: "https://api.omi.me/")!

    private static let resolvedBaseURL: URL = {
        #if DEBUG
        return resolveBaseURL(ProcessInfo.processInfo.environment["OMI_PYTHON_API_URL"])
        #else
        return productionBaseURL
        #endif
    }()

    /// Always ends in `/`, so relative paths concatenate onto it without a special case.
    static func resolveBaseURL(_ override: String?) -> URL {
        guard let override else { return productionBaseURL }
        let trimmed = override.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return productionBaseURL }
        let terminated = trimmed.hasSuffix("/") ? trimmed : trimmed + "/"
        guard
            let url = URL(string: terminated),
            let scheme = url.scheme?.lowercased(),
            scheme == "http" || scheme == "https",
            url.host != nil
        else {
            // A typo in a local override must not silently redirect production traffic to nowhere.
            ContextLog.error("Ignoring unusable OMI_PYTHON_API_URL; using api.omi.me", logCategory)
            return productionBaseURL
        }
        return url
    }

    // MARK: - Verbs

    func get<T: Decodable>(_ path: String, query: [String: String] = [:], as type: T.Type) async throws -> T {
        let normalizedPath = Self.normalized(path)
        let url = try Self.url(for: normalizedPath, query: query)
        var request = URLRequest(url: url)
        request.httpMethod = "GET"
        request.allHTTPHeaderFields = try await headers()

        let (response, data) = try await send(request, method: "GET", path: normalizedPath)
        try Self.throwIfUnsuccessful(response, data)
        return try decode(type, from: data, path: normalizedPath)
    }

    func post<Body: Encodable, T: Decodable>(_ path: String, body: Body, as type: T.Type) async throws -> T {
        let normalizedPath = Self.normalized(path)
        let url = try Self.url(for: normalizedPath, query: [:])
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.allHTTPHeaderFields = try await headers()
        do {
            request.httpBody = try encoder.encode(body)
        } catch {
            // An unencodable body is ours, not the network's; say so rather than blaming transport.
            throw OmiAPIError.decoding("Could not encode the request body for \(normalizedPath)")
        }

        let (response, data) = try await send(request, method: "POST", path: normalizedPath)
        try Self.throwIfUnsuccessful(response, data)
        return try decode(type, from: data, path: normalizedPath)
    }

    /// Posts bytes we have already framed — audio, multipart, anything that isn't a `Codable` body.
    ///
    /// Returns the final status and body instead of throwing on 4xx/5xx: the callers for this are
    /// uploaders that treat "rejected" as data, not as an exception. Auth refresh and the retry
    /// policy still apply, so what comes back is the answer after the client has done its part.
    func postRaw(_ path: String, body: Data, contentType: String) async throws -> (Int, Data) {
        let normalizedPath = Self.normalized(path)
        let url = try Self.url(for: normalizedPath, query: [:])
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.allHTTPHeaderFields = try await headers()
        request.setValue(contentType, forHTTPHeaderField: "Content-Type")
        request.httpBody = body

        let (response, data) = try await send(request, method: "POST", path: normalizedPath)
        return (response.statusCode, data)
    }

    // MARK: - Headers

    /// Headers every request carries, including a fresh Authorization.
    ///
    /// The backend reads the first four; the rest are the telemetry the desktop client has always
    /// sent, kept identical so Context for Claude's traffic is legible in the same dashboards.
    func headers(forceRefresh: Bool = false) async throws -> [String: String] {
        let bearer = try await authorization(forceRefresh: forceRefresh)
        return [
            "Content-Type": "application/json",
            "Authorization": bearer,
            "X-App-Platform": "macos",
            "X-App-Version": Self.appVersion,
            "X-App-Build": Self.appBuild,
            "X-Device-Id-Hash": Self.deviceIdHash,
        ]
    }

    private func authorization(forceRefresh: Bool) async throws -> String {
        let auth = await MainActor.run { OmiAuth.shared }
        guard await auth.isSignedIn else { throw OmiAPIError.notSignedIn }
        do {
            return try await auth.authHeader(forceRefresh: forceRefresh)
        } catch OmiAuthError.airgapMode {
            // Building a header can itself need the network — a stale ID token is refreshed against
            // `securetoken.googleapis.com`. Carried across as `.airgapMode` rather than folded into
            // `.transport` below, because a queue that reads "transport" retries with backoff while
            // one that reads "airgap" simply waits for the switch.
            throw OmiAPIError.airgapMode
        } catch {
            // Two very different failures land here: the account went away, and the refresh call
            // itself failed. Asking auth again is what separates "sign in" from "try later" — and
            // signing the user out is auth's decision, never this file's.
            if await auth.isSignedIn == false { throw OmiAPIError.notSignedIn }
            ContextLog.error("Token refresh failed", Self.logCategory)
            throw OmiAPIError.transport("credentials could not be refreshed")
        }
    }

    // MARK: - Sending

    /// Performs `request`, applying the whole client-side policy, and returns whatever the server
    /// finally said. Never throws on an HTTP status — that judgement belongs to the caller.
    private func send(
        _ request: URLRequest, method: String, path: String
    ) async throws -> (HTTPURLResponse, Data) {
        var request = request
        var retries = 0
        var didRefreshAuth = false

        while true {
            // Monotonic: a duration measured across an NTP correction or a sleep/wake should still
            // read as elapsed time.
            let startedAt = DispatchTime.now().uptimeNanoseconds
            let (response, data) = try await perform(request, method: method, path: path)
            let elapsedMs = Double(DispatchTime.now().uptimeNanoseconds - startedAt) / 1_000_000
            // Method, path, status, duration. Never the query values (they carry the user's own
            // words), never a token, never a body.
            ContextLog.info(
                "\(method) \(path) → \(response.statusCode) in \(Int(elapsedMs.rounded()))ms", Self.logCategory)
            // **The server's own words, but only when the server is describing itself.** A 5xx body
            // is the backend naming which of its dependencies failed — `infrastructure_failure`,
            // `Service temporarily unavailable`, `account_deletion_state_unavailable` — and without
            // it a 503 is indistinguishable from every other 503, which is exactly the position this
            // app was in while a whole source silently returned nothing. Restricted to 5xx on
            // purpose: a 4xx detail is FastAPI quoting *our request* back, and our requests carry
            // the user's own search window and ids.
            if response.statusCode >= 500 {
                let detail = Self.detail(from: data, response: response)
                if !detail.isEmpty {
                    ContextLog.error("\(method) \(path) → \(response.statusCode): \(detail)", Self.logCategory)
                }
            }

            // Exactly one forced refresh per request. A second 401 is an answer, not a prompt to
            // keep asking: looping here is how a client with a genuinely rejected identity turns
            // into a login-storm against the backend.
            if response.statusCode == 401, !didRefreshAuth {
                didRefreshAuth = true
                let refreshed = try await authorization(forceRefresh: true)
                request.setValue(refreshed, forHTTPHeaderField: "Authorization")
                continue
            }

            guard Self.isTransient(response.statusCode), retries < Self.maxRetries,
                let delay = Self.retryDelay(retry: retries + 1, response: response)
            else {
                return (response, data)
            }
            retries += 1
            ContextLog.info(
                "\(method) \(path) → \(response.statusCode); retry \(retries)/\(Self.maxRetries)"
                    + " in \(String(format: "%.2f", delay))s", Self.logCategory)
            try await Task.sleep(for: .seconds(delay))
        }
    }

    /// One trip to the network, with every non-HTTP failure turned into `.transport`.
    ///
    /// Transport failures are never retried here, on purpose: a POST that timed out may well have
    /// been applied server-side already, and a client that resends it duplicates the user's own
    /// data. `waitsForConnectivity` already covers the case this would otherwise be for — no route.
    private func perform(
        _ request: URLRequest, method: String, path: String
    ) async throws -> (HTTPURLResponse, Data) {
        // The one line in this file that touches the network, so this is the one place Airgap Mode
        // has to be honoured. Gating each verb instead would mean every verb added later — and the
        // retry loop above, which comes back through here — needs its own copy of this check.
        //
        // It throws rather than returning a synthetic status: a fabricated 503 would be indexed by
        // `isTransient` and retried three times, spending eight seconds proving that the switch is
        // still on. It also throws *before* the request, so no URL, body, or header ever exists.
        guard !NetworkEgress.isSuppressed(.omiAPI) else {
            ContextLog.info("\(method) \(path) suppressed: Airgap Mode is on", Self.logCategory)
            NetworkEgress.recordSuppression(.omiAPI, outcome: .degraded)
            throw OmiAPIError.airgapMode
        }

        do {
            let (data, urlResponse) = try await session.data(for: request)
            guard let response = urlResponse as? HTTPURLResponse else {
                ContextLog.error("\(method) \(path) → non-HTTP response", Self.logCategory)
                throw OmiAPIError.transport("the server's reply was not HTTP")
            }
            return (response, data)
        } catch let error as OmiAPIError {
            throw error
        } catch is CancellationError {
            throw CancellationError()
        } catch {
            let reason = Self.reason(for: error)
            ContextLog.error("\(method) \(path) failed: \(reason)", Self.logCategory)
            throw OmiAPIError.transport(reason)
        }
    }

    // MARK: - Retry policy

    /// Three retries on top of the first attempt, so a request costs at most four round trips (five
    /// with the one auth refresh) and can never become an open-ended loop.
    private static let maxRetries = 3
    private static let retryBaseDelay: TimeInterval = 0.5
    private static let retryDelayCap: TimeInterval = 8

    /// 429 and 5xx only. A 4xx other than 429 means the request itself is wrong, and sending it
    /// again just spends someone's quota to get the same answer.
    private static func isTransient(_ status: Int) -> Bool {
        status == 429 || (500...599).contains(status)
    }

    /// Seconds to wait before retry number `retry` (1-based), or nil to stop retrying.
    ///
    /// `Retry-After` wins when the server sends one — it knows when it will be ready and we do not.
    /// If it asks for longer than we are willing to hold a call open, we stop instead of sleeping:
    /// blocking a caller for minutes is worse than handing back the 429 and letting it decide.
    ///
    /// Otherwise: exponential from 0.5 s, capped at 8 s, with equal jitter (half the delay fixed,
    /// half random). The jitter matters because Context for Claude's callers are timer-driven — without it,
    /// everything that failed together would come back together, forever.
    private static func retryDelay(retry: Int, response: HTTPURLResponse) -> TimeInterval? {
        if let requested = retryAfterSeconds(response) {
            guard requested <= retryDelayCap else { return nil }
            return max(0, requested)
        }
        let exponential = min(retryDelayCap, retryBaseDelay * pow(2, Double(retry - 1)))
        return exponential / 2 + Double.random(in: 0...(exponential / 2))
    }

    /// `Retry-After` is either delta-seconds or an HTTP-date; both are in the wild.
    private static func retryAfterSeconds(_ response: HTTPURLResponse) -> TimeInterval? {
        guard let raw = response.value(forHTTPHeaderField: "Retry-After")?
            .trimmingCharacters(in: .whitespacesAndNewlines), !raw.isEmpty
        else { return nil }
        if let seconds = TimeInterval(raw) { return max(0, seconds) }
        guard let date = httpDates.date(from: raw) else { return nil }
        return max(0, date.timeIntervalSinceNow)
    }

    private static let httpDates: DateFormatter = {
        let formatter = DateFormatter()
        formatter.dateFormat = "EEE, dd MMM yyyy HH:mm:ss zzz"
        // RFC 7231 dates are English and GMT regardless of where this Mac is.
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.timeZone = TimeZone(identifier: "GMT")
        return formatter
    }()

    // MARK: - URLs

    /// Paths are relative to a base that ends in `/`, so callers pass `"v1/…"` with no leading
    /// slash. A leading slash is caught loudly in debug and repaired in release, because silently
    /// producing `https://api.omi.me//v1/…` gets a 404 that reads like a backend problem.
    static func normalized(_ path: String) -> String {
        let trimmed = path.trimmingCharacters(in: .whitespacesAndNewlines)
        guard trimmed.hasPrefix("/") else { return trimmed }
        ContextLog.error("Path \"\(path)\" has a leading slash; paths are relative to the base URL", logCategory)
        assertionFailure("OmiAPI paths are relative — pass \"v1/…\", not \"\(path)\"")
        return String(trimmed.drop(while: { $0 == "/" }))
    }

    private static func url(for path: String, query: [String: String]) throws -> URL {
        guard !path.isEmpty else { throw OmiAPIError.transport("no path to request") }
        guard var components = URLComponents(url: baseURL, resolvingAgainstBaseURL: false) else {
            throw OmiAPIError.transport("the base URL is unusable")
        }
        // Appending to the base's own path keeps a local override like `http://localhost:8000/api/`
        // working; the setter handles percent-encoding and leaves `/` as a separator.
        let base = components.path.hasSuffix("/") ? components.path : components.path + "/"
        components.path = base + path
        if !query.isEmpty {
            // Sorted so the same call produces the same URL every time — dictionaries do not
            // promise an order, and an unstable URL is miserable to compare in a packet log.
            components.queryItems = query.sorted { $0.key < $1.key }.map {
                URLQueryItem(name: $0.key, value: $0.value)
            }
        }
        guard let url = components.url else {
            throw OmiAPIError.transport("could not build a URL for \(path)")
        }
        return url
    }

    // MARK: - Responses

    private static func throwIfUnsuccessful(_ response: HTTPURLResponse, _ data: Data) throws {
        guard !(200...299).contains(response.statusCode) else { return }
        throw OmiAPIError.http(response.statusCode, detail(from: data, response: response))
    }

    /// The server's own one-line explanation, if it sent one. Truncated hard: this string ends up
    /// in an error the UI may show, and a stack trace or an HTML error page helps nobody.
    private static func detail(from data: Data, response: HTTPURLResponse) -> String {
        var parts: [String] = []
        if let message = jsonMessage(in: data) { parts.append(message) }
        if let raw = response.value(forHTTPHeaderField: "Retry-After") {
            parts.append("retry after \(raw)")
        }
        return parts.joined(separator: " — ")
    }

    private static func jsonMessage(in data: Data) -> String? {
        guard
            let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
        else { return nil }
        for key in ["detail", "message", "error"] {
            guard let value = json[key] as? String else { continue }
            let trimmed = value.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !trimmed.isEmpty else { continue }
            return trimmed.count <= 200 ? trimmed : String(trimmed.prefix(200)) + "…"
        }
        return nil
    }

    private func decode<T: Decodable>(_ type: T.Type, from data: Data, path: String) throws -> T {
        do {
            return try decoder.decode(type, from: data)
        } catch let error as DecodingError {
            let description = Self.describe(error)
            ContextLog.error("\(path) → could not decode \(type)", Self.logCategory)
            throw OmiAPIError.decoding(description)
        } catch {
            ContextLog.error("\(path) → could not decode \(type)", Self.logCategory)
            throw OmiAPIError.decoding("\(type) could not be read")
        }
    }

    /// Names the field, not the value — which field is missing is the whole diagnosis, and the
    /// value is the user's data.
    private static func describe(_ error: DecodingError) -> String {
        func location(_ context: DecodingError.Context) -> String {
            let path = context.codingPath.map(\.stringValue).joined(separator: ".")
            return path.isEmpty ? "the response" : path
        }
        switch error {
        case .keyNotFound(let key, let context):
            return "missing field \(key.stringValue) in \(location(context))"
        case .typeMismatch(let type, let context):
            return "\(location(context)) is not a \(type)"
        case .valueNotFound(let type, let context):
            return "\(location(context)) was null, expected \(type)"
        case .dataCorrupted(let context):
            return "\(location(context)) is malformed"
        @unknown default:
            return "the response did not match what I expected"
        }
    }

    /// `localizedDescription` on a `URLError` is a sentence a person can act on ("The Internet
    /// connection appears to be offline"), which is exactly what belongs in a transport error.
    private static func reason(for error: Error) -> String {
        (error as? URLError)?.localizedDescription ?? error.localizedDescription
    }

    // MARK: - Coding

    private static func makeDecoder() -> JSONDecoder {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        decoder.dateDecodingStrategy = .custom { decoder in
            let container = try decoder.singleValueContainer()
            let raw = try container.decode(String.self)
            // The backend emits both shapes — Firestore timestamps arrive with microseconds,
            // hand-built payloads without — and which one a given field uses is not something a
            // model here should have to know.
            if let date = isoFractional.date(from: raw) { return date }
            if let date = isoStandard.date(from: raw) { return date }
            throw DecodingError.dataCorruptedError(
                in: container, debugDescription: "Not an ISO-8601 date")
        }
        return decoder
    }

    /// Mirrors the decoder exactly: snake_case on the wire, camelCase in Swift, fractional-second
    /// ISO-8601 for dates. A round trip through this pair has to come back unchanged.
    private static func makeEncoder() -> JSONEncoder {
        let encoder = JSONEncoder()
        encoder.keyEncodingStrategy = .convertToSnakeCase
        encoder.dateEncodingStrategy = .custom { date, encoder in
            var container = encoder.singleValueContainer()
            try container.encode(isoFractional.string(from: date))
        }
        return encoder
    }

    // `ISO8601DateFormatter` is thread-safe for parsing and costs enough to build that allocating
    // one per field would show up on a large payload.
    private static nonisolated(unsafe) let isoFractional: ISO8601DateFormatter = {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return formatter
    }()

    private static nonisolated(unsafe) let isoStandard = ISO8601DateFormatter()

    // MARK: - Device identity

    private static let appVersion =
        Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "unknown"
    private static let appBuild = Bundle.main.infoDictionary?["CFBundleVersion"] as? String ?? "unknown"

    /// A stable, non-reversible name for this Mac, in the exact shape the backend will accept.
    ///
    /// Forwarded from `ClientDevice`, which owns the contract and explains it. It is re-exported
    /// here rather than having callers reach past this client because `X-Device-Id-Hash` is a
    /// *header* — it is this file's business what goes in the header set, and every caller that
    /// wanted the value was already asking `OmiAPI` for it.
    static let deviceIdHash = ClientDevice.deviceIdHash
}
