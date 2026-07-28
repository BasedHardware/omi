import ContextCore
import Foundation
import XCTest

// The honesty seams — `nothingFound`, `recallHeadline`, `deepenHistory`, `historyDepthLines`,
// `isWithinRange`, `screenLagSentence` — are internal on purpose: they are the decisions worth
// testing, and testing them through a live Omi account would be neither hermetic nor possible.
@testable import ContextMCPKit

/// The seven tools: their declarations, their date arguments, and what they say when there is
/// nothing to say.
///
/// The declarations are as much of the product as the queries behind them — a tool Claude cannot
/// tell when to reach for is a tool that never runs.
final class ToolsTests: XCTestCase {
    /// Exactly the set in CONTRACTS.md. Renaming one silently unregisters it from every existing
    /// Claude session, so this list is deliberately spelled out rather than derived.
    private let expectedNames: Set<String> = [
        "recall", "recent", "conversations", "transcript", "screen", "activity", "status",
    ]

    /// name → the parameters the contract gives it.
    private let expectedParameters: [String: Set<String>] = [
        "recall": ["query", "since", "until", "limit"],
        "recent": ["minutes"],
        "conversations": ["since", "until", "limit"],
        "transcript": ["session_id"],
        "screen": ["since", "until", "app", "limit"],
        "activity": ["since", "until"],
        "status": [],
    ]

    // MARK: - Declarations

    func testToolsAreExactlyTheSevenInTheContract() {
        XCTAssertEqual(Tools.all.count, 7)
        XCTAssertEqual(Set(Tools.all.map(\.name)), expectedNames)
    }

    func testEveryToolHasAModelFacingDescriptionAndAnObjectSchema() throws {
        for tool in Tools.all {
            XCTAssertGreaterThan(
                tool.description.count, 30,
                "\(tool.name) needs a description that tells Claude when to reach for it")

            let schema = try XCTUnwrap(tool.inputSchema.objectValue, "\(tool.name) has no schema")
            XCTAssertEqual(schema["type"]?.stringValue, "object", "\(tool.name) schema is not an object")
            // A tool with no parameters may legitimately omit `properties` entirely.
            let properties = tool.inputSchema["properties"]?.objectValue ?? [:]
            XCTAssertEqual(
                Set(properties.keys), expectedParameters[tool.name] ?? [],
                "\(tool.name) parameters drifted from the contract")

            for (name, property) in properties {
                // JSON Schema allows a union, and `transcript.session_id` is genuinely one: a
                // session is a local integer id until it has been uploaded, and Omi's UUID after.
                let declared = property["type"]
                let isSingle = declared?.stringValue != nil
                let isUnion = (declared?.arrayValue?.allSatisfy { $0.stringValue != nil }) == true
                    && declared?.arrayValue?.isEmpty == false
                XCTAssertTrue(
                    isSingle || isUnion, "\(tool.name).\(name) has no declared type")
            }
        }
    }

    func testRequiredArgumentsAreDeclaredAsRequired() throws {
        let required: [String: Set<String>] = [
            "recall": ["query"],
            "transcript": ["session_id"],
            "activity": ["since"],
        ]

        for tool in Tools.all {
            let declared = Set((tool.inputSchema["required"]?.arrayValue ?? []).compactMap(\.stringValue))
            XCTAssertEqual(declared, required[tool.name] ?? [], "\(tool.name) required list drifted")
        }
    }

    // MARK: - Date arguments

    func testDateArgParsesTheFormsTheContractPromises() throws {
        let iso = ISO8601DateFormatter()
        let expected = try XCTUnwrap(iso.date(from: "2025-10-09T07:33:20Z")).timeIntervalSince1970
        XCTAssertEqual(
            try XCTUnwrap(DateArg.parse("2025-10-09T07:33:20Z")), expected, accuracy: 1)

        // A bare date is a day, and which midnight it means is a timezone judgement — assert the day
        // rather than the instant, since either reading is correct for the product.
        assertSameDay(try XCTUnwrap(DateArg.parse("2025-10-09")), "2025-10-09")

        let now = ContextTime.now
        let today = try XCTUnwrap(DateArg.parse("today"))
        XCTAssertLessThanOrEqual(today, now + 1)
        XCTAssertLessThan(now - today, 86_400 + 1, "\"today\" must be today's start, not yesterday's")

        let yesterday = try XCTUnwrap(DateArg.parse("yesterday"))
        XCTAssertGreaterThan(today - yesterday, 23 * 3_600.0, "\"yesterday\" is a day back")
        XCTAssertLessThan(today - yesterday, 25 * 3_600.0)

        // Relative English. The tolerances are wide enough for a "start of that day" reading and
        // narrow enough to catch a unit mix-up, which is the regression that actually happens.
        let minutes = try XCTUnwrap(DateArg.parse("30 minutes ago"))
        XCTAssertEqual(minutes, now - 1_800, accuracy: 120)

        let days = try XCTUnwrap(DateArg.parse("3 days ago"))
        XCTAssertGreaterThan(days, now - 4.5 * 86_400)
        XCTAssertLessThan(days, now - 2.4 * 86_400)

        let week = try XCTUnwrap(DateArg.parse("last week"))
        XCTAssertGreaterThan(week, now - 15 * 86_400)
        XCTAssertLessThan(week, now - 5 * 86_400)
    }

