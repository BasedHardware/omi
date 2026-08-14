import ContextCore
import Foundation

/// The Activity spine's account half, over the real Omi backend.
///
/// `ActivityAccountReading` promises one value per read and never a throw, so everything below is an
/// exercise in turning three independent network calls into one honest answer. Three things decide
/// what that answer is:
///
/// 1. **Nothing is attempted when there is nothing to attempt.** Airgap Mode and a signed-out app
///    are answered before a URL is built, not by letting the network refuse three times. The spine
///    polls, so three refusals per tick would be three log lines and three suppression records for
///    a state that cannot change without the user acting.
/// 2. **The three reads race, they do not queue.** The spine is blocked on all of them, so serial
///    reads would cost the sum of three round trips to show one screen.
/// 3. **One dead source never zeroes the others.** See `reachable` below.
///
/// ## The credential, and why it is not the one the app is signed in with
///
/// `/v1/mcp/*` is the one endpoint family a Firebase ID token cannot open. Every route in
/// `backend/routers/mcp.py` depends on `get_uid_from_mcp_api_key`, which looks the bearer up in the
/// `mcp_api_keys` collection after an explicit `startswith("omi_mcp_")` — a session token is not
/// found there, so it comes back `401 {"detail":"Invalid API Key"}`. Reading these three endpoints
/// through `OmiAPI`, which attaches exactly that session token, therefore failed all three sources
/// on every tick and rendered a signed-in account as an empty one.
///
/// So this reads with the `omi_mcp_…` key `MCPKeyProvisioner` writes for this Mac, and a rejected
/// key is repaired rather than reported: **a 401 buys exactly one re-provision and one retry**, per
/// source, per read. Not more, because a key the account has just issued and immediately rejected is
/// the account's answer and not a stale file; not silently, because a key that cannot be replaced
/// makes the feed unreachable — never empty.
///
/// ## The other refusal: 429
///
/// A rate-limited account is neither of those things. The key is good, the request is right, and the
/// account is simply asking us to wait — so it gets its own answer (`.rateLimited`) rather than being
/// folded into "nobody answered", and it gets a small, jittered retry ladder here rather than being
/// handed straight back. The ladder is short on purpose and the waiting is somebody else's job: see
/// `rateLimitRetries` below, and `ActivityStore`'s re-read, which is measured in minutes.
///
/// ## What `reachable` means here
///
/// It answers *"did the account answer at all"*, not *"did every source answer"*. If memories 500 and
/// conversations come back, the feed carries the conversations and stays reachable: the spine can
/// truthfully render what it holds, and the alternative — flipping the whole feed to unreachable —
/// would hide rows we actually have behind a "nobody answered" message that is false. It goes false
/// only when *no* source answered, which is also the exact shape of every reason the account is
/// genuinely unavailable: Airgap Mode, signed out, no route, an outage. Those fail all three
/// together, so the distinction the field exists for survives.
///
/// ## What the endpoints actually give us
///
/// These are `GET /v1/mcp/{conversations,memories,action-items}`, whose FastAPI `response_model`s
/// (`SimpleConversation`, `CleanerMemory`, `SimpleActionItem`) *filter* the documents behind them —
/// a field absent from the model never reaches the wire even when Firestore holds it. Two
/// consequences shape the mapping below and neither is a guess:
///
/// - **`SimpleStructured` carries `title`, `overview` and `category` — no `emoji`.** The seam wants
///   the emoji the account chose; this route does not send it. It is decoded anyway (free, and the
///   day the response model gains it this file needs no change) and otherwise falls back to `🧠`,
///   which is the backend's own default for `ConversationStructureExtraction.emoji`.
/// - **`CleanerMemory` carries no timestamp at all** — `id`, `content`, `category` and a set of
///   optional policy flags. `at` is therefore synthesised; see `WireMemory`.
struct OmiActivityFeed: ActivityAccountReading, ActivityAccountDiagnosing {

    // Everything that reaches off this file, as replaceable closures with the production wiring as
    // their defaults — the pattern `ScreenActivityUploader` established. It is what lets the airgap
    // guard be *proved* rather than asserted: a fetcher that fails the test if it is ever called is
    // the only way to show that a suppressed read sends nothing.

