import ContextCore
import ContextMCPKit
import Foundation
import XCTest

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
