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
        // Empty, not the fallback. Both fallbacks live on `ActivityConversation`, applied once for
        // the account's conversations and this Mac's alike; substituting here would make the model's
        // own unreachable for every account row and let two conversations in the same state — one
        // heard here, one the account sent — wear different words. The row is still never blank:
        // `ActivityConversation.untitled` is what it renders.
        XCTAssertEqual(blank.title, "", "a blank title is passed through for the model to resolve")
        XCTAssertEqual(
            ActivityConversation.untitled, "Untitled conversation",
            "and the model's fallback is the reference's own")
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
        // **Empty, not a glyph.** The seam passes "the account chose none" through as empty and
        // `ActivityConversation` substitutes `💬` for both halves of the spine in one place — the
        // arrangement the reference uses. A fallback applied here would make the model's own
        // unreachable for every account row, and would let a local conversation with nothing to show
        // wear a different glyph from an account one in the same state.
        XCTAssertEqual(
            result.conversations[1].emoji, "",
            "an empty string is the backend's \"no emoji\", and stays empty for the model to resolve")
        XCTAssertEqual(result.conversations[2].emoji, "", "null is passed through the same way")
        XCTAssertEqual(
            ActivityConversation.defaultEmoji, "💬",
            "and the model's fallback is the reference's own client-side default")
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
        // **Created, not due** — `task-1` carries a `due_at` of 14 August and is placed on 1 August,
        // when it was written. `SpineTask.timestamp` is `task.createdAt` and nothing else, and
        // anchoring on the due date instead put every dated commitment in the *future*: the list
        // opened on a day seven weeks out, with today's capture buried below it, and every task
        // stamped 11:59 PM because that is what a date with no time means.
        XCTAssertEqual(result.tasks[0].at, Self.utc(2026, 8, 1, 9, 0, 0), accuracy: 0.001)

        XCTAssertTrue(result.tasks[1].completed)
        XCTAssertEqual(result.tasks[1].at, Self.utc(2026, 8, 2, 9, 0, 0), accuracy: 0.001)

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

// MARK: - The first page of memories is a different backend branch

extension OmiActivityFeedTests {

    /// `offset == 0` and `offset > 0` are two implementations behind one endpoint, and only one of
    /// them currently works for real accounts.
    ///
    /// `GET /v3/memories` sends a zero offset to a Firestore *keyset* scan whose failures surface as
    /// `503 Canonical memory unavailable`; a non-zero offset loads the set and slices it in Python,
    /// touching no keyset query at all. Observed live on this account, four seconds apart: the
    /// shipping Omi app's `offset: 0` refresh 503'd while its `offset > 0` pages returned 100 rows
    /// each. A client that only ever asks for the first page therefore gets **nothing**, which is
    /// exactly where this surface was — every memory or none.
    func testAnUnavailableFirstPageIsAskedAgainFromTheSecondRow() async throws {
        let asked = AskedQueries()
        let rows = try Self.decode([WireMemory].self, Self.memoriesJSON)
        let feed = OmiActivityFeed(
            isAirgapped: { false },
            isSignedIn: { true },
            fetchConversations: { _ in [] },
            fetchMemories: { query in
                await asked.record(query)
                guard query["offset"] != "0" else { throw OmiAPIError.http(503, "Canonical memory unavailable") }
                return rows
            },
            fetchTasks: { _ in Self.emptyPage },
            now: { Self.placement })

        let result = await feed.read(since: nil, until: nil, limit: 50)

        XCTAssertFalse(result.memories.isEmpty, "a 503 on the first page must not empty the column")
        XCTAssertTrue(result.reachable)
        let offsets = await asked.offsets
        XCTAssertEqual(offsets, ["0", "1"], "asked for the first page, then stepped one row past it")
    }