    private let isAirgapped: @Sendable () -> Bool
    private let isSignedIn: @Sendable () async -> Bool
    /// The bearer for the next attempt. Called with `nil` to ask for the current key, and with a key
    /// the backend has just rejected to ask for its replacement — a different string means try
    /// again, `nil` or the same string means there is nothing left to try.
    private let credential: @Sendable (String?) async -> String?
    private let fetchConversations: @Sendable (String, [String: String]) async throws -> [WireConversation]
    private let fetchMemories: @Sendable (String, [String: String]) async throws -> [WireMemory]
    private let fetchTasks: @Sendable (String, [String: String]) async throws -> [WireActionItem]
    private let now: @Sendable () -> Double
    /// How the retry ladder waits. Injected for the same reason the fetchers are: a test that had to
    /// spend the real backoff to prove there was one would be a test nobody runs.
    private let sleep: @Sendable (TimeInterval) async -> Void
    /// Why the last read found nothing to read, for the empty copy. A reference so the diagnosis
    /// survives this struct being copied into the task that reads with it.
    private let diagnosis = AccountDiagnosis()

    init(
        isAirgapped: @escaping @Sendable () -> Bool = { NetworkEgress.isSuppressed(.omiAPI) },
        isSignedIn: @escaping @Sendable () async -> Bool = { await MainActor.run { OmiAuth.shared.isSignedIn } },
        credential: @escaping @Sendable (String?) async -> String? = { rejected in
            guard let rejected else { return await MCPKeyProvisioner.shared.key() }
            return await MCPKeyProvisioner.shared.key(replacing: rejected)
        },
        fetchConversations: @escaping @Sendable (String, [String: String]) async throws -> [WireConversation] = {
            try await OmiMCPRead.get("v1/mcp/conversations", key: $0, query: $1, as: [WireConversation].self)
        },
        fetchMemories: @escaping @Sendable (String, [String: String]) async throws -> [WireMemory] = {
            try await OmiMCPRead.get("v1/mcp/memories", key: $0, query: $1, as: [WireMemory].self)
        },
        fetchTasks: @escaping @Sendable (String, [String: String]) async throws -> [WireActionItem] = {
            try await OmiMCPRead.get("v1/mcp/action-items", key: $0, query: $1, as: [WireActionItem].self)
        },
        now: @escaping @Sendable () -> Double = { Date().timeIntervalSince1970 },
        sleep: @escaping @Sendable (TimeInterval) async -> Void = { try? await Task.sleep(for: .seconds($0)) }
    ) {
        self.isAirgapped = isAirgapped
        self.isSignedIn = isSignedIn
        self.credential = credential
        self.fetchConversations = fetchConversations
        self.fetchMemories = fetchMemories
        self.fetchTasks = fetchTasks
        self.now = now
        self.sleep = sleep
    }

    func unreachableReason() async -> ActivityAccountUnreachableReason? {
        await diagnosis.reason()
    }

    /// One page per source. The spine shows a window of a day, not an account export, and every one
    /// of these endpoints will happily serve hundreds of rows to a caller that asks for them.
    private static let maxPerSource = 200

    private static let category = "activity"

    // MARK: - Reading

