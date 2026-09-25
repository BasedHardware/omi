import ContextCore
import Foundation
import XCTest

// The honesty seams — `nothingFound`, `recallHeadline`, `deepenHistory`, `historyDepthLines`,
// `isWithinRange`, `screenLagSentence` — are internal on purpose: they are the decisions worth
// testing, and testing them through a live Omi account would be neither hermetic nor possible.
@testable import ContextMCPKit

/// The twelve tools: their declarations, their date arguments, and what they say when there is
/// nothing to say.
///
/// The declarations are as much of the product as the queries behind them — a tool Claude cannot
/// tell when to reach for is a tool that never runs.
final class ToolsTests: XCTestCase {
    /// Exactly the set in CONTRACTS.md. Renaming one silently unregisters it from every existing
    /// Claude session, so this list is deliberately spelled out rather than derived.
    private let expectedNames: Set<String> = [
        "recall", "recent", "conversations", "transcript", "screen", "look", "activity", "status",
        "get_memories", "create_memory", "edit_memory", "delete_memory",
    ]

    /// name → the parameters the contract gives it.
    private let expectedParameters: [String: Set<String>] = [
        "recall": ["query", "since", "until", "limit"],
        "recent": ["minutes"],
        "conversations": ["since", "until", "limit"],
        "transcript": ["session_id"],
        "screen": ["since", "until", "app", "limit"],
        "look": ["at", "app", "count"],
        "activity": ["since", "until"],
        "status": [],
        "get_memories": ["limit", "offset", "sort", "categories"],
        "create_memory": ["content", "category"],
        "edit_memory": ["memory_id", "content"],
        "delete_memory": ["memory_id"],
    ]

    /// The prose half of a tool call. Eleven of the twelve tools produce nothing else, and every
    /// assertion in this file that predates `look` is about the prose.
    private func toolText(
        name: String, arguments: JSONValue?, store: ContextStore?, openError: Error? = nil
    ) throws -> String {
        try Tools.call(name: name, arguments: arguments, store: store, openError: openError).text
    }

    // MARK: - Declarations

    func testToolsAreExactlyTheOnesInTheContract() {
        XCTAssertEqual(Tools.all.count, 12)
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
            "create_memory": ["content"],
            "edit_memory": ["memory_id", "content"],
            "delete_memory": ["memory_id"],
        ]

