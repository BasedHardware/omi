import Foundation
import XCTest

@testable import ContextApp

/// What the account half of the Activity spine has to survive: an account that is not there, a
/// source that fails while the others answer, and rows the backend genuinely sends — nullable
/// titles, missing timestamps, and dates in three different shapes.
///
/// Every payload below is decoded from JSON rather than hand-built, because the decoding is half of
/// what can go wrong: a `Conversation` whose `structured.title` is blank must produce a row with a
/// readable title, one whose `started_at` is tz-naive must not land in the wrong hour, and
/// `ActionItemsResponse` is an object where the other two routes are arrays.
///
/// **There is no retry ladder here to test any more.** `OmiAPI` spends the forced token refresh on a
/// 401 and the jittered retries on a 429 or 5xx for every caller in the app, so what these tests
/// drive through the fetcher closures is the *final* answer for a source: one attempt, then
/// classification. Everything that used to prove a re-provisioned `omi_mcp_…` key, a backoff
/// schedule or an honoured `Retry-After` is gone with the machinery it described.
final class OmiActivityFeedTests: XCTestCase {

    // MARK: - No account

    /// Airgap Mode must be answered before a request exists. The fetchers are tripwires: if the read
    /// reaches one of them, the switch did not mean what it says.
    func testAirgapModeIsUnreachableWithoutAskingTheNetwork() async {
        let feed = OmiActivityFeed(
            isAirgapped: { true },
            isSignedIn: { XCTFail("Airgap Mode must not even ask whether we are signed in"); return true },
            fetchConversations: { _ in XCTFail("Airgap Mode must not read conversations"); return [] },
            fetchMemories: { _ in XCTFail("Airgap Mode must not read memories"); return [] },
            fetchTasks: { _ in
                XCTFail("Airgap Mode must not read action items")
                return WireActionItemPage(actionItems: [])
            })

        let result = await feed.read(since: nil, until: nil, limit: 50)

        XCTAssertFalse(result.reachable)
        XCTAssertTrue(result.isEmpty)
    }

    func testSignedOutIsUnreachableWithoutAskingTheNetwork() async {
        let feed = OmiActivityFeed(
            isAirgapped: { false },
            isSignedIn: { false },
            fetchConversations: { _ in XCTFail("A signed-out app has nothing to authenticate with"); return [] },
            fetchMemories: { _ in XCTFail("A signed-out app has nothing to authenticate with"); return [] },
            fetchTasks: { _ in
                XCTFail("A signed-out app has nothing to authenticate with")
                return WireActionItemPage(actionItems: [])
            })

        let result = await feed.read(since: nil, until: nil, limit: 50)

        XCTAssertFalse(result.reachable)
        XCTAssertTrue(result.isEmpty)
    }

    // MARK: - Reachability

    /// The distinction the field exists for: an account that answered and held nothing is not an
    /// account that did not answer.
    func testAnEmptyAccountIsReachable() async {
        let result = await Self.feed(conversations: [], memories: [], tasks: Self.emptyPage)
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
            fetchConversations: { _ in try Self.decode([WireConversation].self, Self.conversationsJSON) },
            fetchMemories: { _ in throw OmiAPIError.http(500, "internal error") },
            fetchTasks: { _ in throw OmiAPIError.transport("the network connection was lost") })

        let result = await feed.read(since: nil, until: nil, limit: 50)