    func read(since: Double?, until: Double?, limit: Int) async -> ActivityAccountFeed {
        // Before any URL exists. `OmiMCPRead` enforces Airgap Mode too — that is the guard that
        // counts — but reaching it means three refusals and three suppression records for one read
        // of a switch that only the user can flip.
        guard !isAirgapped() else {
            // `.degraded` rather than `.dropped`: nothing is lost, the account is simply not being
            // asked, and the same read succeeds when the switch goes off.
            NetworkEgress.recordSuppression(.omiAPI, outcome: .degraded)
            await diagnosis.record(.airgapped)
            return .unreachable
        }
        guard await isSignedIn() else {
            await diagnosis.record(.signedOut)
            return .unreachable
        }
        // One key for all three sources, fetched once. Asking per source would race three
        // provisioning runs on a Mac that has never had a key.
        guard let key = await credential(nil) else {
            // Signed in, not airgapped, and still no credential: the mint failed or has not been
            // able to run. It is the same thing to the reader as a rejected key — the account is
            // there and this Mac cannot open it — so it says the same thing.
            await diagnosis.record(.keyUnavailable)
            ContextLog.error("No Omi MCP key for this Mac; the account cannot be read", Self.category)
            return .unreachable
        }

        let bounded = min(max(limit, 1), Self.maxPerSource)
        // Where a row with no usable timestamp of its own is placed. The upper edge of the window
        // the caller asked about, because every source here is read newest-first: it says "this is
        // among the most recent things the account holds", which is the only claim we can support.
        let placement = until ?? now()

        async let conversationRows = attempt(
            "conversations", key, fetchConversations,
            Self.conversationQuery(since: since, until: until, limit: bounded))
        async let memoryRows = attempt(
            "memories", key, fetchMemories, Self.memoryQuery(since: since, limit: bounded))
        // Tasks are read unwindowed on purpose — the seam says so, and it is right: an open
        // commitment matters today whenever it was written. The endpoint's only date filters are
        // `due_start_date`/`due_end_date`, which bound the *due* date rather than when the item
        // appeared, so windowing here would drop undated commitments entirely.
        async let taskRows = attempt("action-items", key, fetchTasks, ["limit": String(bounded)])

        let conversations = await conversationRows
        let memories = await memoryRows
        let tasks = await taskRows

        guard conversations.rows != nil || memories.rows != nil || tasks.rows != nil else {
            // **Which failure it was decides what the user is told.** A rejection the key could not
            // survive means "reconnect"; a rate limit means "this will clear on its own"; anything
            // else means "I couldn't reach it". All three are far from "you have no memories", which
            // is what an unreasoned empty feed renders as.
            let failures = [conversations.failure, memories.failure, tasks.failure].compactMap { $0 }
            await diagnosis.record(Self.reason(whenNothingAnswered: failures))
            return .unreachable
        }
        await diagnosis.record(nil)

        let feed = ActivityAccountFeed(
            conversations: (conversations.rows ?? []).compactMap { $0.activity(placedAt: placement) },
            memories: (memories.rows ?? []).compactMap { $0.activity(placedAt: placement) },
            tasks: (tasks.rows ?? []).compactMap { $0.activity(placedAt: placement) },
            reachable: true)
        // Counts only. Titles, memory content and task text are the user's own words and none of
        // them belong in a log line.
        ContextLog.info(
            "Account feed: \(feed.conversations.count) conversations, \(feed.memories.count) memories, "
                + "\(feed.tasks.count) tasks", Self.category)
        return feed
    }

    /// What one source came back with: its rows, or `nil` for "this source did not answer" so the
    /// caller can tell a missing source from an empty one — plus, when it did not, the shape of
    /// failure that decides what the reader is told and whether asking again is worth anything.
    private struct SourceOutcome<Row: Sendable>: Sendable {
        let rows: [Row]?
        let failure: SourceFailure?
    }

    /// Why a source came back with nothing, in the only three shapes anything downstream acts on.
    private enum SourceFailure: Sendable, Equatable {
        /// A 401 no fresh key could repair. The account refused this Mac, and only the user can fix it.
        case rejected
        /// A 429 that outlived the retry ladder below. Nothing is wrong; the account wants us to wait.
        case rateLimited
        /// Everything else: a timeout, a 5xx, a response we could not read, a 4xx that is ours.
        case other
    }

    /// Which reason the reader is told when *no* source answered.
    ///
    /// Ordered by what the reader can do about it. A rejection is the one they can act on
    /// (reconnect), so it wins even if another source was merely rate limited; a rate limit is the
    /// one that clears on its own and is worth saying so; everything else is "nobody answered".
    private static func reason(whenNothingAnswered failures: [SourceFailure])
        -> ActivityAccountUnreachableReason
    {
        if failures.contains(.rejected) { return .keyRejected }
        if failures.contains(.rateLimited) { return .rateLimited }
        return .noAnswer
    }

    // MARK: - One source

    /// How many extra attempts one source spends on a 429, on top of the first.
    ///
    /// **The ceiling is two, and hammering is the reason it is not more.** Three sources read in
    /// parallel, so one read already costs the account three requests; at two retries each the worst
    /// case is nine, spread over roughly three seconds, and then the read stops and *reports* the
    /// rate limit instead of asking again. A client that answers a 429 by trying harder is how a
    /// limit stays tripped — which is exactly the state this file was found in. Waiting a rate limit
    /// out is `ActivityStore`'s re-read, whose schedule is measured in minutes.
    private static let rateLimitRetries = 2
    private static let rateLimitBaseDelay: TimeInterval = 1
    private static let rateLimitDelayCap: TimeInterval = 5