    func testDateArgReturnsNilForJunk() {
        for junk in ["", "   ", "not a date", "🙂", "soonish", "2025-13-45", "ago", "banana days ago"] {
            XCTAssertNil(DateArg.parse(junk), "\(junk.debugDescription) is not a date")
        }
    }

    // MARK: - No database yet

    func testEveryToolExplainsItselfWhenNothingHasBeenCaptured() throws {
        // The MCP server is spawned per Claude session and may well run before the app has ever
        // captured anything. That is a sentence, never an exception.
        for (name, arguments) in validArguments() {
            let text = try Tools.call(name: name, arguments: arguments, store: nil)

            XCTAssertFalse(text.isEmpty, "\(name) said nothing")
            XCTAssertTrue(
                text.lowercased().contains("captur"),
                "\(name) should explain that nothing has been captured yet, said: \(text)")
        }
    }

    /// The bug this guards against shipped and misled a real session: a stale MCP server left over
    /// from a rename could not open the database, and every tool reported that nothing had ever been
    /// captured — while the current app was writing a frame every three seconds.
    ///
    /// A nil store is ambiguous on its own. The heartbeat resolves it: the app rewrites it every
    /// 30s, so a fresh beat means capture is running somewhere this reader cannot see, and the
    /// honest answer is "this reader is broken", never "your life is empty".
    func testALiveHeartbeatWithNoDatabaseIsReportedAsAReaderFaultNotAnEmptyHistory() throws {
        let heartbeat = FileManager.default.temporaryDirectory
            .appendingPathComponent("context-heartbeat-\(UUID().uuidString).json")
        defer { try? FileManager.default.removeItem(at: heartbeat) }

        try CaptureState(capturing: true, capabilities: []).write(to: heartbeat)
        let state = try XCTUnwrap(CaptureState.read(from: heartbeat))

        XCTAssertFalse(state.isStale, "a beat written just now must not read as stale")
        XCTAssertTrue(state.capturing)

        // The classifier is the whole fix; asserting on it directly keeps this test honest even if
        // the wording of the sentence it drives changes.
        guard case .readerIsStale = CaptureState.diagnoseMissingDatabase() else {
            throw XCTSkip("no live capture on this machine — the fault path cannot be exercised here")
        }

        for (name, arguments) in validArguments() {
            let text = try Tools.call(name: name, arguments: arguments, store: nil).lowercased()
            XCTAssertFalse(
                text.contains("has never captured anything"),
                "\(name) asserted an empty history while capture was live, said: \(text)")
        }
    }

    /// A stale beat — or none at all — genuinely does mean the app is not running here, and the
    /// tools should keep saying so plainly rather than hedging every answer.
    func testAStaleHeartbeatIsClassifiedAsTheAppSimplyNotRunning() throws {
        let heartbeat = FileManager.default.temporaryDirectory
            .appendingPathComponent("context-heartbeat-\(UUID().uuidString).json")
        defer { try? FileManager.default.removeItem(at: heartbeat) }

        let stale = ContextTime.now - (CaptureState.stalenessSeconds + 60)
        try CaptureState(capturing: true, updatedAt: stale).write(to: heartbeat)
        let state = try XCTUnwrap(CaptureState.read(from: heartbeat))

        XCTAssertTrue(state.isStale, "a beat older than the staleness window must read as stale")
    }

    // MARK: - Empty results