    /// One retry, not a ladder. The second refusal is the account's answer, and a surface that
    /// answered a 503 by walking the offset forward would spend a request per row.
    func testASecondRefusalIsNotWalkedFurtherForward() async throws {
        let asked = AskedQueries()
        let feed = OmiActivityFeed(
            isAirgapped: { false },
            isSignedIn: { true },
            fetchConversations: { _ in try Self.decode([WireConversation].self, Self.conversationsJSON) },
            fetchMemories: { query in
                await asked.record(query)
                throw OmiAPIError.http(503, "Canonical memory unavailable")
            },
            fetchTasks: { _ in Self.emptyPage },
            now: { Self.placement })

        let result = await feed.read(since: nil, until: nil, limit: 50)

        let offsets = await asked.offsets
        XCTAssertEqual(offsets, ["0", "1"], "exactly two attempts, ever")
        XCTAssertTrue(result.memories.isEmpty)
        // Conversations answered, so the feed still carries what it has.
        XCTAssertTrue(result.reachable)
    }

    /// Anything that is *not* a 503 is not the branch split, so stepping the offset would spend a
    /// request to be told the same thing.
    func testAFailureThatIsNotAFirstPageOutageIsNotRetried() async throws {
        let asked = AskedQueries()
        let feed = OmiActivityFeed(
            isAirgapped: { false },
            isSignedIn: { true },
            fetchConversations: { _ in [] },
            fetchMemories: { query in
                await asked.record(query)
                throw OmiAPIError.http(500, "")
            },
            fetchTasks: { _ in Self.emptyPage },
            now: { Self.placement })

        _ = await feed.read(since: nil, until: nil, limit: 50)

        let offsets = await asked.offsets
        XCTAssertEqual(offsets, ["0"], "a 500 is asked once and reported")
    }
}

/// The queries a fetcher was actually handed, in order.
private actor AskedQueries {
    private(set) var queries: [[String: String]] = []
    func record(_ query: [String: String]) { queries.append(query) }
    var offsets: [String] { queries.map { $0["offset"] ?? "absent" } }
}

// MARK: - One read is one page, and successive reads walk the account in

/// **The defect these are written from: the reader only ever held the first page.**
///
/// Every source came back at `maxPerSource` on the real account — the app's own log said
/// `200 conversations, 200 memories, 200 tasks` — while the shipping Omi app beside it had already
/// paged 1,996 rows in and was still going. A first page is not a corpus, and nothing downstream can
/// tell the two apart from the outside.
///
/// So the reader carries a cursor and each successive read fetches the next page of exactly one
/// source, round-robin, answering with everything gathered so far. What follows is the whole of that
/// contract: where the next page starts, what ends a source, and what bounds it when nothing does.
extension OmiActivityFeedTests {

    /// Successive reads walk every source in, one page per read, and the answer is cumulative.
    ///
    /// **One request in flight, and only the first read races.** The opening read is the one the
    /// panel's first paint is blocked on, so its three sources go together; every page behind it
    /// lands under a list the reader can already use, where a second concurrent request buys nothing
    /// and spends someone's account — which is how this surface got itself rate limited off
    /// `/v1/mcp/*` in the first place.
    func testSuccessiveReadsPageEverySourceInOneAtATime() async {
        let backend = PagingBackend(conversations: 5, memories: 5, tasks: 5)
        let feed = Self.feed(over: backend)

        let last = await Self.readUntilSettled(feed, limit: 2)

        XCTAssertEqual(last.conversations.count, 5, "every page, not the first one")
        XCTAssertEqual(last.memories.count, 5)
        XCTAssertEqual(last.tasks.count, 5)
        XCTAssertEqual(
            last.conversations.map(\.id), ["c0", "c1", "c2", "c3", "c4"],
            "in the order the account sent them, with no row arriving twice")

        // **A short page is not the last page** — `ServerPaging`'s rule, and the reason for the
        // request at offset 5. These routes fetch `limit` documents and then drop the discarded and
        // unparseable ones in Python, so a page of one where two were asked for is routine and
        // reading it as the end is how the rest of an account disappears. Only the empty page ends
        // it, and it costs exactly one extra request per source.
        let conversationAsks = await backend.asks("conversations")
        XCTAssertEqual(conversationAsks, [0, 2, 4, 5], "0, 2, the short page at 4, then the empty one")
        let memoryAsks = await backend.asks("memories")
        XCTAssertEqual(memoryAsks, [0, 2, 4, 5])
        // Except for the one source that can say so itself: `/v1/action-items` answers with an
        // authoritative `has_more`, so there is no empty page to spend a request on.
        let taskAsks = await backend.asks("tasks")
        XCTAssertEqual(taskAsks, [0, 2, 4], "`has_more: false` is the end, without a page to prove it")
    }

