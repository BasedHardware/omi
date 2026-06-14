import XCTest

@testable import Omi_Computer

/// Tests for the per-query timing value type used by Track 2 telemetry.
///
/// The struct is pure: no I/O, no analytics SDK, no global state. These tests
/// verify the arithmetic, ordering rules, idempotency, and JSON round-trip —
/// the same properties the call sites in `FloatingControlBarWindow` rely on.
final class FloatingBarQueryTimingTests: XCTestCase {

    // MARK: - Init

    func testInitDefaultsAreSensible() {
        let timing = FloatingBarQueryTiming(
            source: .text, queryLength: 42, model: "claude-sonnet-4-6"
        )
        XCTAssertFalse(timing.queryId.isEmpty)
        XCTAssertEqual(timing.source, .text)
        XCTAssertEqual(timing.queryLength, 42)
        XCTAssertEqual(timing.model, "claude-sonnet-4-6")
        XCTAssertTrue(timing.stages.isEmpty)
        XCTAssertNil(timing.final)
    }

    func testInitGeneratesUniqueQueryIds() {
        let a = FloatingBarQueryTiming(source: .text, queryLength: 1)
        let b = FloatingBarQueryTiming(source: .text, queryLength: 1)
        XCTAssertNotEqual(a.queryId, b.queryId)
    }

    // MARK: - mark(_:)

    func testMarkRecordsStageWithElapsedTime() {
        let started = Date()
        let timing = FloatingBarQueryTiming(
            startedAt: started, source: .text, queryLength: 10
        )
        var t = timing
        t.mark(.userInput, now: started)
        t.mark(.routerDone, now: started.addingTimeInterval(0.320))  // 320ms
        t.mark(.firstDelta, now: started.addingTimeInterval(0.950))  // 950ms

        XCTAssertEqual(t.stages.count, 3)
        XCTAssertEqual(t.stages[0].stage, .userInput)
        XCTAssertEqual(t.stages[0].msSinceStart, 0.0, accuracy: 0.0001)
        XCTAssertEqual(t.stages[1].stage, .routerDone)
        XCTAssertEqual(t.stages[1].msSinceStart, 320.0, accuracy: 0.0001)
        XCTAssertEqual(t.stages[2].stage, .firstDelta)
        XCTAssertEqual(t.stages[2].msSinceStart, 950.0, accuracy: 0.0001)
    }

    func testMarkIsIdempotentPerStage() {
        let started = Date()
        var t = FloatingBarQueryTiming(
            startedAt: started, source: .text, queryLength: 1
        )
        t.mark(.firstDelta, now: started.addingTimeInterval(0.500))
        t.mark(.firstDelta, now: started.addingTimeInterval(1.000))  // ignored
        t.mark(.firstDelta, now: started.addingTimeInterval(2.000))  // ignored

        XCTAssertEqual(t.stages.count, 1)
        XCTAssertEqual(t.stages[0].msSinceStart, 500.0, accuracy: 0.0001)
    }

    func testMarkAcceptsNote() {
        let started = Date()
        var t = FloatingBarQueryTiming(
            startedAt: started, source: .text, queryLength: 1
        )
        t.mark(.screenshotDone, now: started.addingTimeInterval(0.100), note: "skipped")
        XCTAssertEqual(t.stages[0].note, "skipped")
    }

    func testMarkOutOfOrderStagesArePreserved() {
        // Stages can be marked in any order (e.g. router might finish after
        // screenshot on a slow network). The order in the array is the call
        // order, which is what dashboards want.
        let started = Date()
        var t = FloatingBarQueryTiming(
            startedAt: started, source: .text, queryLength: 1
        )
        t.mark(.firstDelta, now: started.addingTimeInterval(0.500))
        t.mark(.routerDone, now: started.addingTimeInterval(0.300))
        t.mark(.quotaDone, now: started.addingTimeInterval(0.100))

        XCTAssertEqual(t.stages.map(\.stage), [.firstDelta, .routerDone, .quotaDone])
    }

    // MARK: - endQuery(...)