    func testAnEmptyResultReportsTheCoverageWindow() throws {
        // "Never happened" and "not captured" are different answers, and only the coverage window
        // tells them apart. The corpus is dated 2025 so the year can only come from the data.
        let store = try seededStore()

        let text = try Tools.call(
            name: "recall", arguments: ["query": "chinchilla"], store: store)

        XCTAssertFalse(text.contains("pricing"), "recall returned a row that does not match")
        XCTAssertTrue(text.contains("2025"), "empty recall lost the coverage window, said: \(text)")
    }

    func testStatusRendersTheCoverageWindow() throws {
        let store = try seededStore()

        let text = try Tools.call(name: "status", arguments: nil, store: store)

        XCTAssertTrue(text.contains("2025"), "status lost the coverage window, said: \(text)")
    }

    func testToolsRenderCapturedContext() throws {
        let store = try seededStore()

        let text = try Tools.call(name: "recall", arguments: ["query": "pricing"], store: store)

        XCTAssertTrue(text.contains("pricing change"), "recall did not render the line it found: \(text)")
    }

    // MARK: - A search that ran vs. a search that could not run
    //
    // The suite this joins had 67 green tests while every tool asserted an empty history from a
    // database it could not read: coverage existed for `store == nil`, and not for the third state —
    // the file is there, it opens, and the query fails. These tests live in that state.

    /// The blind spot, exercised directly. A database that opens and then refuses to answer says
    /// nothing whatsoever about what the user did; reporting it as an empty history is the worst
    /// failure this product has.
    func testADatabaseThatOpensButCannotBeQueriedIsNeverAnEmptyHistory() throws {
        let store = try unreadableStore()
        let calls: [(String, JSONValue)] = [
            ("recall", ["query": "pricing"]),
            ("conversations", [:]),
            ("screen", [:]),
        ]

        for (name, arguments) in calls {
            let text = try Tools.call(name: name, arguments: arguments, store: store)

            XCTAssertTrue(
                text.contains("present on this Mac but could not be read"),
                "\(name) hid a failed local read, said: \(text)")
            // The exact wording that used to appear here, and the reason this test exists: the
            // reader fell back to the "no database at all" sentence for a database that was
            // sitting right there.
            XCTAssertFalse(
                text.contains("no local database"),
                "\(name) reported a broken read as a missing database, said: \(text)")
            // Not even in the footer: a search that did not run may not be described as one that did.
            XCTAssertFalse(
                text.contains("captured locally on this Mac was searched"),
                "\(name) claimed in its footer to have searched the local half, said: \(text)")
            assertMakesNoClaimAboutAnEmptyLife(text, tool: name)
        }
    }

    /// The behaviour the benchmark praised, pinned so this change cannot regress it: `recent` and
    /// `activity` are local-only and have nothing honest to say when the local half is broken, so
    /// they fail hard instead of returning an empty day.
    func testRecentAndActivityStillFailLoudlyRatherThanReportingAnEmptyDay() throws {
        let store = try unreadableStore()

        XCTAssertThrowsError(
            try Tools.call(name: "recent", arguments: ["minutes": 30], store: store),
            "recent answered from a database it could not read")
        XCTAssertThrowsError(
            try Tools.call(name: "activity", arguments: ["since": "yesterday"], store: store),
            "activity answered from a database it could not read")
    }

    func testStatusSaysTheDatabaseOpenedAndFailedRatherThanThatNothingWasCaptured() throws {
        let store = try unreadableStore()

        let text = try Tools.call(name: "status", arguments: nil, store: store)

        XCTAssertTrue(
            text.contains("could not be read"),
            "status hid the read failure, said: \(text)")
        assertMakesNoClaimAboutAnEmptyLife(text, tool: "status")
    }

    /// `recall`'s headline is the sentence a reader acts on. "Nothing on this Mac matched X" is a
    /// negative result — it claims the local half looked. It was printed verbatim when the local
    /// half had never run, which turns a broken reader into evidence that the thing never happened.
    func testRecallHeadlineNeverReportsAFailedLocalSearchAsANegativeResult() {
        let searched = Tools.recallHeadline(
            query: "chinchilla", range: "", liveMatches: 0, omiRelated: 3, localSearched: true)
        let neverRan = Tools.recallHeadline(
            query: "chinchilla", range: "", liveMatches: 0, omiRelated: 3, localSearched: false)

        XCTAssertNotEqual(
            searched, neverRan,
            "a search that ran and a search that could not run got the same headline")
        XCTAssertTrue(
            searched.contains("searched") && searched.contains("no match"),
            "an executed, empty local search must be reported as one: \(searched)")
        XCTAssertTrue(
            neverRan.contains("not searched"),
            "a local half that never ran must say so: \(neverRan)")
        XCTAssertFalse(
            neverRan.lowercased().contains("nothing on this mac matched"),
            "a failed search was still headlined as a negative result: \(neverRan)")

        // A real match is still a match — the fix must not hedge the one confident case.
        let matched = Tools.recallHeadline(
            query: "pricing", range: "", liveMatches: 2, omiRelated: 0, localSearched: true)
        XCTAssertTrue(matched.contains("2 matches for \"pricing\""), matched)
    }