    /// **The one row the memories step spends is the only row it spends.**
    ///
    /// `GET /v3/memories` at `offset: 0` runs a Firestore keyset scan that 503s for real accounts,
    /// so the first page is re-asked from `offset: 1` — see `attemptMemories`. That costs the newest
    /// memory, deliberately and once. The danger is the *next* page: a cursor that advanced by the
    /// page size from the offset it asked for (0 + 2) rather than from the one the request carried
    /// (1 + 2) would step back over a row it already holds, or — with the arithmetic the other way
    /// round — skip one it never fetched. Neither is visible on screen; both are silent holes in the
    /// account.
    func testTheSteppedFirstMemoryPageNeitherSkipsNorRepeatsARow() async {
        let backend = PagingBackend(conversations: 0, memories: 5, tasks: 0, memoriesFirstPageFails: true)
        let feed = Self.feed(over: backend)

        let last = await Self.readUntilSettled(feed, limit: 2)

        XCTAssertEqual(
            last.memories.map(\.id), ["m1", "m2", "m3", "m4"],
            "every memory but the newest, which is the documented cost of the step — and each once")
        let asks = await backend.asks("memories")
        XCTAssertEqual(
            asks, [0, 1, 3, 5],
            "asked at 0, stepped to 1, and then advanced from the offset the request actually used")
        XCTAssertTrue(last.memoriesBeginPastHead, "the page began past its own head, and says so")
    }

    /// A source that keeps failing stops being asked, and its rows are never presented as complete.
    ///
    /// Three attempts is the reference's stall limit, for the reference's reason: one page can fail
    /// for a reason the next will not repeat, three in a row is an endpoint that is down, and a
    /// client that answers a refusal by asking again is how a limit stays tripped. It stays out of
    /// `answered` for as long as it is failing, which is what keeps the corner saying "still
    /// counting" over a corpus that really is incomplete.
    func testAFailingSourceIsBoundedAndIsNeverReportedAsAnswered() async {
        let backend = PagingBackend(conversations: 5, memories: 5, tasks: 0, failing: ["memories"])
        let feed = Self.feed(over: backend)

        let last = await Self.readUntilSettled(feed, limit: 2)

        let asks = await backend.asks("memories")
        XCTAssertEqual(asks.count, OmiActivityFeed.failureLimit, "three attempts, then it is left alone")
        XCTAssertFalse(
            last.answered.contains(.memories),
            "a source that is down has rows behind it, whatever the other two managed")
        XCTAssertTrue(last.answered.contains(.conversations), "and it does not take the others with it")
        XCTAssertEqual(last.conversations.count, 5)
    }

    /// **A backend that pages forever costs a bounded number of requests.** The account is walked
    /// in behind a live surface, so the failure mode of getting this wrong is not a wrong number on
    /// screen — it is this Mac asking someone's account for pages until the app is quit.
    func testAnEndlessBackendIsStoppedByThePageBudget() async {
        let backend = PagingBackend(conversations: .max, memories: 0, tasks: 0)
        let feed = Self.feed(over: backend)

        let last = await Self.readUntilSettled(feed, limit: 1, reads: OmiActivityFeed.maximumPagesPerSource * 2)

        let asks = await backend.asks("conversations")
        XCTAssertEqual(asks.count, OmiActivityFeed.maximumPagesPerSource, "the budget, and not one page more")
        XCTAssertFalse(
            last.answered.contains(.conversations),
            "it stopped with pages still behind it, so nothing may read what it holds as everything")
    }

