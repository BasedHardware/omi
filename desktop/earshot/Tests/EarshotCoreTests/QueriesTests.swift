import EarshotCore
import Foundation
import XCTest

/// The read layer: what Claude actually sees.
///
/// Every assertion here is over the seeded corpus in `Fixture`, so a failure names a behaviour
/// ("recall stopped merging screen hits") rather than a row count that happened to change.
final class QueriesTests: XCTestCase {
    private var fixture: Fixture!

    override func setUpWithError() throws {
        fixture = try Fixture()
    }

    override func tearDownWithError() throws {
        fixture?.tearDown()
        fixture = nil
    }

    // MARK: - Recall

    func testRecallMergesSpeechAndScreenNewestFirst() throws {
        // "roadmap" was said once and was on screen once, an hour and a half apart.
        let hits = try Queries.recall(fixture.store, query: "roadmap")

        XCTAssertEqual(hits.map(\.kind), ["said", "screen"])
        XCTAssertEqual(hits.map(\.at), [Fixture.base + 7210, Fixture.base + 130])
        XCTAssertEqual(hits.first?.text, "thinking out loud about the roadmap")
        XCTAssertEqual(hits.last?.app, "Google Chrome")
        XCTAssertEqual(hits.last?.window, "Roadmap — Notion")
        XCTAssertEqual(hits.first?.sessionId, fixture.sessionB)
    }

    func testRecallAttributesSpeakersAndCarriesAHumanTimestamp() throws {
        let hits = try Queries.recall(fixture.store, query: "migration")

        let hit = try XCTUnwrap(hits.first)
        // Mic is the user, the system tap is everyone else — the whole of Earshot's diarization.
        XCTAssertEqual(hit.kind, "heard")
        XCTAssertEqual(hit.when, EarshotTime.describe(Fixture.base + 30))
        XCTAssertEqual(hit.sessionId, fixture.sessionA)
    }

    func testRecallRespectsLimitSinceAndUntil() throws {
        // "pricing" matches two spoken lines (+10, +60) and one frame (+100).
        let all = try Queries.recall(fixture.store, query: "pricing")
        XCTAssertEqual(all.map(\.at), [Fixture.base + 100, Fixture.base + 60, Fixture.base + 10])

        let capped = try Queries.recall(fixture.store, query: "pricing", limit: 2)
        XCTAssertEqual(capped.map(\.at), [Fixture.base + 100, Fixture.base + 60])

        // The cap applies after the merge, not per source — otherwise a limit of 2 would return
        // two speech hits and two screen hits.
        XCTAssertEqual(try Queries.recall(fixture.store, query: "pricing", limit: 1).count, 1)

        let since = try Queries.recall(fixture.store, query: "pricing", since: Fixture.base + 50)
        XCTAssertEqual(since.map(\.at), [Fixture.base + 100, Fixture.base + 60])

        let until = try Queries.recall(fixture.store, query: "pricing", until: Fixture.base + 70)
        XCTAssertEqual(until.map(\.at), [Fixture.base + 60, Fixture.base + 10])

        let window = try Queries.recall(
            fixture.store, query: "pricing", since: Fixture.base + 50, until: Fixture.base + 70)
        XCTAssertEqual(window.map(\.at), [Fixture.base + 60])
    }

    func testRecallSurvivesHostileInput() throws {
        // Anything a person or a model might type. None of it may reach SQLite as FTS5 syntax.
        let hostile = [
            "\"", "*", "AND", "OR", "NOT x", "a:b", "🙂", "", "   ", "\t\n",
            "\"unterminated", "foo*", "NEAR(a b)", "-excluded", "^caret", "a AND b OR NOT c",
            "pricing\" OR segments_fts MATCH \"", "()", "column:value*",
        ]

        for query in hostile {
            XCTAssertNoThrow(
                try Queries.recall(fixture.store, query: query),
                "recall threw on \(query.debugDescription)")
        }
    }

    func testFTSExpressionQuotesTermsAndDropsOperators() throws {
        // Terms are quoted and OR-joined: ambient recall should surface anything related rather than
        // return nothing because one word of the phrase was missing.
        XCTAssertEqual(Queries.ftsExpression(for: "pricing"), "\"pricing\"")
        XCTAssertEqual(Queries.ftsExpression(for: "pricing change"), "\"pricing\" OR \"change\"")
        // Operators are stripped, not escaped — an operator that survives is a syntax error waiting
        // for the one user who types it.
        XCTAssertEqual(Queries.ftsExpression(for: "NOT x"), "\"x\"")
        XCTAssertEqual(Queries.ftsExpression(for: "\"pricing\""), "\"pricing\"")
        XCTAssertNotNil(Queries.ftsExpression(for: "a:b"))

        // Nothing left to search for is nil, so the caller answers "no results" instead of handing
        // SQLite an empty MATCH.
        for empty in ["", "   ", "\"", "*", "AND", "🙂", "()"] {
            XCTAssertNil(
                Queries.ftsExpression(for: empty),
                "\(empty.debugDescription) should not produce an expression")
        }
    }

