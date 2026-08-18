import Foundation
import XCTest

@testable import ContextApp

/// The memory column, read the way the shipping Omi app reads it: this Mac first, the account
/// second.
///
/// The defect these cover was measured rather than imagined. `GET /v3/memories` returned
/// `503 Canonical memory unavailable` for eight hours, on every request shape tried including the
/// shipping client's byte-identical one, while that app went on showing 6,598 memories out of its own
/// SQLite without a single failure line in its log. This panel, reading only the network, drew an
/// empty column indistinguishable from an empty account.
final class ActivityLocalMemoriesTests: XCTestCase {

    // MARK: - Fixtures

    private func memory(_ id: String, _ content: String = "A fact", at: Double = 1_000)
        -> ActivityAccountMemory
    {
        ActivityAccountMemory(id: id, content: content, at: at)
    }

    private func reader(
        account: ActivityAccountFeed,
        local: [ActivityAccountMemory],
        available: Bool = true
    ) -> ActivityLocalMemories {
        ActivityLocalMemories(
            StubAccountReader(answer: account),
            local: StubLocalMemories(rows: local, available: available))
    }

    // MARK: - The outage

    /// **The whole feature.** Memories 503 while conversations and tasks answer, and the column is
    /// drawn from this Mac — with the feed saying, per source, exactly where the rows came from.
    func testAMemoriesOutageIsFilledFromThisMacAndDeclared() async {
        let feed = await reader(
            account: ActivityAccountFeed(answered: [.conversations, .tasks]),
            local: [memory("b-1"), memory("local_7", "Not yet synced")]
        ).read(since: nil, until: nil, limit: 50)

        XCTAssertEqual(feed.memories.map(\.id), ["b-1", "local_7"])
        XCTAssertEqual(feed.locallySourced, [.memories])
        // The account is still not answering for memories, and nothing here may pretend otherwise.
        XCTAssertFalse(feed.answered.contains(.memories))
        // Two sources did answer, so the account is reachable and the empty copy stays away.
        XCTAssertTrue(feed.reachable)
    }

    /// A total outage is filled too — and must still report itself as unreachable. Drawing from a
    /// local database may not turn an outage into a clean bill of health, because `reachable` is what
    /// the rest of the surface reasons about.
    func testATotalOutageIsFilledWithoutBecomingReachable() async {
        let feed = await reader(
            account: .unreachable,
            local: [memory("b-1")]
        ).read(since: nil, until: nil, limit: 50)

        XCTAssertEqual(feed.memories.map(\.id), ["b-1"])
        XCTAssertFalse(feed.reachable)
        XCTAssertTrue(feed.answered.isEmpty)
        XCTAssertEqual(feed.locallySourced, [.memories])
    }

    // MARK: - The healthy path

    /// **Cache-first is not a fallback**, which is the part that is easy to get wrong. The local
    /// table holds memories that have not synced yet — 27 of them on the measured machine — and those
    /// exist nowhere else, so a perfectly healthy read still merges them in.
    func testAHealthyReadStillMergesTheRowsThatHaveNotSyncedYet() async {
        let feed = await reader(
            account: ActivityAccountFeed(
                memories: [memory("b-1")], answered: Set(ActivityAccountSource.allCases)),
            local: [memory("b-1"), memory("local_7", "Not yet synced")]
        ).read(since: nil, until: nil, limit: 50)

        XCTAssertEqual(feed.memories.map(\.id), ["b-1", "local_7"])
        XCTAssertEqual(feed.locallySourced, [.memories])
        // …and the account answered, which is what keeps the note off the screen. See
        // `ActivityAccountLocalNoteTests`.
        XCTAssertTrue(feed.answered.contains(.memories))
    }

    /// **A synced row the account did not return is a memory the account no longer has.**
    ///
    /// Deleted on the phone, perhaps minutes ago. Re-adding it from a local copy that has not caught
    /// up would resurrect something the user threw away — permanently, on every open. `backendId` is
    /// exactly the evidence needed: a row that has one has synced, so its absence from a *successful*
    /// read is meaningful.
    func testASyncedRowMissingFromASuccessfulReadIsNotResurrected() async {
        let feed = await reader(
            account: ActivityAccountFeed(
                memories: [memory("b-1")], answered: Set(ActivityAccountSource.allCases)),
            local: [memory("b-1"), memory("b-deleted", "Deleted on the phone")]
        ).read(since: nil, until: nil, limit: 50)

        XCTAssertEqual(feed.memories.map(\.id), ["b-1"])
        // Nothing was added, so nothing is locally sourced and the feed is left exactly as it came.
        XCTAssertTrue(feed.locallySourced.isEmpty)
    }

