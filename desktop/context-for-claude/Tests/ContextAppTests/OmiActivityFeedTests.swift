import Foundation
import XCTest

@testable import ContextApp

/// What the account half of the Activity spine has to survive: an account that is not there, a
/// source that fails while the others answer, and rows the backend genuinely sends — nullable
/// titles, missing timestamps, and dates in three different shapes.
///
/// Every payload below is decoded from JSON rather than hand-built, because the decoding is half of
/// what can go wrong: a `SimpleConversation` whose `structured.title` is blank must produce a row
/// with a readable title, and one whose `started_at` is tz-naive must not land in the wrong hour.
final class OmiActivityFeedTests: XCTestCase {

    // MARK: - No account

    /// Airgap Mode must be answered before a request exists. The fetchers are tripwires: if the read
    /// reaches one of them, the switch did not mean what it says.
    func testAirgapModeIsUnreachableWithoutAskingTheNetwork() async {
        let feed = OmiActivityFeed(
            isAirgapped: { true },
            isSignedIn: { XCTFail("Airgap Mode must not even ask whether we are signed in"); return true },
            credential: { _ in XCTFail("A read that cannot happen must not ask for a credential"); return nil },
            fetchConversations: { _, _ in XCTFail("Airgap Mode must not read conversations"); return [] },
            fetchMemories: { _, _ in XCTFail("Airgap Mode must not read memories"); return [] },
            fetchTasks: { _, _ in XCTFail("Airgap Mode must not read action items"); return [] })

        let result = await feed.read(since: nil, until: nil, limit: 50)

        XCTAssertFalse(result.reachable)
        XCTAssertTrue(result.isEmpty)
    }

    func testSignedOutIsUnreachableWithoutAskingTheNetwork() async {
        let feed = OmiActivityFeed(
            isAirgapped: { false },
            isSignedIn: { false },
            credential: { _ in XCTFail("A read that cannot happen must not ask for a credential"); return nil },
            fetchConversations: { _, _ in XCTFail("A signed-out app has nothing to authenticate with"); return [] },
            fetchMemories: { _, _ in XCTFail("A signed-out app has nothing to authenticate with"); return [] },
            fetchTasks: { _, _ in XCTFail("A signed-out app has nothing to authenticate with"); return [] })

        let result = await feed.read(since: nil, until: nil, limit: 50)

        XCTAssertFalse(result.reachable)
        XCTAssertTrue(result.isEmpty)
    }

    // MARK: - Reachability

    /// The distinction the field exists for: an account that answered and held nothing is not an
    /// account that did not answer.
    func testAnEmptyAccountIsReachable() async {
        let result = await Self.feed(conversations: [], memories: [], tasks: [])
            .read(since: nil, until: nil, limit: 50)

        XCTAssertTrue(result.reachable)
        XCTAssertTrue(result.isEmpty)
    }

    /// One dead source must not zero the others, and the feed stays reachable: the account *did*
    /// answer, and hiding the conversations we hold behind "nobody answered" would be the lie.
    func testOneFailingSourceDoesNotZeroTheOthers() async throws {
        let feed = OmiActivityFeed(
            isAirgapped: { false },
            isSignedIn: { true },
            credential: { _ in Self.provisionedKey },
            fetchConversations: { _, _ in try Self.decode([WireConversation].self, Self.conversationsJSON) },
            fetchMemories: { _, _ in throw OmiAPIError.http(500, "internal error") },
            fetchTasks: { _, _ in throw OmiAPIError.transport("the network connection was lost") })

        let result = await feed.read(since: nil, until: nil, limit: 50)

        XCTAssertTrue(result.reachable)
        XCTAssertEqual(result.conversations.count, 3)
        XCTAssertTrue(result.memories.isEmpty)
        XCTAssertTrue(result.tasks.isEmpty)
    }

    func testEverySourceFailingIsUnreachable() async {
        let feed = OmiActivityFeed(
            isAirgapped: { false },
            isSignedIn: { true },
            credential: { _ in Self.provisionedKey },
            fetchConversations: { _, _ in throw OmiAPIError.transport("offline") },
            fetchMemories: { _, _ in throw OmiAPIError.transport("offline") },
            fetchTasks: { _, _ in throw OmiAPIError.decoding("missing field id in the response") })

        let result = await feed.read(since: nil, until: nil, limit: 50)

        XCTAssertFalse(result.reachable)
        XCTAssertTrue(result.isEmpty)
    }