    /// The same distinction one level down, for the empty-result sentence every tool shares.
    func testAnEmptyAnswerNamesWhichHalvesWereActuallySearched() {
        let both = Tools.nothingFound(
            what: "conversations", localSearched: true, omiSearched: true, omiClause: "it was searched")
        XCTAssertTrue(both.contains("Both halves were searched"), both)

        let localOnly = Tools.nothingFound(
            what: "conversations", localSearched: true, omiSearched: false,
            omiClause: "no Omi MCP API key is configured")
        XCTAssertTrue(localOnly.contains("The Omi account was **not** searched"), localOnly)

        let omiOnly = Tools.nothingFound(
            what: "conversations", localSearched: false, omiSearched: true, omiClause: "it was searched")
        XCTAssertTrue(omiOnly.contains("local capture was **not** searched"), omiOnly)

        // Nothing ran at all. This must never read as a result of any kind.
        let neither = Tools.nothingFound(
            what: "conversations", localSearched: false, omiSearched: false,
            omiClause: "no Omi MCP API key is configured")
        XCTAssertTrue(neither.contains("No search ran"), neither)
        XCTAssertTrue(neither.contains("not a negative result"), neither)
    }

    // MARK: - How far back the account really goes

    /// `status` reported the date of conversation number 501 as the depth of the account. On a busy
    /// account that is a couple of months, while the account itself goes back years — so a model
    /// asking "how far back do you know me?" was told a few months and then declined to search
    /// earlier. This is that account: 501 back lands in June 2026, the record starts in August 2024.
    func testTheHistoryProbeIsWalkedPastItsOwnSampleWithinARequestBudget() {
        let earliest = epoch("2024-08-12")
        let newest = epoch("2026-07-20")
        let sampled = epoch("2026-06-09")

        var probes = 0
        let floor = Tools.deepenHistory(from: sampled) { anchor in
            probes += 1
            // The account, honestly simulated: the newest conversation at or before the anchor.
            guard anchor >= earliest else { return .empty }
            return .found(min(anchor, newest))
        }

        XCTAssertLessThanOrEqual(
            probes, Tools.deepeningProbeBudget, "the walk went over its request budget")
        XCTAssertFalse(floor.filterIgnored)
        XCTAssertFalse(floor.haltedByFailure)
        XCTAssertGreaterThan(
            sampled - floor.provenOldest, 365 * 86_400,
            "the walk did not get materially past the sample it started from")
        XCTAssertGreaterThanOrEqual(
            floor.provenOldest, earliest, "the walk claimed a record older than the account holds")
        XCTAssertLessThan(
            floor.emptyAtOrBefore ?? .infinity, earliest,
            "the bracket excluded records the account really holds")
    }

    /// A request that failed is not an empty account. Folding the two together would print
    /// "nothing before <date>" about an account with years of history behind it.
    func testAFailedProbeIsNeverRenderedAsTheAccountHavingNothingOlder() {
        let sampled = epoch("2026-06-09")

        let floor = Tools.deepenHistory(from: sampled) { _ in .unavailable }

        XCTAssertTrue(floor.haltedByFailure)
        XCTAssertNil(floor.emptyAtOrBefore, "a failed request was recorded as an empty account")
        XCTAssertEqual(floor.provenOldest, sampled)

        let text = Tools.historyDepthLines(probeOffset: 500, sampledStart: sampled, floor: floor)
            .joined(separator: "\n")
        XCTAssertFalse(
            text.contains("holds nothing at or before"),
            "a failed probe was reported as proof the history stops there: \(text)")
        XCTAssertTrue(text.contains("could not be read"), text)
    }