    /// …and when the account said *nothing*, there is no answer for an absence to be meaningful
    /// against, so every local row is shown.
    func testASilentAccountShowsEverySyncedRowToo() async {
        let feed = await reader(
            account: ActivityAccountFeed(answered: [.conversations]),
            local: [memory("b-1"), memory("b-2")]
        ).read(since: nil, until: nil, limit: 50)

        XCTAssertEqual(feed.memories.map(\.id), ["b-1", "b-2"])
    }

    /// The account is the authority on its own memories: an edit made on the phone reaches the
    /// backend long before it reaches this Mac's copy, so a collision is resolved in its favour and
    /// never by showing the fact twice.
    func testTheAccountsVersionWinsACollision() {
        let merged = ActivityLocalMemories.merge(
            account: [memory("b-1", "The corrected wording")],
            local: [memory("b-1", "The stale wording")],
            accountAnswered: true)

        XCTAssertEqual(merged.map(\.content), ["The corrected wording"])
    }

    // MARK: - No Omi app

    /// A Mac running Context for Claude on its own has no local database, and the feed must come
    /// through untouched — not merely empty, but unmarked, so nothing claims a local source that does
    /// not exist.
    func testNoOmiInstallLeavesTheFeedExactlyAsTheAccountGaveIt() async {
        let feed = await reader(
            account: .unreachable, local: [memory("b-1")], available: false
        ).read(since: nil, until: nil, limit: 50)

        XCTAssertTrue(feed.isEmpty)
        XCTAssertTrue(feed.locallySourced.isEmpty)
        XCTAssertFalse(feed.reachable)
    }

    /// An install with a database and nothing in it yet is the same claim, reached the other way.
    func testAnEmptyLocalDatabaseMarksNothing() async {
        let feed = await reader(account: .unreachable, local: [])
            .read(since: nil, until: nil, limit: 50)

        XCTAssertTrue(feed.locallySourced.isEmpty)
    }

    // MARK: - Airgap Mode

    /// **Reading a database on this Mac is not egress, so Airgap Mode has nothing to suppress — and
    /// the airgapped user gets the better answer rather than a worse one.** The fetchers are
    /// tripwires: a read that reached one of them would fail here, which is what proves the switch
    /// still means what it says.
    func testAirgapModeStillSendsNothingAndTheColumnIsDrawnLocally() async {
        let reader = ActivityLocalMemories(
            OmiActivityFeed(
                isAirgapped: { true },
                isSignedIn: { XCTFail("Airgap Mode must not even ask whether we are signed in"); return true },
                fetchConversations: { _ in XCTFail("Airgap Mode must not read conversations"); return [] },
                fetchMemories: { _ in XCTFail("Airgap Mode must not read memories"); return [] },
                fetchTasks: { _ in
                    XCTFail("Airgap Mode must not read action items")
                    return WireActionItemPage(actionItems: [])
                }),
            local: StubLocalMemories(rows: [memory("b-1")], available: true))

        let feed = await reader.read(since: nil, until: nil, limit: 50)

        XCTAssertEqual(feed.memories.map(\.id), ["b-1"])
        XCTAssertFalse(feed.reachable)
        let reason = await reader.unreachableReason()
        XCTAssertEqual(reason, .airgapped, "why the account is silent is still upstream's to say")
    }

    /// The local read is bounded by the same ceiling the account read is. This is a column on a
    /// panel, not an export of a table that is six and a half thousand rows deep.
    func testTheLocalReadIsBoundedByTheAccountCeiling() async {
        let counter = StubLocalMemories(rows: [memory("b-1")], available: true)
        _ = await ActivityLocalMemories(
            StubAccountReader(answer: .unreachable), local: counter
        ).read(since: nil, until: nil, limit: 100_000)

        XCTAssertEqual(counter.lastLimit, OmiActivityFeed.maxPerSource)
    }
}

/// An account that answers with whatever the test handed it.
private struct StubAccountReader: ActivityAccountReading {
    let answer: ActivityAccountFeed

    func read(since: Double?, until: Double?, limit: Int) async -> ActivityAccountFeed { answer }
}