    func testEndQueryPopulatesFinalAndMarksComplete() {
        let started = Date()
        var t = FloatingBarQueryTiming(
            startedAt: started, source: .text, queryLength: 5
        )
        t.endQuery(
            now: started.addingTimeInterval(1.234),
            hadScreenshot: true,
            toolCallCount: 2,
            promptTokens: 100,
            completionTokens: 50,
            costUsd: 0.012
        )

        let final = try! XCTUnwrap(t.final)
        XCTAssertEqual(final.totalMs, 1234.0, accuracy: 0.0001)
        XCTAssertTrue(final.hadScreenshot)
        XCTAssertEqual(final.toolCallCount, 2)
        XCTAssertEqual(final.promptTokens, 100)
        XCTAssertEqual(final.completionTokens, 50)
        XCTAssertEqual(final.costUsd!, 0.012, accuracy: 0.0001)
        XCTAssertFalse(final.cancelled)
        XCTAssertEqual(final.reason, .completed)

        // .complete stage is auto-appended and uses the same `now` so the
        // mark and final.totalMs always agree.
        XCTAssertEqual(t.stages.last?.stage, .complete)
        let completeMs = try! XCTUnwrap(t.stages.last?.msSinceStart)
        XCTAssertEqual(completeMs, 1234.0, accuracy: 0.0001)
    }

    func testEndQueryCancelledRecordsNote() {
        let started = Date()
        var t = FloatingBarQueryTiming(
            startedAt: started, source: .voice, queryLength: 5
        )
        t.endQuery(
            now: started.addingTimeInterval(0.500),
            hadScreenshot: false,
            toolCallCount: 0,
            cancelled: true,
            reason: .error,
            error: "bridge_timeout"
        )
        XCTAssertEqual(t.final?.reason, .error)
        XCTAssertEqual(t.final?.error, "bridge_timeout")
        XCTAssertTrue(t.final?.cancelled ?? false)
        XCTAssertEqual(t.stages.last?.note, "cancelled")
    }

    func testEndQueryDoesNotDuplicateCompleteMark() {
        let started = Date()
        var t = FloatingBarQueryTiming(
            startedAt: started, source: .text, queryLength: 1
        )
        t.mark(.complete, now: started.addingTimeInterval(0.900))
        t.endQuery(
            now: started.addingTimeInterval(1.000),
            hadScreenshot: false,
            toolCallCount: 0
        )
        // Only one .complete mark — the first one wins.
        let completeMarks = t.stages.filter { $0.stage == .complete }
        XCTAssertEqual(completeMarks.count, 1)
        XCTAssertEqual(completeMarks[0].msSinceStart, 900.0, accuracy: 0.0001)
    }

    func testEndQueryRequiresPositiveTotalMs() {
        // Defensive: if endQuery is called with `now` before `startedAt`,
        // totalMs is negative. Test that the struct doesn't crash — the
        // logger is responsible for filtering or flagging.
        let started = Date()
        var t = FloatingBarQueryTiming(
            startedAt: started, source: .text, queryLength: 1
        )
        t.endQuery(
            now: started.addingTimeInterval(-5.0),
            hadScreenshot: false,
            toolCallCount: 0
        )
        XCTAssertEqual(t.final?.totalMs ?? 0, -5000.0, accuracy: 0.0001)
    }

    // MARK: - Read helpers

    func testMsForReturnsValueForMarkedStage() {
        let started = Date()
        var t = FloatingBarQueryTiming(
            startedAt: started, source: .text, queryLength: 1
        )
        t.mark(.firstDelta, now: started.addingTimeInterval(0.450))
        let firstDeltaMs = try! XCTUnwrap(t.ms(for: .firstDelta))
        XCTAssertEqual(firstDeltaMs, 450.0, accuracy: 0.0001)
        XCTAssertNil(t.ms(for: .complete))
    }

    func testDeltaMsReturnsDifference() {
        let started = Date()
        var t = FloatingBarQueryTiming(
            startedAt: started, source: .text, queryLength: 1
        )
        t.mark(.routerDone, now: started.addingTimeInterval(0.100))
        t.mark(.screenshotDone, now: started.addingTimeInterval(0.350))
        t.mark(.firstDelta, now: started.addingTimeInterval(0.700))

        let routerToScreenshot = try! XCTUnwrap(t.deltaMs(from: .routerDone, to: .screenshotDone))
        let screenshotToFirst = try! XCTUnwrap(t.deltaMs(from: .screenshotDone, to: .firstDelta))
        let routerToFirst = try! XCTUnwrap(t.deltaMs(from: .routerDone, to: .firstDelta))
        XCTAssertEqual(routerToScreenshot, 250.0, accuracy: 0.0001)
        XCTAssertEqual(screenshotToFirst, 350.0, accuracy: 0.0001)
        XCTAssertEqual(routerToFirst, 600.0, accuracy: 0.0001)
    }