    /// Runs one source, spending at most one re-provisioned key on a 401 and at most
    /// `rateLimitRetries` waits on a 429.
    ///
    /// Both retries are deliberately here and not inside the HTTP helper. A 401 from `/v1/mcp/*` is
    /// not a transport problem to be backed off — it is a statement that this Mac's key is no longer
    /// the account's, and the only thing that can answer it is the half of the product that can mint
    /// one. Bounded at one attempt because `MCPKeyProvisioner` is where "should another key exist at
    /// all" is decided; a second retry here would just ask it the same question twice. A 429 is the
    /// opposite kind of refusal — the credential is fine and time is the whole repair — so it is
    /// waited on rather than re-credentialled, and the wait is bounded for the reason above.
    private func attempt<Row: Sendable>(
        _ source: String,
        _ key: String,
        _ fetch: @escaping @Sendable (String, [String: String]) async throws -> [Row],
        _ query: [String: String]
    ) async -> SourceOutcome<Row> {
        var key = key
        var didReprovision = false
        var waits = 0

        while true {
            do {
                let rows = try await fetch(key, query)
                if didReprovision {
                    ContextLog.info("Account \(source) recovered on a freshly provisioned key", Self.category)
                }
                return SourceOutcome(rows: rows, failure: nil)
            } catch {
                switch Self.classify(error) {
                case .rejectedKey:
                    // A second 401 is the account's answer, not a prompt to mint again.
                    guard !didReprovision, let replacement = await credential(key), replacement != key else {
                        ContextLog.error(
                            "Account \(source) unavailable: the key was rejected and not replaced", Self.category)
                        return SourceOutcome(rows: nil, failure: .rejected)
                    }
                    didReprovision = true
                    key = replacement

                case .rateLimited(let retryAfter):
                    guard waits < Self.rateLimitRetries,
                        let delay = Self.rateLimitDelay(attempt: waits + 1, retryAfter: retryAfter)
                    else {
                        ContextLog.error("Account \(source) unavailable: rate limited", Self.category)
                        return SourceOutcome(rows: nil, failure: .rateLimited)
                    }
                    waits += 1
                    ContextLog.info(
                        "Account \(source) rate limited; retry \(waits)/\(Self.rateLimitRetries) in "
                            + "\(String(format: "%.2f", delay))s", Self.category)
                    await sleep(delay)

                case .other:
                    let after = didReprovision ? " after re-provisioning" : ""
                    ContextLog.error(
                        "Account \(source) unavailable\(after): \(Self.reason(for: error))", Self.category)
                    return SourceOutcome(rows: nil, failure: .other)
                }
            }
        }
    }

    /// What a thrown error means to the loop above.
    ///
    /// **The branch is on the status line and nothing else**, which is not an accident. A 429 on this
    /// endpoint family comes back from an edge proxy as an HTML error page rather than as the API's
    /// own `{"detail": …}`, so anything that read the *body* to decide what had happened would report
    /// a rate limit as an unreadable response and retry none of it. `OmiMCPRead` reads the status
    /// first and never decodes a failed response, and this is the other half of that promise.
    ///
    /// 403 is a key that authenticated and lacks the access, which minting another copy of the same
    /// thing cannot fix, so it is not a rejection.
    private static func classify(_ error: Error) -> SourceError {
        if let limited = error as? OmiMCPRateLimited { return .rateLimited(retryAfter: limited.retryAfter) }
        guard let apiError = error as? OmiAPIError else { return .other }
        switch apiError {
        case .http(401, _): return .rejectedKey
        // Any other thrower of a plain 429 — a caller with its own client, a test's fetcher — is
        // still a rate limit; it just came without the server's own `Retry-After`.
        case .http(429, _): return .rateLimited(retryAfter: nil)
        default: return .other
        }
    }

    private enum SourceError {
        case rejectedKey
        case rateLimited(retryAfter: TimeInterval?)
        case other
    }

    /// Seconds to wait before re-asking a rate-limited source, or nil to stop now.
    ///
    /// `Retry-After` wins when the server sent one — it knows when it will be ready and we do not.
    /// When it asks for longer than the cap we stop rather than hold the panel's read open for it:
    /// a wait measured in minutes belongs to `ActivityStore`'s re-read, not to a request in flight.
    /// Otherwise 1s then 2s with equal jitter (half fixed, half random), for the reason `OmiAPI`
    /// documents about the same policy: this app's callers are timer-driven, so an unjittered
    /// backoff brings everything that failed together back together, forever.
    private static func rateLimitDelay(attempt: Int, retryAfter: TimeInterval?) -> TimeInterval? {
        if let retryAfter {
            guard retryAfter <= rateLimitDelayCap else { return nil }
            return max(0, retryAfter)
        }
        let exponential = min(rateLimitDelayCap, rateLimitBaseDelay * pow(2, Double(attempt - 1)))
        return exponential / 2 + Double.random(in: 0...(exponential / 2))
    }