    /// Reading past the end costs nothing. The store reads once more than it needs to — that is how
    /// it learns the account has run out — and that read must not be a request.
    func testReadingPastTheEndSendsNothing() async {
        let backend = PagingBackend(conversations: 1, memories: 1, tasks: 1)
        let feed = Self.feed(over: backend)

        _ = await Self.readUntilSettled(feed, limit: 2)
        let spent = await backend.asks("conversations").count + backend.asks("memories").count
            + backend.asks("tasks").count
        _ = await feed.read(since: nil, until: nil, limit: 2)
        _ = await feed.read(since: nil, until: nil, limit: 2)
        let after = await backend.asks("conversations").count + backend.asks("memories").count
            + backend.asks("tasks").count

        XCTAssertEqual(after, spent, "a settled corpus is answered from what is already held")
    }

    // MARK: - Driving the pages

    /// Reads until the reader stops asking for anything, the way `ActivityStore` does: again while
    /// the answer keeps growing, and once more to find out that it has stopped.
    // MARK: - Coming back to a settled corpus

    /// **The cursor only ever moves away from the newest row, and that is the one place new rows
    /// arrive.** Once every source is exhausted the reader answers `.settled` and makes no further
    /// request — correct while nothing behind the cursor changes, useless the moment somebody comes
    /// back to the panel an hour later. `refreshHead` is the reopening, and this is what it must
    /// cost: three requests at offset zero, not a second walk of the account.
    func testRefreshingTheHeadRereadsOffsetZeroWithoutWalkingTheAccountAgain() async {
        let backend = PagingBackend(conversations: 5, memories: 0, tasks: 0)
        let feed = Self.feed(over: backend)

        _ = await Self.readUntilSettled(feed, limit: 2)
        let walked = await backend.asks("conversations")
        XCTAssertEqual(walked, [0, 2, 4, 5], "precondition: the whole account is in")

        await feed.refreshHead()
        _ = await Self.readUntilSettled(feed, limit: 2)

        let reasked = await backend.asks("conversations")
        XCTAssertEqual(
            reasked, walked + [0], "one request at the head, and the walk is not repeated")
    }

    /// **The regression this pair of changes exists for, at the reader.** A conversation is
    /// uploaded before the backend has titled it, so the row the account first hands over is
    /// untitled; the title lands minutes later. A corpus whose de-duplication was
    /// first-sighting-wins would keep the untitled copy for the life of the process, which is the
    /// panel saying `Untitled conversation` over a conversation that has had a name for an hour.
    func testARowTheAccountHasSinceTitledReplacesTheUntitledCopy() async {
        let backend = RetitlingBackend()
        let feed = OmiActivityFeed(
            isAirgapped: { false },
            isSignedIn: { true },
            fetchConversations: { try await backend.conversations($0) },
            fetchMemories: { _ in [] },
            fetchTasks: { _ in WireActionItemPage(actionItems: []) },
            now: { Self.placement })

        let first = await feed.read(since: nil, until: nil, limit: 10)
        XCTAssertEqual(first.conversations.map(\.title), [""], "the backend has not named it yet")

        await backend.title("Design review")
        await feed.refreshHead()
        let second = await feed.read(since: nil, until: nil, limit: 10)

        XCTAssertEqual(second.conversations.count, 1, "one conversation, not two copies of one")
        XCTAssertEqual(second.conversations.map(\.title), ["Design review"])
    }