    // MARK: - A rejected key

    /// The failure this whole path exists for. `/v1/mcp/*` authenticates an `omi_mcp_…` key and
    /// nothing else, so a key the account has retired takes every source down at once — and the
    /// repair is to mint another, **once**, and read again on it.
    func testARejectedKeyIsReprovisionedOnceAndTheReadRetries() async throws {
        let mint = CallCounter()
        let attempts = CallCounter()
        let feed = OmiActivityFeed(
            isAirgapped: { false },
            isSignedIn: { true },
            credential: { rejected in
                guard let rejected else { return Self.staleKey }
                XCTAssertEqual(rejected, Self.staleKey, "the replacement must be asked for by the key that failed")
                await mint.hit()
                return Self.provisionedKey
            },
            fetchConversations: { key, _ in
                await attempts.hit()
                guard key == Self.provisionedKey else { throw OmiAPIError.http(401, "") }
                return try Self.decode([WireConversation].self, Self.conversationsJSON)
            },
            fetchMemories: { _, _ in [] },
            fetchTasks: { _, _ in [] })

        let result = await feed.read(since: nil, until: nil, limit: 50)

        let mints = await mint.count
        let tries = await attempts.count
        let reason = await feed.unreachableReason()
        XCTAssertTrue(result.reachable)
        XCTAssertEqual(result.conversations.count, 3, "the retry has to actually carry the rows")
        XCTAssertEqual(mints, 1, "exactly one re-provision — a rejection is not a retry ladder")
        XCTAssertEqual(tries, 2, "the stale key, then the fresh one, and no more")
        XCTAssertNil(reason, "a read that recovered has no failure to report")
    }

    /// The other half, and the one that used to render as "you have no memories": a key that cannot
    /// be replaced. It must come back unreachable — with the reason that tells the user to
    /// reconnect — and it must stop asking rather than mint a key per source forever.
    func testARejectionThatCannotBeRepairedIsUnreachableRatherThanEmpty() async throws {
        let mint = CallCounter()
        let attempts = CallCounter()
        let feed = OmiActivityFeed(
            isAirgapped: { false },
            isSignedIn: { true },
            credential: { rejected in
                guard rejected != nil else { return Self.staleKey }
                await mint.hit()
                // The account refused, or Airgap Mode came on, or the mint failed: nothing to try.
                return nil
            },
            fetchConversations: { _, _ in
                await attempts.hit()
                throw OmiAPIError.http(401, "")
            },
            fetchMemories: { _, _ in
                await attempts.hit()
                throw OmiAPIError.http(401, "")
            },
            fetchTasks: { _, _ in
                await attempts.hit()
                throw OmiAPIError.http(401, "")
            })

        let result = await feed.read(since: nil, until: nil, limit: 50)

        let reason = await feed.unreachableReason()
        let tries = await attempts.count
        let mints = await mint.count
        XCTAssertFalse(result.reachable, "an account that refused this Mac's key is not an empty account")
        XCTAssertTrue(result.isEmpty)
        XCTAssertEqual(
            reason, .keyRejected,
            "the empty copy has to be able to say \"reconnect\" rather than \"nothing here\"")
        XCTAssertEqual(tries, 3, "one attempt per source and no retry without a new key")
        XCTAssertEqual(mints, 3, "each source asks once — the provisioner is what de-duplicates")
    }

    /// Signed in, not airgapped, and no key at all: nothing is even attempted, and the reader is
    /// told the same actionable thing as a rejection rather than "nothing happened".
    func testNoKeyAtAllIsUnreachableWithoutAskingTheNetwork() async {
        let feed = OmiActivityFeed(
            isAirgapped: { false },
            isSignedIn: { true },
            credential: { _ in nil },
            fetchConversations: { _, _ in XCTFail("There is nothing to authenticate with"); return [] },
            fetchMemories: { _, _ in XCTFail("There is nothing to authenticate with"); return [] },
            fetchTasks: { _, _ in XCTFail("There is nothing to authenticate with"); return [] })

        let result = await feed.read(since: nil, until: nil, limit: 50)

        let reason = await feed.unreachableReason()
        XCTAssertFalse(result.reachable)
        XCTAssertEqual(reason, .keyUnavailable)
    }

