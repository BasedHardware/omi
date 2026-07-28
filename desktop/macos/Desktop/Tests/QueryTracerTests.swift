import XCTest

@testable import Omi_Computer

final class QueryTracerTests: XCTestCase {

  // MARK: - 1. Basic span recording

  func testBasicSpanRecording() {
    let tracer = QueryTracer(query: "hello", inputMode: .text)
    tracer.begin("parse")
    // Burn a tiny bit of time so dur > 0
    for _ in 0..<1_000_000 { _ = Int.random(in: 0...1) }
    tracer.end("parse")

    let trace = tracer.buildTrace(tokenCount: 0, model: nil)
    XCTAssertEqual(trace.spans.count, 1)
    XCTAssertEqual(trace.spans[0].name, "parse")
    XCTAssertGreaterThanOrEqual(trace.spans[0].dur_ms, 0)
    XCTAssertNotNil(trace.spans[0].end_ms)
  }

  // MARK: - 2. Nested spans

  func testNestedSpans() {
    let tracer = QueryTracer(query: "nested", inputMode: .text)
    tracer.begin("parent")
    tracer.begin("child")
    tracer.end("child")
    tracer.end("parent")

    let trace = tracer.buildTrace(tokenCount: 0, model: nil)
    XCTAssertEqual(trace.spans.count, 1, "Only one top-level span expected")
    let parent = trace.spans[0]
    XCTAssertEqual(parent.name, "parent")
    XCTAssertNotNil(parent.children)
    XCTAssertEqual(parent.children?.count, 1)
    XCTAssertEqual(parent.children?[0].name, "child")
  }

  // MARK: - 3. Gap detection

  func testGapDetection() {
    let tracer = QueryTracer(query: "gap", inputMode: .text)

    tracer.begin("A")
    tracer.end("A")

    // Sleep to create a gap > 50ms
    Thread.sleep(forTimeInterval: 0.07)

    tracer.begin("B")
    tracer.end("B")

    let trace = tracer.buildTrace(tokenCount: 0, model: nil)
    XCTAssertEqual(trace.spans.count, 2)
    XCTAssertFalse(trace.flagged_gaps.isEmpty, "A gap > 50ms should be flagged")
    XCTAssertEqual(trace.flagged_gaps[0].from, "A")
    XCTAssertEqual(trace.flagged_gaps[0].to, "B")
    XCTAssertGreaterThanOrEqual(trace.flagged_gaps[0].gap_ms, 50)
  }

  // MARK: - 4. TTFT marking

  func testTTFTMarking() throws {
    let tracer = QueryTracer(query: "ttft", inputMode: .text)
    Thread.sleep(forTimeInterval: 0.01)
    tracer.markTTFT()
    let firstTrace = tracer.buildTrace(tokenCount: 10, model: "gpt-4")
    let firstTTFT = try XCTUnwrap(firstTrace.ttft_ms)

    // Second call should be ignored.
    Thread.sleep(forTimeInterval: 0.05)
    tracer.markTTFT()

    let trace = tracer.buildTrace(tokenCount: 10, model: "gpt-4")
    XCTAssertEqual(trace.ttft_ms, firstTTFT)
    XCTAssertGreaterThan(trace.total_ms, firstTTFT)
  }

  // MARK: - 5. Metadata passthrough

  func testMetadataPassthrough() {
    let tracer = QueryTracer(query: "meta", inputMode: .text)
    tracer.begin("step", metadata: ["key": "val"])
    tracer.end("step", metadata: ["extra": "data"])

    let trace = tracer.buildTrace(tokenCount: 0, model: nil)
    let span = trace.spans[0]
    XCTAssertEqual(span.meta?["key"], "val")
    XCTAssertEqual(span.meta?["extra"], "data")
  }

  // MARK: - 6. Closure-based span API (async)

  func testClosureBasedSpanAsync() async throws {
    let tracer = QueryTracer(query: "closure", inputMode: .text)
    let result = await tracer.span("compute") {
      try? await Task.sleep(nanoseconds: 5_000_000)  // 5ms
      return 42
    }
    XCTAssertEqual(result, 42)

    let trace = tracer.buildTrace(tokenCount: 0, model: nil)
    XCTAssertEqual(trace.spans.count, 1)
    XCTAssertEqual(trace.spans[0].name, "compute")
    XCTAssertNotNil(trace.spans[0].end_ms)
  }

  // MARK: - 7. Nil tracer safety

  func testNilTracerSafety() {
    let tracer: QueryTracer? = nil
    // These should simply not crash
    tracer?.begin("x")
    tracer?.end("x")
    tracer?.markTTFT()
    // If we got here, the test passes
  }

  // MARK: - 8. JSONL serialization