    /// A coarse label, deliberately not the error's own message: `OmiAPIError.http` carries a
    /// server-supplied detail string and `.decoding` names a field, and neither is worth the risk of
    /// putting a fragment of someone's data in the log for a line that only ever asks "why not".
    private static func reason(for error: Error) -> String {
        if error is OmiMCPRateLimited { return "rate limited" }
        guard let apiError = error as? OmiAPIError else { return "failed" }
        switch apiError {
        case .notSignedIn: return "signed out"
        case .airgapMode: return "Airgap Mode"
        case .http(let status, _): return "HTTP \(status)"
        case .decoding: return "unreadable response"
        case .transport: return "no answer"
        }
    }

    // MARK: - Queries

    /// `start_date`/`end_date` are FastAPI `Optional[datetime]` parameters, so the window is applied
    /// server-side and the client never pages a day it will not show.
    private static func conversationQuery(since: Double?, until: Double?, limit: Int) -> [String: String] {
        var query = ["limit": String(limit)]
        if let since { query["start_date"] = iso(since) }
        if let until { query["end_date"] = iso(until) }
        return query
    }

    /// Memories can only be bounded below, and only by *update* time: `updated_after` is the single
    /// date parameter `GET /v1/mcp/memories` accepts. There is no upper bound and, because the rows
    /// come back without timestamps at all (see `WireMemory`), **no client-side filter is possible
    /// either** — a memory cannot be excluded from a window it cannot be placed in. So a windowed
    /// read returns the newest memories touched since `since`, and an unwindowed one the newest
    /// memories outright. `sort` is pinned rather than left to the endpoint's default so the order
    /// this file relies on is stated where it is relied upon.
    private static func memoryQuery(since: Double?, limit: Int) -> [String: String] {
        var query = ["limit": String(limit), "sort": "created_desc"]
        if let since { query["updated_after"] = iso(since) }
        return query
    }

    /// Always UTC with an explicit `Z`. A naive datetime string would be read by the backend in
    /// whatever zone it decided to assume, which is how a window silently slides by hours.
    private static func iso(_ epochSeconds: Double) -> String {
        outboundISO.string(from: Date(timeIntervalSince1970: epochSeconds))
    }

    private static nonisolated(unsafe) let outboundISO: ISO8601DateFormatter = {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime]
        formatter.timeZone = TimeZone(secondsFromGMT: 0)
        return formatter
    }()
}

// MARK: - Why the account did not answer

/// The last read's diagnosis, held across reads so the empty copy can be resolved after the fact.
///
/// An actor rather than a lock because every writer and the one reader are already `async`, and it
/// keeps the whole of this file free of shared mutable state that Swift cannot see.
private actor AccountDiagnosis {
    private var last: ActivityAccountUnreachableReason?

    func record(_ reason: ActivityAccountUnreachableReason?) {
        last = reason
    }

    func reason() -> ActivityAccountUnreachableReason? { last }
}

// MARK: - Reading /v1/mcp/*

/// The account said 429, and how long it asked us to wait if it said.
///
/// Its own type rather than `OmiAPIError.http(429, …)` because that case's second field is a
/// *server message*, and there is nowhere in it to put a delay that the client is meant to act on
/// rather than show. Keeping the wait attached to the refusal is what lets the retry ladder honour
/// `Retry-After` instead of inventing a number the account never asked for.
struct OmiMCPRateLimited: Error, Sendable, Equatable {
    /// Seconds the server asked for, when it sent a `Retry-After` at all.
    let retryAfter: TimeInterval?
}

/// A GET against `/v1/mcp/*` carrying an `omi_mcp_…` key.
///
/// **Separate from `OmiAPI` because the credential is.** `OmiAPI` exists to attach the signed-in
/// session's Firebase ID token to everything it sends, and that token is precisely what these
/// endpoints reject; there is no shape of call into it that would carry a different bearer. So this
/// is the same pattern `MCPKeyProvisioner.retire` already uses for the one verb `OmiAPI` has no
/// place for — a request built here, with this file's own copy of the two policies that are not
/// optional: the Airgap guard, and never putting a credential or a row of the user's data in a log.
///
/// **One attempt, and the one ladder that matters lives above this.** `OmiAPI`'s backoff exists for
/// writes that must eventually land; this is a read behind a surface that asks again whenever the
/// window moves, so a 5xx costs one tick of one column rather than the seconds a retry would hold
/// the whole panel for. The single exception is 429, which is not a transport hiccup but the account
/// naming a time — and it is retried by `OmiActivityFeed.attempt`, above the fetcher seam, so the
/// policy is testable without a network.
enum OmiMCPRead {
    private static let category = "activity"

