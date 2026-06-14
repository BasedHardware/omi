import XCTest

@testable import Omi_Computer

/// Tests for `FloatingBarTimingLogger` (the side-effect layer).
///
/// Pure file IO is tested against a temp file. PostHog dispatch is tested
/// against a capture-only fake so the test never touches the live SDK or
/// the network.
@MainActor
final class FloatingBarTimingLoggerTests: XCTestCase {

    private var tmpDir: URL!
    private var tmpFile: String!
    private var capture: PostHogEmitCapture!
    private var stdCapture: StandardLogCapture!

    override func setUp() async throws {
        try await super.setUp()
        tmpDir = FileManager.default.temporaryDirectory
            .appendingPathComponent("omi-floating-bar-timings-tests-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: tmpDir, withIntermediateDirectories: true)
        tmpFile = tmpDir.appendingPathComponent("timings.log").path
        capture = PostHogEmitCapture()
        stdCapture = StandardLogCapture()
    }

    override func tearDown() async throws {
        try? FileManager.default.removeItem(at: tmpDir)
        try await super.tearDown()
    }

    private func makeLogger() -> FloatingBarTimingLogger {
        // Use a serial queue so the test can deterministically wait for the
        // async file write. The default `logQueue` (concurrent utility) would
        // require a sleep.
        let queue = DispatchQueue(label: "test.timings", qos: .userInitiated)
        return FloatingBarTimingLogger(
            timingsLogFile: tmpFile,
            logQueue: queue,
            postHog: capture,
            standardLog: stdCapture
        )
    }

    private func makeEndedTiming(
        id: String = "test-id",
        source: FloatingBarQueryTiming.Source = .text,
        length: Int = 10
    ) -> FloatingBarQueryTiming {
        let started = Date(timeIntervalSince1970: 1_700_000_000)
        var t = FloatingBarQueryTiming(
            queryId: id,
            startedAt: started,
            source: source,
            queryLength: length,
            model: "claude-sonnet-4-6"
        )
        t.mark(.userInput, now: started)
        t.mark(.routerDone, now: started.addingTimeInterval(0.300))
        t.mark(.quotaDone, now: started.addingTimeInterval(0.310))
        t.mark(.screenshotDone, now: started.addingTimeInterval(0.450), note: "skipped")
        t.mark(.firstDelta, now: started.addingTimeInterval(0.900))
        t.endQuery(
            now: started.addingTimeInterval(1.500),
            hadScreenshot: false,
            toolCallCount: 0
        )
        return t
    }

    // MARK: - record(...)

    func testRecordWritesValidJSONLineToFile() throws {
        let logger = makeLogger()
        let timing = makeEndedTiming(id: "abc-123")
        logger.record(timing)

        // The file write is dispatched on the log queue. Poll until the
        // file exists and has content (waitForFileContent has a 1s deadline
        // and gives up with XCTFail). Previous versions tried to drain via
        // a sync barrier on a fresh queue but that's a no-op — the fresh
        // queue has no relationship to the logger's queue.
        let data = try waitForFileContent()
        let line = try XCTUnwrap(
            String(data: data, encoding: .utf8)
        ).trimmingCharacters(in: .whitespacesAndNewlines)
        XCTAssertFalse(line.isEmpty, "Expected non-empty line, got empty")

        // Each line is one JSON object terminated by \n. We use a single line
        // for one record call.
        let object = try XCTUnwrap(
            try JSONSerialization.jsonObject(with: Data(line.utf8)) as? [String: Any]
        )
        XCTAssertEqual(object["queryId"] as? String, "abc-123")
        XCTAssertEqual(object["source"] as? String, "text")
        XCTAssertEqual(object["queryLength"] as? Int, 10)
        XCTAssertEqual(object["model"] as? String, "claude-sonnet-4-6")
        let final = try XCTUnwrap(object["final"] as? [String: Any])
        let finalTotalMs = try XCTUnwrap(final["totalMs"] as? Double)
        XCTAssertEqual(finalTotalMs, 1500.0, accuracy: 0.001)
        XCTAssertEqual(final["hadScreenshot"] as? Bool, false)
        XCTAssertEqual(final["toolCallCount"] as? Int, 0)
        XCTAssertEqual(final["cancelled"] as? Bool, false)
        XCTAssertEqual(final["reason"] as? String, "completed")
    }

    func testRecordAppendsAcrossMultipleCalls() throws {
        let logger = makeLogger()
        logger.record(makeEndedTiming(id: "first"))
        logger.record(makeEndedTiming(id: "second"))
        logger.record(makeEndedTiming(id: "third"))

        let data = try waitForFileContent()
        let content = try XCTUnwrap(String(data: data, encoding: .utf8))
        // Three lines, one per record() call, in order.
        let lines = content.split(separator: "\n").filter { !$0.isEmpty }
        XCTAssertEqual(lines.count, 3)
        for line in lines {
            let obj = try XCTUnwrap(
                try JSONSerialization.jsonObject(with: Data(line.utf8)) as? [String: Any]
            )
            XCTAssertNotNil(obj["queryId"])
        }
    }

    func testRecordSkipsUnendedTimings() async throws {
        let logger = makeLogger()
        // A timing with no `final` should NOT be written.
        var t = FloatingBarQueryTiming(source: .text, queryLength: 1)
        t.mark(.userInput)
        logger.record(t)

        // Nothing should have been written. Wait briefly to give the async
        // queue a chance to (not) write.
        try? await Task.sleep(nanoseconds: 100_000_000)
        XCTAssertFalse(FileManager.default.fileExists(atPath: tmpFile))
        // A warning should have been logged via the standard logger.
        XCTAssertTrue(stdCapture.messages.contains { $0.contains("skipping record") })
    }

    func testRecordEmitsPostHogEventWithFlattenedStageTimings() {
        let logger = makeLogger()
        let timing = makeEndedTiming(id: "ph-test", source: .voice, length: 42)
        logger.record(timing)

        XCTAssertEqual(capture.events.count, 1)
        let (name, props) = capture.events[0]
        XCTAssertEqual(name, "floating_bar_query_timing")
        XCTAssertEqual(props["query_id"] as? String, "ph-test")
        XCTAssertEqual(props["source"] as? String, "voice")
        XCTAssertEqual(props["query_length"] as? Int, 42)
        XCTAssertEqual(props["model"] as? String, "claude-sonnet-4-6")

        // Stage timings are flattened to stage_<name>_ms. addingTimeInterval
        // accumulates sub-microsecond float error, so use 0.001ms accuracy.
        let userInput = try! XCTUnwrap(props["stage_userInput_ms"] as? Double)
        XCTAssertEqual(userInput, 0.0, accuracy: 0.001)
        let routerDone = try! XCTUnwrap(props["stage_routerDone_ms"] as? Double)
        XCTAssertEqual(routerDone, 300.0, accuracy: 0.001)
        let quotaDone = try! XCTUnwrap(props["stage_quotaDone_ms"] as? Double)
        XCTAssertEqual(quotaDone, 310.0, accuracy: 0.001)
        let screenshotDone = try! XCTUnwrap(props["stage_screenshotDone_ms"] as? Double)
        XCTAssertEqual(screenshotDone, 450.0, accuracy: 0.001)
        let firstDelta = try! XCTUnwrap(props["stage_firstDelta_ms"] as? Double)
        XCTAssertEqual(firstDelta, 900.0, accuracy: 0.001)
        let complete = try! XCTUnwrap(props["stage_complete_ms"] as? Double)
        XCTAssertEqual(complete, 1500.0, accuracy: 0.001)

        // Stage notes propagate as stage_<name>_note.
        XCTAssertEqual(props["stage_screenshotDone_note"] as? String, "skipped")

        // Final fields.
        let total = try! XCTUnwrap(props["total_ms"] as? Double)
        XCTAssertEqual(total, 1500.0, accuracy: 0.001)
        XCTAssertEqual(props["had_screenshot"] as? Bool, false)
        XCTAssertEqual(props["tool_call_count"] as? Int, 0)
        XCTAssertEqual(props["cancelled"] as? Bool, false)
        XCTAssertEqual(props["end_reason"] as? String, "completed")
    }

    func testRecordIsIdempotent() throws {
        // Calling record twice on the same struct should not double-write.
        // (The logger doesn't have built-in idempotency, but the call site
        // is expected to nil the timing after record() — the doc on
        // `activeTiming` in FloatingControlBarWindow documents this contract.
        // The PostHog side effect IS duplicated — this test documents the
        // current behavior so a future change is intentional.)
        let logger = makeLogger()
        let timing = makeEndedTiming(id: "dupe")
        logger.record(timing)
        logger.record(timing)

        XCTAssertEqual(capture.events.count, 2)  // documented behavior
    }

    // MARK: - StandardLog (recursion regression guard)

    func testStandardLogLiveDoesNotRecurseInfinitely() {
        // Regression guard for the Greptile-flagged bug on PR #7886:
        // `StandardLogLive.log(_:)` was named the same as the global
        // `log(_:)` function and recursed into itself with no base case.
        // The fix renamed the protocol witness to `write(_:)`. Verify the
        // live impl now dispatches to the global log without recursing.
        //
        // Calling `write(_:)` on StandardLogLive used to crash with stack
        // overflow. With the fix, it calls the global log() function which
        // writes to the standard log file (no crash). We don't assert on
        // the log content here (the global log goes to /tmp/omi.log and
        // is not captured in tests); we just verify the call returns.
        let live = StandardLogLive()
        live.write("FloatingBarTimingLogger: regression test for recursion")
        // If we got here without crashing, the recursion is fixed.
    }

    // MARK: - appendLine (static, testable)

    func testAppendLineCreatesFileIfMissing() {
        let path = tmpFile!
        XCTAssertFalse(FileManager.default.fileExists(atPath: path))
        FloatingBarTimingLogger.appendLine("hello", to: path)
        XCTAssertTrue(FileManager.default.fileExists(atPath: path))
        let content = try! String(contentsOfFile: path, encoding: .utf8)
        XCTAssertEqual(content, "hello\n")
    }

    func testAppendLineAppendsToExistingFile() {
        let path = tmpFile!
        FloatingBarTimingLogger.appendLine("first", to: path)
        FloatingBarTimingLogger.appendLine("second", to: path)
        FloatingBarTimingLogger.appendLine("third", to: path)
        let content = try! String(contentsOfFile: path, encoding: .utf8)
        XCTAssertEqual(content, "first\nsecond\nthird\n")
    }

    // MARK: - postHogProperties (pure, testable)

    func testPostHogPropertiesOmitsOptionalsWhenNil() {
        let started = Date(timeIntervalSince1970: 1_700_000_000)
        var t = FloatingBarQueryTiming(
            queryId: "x",
            startedAt: started,
            source: .text,
            queryLength: 1,
            model: nil  // no model
        )
        t.mark(.userInput, now: started)
        t.endQuery(
            now: started.addingTimeInterval(0.100),
            hadScreenshot: false,
            toolCallCount: 0,
            promptTokens: nil,
            completionTokens: nil,
            costUsd: nil
        )
        let props = FloatingBarTimingLogger.postHogProperties(for: t)
        XCTAssertNil(props["model"])
        XCTAssertNil(props["prompt_tokens"])
        XCTAssertNil(props["completion_tokens"])
        XCTAssertNil(props["cost_usd"])
        XCTAssertNil(props["error"])
    }

    func testPostHogPropertiesIncludesError() {
        let started = Date(timeIntervalSince1970: 1_700_000_000)
        var t = FloatingBarQueryTiming(
            startedAt: started, source: .text, queryLength: 1
        )
        t.mark(.userInput, now: started)
        t.endQuery(
            now: started.addingTimeInterval(0.050),
            hadScreenshot: false,
            toolCallCount: 0,
            cancelled: true,
            reason: .error,
            error: "bridge_dead"
        )
        let props = FloatingBarTimingLogger.postHogProperties(for: t)
        XCTAssertEqual(props["error"] as? String, "bridge_dead")
        XCTAssertEqual(props["cancelled"] as? Bool, true)
        XCTAssertEqual(props["end_reason"] as? String, "error")
    }

    // MARK: - Wait helpers

    /// Poll the file for content, up to 1s, to give the async log queue a
    /// chance to flush. The logger uses an async dispatch so we can't
    /// deterministically wait on it without coupling test to implementation.
    private func waitForFileContent(file: StaticString = #file, line: UInt = #line) throws -> Data {
        let deadline = Date().addingTimeInterval(1.0)
        while Date() < deadline {
            if FileManager.default.fileExists(atPath: tmpFile),
               let data = try? Data(contentsOf: URL(fileURLWithPath: tmpFile)),
               !data.isEmpty {
                return data
            }
            Thread.sleep(forTimeInterval: 0.01)
        }
        XCTFail("File never received content", file: file, line: line)
        return Data()
    }
}