    /// Signing out. The reader now outlives a sign-out — it belongs to the process rather than to a
    /// panel — so everything the previous account handed over has to go, cursors included.
    func testForgettingDropsEveryRowAndReopensFromTheTop() async {
        let backend = PagingBackend(conversations: 3, memories: 0, tasks: 0)
        let feed = Self.feed(over: backend)

        let settled = await Self.readUntilSettled(feed, limit: 10)
        XCTAssertEqual(settled.conversations.count, 3, "precondition")

        await feed.forget()
        let after = await feed.read(since: nil, until: nil, limit: 10)

        let asks = await backend.asks("conversations")
        XCTAssertEqual(
            asks.last, 0, "the next read starts at the top, as a first read does")
        XCTAssertEqual(
            after.conversations.count, 3,
            "and what it holds is what this read returned, not what the last account said")
    }

    /// **The third of the sign-out races.** `read` fetches and *then* commits, so a `forget()` that
    /// lands between the two used to have its emptied corpus repopulated by the page already on its
    /// way back — the previous account's conversations, filed after the store had finished
    /// forgetting them. The epoch is captured before a request leaves and quoted by every commit.
    ///
    /// **The two accounts return different ids on purpose.** The corpus files rows by identity and
    /// replaces one it already holds, so a test where both reads return the same id cannot tell a
    /// surviving row from a re-fetched one — it passes with the fence torn out, which is worth
    /// nothing. Distinct ids make the difference a row count: one row if the sign-out was honoured,
    /// two if the previous account's page survived it.
    func testAPageFetchedBeforeSignOutIsNeverFiled() async {
        let gate = ReadGate()
        let calls = Counter()
        let feed = OmiActivityFeed(
            isAirgapped: { false },
            isSignedIn: { true },
            fetchConversations: { _ in
                let first = await calls.next() == 0
                // Only the first read — the one raced with the sign-out — is held.
                if first { await gate.arriveAndWait() }
                let id = first ? "previous-account" : "next-account"
                return [
                    WireConversation(
                        id: id, createdAt: nil, startedAt: WireInstant(seconds: 1_786_000_000),
                        finishedAt: nil,
                        structured: WireConversation.WireStructured(
                            title: id, overview: nil, emoji: "🎙️"))
                ]
            },
            fetchMemories: { _ in [] },
            fetchTasks: { _ in WireActionItemPage(actionItems: []) },
            now: { Self.placement })

        async let reading = feed.read(since: nil, until: nil, limit: 10)
        await gate.waitUntilArrived()

        // Sign-out, while the previous account's response is in flight.
        await feed.forget()
        await gate.open()
        _ = await reading

        // The read's own return value may carry what it fetched — it is a value, not state. What
        // must not have happened is the *filing*, so the next account's read sees its own row alone.
        let next = await feed.read(since: nil, until: nil, limit: 10)
        XCTAssertEqual(
            next.conversations.map(\.id), ["next-account"],
            "the previous account's page was in flight across the sign-out and must not be held")
    }

    /// **A revalidation has to be able to delete, and until the head became authoritative it could
    /// only add.** `reopenHead` re-reads offset zero and `absorb` replaces the ids it sees, so a
    /// conversation deleted on the phone stayed on the spine for the life of the process. That is a
    /// regression the process-lived store introduced: a panel rebuilt per window used to lose the
    /// row simply by being rebuilt.
    func testAHeadRereadDropsARowTheAccountHasStoppedListing() async {
        let backend = MutableHeadBackend(ids: ["c2", "c1", "c0"])
        let feed = Self.feed(overMutableHead: backend)

        let first = await feed.read(since: nil, until: nil, limit: 10)
        XCTAssertEqual(first.conversations.map(\.id), ["c2", "c1", "c0"], "precondition")

        // c1 is deleted on the phone.
        await backend.set(ids: ["c2", "c0"])
        await feed.refreshHead()
        let second = await feed.read(since: nil, until: nil, limit: 10)

        XCTAssertEqual(
            second.conversations.map(\.id), ["c2", "c0"],
            "a row absent from a re-read of the head, within the head's own range, has gone")
    }