    /// A 403 is a key that authenticated and lacks the access. Minting another copy of the same
    /// credential cannot change that, so it must not be spent on one.
    func testAForbiddenSourceIsNotReprovisioned() async {
        let mint = CallCounter()
        let feed = OmiActivityFeed(
            isAirgapped: { false },
            isSignedIn: { true },
            credential: { rejected in
                if rejected != nil { await mint.hit() }
                return Self.provisionedKey
            },
            fetchConversations: { _, _ in throw OmiAPIError.http(403, "") },
            fetchMemories: { _, _ in [] },
            fetchTasks: { _, _ in [] })

        let result = await feed.read(since: nil, until: nil, limit: 50)

        let mints = await mint.count
        XCTAssertTrue(result.reachable, "two sources answered")
        XCTAssertEqual(mints, 0, "a 403 is access, not identity — another key of the same kind changes nothing")
    }

    /// The airgap and signed-out reasons are what let the empty copy say something other than "I
    /// couldn't reach it" for two states that are not failures at all.
    func testTheReasonNamesAirgapAndSignedOutSeparately() async {
        let airgapped = OmiActivityFeed(
            isAirgapped: { true }, isSignedIn: { true }, credential: { _ in Self.provisionedKey },
            fetchConversations: { _, _ in [] }, fetchMemories: { _, _ in [] }, fetchTasks: { _, _ in [] })
        _ = await airgapped.read(since: nil, until: nil, limit: 50)
        let airgapReason = await airgapped.unreachableReason()
        XCTAssertEqual(airgapReason, .airgapped)

        let signedOut = OmiActivityFeed(
            isAirgapped: { false }, isSignedIn: { false }, credential: { _ in Self.provisionedKey },
            fetchConversations: { _, _ in [] }, fetchMemories: { _, _ in [] }, fetchTasks: { _, _ in [] })
        _ = await signedOut.read(since: nil, until: nil, limit: 50)
        let signedOutReason = await signedOut.unreachableReason()
        XCTAssertEqual(signedOutReason, .signedOut)

        let offline = OmiActivityFeed(
            isAirgapped: { false }, isSignedIn: { true }, credential: { _ in Self.provisionedKey },
            fetchConversations: { _, _ in throw OmiAPIError.transport("offline") },
            fetchMemories: { _, _ in throw OmiAPIError.transport("offline") },
            fetchTasks: { _, _ in throw OmiAPIError.transport("offline") })
        _ = await offline.read(since: nil, until: nil, limit: 50)
        let offlineReason = await offline.unreachableReason()
        XCTAssertEqual(offlineReason, .noAnswer)
    }

    // MARK: - A rate-limited account

    /// The state this ladder was written from: every `/v1/mcp/*` endpoint answering 429 while the
    /// key, the request and the account were all fine. It must be told apart from a rejection (auth
    /// is not the problem), from an outage (something *did* answer), and above all from an empty
    /// account — and it must stop asking, because asking harder is what keeps a limit tripped.
    func testARateLimitedAccountSaysSoAndStopsAsking() async {
        let attempts = CallCounter()
        let waits = SleepRecorder()
        let refuse: @Sendable () async throws -> Void = {
            await attempts.hit()
            // A bare `OmiAPIError.http(429, …)` rather than `OmiMCPRateLimited`: any thrower of a
            // plain 429 is still a rate limit, it just came without the server's own `Retry-After`.
            throw OmiAPIError.http(429, "")
        }
        let feed = OmiActivityFeed(
            isAirgapped: { false },
            isSignedIn: { true },
            credential: { rejected in
                XCTAssertNil(rejected, "a 429 is not an identity problem — no key may be spent on it")
                return Self.provisionedKey
            },
            fetchConversations: { _, _ in try await refuse(); return [] },
            fetchMemories: { _, _ in try await refuse(); return [] },
            fetchTasks: { _, _ in try await refuse(); return [] },
            sleep: { await waits.record($0) })

        let result = await feed.read(since: nil, until: nil, limit: 50)

        let reason = await feed.unreachableReason()
        let tries = await attempts.count
        XCTAssertFalse(result.reachable, "a rate-limited account is not an empty one")
        XCTAssertEqual(
            reason, .rateLimited,
            "neither a rejected key nor \"nobody answered\" — the account answered, and said wait")
        XCTAssertEqual(tries, 9, "three sources, each the first attempt plus two retries, and no more")
    }

