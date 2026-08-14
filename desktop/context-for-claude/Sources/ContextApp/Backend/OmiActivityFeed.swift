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
/// ## These are the endpoints the shipping Omi clients read, on the credential they read them with
///
/// `GET /v1/conversations`, `GET /v3/memories` and `GET /v1/action-items`, carrying the signed-in
/// session's Firebase ID token — which is to say, exactly what the macOS app and the Flutter app
/// ask for and exactly how they ask for it. That is not a preference; the alternative was measurably
/// worse in three separate ways, and this file used to be written against it:
///
/// - **`/v1/mcp/*` is rate limited and this surface is not the caller it was designed for.** Every
///   route authenticated by `get_uid_from_mcp_api_key` spends the `mcp:read` policy inside the auth
///   dependency itself — 300 requests an hour, **fail-closed** — before the handler is reached. That
///   budget exists for an agent asking occasional questions, not for a panel that re-reads three
///   sources whenever its window moves, and the panel duly spent it: the whole account rendered as
///   429 for hours at a time. `get_current_user_uid` performs no rate-limit check at all, and none
///   of the three routes above opts into one, so the surface the user actually looks at is no longer
///   competing with the MCP server for the same hourly allowance.
/// - **The MCP response models are strictly poorer.** `SimpleStructured` is `title`, `overview`,
///   `category` and carries **no `emoji`** — the row's emoji had to be defaulted to `🧠` for every
///   conversation, including the ones the account had chosen an emoji for. `Conversation.structured`
///   is a full `Structured`, whose `emoji` is a real field. `CleanerMemory` carries **no timestamp
///   whatsoever**, so every memory had to be dropped onto the window's upper edge and none of them
///   could be placed on the day it happened, or filtered out of a window at all. `MemoryDB` declares
///   `created_at` and `updated_at` as required, and no exposure mode strips them.
/// - **It needed a second credential to exist.** The `omi_mcp_…` key is minted for the MCP server,
///   which is a separate process with no session of its own; the app has never needed it to read its
///   own user's account. Reading through it meant this file could fail — and did — in ways the app
///   was otherwise immune to: a key that had been rotated out from under it, a key that had never
///   been minted, a mint that could not run. All of that is gone. `OmiAPI` attaches the session the
///   user is already signed in with.
///
/// ## Retries live in `OmiAPI`, not here
///
/// There is no ladder in this file. `OmiAPI` already spends exactly one forced token refresh on a
/// 401 and up to three jittered retries on a 429 or 5xx, and it does that for every caller in the
/// app rather than once per feature. What reaches the `catch` below has therefore already been
/// retried as much as it is going to be, which is why each failure here is final and is classified
/// rather than re-attempted.
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
struct OmiActivityFeed: ActivityAccountReading, ActivityAccountDiagnosing {

    // Everything that reaches off this file, as replaceable closures with the production wiring as
    // their defaults — the pattern `ScreenActivityUploader` established. It is what lets the airgap
    // guard be *proved* rather than asserted: a fetcher that fails the test if it is ever called is
    // the only way to show that a suppressed read sends nothing.

    private let isAirgapped: @Sendable () -> Bool
    private let isSignedIn: @Sendable () async -> Bool
    private let fetchConversations: @Sendable ([String: String]) async throws -> [WireConversation]
    private let fetchMemories: @Sendable ([String: String]) async throws -> [WireMemory]
    private let fetchTasks: @Sendable ([String: String]) async throws -> WireActionItemPage
    private let now: @Sendable () -> Double
    /// Why the last read found nothing to read, for the empty copy. A reference so the diagnosis
    /// survives this struct being copied into the task that reads with it.
    private let diagnosis = AccountDiagnosis()