    /// **And it may only delete within the range the head page actually covers.** A head page
    /// returned the newest `limit` rows and is evidence about nothing older; treating its absence as
    /// a deletion would empty the account behind it on every revalidation.
    func testAHeadRereadNeverDeletesRowsOlderThanItsOwnPage() async {
        let backend = MutableHeadBackend(ids: ["c4", "c3", "c2", "c1", "c0"])
        let feed = Self.feed(overMutableHead: backend)

        // Page the whole account in two at a time.
        let all = await Self.readUntilSettled(feed, limit: 2)
        XCTAssertEqual(all.conversations.count, 5, "precondition")

        // The head is re-read at a page size of two, so it can only speak for c4 and c3.
        await feed.refreshHead()
        let after = await Self.readUntilSettled(feed, limit: 2)

        XCTAssertEqual(
            Set(after.conversations.map(\.id)), ["c0", "c1", "c2", "c3", "c4"],
            "everything behind the head page is untouched by a re-read of it")
    }

    private static func feed(overMutableHead backend: MutableHeadBackend) -> OmiActivityFeed {
        OmiActivityFeed(
            isAirgapped: { false },
            isSignedIn: { true },
            fetchConversations: { try await backend.conversations($0) },
            fetchMemories: { _ in [] },
            fetchTasks: { _ in WireActionItemPage(actionItems: []) },
            now: { placement })
    }

    private static func readUntilSettled(
        _ feed: OmiActivityFeed, limit: Int, reads: Int = 40
    ) async -> ActivityAccountFeed {
        var last = await feed.read(since: nil, until: nil, limit: limit)
        for _ in 0..<reads {
            let next = await feed.read(since: nil, until: nil, limit: limit)
            let grew = next.rowCount > last.rowCount
            last = next
            if !grew { break }
        }
        return last
    }

    private static func feed(over backend: PagingBackend) -> OmiActivityFeed {
        OmiActivityFeed(
            isAirgapped: { false },
            isSignedIn: { true },
            fetchConversations: { try await backend.conversations($0) },
            fetchMemories: { try await backend.memories($0) },
            fetchTasks: { try await backend.tasks($0) },
            now: { placement })
    }
}

/// A backend that pages the way these three routes do, and remembers every offset it was asked for.
///
/// `conversations`/`memories`/`tasks` are row counts rather than fixtures because what is under test
/// is the arithmetic of the cursor: which offset the next page starts at, what ends a source, and
/// what happens when one of them will not answer at all. The row shapes themselves are covered by
/// the decoding tests above.
private actor PagingBackend {
    private let counts: [String: Int]
    /// Sources that refuse every request, however it is shaped.
    private let failing: Set<String>
    /// Whether `offset: 0` 503s, as `/v3/memories` currently does for real accounts.
    private let memoriesFirstPageFails: Bool
    private var asked: [String: [Int]] = [:]

    init(
        conversations: Int, memories: Int, tasks: Int,
        failing: Set<String> = [], memoriesFirstPageFails: Bool = false
    ) {
        counts = ["conversations": conversations, "memories": memories, "tasks": tasks]
        self.failing = failing
        self.memoriesFirstPageFails = memoriesFirstPageFails
    }

    func asks(_ source: String) -> [Int] { asked[source] ?? [] }

    func conversations(_ query: [String: String]) throws -> [WireConversation] {
        try page("conversations", query).map { index in
            WireConversation(
                id: "c\(index)", createdAt: nil, startedAt: WireInstant(seconds: 1_786_000_000 + Double(index)),
                finishedAt: nil,
                structured: WireConversation.WireStructured(title: "Talk \(index)", overview: nil, emoji: "🎙️"))
        }
    }

    func memories(_ query: [String: String]) throws -> [WireMemory] {
        let rows = try page("memories", query)
        return rows.map { index in
            WireMemory(
                id: "m\(index)", content: "Fact \(index)",
                capturedAt: WireInstant(seconds: 1_786_000_000 + Double(index)), createdAt: nil,
                updatedAt: nil, conversationId: nil)
        }
    }

    func tasks(_ query: [String: String]) throws -> WireActionItemPage {
        let rows = try page("tasks", query)
        let total = counts["tasks"] ?? 0
        let items = rows.map { index in
            WireActionItem(
                id: "t\(index)", text: "Do \(index)", completed: false,
                createdAt: WireInstant(seconds: 1_786_000_000 + Double(index)), dueAt: nil, completedAt: nil)
        }
        return WireActionItemPage(actionItems: items, hasMore: (rows.last.map { $0 + 1 } ?? 0) < total)
    }

    /// The rows one request covers, recording the offset it carried.
    private func page(_ source: String, _ query: [String: String]) throws -> Range<Int> {
        let offset = Int(query["offset"] ?? "0") ?? 0
        let limit = Int(query["limit"] ?? "1") ?? 1
        asked[source, default: []].append(offset)
        if failing.contains(source) { throw OmiAPIError.http(500, "") }
        if source == "memories", memoriesFirstPageFails, offset == 0 {
            throw OmiAPIError.http(503, "Canonical memory unavailable")
        }
        let total = counts[source] ?? 0
        guard offset < total else { return offset..<offset }
        return offset..<min(offset + limit, total)
    }
}