/// A local database that holds whatever the test handed it, and remembers what it was asked for.
///
/// A class so the recorded limit survives the value being copied into the read; `@unchecked Sendable`
/// is honest because the only writer is the one synchronous call the test makes.
private final class StubLocalMemories: ActivityLocalMemoryReading, @unchecked Sendable {
    private let rows: [ActivityAccountMemory]
    let isAvailable: Bool
    private(set) var lastLimit: Int?

    init(rows: [ActivityAccountMemory], available: Bool) {
        self.rows = rows
        self.isAvailable = available
    }

    func recent(limit: Int) -> [ActivityAccountMemory] {
        lastLimit = limit
        return rows
    }
}

// MARK: - What the reader is told

/// The line over the stream when a column is standing in for the account.
///
/// Held separately from the merge because it is the half that fails silently: a merge that works
/// perfectly and says nothing is exactly what the shipping app does, and exactly what this app must
/// not — its eight-hour outage was invisible for precisely that reason.
final class ActivityAccountLocalNoteTests: XCTestCase {

    private func note(
        locallySourced: Set<ActivityAccountSource>,
        answered: Set<ActivityAccountSource>,
        kind: ActivityKind = .all,
        reason: ActivityAccountUnreachableReason? = nil
    ) -> ActivityAccountLocalNote? {
        ActivityAccountLocalNote.resolve(
            locallySourced: locallySourced, answered: answered, kind: kind, reason: reason)
    }

    /// A live panel says nothing. A caveat that is always on screen is one nobody reads.
    func testALiveFeedGetsNoNote() {
        XCTAssertNil(note(locallySourced: [], answered: Set(ActivityAccountSource.allCases)))
    }

    /// **The one that matters most, and the easiest to get wrong.** A handful of not-yet-synced
    /// memories merged alongside a successful account read is the normal healthy state — main does it
    /// on every launch — and warning about it would put a permanent caveat on a panel that is fine.
    func testASourceThatAnsweredIsNeverWorthANoteEvenWithLocalRowsInIt() {
        XCTAssertNil(
            note(locallySourced: [.memories], answered: Set(ActivityAccountSource.allCases)))
    }

    /// The note names where the rows came from, and never implies they are the account's answer.
    func testTheNoteNamesThisMacAsTheSource() throws {
        let sentence = try XCTUnwrap(
            note(locallySourced: [.memories], answered: [.conversations, .tasks])
        ).sentence

        XCTAssertTrue(sentence.contains("These memories"), sentence)
        XCTAssertTrue(sentence.contains("Omi app on this Mac"), sentence)
        XCTAssertTrue(sentence.contains("couldn't be read"), sentence)
    }

    /// Nothing on a soloed `Rewind` or `Tasks` comes from the memory column, so a note about it there
    /// is a caveat on rows that are not on screen — the same mistake the empty copy made when it
    /// blamed the account for an empty `Rewind`.
    func testAChipThatExcludesTheColumnCarriesNoNote() {
        for kind in [ActivityKind.rewind, .tasks, .conversations] {
            XCTAssertNil(
                note(locallySourced: [.memories], answered: [.conversations], kind: kind),
                "\(kind.title) shows no memories, so it cannot mislabel one")
        }
    }

    /// A soloed `Memories` does carry it — and drops the noun, because the reader already knows which
    /// kind they are looking at and restating it would open by telling them what they just pressed.
    func testASoloedMemoriesChipCarriesTheNoteWithoutRestatingTheKind() throws {
        let sentence = try XCTUnwrap(
            note(locallySourced: [.memories], answered: [.conversations], kind: .memories)
        ).sentence

        XCTAssertTrue(sentence.hasPrefix("These come from the Omi app on this Mac"), sentence)
    }

    /// **The note may only promise a refresh that is actually scheduled.**
    ///
    /// `ActivityStore.scheduleAccountReread` re-reads the failures time can fix and nothing else, so
    /// "I'll ask it again shortly" is a lie under Airgap Mode and to a signed-out app — and it is the
    /// worst kind, because it tells someone to wait for something that will never happen instead of
    /// naming the switch or the sign-in that would fix it.
    func testTheRepairOfferedMatchesWhatTheStoreWillActuallyDo() throws {
        func sentence(_ reason: ActivityAccountUnreachableReason?) throws -> String {
            try XCTUnwrap(note(locallySourced: [.memories], answered: [], reason: reason)).sentence
        }

        XCTAssertTrue(try sentence(.rateLimited).contains("ask it again shortly"))
        XCTAssertTrue(try sentence(.noAnswer).contains("ask it again shortly"))
        // The partial outage carries no whole-feed reason, and it *is* re-read — see
        // `ActivityStore.absorb(account:reason:generation:)`.
        XCTAssertTrue(try sentence(nil).contains("ask it again shortly"))

        let airgapped = try sentence(.airgapped)
        XCTAssertTrue(airgapped.contains("Airgap Mode"), airgapped)
        XCTAssertFalse(airgapped.contains("ask it again"), airgapped)

        let signedOut = try sentence(.signedOut)
        XCTAssertTrue(signedOut.contains("sign in to Omi"), signedOut)
        XCTAssertFalse(signedOut.contains("ask it again"), signedOut)

        let rejected = try sentence(.keyRejected)
        XCTAssertTrue(rejected.contains("sign out and back in"), rejected)
        XCTAssertFalse(rejected.contains("ask it again"), rejected)
    }

