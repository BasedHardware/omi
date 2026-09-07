import Foundation
import GRDB
import XCTest

@testable import Omi_Computer

private final class DraftEngine: LocalInferenceService, @unchecked Sendable {
  let engineID: LocalInferenceEngineID
  let capabilities: LocalInferenceCapabilities
  private let lock = NSLock()
  private var generateResults: [Result<LocalSummaryDraft, Error>]
  private var rejectOverWindow: Bool
  private(set) var generateCallCount = 0
  private(set) var prompts: [String] = []
  private(set) var maxPromptTokens = 0

  init(
    engineID: LocalInferenceEngineID = .localServer,
    contextWindowTokens: Int,
    generateResults: [Result<LocalSummaryDraft, Error>],
    rejectOverWindow: Bool = true
  ) {
    self.engineID = engineID
    self.capabilities = LocalInferenceCapabilities(
      structuredOutput: true,
      toolLoop: false,
      contextWindowTokens: contextWindowTokens
    )
    self.generateResults = generateResults
    self.rejectOverWindow = rejectOverWindow
  }

  func generateStructured<T: Decodable>(prompt: String, schema _: LocalInferenceJSONSchema) async throws -> T {
    let tokens = ConversationChunkSummarizer.estimatedTokens(prompt)
    let result: Result<LocalSummaryDraft, Error> = lock.withLock {
      generateCallCount += 1
      prompts.append(prompt)
      maxPromptTokens = max(maxPromptTokens, tokens)
      if rejectOverWindow, tokens > capabilities.contextWindowTokens {
        return .failure(LocalInferenceError.engineFailed("exceededContextWindowSize"))
      }
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

#if DEBUG
  final class ConversationChunkSummarizerTests: XCTestCase {
    override func setUp() {
      super.setUp()
      DesktopDiagnosticsManager.shared.resetForTests()
    }

    override func tearDown() {
      DesktopDiagnosticsManager.shared.resetForTests()
      super.tearDown()
    }

    func testSingleChunkSkipsTheMapPass() async throws {
      let engine = DraftEngine(
        contextWindowTokens: 8192,
        generateResults: [
          .success(LocalSummaryDraft(title: "Short call", overview: "One chunk."))
        ]
      )
      let store = MemoryLocalProjectionStore()
      let summarizer = makeSummarizer(engine: engine, store: store)

      let stored = try await summarizer.summarize(
        sessionId: 1,
        segments: [TranscriptHash.Segment(text: "Hello from a short meeting.")],
        startedAt: startedAt
      )
      let payload = try ClientProcessingContract.decode(stored.json)

      XCTAssertEqual(engine.generateCallCount, 1)
      XCTAssertEqual(payload.structure.title, "Short call")
      XCTAssertEqual(payload.schemaVersion, 1)
      XCTAssertEqual(payload.provenance.runtime, "local")
      XCTAssertEqual(
        payload.transcriptSha256,
        TranscriptHash.sha256(segments: [
          TranscriptHash.Segment(text: "Hello from a short meeting.")
        ]))
    }

    func testThirtyMinuteConversationNeverExceedsTheEngineWindow() async throws {
      let engine = DraftEngine(contextWindowTokens: 4096, generateResults: [])
      let store = MemoryLocalProjectionStore()
      let summarizer = makeSummarizer(engine: engine, store: store)
      let segments = thirtyMinuteSegments()

      let stored = try await summarizer.summarize(sessionId: 7, segments: segments, startedAt: startedAt)
      let payload = try ClientProcessingContract.decode(stored.json)
      let maxPrompt = engine.maxPromptTokens

      XCTAssertGreaterThan(engine.generateCallCount, 1, "a 30-minute transcript on a 4096-token window must chunk")
      XCTAssertLessThanOrEqual(maxPrompt, 4096)
      XCTAssertEqual(payload.schemaVersion, 1)
      XCTAssertFalse(engine.prompts.contains(where: { $0.contains("exceededContextWindowSize") }))
    }

    func testRetryReturnsTheStoredProjectionAndDoesNotRegenerate() async throws {
      let engine = DraftEngine(
        contextWindowTokens: 8192,
        generateResults: [
          .success(LocalSummaryDraft(title: "First pass", overview: "Keep this.")),
          .success(LocalSummaryDraft(title: "Must not run", overview: "regenerated")),
        ]
      )
      let store = MemoryLocalProjectionStore()
      let summarizer = makeSummarizer(engine: engine, store: store)
      let segments = [TranscriptHash.Segment(text: "We decided to ship S10 today.")]

      let first = try await summarizer.summarize(sessionId: 3, segments: segments, startedAt: startedAt)
      let second = try await summarizer.summarize(sessionId: 3, segments: segments, startedAt: startedAt)

      XCTAssertEqual(first.json, second.json)
      XCTAssertEqual(engine.generateCallCount, 1, "retry must send the stored blob, never regenerate")
      let payload = try ClientProcessingContract.decode(second.json)
      XCTAssertEqual(payload.structure.title, "First pass")
    }

    func testForcedEngineFailurePersistsDeterministicMinimumAndDoesNotCallAnotherEngine() async throws {
      let local = DraftEngine(
        contextWindowTokens: 2048,
        generateResults: [
          .failure(LocalInferenceError.engineFailed("forced failure")),
          .failure(LocalInferenceError.engineFailed("forced failure")),
        ]
      )
      let cloud = DraftEngine(
        engineID: .afm,
        contextWindowTokens: 4096,
        generateResults: [.success(LocalSummaryDraft(title: "cloud should never run"))]
      )
      let store = MemoryLocalProjectionStore()
      let runtime = LocalInferenceRuntime(
        engines: [local, cloud],
        killSwitches: .enabled,
        fallback: DesktopLocalInferenceFallbackRecorder(),
        defaultEngineID: .localServer
      )
      let summarizer = ConversationChunkSummarizer(
        runtime: runtime,
        store: store,
        now: { Date(timeIntervalSince1970: 1_704_140_040) },
        deviceClass: "macos",
        sourceLabel: "Recording",
        timeZone: TimeZone.gmt
      )
      let segments = [TranscriptHash.Segment(text: "We decided to ship the local runtime today. Extra sentence.")]

      let stored = try await summarizer.summarize(sessionId: 9, segments: segments, startedAt: startedAt)
      let payload = try ClientProcessingContract.decode(stored.json)
      let snapshot = try latestFallbackSnapshot()

      XCTAssertEqual(payload.structure.title, "We decided to ship the local runtime today.")
      XCTAssertEqual(payload.structure.overview, "")
      XCTAssertEqual(payload.provenance.runtime, "deterministic")
      XCTAssertEqual(local.generateCallCount, 2)
      XCTAssertEqual(cloud.generateCallCount, 0, "failure must not cascade to another engine")
      XCTAssertEqual(snapshot["area"] as? String, "local_llm")
      XCTAssertEqual(snapshot["to"] as? String, "deterministic_minimum")

      let retried = try await summarizer.summarize(sessionId: 9, segments: segments, startedAt: startedAt)
      XCTAssertEqual(retried.json, stored.json)
      XCTAssertEqual(local.generateCallCount, 2)
    }

    func testHashChangeRegeneratesAndKeepsTheNewStoredBlob() async throws {
      let engine = DraftEngine(
        contextWindowTokens: 8192,
        generateResults: [
          .success(LocalSummaryDraft(title: "Original")),
          .success(LocalSummaryDraft(title: "Edited")),
        ]
      )
      let store = MemoryLocalProjectionStore()
      let summarizer = makeSummarizer(engine: engine, store: store)

      _ = try await summarizer.summarize(
        sessionId: 4,
        segments: [TranscriptHash.Segment(text: "one")],
        startedAt: startedAt
      )
      let second = try await summarizer.summarize(
        sessionId: 4,
        segments: [TranscriptHash.Segment(text: "two")],
        startedAt: startedAt
      )
      let payload = try ClientProcessingContract.decode(second.json)

      XCTAssertEqual(engine.generateCallCount, 2)
      XCTAssertEqual(payload.structure.title, "Edited")
    }

    func testGRDBStoreRoundTripsTheExactJSONBytes() async throws {
      let queue = try migratedQueue()
      try await queue.write { db in
        try db.execute(
          sql: "INSERT INTO transcription_sessions (id, updatedAt) VALUES (11, ?)",
          arguments: [Date()]
        )
      }
      let store = GRDBLocalProjectionStore(queue: queue)
      let projection = ClientProcessingContract.assemble(
        draft: LocalSummaryDraft(title: "Persisted", overview: "From GRDB."),
        transcriptSha256: TranscriptHash.sha256(segments: [TranscriptHash.Segment(text: "hi")]),
        provenance: OmiAPI.ProjectionProvenance(
          deviceClass: "macos",
          generatedAt: "2024-01-01T20:14:00Z",
          modelId: "local-server",
          runtime: "local"
        ),
        fallbackTitle: "Recording"
      )
      let stored = try ClientProcessingContract.stored(projection)
      try await store.save(sessionId: 11, projection: stored)
      let reloaded = try await GRDBLocalProjectionStore(queue: queue).load(sessionId: 11)

      XCTAssertEqual(reloaded?.json, stored.json)
      XCTAssertEqual(reloaded?.transcriptSha256, stored.transcriptSha256)
    }

    func testMigrationIsIdempotentWhenTheColumnAlreadyExists() throws {
      let queue = try DatabaseQueue()
      try queue.write { db in
        try db.execute(
          sql: """
            CREATE TABLE transcription_sessions (
              id INTEGER PRIMARY KEY,
              updatedAt DATETIME,
              clientProcessingJson TEXT
            )
            """)
      }
      var migrator = DatabaseMigrator()
      RewindDatabase.registerClientProcessingProjectionMigration(on: &migrator)
      XCTAssertNoThrow(try migrator.migrate(queue))
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

    private func thirtyMinuteSegments() -> [TranscriptHash.Segment] {
      // ~150 wpm × 30 min ≈ 4500 words. Repeating a 15-word line 300 times is
      // enough to overflow AFM's 4096-token shared window.
      let line = "This is filler speech used to force map-reduce on a four thousand token window."
      return (0..<300).map { index in
        TranscriptHash.Segment(speaker: "SPEAKER_00", text: "\(line) \(index)")
      }
    }

    private func migratedQueue() throws -> DatabaseQueue {
      let queue = try DatabaseQueue()
      try queue.write { db in
        try db.execute(
          sql: """
            CREATE TABLE transcription_sessions (
              id INTEGER PRIMARY KEY,
              updatedAt DATETIME
            )
            """)
      }
      var migrator = DatabaseMigrator()
      RewindDatabase.registerClientProcessingProjectionMigration(on: &migrator)
      try migrator.migrate(queue)
      return queue
    }

    private func latestFallbackSnapshot() throws -> [String: Any] {
      let url = try XCTUnwrap(DesktopDiagnosticsManager.shared.writeDiagnosticsAttachment())
      defer { try? FileManager.default.removeItem(at: url) }
      let data = try Data(contentsOf: url)
      let root = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
      let snapshots = try XCTUnwrap(root["snapshots"] as? [[String: Any]])
      return try XCTUnwrap(snapshots.last { ($0["event"] as? String) == "fallback_triggered" })
    }
  }
#endif
