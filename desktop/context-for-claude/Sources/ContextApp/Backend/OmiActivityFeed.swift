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
/// ## One read is one page, and successive reads walk the account in
///
/// **A read used to be the newest page of each source and nothing else, forever.** Every source came
/// back at `maxPerSource` on a real account — the log said `200 conversations, 200 memories, 200
/// tasks` — while the shipping Omi app beside it had already paged 1,996 rows in and was still
/// going. One page is not a corpus, and a surface denominated in the account's rows cannot tell the
/// two apart from the outside.
///
/// So the reader carries a cursor (`AccountCorpus`) and **each successive `read` fetches the next
/// page of exactly one source, round-robin, and answers with everything gathered so far**. That
/// shape is deliberate and the alternatives were worse:
///
/// - **The paging cannot live in the store.** The store holds an `ActivityAccountReading`, and in
///   the app that value is `ActivityLocalMemories` wrapping this one. A per-page request travelling
///   as a new seam method would stop at that decorator, which knows nothing about pages; a per-page
///   *result* travelling back on `ActivityAccountFeed` would be dropped the moment the decorator
///   rebuilt the feed to merge this Mac's memories in. The one thing that crosses it unchanged is a
///   `read` and the rows it answers with, so that is what paging is expressed in.
/// - **One source per read, not three.** Three racing requests are right for the first read, which
///   is a screen nobody is looking at yet; they are wrong thirty times over. Round-robin keeps one
///   request in flight, which is the whole of this surface's politeness budget — see the rate-limit
///   note above for what happened the last time this panel was generous with someone's account.
/// - **Bounded twice.** A source stops when a page comes back empty (`ServerPaging`'s rule: a
///   *short* page is not the end, because these routes post-filter after Firestore's limit), when it
///   has failed `failureLimit` times in a row, or when it has spent `maximumPagesPerSource`. A
///   backend that pages forever costs a bounded number of requests, not a hot loop.
///
/// The caller drives it: `ActivityStore` reads again while the answer keeps growing and stops when
/// it does not. Nothing here schedules its own work.
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
struct OmiActivityFeed: ActivityAccountReading, ActivityAccountDiagnosing, ActivityAccountCursor {

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
    /// Every page gathered so far, and where each source's next one starts. A reference for the same
    /// reason `diagnosis` is: the store copies this struct into the task it reads with, and a cursor
    /// that reset on every copy would fetch page one for the rest of the session.
    private let corpus = AccountCorpus()

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

    /// Reopens the newest page of every source, so the next `read` asks the account for it again.
    ///
    /// **The corpus is a cursor that only ever moves forward, and that is right for hydration and
    /// wrong for coming back to a panel an hour later.** Once every source has run out of pages the
    /// reader answers `.settled` and makes no further request for the life of the window: correct,
    /// because nothing behind the cursor changes, and useless, because everything *in front* of it
    /// does. A conversation recorded since the last read lives at offset zero, which is the one
    /// offset a forward-only walk will never ask for twice.
    ///
    /// So this clears the opening flag and nothing else. The next read races the three heads exactly
    /// as a first read does, new rows are appended, rows already held are **updated in place** —
    /// which is how a title the account has since written reaches a row that was cached untitled —
    /// and each source's paging cursor is left where hydration left it, so revalidating costs three
    /// requests rather than a second walk of the account.
    ///
    /// Deliberately not a `read` of its own. The store still calls `read`, so the local-memory
    /// decorator still wraps the answer and there is one path into the feed rather than two.
    func refreshHead() async {
        await corpus.reopenHead()
    }