    /// The ladder itself: bounded, and each wait longer than the last. Only one source is rate
    /// limited so the waits recorded are provably that source's, in order.
    func testTheRetryLadderIsBoundedAndBacksOff() async {
        let attempts = CallCounter()
        let waits = SleepRecorder()
        let feed = Self.rateLimited(
            conversations: { throw OmiMCPRateLimited(retryAfter: nil) },
            attempts: attempts, waits: waits)

        let result = await feed.read(since: nil, until: nil, limit: 50)

        let recorded = await waits.durations
        let tries = await attempts.count
        XCTAssertTrue(result.reachable, "the other two sources answered")
        XCTAssertTrue(result.conversations.isEmpty)
        XCTAssertEqual(tries, 3, "one attempt plus two retries")
        XCTAssertEqual(recorded.count, 2, "one wait per retry, and the ladder stops there")
        // Equal jitter over 1s then 2s: half the delay is fixed, half is random.
        XCTAssertTrue((0.5...1.0).contains(recorded[0]), "first wait was \(recorded[0])s")
        XCTAssertTrue((1.0...2.0).contains(recorded[1]), "second wait was \(recorded[1])s")
        XCTAssertGreaterThan(recorded[1], recorded[0], "backing off means waiting longer, not the same")
    }

    /// A retry that lands has to actually carry the rows, or the ladder is just a slower failure.
    func testASourceThatClearsOnRetryCarriesItsRows() async throws {
        let attempts = CallCounter()
        let waits = SleepRecorder()
        let feed = Self.rateLimited(
            conversations: {
                guard await attempts.count > 1 else { throw OmiMCPRateLimited(retryAfter: nil) }
                return try Self.decode([WireConversation].self, Self.conversationsJSON)
            },
            attempts: attempts, waits: waits)

        let result = await feed.read(since: nil, until: nil, limit: 50)

        let recorded = await waits.durations
        XCTAssertTrue(result.reachable)
        XCTAssertEqual(result.conversations.count, 3)
        XCTAssertEqual(recorded.count, 1, "one wait, because the second attempt answered")
    }

    /// `Retry-After` is the server saying when it will be ready, and it wins over our own guess —
    /// but only up to the point where waiting would hold the panel's read open. Past that we stop
    /// and report the rate limit, and the store's re-read is what waits it out.
    func testRetryAfterIsHonouredAndAWaitTooLongIsNotSpentInline() async {
        let attempts = CallCounter()
        let waits = SleepRecorder()
        let brief = Self.rateLimited(
            conversations: { throw OmiMCPRateLimited(retryAfter: 3) }, attempts: attempts, waits: waits)
        _ = await brief.read(since: nil, until: nil, limit: 50)

        let recorded = await waits.durations
        let tries = await attempts.count
        XCTAssertEqual(recorded, [3, 3], "the server's own number, unjittered — it knows and we do not")
        XCTAssertEqual(tries, 3)

        let patient = CallCounter()
        let unspent = SleepRecorder()
        let long = Self.rateLimited(
            conversations: { throw OmiMCPRateLimited(retryAfter: 120) }, attempts: patient, waits: unspent)
        _ = await long.read(since: nil, until: nil, limit: 50)

        let unspentWaits = await unspent.durations
        let patientTries = await patient.count
        XCTAssertTrue(unspentWaits.isEmpty, "two minutes is not a wait to hold a read open for")
        XCTAssertEqual(patientTries, 1, "it stops rather than sleeping, and reports the limit")
    }