        for tool in Tools.all {
            let declared = Set((tool.inputSchema["required"]?.arrayValue ?? []).compactMap(\.stringValue))
            XCTAssertEqual(declared, required[tool.name] ?? [], "\(tool.name) required list drifted")
        }
    }

    func testMemoryWritesFailClearlyWhenNoOmiKeyIsConfigured() throws {
        let create = try toolText(
            name: "create_memory",
            arguments: ["content": .string("Nik is the founder")],
            store: nil)
        XCTAssertTrue(create.contains("no Omi MCP API key is configured"), create)

        let edit = try toolText(
            name: "edit_memory",
            arguments: ["memory_id": .string("memory-1"), "content": .string("corrected")],
            store: nil)
        XCTAssertTrue(edit.contains("no Omi MCP API key is configured"), edit)

        let delete = try toolText(
            name: "delete_memory",
            arguments: ["memory_id": .string("memory-1")],
            store: nil)
        XCTAssertTrue(delete.contains("no Omi MCP API key is configured"), delete)
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
            let text = try toolText(name: name, arguments: arguments, store: nil)

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
            let text = try toolText(name: name, arguments: arguments, store: nil).lowercased()
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

        let text = try toolText(
            name: "recall", arguments: ["query": "chinchilla"], store: store)

        XCTAssertFalse(text.contains("pricing"), "recall returned a row that does not match")
        XCTAssertTrue(text.contains("2025"), "empty recall lost the coverage window, said: \(text)")
    }

    func testStatusRendersTheCoverageWindow() throws {
        let store = try seededStore()

        let text = try toolText(name: "status", arguments: nil, store: store)

        XCTAssertTrue(text.contains("2025"), "status lost the coverage window, said: \(text)")
    }

    func testToolsRenderCapturedContext() throws {
        let store = try seededStore()

        let text = try toolText(name: "recall", arguments: ["query": "pricing"], store: store)

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
            let text = try toolText(name: name, arguments: arguments, store: store)

            // **Either disclosure counts, and the reason there are two is worth recording.**
            //
            // The tool has two ways of saying the local read failed, and which one it reaches for
            // depends on whether the *Omi* half found anything: with nothing to show it prints the
            // reader-fault footer, and with related memories to show it leads with the headline
            // instead. This assertion used to name only the footer, and it held for one reason —
            // `ContextPaths.omiDatabaseURL` was resolving to an empty test fixture rather than to
            // the user's real Omi database (see `OmiMemoryStoreTests`), so the Omi half was always
            // empty in this process and the second branch was unreachable. With that scan fixed,
            // this test now reads whatever memories the machine running it happens to hold.
            //
            // Naming both sentences keeps every guard this test exists for — the read must be
            // disclosed, and the three claims below must never appear — without the answer
            // depending on the developer's own account. It does not close the underlying gap:
            // `Tools` reaches `OmiBackend.shared`, which reaches `OmiMemoryStore.shared`, so this
            // suite still reads a real local database when one is installed.
            XCTAssertTrue(
                text.contains("present on this Mac but could not be read")
                    || text.contains("the search could not run"),
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
            try toolText(name: "recent", arguments: ["minutes": 30], store: store),
            "recent answered from a database it could not read")
        XCTAssertThrowsError(
            try toolText(name: "activity", arguments: ["since": "yesterday"], store: store),
            "activity answered from a database it could not read")
    }

    func testStatusSaysTheDatabaseOpenedAndFailedRatherThanThatNothingWasCaptured() throws {
        let store = try unreadableStore()

        let text = try toolText(name: "status", arguments: nil, store: store)

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

    // MARK: - A sensor that was switched off

    /// A search that ran perfectly over a microphone nobody turned on is not evidence about the
    /// user. "Both halves were searched, so this is a real empty result" is true and, alone,
    /// licenses a model to report that nothing was said or on screen — so the empty answer has to
    /// name the permission that made it empty.
    func testAnEmptyAnswerNamesACaptureSensorThatWasSwitchedOff() throws {
        let clause = try XCTUnwrap(
            Tools.deniedCaptureClause(
                CaptureState(
                    capturing: true,
                    capabilities: [
                        CapabilityReport(name: "microphone", granted: true, detail: "Granted"),
                        CapabilityReport(
                            name: "screen", granted: false,
                            detail: "Screen Recording is off in System Settings"),
                    ])),
            "a denied permission produced no disclosure at all")

        // The wording `status` uses for the same fact, so a reader does not have to work out that
        // two phrasings are one claim.
        XCTAssertTrue(clause.contains("Not granted"), clause)
        XCTAssertTrue(clause.contains("never captured at all"), clause)
        XCTAssertTrue(clause.lowercased().contains("screen recording"), clause)
        XCTAssertFalse(
            clause.lowercased().contains("microphone"),
            "a granted sensor was named as one that was off: \(clause)")
    }

    /// The rule that keeps this from becoming its own confident falsehood: what the heartbeat does
    /// not say, the answer does not claim. Silence is the only safe rendering of unknown — the
    /// failure to avoid is not a missing disclosure but a manufactured reassurance.
    func testUnknownCapturePermissionsMakeNoClaimInEitherDirection() {
        XCTAssertNil(
            Tools.deniedCaptureClause(nil),
            "an absent or unreadable heartbeat became a claim about permissions")
        XCTAssertNil(
            Tools.deniedCaptureClause(CaptureState(capturing: false, capabilities: [])),
            "a heartbeat that reports no capabilities knows nothing and must say nothing")
        XCTAssertNil(
            Tools.deniedCaptureClause(
                CaptureState(
                    capturing: true,
                    capabilities: [
                        CapabilityReport(name: "microphone", granted: true, detail: "Granted"),
                        CapabilityReport(name: "screen", granted: true, detail: "Granted"),
                    ])),
            "every permission granted needs no clause")
    }

    /// A stale beat means the app is not running, not that the grant was restored: a TCC decision
    /// outlives the process that reported it, and nothing was being captured while the app was gone
    /// either. Dropping the disclosure on staleness is what made this evidence expire after 90
    /// seconds — including inside a slow test run.
    func testALastKnownDenialSurvivesAStaleHeartbeat() throws {
        let stale = CaptureState(
            capturing: false,
            capabilities: [
                CapabilityReport(name: "screen", granted: false, detail: "Screen Recording is off"),
            ],
            updatedAt: ContextTime.now - (CaptureState.stalenessSeconds + 600))

        let clause = try XCTUnwrap(
            Tools.deniedCaptureClause(stale), "a stale beat dropped a denial it had recorded")

        XCTAssertTrue(clause.contains("never captured at all"), clause)
        XCTAssertTrue(
            clause.contains("last reported"),
            "a last-known grant must be dated rather than stated as current: \(clause)")
    }

    // MARK: - Account history sample

    /// `status` gets one bounded account probe. Its result is useful reachability evidence, but not
    /// a license to make hidden history-crawl requests or to describe the sampled row as the start
    /// of a person's record.
    func testStatusPresentsTheSingleHistoryProbeAsASampleNotARecordBoundary() {
        let sampled = epoch("2026-06-09")

        let text = Tools.historySampleLine(probeOffset: 500, sampledStart: sampled)

        XCTAssertTrue(text.contains(ContextTime.describe(sampled)), text)
        XCTAssertTrue(text.contains("not the start of the record"), text)
        XCTAssertTrue(text.contains("`since`"), text)
        XCTAssertFalse(text.contains("extra request"), text)
    }

    func testAnEmptyHistoryProbeIsNotReportedAsAnAccountCount() {
        let text = Tools.historySampleLine(probeOffset: 500, sampledStart: nil)

        XCTAssertTrue(text.contains("cannot tell which"), text)
        XCTAssertTrue(text.contains("not a count"), text)
    }

    // MARK: - `screen`: the order and the filters it claims

    /// The header promises newest-first. Whatever order the two halves hand over, the rendering must
    /// deliver the order it printed — a list read as newest-first that is not is worse than an
    /// unordered one, because nothing in the output reveals the mistake.
    func testScreenRendersNewestFirstAndSaysSo() throws {
        let store = try screenStore()

        let text = try toolText(name: "screen", arguments: [:], store: store)

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

        let text = try toolText(
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

    /// `conversations` prints the same kind of promise in its header and used to leave it entirely
    /// to whichever half answered — the local query, and an Omi endpoint whose date bounds are a
    /// request rather than a guarantee. A conversation listed under a window it falls outside is the
    /// worst shape this failure takes: the reader is confident about the wrong slice of the day.
    func testConversationsListsOnlyWhatIsInsideTheRangeItPrints() throws {
        let store = try conversationStore()

        let text = try toolText(
            name: "conversations",
            arguments: ["since": .number(base + 1_000), "until": .number(base + 5_000)],
            store: store)

        XCTAssertTrue(text.contains("#2"), "the in-range conversation is missing: \(text)")
        XCTAssertFalse(text.contains("#1"), "a conversation before `since` was listed: \(text)")
        XCTAssertFalse(text.contains("#3"), "a conversation after `until` was listed: \(text)")
        // The header is the claim; both boundaries it names must be the ones that were applied.
        XCTAssertTrue(text.contains("between"), "the applied range was not printed: \(text)")
    }

    /// The enforcement seam itself, which is the half an offline test can reach: the local query
    /// filters correctly on its own, so only this exercises what the tool layer adds on top of a
    /// half that did not. Undated records cannot be judged against a window, so they are kept and
    /// counted rather than silently treated as inside it.
    func testRangeEnforcementIsOneSeamForEveryListingTool() {
        struct Record { let id: String; let at: Double }
        let records = [
            Record(id: "inside", at: 500),
            Record(id: "before", at: 10),
            Record(id: "after", at: 5_000),
            Record(id: "undated", at: 0),
        ]

        let ranged = Tools.restrictToRange(records, since: 100, until: 1_000, at: { $0.at })

        XCTAssertEqual(ranged.kept.map(\.id), ["inside", "undated"])
        XCTAssertEqual(ranged.droppedOutOfRange, 2)
        XCTAssertEqual(ranged.undated, 1)

        // What it cost is stated, not hidden: a silently emptied window and a genuinely empty one
        // are different answers.
        let notes = Tools.rangeEnforcementNotes(ranged, noun: "conversation")
        XCTAssertEqual(notes.count, 2, "\(notes)")
        XCTAssertTrue(notes[0].contains("2 conversations"), notes[0])
        XCTAssertTrue(notes[0].contains("were dropped here"), notes[0])
        XCTAssertTrue(notes[1].contains("no timestamp"), notes[1])

        // No window asked for is no window enforced — and nothing to disclose.
        let unbounded = Tools.restrictToRange(records, since: nil, until: nil, at: { $0.at })
        XCTAssertEqual(unbounded.kept.count, records.count)
        XCTAssertTrue(Tools.rangeEnforcementNotes(unbounded, noun: "conversation").isEmpty)
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

        let text = try toolText(name: "status", arguments: nil, store: store)

        XCTAssertTrue(text.contains("Freshness"), "status said nothing about freshness: \(text)")
        XCTAssertTrue(
            text.contains("screen"), "status did not name the half that lags: \(text)")
        XCTAssertTrue(
            text.contains(#"read that gap as "it was not on screen""#),
            "status did not tell the reader what the lag means: \(text)")
    }

    // MARK: - A guess must not read as a fact
    //
    // The dogfooding failure these pin: the microphone picked up music playing in the room, the
    // recogniser wrote the lyrics out as first-person speech, and this layer printed them as `*me*`
    // — the same shape, the same authority, the same page as things the user had really said. The
    // fix has to keep the line visible (hiding it makes the record look cleaner than it is) while
    // making it impossible to read as a quote.

    /// The whole pipeline, from a stored score to what the model actually reads: one line the
    /// transcriber was unsure of, one from before scores were kept, one it was confident about.
    func testTranscriptMarksTheUncertainLineAndOnlyTheUncertainLine() throws {
        let fixture = try confidenceStore()

        let text = try toolText(
            name: "transcript",
            arguments: ["session_id": .number(Double(fixture.sessionId))],
            store: fixture.store)

        // Marked, not hidden: a filtered transcript is a tidier lie, not a truer record.
        XCTAssertTrue(text.contains("MUSIC-LYRIC"), "the low-confidence line was dropped: \(text)")
        XCTAssertTrue(
            line(containing: "MUSIC-LYRIC", in: text).contains(Tools.uncertainTranscriptMarker),
            "a line the transcriber doubted was rendered as fact: \(text)")

        // Unknown is not doubtful. Every line recorded before the column existed has a nil score,
        // and marking those would back-date doubt onto the whole archive and mean nothing.
        XCTAssertFalse(
            line(containing: "PRE-COLUMN", in: text).contains(Tools.uncertainTranscriptMarker),
            "an unscored line was rendered as low confidence: \(text)")

        XCTAssertFalse(
            line(containing: "REAL-SPEECH", in: text).contains(Tools.uncertainTranscriptMarker),
            "a confident line was hedged: \(text)")
    }

    /// The decision itself, at the seam, including the two scores that must not be read as doubt.
    func testTheConfidenceBarMarksBelowItselfAndNothingElse() {
        let floor = Tools.transcriptConfidenceFloor

        XCTAssertTrue(Tools.isUncertainTranscript(speech("music", confidence: floor - 0.01)))
        XCTAssertTrue(Tools.isUncertainTranscript(speech("music", confidence: 0.0)))
        XCTAssertFalse(Tools.isUncertainTranscript(speech("real", confidence: floor)))
        XCTAssertFalse(Tools.isUncertainTranscript(speech("real", confidence: 0.99)))
        XCTAssertFalse(
            Tools.isUncertainTranscript(speech("older than the column", confidence: nil)),
            "nil confidence is unknown, not doubtful")

        // Not a probability on the scale this layer reads — a log-probability, say — so it says
        // nothing. Reading it as doubt would mark every line in the database at once.
        XCTAssertFalse(Tools.isUncertainTranscript(speech("log prob", confidence: -3.2)))
        XCTAssertFalse(Tools.isUncertainTranscript(speech("out of range", confidence: 12)))

        // The bar belongs to `Hit`; a second copy of the number in the rendering layer is how two
        // layers start disagreeing about which lines are doubtful.
        XCTAssertEqual(floor, Hit.lowConfidenceFloor)
    }

    /// OCR confidence is a different measurement of a different thing, and `Queries` carries a
    /// collapsed hit's score through rather than defaulting it — so a screen row could arrive here
    /// with a number attached. It must never wear a "may be background audio" mark.
    func testAScreenHitIsNeverMarkedWithSpeechUncertainty() {
        let frame = Hit(
            kind: "screen", at: base, text: "OCR-TEXT", app: "Safari", window: "Notes", confidence: 0.1)

        XCTAssertFalse(Tools.isUncertainTranscript(frame))
        XCTAssertFalse(
            Tools.renderHitsOnly([frame], order: .oldestFirst).contains(Tools.uncertainTranscriptMarker),
            "a screen row was marked with transcription doubt")
    }

    /// A marker met cold is a decoration. The convention is stated once, above the first line that
    /// uses it, so a model reading a page of results knows what it means before it needs to.
    func testTheUncertaintyConventionIsStatedOnceAboveTheFirstMarkedLine() throws {
        let text = Tools.renderHitsOnly(
            [
                speech("LYRIC-ONE", at: base, confidence: 0.2),
                speech("LYRIC-TWO", at: base + 60, confidence: 0.3),
            ],
            order: .oldestFirst)

        XCTAssertEqual(
            text.components(separatedBy: "Confidence: a line marked").count - 1, 1,
            "the convention was stated more or less than once: \(text)")
        let legendAt = try XCTUnwrap(offset(of: "Confidence: a line marked", in: text))
        let firstMarkedAt = try XCTUnwrap(offset(of: "LYRIC-ONE", in: text))
        XCTAssertLessThan(
            legendAt, firstMarkedAt,
            "the convention arrived after the line that needed it: \(text)")

        // And a page with nothing to doubt says nothing about doubt — a legend printed over clean
        // results teaches a reader to distrust everything, which is its own kind of noise.
        let clean = Tools.renderHitsOnly([speech("REAL-SPEECH", at: base, confidence: 0.95)], order: .oldestFirst)
        XCTAssertFalse(clean.contains("Confidence: a line marked"), clean)
        XCTAssertFalse(clean.contains(Tools.uncertainTranscriptMarker), clean)
    }

    // MARK: - The sync watermark, carried on the answer

    /// A caller who asks `screen` for "the last hour" gets nothing from the Omi half whether or not
    /// the user was at their screen, because that half runs hours behind. Finding out which used to
    /// take a second `status` call — so the answer now carries the watermark itself.
    func testScreenCarriesTheSyncWatermarkWithoutASecondStatusCall() throws {
        let store = try screenStore()

        let populated = try toolText(name: "screen", arguments: [:], store: store)
        XCTAssertTrue(
            populated.contains("Screen synced through:"),
            "screen did not say how far the account's screen history has synced: \(populated)")

        // The empty answer is where it decides the meaning, so it must be there too.
        let empty = try toolText(
            name: "screen",
            arguments: [
                "since": .number(screenBase - 10 * 86_400),
                "until": .number(screenBase - 9 * 86_400),
            ],
            store: store)
        XCTAssertFalse(empty.contains("ALPHA-OLDEST"), "the fixture window was not empty: \(empty)")
        XCTAssertTrue(
            empty.contains("Screen synced through:"),
            "an empty screen answer left the reader to infer the watermark: \(empty)")
    }

    func testRecallCarriesTheSyncWatermarkToo() throws {
        let store = try seededStore()

        let text = try toolText(name: "recall", arguments: ["query": "pricing"], store: store)

        XCTAssertTrue(text.contains("Screen synced through:"), text)
    }

    /// The three states are three different amounts of evidence, and only one of them is a
    /// measurement. An estimate dressed up as a timestamp is exactly the failure the rest of this
    /// file exists to prevent, one level down.
    func testAnEstimatedWatermarkSaysSoAndAnUnreadAccountPrintsNoTimeAtAll() {
        let now = ContextTime.now

        let observed = Tools.screenWatermark(
            newestOmiScreenRow: now - 3 * 3_600, accountRead: true,
            notReadClause: "", estimateReason: "", now: now)
        XCTAssertEqual(observed, .observed(now - 3 * 3_600))
        let observedText = Tools.screenWatermarkSentence(observed)
        XCTAssertTrue(observedText.contains(ContextTime.describe(now - 3 * 3_600)), observedText)
        XCTAssertTrue(
            observedText.contains("at least"),
            "a proven row is a floor, not the instant sync stopped: \(observedText)")

        let estimated = Tools.screenWatermark(
            newestOmiScreenRow: nil, accountRead: true,
            notReadClause: "", estimateReason: "no dated screen row came back", now: now)
        XCTAssertEqual(estimated, .estimated(now - Tools.omiScreenSyncLag, "no dated screen row came back"))
        let estimatedText = Tools.screenWatermarkSentence(estimated)
        XCTAssertTrue(estimatedText.contains("estimate"), estimatedText)
        XCTAssertTrue(
            estimatedText.contains(":00"),
            "an estimate was printed to the minute, which reads as a measurement: \(estimatedText)")

        // Nobody looked, so there is nothing to state — and an estimate of an unread account would
        // be a number with no evidence behind it at all.
        let unread = Tools.screenWatermark(
            newestOmiScreenRow: nil, accountRead: false,
            notReadClause: "no Omi MCP API key is configured", estimateReason: "", now: now)
        XCTAssertEqual(unread, .unavailable("no Omi MCP API key is configured"))
        let unreadText = Tools.screenWatermarkSentence(unread)
        XCTAssertTrue(unreadText.contains("unknown"), unreadText)
        XCTAssertFalse(
            unreadText.contains(where: \.isNumber),
            "a watermark nobody could read printed a time anyway: \(unreadText)")
    }

    // MARK: - Invalid arguments

    func testInvalidArgumentsAreToolErrors() throws {
        let store = try seededStore()

        // Required argument missing: answering "no results" would tell Claude the user never said it.
        XCTAssertThrowsError(try toolText(name: "recall", arguments: nil, store: store))
        XCTAssertThrowsError(try toolText(name: "transcript", arguments: [:], store: store))
        // Unparseable dates are an explicit error, not a silently ignored filter.
        XCTAssertThrowsError(
            try toolText(
                name: "recall", arguments: ["query": "pricing", "since": "soonish"], store: store))
        XCTAssertThrowsError(try toolText(name: "no_such_tool", arguments: nil, store: store))
    }

    /// A filter that is present but not a date in any reading used to return nil, which the caller
    /// reads as "no filter was asked for": the search then ran over everything *and the header
    /// printed no range at all*, so the caller believed it had bounded the question with nothing in
    /// the answer to say otherwise. Loud is the only safe outcome.
    func testATimeFilterOfTheWrongTypeIsRejectedRatherThanDropped() throws {
        let store = try seededStore()
        let wrongTypes: [(String, JSONValue)] = [
            ("a boolean", .bool(true)),
            ("an array", .array([.number(1), .number(2)])),
            ("an object", .object(["x": .number(1)])),
        ]

        for (label, value) in wrongTypes {
            XCTAssertThrowsError(
                try toolText(
                    name: "recall", arguments: ["query": "pricing", "since": value], store: store),
                "a `since` of \(label) was dropped rather than rejected")
        }

        // The one shape that may still pass through: an empty string is "no filter asked for", and
        // the header then prints no range, so nothing is claimed that was not applied.
        let unbounded = try toolText(
            name: "recall", arguments: ["query": "pricing", "since": ""], store: store)
        XCTAssertFalse(
            unbounded.split(separator: "\n").first?.lowercased().contains("since") ?? false,
            "an empty `since` was printed as an applied filter: \(unbounded)")
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

    /// Three conversations spread over three hours, one line each, so a `since` / `until` window
    /// can select exactly the middle one.
    private func conversationStore() throws -> ContextStore {
        let root = FileManager.default.temporaryDirectory
            .appendingPathComponent("ambient-conversations-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        addTeardownBlock { try? FileManager.default.removeItem(at: root) }

        let store = try ContextStore(url: root.appendingPathComponent("context.db"))
        for start in [base, base + 3_000, base + 9_000] {
            let sessionId = try store.openSession(at: start, appHint: "zoom.us")
            try store.closeSession(sessionId, at: start + 300)
            _ = try store.insertSegment(
                Segment(
                    sessionId: sessionId,
                    startedAt: start + 10,
                    endedAt: start + 15,
                    source: .mic,
                    text: "a line inside this conversation"))
        }
        return store
    }

    /// 2025-10-09T08:53:20Z, fixed — a test that reads the wall clock fails on a Tuesday.
    private let base: Double = 1_760_000_000

    private func speech(
        _ text: String,
        at: Double? = nil,
        confidence: Double?,
        kind: String = "said"
    ) -> Hit {
        // Through the initializer rather than by assignment: `Hit` derives its own low-confidence
        // flag there, and a hit whose flag disagreed with its score would test nothing real.
        Hit(kind: kind, at: at ?? base, text: text, confidence: confidence)
    }

    /// The rendered line carrying `marker`, so an assertion is about *that* line rather than about
    /// the page — the legend also names the marker, and a page-wide `contains` would pass on it.
    private func line(
        containing marker: String,
        in text: String,
        file: StaticString = #filePath,
        line: UInt = #line
    ) -> String {
        guard let found = text.split(separator: "\n").first(where: { $0.contains(marker) }) else {
            XCTFail("no rendered line contained \(marker): \(text)", file: file, line: line)
            return ""
        }
        return String(found)
    }

    private func offset(of needle: String, in text: String) -> Int? {
        text.range(of: needle).map { text.distance(from: text.startIndex, to: $0.lowerBound) }
    }

    /// One conversation of three lines: a song the microphone heard as the user's own speech (0.57,
    /// the score from the session that prompted this), a line from before scores were stored at all,
    /// and an ordinary confident sentence.
    private func confidenceStore() throws -> (store: ContextStore, sessionId: Int64) {
        let root = FileManager.default.temporaryDirectory
            .appendingPathComponent("ambient-confidence-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        addTeardownBlock { try? FileManager.default.removeItem(at: root) }

        let store = try ContextStore(url: root.appendingPathComponent("context.db"))
        let sessionId = try store.openSession(at: base, appHint: "Spotify")
        try store.closeSession(sessionId, at: base + 300)

        let lines: [(String, Double?)] = [
            ("MUSIC-LYRIC and I will always love you", 0.57),
            ("PRE-COLUMN recorded before confidence was stored", nil),
            ("REAL-SPEECH we ship the pricing change on Friday", 0.96),
        ]
        for (index, entry) in lines.enumerated() {
            let at = base + Double(10 + index * 10)
            _ = try store.insertSegment(
                Segment(
                    sessionId: sessionId,
                    startedAt: at,
                    endedAt: at + 4,
                    source: .mic,
                    text: entry.0,
                    confidence: entry.1))
        }
        return (store, sessionId)
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

    // MARK: - Screen is not optional

    /// Speech and screen answer different questions — what was said, and what was in front of them
    /// — so neither may starve the other. Screen rows rank below speech, so any limit smaller than
    /// the number of matches used to drop every one of them.
    ///
    /// Measured on real capture before the fix: `recall("boston")` returned ten spoken lines and
    /// **none** of the six screen moments that matched, one of which was the travel page the user
    /// was looking at while they spoke. Raising the limit brought them back, which is what proved
    /// they had been found and then discarded rather than never fetched.
    func testScreenSurvivesALimitSmallerThanTheSpeechThatOutranksIt() throws {
        let root = FileManager.default.temporaryDirectory
            .appendingPathComponent("ambient-screen-floor-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        addTeardownBlock { try? FileManager.default.removeItem(at: root) }
        let store = try ContextStore(url: root.appendingPathComponent("context.db"))

        // Comfortably more speech than the limit, so every screen row loses on rank alone.
        let sessionId = try store.openSession(at: base, appHint: "Arc")
        for index in 0..<30 {
            _ = try store.insertSegment(
                Segment(
                    sessionId: sessionId,
                    startedAt: base + Double(index),
                    endedAt: base + Double(index) + 1,
                    source: .mic,
                    text: "talking about the boston trip, line \(index)"))
        }
        try store.closeSession(sessionId, at: base + 40)
        for index in 0..<4 {
            _ = try store.insertFrame(
                Frame(
                    capturedAt: base + 100 + Double(index) * 60,
                    appName: "Arc",
                    windowTitle: "bus from ny to boston",
                    ocrText: "boston departures and fares"))
        }

        let text = try toolText(
            name: "recall", arguments: ["query": "boston", "limit": 10], store: store)

        XCTAssertTrue(
            text.split(separator: "\n").contains { $0.contains("*screen*") },
            "every screen match was crowded out by higher-ranked speech: \(text)")
        XCTAssertTrue(
            text.contains("boston departures") || text.contains("bus from ny to boston"),
            "a screen row survived but carried none of what was on screen: \(text)")
    }

    // MARK: - The client's inline ceiling

    /// A result larger than the client will inline is not a large answer — it is no answer. Claude
    /// Code writes an oversized tool result to a file and hands the model a path, and in the
    /// incident this guards, the model never opened it: a 67,000-character `recent` became a file
    /// path, and the one line that answered the question went unread.
    ///
    /// Asserted across every tool through the clamp the server actually applies, because the
    /// renderer budget that only four of the eleven pass through was never the whole ceiling.
    func testNoToolResultExceedsTheClientInlineCeiling() {
        let oversized = String(
            repeating: "- **1:06 PM** · *me* · live: a captured line long enough to matter\n", count: 5_000)
        XCTAssertGreaterThan(oversized.count, Tools.maxToolResultCharacters, "the fixture is not oversized")

        for tool in Tools.all.map(\.name) {
            XCTAssertLessThanOrEqual(
                Tools.clampToolResult(oversized, tool: tool).count, Tools.maxToolResultCharacters,
                "\(tool) can still emit a result the client will spool to a file")
        }
    }

    /// A result that stops early without saying so reads as a complete account of the window, and
    /// "nothing after 1:06 PM" then becomes evidence that nothing happened after 1:06 PM.
    ///
    /// And the recovery it offers has to be one the caller can actually perform: the shared note
    /// used to tell `recent` — whose only parameter is `minutes` — to narrow `since` / `until` or
    /// ask for a smaller `limit`.
    func testAClampedResultSaysSoAndNamesOnlyParametersTheToolAccepts() {
        let oversized = String(repeating: "captured context that runs well past the ceiling\n", count: 5_000)

        // Each tool's own schema. Written out rather than derived from `Tools.all` so that widening
        // a schema without revisiting the advice is a test failure, not a silent divergence.
        let accepts: [String: Set<String>] = [
            "recall": ["query", "since", "until", "limit"],
            "recent": ["minutes"],
            "conversations": ["since", "until", "limit"],
            "transcript": ["session_id"],
            "screen": ["since", "until", "app", "limit"],
            "look": ["at", "app", "count"],
            "activity": ["since", "until"],
            "status": [],
        ]
        let everyParameter: Set<String> = [
            "query", "since", "until", "limit", "minutes", "app", "session_id", "at", "count",
        ]

        for tool in Tools.all.map(\.name) {
            let clamped = Tools.clampToolResult(oversized, tool: tool)
            XCTAssertTrue(
                clamped.contains(Tools.clampedResultMarker),
                "\(tool) dropped the end of its answer without saying so")

            for parameter in everyParameter.subtracting(accepts[tool] ?? []) {
                XCTAssertFalse(
                    clamped.contains("`\(parameter)`"),
                    "\(tool) told the caller to use `\(parameter)`, which its schema does not accept")
            }
        }
    }

    /// The renderer drops the least relevant lines and explains itself; the boundary clamp can only
    /// cut the tail. So the renderer has to reach the ceiling first, or every long answer loses its
    /// end instead of its least useful middle.
    func testTheRendererTrimsBeforeTheBoundaryClampHasTo() {
        let hits = (0..<4_000).map {
            speech("line \($0) of captured speech about the Lisbon trip", at: base + Double($0), confidence: 0.9)
        }
        let rendered = Tools.renderHitsOnly(hits, order: .oldestFirst)

        XCTAssertLessThanOrEqual(
            rendered.count, Tools.maxToolResultCharacters,
            "the renderer handed the boundary clamp more than the client can inline")
        XCTAssertTrue(
            rendered.contains("omitted to keep this readable"),
            "the renderer dropped lines without telling the reader")
        XCTAssertEqual(
            Tools.clampToolResult(rendered, tool: "recent"), rendered,
            "the blunt clamp had to cut what the renderer should already have trimmed")
    }
}