    // MARK: - Recent and screen

    func testRecentWindowIsMinutesNotSeconds() throws {
        let scratch = try makeEmptyFixture()
        let now = EarshotTime.now
        let sessionId = try scratch.store.openSession(at: now - 4_000, appHint: nil)
        try scratch.addSegment(session: sessionId, at: now - 3_600, source: .mic, "an hour ago")
        try scratch.addSegment(session: sessionId, at: now - 60, source: .mic, "a minute ago")
        try scratch.addFrame(at: now - 120, app: "Xcode", window: "two minutes ago")

        let hits = try Queries.recent(scratch.store, minutes: 30)

        XCTAssertEqual(hits.map(\.text), ["a minute ago", "two minutes ago"])
    }

    func testScreenFiltersByAppSubstringNewestFirst() throws {
        // Callers pass "Chrome" and mean "Google Chrome".
        let hits = try Queries.screen(fixture.store, app: "Chrome")

        XCTAssertEqual(hits.map(\.at), [Fixture.base + 130, Fixture.base + 100])
        XCTAssertEqual(Set(hits.map(\.kind)), ["screen"])
        XCTAssertEqual(hits.first?.app, "Google Chrome")
        XCTAssertEqual(try Queries.screen(fixture.store, app: "Xcode").count, 1)
        XCTAssertEqual(try Queries.screen(fixture.store, limit: 1).map(\.at), [Fixture.base + 7300])
    }

    // MARK: - Sessions

    func testSessionsSummariseBothSidedAndOneSidedConversations() throws {
        let summaries = try Queries.sessions(fixture.store)

        XCTAssertEqual(summaries.map(\.id), [fixture.sessionB, fixture.sessionA])

        let both = try XCTUnwrap(summaries.last)
        XCTAssertEqual(both.lineCount, 3)
        XCTAssertTrue(both.bothSidesPresent, "a session with mic and system audio is a conversation")
        XCTAssertEqual(both.appHint, "zoom.us")
        XCTAssertEqual(both.endedAt, Fixture.base + 600)
        XCTAssertEqual(both.durationSeconds, 600)
        XCTAssertTrue(both.preview.contains("we decided to ship the pricing change"),
                      "preview lost the opening line: \(both.preview)")
        XCTAssertTrue(both.preview.contains("sounds good"),
                      "preview lost the other side: \(both.preview)")

        let oneSided = try XCTUnwrap(summaries.first)
        XCTAssertEqual(oneSided.lineCount, 1)
        XCTAssertFalse(oneSided.bothSidesPresent, "one voice is the user talking, not a call")
        XCTAssertNil(oneSided.endedAt, "session B is still open")
        // An open session still has a duration: whatever it has captured so far.
        XCTAssertEqual(oneSided.durationSeconds, 15)
        XCTAssertTrue(oneSided.preview.contains("thinking out loud about the roadmap"))
    }

    func testSessionsRespectLimitSinceAndUntil() throws {
        XCTAssertEqual(try Queries.sessions(fixture.store, limit: 1).map(\.id), [fixture.sessionB])
        XCTAssertEqual(
            try Queries.sessions(fixture.store, since: Fixture.base + 7_000).map(\.id),
            [fixture.sessionB])
        XCTAssertEqual(
            try Queries.sessions(fixture.store, until: Fixture.base + 1_000).map(\.id),
            [fixture.sessionA])
    }

    func testTranscriptIsChronologicalAndAttributed() throws {
        let lines = try Queries.transcript(fixture.store, sessionId: fixture.sessionA)

        // Reverse of every other query on purpose: a conversation only reads forwards.
        XCTAssertEqual(lines.map(\.at), [Fixture.base + 10, Fixture.base + 30, Fixture.base + 60])
        XCTAssertEqual(lines.map(\.kind), ["said", "heard", "said"])
        XCTAssertEqual(lines.compactMap(\.sessionId), Array(repeating: fixture.sessionA, count: 3))
        XCTAssertEqual(lines.first?.text, "we decided to ship the pricing change on Friday")

        XCTAssertEqual(try Queries.transcript(fixture.store, sessionId: 9_999), [])
    }

    // MARK: - Activity