    /// When the three sources fail for different reasons, the reader is told the one they can act
    /// on. A rejection means "reconnect"; a rate limit only means "wait", so it does not outrank it.
    func testARejectedKeyOutranksARateLimit() async {
        let waits = SleepRecorder()
        let feed = OmiActivityFeed(
            isAirgapped: { false },
            isSignedIn: { true },
            credential: { rejected in rejected == nil ? Self.staleKey : nil },
            fetchConversations: { _, _ in throw OmiAPIError.http(401, "") },
            fetchMemories: { _, _ in throw OmiMCPRateLimited(retryAfter: nil) },
            fetchTasks: { _, _ in throw OmiMCPRateLimited(retryAfter: nil) },
            sleep: { await waits.record($0) })

        let result = await feed.read(since: nil, until: nil, limit: 50)

        let reason = await feed.unreachableReason()
        XCTAssertFalse(result.reachable)
        XCTAssertEqual(reason, .keyRejected, "the one of the three the user can do something about")
    }

    // MARK: - Reading the account again

    /// A read that failed for a reason time can fix must be made again. Before this, the account was
    /// read once per time window: a rate limit at the moment the panel opened left it empty for the
    /// whole session, with nothing on any schedule that would ever look again.
    @MainActor
    func testARateLimitedStoreReadsTheAccountAgainUntilItAnswers() async throws {
        let account = ScriptedAccount([.rateLimited, .noAnswer, nil])
        let store = ActivityStore(
            store: { nil }, account: account, accountRetryDelays: Self.immediateLadder)

        store.start()
        try await Self.waitUntil("the account never healed") { store.accountReachable }

        let reads = await account.reads
        XCTAssertEqual(reads, 3, "the first read, then one per failure that could clear")
        XCTAssertNil(store.accountUnreachableReason)
    }

    /// The other half, and the one that would be a defect rather than a feature: a failure only the
    /// user can repair must not become a poll. A rejected key would mint a fresh credential on every
    /// attempt; a signed-out app and Airgap Mode can only ever give the same answer.
    ///
    /// The rate-limited store beside it is the control — its ladder running out on the same schedule
    /// is what proves enough time passed for a timer to have fired, without this test sleeping on a
    /// guess.
    @MainActor
    func testAFailureOnlyTheUserCanRepairIsNeverPolled() async throws {
        let rejected = ScriptedAccount([.keyRejected])
        let rejectedStore = ActivityStore(
            store: { nil }, account: rejected, accountRetryDelays: Self.immediateLadder)
        let limited = ScriptedAccount([.rateLimited])
        let limitedStore = ActivityStore(
            store: { nil }, account: limited, accountRetryDelays: Self.immediateLadder)

        rejectedStore.start()
        limitedStore.start()
        try await Self.waitUntil("the healable ladder never ran out") {
            await limited.reads == Self.immediateLadder.count + 1
        }

        let attempts = await rejected.reads
        XCTAssertEqual(attempts, 1, "a key the account refused is not a thing to ask about on a timer")
        XCTAssertEqual(rejectedStore.accountUnreachableReason, .keyRejected)
        XCTAssertEqual(limitedStore.accountUnreachableReason, .rateLimited)
    }

    /// The policy the schedule is built on, stated once where it can be read: which reasons another
    /// read could answer differently, and which are answers already.
    func testOnlyFailuresTimeCanFixAreScheduled() {
        for healable in [ActivityAccountUnreachableReason.rateLimited, .noAnswer, .keyUnavailable] {
            XCTAssertTrue(ActivityStore.healsOnItsOwn(healable), "\(healable) clears without the user")
        }
        for permanent in [ActivityAccountUnreachableReason.airgapped, .signedOut, .keyRejected] {
            XCTAssertFalse(ActivityStore.healsOnItsOwn(permanent), "\(permanent) needs the user, not a timer")
        }
    }

    // MARK: - Conversations

