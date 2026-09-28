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
  private(set) var schemaNames: [String] = []
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

  func generateStructured<T: Decodable>(prompt: String, schema: LocalInferenceJSONSchema) async throws -> T {
    let tokens = ConversationChunkSummarizer.estimatedTokens(prompt)
    let result: Result<LocalSummaryDraft, Error> = lock.withLock {
      generateCallCount += 1
      prompts.append(prompt)
      schemaNames.append(schema.name)
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

    // red-proof: use LocalSummaryDraft.jsonSchema for the map pass again
    func testMapPassesAskForASmallerDraftThanTheFinalPass() async throws {
      let engine = DraftEngine(contextWindowTokens: 4096, generateResults: [])
      let summarizer = makeSummarizer(engine: engine, store: MemoryLocalProjectionStore())
      _ = try await summarizer.summarize(sessionId: 11, segments: thirtyMinuteSegments(), startedAt: startedAt)

      let names = engine.schemaNames
      XCTAssertGreaterThan(names.count, 2, "expected several map passes and one reduce")
      XCTAssertEqual(
        names.last, LocalSummaryDraft.jsonSchema.name, "the reduce sees the whole meeting and keeps the full caps")
      XCTAssertTrue(
        names.dropLast().allSatisfy { $0 == LocalSummaryDraft.mapJSONSchema.name },
        "a map pass that may emit 8 sections and 15 items overflowed AFM's prompt+completion window")

      func caps(_ schema: LocalInferenceJSONSchema) throws -> [Int] {
        let object = try XCTUnwrap(JSONSerialization.jsonObject(with: schema.json) as? [String: Any])
        let properties = try XCTUnwrap(object["properties"] as? [String: Any])
        return try ["sections", "events", "action_items"].map {
          try XCTUnwrap((properties[$0] as? [String: Any])?["maxItems"] as? Int)
        }
      }
      let full = try caps(LocalSummaryDraft.jsonSchema)
      let map = try caps(LocalSummaryDraft.mapJSONSchema)
      XCTAssertEqual(full, [8, 6, 15])
      XCTAssertTrue(zip(map, full).allSatisfy { $0 < $1 }, "map caps \(map) must be tighter than \(full)")
      // The bridge parse is the OS-independent half of what AFM will accept.
      XCTAssertNoThrow(try AFMJSONSchemaBridge.parse(LocalSummaryDraft.mapJSONSchema))
    }

    // red-proof: drop the `windowTokens` budget from reducePrompt
    func testReducePromptFitsTheWindowAndKeepsEveryPartialsCommitments() {
      let body = String(repeating: "Detail about the rollout plan and its many caveats. ", count: 120)
      let partials = (1...6).map { index in
        LocalSummaryDraft(
          title: "part \(index)",
          overview: "Overview of part \(index).",
          sections: (1...5).map { LocalSectionDraft(heading: "Topic \(index).\($0)", bodyMarkdown: body) },
          actionItems: [LocalActionItemDraft(description: "Owner \(index) ships item \(index) — naïve café ✓")]
        )
      }
      let window = 8192
      let unbounded = ConversationChunkSummarizer.reducePrompt(partials)
      XCTAssertGreaterThan(
        ConversationChunkSummarizer.estimatedTokens(unbounded), window, "fixture must overflow to prove anything")

      let bounded = ConversationChunkSummarizer.reducePrompt(partials, windowTokens: window)
      XCTAssertLessThanOrEqual(
        ConversationChunkSummarizer.estimatedTokens(bounded)
          + ConversationChunkSummarizer.completionReserve(windowTokens: window),
        window)
      for index in 1...6 {
        XCTAssertTrue(bounded.contains("Overview of part \(index)."), "partial \(index) vanished")
        XCTAssertTrue(
          bounded.contains("Action: Owner \(index) ships item \(index)"),
          "a cut must cost section detail before it costs a commitment (partial \(index))")
      }
    }

    func testCompletionReserveScalesWithTheWindow() {
      XCTAssertEqual(ConversationChunkSummarizer.completionReserve(windowTokens: 8192), 3584)
      XCTAssertEqual(ConversationChunkSummarizer.completionReserve(windowTokens: 32768), 3584)
      XCTAssertEqual(ConversationChunkSummarizer.completionReserve(windowTokens: 4096), 2048)
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
        contextWindowTokens: 8192,
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

    /// red-proof: return `assembled` unconditionally and this stores a projection
    /// whose model_id is the engine's, with nothing in it.
    func testTitleOnlyDraftFailsClosedToTheMinimumInsteadOfImpersonatingASummary() async throws {
      // Schema-valid and content-free. `LocalSummaryDraft` decodes every field
      // through `decodeIfPresent ?? ""` / `?? []`, so this is what a fail-open
      // constrained-decoding path produces.
      let engine = DraftEngine(
        contextWindowTokens: 2048,
        generateResults: [.success(LocalSummaryDraft(title: "Team Sync"))]
      )
      let store = MemoryLocalProjectionStore()
      let runtime = LocalInferenceRuntime(
        engines: [engine],
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

      let stored = try await summarizer.summarize(sessionId: 21, segments: segments, startedAt: startedAt)
      let payload = try ClientProcessingContract.decode(stored.json)

      // The deterministic minimum, not the model's empty draft. Attribution is
      // the point: a projection stamped with an engine id outranks the minimum
      // for display, so an empty one must not claim to be the engine's work.
      XCTAssertEqual(payload.provenance.modelId, ClientProcessingContract.deterministicModelID)
      XCTAssertEqual(payload.provenance.runtime, "deterministic")
      XCTAssertNotEqual(payload.structure.title, "Team Sync")

      let snapshot = try latestFallbackSnapshot()
      XCTAssertEqual(snapshot["reason"] as? String, "contentless_projection")
    }

    /// The gate must not swallow a thin but real summary. One action item and
    /// nothing else is still something the user did not have before.
    func testASingleActionItemIsEnoughContentToKeepTheProjection() async throws {
      let engine = DraftEngine(
        contextWindowTokens: 2048,
        generateResults: [
          .success(
            LocalSummaryDraft(
              title: "Team Sync",
              actionItems: [LocalActionItemDraft(description: "Send the notes", completed: false)]
            ))
        ]
      )
      let store = MemoryLocalProjectionStore()
      let runtime = LocalInferenceRuntime(
        engines: [engine],
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

      let stored = try await summarizer.summarize(sessionId: 22, segments: segments, startedAt: startedAt)
      let payload = try ClientProcessingContract.decode(stored.json)

      XCTAssertEqual(payload.provenance.modelId, LocalInferenceEngineID.localServer.rawValue)
      XCTAssertEqual(payload.structure.title, "Team Sync")
      XCTAssertEqual(payload.actionItems?.count, 1)
    }

    func testHashChangeRegeneratesAndKeepsTheNewStoredBlob() async throws {
      // Overviews carry the content. This test is about regeneration on a hash
      // change, so its drafts must survive the contentless gate on their own
      // merits; a title-only draft now fails closed to the minimum and would
      // make this assert the wrong thing.
      let engine = DraftEngine(
        contextWindowTokens: 8192,
        generateResults: [
          .success(LocalSummaryDraft(title: "Original", overview: "First pass")),
          .success(LocalSummaryDraft(title: "Edited", overview: "Second pass")),
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
      // enough to overflow a 4096-token engine window (chunker stress, not AFM).
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