    init(
        isAirgapped: @escaping @Sendable () -> Bool = { NetworkEgress.isSuppressed(.omiAPI) },
        isSignedIn: @escaping @Sendable () async -> Bool = { await MainActor.run { OmiAuth.shared.isSignedIn } },
        fetchConversations: @escaping @Sendable ([String: String]) async throws -> [WireConversation] = {
            try await OmiAPI.shared.get("v1/conversations", query: $0, as: [WireConversation].self)
        },
        fetchMemories: @escaping @Sendable ([String: String]) async throws -> [WireMemory] = {
            try await OmiAPI.shared.get("v3/memories", query: $0, as: [WireMemory].self)
        },
        fetchTasks: @escaping @Sendable ([String: String]) async throws -> WireActionItemPage = {
            try await OmiAPI.shared.get("v1/action-items", query: $0, as: WireActionItemPage.self)
        },
        now: @escaping @Sendable () -> Double = { Date().timeIntervalSince1970 }
    ) {
        self.isAirgapped = isAirgapped
        self.isSignedIn = isSignedIn
        self.fetchConversations = fetchConversations
        self.fetchMemories = fetchMemories
        self.fetchTasks = fetchTasks
        self.now = now
    }

    func unreachableReason() async -> ActivityAccountUnreachableReason? {
        await diagnosis.reason()
    }

    /// One page per source. The spine shows a window of a day, not an account export, and every one
    /// of these endpoints will happily serve hundreds of rows to a caller that asks for them — the
    /// server-side ceilings are 1000, 500 and 500 respectively, all far above anything this panel
    /// should be pulling to draw one window.
    ///
    /// Not private, because `ActivityAccountCache` bounds itself by the same number: a cache of the
    /// last answer that could hold more rows than an answer is allowed to contain would grow past
    /// the thing it is a copy of, one 503 at a time.
    static let maxPerSource = 200

    private static let category = "activity"

    // MARK: - Reading

    func read(since: Double?, until: Double?, limit: Int) async -> ActivityAccountFeed {
        // Before any URL exists. `OmiAPI` enforces Airgap Mode too — that is the guard that counts —
        // but reaching it means three refusals and three suppression records for one read of a
        // switch that only the user can flip.
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

        let bounded = min(max(limit, 1), Self.maxPerSource)
        // Where a row with no usable timestamp of its own is placed. The upper edge of the window
        // the caller asked about, because every source here is read newest-first: it says "this is
        // among the most recent things the account holds", which is the only claim we can support.
        let placement = until ?? now()

        async let conversationRows = attempt(
            "conversations", fetchConversations, Self.conversationQuery(limit: bounded))
        async let memoryRows = attempt("memories", fetchMemories, Self.memoryQuery(limit: bounded))
        // Tasks are read unwindowed on purpose — the seam says so, and it is right: an open
        // commitment matters today whenever it was written. The endpoint does accept `start_date`
        // and `due_start_date`, but the first bounds *creation* and the second bounds the due date,
        // and windowing by either would drop the undated commitments that matter most.
        async let taskPage = attempt("action-items", fetchTasks, ["limit": String(bounded)])

        let conversations = await conversationRows
        let memories = await memoryRows
        let tasks = await taskPage

        guard conversations.rows != nil || memories.rows != nil || tasks.rows != nil else {
            // **Which failure it was decides what the user is told.** A rejection the session could
            // not survive means "sign in again"; a rate limit means "this will clear on its own";
            // anything else means "I couldn't reach it". All three are far from "you have no
            // memories", which is what an unreasoned empty feed renders as.
            let failures = [conversations.failure, memories.failure, tasks.failure].compactMap { $0 }
            await diagnosis.record(Self.reason(whenNothingAnswered: failures))
            return .unreachable
        }
        await diagnosis.record(nil)

        // **Which sources answered, not merely that one did.** The rows below cannot carry the
        // distinction on their own — an endpoint that 503'd and an account that holds no memories
        // both produce an empty array — so it travels beside them. Everything downstream that has to
        // tell "said nothing" from "said nothing yet" reads this, and `ActivityAccountCaching` in
        // particular refuses to overwrite the last good answer for a source that is not in it.
        var answered: Set<ActivityAccountSource> = []
        if conversations.rows != nil { answered.insert(.conversations) }
        if memories.rows != nil { answered.insert(.memories) }
        if tasks.rows != nil { answered.insert(.tasks) }

        let feed = ActivityAccountFeed(
            conversations: (conversations.rows ?? []).compactMap { $0.activity(placedAt: placement) },
            memories: (memories.rows ?? []).compactMap { $0.activity(placedAt: placement) },
            tasks: (tasks.rows?.actionItems ?? []).compactMap { $0.activity(placedAt: placement) },
            answered: answered)
        // Counts only. Titles, memory content and task text are the user's own words and none of
        // them belong in a log line.
        ContextLog.info(
            "Account feed: \(feed.conversations.count) conversations, \(feed.memories.count) memories, "
                + "\(feed.tasks.count) tasks", Self.category)
        return feed
    }