    /// A date filter the server ignored proves nothing about depth.
    func testADeepProbeThatIgnoresTheDateFilterProducesNoClaim() {
        let sampled = epoch("2026-06-09")
        let newest = epoch("2026-07-20")

        let floor = Tools.deepenHistory(from: sampled) { _ in .found(newest) }

        XCTAssertTrue(floor.filterIgnored)
        XCTAssertEqual(floor.provenOldest, sampled, "a claim was built on an unapplied filter")

        let text = Tools.historyDepthLines(probeOffset: 500, sampledStart: sampled, floor: floor)
            .joined(separator: "\n")
        XCTAssertFalse(text.contains(ContextTime.describe(newest)), text)
        XCTAssertTrue(text.contains("did not apply"), text)
    }

    /// The rendering half: whatever the probe found, the sampled date must never be presented as
    /// the date the user's record begins, and the reader must be told that searching earlier works.
    func testStatusPresentsTheProbeDepthAsASampleAndNotAsTheStartOfTheRecord() {
        let sampled = epoch("2026-06-09")
        let proven = epoch("2024-12-08")
        let floor = Tools.HistoryFloor(
            startedFrom: sampled,
            provenOldest: proven,
            emptyAtOrBefore: epoch("2024-06-09"),
            probesUsed: 4,
            filterIgnored: false,
            haltedByFailure: false
        )

        let text = Tools.historyDepthLines(probeOffset: 500, sampledStart: sampled, floor: floor)
            .joined(separator: "\n")

        XCTAssertTrue(
            text.contains(ContextTime.describe(sampled)), "the sample itself is still reported")
        XCTAssertTrue(
            text.contains(ContextTime.describe(proven)),
            "status kept quiet about the older record the probe proved: \(text)")
        XCTAssertTrue(
            text.contains("not the start of the record"),
            "the sample was presented as a fact about the user's history: \(text)")
        XCTAssertTrue(
            text.contains("`since`"),
            "status did not tell the reader that searching earlier still works: \(text)")

        // Without any deepening at all the framing must still hold — a probe is a probe.
        let sampleOnly = Tools.historyDepthLines(probeOffset: 500, sampledStart: sampled, floor: nil)
            .joined(separator: "\n")
        XCTAssertTrue(sampleOnly.contains("not the start of the record"), sampleOnly)
    }

    /// An empty deep probe is ambiguous — few conversations, or one request that failed — and the
    /// old wording asserted the first. It may not be reported as a count.
    func testAnEmptyDeepProbeIsNotReportedAsACountOfTheAccount() {
        let text = Tools.historyDepthLines(probeOffset: 500, sampledStart: nil, floor: nil)
            .joined(separator: "\n")

        XCTAssertTrue(text.contains("cannot tell which"), text)
        XCTAssertTrue(text.contains("not a count"), text)
    }

    // MARK: - `screen`: the order and the filters it claims

    /// The header promises newest-first. Whatever order the two halves hand over, the rendering must
    /// deliver the order it printed — a list read as newest-first that is not is worse than an
    /// unordered one, because nothing in the output reveals the mistake.
    func testScreenRendersNewestFirstAndSaysSo() throws {
        let store = try screenStore()

        let text = try Tools.call(name: "screen", arguments: [:], store: store)

        XCTAssertTrue(text.contains("newest first"), "screen stopped claiming an order: \(text)")
        let positions = ["CHARLIE-NEWEST", "BRAVO-MIDDLE", "ALPHA-OLDEST"].map { marker -> Int in
            guard let range = text.range(of: marker) else { return -1 }
            return text.distance(from: text.startIndex, to: range.lowerBound)
        }
        XCTAssertFalse(positions.contains(-1), "screen dropped a record it should have shown: \(text)")
        XCTAssertEqual(
            positions, positions.sorted(),
            "screen claimed newest-first and rendered another order: \(text)")
    }

    /// A printed filter is a claim about what was excluded. Applying it in the rendering layer is
    /// what makes the claim true whatever the query underneath did with `since`.
    func testScreenOnlyShowsWhatIsInsideTheRangeItPrints() throws {
        let store = try screenStore()

        let text = try Tools.call(
            name: "screen",
            arguments: [
                "since": .number(screenBase - 60),
                "until": .number(screenBase + 660),
            ],
            store: store)

        XCTAssertTrue(text.contains("ALPHA-OLDEST"), "the in-range record is missing: \(text)")
        XCTAssertTrue(text.contains("BRAVO-MIDDLE"), "the in-range record is missing: \(text)")
        XCTAssertFalse(
            text.contains("CHARLIE-NEWEST"), "a record after `until` was printed anyway: \(text)")
        XCTAssertFalse(
            text.contains("DELTA-LAST-YEAR"), "a record before `since` was printed anyway: \(text)")
    }

