import Foundation
import GRDB
import XCTest

@testable import Omi_Computer

#if DEBUG
  final class LocalSummaryBenchmarkTests: XCTestCase {
    override func setUp() {
      super.setUp()
      DesktopDiagnosticsManager.shared.resetForTests()
    }

    override func tearDown() {
      DesktopDiagnosticsManager.shared.resetForTests()
      super.tearDown()
    }

    func testValidDraftReportsSchemaValidAndTiming() async throws {
      let engine = DraftEngine(
        contextWindowTokens: 8192,
        generateResults: [
          .success(LocalSummaryDraft(title: "Standup", overview: "Shipped the gate."))
        ]
      )
      let store = MemoryLocalProjectionStore()
      let summarizer = makeSummarizer(engine: engine, store: store)
      let segments = [TranscriptHash.Segment(text: "We shipped the env-diff gate.")]
      let report = await LocalSummaryBenchmark.run(
        sessions: [
          LocalSummaryBenchmark.Session(sessionId: 3, startedAt: startedAt, segments: segments)
        ],
        summarizer: summarizer,
        engineID: "local-server",
        now: { Date(timeIntervalSince1970: 1_704_140_040) }
      )

      XCTAssertEqual(report.kind, LocalSummaryBenchmark.reportKind)
      XCTAssertEqual(report.version, LocalSummaryBenchmark.reportVersion)
      XCTAssertEqual(report.engineID, "local-server")
      XCTAssertEqual(report.cases.count, 1)
      let row = try XCTUnwrap(report.cases.first)
      XCTAssertTrue(row.schemaValid)
      XCTAssertEqual(row.schemaErrors, [])
      XCTAssertFalse(row.fallback)
      XCTAssertEqual(row.runtime, "local")
      XCTAssertTrue(row.titlePresent)
      XCTAssertGreaterThanOrEqual(row.elapsedMs, 0)
      XCTAssertEqual(row.transcriptSha256, TranscriptHash.sha256(segments: segments))
      XCTAssertEqual(engine.generateCallCount, 1)
    }

    func testForcedEngineFailureIsFallbackAndStillSchemaValid() async throws {
      let engine = DraftEngine(
        contextWindowTokens: 8192,
        generateResults: [
          .failure(LocalInferenceError.engineFailed("offline")),
          .failure(LocalInferenceError.engineFailed("offline")),
        ]
      )
      let report = await LocalSummaryBenchmark.run(
        sessions: [
          LocalSummaryBenchmark.Session(
            sessionId: 4,
            startedAt: startedAt,
            segments: [TranscriptHash.Segment(text: "Still lands a minimum.")]
          )
        ],
        summarizer: ConversationChunkSummarizer(
          runtime: LocalInferenceRuntime(
            engines: [engine],
            killSwitches: .enabled,
            fallback: DesktopLocalInferenceFallbackRecorder(),
            defaultEngineID: .localServer
          ),
          store: MemoryLocalProjectionStore(),
          now: { Date(timeIntervalSince1970: 1_704_140_040) },
          deviceClass: "macos",
          sourceLabel: "Recording",
          timeZone: TimeZone.gmt
        ),
        engineID: "local-server"
      )

      let row = try XCTUnwrap(report.cases.first)
      XCTAssertTrue(row.fallback)
      XCTAssertEqual(row.runtime, ClientProcessingContract.deterministicRuntime)
      XCTAssertTrue(row.schemaValid, "the deterministic minimum is a valid wire projection")
      XCTAssertTrue(row.titlePresent)
    }

    func testEvaluateRejectsWrongSchemaVersionAndHash() {
      let digest = TranscriptHash.sha256(segments: [TranscriptHash.Segment(text: "hi")])
      let projection = OmiAPI.ClientProcessing(
        actionItems: [],
        provenance: OmiAPI.ProjectionProvenance(
          deviceClass: "macos",
          generatedAt: "2024-01-01T20:14:00Z",
          modelId: "local-server",
          runtime: "local"
        ),
        schemaVersion: 2,
        structure: OmiAPI.ProjectedStructure(title: "   "),
        transcriptSha256: "deadbeef"
      )
      let judged = LocalSummaryBenchmark.evaluate(projection, expectedDigest: digest)
      XCTAssertFalse(judged.schemaValid)
      XCTAssertEqual(Set(judged.errors), ["schema_version", "transcript_sha256", "title"])
    }

    func testWritePinsTheReportContractToDisk() throws {
      let report = LocalSummaryBenchmark.Report(
        kind: LocalSummaryBenchmark.reportKind,
        version: LocalSummaryBenchmark.reportVersion,
        generatedAt: "2024-01-01T20:14:00Z",
        engineID: "local-server",
        cases: [
          LocalSummaryBenchmark.Case(
            sessionId: 9,
            transcriptSha256: "abc",
            elapsedMs: 12,
            schemaValid: true,
            schemaErrors: [],
            fallback: false,
            runtime: "local",
            titlePresent: true
          )
        ]
      )
      let url = FileManager.default.temporaryDirectory
        .appendingPathComponent("local-summary-benchmark-test-\(UUID().uuidString).json")
      defer { try? FileManager.default.removeItem(at: url) }
      try LocalSummaryBenchmark.write(report, to: url)
      let decoded = try JSONDecoder().decode(LocalSummaryBenchmark.Report.self, from: Data(contentsOf: url))
      XCTAssertEqual(decoded, report)
      let raw = try XCTUnwrap(JSONSerialization.jsonObject(with: Data(contentsOf: url)) as? [String: Any])
      XCTAssertEqual(raw["kind"] as? String, "local_summary_benchmark")
      XCTAssertEqual(raw["version"] as? Int, 1)
      XCTAssertNotNil(raw["cases"], "deleting the report writer must fail this pin")
    }

    func testLoadRecentSessionsReturnsLastKWithSegments() throws {
      let queue = try listingQueue()
      try queue.write { db in
        try db.execute(
          sql: """
            INSERT INTO transcription_sessions (id, startedAt, deleted) VALUES
              (1, ?, 0),
              (2, ?, 0),
              (3, ?, 1)
            """,
          arguments: [
            Date(timeIntervalSince1970: 100),
            Date(timeIntervalSince1970: 200),
            Date(timeIntervalSince1970: 300),
          ]
        )
        try db.execute(
          sql: """
            INSERT INTO transcription_segments
              (sessionId, speaker, text, startTime, endTime, segmentOrder, createdAt, isUser)
            VALUES
              (1, 0, 'older', 0, 1, 0, ?, 0),
              (2, 0, 'newer', 0, 1, 0, ?, 0),
              (3, 0, 'deleted', 0, 1, 0, ?, 0)
            """,
          arguments: [Date(), Date(), Date()]
        )
      }
      let loaded = try queue.read { db in
        try LocalSummaryBenchmark.loadRecentSessions(from: db, limit: 10)
      }
      XCTAssertEqual(loaded.map(\.sessionId), [2, 1])
      XCTAssertEqual(loaded.first?.segments.map(\.text), ["newer"])
    }

    private var startedAt: Date {
      Date(timeIntervalSince1970: 1_704_140_040)
    }

    private func makeSummarizer(
      engine: DraftEngine,
      store: MemoryLocalProjectionStore
    ) -> ConversationChunkSummarizer {
      ConversationChunkSummarizer(
        runtime: LocalInferenceRuntime(
          engines: [engine],
          killSwitches: .enabled,
          fallback: DesktopLocalInferenceFallbackRecorder(),
          defaultEngineID: .localServer
        ),
        store: store,
        now: { Date(timeIntervalSince1970: 1_704_140_040) },
        deviceClass: "macos",
        sourceLabel: "Recording",
        timeZone: TimeZone.gmt
      )
    }

    private func listingQueue() throws -> DatabaseQueue {
      let queue = try DatabaseQueue()
      try queue.write { db in
        try db.execute(
          sql: """
            CREATE TABLE transcription_sessions (
              id INTEGER PRIMARY KEY,
              startedAt DATETIME,
              deleted INTEGER DEFAULT 0
            )
            """)
        try db.execute(
          sql: """
            CREATE TABLE transcription_segments (
              id INTEGER PRIMARY KEY,
              sessionId INTEGER NOT NULL,
              speaker INTEGER NOT NULL,
              text TEXT NOT NULL,
              startTime DOUBLE NOT NULL,
              endTime DOUBLE NOT NULL,
              segmentOrder INTEGER NOT NULL,
              createdAt DATETIME,
              speakerLabel TEXT,
              isUser INTEGER NOT NULL DEFAULT 0,
              personId TEXT
            )
            """)
      }
      return queue
    }
  }

  private final class DraftEngine: LocalInferenceService, @unchecked Sendable {
    let engineID: LocalInferenceEngineID
    let capabilities: LocalInferenceCapabilities
    private let lock = NSLock()
    private var generateResults: [Result<LocalSummaryDraft, Error>]
    private(set) var generateCallCount = 0

    init(
      engineID: LocalInferenceEngineID = .localServer,
      contextWindowTokens: Int,
      generateResults: [Result<LocalSummaryDraft, Error>]
    ) {
      self.engineID = engineID
      self.capabilities = LocalInferenceCapabilities(
        structuredOutput: true,
        toolLoop: false,
        contextWindowTokens: contextWindowTokens
      )
      self.generateResults = generateResults
    }

    func generateStructured<T: Decodable>(prompt _: String, schema _: LocalInferenceJSONSchema) async throws -> T {
      let result: Result<LocalSummaryDraft, Error> = lock.withLock {
        generateCallCount += 1
        if generateResults.isEmpty {
          return .success(LocalSummaryDraft(title: "chunk-\(generateCallCount)", overview: "ok"))
        }
        return generateResults.removeFirst()
      }
      let draft = try result.get()
      return try JSONDecoder().decode(T.self, from: JSONEncoder().encode(draft))
    }

    func runToolLoop(prompt _: String, tools _: [LocalInferenceToolSpec], budget _: ToolLoopBudget) async throws
      -> ToolLoopResult
    {
      throw LocalInferenceError.capabilityUnavailable("tool_loop")
    }
  }
#endif