    static func get<T: Decodable>(
        _ path: String, key: String, query: [String: String], as type: T.Type
    ) async throws -> T {
        guard !NetworkEgress.isSuppressed(.omiAPI) else {
            NetworkEgress.recordSuppression(.omiAPI, outcome: .degraded)
            throw OmiAPIError.airgapMode
        }

        let normalized = OmiAPI.normalized(path)
        guard var components = URLComponents(url: OmiAPI.baseURL, resolvingAgainstBaseURL: false) else {
            throw OmiAPIError.transport("the base URL is unusable")
        }
        let base = components.path.hasSuffix("/") ? components.path : components.path + "/"
        components.path = base + normalized
        if !query.isEmpty {
            // Sorted, so the same call produces the same URL every time and a packet log is
            // comparable across ticks.
            components.queryItems = query.sorted { $0.key < $1.key }.map {
                URLQueryItem(name: $0.key, value: $0.value)
            }
        }
        guard let url = components.url else {
            throw OmiAPIError.transport("could not build a URL for \(normalized)")
        }

        var request = URLRequest(url: url)
        request.httpMethod = "GET"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue("Bearer \(key)", forHTTPHeaderField: "Authorization")
        request.setValue("macos", forHTTPHeaderField: "X-App-Platform")
        request.setValue(OmiAPI.deviceIdHash, forHTTPHeaderField: "X-Device-Id-Hash")

        let data: Data
        let response: HTTPURLResponse
        do {
            let (body, urlResponse) = try await session.data(for: request)
            guard let http = urlResponse as? HTTPURLResponse else {
                throw OmiAPIError.transport("the server's reply was not HTTP")
            }
            data = body
            response = http
        } catch let error as OmiAPIError {
            throw error
        } catch is CancellationError {
            throw CancellationError()
        } catch {
            // **Every request that was made leaves exactly one line.** The line below is written
            // when a reply arrives, so a request that never got one left no trace of having been
            // made at all — and a log showing `GET v1/mcp/memories → 429` with no conversations line
            // beside it reads as though conversations had not been asked for, when what actually
            // happened was a 30-second timeout on an account that was rate-limiting the other two.
            // The numeric `URLError` code says which failure it was without quoting a URL or a body.
            let code = (error as? URLError)?.errorCode
            ContextLog.error(
                "GET \(normalized) got no reply (URLError \(code.map(String.init) ?? "none"))", category)
            let reason = (error as? URLError)?.localizedDescription ?? error.localizedDescription
            throw OmiAPIError.transport(reason)
        }

        // Path and status only. The query values are the user's own window and the body is their
        // conversations; neither belongs in a log line, and nor does the bearer above.
        ContextLog.info("GET \(normalized) → \(response.statusCode)", category)
        guard (200...299).contains(response.statusCode) else {
            // **Judged on the status line, before anything looks at the body** — which is what keeps
            // a 429 classified as a 429. These come back from an edge proxy as an HTML error page
            // rather than as the API's own JSON, so a path that tried to read the body first would
            // call a rate limit an unreadable response.
            if response.statusCode == 429 {
                throw OmiMCPRateLimited(retryAfter: Self.retryAfterSeconds(response))
            }
            // No server detail carried across: the caller only ever branches on the status, and a
            // FastAPI `detail` can quote the request back.
            throw OmiAPIError.http(response.statusCode, "")
        }

        do {
            return try decoder.decode(type, from: data)
        } catch let error as DecodingError {
            throw OmiAPIError.decoding(describe(error))
        } catch {
            throw OmiAPIError.decoding("\(type) could not be read")
        }
    }