    /// Drops every row and every cursor. The signed-in account has changed.
    ///
    /// **This reader now outlives a sign-out and did not used to.** It was built per panel, so
    /// forgetting was what happened when the window closed and nothing had to say so. One reader for
    /// the life of the process is what makes coming back to the panel instant (`ActivitySpine`), and
    /// the price of that is exactly this: the corpus is account-scoped state, and nobody else is
    /// going to throw it away on the way out.
    func forget() async {
        await corpus.forgetEverything()
        await diagnosis.record(nil)
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

    /// How many pages of one source a reader will ever ask for.
    ///
    /// A hundred pages of two hundred rows is twenty thousand of *one* kind — several times the
    /// largest account this has been measured against, and a hard stop for a backend that pages
    /// forever. It also bounds the whole surface's appetite: three sources, one request each per
    /// page, is at most three hundred requests for the life of a window and no more.
    static let maximumPagesPerSource = 100

    /// Consecutive failures before a source stops being asked.
    ///
    /// The reference's stall limit, for the reference's reason: one page can fail for a reason the
    /// next one will not repeat, three in a row is an endpoint that is down, and asking a fourth
    /// time is how a client becomes the reason a limit stays tripped. A source that stops here is
    /// reported as *not answered*, so nothing downstream reads the rows it did manage as complete.
    static let failureLimit = 3

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

        // **A read gathers until it has something new, or until every open source has been tried
        // once.** One page is one request and that is the normal case; the loop exists for the end
        // of a source, where the page that proves it is over returns nothing. The caller's only
        // signal is whether the answer grew, so a read that reported "no growth" the moment
        // conversations ran out would stop the walk with the other two sources half-read.
        //
        // `tried` is what keeps that from becoming a retry ladder: a source that has already been
        // asked in this read is not asked again, whatever it answered. One attempt per source per
        // read, here as everywhere else in this file — `OmiAPI` has already done the retrying.
        // **Which account this read belongs to, captured before a single request leaves.** A read is
        // a network round trip and `forget()` is a keystroke, so the two overlap: without this, a
        // page fetched for the account the user has just signed out of commits into a corpus that
        // was emptied while it was in flight, and the panel repopulates with the previous account's
        // conversations. The commits below quote it and `AccountCorpus` drops the ones that no
        // longer match.
        let epoch = await corpus.epoch()

        var tried: Set<ActivityAccountSource> = []
        pages: for _ in ActivityAccountSource.allCases.indices {
            let before = await corpus.rowCount()
            switch await corpus.next(skipping: tried) {
            case .opening:
                // The opening read has asked all three already; there is nothing left to try.
                await readOpeningPage(limit: bounded, epoch: epoch)
                await corpus.headWasRead()
                break pages
            case .page(let source, let offset):
                tried.insert(source)
                await readPage(source, offset: offset, limit: bounded, epoch: epoch)
            case .settled:
                // Every source has ended, failed out, spent its budget or been asked already.
                // Nothing more is asked, and the answer is what is already held — which is what
                // makes a caller that reads once more than it needed to cost nothing.
                break pages
            }
            if await corpus.rowCount() > before { break }
        }

        let held = await corpus.held()

        guard !held.answered.isEmpty else {
            // **Which failure it was decides what the user is told.** A rejection the session could
            // not survive means "sign in again"; a rate limit means "this will clear on its own";
            // anything else means "I couldn't reach it". All three are far from "you have no
            // memories", which is what an unreasoned empty feed renders as.
            await diagnosis.record(Self.reason(whenNothingAnswered: held.failures))
            return .unreachable
        }
        await diagnosis.record(nil)

        let feed = ActivityAccountFeed(
            conversations: held.conversations.compactMap { $0.activity(placedAt: placement) },
            memories: held.memories.compactMap { $0.activity(placedAt: placement) },
            tasks: held.tasks.compactMap { $0.activity(placedAt: placement) },
            answered: held.answered,
            memoriesBeginPastHead: held.memoriesBeginPastHead)
        // Counts only. Titles, memory content and task text are the user's own words and none of
        // them belong in a log line.
        ContextLog.info(
            "Account feed: \(feed.conversations.count) conversations, \(feed.memories.count) memories, "
                + "\(feed.tasks.count) tasks", Self.category)
        return feed
    }

    /// The first read: the newest page of all three sources, raced.
    ///
    /// The three reads race here and nowhere else. This is the read the panel's first paint is
    /// blocked on, so serial reads would cost the sum of three round trips to show one screen; every
    /// page after this one lands behind a list the reader can already use, where a second request in
    /// flight buys nothing and spends someone's account.
    private func readOpeningPage(limit: Int, epoch: Int) async {
        async let conversationRows = attempt(
            "conversations", fetchConversations, Self.conversationQuery(limit: limit, offset: 0))
        async let memoryRows = attemptMemories(limit: limit, offset: 0)
        // Tasks are read unwindowed on purpose — the seam says so, and it is right: an open
        // commitment matters today whenever it was written. The endpoint does accept `start_date`
        // and `due_start_date`, but the first bounds *creation* and the second bounds the due date,
        // and windowing by either would drop the undated commitments that matter most.
        async let taskPage = attempt("action-items", fetchTasks, Self.taskQuery(limit: limit, offset: 0))

        await corpus.commit(conversations: await conversationRows, epoch: epoch)
        await corpus.commit(memories: await memoryRows, epoch: epoch)
        await corpus.commit(tasks: await taskPage, epoch: epoch)
    }

