import ContextCore
import XCTest

/// What the account cache table has to do, and — more importantly — what it must not do to the
/// sources nobody wrote.
///
/// The whole reason this table exists is a launch that had nothing to paint until the network
/// answered. The whole reason it is *per source* is that the account's three endpoints fail
/// independently, and a cache that a single 503 could wipe would be worse than no cache at all: it
/// would be a surface that looks fine until the day the backend has a bad hour, and then looks
/// exactly as broken as before while claiming to be fixed.
final class AccountCacheQueriesTests: XCTestCase {
    private var fixture: Fixture!

    override func setUpWithError() throws {
        fixture = try Fixture(seeded: false)
    }

    override func tearDown() {
        fixture.tearDown()
        fixture = nil
    }

    private func row(_ id: String, at: Double, _ payload: String = "{}") -> CachedAccountRow {
        CachedAccountRow(source: "conversations", id: id, at: at, payload: payload)
    }

    func testARowSurvivesTheRoundTrip() throws {
        try AccountCacheQueries.replace(
            fixture.store, source: "conversations",
            rows: [row("a", at: 10, #"{"title":"Standup"}"#)], keeping: 50)

        let read = try AccountCacheQueries.recent(fixture.store, source: "conversations", limit: 50)

        XCTAssertEqual(read.count, 1)
        XCTAssertEqual(read.first?.id, "a")
        XCTAssertEqual(read.first?.at, 10)
        XCTAssertEqual(read.first?.payload, #"{"title":"Standup"}"#)
    }

    /// Newest first, because the caller is drawing a spine that starts at today and a `LIMIT` over
    /// the wrong order would keep the oldest rows in the account.
    func testRowsComeBackNewestFirst() throws {
        try AccountCacheQueries.replace(
            fixture.store, source: "conversations",
            rows: [row("old", at: 1), row("new", at: 3), row("middle", at: 2)], keeping: 50)

        XCTAssertEqual(
            try AccountCacheQueries.recent(fixture.store, source: "conversations", limit: 50)
                .map(\.id),
            ["new", "middle", "old"])
    }

    /// The same id written twice is one row carrying the second write. This is what makes a
    /// conversation the backend has since titled reach the cache without duplicating it.
    func testWritingTheSameIdAgainUpdatesItRatherThanDuplicatingIt() throws {
        try AccountCacheQueries.replace(
            fixture.store, source: "conversations", rows: [row("a", at: 10, #"{"title":""}"#)],
            keeping: 50)
        try AccountCacheQueries.replace(
            fixture.store, source: "conversations",
            rows: [row("a", at: 11, #"{"title":"Named at last"}"#)], keeping: 50)

        let read = try AccountCacheQueries.recent(fixture.store, source: "conversations", limit: 50)
        XCTAssertEqual(read.count, 1)
        XCTAssertEqual(read.first?.payload, #"{"title":"Named at last"}"#)
        XCTAssertEqual(read.first?.at, 11)
    }

    /// **The bound is the reason this table can live in a capture database.** Without it, one
    /// hydration walk a day writes the account's whole history into the file that holds the user's
    /// screenshots.
    func testTheTrimKeepsOnlyTheNewest() throws {
        let rows = (1...10).map { row("id-\($0)", at: Double($0)) }
        try AccountCacheQueries.replace(
            fixture.store, source: "conversations", rows: rows, keeping: 3)

        XCTAssertEqual(try AccountCacheQueries.count(fixture.store, source: "conversations"), 3)
        XCTAssertEqual(
            try AccountCacheQueries.recent(fixture.store, source: "conversations", limit: 50)
                .map(\.id),
            ["id-10", "id-9", "id-8"])
    }

    /// **The test this table exists for.** Writing one source must be invisible to the other two:
    /// the observed backend state is conversations serving normally while `/v3/memories` answers
    /// 503, and a write that cleared the table would spend a healthy source's cache on a sick one's
    /// outage.
    func testWritingOneSourceLeavesTheOthersAlone() throws {
        try AccountCacheQueries.replace(
            fixture.store, source: "memories",
            rows: [CachedAccountRow(source: "memories", id: "m1", at: 5, payload: "{}")],
            keeping: 50)
        try AccountCacheQueries.replace(
            fixture.store, source: "tasks",
            rows: [CachedAccountRow(source: "tasks", id: "t1", at: 5, payload: "{}")], keeping: 50)

        // Conversations answer; the other two do not, so nobody writes them.
        try AccountCacheQueries.replace(
            fixture.store, source: "conversations", rows: [row("c1", at: 6)], keeping: 50)

        XCTAssertEqual(try AccountCacheQueries.count(fixture.store, source: "memories"), 1)
        XCTAssertEqual(try AccountCacheQueries.count(fixture.store, source: "tasks"), 1)
        XCTAssertEqual(try AccountCacheQueries.count(fixture.store, source: "conversations"), 1)
    }

    /// And the trim of one source may not reach into another's rows either, which is the way the
    /// isolation above is most easily broken by a `DELETE` that forgets its `WHERE`.
    func testTheTrimIsScopedToItsOwnSource() throws {
        try AccountCacheQueries.replace(
            fixture.store, source: "memories",
            rows: (1...5).map { CachedAccountRow(source: "memories", id: "m\($0)", at: Double($0), payload: "{}") },
            keeping: 50)

        try AccountCacheQueries.replace(
            fixture.store, source: "conversations",
            rows: (1...5).map { row("c\($0)", at: Double($0)) }, keeping: 1)

        XCTAssertEqual(try AccountCacheQueries.count(fixture.store, source: "conversations"), 1)
        XCTAssertEqual(
            try AccountCacheQueries.count(fixture.store, source: "memories"), 5,
            "trimming one source must not touch another")
    }

    /// **Ties on `at` are ordinary, so the order may not depend on them alone.** A date-only task is
    /// stamped at 11:59 PM like every other one; a backfilled batch of memories shares an instant.
    /// Without `id` as a second key SQLite may return any subset in any order, so the page a launch
    /// paints can disagree with the page the trim decided to keep.
    func testRowsSharingAnInstantAreOrderedAndTrimmedStably() throws {
        let tied = ["b", "d", "a", "c"].map { row($0, at: 100) }
        try AccountCacheQueries.replace(
            fixture.store, source: "conversations", rows: tied, keeping: 50)

        let first = try AccountCacheQueries.recent(
            fixture.store, source: "conversations", limit: 50
        ).map(\.id)
        XCTAssertEqual(first, ["d", "c", "b", "a"], "id decides, descending, when the instant cannot")

        // And the trim keeps the same rows the read would have shown, which is the half that
        // silently loses data when the two orders disagree.
        try AccountCacheQueries.replace(
            fixture.store, source: "conversations", rows: tied, keeping: 2)
        XCTAssertEqual(
            try AccountCacheQueries.recent(fixture.store, source: "conversations", limit: 50)
                .map(\.id),
            ["d", "c"])
    }

    /// Signing out. One account's rows must never be the first thing the next account sees.
    func testClearEmptiesEverySource() throws {
        try AccountCacheQueries.replace(
            fixture.store, source: "conversations", rows: [row("c1", at: 1)], keeping: 50)
        try AccountCacheQueries.replace(
            fixture.store, source: "memories",
            rows: [CachedAccountRow(source: "memories", id: "m1", at: 1, payload: "{}")],
            keeping: 50)

        try AccountCacheQueries.clear(fixture.store)

        XCTAssertEqual(try AccountCacheQueries.count(fixture.store, source: "conversations"), 0)
        XCTAssertEqual(try AccountCacheQueries.count(fixture.store, source: "memories"), 0)
    }

    /// A limit of zero is a caller asking for nothing, not a caller asking for everything — the
    /// shape `LIMIT 0` and `LIMIT -1` disagree about in SQLite.
    func testAskingForNothingReturnsNothing() throws {
        try AccountCacheQueries.replace(
            fixture.store, source: "conversations", rows: [row("c1", at: 1)], keeping: 50)

        XCTAssertTrue(
            try AccountCacheQueries.recent(fixture.store, source: "conversations", limit: 0).isEmpty)
    }
}