    func testConversationsDecodeWithNullTitlesTimestampsAndEmoji() async throws {
        let result = await Self.feed(
            conversations: try Self.decode([WireConversation].self, Self.conversationsJSON),
            memories: [], tasks: [], now: { Self.placement })
            .read(since: nil, until: nil, limit: 50)

        // The row with no `id` is gone: it cannot be identified, so it cannot be a row.
        XCTAssertEqual(result.conversations.map(\.id), ["conv-1", "conv-2", "conv-3"])

        let full = result.conversations[0]
        XCTAssertEqual(full.title, "Standup with Mila")
        XCTAssertEqual(full.overview, "Shipping the spine on Thursday.")
        // Microseconds and an explicit `+00:00` offset — what Pydantic serialises a tz-aware
        // datetime to.
        XCTAssertEqual(full.startedAt, Self.utc(2026, 8, 13, 9, 0, 0) + 0.123, accuracy: 0.001)
        XCTAssertEqual(full.finishedAt, Self.utc(2026, 8, 13, 9, 42, 10), accuracy: 0.001)
        // `SimpleStructured` does not carry an emoji at all, so this is the backend's own default.
        XCTAssertEqual(full.emoji, "🧠")

        let blank = result.conversations[1]
        XCTAssertEqual(blank.title, "Untitled conversation", "a blank title must never render an empty row")
        XCTAssertNil(blank.overview, "an empty overview is nothing to show, not an empty line")
        XCTAssertEqual(blank.startedAt, Self.placement, "an undated conversation sits at the window edge")
        XCTAssertEqual(blank.finishedAt, Self.placement)

        let naive = result.conversations[2]
        XCTAssertEqual(naive.emoji, "📚", "an emoji the account did send must survive")
        // `2026-08-13 11:30:00`: no zone, space-separated. Read as UTC, which is what the backend
        // itself does with a naive timestamp — reading it as local time would move it by hours.
        XCTAssertEqual(naive.startedAt, Self.utc(2026, 8, 13, 11, 30, 0), accuracy: 0.001)
        XCTAssertEqual(naive.finishedAt, naive.startedAt, "a missing finish cannot precede the start")
    }

    // MARK: - Memories

    /// `CleanerMemory` carries no timestamp, so a memory is placed at the window's upper edge and
    /// the server's newest-first order is what actually carries the sequence.
    func testMemoriesWithoutTimestampsArePlacedAtTheWindowEdge() async throws {
        let result = await Self.feed(
            conversations: [], memories: try Self.decode([WireMemory].self, Self.memoriesJSON), tasks: [],
            now: { Self.placement })
            .read(since: nil, until: Self.windowEnd, limit: 50)

        XCTAssertEqual(result.memories.map(\.id), ["mem-1", "mem-3"])
        XCTAssertEqual(result.memories[0].content, "Prefers espresso")
        XCTAssertEqual(result.memories[0].at, Self.windowEnd, "with no timestamp, the window's edge — not `now`")
        XCTAssertEqual(result.memories[1].at, Self.utc(2026, 8, 10, 8, 0, 0), accuracy: 0.001)
    }

    // MARK: - Tasks

    func testTasksPreferTheDueDateAndDefaultToNotCompleted() async throws {
        let result = await Self.feed(
            conversations: [], memories: [], tasks: try Self.decode([WireActionItem].self, Self.tasksJSON),
            now: { Self.placement })
            .read(since: nil, until: nil, limit: 50)

        XCTAssertEqual(result.tasks.map(\.id), ["task-1", "task-2", "task-4"])

        XCTAssertEqual(result.tasks[0].text, "Send the invoice")
        XCTAssertFalse(result.tasks[0].completed)
        XCTAssertEqual(result.tasks[0].at, Self.utc(2026, 8, 14, 17, 0, 0), accuracy: 0.001)

        XCTAssertTrue(result.tasks[1].completed)
        XCTAssertEqual(
            result.tasks[1].at, Self.utc(2026, 8, 2, 9, 0, 0), accuracy: 0.001,
            "no due date falls back to created")

        // A bare number of seconds, the shape the sibling screen-activity rows use.
        XCTAssertEqual(result.tasks[2].at, 1_786_000_000.5, accuracy: 0.001)
        // `completed` absent entirely.
        XCTAssertFalse(result.tasks[2].completed)
    }

    // MARK: - The window on the wire