    /// The decision itself, at the seam the tool uses. Undated records cannot be judged against a
    /// window, so they are kept and flagged rather than counted as inside it.
    func testRangeEnforcementKeepsOnlyWhatItCanVouchFor() {
        let since = epoch("2026-07-01")
        let until = epoch("2026-07-05")

        XCTAssertTrue(Tools.isWithinRange(epoch("2026-07-03"), since: since, until: until))
        XCTAssertFalse(Tools.isWithinRange(epoch("2026-06-30"), since: since, until: until))
        XCTAssertFalse(Tools.isWithinRange(epoch("2026-07-06"), since: since, until: until))
        XCTAssertTrue(Tools.isWithinRange(0, since: since, until: until), "an undated record is kept")
        XCTAssertTrue(Tools.isWithinRange(epoch("2020-01-01"), since: nil, until: nil))
    }

    // MARK: - The two halves are not equally fresh

    /// Omi ingests screen text hours after it happened while conversations arrive in minutes, so the
    /// freshest screen data is exactly what the account half cannot see. Unsaid, a model reads that
    /// gap as "the user was not looking at that".
    func testScreenWarnsThatTheOmiHalfLagsHoursBehind() {
        let now = ContextTime.now

        let live = Tools.screenLagSentence(until: nil, now: now)
        XCTAssertTrue(
            live?.contains("not synced to Omi yet") == true,
            "an unbounded screen query must carry the lag caveat, said: \(live ?? "nothing")")
        XCTAssertNotNil(
            Tools.screenLagSentence(until: now - 600, now: now),
            "a window inside the lag must carry the caveat")
        XCTAssertNil(
            Tools.screenLagSentence(until: now - 5 * 3_600, now: now),
            "a window that closed long before the lag does not need the caveat")
    }