    func testActivityCollapsesRunsSplitsOnGapsAndDropsGlances() throws {
        let scratch = try makeEmptyFixture()
        let base = Fixture.base

        // 40 s in Chrome.
        for offset in stride(from: 0.0, through: 40.0, by: 5.0) {
            try scratch.addFrame(at: base + offset, app: "Google Chrome",
                                 window: offset == 0 ? "Docs" : "Pricing rollout — Docs")
        }
        // App switch closes the block: 20 s in Xcode.
        for offset in stride(from: 45.0, through: 65.0, by: 5.0) {
            try scratch.addFrame(at: base + offset, app: "Xcode", window: "Store.swift")
        }
        // Same app again, but 335 s later — the user walked away, so this is a second block.
        for offset in stride(from: 400.0, through: 420.0, by: 5.0) {
            try scratch.addFrame(at: base + offset, app: "Xcode", window: "Queries.swift")
        }
        // 5 s in Finder: a glance, not a stretch of work.
        try scratch.addFrame(at: base + 500, app: "Finder", window: "Downloads")
        try scratch.addFrame(at: base + 505, app: "Finder", window: "Downloads")

        let blocks = try Queries.activity(scratch.store, since: base - 60, until: base + 900)

        XCTAssertEqual(blocks.map(\.app), ["Google Chrome", "Xcode", "Xcode"])
        XCTAssertEqual(blocks.map(\.startedAt), [base, base + 45, base + 400])
        XCTAssertEqual(blocks.map(\.durationSeconds), [40, 20, 20])
        XCTAssertFalse(blocks.contains { $0.app == "Finder" }, "a 5 s glance is noise, not a block")
        // The most descriptive title the app showed during the stretch.
        XCTAssertEqual(blocks.first?.window, "Pricing rollout — Docs")
        XCTAssertEqual(blocks.last?.window, "Queries.swift")

        // The window is a filter, not a hint.
        let narrowed = try Queries.activity(scratch.store, since: base + 100, until: base + 900)
        XCTAssertEqual(narrowed.map(\.startedAt), [base + 400])
        XCTAssertEqual(try Queries.activity(scratch.store, since: base + 700, until: base + 900), [])
    }

    // MARK: - Status

    func testStatusReportsCountsAndCoverage() throws {
        let status = try Queries.status(fixture.store)

        XCTAssertEqual(status.segmentCount, 4)
        XCTAssertEqual(status.frameCount, 3)
        XCTAssertEqual(status.sessionCount, 2)
        // Coverage spans speech and screen together: the oldest line and the newest frame.
        XCTAssertEqual(status.oldestAt, Fixture.base + 10)
        XCTAssertEqual(status.newestAt, Fixture.base + 7_300)
        XCTAssertTrue(status.coverage.contains(EarshotTime.describe(Fixture.base + 10)),
                      "coverage lost its start: \(status.coverage)")
        XCTAssertTrue(status.coverage.contains(EarshotTime.describe(Fixture.base + 7_300)),
                      "coverage lost its end: \(status.coverage)")
        XCTAssertFalse(status.databasePath.isEmpty)
    }

    func testStatusOnAnEmptyStoreSaysSoRatherThanGuessing() throws {
        let scratch = try makeEmptyFixture()

        let status = try Queries.status(scratch.store)

        XCTAssertEqual(status.segmentCount, 0)
        XCTAssertNil(status.oldestAt)
        XCTAssertNil(status.newestAt)
        XCTAssertEqual(status.coverage, "no data captured yet")
    }

    func testStatusIsNotCapturingWithoutALiveHeartbeat() throws {
        // `status` reads the process-wide heartbeat path and the contract gives it no injection
        // point, so the expectation is derived from that same file. The test never writes it — a
        // unit test must not be able to tell the running app it is paused.
        let state = CaptureState.read()

        let status = try Queries.status(fixture.store)

        if let state, !state.isStale {
            XCTAssertEqual(status.capturing, state.capturing)
        } else {
            XCTAssertFalse(status.capturing, "an absent or stale heartbeat means the app is not running")
            XCTAssertNotNil(status.pausedReason)
            if state == nil {
                XCTAssertEqual(status.pausedReason, "Earshot is not running")
            }
        }
    }

    func testHeartbeatGoesStaleOnSchedule() throws {
        // The rule `status` depends on, tested without touching the real heartbeat file.
        let url = fixture.root.appendingPathComponent("capture-state.json")
        let now = EarshotTime.now

        try JSONEncoder().encode(CaptureState(capturing: true, updatedAt: now)).write(to: url)
        XCTAssertEqual(CaptureState.read(from: url)?.isStale, false)

        let old = CaptureState(capturing: true, updatedAt: now - CaptureState.stalenessSeconds - 60)
        try JSONEncoder().encode(old).write(to: url)
        XCTAssertEqual(CaptureState.read(from: url)?.isStale, true)

        XCTAssertNil(CaptureState.read(from: fixture.root.appendingPathComponent("absent.json")))
    }

    // MARK: - Helpers

    /// A second, empty store for the tests that need to author their own corpus. Torn down with the
    /// test rather than in `tearDown`, so no test can see another's rows.
    private func makeEmptyFixture() throws -> Fixture {
        let scratch = try Fixture(seeded: false)
        addTeardownBlock { scratch.tearDown() }
        return scratch
    }
}