/// One conversation whose title the backend fills in later — the ordinary lifecycle of an uploaded
/// transcript, and the reason a corpus has to be able to replace a row it already holds.
private actor RetitlingBackend {
    private var currentTitle = ""

    func title(_ title: String) { currentTitle = title }

    func conversations(_ query: [String: String]) -> [WireConversation] {
        guard (Int(query["offset"] ?? "0") ?? 0) == 0 else { return [] }
        return [
            WireConversation(
                id: "c0", createdAt: nil, startedAt: WireInstant(seconds: 1_786_000_000),
                finishedAt: nil,
                structured: WireConversation.WireStructured(
                    title: currentTitle, overview: nil, emoji: "🎙️"))
        ]
    }
}

/// A latch that also reports when the request reached it, so a test can drive a sign-out into the
/// window between a fetch leaving and its response being filed.
private actor ReadGate {
    private var arrived = false
    private var isOpen = false
    private var waiters: [CheckedContinuation<Void, Never>] = []

    func arriveAndWait() async {
        arrived = true
        guard !isOpen else { return }
        await withCheckedContinuation { waiters.append($0) }
    }

    func waitUntilArrived() async {
        while !arrived { await Task.yield() }
    }

    func open() {
        isOpen = true
        for waiter in waiters { waiter.resume() }
        waiters = []
    }
}

/// A call counter, so a fetcher can answer differently for the read before a sign-out and the read
/// after it.
private actor Counter {
    private var count = 0
    func next() -> Int {
        defer { count += 1 }
        return count
    }
}

/// A conversations endpoint whose row set the test can change between reads, newest id first.
///
/// Instants descend with position so a page's "oldest row" is well defined — which is what bounds
/// what a head re-read is allowed to delete.
private actor MutableHeadBackend {
    private var ids: [String]

    init(ids: [String]) { self.ids = ids }

    func set(ids: [String]) { self.ids = ids }

    func conversations(_ query: [String: String]) -> [WireConversation] {
        let offset = Int(query["offset"] ?? "0") ?? 0
        let limit = Int(query["limit"] ?? "1") ?? 1
        guard offset < ids.count else { return [] }
        let page = ids[offset..<min(offset + limit, ids.count)]
        return page.enumerated().map { position, id in
            WireConversation(
                id: id, createdAt: nil,
                startedAt: WireInstant(seconds: 1_786_000_000 - Double(offset + position)),
                finishedAt: nil,
                structured: WireConversation.WireStructured(
                    title: id, overview: nil, emoji: "🎙️"))
        }
    }
}