    func testStatusSaysTheOmiScreenHalfRunsHoursBehindThisMac() throws {
        let store = try seededStore()

        let text = try Tools.call(name: "status", arguments: nil, store: store)

        XCTAssertTrue(text.contains("Freshness"), "status said nothing about freshness: \(text)")
        XCTAssertTrue(
            text.contains("screen"), "status did not name the half that lags: \(text)")
        XCTAssertTrue(
            text.contains(#"read that gap as "it was not on screen""#),
            "status did not tell the reader what the lag means: \(text)")
    }

    // MARK: - Invalid arguments

    func testInvalidArgumentsAreToolErrors() throws {
        let store = try seededStore()

        // Required argument missing: answering "no results" would tell Claude the user never said it.
        XCTAssertThrowsError(try Tools.call(name: "recall", arguments: nil, store: store))
        XCTAssertThrowsError(try Tools.call(name: "transcript", arguments: [:], store: store))
        // Unparseable dates are an explicit error, not a silently ignored filter.
        XCTAssertThrowsError(
            try Tools.call(
                name: "recall", arguments: ["query": "pricing", "since": "soonish"], store: store))
        XCTAssertThrowsError(try Tools.call(name: "no_such_tool", arguments: nil, store: store))
    }

    // MARK: - Helpers

    /// Valid arguments for every tool, so a test exercises the path it means to and not an
    /// argument-validation failure on the way in.
    private func validArguments() -> [(String, JSONValue?)] {
        [
            ("recall", ["query": "pricing"]),
            ("recent", ["minutes": 30]),
            ("conversations", [:]),
            ("transcript", ["session_id": 1]),
            ("screen", [:]),
            ("activity", ["since": "yesterday"]),
            ("status", nil),
        ]
    }

    private func assertSameDay(
        _ epoch: Double,
        _ day: String,
        file: StaticString = #filePath,
        line: UInt = #line
    ) {
        let date = Date(timeIntervalSince1970: epoch)
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.dateFormat = "yyyy-MM-dd"
        let local = formatter.string(from: date)
        formatter.timeZone = TimeZone(identifier: "UTC")
        let utc = formatter.string(from: date)
        XCTAssertTrue(
            local == day || utc == day,
            "expected \(day), parsed to \(local) locally / \(utc) UTC",
            file: file, line: line)
    }

    /// Fails the test if a tool turned a reader fault into a claim about the user's life.
    private func assertMakesNoClaimAboutAnEmptyLife(
        _ text: String,
        tool: String,
        file: StaticString = #filePath,
        line: UInt = #line
    ) {
        for claim in [
            "has captured nothing on this Mac",
            "has never captured anything",
            "has recorded nothing locally",
            "no data captured yet",
        ] {
            XCTAssertFalse(
                text.contains(claim),
                "\(tool) asserted an empty history (\"\(claim)\") from a database it could not read",
                file: file, line: line)
        }
    }

    /// A database that opens and then fails every query — the third state, and the one the suite
    /// had no coverage for. A zero-length file is a valid, empty SQLite database: it opens read-only
    /// (no migrations run in that mode) and every query then fails on a missing table, which is what
    /// a reader sees against a database written by a different schema.
    private func unreadableStore() throws -> ContextStore {
        let root = FileManager.default.temporaryDirectory
            .appendingPathComponent("ambient-unreadable-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        addTeardownBlock { try? FileManager.default.removeItem(at: root) }

        let url = root.appendingPathComponent("context.db")
        XCTAssertTrue(FileManager.default.createFile(atPath: url.path, contents: Data()))

        let store: ContextStore
        do {
            store = try ContextStore(url: url, readOnly: true)
        } catch {
            throw XCTSkip("this environment will not open an empty database read-only: \(error)")
        }
        // Guard the premise: if the queries started succeeding, the fixture no longer exercises the
        // state under test and the assertions below would be vacuous.
        XCTAssertThrowsError(try Queries.status(store), "the fixture store answered a query")
        return store
    }

    /// The first frame in `screenStore`, and the anchor every range in these tests is written
    /// against. 2026-07-22T08:00:00Z, fixed — a test that reads the wall clock fails on a Tuesday.
    private let screenBase: Double = 1_784_707_200

    /// Four screen observations with unmistakable markers: three inside one morning and one a year
    /// earlier, so both ordering and range enforcement are observable in the rendered text.
    private func screenStore() throws -> ContextStore {
        let root = FileManager.default.temporaryDirectory
            .appendingPathComponent("ambient-screen-tests-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        addTeardownBlock { try? FileManager.default.removeItem(at: root) }

        let store = try ContextStore(url: root.appendingPathComponent("context.db"))
        let frames: [(Double, String)] = [
            (screenBase - 365 * 86_400, "DELTA-LAST-YEAR"),
            (screenBase, "ALPHA-OLDEST"),
            (screenBase + 600, "BRAVO-MIDDLE"),
            (screenBase + 1_200, "CHARLIE-NEWEST"),
        ]
        for (at, marker) in frames {
            _ = try store.insertFrame(
                Frame(
                    capturedAt: at,
                    appName: "Safari",
                    windowTitle: "Notes",
                    ocrText: "\(marker) on screen"))
        }
        return store
    }

    /// A fixed local-midnight epoch for a `yyyy-MM-dd` day.
    private func epoch(_ day: String) -> Double {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.dateFormat = "yyyy-MM-dd"
        formatter.timeZone = TimeZone.current
        return formatter.date(from: day)?.timeIntervalSince1970 ?? 0
    }

    /// One conversation and one frame, dated in 2025 so a rendered coverage window is unmistakable.
    private func seededStore() throws -> ContextStore {
        let root = FileManager.default.temporaryDirectory
            .appendingPathComponent("ambient-tools-tests-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        addTeardownBlock { try? FileManager.default.removeItem(at: root) }

        let store = try ContextStore(url: root.appendingPathComponent("context.db"))
        // 2025-10-09T08:53:20Z, fixed: a test that reads the wall clock is a test that fails on a
        // Tuesday for no reason.
        let base: Double = 1_760_000_000
        let sessionId = try store.openSession(at: base, appHint: "zoom.us")
        try store.closeSession(sessionId, at: base + 600)
        _ = try store.insertSegment(
            Segment(
                sessionId: sessionId,
                startedAt: base + 10,
                endedAt: base + 15,
                source: .mic,
                text: "we decided to ship the pricing change on Friday"))
        _ = try store.insertFrame(
            Frame(
                capturedAt: base + 100,
                appName: "Google Chrome",
                windowTitle: "Pricing — Notion",
                ocrText: "pricing change rollout notes"))
        return store
    }
}