    /// One page of one source, at the offset the cursor asked for.
    private func readPage(
        _ source: ActivityAccountSource, offset: Int, limit: Int, epoch: Int
    ) async {
        switch source {
        case .conversations:
            let outcome = await attempt(
                "conversations", fetchConversations, Self.conversationQuery(limit: limit, offset: offset))
            await corpus.commit(conversations: outcome, epoch: epoch)
        case .memories:
            await corpus.commit(
                memories: await attemptMemories(limit: limit, offset: offset), epoch: epoch)
        case .tasks:
            let outcome = await attempt(
                "action-items", fetchTasks, Self.taskQuery(limit: limit, offset: offset))
            await corpus.commit(tasks: outcome, epoch: epoch)
        }
    }

    /// Reads memories, and steps past the first row when the backend cannot serve the first page.
    ///
    /// **`offset == 0` and `offset > 0` are two different implementations behind one endpoint**, and
    /// only one of them is currently working for real accounts. `GET /v3/memories` sends a zero
    /// offset to `MemoryService.read_page`, which runs a Firestore *keyset* scan; any non-HTTP error
    /// that scan raises surfaces as `503 Canonical memory unavailable`. A non-zero offset goes to
    /// `MemoryService.read`, which loads the set and slices it in Python — no keyset query at all.
    ///
    /// That is not a theory. The shipping Omi app was observed doing both within four seconds on
    /// this account: its `offset: 0` auto-refresh failed with that exact 503 at 10:26:37, and its
    /// `offset > 0` pages returned 100 rows each at 10:26:41, 10:26:52 and 10:26:57. The reason the
    /// app still looks healthy is that its refresh swallows the failure and keeps the rows it
    /// already had — a first-run client gets nothing at all, which is precisely where this surface
    /// was.
    ///
    /// So a 503 on the first page is answered by asking again from `offset: 1`. **The cost is exactly
    /// one row — the newest memory — and it is worth naming rather than hiding**: the alternative on
    /// this account today is every memory or none. No string matching on the server's message; any
    /// 503 on the first page buys the one retry, because the branch that fails is selected by the
    /// offset and nothing else, so the retry is right whatever the message says.
    ///
    /// The retry is deliberately *not* a general policy in `attempt`: conversations and action-items
    /// have no equivalent split, and stepping their offsets would silently drop a row for nothing.
    ///
    /// **Only the first page ever steps, and every later page is asked for plainly.** The branch that
    /// fails is selected by `offset == 0` and nothing else, so a page at offset 400 is already on the
    /// working implementation and a 503 there means what a 503 usually means. The step is also why
    /// the offset the request actually used travels back on the outcome: a page that began at 1 and
    /// returned 200 rows ends at row 200, so the next one starts at 201. Advancing by the page size
    /// from the offset we *asked* for would skip the row the step landed on — the one row this
    /// arrangement can afford to lose is the newest memory, and it has already been spent.
    private func attemptMemories(limit: Int, offset: Int) async -> SourceOutcome<[WireMemory]> {
        do {
            let rows = try await fetchMemories(Self.memoryQuery(limit: limit, offset: offset))
            return SourceOutcome(rows: rows, failure: nil, offset: offset)
        } catch {
            // Only a 503 on the first page means the failing branch. A 500, a timeout, a rejection —
            // or a 503 at any other offset — is not the split above, and re-asking at a different
            // offset would spend a request to be told the same thing, so those fall through to the
            // shared classification below, unretried.
            guard offset == 0, case .http(503, _)? = error as? OmiAPIError else {
                ContextLog.error("Account memories unavailable: \(Self.reason(for: error))", Self.category)
                return SourceOutcome(rows: nil, failure: Self.classify(error), offset: offset)
            }
            ContextLog.info(
                "Account memories: the first page is unavailable; asking again from the second row",
                Self.category)
            let stepped = await attempt(
                "memories", fetchMemories, Self.memoryQuery(limit: limit, offset: Self.firstPageStep))
            // Flagged only when the retry actually produced rows: a page that failed twice is not a
            // page missing its head, it is no page at all.
            return SourceOutcome(
                rows: stepped.rows, failure: stepped.failure, offset: Self.firstPageStep,
                beganPastHead: stepped.rows != nil)
        }
    }