    /// What one source came back with: its rows, or `nil` for "this source did not answer" so the
    /// caller can tell a missing source from an empty one — plus, when it did not, the shape of
    /// failure that decides what the reader is told.
    private struct SourceOutcome<Row: Sendable>: Sendable {
        let rows: Row?
        let failure: SourceFailure?
    }

    /// Why a source came back with nothing, in the only three shapes anything downstream acts on.
    private enum SourceFailure: Sendable, Equatable {
        /// A 401 that survived `OmiAPI`'s one forced token refresh. The account refused this Mac's
        /// session, and only the user can fix it.
        case rejected
        /// A 429 that outlived `OmiAPI`'s retries. Nothing is wrong; the account wants us to wait.
        case rateLimited
        /// Everything else: a timeout, a 5xx, a response we could not read, a 4xx that is ours.
        case other
    }

    /// Which reason the reader is told when *no* source answered.
    ///
    /// Ordered by what the reader can do about it. A rejection is the one they can act on (sign in
    /// again), so it wins even if another source was merely rate limited; a rate limit is the one
    /// that clears on its own and is worth saying so; everything else is "nobody answered".
    ///
    /// `.keyRejected` is the seam's name for the first of those and it now names a rejected
    /// *session* rather than a rejected key — the credential this file reads with changed, the thing
    /// the reader is told did not. The copy that renders it has never mentioned a key: it says Omi
    /// could not authenticate this Mac and to sign out and back in, which is exactly the repair for
    /// a session the backend will not accept.
    private static func reason(whenNothingAnswered failures: [SourceFailure])
        -> ActivityAccountUnreachableReason
    {
        if failures.contains(.rejected) { return .keyRejected }
        if failures.contains(.rateLimited) { return .rateLimited }
        return .noAnswer
    }

    // MARK: - One source

    /// Runs one source. One attempt, because by the time anything throws out of `OmiAPI` the retrying
    /// has already happened: a 401 has cost a forced token refresh and a second try, and a 429 or a
    /// 5xx has cost up to three jittered retries. A second ladder stacked here would multiply those,
    /// and a client that answers a refusal by trying harder is how a limit stays tripped — which is
    /// the state this surface was found in.
    private func attempt<Row: Sendable>(
        _ source: String,
        _ fetch: @escaping @Sendable ([String: String]) async throws -> Row,
        _ query: [String: String]
    ) async -> SourceOutcome<Row> {
        do {
            return SourceOutcome(rows: try await fetch(query), failure: nil)
        } catch {
            let failure = Self.classify(error)
            ContextLog.error("Account \(source) unavailable: \(Self.reason(for: error))", Self.category)
            return SourceOutcome(rows: nil, failure: failure)
        }
    }

    /// What a thrown error means to the caller above — the status line and nothing else.
    ///
    /// 403 is a session that authenticated and lacks the access, which signing in again cannot fix,
    /// so it is not a rejection.
    private static func classify(_ error: Error) -> SourceFailure {
        guard let apiError = error as? OmiAPIError else { return .other }
        switch apiError {
        case .notSignedIn: return .rejected
        case .http(401, _): return .rejected
        case .http(429, _): return .rateLimited
        default: return .other
        }
    }