    func testTheWindowAndLimitReachTheEndpointsThatAcceptThem() async throws {
        let recorder = QueryRecorder()
        let feed = OmiActivityFeed(
            isAirgapped: { false },
            isSignedIn: { true },
            credential: { _ in Self.provisionedKey },
            fetchConversations: { await recorder.record("conversations", $1); return [] },
            fetchMemories: { await recorder.record("memories", $1); return [] },
            fetchTasks: { await recorder.record("action-items", $1); return [] })

        _ = await feed.read(
            since: Self.utc(2026, 8, 13, 0, 0, 0), until: Self.utc(2026, 8, 14, 0, 0, 0), limit: 5000)

        let conversations = await recorder.query("conversations")
        XCTAssertEqual(conversations?["start_date"], "2026-08-13T00:00:00Z")
        XCTAssertEqual(conversations?["end_date"], "2026-08-14T00:00:00Z")
        // Clamped: the spine shows a window, not an account export.
        XCTAssertEqual(conversations?["limit"], "200")

        let memories = await recorder.query("memories")
        XCTAssertEqual(memories?["updated_after"], "2026-08-13T00:00:00Z", "the only date filter this endpoint has")
        XCTAssertEqual(memories?["sort"], "created_desc")

        let tasks = await recorder.query("action-items")
        XCTAssertEqual(tasks?["limit"], "200")
        // Deliberate: the endpoint's date filters bound the *due* date, so windowing here would
        // drop every undated commitment — and an open commitment matters today regardless.
        XCTAssertNil(tasks?["due_start_date"])
        XCTAssertNil(tasks?["due_end_date"])
    }

    // MARK: - Fixtures

    /// A page as `GET /v1/mcp/conversations` sends it: the full row, one whose title and overview
    /// are blank and whose timestamps are null, one with a tz-naive space-separated start and no
    /// finish at all, and one with no `id`.
    private static let conversationsJSON = """
        [
          {
            "id": "conv-1",
            "started_at": "2026-08-13T09:00:00.123456+00:00",
            "finished_at": "2026-08-13T09:42:10Z",
            "structured": {
              "title": "Standup with Mila",
              "overview": "Shipping the spine on Thursday.",
              "category": "work"
            },
            "language": "en",
            "apps_results": []
          },
          {
            "id": "conv-2",
            "started_at": null,
            "finished_at": null,
            "structured": { "title": "   ", "overview": "", "category": "other" },
            "apps_results": []
          },
          {
            "id": "conv-3",
            "started_at": "2026-08-13 11:30:00",
            "structured": {
              "title": "Reading",
              "overview": "Notes on the spine.",
              "category": "personal",
              "emoji": "📚"
            }
          },
          {
            "started_at": "2026-08-13T12:00:00Z",
            "structured": { "title": "No id", "overview": "dropped", "category": "other" }
          }
        ]
        """

    /// `CleanerMemory` as it actually arrives — no timestamp — plus a blank-content row and one
    /// with no `id`.
    private static let memoriesJSON = """
        [
          { "id": "mem-1", "content": "Prefers espresso", "category": "core", "reviewed": true },
          { "id": "mem-2", "content": "   ", "category": "core" },
          {
            "id": "mem-3",
            "content": "Ships on Thursdays",
            "category": "work",
            "created_at": "2026-08-10T08:00:00Z"
          },
          { "content": "no id", "category": "core" }
        ]
        """

    private static let tasksJSON = """
        [
          {
            "id": "task-1",
            "description": "Send the invoice",
            "completed": false,
            "created_at": "2026-08-01T09:00:00Z",
            "due_at": "2026-08-14T17:00:00Z",
            "completed_at": null,
            "conversation_id": "conv-1"
          },
          {
            "id": "task-2",
            "description": "Book the flight",
            "completed": true,
            "created_at": "2026-08-02T09:00:00Z",
            "due_at": null,
            "completed_at": "2026-08-03T10:00:00Z"
          },
          { "id": "task-3", "description": "", "created_at": null },
          { "id": "task-4", "description": "Numeric timestamp", "created_at": 1786000000.5 }
        ]
        """

    // MARK: - Helpers

    /// Stands in for "now" and for the window's upper edge, so a row placed at either is provably
    /// placed rather than accidentally right.
    private static let placement: Double = 1_786_000_500
    private static let windowEnd: Double = 1_786_004_000

    /// Two distinguishable credentials. Not real keys and never written anywhere — the point is only
    /// that "the key that was rejected" and "the key that replaced it" can be told apart.
    private static let staleKey = "omi_mcp_stale"
    private static let provisionedKey = "omi_mcp_fresh"

    private actor CallCounter {
        private(set) var count = 0
        func hit() { count += 1 }
    }