    /// One row, which is the smallest step that leaves the failing branch.
    private static let firstPageStep = 1

    /// What one source came back with: its rows, or `nil` for "this source did not answer" so the
    /// caller can tell a missing source from an empty one — plus, when it did not, the shape of
    /// failure that decides what the reader is told.
    fileprivate struct SourceOutcome<Row: Sendable>: Sendable {
        let rows: Row?
        let failure: SourceFailure?
        /// The offset the request that produced these rows actually carried, which is not always the
        /// one it was asked for — see `attemptMemories`. The cursor advances from this, never from
        /// the offset it handed out.
        var offset = 0
        /// True when this page had to start past its own first row to be served. Only memories can
        /// set it; see `attemptMemories`.
        var beganPastHead = false
    }

    /// Why a source came back with nothing, in the only three shapes anything downstream acts on.
    fileprivate enum SourceFailure: Sendable, Equatable {
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
        // Read back rather than passed alongside: the cursor advances from the offset the request
        // actually carried, and a second copy of it in a parameter is a second thing to get wrong.
        let offset = Int(query["offset"] ?? "0") ?? 0
        do {
            return SourceOutcome(rows: try await fetch(query), failure: nil, offset: offset)
        } catch {
            let failure = Self.classify(error)
            ContextLog.error("Account \(source) unavailable: \(Self.reason(for: error))", Self.category)
            return SourceOutcome(rows: nil, failure: failure, offset: offset)
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
    private static func conversationQuery(limit: Int, offset: Int) -> [String: String] {
        [
            "limit": String(limit),
            "offset": String(offset),
            "statuses": "completed,processing",
            "include_discarded": "false",
        ]
    }

    /// `GET /v1/action-items` pages on `offset` and answers with an authoritative `has_more`, which
    /// is the one source here that can say it has reached the end without spending a request to
    /// prove it.
    private static func taskQuery(limit: Int, offset: Int) -> [String: String] {
        ["limit": String(limit), "offset": String(offset)]
    }

    /// `device_scope` is left alone: its default is `all`, which is what this wants, and sending
    /// `current` is what makes the backend 400 for an account without the canonical lifecycle.
    private static func memoryQuery(limit: Int, offset: Int = 0) -> [String: String] {
        ["limit": String(limit), "offset": String(offset)]
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

// MARK: - Everything the account has handed over so far

/// The paging cursor and the rows it has gathered, for one signed-in session.
///
/// An actor for the reason `AccountDiagnosis` is one: `OmiActivityFeed` is a struct that gets copied
/// into whatever task reads with it, and paging state that copied with it would restart at page one
/// on every read. Everything mutable in this file lives here, so nothing else needs a lock.
///
/// **The two rules that make offset paging against this backend correct** are `ServerPaging`'s, and
/// both are load-bearing:
///
/// 1. **A short page is not the last page.** `/v3/memories` and `/v1/conversations` both fetch
///    `limit` documents and then drop the rejected, superseded and unparseable ones *in Python*, so
///    a request for 200 routinely answers 197. Reading that as the end is silent and total — the
///    account's other thousands of rows become unreachable for the rest of the session. Only an
///    empty page ends a source, which costs exactly one extra request at the end of each one.
/// 2. **An offset is not a stable cursor.** The memories query orders by mutable `scoring`, so a row
///    can move between two pages fetched seconds apart and arrive in both — or in neither. Pages are
///    therefore merged by identity, first sighting wins, and the cursor advances by the rows a page
///    actually *returned* rather than by the page size, which cannot skip a row under either
///    interpretation of where the backend applies its own filtering.
private actor AccountCorpus {

    /// What the next read has to do.
    enum Step: Sendable, Equatable {
        /// Nothing has been read yet: the newest page of all three sources, raced.
        case opening
        /// One page of one source. The offset is where that source's rows left off.
        case page(ActivityAccountSource, offset: Int)
        /// Every source has ended, failed out or spent its budget. No request is worth making.
        case settled
    }

    /// The whole corpus as one answer, plus what may be claimed about it.
    struct Held: Sendable {
        var conversations: [WireConversation] = []
        var memories: [WireMemory] = []
        var tasks: [WireActionItem] = []
        /// Sources whose rows here are the account's own answer as far as they go. A source that is
        /// currently failing, that has never answered, or that ran out of page budget with rows
        /// still behind it is *not* in here — which is what stops anything downstream reporting a
        /// partial corpus as a complete one.
        var answered: Set<ActivityAccountSource> = []
        /// The most recent failure of each source that has one, for the reader's diagnosis.
        var failures: [OmiActivityFeed.SourceFailure] = []
        var memoriesBeginPastHead = false
    }

    private var conversations: [WireConversation] = []
    private var memories: [WireMemory] = []
    private var tasks: [WireActionItem] = []
    /// Where each id already sits in the array above, so a row seen twice is *replaced* rather than
    /// dropped. A set of ids could only answer "have we had this one", which was enough while the
    /// cursor only moved forward and is not enough now `reopenHead` re-asks for page zero: the whole
    /// point of re-asking is that a row may have changed since, and the change we care about most is
    /// a conversation the backend has titled in the meantime.
    private var index: [ActivityAccountSource: [String: Int]] = [:]
    private var state: [ActivityAccountSource: SourceState] = [:]
    private var didOpen = false
    private var memoriesBeganPastHead = false
    /// Which source the round-robin resumes at.
    private var rotation = 0

    private struct SourceState {
        var nextOffset = 0
        var pages = 0
        var failures = 0
        var everAnswered = false
        /// A page came back empty, or the source told us there is no more.
        var isExhausted = false
        var lastFailure: OmiActivityFeed.SourceFailure?

        /// Whether this source is worth another request.
        var isOpen: Bool {
            !isExhausted && failures < OmiActivityFeed.failureLimit
                && pages < OmiActivityFeed.maximumPagesPerSource
        }

        /// Whether the rows held for it may be presented as the account's own answer.
        ///
        /// A source that spent its whole page budget is deliberately *not* one: it stopped with
        /// pages very possibly still behind it, and something downstream would read that as an
        /// inventory. Reaching the end on the last page of the budget is the one exception — the
        /// empty page proves there was nothing left, whatever the budget said.
        var isAnswered: Bool {
            guard everAnswered, failures == 0 else { return false }
            return isExhausted || pages < OmiActivityFeed.maximumPagesPerSource
        }
    }

    /// The next thing to fetch, and the only place the rotation moves.
    ///
    /// Round-robin rather than "finish one source then start the next" so that a long source cannot
    /// hold the other two behind it: a spine whose conversations are all in but whose tasks have not
    /// started is a spine with a whole kind missing from every day it draws.
    /// - Parameter skipping: sources the caller has already asked in this read. A page that answered
    ///   with nothing is not a reason to ask the same source again a moment later.
    func next(skipping: Set<ActivityAccountSource> = []) -> Step {
        guard didOpen else {
            didOpen = true
            return .opening
        }
        let sources = ActivityAccountSource.allCases
        for turn in 0..<sources.count {
            let source = sources[(rotation + turn) % sources.count]
            guard !skipping.contains(source) else { continue }
            let current = state[source] ?? SourceState()
            guard current.isOpen else { continue }
            rotation = (rotation + turn + 1) % sources.count
            return .page(source, offset: current.nextOffset)
        }
        return .settled
    }

    /// Which account the rows in here belong to. Bumped by `forgetEverything`; quoted by every
    /// commit, so a page fetched for an account the user has since signed out of is dropped instead
    /// of repopulating an emptied corpus. See `epoch` in `OmiActivityFeed.read`.
    private var generation = 0

    func epoch() -> Int { generation }

    /// The reopened head has been read; later pages are ordinary paging again and may not delete.
    func headWasRead() { headIsAuthoritative = false }

    /// Whether a page fetched at `epoch` may still be filed. False after a sign-out.
    private func isCurrent(_ epoch: Int) -> Bool { epoch == generation }

    func commit(
        conversations outcome: OmiActivityFeed.SourceOutcome<[WireConversation]>, epoch: Int
    ) {
        guard isCurrent(epoch) else { return }
        record(.conversations, outcome, received: outcome.rows?.count)
        if let rows = outcome.rows, isHeadReread(outcome) {
            prune(
                .conversations, keeping: rows.compactMap(\.id),
                newerThan: rows.compactMap { $0.startedAt?.seconds ?? $0.createdAt?.seconds }.min(),
                from: &conversations, at: { $0.startedAt?.seconds ?? $0.createdAt?.seconds })
        }
        for row in outcome.rows ?? [] {
            absorb(.conversations, id: row.id, row: row, into: &conversations)
        }
    }

    func commit(memories outcome: OmiActivityFeed.SourceOutcome<[WireMemory]>, epoch: Int) {
        guard isCurrent(epoch) else { return }
        if outcome.beganPastHead { memoriesBeganPastHead = true }
        record(.memories, outcome, received: outcome.rows?.count)
        // **Never for memories that had to start past their own head.** That page is complete
        // except at the top by construction, so the rows above it are absent because they were
        // never asked for — deleting them would be reading "not fetched" as "deleted".
        if let rows = outcome.rows, isHeadReread(outcome), !outcome.beganPastHead {
            prune(
                .memories, keeping: rows.compactMap(\.id),
                newerThan: rows.compactMap { $0.capturedAt?.seconds ?? $0.createdAt?.seconds }.min(),
                from: &memories, at: { $0.capturedAt?.seconds ?? $0.createdAt?.seconds })
        }
        for row in outcome.rows ?? [] {
            absorb(.memories, id: row.id, row: row, into: &memories)
        }
    }

    func commit(tasks outcome: OmiActivityFeed.SourceOutcome<WireActionItemPage>, epoch: Int) {
        guard isCurrent(epoch) else { return }
        record(.tasks, outcome, received: outcome.rows?.actionItems.count)
        // The one source that can say it has reached the end without an empty page to prove it.
        if let page = outcome.rows, !page.hasMore { state[.tasks]?.isExhausted = true }
        if let page = outcome.rows, isHeadReread(outcome) {
            prune(
                .tasks, keeping: page.actionItems.compactMap(\.id),
                newerThan: page.actionItems.compactMap { $0.createdAt?.seconds }.min(),
                from: &tasks, at: { $0.createdAt?.seconds })
        }
        for row in outcome.rows?.actionItems ?? [] {
            absorb(.tasks, id: row.id, row: row, into: &tasks)
        }
    }

    /// Whether this page is a re-read of a head we have already seen, and so may delete.
    private func isHeadReread<Row>(_ outcome: OmiActivityFeed.SourceOutcome<Row>) -> Bool {
        headIsAuthoritative && outcome.offset == 0
    }

    /// Drops rows the account has stopped listing, **within the window the new head page covers.**
    ///
    /// Without this a revalidation could only add and update: `reopenHead` re-reads offset zero and
    /// `absorb` replaces the ids it sees, so a conversation deleted on the phone stayed on the spine
    /// for the life of the process. That is a regression the process-lived store introduced — a
    /// panel rebuilt per window used to lose the row simply by being rebuilt.
    ///
    /// **The bound is what makes it safe.** A head page is authoritative only for its own range: it
    /// returned the newest `limit` rows, so anything held that is *newer than its oldest row* and
    /// absent from it has genuinely gone. Everything older is behind the page and says nothing about
    /// itself. An empty head page means the source now holds nothing at all, and every row goes.
    private func prune<Row>(
        _ source: ActivityAccountSource,
        keeping ids: [String],
        newerThan oldest: Double?,
        from rows: inout [Row],
        at instant: (Row) -> Double?
    ) {
        let returned = Set(ids)
        func survives(_ row: Row, _ id: String) -> Bool {
            if returned.contains(id) { return true }
            // Older than the page's own reach, so the page is not evidence about it.
            guard let oldest else { return false }
            guard let at = instant(row) else { return true }
            return at < oldest
        }

        var kept: [Row] = []
        var rebuilt: [String: Int] = [:]
        kept.reserveCapacity(rows.count)
        let byIndex = Dictionary(uniqueKeysWithValues: (index[source] ?? [:]).map { ($1, $0) })
        for (position, row) in rows.enumerated() {
            guard let id = byIndex[position] else { continue }
            guard survives(row, id) else { continue }
            rebuilt[id] = kept.count
            kept.append(row)
        }
        rows = kept
        index[source] = rebuilt
    }

    /// Reopens the newest page of every source without disturbing where hydration has walked to.
    ///
    /// One flag, and the restraint is the design — see `OmiActivityFeed.refreshHead`. `nextOffset`,
    /// `pages` and `isExhausted` are all left alone: a source that has reached its end has reached
    /// it, and the rows arriving at offset zero are in front of the cursor rather than behind it.
    func reopenHead() {
        didOpen = false
        headIsAuthoritative = true
    }

    /// Whether the next opening commit is a *re-read* of the head rather than a first sight of it.
    ///
    /// It is what lets a re-read delete. See `prune(_:keeping:newerThan:)`.
    private var headIsAuthoritative = false

    /// Back to the state this actor was constructed in. Every field, deliberately enumerated rather
    /// than reassigned wholesale — an actor cannot replace `self`, and a field added later that this
    /// forgot to clear would be one account's data surviving into another's session.
    func forgetEverything() {
        // First, so that a page already in flight for the previous account cannot file itself
        // between this call and the next read.
        generation &+= 1
        conversations = []
        memories = []
        tasks = []
        index = [:]
        state = [:]
        didOpen = false
        memoriesBeganPastHead = false
        rotation = 0
    }

    /// How many rows are held over every source — the reader's own version of the growth signal the
    /// caller reads, and cheaper than building a whole `Held` to count one.
    func rowCount() -> Int { conversations.count + memories.count + tasks.count }

    func held() -> Held {
        Held(
            conversations: conversations,
            memories: memories,
            tasks: tasks,
            answered: Set(state.filter { $0.value.isAnswered }.keys),
            failures: state.values.compactMap(\.lastFailure),
            memoriesBeginPastHead: memoriesBeganPastHead)
    }

    /// Moves one source's cursor by what its page did.
    ///
    /// - Parameter received: the rows the page returned **before** anything here dropped duplicates
    ///   or rows with no id, or nil when it did not answer. It is the raw count that the offset has
    ///   to advance by; advancing by the rows worth keeping would re-request the ones already
    ///   discarded, forever.
    private func record<Row>(
        _ source: ActivityAccountSource, _ outcome: OmiActivityFeed.SourceOutcome<Row>, received: Int?
    ) {
        var current = state[source] ?? SourceState()
        current.pages += 1
        if let received {
            current.failures = 0
            current.lastFailure = nil
            current.everAnswered = true
            // **Monotonic, because the head can be re-read.** `reopenHead` sends the next read back
            // to offset zero without moving the cursor, so a plain assignment here would walk the
            // whole account again from page one after every revalidation. A walk only ever moves
            // forward, so taking the larger of the two is the same arithmetic everywhere else.
            current.nextOffset = max(current.nextOffset, outcome.offset + max(received, 0))
            // `ServerPaging`: only an empty page is the end. A short one is the backend's own
            // post-filtering, and reading it as the end is how the rest of an account disappears.
            if received == 0 { current.isExhausted = true }
        } else {
            current.failures += 1
            current.lastFailure = outcome.failure
        }
        state[source] = current
    }

    /// Files one row under its identity: appended the first time, **replaced** every time after.
    ///
    /// Replacement rather than the first-sighting-wins rule this used to have. Both are correct for
    /// a forward-only walk, where a row arriving twice is the offset drift `ServerPaging` documents
    /// and the two copies are the same row. They are not both correct once `reopenHead` re-asks for
    /// page zero: there the second copy is deliberately newer, and keeping the first is how a
    /// conversation the backend titled ten minutes ago goes on reading `Untitled conversation` until
    /// the panel is rebuilt. Position is held constant so nothing reorders under the reader.
    ///
    /// A row with no id cannot be identified, so it cannot be diffed, selected or scrolled to — the
    /// projection drops it too, and it is dropped here rather than appended unkeyed.
    private func absorb<Row>(
        _ source: ActivityAccountSource, id: String?, row: Row, into rows: inout [Row]
    ) {
        guard let id, !id.isEmpty else { return }
        if let existing = index[source]?[id] {
            rows[existing] = row
            return
        }
        index[source, default: [:]][id] = rows.count
        rows.append(row)
    }
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
            // **When it was written, not when it is owed** — `SpineTask.timestamp` is
            // `task.createdAt` and nothing else, and the reason is visible the moment you do it the
            // other way. This surface is a record of what happened, ordered newest-first, and a due
            // date is a date in the *future*: anchoring on it hoisted every dated commitment above
            // today, so the list opened on "Monday 5 October" — seven weeks out — with today's real
            // capture buried four day-headers below it, and every task stamped 11:59 PM because
            // that is what a date with no time means.
            //
            // `due_at` is still decoded and still worth showing on the task itself; it is simply not
            // where the row belongs on a clock. Completion is the last resort for a row that somehow
            // has neither.
            at: createdAt?.seconds ?? completedAt?.seconds ?? fallback)
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