  func testJSONLSerialization() throws {
    let tracer = QueryTracer(query: "json test", inputMode: .voicePTTBatch, capturesContent: true)
    tracer.begin("step1")
    tracer.end("step1")

    let trace = tracer.buildTrace(tokenCount: 5, model: "gpt-4")
    let encoder = JSONEncoder()
    let data = try encoder.encode(trace)
    let json = try JSONSerialization.jsonObject(with: data) as? [String: Any]

    XCTAssertNotNil(json)
    XCTAssertTrue(trace.trace_id.hasPrefix("t_"))
    XCTAssertEqual(json?["query_text"] as? String, "json test")
    XCTAssertEqual(json?["query_length"] as? Int, 9)
    XCTAssertEqual(json?["content_captured"] as? Bool, true)
    XCTAssertEqual(json?["input_mode"] as? String, "voice_ptt_batch")
    XCTAssertEqual(json?["token_count"] as? Int, 5)
    XCTAssertEqual(json?["model"] as? String, "gpt-4")
    XCTAssertNotNil(json?["trace_id"])
    XCTAssertNotNil(json?["timestamp"])
    XCTAssertNotNil(json?["spans"])
  }

  // MARK: - 9. Tool execution capture

  func testToolExecutionCapture() {
    let tracer = QueryTracer(query: "tools", inputMode: .text, capturesContent: true)
    tracer.captureToolExecution(
      toolUseId: "call-1",
      name: "spawn_agent",
      input: #"{"objective":"GAUNTLET-TEST-SPAWN"}"#,
      output: #"{"ok":true}"#,
      durationMs: 42
    )

    let trace = tracer.buildTrace(tokenCount: 0, model: nil)
    XCTAssertEqual(trace.tool_executions?.count, 1)
    XCTAssertEqual(trace.tool_executions?[0].name, "spawn_agent")
    XCTAssertEqual(trace.tool_executions?[0].tool_use_id, "call-1")
    XCTAssertTrue(trace.tool_executions?[0].input.contains("GAUNTLET-TEST-SPAWN") ?? false)
    XCTAssertEqual(trace.tool_executions?[0].dur_ms, 42)
  }

  func testProductionTraceKeepsShapeWithoutUserContent() {
    let tracer = QueryTracer(
      query: "private spoken request",
      inputMode: .voicePTTBatch,
      capturesContent: false
    )
    tracer.captureRequest(
      systemPrompt: "private system prompt",
      messages: [["role": "user", "content": "private history"]],
      hasScreenshot: true
    )
    tracer.captureResponse(text: "private response")
    tracer.captureToolExecution(
      toolUseId: "call-1",
      name: "WebSearch: private health query",
      input: "private tool input",
      output: "private tool output",
      durationMs: 8
    )

    let trace = tracer.buildTrace(tokenCount: 3, model: "test-model")
    XCTAssertEqual(trace.query_text, "")
    XCTAssertEqual(trace.query_length, 22)
    XCTAssertFalse(trace.content_captured)
    XCTAssertNil(trace.request?.system_prompt)
    XCTAssertNil(trace.request?.messages)
    XCTAssertNil(trace.request?.response_text)
    XCTAssertEqual(trace.request?.has_screenshot, true)
    XCTAssertEqual(trace.tool_executions?.first?.name, "websearch")
    XCTAssertEqual(trace.tool_executions?.first?.input, "")
    XCTAssertEqual(trace.tool_executions?.first?.output, "")
    XCTAssertEqual(tracer.toolNameForTrace("Read: /Users/person/private.txt"), "read")
  }

  func testTraceFilesArePrivate() throws {
    let directory = FileManager.default.temporaryDirectory
      .appendingPathComponent("query-tracer-permissions-\(UUID().uuidString)")
    defer { try? FileManager.default.removeItem(at: directory) }

    QueryTracer.prepareLogDirectory(directory)
    let file = directory.appendingPathComponent("traces.jsonl")
    QueryTracer.appendTraceLine("{}", to: file)

    let directoryAttributes = try FileManager.default.attributesOfItem(atPath: directory.path)
    let fileAttributes = try FileManager.default.attributesOfItem(atPath: file.path)
    let directoryMode = try XCTUnwrap(directoryAttributes[.posixPermissions] as? NSNumber).intValue
    let fileMode = try XCTUnwrap(fileAttributes[.posixPermissions] as? NSNumber).intValue
    XCTAssertEqual(directoryMode & 0o777, 0o700)
    XCTAssertEqual(fileMode & 0o777, 0o600)
  }

  // MARK: - 10. Summary line format

  func testSummaryLineFormat() {
    let tracer = QueryTracer(query: "summary", inputMode: .voicePTTLive)
    tracer.begin("parse")
    tracer.end("parse")
    tracer.markTTFT()

    let trace = tracer.buildTrace(tokenCount: 10, model: "gpt-4")
    let line = trace.summaryLine

    XCTAssertTrue(line.hasPrefix("[trace]"), "Summary should start with [trace]")
    XCTAssertTrue(line.contains("id="), "Summary should contain id=")
    XCTAssertTrue(line.contains("mode="), "Summary should contain mode=")
    XCTAssertTrue(line.contains("ttft="), "Summary should contain ttft=")
    XCTAssertTrue(line.contains("parse="), "Summary should contain stage names")
  }

  func testFinalizeIsExactlyOnce() {
    let tracer = QueryTracer(query: "one terminal trace", inputMode: .text)

    XCTAssertTrue(tracer.finalize(tokenCount: 0, model: "test-model"))
    XCTAssertFalse(tracer.finalize(tokenCount: 99, model: "late-model"))
  }
}