        let reason = await feed.unreachableReason()
        XCTAssertTrue(result.reachable)
        XCTAssertEqual(result.conversations.count, 3)
        XCTAssertTrue(result.memories.isEmpty)
        XCTAssertTrue(result.tasks.isEmpty)
        XCTAssertNil(reason, "a read that carried rows has no failure to report")
    }

    func testEverySourceFailingIsUnreachable() async {
        let feed = OmiActivityFeed(
            isAirgapped: { false },
            isSignedIn: { true },
            fetchConversations: { _ in throw OmiAPIError.transport("offline") },
            fetchMemories: { _ in throw OmiAPIError.transport("offline") },
            fetchTasks: { _ in throw OmiAPIError.decoding("missing field id in the response") })

        let result = await feed.read(since: nil, until: nil, limit: 50)

        let reason = await feed.unreachableReason()
        XCTAssertFalse(result.reachable)
        XCTAssertTrue(result.isEmpty)
        XCTAssertEqual(reason, .noAnswer)
    }

    // MARK: - Why nobody answered

    /// The failure that used to render as "you have no memories". A session the backend refused —
    /// after `OmiAPI` already spent its one forced token refresh on it — must come back unreachable
    /// with the reason that tells the user to sign in again, and it must ask exactly once per
    /// source: there is nothing left here to retry with.
    func testARefusedSessionIsUnreachableRatherThanEmpty() async {
        let attempts = CallCounter()
        let refuse: @Sendable () async throws -> Void = {
            await attempts.hit()
            throw OmiAPIError.http(401, "")
        }
        let feed = OmiActivityFeed(
            isAirgapped: { false },
            isSignedIn: { true },
            fetchConversations: { _ in try await refuse(); return [] },
            fetchMemories: { _ in try await refuse(); return [] },
            fetchTasks: { _ in try await refuse(); return Self.emptyPage })

        let result = await feed.read(since: nil, until: nil, limit: 50)

        let reason = await feed.unreachableReason()
        let tries = await attempts.count
        XCTAssertFalse(result.reachable, "an account that refused this Mac's session is not an empty account")
        XCTAssertTrue(result.isEmpty)
        XCTAssertEqual(
            reason, .keyRejected,
            "the empty copy has to be able to say \"sign in again\" rather than \"nothing here\"")
        XCTAssertEqual(tries, 3, "one attempt per source — `OmiAPI` has already done the retrying")
    }

    /// `OmiAPIError.notSignedIn` is the same claim as a 401 arriving from the wire: the request
    /// carried no session the account would accept. A 403 is not — that session authenticated and
    /// lacks the access, which signing in again cannot repair.
    func testASessionlessRequestIsARejectionAndAForbiddenOneIsNot() async {
        let sessionless = Self.failing(with: OmiAPIError.notSignedIn)
        _ = await sessionless.read(since: nil, until: nil, limit: 50)
        let sessionlessReason = await sessionless.unreachableReason()
        XCTAssertEqual(sessionlessReason, .keyRejected)

        let forbidden = Self.failing(with: OmiAPIError.http(403, ""))
        _ = await forbidden.read(since: nil, until: nil, limit: 50)
        let forbiddenReason = await forbidden.unreachableReason()
        XCTAssertEqual(
            forbiddenReason, .noAnswer,
            "access is not identity — telling the user to sign in again would be advice that cannot work")
    }

    /// A 429 that outlived `OmiAPI`'s retries. It must be told apart from a rejection (auth is not
    /// the problem), from an outage (something *did* answer), and above all from an empty account.
    func testARateLimitedAccountSaysSoRatherThanRenderingAsEmpty() async {
        let limited = Self.failing(with: OmiAPIError.http(429, ""))

        let result = await limited.read(since: nil, until: nil, limit: 50)

        let reason = await limited.unreachableReason()
        XCTAssertFalse(result.reachable, "a rate-limited account is not an empty one")
        XCTAssertEqual(
            reason, .rateLimited,
            "neither a rejected session nor \"nobody answered\" — the account answered, and said wait")
    }

    /// When the three sources fail for different reasons, the reader is told the one they can act
    /// on. A rejection means "sign in again"; a rate limit only means "wait", so it does not outrank
    /// it, and a 5xx is not something the reader can do anything with at all.
    func testARejectedSessionOutranksARateLimit() async {
        let feed = OmiActivityFeed(
            isAirgapped: { false },
            isSignedIn: { true },
            fetchConversations: { _ in throw OmiAPIError.http(401, "") },
            fetchMemories: { _ in throw OmiAPIError.http(429, "") },
            fetchTasks: { _ in throw OmiAPIError.http(503, "") })

        let result = await feed.read(since: nil, until: nil, limit: 50)

        let reason = await feed.unreachableReason()
        XCTAssertFalse(result.reachable)
        XCTAssertEqual(reason, .keyRejected, "the one of the three the user can do something about")
    }

    /// The airgap and signed-out reasons are what let the empty copy say something other than "I
    /// couldn't reach it" for two states that are not failures at all.
    func testTheReasonNamesAirgapAndSignedOutSeparately() async {
        let airgapped = OmiActivityFeed(
            isAirgapped: { true }, isSignedIn: { true },
            fetchConversations: { _ in [] }, fetchMemories: { _ in [] }, fetchTasks: { _ in Self.emptyPage })
        _ = await airgapped.read(since: nil, until: nil, limit: 50)
        let airgapReason = await airgapped.unreachableReason()
        XCTAssertEqual(airgapReason, .airgapped)

        let signedOut = OmiActivityFeed(
            isAirgapped: { false }, isSignedIn: { false },
            fetchConversations: { _ in [] }, fetchMemories: { _ in [] }, fetchTasks: { _ in Self.emptyPage })
        _ = await signedOut.read(since: nil, until: nil, limit: 50)
        let signedOutReason = await signedOut.unreachableReason()
        XCTAssertEqual(signedOutReason, .signedOut)
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
    /// user can repair must not become a poll. A refused session would be re-refused on every
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
        XCTAssertEqual(attempts, 1, "a session the account refused is not a thing to ask about on a timer")
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

    /// **A feed that answered for two sources out of three is still a failure for the third.**
    ///
    /// It reads as a success — `reachable` is true, because the account did answer — and the ladder
    /// used to reset on it, so a source that 503'd stayed missing for the whole window while the
    /// panel looked perfectly healthy. That is not hypothetical: it is the state the backend was in
    /// when the account cache was written, with `/v1/conversations` serving and `/v3/memories`
    /// returning 503. With the cache in front of it the missing source is now *drawn* from the last
    /// good answer, which makes the schedule matter more rather than less — an unrefreshed panel
    /// showing hours-old memories under a live-looking header is exactly what the cache must not
    /// become.
    @MainActor
    func testAPartialAnswerIsReadAgainUntilEverySourceAnswers() async throws {
        let account = PartialAccount([
            [.conversations, .tasks], [.conversations, .tasks], Set(ActivityAccountSource.allCases),
        ])
        let store = ActivityStore(
            store: { nil }, account: account, accountRetryDelays: Self.immediateLadder)

        store.start()
        try await Self.waitUntil("the missing source never came back") {
            await account.reads == 3
        }

        XCTAssertTrue(store.accountReachable, "two sources answering is a reachable account")
        XCTAssertNil(store.accountUnreachableReason)
    }

    /// And it is bounded on the same terms as every other failure here. A source that is permanently
    /// down must not turn the panel into a poll for the life of the window — `accountRereads` is not
    /// reset by a partial answer, which is what makes the ladder run out.
    @MainActor
    func testAPermanentlyHalfDeadAccountIsNotPolledForever() async throws {
        let account = PartialAccount([[.conversations]])
        let store = ActivityStore(
            store: { nil }, account: account, accountRetryDelays: Self.immediateLadder)

        store.start()
        try await Self.waitUntil("the ladder never ran out") {
            await account.reads == Self.immediateLadder.count + 1
        }
        // Long enough for another rung to have fired if one had been queued.
        try await Task.sleep(for: .milliseconds(50))

        let reads = await account.reads
        XCTAssertEqual(reads, Self.immediateLadder.count + 1, "the first read, then the whole ladder")
    }

    // MARK: - Conversations

    func testConversationsDecodeWithNullTitlesAndTimestamps() async throws {
        let result = await Self.feed(
            conversations: try Self.decode([WireConversation].self, Self.conversationsJSON),
            memories: [], tasks: Self.emptyPage, now: { Self.placement })
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

        let blank = result.conversations[1]
        XCTAssertEqual(blank.title, "Untitled conversation", "a blank title must never render an empty row")
        XCTAssertNil(blank.overview, "an empty overview is nothing to show, not an empty line")
        XCTAssertEqual(blank.startedAt, Self.placement, "an undated conversation sits at the window edge")
        XCTAssertEqual(blank.finishedAt, Self.placement)

        let naive = result.conversations[2]
        // `2026-08-13 11:30:00`: no zone, space-separated. Read as UTC, which is what the backend
        // itself does with a naive timestamp — reading it as local time would move it by hours.
        XCTAssertEqual(naive.startedAt, Self.utc(2026, 8, 13, 11, 30, 0), accuracy: 0.001)
        XCTAssertEqual(naive.finishedAt, naive.startedAt, "a missing finish cannot precede the start")
    }

    /// **The emoji the account chose, on the rows it chose one for.** This is the reason
    /// `/v1/conversations` is worth reading at all: `SimpleStructured` on the MCP route carried no
    /// `emoji` field, so every conversation in the panel wore the same fallback glyph regardless of
    /// what the account had picked. `Structured.emoji` is a declared field, and the fallback now
    /// only stands in where the extractor genuinely produced nothing.
    func testTheAccountsOwnEmojiSurvivesAndOnlyABlankOneFallsBack() async throws {
        let result = await Self.feed(
            conversations: try Self.decode([WireConversation].self, Self.conversationsJSON),
            memories: [], tasks: Self.emptyPage, now: { Self.placement })
            .read(since: nil, until: nil, limit: 50)

        XCTAssertEqual(result.conversations[0].emoji, "🎙️", "an emoji the account did send must survive")
        XCTAssertEqual(
            result.conversations[1].emoji, WireConversation.defaultEmoji,
            "an empty string is the backend's \"no emoji\", not an emoji")
        XCTAssertEqual(result.conversations[2].emoji, WireConversation.defaultEmoji, "null falls back too")
        XCTAssertEqual(WireConversation.defaultEmoji, "🧠", "the same glyph the rest of Omi defaults to")
    }

    // MARK: - Memories

    /// **A windowed read must still carry every memory the page held. Do not add a filter here.**
    ///
    /// This test exists to stop the obvious-looking repair, so read this before "fixing" it: the
    /// window `read(since:until:)` carries is not a filter, it is a placement hint, and the rows
    /// below are deliberately scattered days on either side of it. Two reasons, and the second one
    /// is the defect this was written from:
    ///
    /// 1. `GET /v3/memories` has no date parameter of any kind — `limit`, `offset`, `cursor`,
    ///    `device_scope` and nothing else — so a windowed memory read can only ever be done in the
    ///    client, over whatever rows the newest page happened to contain. That set is not "the
    ///    memories from that day" and cannot be made into it by filtering.
    /// 2. **A memory does not belong to the day it was created.** A memory whose `conversation_id`
    ///    names a conversation on screen is filed under *that conversation's* day by the composer.
    ///    Dropping rows here by their own instant throws away precisely the ones composition would
    ///    have re-seated, which is how a day full of conversations renders with none of the memories
    ///    those conversations produced. The user's report was that memories and conversations were
    ///    "still not loading properly", and this was why.
    ///
    /// Windowing is `ActivityComposer`'s job, over rows already in hand. This file's job is to hand
    /// it the newest page intact.
    func testAWindowedReadStillCarriesEveryMemoryThePageHeld() async throws {
        let result = await Self.feed(
            conversations: [], memories: try Self.decode([WireMemory].self, Self.memoriesJSON),
            tasks: Self.emptyPage, now: { Self.placement })
            .read(since: Self.windowStart, until: Self.windowEnd, limit: 50)

        XCTAssertEqual(
            result.memories.map(\.id), ["mem-learned", "mem-before", "mem-updated", "mem-undated", "mem-after"],
            "every row the page held — including the ones days before and days after the window")
        XCTAssertEqual(result.memories[0].content, "Prefers espresso")
        XCTAssertEqual(
            result.memories[1].at, Self.utc(2026, 8, 10, 8, 0, 0), accuracy: 0.001,
            "three days before `since`, and still here")
        XCTAssertEqual(
            result.memories[4].at, Self.utc(2026, 8, 20, 9, 0, 0), accuracy: 0.001,
            "a week after `until`, and still here")

        // The blank-content row and the one with no `id` are the only two that ever go: neither can
        // be rendered as a row at all, which is a different claim from "not in this window".
        XCTAssertFalse(result.memories.contains { $0.content.trimmingCharacters(in: .whitespaces).isEmpty })
    }

    /// **When a memory was *learned*, not when its row was written.** `captured_at` and `created_at`
    /// are hours or days apart for anything that arrived in a batch — an import, a backfill, a phone
    /// that was offline all day — so preferring the second one files a memory on the day the server
    /// got round to it. This is the order the shipping macOS app reads for the same screen.
    func testMemoryPlacementPrefersWhenItWasLearned() async throws {
        let result = await Self.feed(
            conversations: [], memories: try Self.decode([WireMemory].self, Self.memoriesJSON),
            tasks: Self.emptyPage, now: { Self.placement })
            .read(since: Self.windowStart, until: Self.windowEnd, limit: 50)

        XCTAssertEqual(
            result.memories[0].at, Self.utc(2026, 8, 13, 9, 15, 0) + 0.482, accuracy: 0.001,
            "`captured_at` wins over a `created_at` written twelve hours later")
        XCTAssertEqual(
            result.memories[1].at, Self.utc(2026, 8, 10, 8, 0, 0), accuracy: 0.001,
            "no `captured_at`, so the row's creation is the best we know")
        XCTAssertEqual(
            result.memories[2].at, Self.utc(2026, 8, 13, 18, 0, 0), accuracy: 0.001,
            "neither, so `updated_at` — still an instant the account vouches for")
        XCTAssertEqual(
            result.memories[3].at, Self.windowEnd,
            "none of the three: the window's upper edge, because this page is read newest-first")
    }

    /// The upper edge is the *caller's* `until`, and `now` only when there is no window at all — an
    /// undated row has to land somewhere the reader would look, not at the epoch.
    func testAnUndatedMemoryFallsBackToNowWhenThereIsNoWindow() async throws {
        let result = await Self.feed(
            conversations: [], memories: try Self.decode([WireMemory].self, Self.memoriesJSON),
            tasks: Self.emptyPage, now: { Self.placement })
            .read(since: nil, until: nil, limit: 50)

        XCTAssertEqual(result.memories.map(\.id).count, 5, "an unbounded read drops nothing either")
        XCTAssertEqual(result.memories[3].at, Self.placement, "no upper bound, so the undated row sits at `now`")
    }

    // MARK: - Tasks

    /// `GET /v1/action-items` answers with `ActionItemsResponse` — an **object**, where the other two
    /// routes answer with bare arrays. Decoding it as an array is the whole page arriving as nothing.
    func testTheActionItemPageDecodesFromAnObject() async throws {
        let page = try Self.decode(WireActionItemPage.self, Self.tasksPageJSON)

        XCTAssertEqual(page.actionItems.count, 4)
        XCTAssertTrue(page.hasMore, "the field the response model declares, read rather than assumed")
    }

    /// `items` is the spelling the shipping macOS client also accepts, and this reads both for the
    /// same reason it does: the cost is one line, and the failure it avoids is a silently empty page.
    func testTheAlternateItemsSpellingDecodesToo() async throws {
        let page = try Self.decode(
            WireActionItemPage.self,
            """
            { "items": [ { "id": "task-9", "description": "Renew the domain" } ] }
            """)

        XCTAssertEqual(page.actionItems.count, 1)
        XCTAssertFalse(page.hasMore, "absent `has_more` is \"no more\", not a decoding failure")
    }

    /// A page carrying neither key must come back empty rather than throw. One unrecognised page
    /// shape costs the tasks; a throw here would cost the reachability of the whole read.
    func testAPageWithNeitherKeyYieldsNoTasksRatherThanThrowing() async throws {
        let page = try Self.decode(WireActionItemPage.self, #"{ "has_more": false }"#)
        XCTAssertTrue(page.actionItems.isEmpty)

        let result = await Self.feed(conversations: [], memories: [], tasks: page)
            .read(since: nil, until: nil, limit: 50)

        XCTAssertTrue(result.reachable, "the source answered — it just had nothing in it")
        XCTAssertTrue(result.tasks.isEmpty)
    }

    func testTasksPreferTheDueDateAndDefaultToNotCompleted() async throws {
        let result = await Self.feed(
            conversations: [], memories: [],
            tasks: try Self.decode(WireActionItemPage.self, Self.tasksPageJSON),
            now: { Self.placement })
            .read(since: nil, until: nil, limit: 50)

        // `task-3` is gone: `description` is the wire name for the row's text, and an empty one is
        // the "never an empty row" failure wearing a value.
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

    // MARK: - Timestamps

    /// Three shapes are in the wild across these routes, and one unreadable date must never cost the
    /// page it arrived on. The zoneless case is the load-bearing one: `Foundation` refuses it
    /// outright, and the tempting repair — letting it parse as *local* time — would silently move an
    /// instant by hours in whichever direction this Mac happens to sit from UTC.
    func testWireInstantReadsEveryTimestampShapeTheseRoutesSend() throws {
        // Tz-aware, with microseconds Pydantic emits and `ISO8601DateFormatter` cannot hold.
        XCTAssertEqual(
            try XCTUnwrap(WireInstant.parse("2026-08-13T09:00:00.123456+00:00")),
            Self.utc(2026, 8, 13, 9, 0, 0) + 0.123, accuracy: 0.001)
        XCTAssertEqual(
            try XCTUnwrap(WireInstant.parse("2026-08-13T06:00:00-03:00")),
            Self.utc(2026, 8, 13, 9, 0, 0), accuracy: 0.001, "an offset that is not UTC still resolves to UTC")

        // No zone at all, in both the `T` and the `str(datetime)` spelling. Read as UTC.
        XCTAssertEqual(
            try XCTUnwrap(WireInstant.parse("2026-08-13T11:30:00")),
            Self.utc(2026, 8, 13, 11, 30, 0), accuracy: 0.001)
        XCTAssertEqual(
            try XCTUnwrap(WireInstant.parse("2026-08-13 11:30:00.482913")),
            Self.utc(2026, 8, 13, 11, 30, 0) + 0.482, accuracy: 0.001)

        // Anything unreadable is "no timestamp", never a throw.
        XCTAssertNil(WireInstant.parse(""))
        XCTAssertNil(WireInstant.parse("   "))
        XCTAssertNil(WireInstant.parse("last Tuesday"))

        // And through the decoder, where the third shape lives: a bare number of seconds, and a null
        // that must not take the row down with it.
        let decoded = try Self.decode([WireInstant].self, #"["2026-08-13T09:00:00Z", 1786000000.5, null, "?"]"#)
        XCTAssertEqual(try XCTUnwrap(decoded[0].seconds), Self.utc(2026, 8, 13, 9, 0, 0), accuracy: 0.001)
        XCTAssertEqual(try XCTUnwrap(decoded[1].seconds), 1_786_000_000.5, accuracy: 0.001)
        XCTAssertNil(decoded[2].seconds)
        XCTAssertNil(decoded[3].seconds)
    }

    // MARK: - The window on the wire

    /// **No source is fetched by date, and the window the caller passed reaches none of them.** The
    /// shipping macOS app's own spine passes a nil date range and takes the most recent page, and
    /// its time control is a predicate over rows already composed. A date-windowed fetch reads as
    /// the more efficient design and is the bug: `/v3/memories` has no date parameter to window
    /// with, and a memory is filed under its conversation's day rather than its own, so bounding the
    /// fetch discards the rows composition would have re-seated.
    ///
    /// What does reach the wire is the page bound and the two filters that are about *what a row is*
    /// rather than when it happened.
    func testNoSourceIsFetchedByDateAndTheLimitIsClamped() async throws {
        let recorder = QueryRecorder()
        let feed = OmiActivityFeed(
            isAirgapped: { false },
            isSignedIn: { true },
            fetchConversations: { await recorder.record("conversations", $0); return [] },
            fetchMemories: { await recorder.record("memories", $0); return [] },
            fetchTasks: { await recorder.record("action-items", $0); return Self.emptyPage })

        _ = await feed.read(since: Self.windowStart, until: Self.windowEnd, limit: 5000)

        let conversations = await recorder.query("conversations")
        // The endpoint does accept `start_date`/`end_date`. They are not sent, and that is the
        // point: the newest page, then compose, then filter.
        XCTAssertNil(conversations?["start_date"], "the conversation fetch is not windowed by date")
        XCTAssertNil(conversations?["end_date"], "the conversation fetch is not windowed by date")
        // Clamped: this draws a panel, not an account export.
        XCTAssertEqual(conversations?["limit"], "200")
        XCTAssertEqual(conversations?["offset"], "0")
        // Sent rather than left to the server's defaults, because the default is `True` and a
        // conversation the user threw away has no business on a timeline of their day.
        XCTAssertEqual(conversations?["include_discarded"], "false")
        XCTAssertEqual(conversations?["statuses"], "completed,processing")
        XCTAssertNil(conversations?["sources"], "filtering to this Mac would hide everything the phone heard")

        let memories = await recorder.query("memories")
        XCTAssertEqual(memories?["limit"], "200")
        XCTAssertEqual(memories?["offset"], "0")
        // This endpoint has no date parameter of any kind to send even if we wanted one.
        for absent in ["start_date", "end_date", "updated_after", "cursor"] {
            XCTAssertNil(memories?[absent], "`/v3/memories` accepts no \(absent)")
        }
        // Its default is `all`, which is what this wants; sending `current` is what makes the
        // backend 400 for an account without the canonical lifecycle.
        XCTAssertNil(memories?["device_scope"])

        let tasks = await recorder.query("action-items")
        XCTAssertEqual(tasks?["limit"], "200")
        // Deliberate for a second reason on top of the shared one: `start_date` bounds creation and
        // `due_start_date` bounds the due date, so windowing by either would drop the undated
        // commitments that matter most.
        XCTAssertNil(tasks?["due_start_date"])
        XCTAssertNil(tasks?["start_date"])
    }

    // MARK: - Fixtures

    /// A page as `GET /v1/conversations` sends it — `List[Conversation]`, whose `structured` is the
    /// full `Structured` model: the complete row with the emoji the account chose, one whose title,
    /// overview and emoji are blank and whose timestamps are null, one with a tz-naive
    /// space-separated start, a null emoji and no finish at all, and one with no `id`.
    private static let conversationsJSON = """
        [
          {
            "id": "conv-1",
            "created_at": "2026-08-13T09:45:00Z",
            "started_at": "2026-08-13T09:00:00.123456+00:00",
            "finished_at": "2026-08-13T09:42:10Z",
            "structured": {
              "title": "Standup with Mila",
              "overview": "Shipping the spine on Thursday.",
              "emoji": "🎙️",
              "category": "work",
              "action_items": [],
              "events": []
            },
            "status": "completed",
            "source": "omi",
            "language": "en",
            "discarded": false,
            "apps_results": []
          },
          {
            "id": "conv-2",
            "created_at": null,
            "started_at": null,
            "finished_at": null,
            "structured": {
              "title": "   ",
              "overview": "",
              "emoji": "",
              "category": "other",
              "action_items": [],
              "events": []
            },
            "status": "completed",
            "discarded": false,
            "apps_results": []
          },
          {
            "id": "conv-3",
            "started_at": "2026-08-13 11:30:00",
            "structured": {
              "title": "Reading",
              "overview": "Notes on the spine.",
              "emoji": null,
              "category": "personal",
              "action_items": [],
              "events": []
            },
            "status": "completed"
          },
          {
            "started_at": "2026-08-13T12:00:00Z",
            "structured": { "title": "No id", "overview": "dropped", "emoji": "📚", "category": "other" }
          }
        ]
        """

    /// `List[MemoryDB]` as `GET /v3/memories` sends it. The rows are named for what each one proves
    /// rather than numbered, because two separate claims are read off this one page: which timestamp
    /// places a memory, and that the window drops none of them. So they are deliberately scattered
    /// around `windowStart`…`windowEnd` — one learned inside it whose row was written half a day
    /// later, one three days before, one placed by `updated_at` alone, one with no timestamp at all,
    /// and one a week after — plus a blank-content row and one with no `id`, the only two that a
    /// reader can genuinely do nothing with.
    private static let memoriesJSON = """
        [
          {
            "id": "mem-learned",
            "content": "Prefers espresso",
            "category": "core",
            "captured_at": "2026-08-13T09:15:00.482913+00:00",
            "created_at": "2026-08-13T21:30:00Z",
            "updated_at": "2026-08-13T21:30:00Z",
            "reviewed": true,
            "manually_added": false,
            "deleted": false
          },
          {
            "id": "mem-before",
            "content": "Ships on Thursdays",
            "category": "work",
            "created_at": "2026-08-10T08:00:00Z",
            "updated_at": "2026-08-10T08:00:00Z"
          },
          {
            "id": "mem-updated",
            "content": "Only ever updated",
            "category": "core",
            "captured_at": null,
            "created_at": null,
            "updated_at": "2026-08-13T18:00:00Z"
          },
          { "id": "mem-undated", "content": "No timestamp at all", "category": "core" },
          {
            "id": "mem-after",
            "content": "Next week's",
            "category": "core",
            "captured_at": "2026-08-20T09:00:00Z",
            "created_at": "2026-08-20T09:00:00Z",
            "updated_at": "2026-08-20T09:00:00Z"
          },
          { "id": "mem-blank", "content": "   ", "category": "core", "captured_at": "2026-08-13T10:00:00Z" },
          { "content": "no id", "category": "core", "captured_at": "2026-08-13T10:00:00Z" }
        ]
        """

    /// `ActionItemsResponse` — an object, not an array — carrying `ActionItemResponse` rows, whose
    /// wire name for the row's text is `description`.
    private static let tasksPageJSON = """
        {
          "action_items": [
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
          ],
          "has_more": true
        }
        """

    // MARK: - Helpers

    /// Stands in for "now", so a row placed there is provably placed rather than accidentally right.
    private static let placement: Double = 1_786_000_500

    /// The day the memory fixtures are arranged around, as the caller would ask for it.
    private static let windowStart = utc(2026, 8, 13, 0, 0, 0)
    private static let windowEnd = utc(2026, 8, 14, 0, 0, 0)

    private static let emptyPage = WireActionItemPage(actionItems: [])

    private actor CallCounter {
        private(set) var count = 0
        func hit() { count += 1 }
    }

    /// Every source failing the same way, for the tests that are only about how a failure is
    /// classified once nothing has answered.
    private static func failing(with error: OmiAPIError) -> OmiActivityFeed {
        OmiActivityFeed(
            isAirgapped: { false },
            isSignedIn: { true },
            fetchConversations: { _ in throw error },
            fetchMemories: { _ in throw error },
            fetchTasks: { _ in throw error })
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

    /// An account that answers for some sources and not others, one scripted read at a time. The
    /// last entry is repeated once the script runs out, so a permanently half-dead account is one
    /// entry long.
    private actor PartialAccount: ActivityAccountReading {
        private let answers: [Set<ActivityAccountSource>]
        private(set) var reads = 0

        init(_ answers: [Set<ActivityAccountSource>]) {
            self.answers = answers
        }

        func read(since: Double?, until: Double?, limit: Int) async -> ActivityAccountFeed {
            let answered = answers[min(reads, answers.count - 1)]
            reads += 1
            return ActivityAccountFeed(answered: answered)
        }
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
        tasks: WireActionItemPage,
        now: @escaping @Sendable () -> Double = { placement }
    ) -> OmiActivityFeed {
        OmiActivityFeed(
            isAirgapped: { false },
            isSignedIn: { true },
            fetchConversations: { _ in conversations },
            fetchMemories: { _ in memories },
            fetchTasks: { _ in tasks },
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