    /// The corner sentence needs no third scope: memories read from
    /// `~/Library/Application Support/Omi` are kept on this Mac exactly as the screen capture is, so
    /// the narrow claim is the true description of both halves.
    func testTheCountLineNarrowsHonestlyWithoutAThirdScope() {
        XCTAssertEqual(ActivityCount.scope(accountUnreachable: .noAnswer), ActivityCount.localScope)
        XCTAssertEqual(ActivityCount.scope(accountUnreachable: nil), ActivityCount.scope)
    }
}

// MARK: - A page that had to skip its own first row

extension ActivityLocalMemoriesTests {

    /// The `/v3/memories` first page is currently unservable for real accounts, so a 503 there is
    /// answered by re-asking from `offset: 1`. The page that comes back is complete *except at the
    /// head* — and the no-resurrection rule, which is right for a whole page, is wrong for exactly
    /// the rows above it: they are missing because they were never asked for, not because they were
    /// deleted somewhere else.
    func testASyncedRowAboveATruncatedPageIsRestored() {
        let account = [
            ActivityAccountMemory(id: "b", content: "second newest", at: 200),
            ActivityAccountMemory(id: "c", content: "older", at: 100),
        ]
        let local = [
            ActivityAccountMemory(id: "a", content: "the newest, never returned", at: 300),
            ActivityAccountMemory(id: "b", content: "second newest", at: 200),
            ActivityAccountMemory(id: "gone", content: "deleted on the phone", at: 150),
        ]

        let merged = ActivityLocalMemories.merge(
            account: account, local: local, accountAnswered: true, beginsPastHead: true)

        XCTAssertEqual(
            Set(merged.map(\.id)), ["a", "b", "c"],
            "the row above the head comes back; a row deleted inside the page's range does not")
    }

    /// The bound is the whole point. Without it, "the page is incomplete" would readmit every
    /// deletion the account has ever made.
    func testATruncatedPageStillRefusesADeletionInsideItsRange() {
        let account = [ActivityAccountMemory(id: "b", content: "newest returned", at: 200)]
        let local = [
            ActivityAccountMemory(id: "b", content: "newest returned", at: 200),
            ActivityAccountMemory(id: "gone", content: "deleted on the phone", at: 199),
        ]

        let merged = ActivityLocalMemories.merge(
            account: account, local: local, accountAnswered: true, beginsPastHead: true)

        XCTAssertEqual(merged.map(\.id), ["b"], "199 is inside the page, so its absence is meaningful")
    }

    /// An ordinary complete page is unchanged: a synced row the account did not return stays gone.
    func testACompletePageIsUnaffectedByTheHeadRule() {
        let account = [ActivityAccountMemory(id: "b", content: "kept", at: 200)]
        let local = [
            ActivityAccountMemory(id: "a", content: "deleted on the phone", at: 300),
            ActivityAccountMemory(id: "b", content: "kept", at: 200),
        ]

        let merged = ActivityLocalMemories.merge(
            account: account, local: local, accountAnswered: true, beginsPastHead: false)

        XCTAssertEqual(merged.map(\.id), ["b"], "no truncation, so absence means deleted")
    }

    /// A truncated page that came back empty has no head to be past and no range to be inside, so
    /// every synced local row is above it.
    func testAnEmptyTruncatedPageRestoresEverythingLocal() {
        let local = [ActivityAccountMemory(id: "a", content: "kept", at: 300)]

        let merged = ActivityLocalMemories.merge(
            account: [], local: local, accountAnswered: true, beginsPastHead: true)

        XCTAssertEqual(merged.map(\.id), ["a"])
    }
}