    /// `Retry-After` is either delta-seconds or an HTTP-date; both are in the wild.
    ///
    /// A second copy of the parse `OmiAPI` already does, because that one is private to a client
    /// this file deliberately does not go through — the credential is the whole reason `OmiMCPRead`
    /// exists — and a header this small is not worth widening that client's surface for.
    private static func retryAfterSeconds(_ response: HTTPURLResponse) -> TimeInterval? {
        guard
            let raw = response.value(forHTTPHeaderField: "Retry-After")?
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

    /// Names the field, never the value — which field is wrong is the whole diagnosis, and the value
    /// is the user's data.
    private static func describe(_ error: DecodingError) -> String {
        func location(_ context: DecodingError.Context) -> String {
            let path = context.codingPath.map(\.stringValue).joined(separator: ".")
            return path.isEmpty ? "the response" : path
        }
        switch error {
        case .keyNotFound(let key, let context): return "missing field \(key.stringValue) in \(location(context))"
        case .typeMismatch(let type, let context): return "\(location(context)) is not a \(type)"
        case .valueNotFound(let type, let context): return "\(location(context)) was null, expected \(type)"
        case .dataCorrupted(let context): return "\(location(context)) is malformed"
        @unknown default: return "the response did not match what I expected"
        }
    }

    private static let session: URLSession = {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.timeoutIntervalForRequest = 30
        configuration.timeoutIntervalForResource = 60
        // Responses are one person's conversations and memories. Nothing about them belongs in a
        // shared on-disk URL cache.
        configuration.urlCache = nil
        configuration.requestCachePolicy = .reloadIgnoringLocalCacheData
        return URLSession(configuration: configuration)
    }()

    /// Snake_case in, camelCase out — the same conversion `OmiAPI`'s decoder does, which is what the
    /// wire shapes below are written against. No date strategy: every timestamp here is a
    /// `WireInstant`, which reads the three shapes this API actually sends.
    private static let decoder: JSONDecoder = {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return decoder
    }()
}

// MARK: - Wire shapes
//
// `OmiAPI`'s decoder converts snake_case to camelCase, so the wire's `started_at` is matched by
// `startedAt` here. Every field is optional and no field is a `Date`: these are the shapes an
// account's whole history arrives in, and a single row with a null title or a timestamp the shared
// decoder dislikes must never cost the user the page it was on. Same reasoning as
// `MCPKeyProvisioner`'s wire shapes, for the same reason.

/// `GET /v1/mcp/conversations` → `SimpleConversation`: `id`, `started_at`, `finished_at`,
/// `structured`, `language`, `apps_results`. Only the first four are read.
struct WireConversation: Decodable, Sendable {
    let id: String?
    let startedAt: WireInstant?
    let finishedAt: WireInstant?
    let structured: WireStructured?

    /// `SimpleStructured` is `title`, `overview`, `category`. `emoji` is decoded on spec — the
    /// conversation document has one, this response model does not expose it.
    struct WireStructured: Decodable, Sendable {
        let title: String?
        let overview: String?
        let emoji: String?
    }

    /// The account's own default when the extractor produced no emoji, kept identical so a
    /// conversation looks the same here as it does everywhere else in Omi.
    static let defaultEmoji = "🧠"

    /// nil for a row with no id: it cannot be identified, so it cannot be diffed, selected or
    /// scrolled to, and `Identifiable` would collide every one of them onto the same row.
    func activity(placedAt fallback: Double) -> ActivityAccountConversation? {
        guard let id, !id.isEmpty else { return nil }
        let started = startedAt?.seconds
        let finished = finishedAt?.seconds
        let begins = started ?? finished ?? fallback
        let overview = WireText.presentable(structured?.overview)
        return ActivityAccountConversation(
            id: id,
            // The overview is shown directly under the title, so borrowing it for a missing title
            // would fill the row with the same sentence twice and still say nothing new.
            title: WireText.presentable(structured?.title) ?? "Untitled conversation",
            emoji: WireText.presentable(structured?.emoji) ?? Self.defaultEmoji,
            startedAt: begins,
            // A finish before the start is not orderable; the row is drawn from these two.
            finishedAt: max(finished ?? begins, begins),
            overview: overview)
    }
}

/// `GET /v1/mcp/memories` → `CleanerMemory`: `id`, `content`, `category`, and optional policy flags
/// (`reviewed`, `manually_added`, `memory_default_memory`, …). **There is no timestamp in that
/// model**, so `created_at`/`updated_at` are decoded speculatively — they cost nothing, they are what
/// the underlying documents hold, and they are what this row wants — and when neither arrives the
/// memory is placed at the window's upper edge.
///
/// That placement is a placement, not a claim: the endpoint returns newest-created first and the
/// mapped array preserves that order, so the sequence is true even where the instants are uniform.
struct WireMemory: Decodable, Sendable {
    let id: String?
    let content: String?
    let createdAt: WireInstant?
    let updatedAt: WireInstant?

    func activity(placedAt fallback: Double) -> ActivityAccountMemory? {
        guard let id, !id.isEmpty, let content = WireText.presentable(content) else { return nil }
        return ActivityAccountMemory(
            id: id,
            content: content,
            at: createdAt?.seconds ?? updatedAt?.seconds ?? fallback)
    }
}

/// `GET /v1/mcp/action-items` → `SimpleActionItem`: `id`, `description`, `completed`, `created_at`,
/// `due_at`, `completed_at`, `conversation_id`.
struct WireActionItem: Decodable, Sendable {
    let id: String?
    let text: String?
    let completed: Bool?
    let createdAt: WireInstant?
    let dueAt: WireInstant?
    let completedAt: WireInstant?