    /// What the retry ladder waited, in the order it waited it. Injected in place of the real sleep
    /// so the backoff can be asserted rather than endured.
    private actor SleepRecorder {
        private(set) var durations: [TimeInterval] = []
        func record(_ seconds: TimeInterval) { durations.append(seconds) }
    }

    /// One rate-limited source beside two that answer, so the waits recorded are provably that
    /// source's and in its order.
    private static func rateLimited(
        conversations: @escaping @Sendable () async throws -> [WireConversation],
        attempts: CallCounter,
        waits: SleepRecorder
    ) -> OmiActivityFeed {
        OmiActivityFeed(
            isAirgapped: { false },
            isSignedIn: { true },
            credential: { _ in Self.provisionedKey },
            fetchConversations: { _, _ in
                await attempts.hit()
                return try await conversations()
            },
            fetchMemories: { _, _ in [] },
            fetchTasks: { _, _ in [] },
            sleep: { await waits.record($0) })
    }

    /// The healing schedule with its waits removed. The *shape* of the ladder is what these tests
    /// are about — how many reads a failure buys, and which failures buy any — and spending the real
    /// eight minutes to prove it would be a test nobody runs.
    private static let immediateLadder: [Duration] = [.zero, .zero, .zero, .zero]

    /// An account with its answers written down: one per read, the last one repeating. `nil` means
    /// it answered.
    private actor ScriptedAccount: ActivityAccountReading, ActivityAccountDiagnosing {
        private let answers: [ActivityAccountUnreachableReason?]
        private(set) var reads = 0
        private var last: ActivityAccountUnreachableReason?

        init(_ answers: [ActivityAccountUnreachableReason?]) {
            self.answers = answers
        }

        func read(since: Double?, until: Double?, limit: Int) async -> ActivityAccountFeed {
            let answer = answers[min(reads, answers.count - 1)]
            reads += 1
            last = answer
            return answer == nil ? .empty : .unreachable
        }

        func unreachableReason() async -> ActivityAccountUnreachableReason? { last }
    }

    /// Polls until the condition holds, or fails the test. A deadline rather than a sleep: what is
    /// being waited for is a timer firing on another task, and a fixed sleep is either flaky or slow.
    private static func waitUntil(
        _ message: String,
        within timeout: TimeInterval = 5,
        file: StaticString = #filePath,
        line: UInt = #line,
        _ condition: @MainActor @Sendable () async -> Bool
    ) async throws {
        let deadline = Date().addingTimeInterval(timeout)
        while Date() < deadline {
            if await condition() { return }
            try await Task.sleep(for: .milliseconds(2))
        }
        XCTFail(message, file: file, line: line)
    }

    private static func feed(
        conversations: [WireConversation],
        memories: [WireMemory],
        tasks: [WireActionItem],
        now: @escaping @Sendable () -> Double = { placement }
    ) -> OmiActivityFeed {
        OmiActivityFeed(
            isAirgapped: { false },
            isSignedIn: { true },
            credential: { _ in Self.provisionedKey },
            fetchConversations: { _, _ in conversations },
            fetchMemories: { _, _ in memories },
            fetchTasks: { _, _ in tasks },
            now: now)
    }

    /// Mirrors `OmiAPI`'s decoder, which is what these shapes are decoded under in production: the
    /// wire is snake_case and the properties are camelCase.
    private static func decode<T: Decodable>(_ type: T.Type, _ json: String) throws -> T {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(type, from: Data(json.utf8))
    }

    /// An expectation built from calendar components rather than from another ISO parser, so a bug
    /// in the parser under test cannot also produce the number it is compared against.
    private static func utc(_ year: Int, _ month: Int, _ day: Int, _ hour: Int, _ minute: Int, _ second: Int)
        -> Double
    {
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = TimeZone(secondsFromGMT: 0)!
        let components = DateComponents(
            year: year, month: month, day: day, hour: hour, minute: minute, second: second)
        return calendar.date(from: components)!.timeIntervalSince1970
    }

    private actor QueryRecorder {
        private var queries: [String: [String: String]] = [:]

        func record(_ source: String, _ query: [String: String]) {
            queries[source] = query
        }

        func query(_ source: String) -> [String: String]? {
            queries[source]
        }
    }
}