    /// A coarse label, deliberately not the error's own message: `OmiAPIError.http` carries a
    /// server-supplied detail string and `.decoding` names a field, and neither is worth the risk of
    /// putting a fragment of someone's data in the log for a line that only ever asks "why not".
    private static func reason(for error: Error) -> String {
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
    //
    // Shaped after the requests the shipping macOS client's own version of this screen sends, which
    // is the answer to a question it is very easy to get wrong.
    //
    // **Nothing here is windowed by date, and that is deliberate.** `read(since:until:)` carries a
    // window and these queries ignore it: every source asks for the newest page and the window is
    // applied afterwards, to the composed stream, by `ActivityComposer`. The shipping app does
    // exactly this — its spine passes a nil date range and takes the most recent page, and its
    // `Filter ›` time control is a post-composition predicate over rows already in hand.
    //
    // A date-windowed fetch reads as the more efficient design and is in fact the bug. Two reasons,
    // and the second one is fatal:
    //
    // 1. **`/v3/memories` has no date parameter to window with.** `limit`, `offset`, `cursor`,
    //    `device_scope` — that is the whole surface. So a windowed memory read can only be done in
    //    the client, over whatever rows the newest page happened to contain, which is not the same
    //    set as "the memories from that day" and never will be.
    // 2. **A memory does not belong to the day it was created.** In the shipping app a memory whose
    //    `conversation_id` names a conversation on screen is filed under *that conversation's* day,
    //    not its own timestamp. Filtering by the memory's own instant before composition throws away
    //    exactly the rows that composition would have re-seated — which is how a day full of
    //    conversations ends up showing none of the memories those conversations produced.

    /// `statuses` and `include_discarded` are sent rather than left to the server's defaults because
    /// the defaults are not what this surface wants: `include_discarded` defaults to `True`, and a
    /// discarded conversation is one the user threw away — it has no business reappearing on a
    /// timeline of their day. `sources` is deliberately *not* sent: this shows the account, and
    /// filtering to this Mac's own uploads would hide everything the phone recorded.
    private static func conversationQuery(limit: Int) -> [String: String] {
        [
            "limit": String(limit),
            "offset": "0",
            "statuses": "completed,processing",
            "include_discarded": "false",
        ]
    }

    /// `device_scope` is left alone: its default is `all`, which is what this wants, and sending
    /// `current` is what makes the backend 400 for an account without the canonical lifecycle.
    private static func memoryQuery(limit: Int) -> [String: String] {
        ["limit": String(limit), "offset": "0"]
    }
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

// MARK: - Wire shapes
//
// `OmiAPI`'s decoder converts snake_case to camelCase, so the wire's `started_at` is matched by
// `startedAt` here. Every field is optional and no field is a `Date`: these are the shapes an
// account's whole history arrives in, and a single row with a null title or a timestamp the shared
// decoder dislikes must never cost the user the page it was on. Same reasoning as
// `MCPKeyProvisioner`'s wire shapes, for the same reason.

/// `GET /v1/conversations` → `List[Conversation]`. That model carries some thirty fields; the four
/// below are the ones a row is drawn from. Locked conversations come back redacted by
/// `redact_conversations_for_list`, which strips segments, action items and app results and **keeps
/// the title, overview and emoji** — so a locked row still renders as itself here.
struct WireConversation: Decodable, Sendable {
    let id: String?
    let createdAt: WireInstant?
    let startedAt: WireInstant?
    let finishedAt: WireInstant?
    let structured: WireStructured?

    /// `Structured` — the real one, not the MCP route's three-field projection. `emoji` is a
    /// declared field here, which is the reason this endpoint is worth reading: under `/v1/mcp/*`
    /// every conversation in the panel wore the same fallback glyph.
    struct WireStructured: Decodable, Sendable {
        let title: String?
        let overview: String?
        let emoji: String?
    }

    /// nil for a row with no id: it cannot be identified, so it cannot be diffed, selected or
    /// scrolled to, and `Identifiable` would collide every one of them onto the same row.
    func activity(placedAt fallback: Double) -> ActivityAccountConversation? {
        guard let id, !id.isEmpty else { return nil }
        let started = startedAt?.seconds
        let finished = finishedAt?.seconds
        // `created_at` last, and only as a rescue: it is when the *record* was written, which for an
        // upload that arrived hours after the fact is not when the conversation happened.
        let begins = started ?? finished ?? createdAt?.seconds ?? fallback
        return ActivityAccountConversation(
            id: id,
            // Neither fallback is applied here, and that is the reference's own arrangement: an
            // absent title and an absent emoji are passed through as empty, and
            // `ActivityConversation` supplies "Untitled conversation" and `💬` in one place for both
            // halves of the spine. Substituting at this seam instead would mean a local conversation
            // and an account one with nothing to show wore different glyphs, and would make the
            // model's own fallback unreachable for every account row.
            title: WireText.presentable(structured?.title) ?? "",
            emoji: WireText.presentable(structured?.emoji) ?? "",
            startedAt: begins,
            // A finish before the start is not orderable; the row is drawn from these two.
            finishedAt: max(finished ?? begins, begins),
            overview: WireText.presentable(structured?.overview))
    }
}

/// `GET /v3/memories` → `List[MemoryDB]`, which declares `created_at` and `updated_at` as required
/// and whose serialisation contract strips neither: `MEMORY_INTERNAL_FIELDS` and
/// `CANONICAL_LIFECYCLE_FIELDS` between them drop a dozen policy fields and no timestamp. Both
/// shipping clients decode them non-optionally. They are optional here anyway, for the reason every
/// field in this file is — one malformed row must not cost the page.
struct WireMemory: Decodable, Sendable {
    let id: String?
    let content: String?
    let capturedAt: WireInstant?
    let createdAt: WireInstant?
    let updatedAt: WireInstant?
    /// `MemoryDB.conversation_id` — which conversation the extractor drew this fact out of. Declared
    /// `Optional[str]` there and stripped by nothing on the way out (`response_model=List[MemoryDB]`),
    /// so nil here means the account really did not record one: a fact the user wrote down, or one
    /// old enough to predate the field.
    let conversationId: String?

    func activity(placedAt fallback: Double) -> ActivityAccountMemory? {
        guard let id, !id.isEmpty, let content = WireText.presentable(content) else { return nil }
        return ActivityAccountMemory(
            id: id,
            content: content,
            // **`captured_at` first, and this order is not interchangeable.** It is when the thing
            // was *learned*; `created_at` is when the row was written. For anything that arrived in
            // a batch — an import, a backfill, a phone that was offline all day — those are hours or
            // days apart, and ordering by the second one files a memory on the day the server got
            // round to it rather than the day it happened. This is the same reading the shipping
            // macOS app takes for the same screen.
            at: capturedAt?.seconds ?? createdAt?.seconds ?? updatedAt?.seconds ?? fallback,
            // Empty is the same claim as absent — the backend defaults several of these to `''` —
            // and an empty id would match no conversation anyway, so it is normalised to nil here
            // rather than becoming a key the composer looks up and never finds.
            conversationID: WireText.presentable(conversationId))
    }
}

/// `GET /v1/action-items` → `ActionItemsResponse`, which is an **object** — `{action_items, has_more}`
/// — and not a bare array like the other two. `has_more` is decoded and unused: the spine reads one
/// bounded page per window by design, and a field that exists on the wire is cheaper to name than to
/// explain the absence of.
struct WireActionItemPage: Decodable, Sendable {
    let actionItems: [WireActionItem]
    let hasMore: Bool

    private enum CodingKeys: String, CodingKey {
        case actionItems
        case items
        case hasMore
    }

    /// `action_items` is what the response model declares, and `items` is what the shipping macOS
    /// client also accepts. Both are read here for the same reason it reads both: the cost is one
    /// line, and the failure it avoids is the whole page decoding to nothing.
    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        actionItems =
            try container.decodeIfPresent([WireActionItem].self, forKey: .actionItems)
            ?? container.decodeIfPresent([WireActionItem].self, forKey: .items)
            ?? []
        hasMore = try container.decodeIfPresent(Bool.self, forKey: .hasMore) ?? false
    }

    init(actionItems: [WireActionItem], hasMore: Bool = false) {
        self.actionItems = actionItems
        self.hasMore = hasMore
    }
}

/// One row of that page — `ActionItemResponse`. Its `model_config` is `extra='ignore'`, so the
/// twenty-odd fields not named here are simply not read.
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
/// Three shapes are in the wild across these routes and this type absorbs all of them rather than
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