    func testDeltaMsReturnsNilWhenStageMissing() {
        let t = FloatingBarQueryTiming(source: .text, queryLength: 1)
        XCTAssertNil(t.deltaMs(from: .routerDone, to: .firstDelta))
    }

    // MARK: - JSON round-trip

    func testJSONEncodingIsStable() throws {
        let started = Date(timeIntervalSince1970: 1_700_000_000)
        var t = FloatingBarQueryTiming(
            queryId: "fixed-id",
            startedAt: started,
            source: .voice,
            queryLength: 12,
            model: "claude-sonnet-4-6"
        )
        t.mark(.userInput, now: started)
        t.mark(.routerDone, now: started.addingTimeInterval(0.300), note: "fast_path")
        t.endQuery(
            now: started.addingTimeInterval(1.000),
            hadScreenshot: true,
            toolCallCount: 1,
            promptTokens: 50,
            completionTokens: 25
        )

        let encoder = JSONEncoder()
        encoder.dateEncodingStrategy = .iso8601
        let data = try encoder.encode(t)

        // The data must be valid JSON (no top-level array) and contain the
        // expected fields. We don't pin the exact byte-for-byte output —
        // future field additions must not break the test.
        let object = try XCTUnwrap(
            try JSONSerialization.jsonObject(with: data) as? [String: Any]
        )
        XCTAssertEqual(object["queryId"] as? String, "fixed-id")
        XCTAssertEqual(object["source"] as? String, "voice")
        XCTAssertEqual(object["queryLength"] as? Int, 12)
        XCTAssertEqual(object["model"] as? String, "claude-sonnet-4-6")
        XCTAssertNotNil(object["startedAt"])

        let stages = try XCTUnwrap(object["stages"] as? [[String: Any]])
        XCTAssertEqual(stages.count, 3)
        XCTAssertEqual(stages[0]["stage"] as? String, "userInput")
        XCTAssertEqual(stages[1]["stage"] as? String, "routerDone")
        XCTAssertEqual(stages[1]["note"] as? String, "fast_path")
        XCTAssertEqual(stages[2]["stage"] as? String, "complete")
    }

    func testJSONDecodingRoundTrips() throws {
        let started = Date(timeIntervalSince1970: 1_700_000_000)
        var original = FloatingBarQueryTiming(
            queryId: "abc",
            startedAt: started,
            source: .text,
            queryLength: 7
        )
        original.mark(.userInput, now: started)
        original.endQuery(
            now: started.addingTimeInterval(0.500),
            hadScreenshot: false,
            toolCallCount: 0
        )

        // Use the default `deferredToDate` strategy (a Double number of
        // seconds) so the round-trip preserves sub-millisecond precision.
        // ISO8601 only encodes whole seconds and would lose the exact wall
        // clock time, breaking Equatable on the StageMark.wallClock field.
        let encoder = JSONEncoder()
        let data = try encoder.encode(original)
        let decoded = try JSONDecoder().decode(
            FloatingBarQueryTiming.self,
            from: data
        )
        XCTAssertEqual(decoded, original)
    }

    // MARK: - Source enum

    func testSourceRawValues() {
        XCTAssertEqual(FloatingBarQueryTiming.Source.text.rawValue, "text")
        XCTAssertEqual(FloatingBarQueryTiming.Source.voice.rawValue, "voice")
        XCTAssertEqual(FloatingBarQueryTiming.Source.notification.rawValue, "notification")
    }

    // MARK: - Stage enum

    func testAllStagesHaveRawValues() {
        for stage in FloatingBarQueryTiming.Stage.allCases {
            XCTAssertFalse(stage.rawValue.isEmpty, "Stage \(stage) has empty rawValue")
        }
    }

    func testStageRawValuesAreStable() {
        // The raw values are part of the wire format (log file + PostHog keys).
        // Renaming them would silently break dashboards — pin them in a test.
        let expected: [FloatingBarQueryTiming.Stage: String] = [
            .userInput: "userInput",
            .routerDone: "routerDone",
            .quotaDone: "quotaDone",
            .screenshotDone: "screenshotDone",
            .firstDelta: "firstDelta",
            .complete: "complete",
        ]
        for (stage, raw) in expected {
            XCTAssertEqual(stage.rawValue, raw)
        }
    }
}