    // `description` is the wire name; `text` is the seam's. Spelled without an underscore, so the
    // decoder's snake_case conversion leaves it alone and this raw value is what actually arrives.
    private enum CodingKeys: String, CodingKey {
        case id
        case text = "description"
        case completed
        case createdAt
        case dueAt
        case completedAt
    }

    func activity(placedAt fallback: Double) -> ActivityAccountTask? {
        guard let id, !id.isEmpty, let text = WireText.presentable(text) else { return nil }
        return ActivityAccountTask(
            id: id,
            text: text,
            completed: completed ?? false,
            // Due date first: a commitment belongs on the day it is owed, and that is the day the
            // spine is being asked about. Falling back through creation to completion so that a
            // task with only one of the three is still placeable.
            at: dueAt?.seconds ?? createdAt?.seconds ?? completedAt?.seconds ?? fallback)
    }
}

enum WireText {
    /// Trimmed text, or nil when there is nothing to show. The backend defaults several of these
    /// fields to `''` rather than omitting them, and an empty string rendered into a row is the
    /// "never an empty row" failure wearing a value.
    static func presentable(_ raw: String?) -> String? {
        guard let trimmed = raw?.trimmingCharacters(in: .whitespacesAndNewlines), !trimmed.isEmpty else {
            return nil
        }
        return trimmed
    }
}

/// A timestamp as this API actually sends them, reduced to Unix epoch seconds.
///
/// Three shapes are in the wild across `/v1/mcp/*` and this type absorbs all of them rather than
/// letting any one of them throw:
///
/// - ISO-8601 with an offset — what Pydantic serialises a tz-aware `datetime` to.
/// - ISO-8601 with **no zone at all**. Tz-naive datetimes reach these documents (the backend has
///   had to coerce them to UTC on its own side; see the action-item date fix), and `Foundation`
///   simply refuses to parse one. Refusing is the safe half; guessing *local* time would be the
///   dangerous half, silently moving an instant by hours, so a zoneless string is read as UTC —
///   the same reading the backend gives it.
/// - A bare number of seconds, which is how the sibling screen-activity rows carry their time.
///
/// Anything else becomes "no timestamp", never a decoding failure: one unreadable date must not
/// cost the page it arrived on.
struct WireInstant: Decodable, Sendable, Equatable {
    let seconds: Double?

    init(seconds: Double?) {
        self.seconds = seconds
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        if let text = try? container.decode(String.self) {
            seconds = Self.parse(text)
        } else if let number = try? container.decode(Double.self) {
            seconds = number
        } else {
            seconds = nil
        }
    }

    static func parse(_ raw: String) -> Double? {
        let trimmed = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return nil }
        // `str(datetime)` — which parts of the backend still use — separates date and time with a
        // space, and `ISO8601DateFormatter` requires the `T`.
        var text = trimmed.replacingOccurrences(of: " ", with: "T")
        text = truncatingFraction(text)
        if !hasTimeZone(text) { text += "Z" }
        if let date = fractional.date(from: text) { return date.timeIntervalSince1970 }
        if let date = standard.date(from: text) { return date.timeIntervalSince1970 }
        return nil
    }

    /// Firestore and Pydantic emit microseconds. `ISO8601DateFormatter` is only dependable at
    /// milliseconds, and a rejected date here would be a row placed at the wrong instant — the
    /// sub-millisecond remainder is worth nothing to a timeline that draws in minutes.
    private static func truncatingFraction(_ text: String) -> String {
        guard let dot = text.firstIndex(of: ".") else { return text }
        var end = text.index(after: dot)
        var digits = 0
        while end < text.endIndex, text[end].isNumber {
            digits += 1
            end = text.index(after: end)
        }
        guard digits > 3 else { return text }
        let keep = text.index(dot, offsetBy: 4)
        return String(text[..<keep]) + String(text[end...])
    }

    /// A zone designator can only appear after the time, which is why the date's own hyphens do not
    /// count as one.
    private static func hasTimeZone(_ text: String) -> Bool {
        guard let separator = text.firstIndex(of: "T") else { return false }
        let time = text[text.index(after: separator)...]
        return time.contains("Z") || time.contains("z") || time.contains("+") || time.contains("-")
    }

    private static nonisolated(unsafe) let fractional: ISO8601DateFormatter = {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return formatter
    }()

    private static nonisolated(unsafe) let standard = ISO8601DateFormatter()
}
