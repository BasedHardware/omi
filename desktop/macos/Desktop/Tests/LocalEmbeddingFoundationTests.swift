import Foundation
@preconcurrency import GRDB
import XCTest

@testable import Omi_Computer

@MainActor
final class LocalEmbeddingFoundationTests: XCTestCase {
  private func fixture() throws -> (LocalEmbeddingStore, URL) {
    let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
    try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
    let pool = try DatabasePool(path: directory.appendingPathComponent("fixture.sqlite").path)
    try pool.write { db in
      try db.execute(
        sql: """
          CREATE TABLE screenshots(id INTEGER PRIMARY KEY, timestamp DATETIME NOT NULL, appName TEXT NOT NULL,
            windowTitle TEXT, ocrText TEXT, embedding BLOB);
          CREATE VIRTUAL TABLE screenshots_fts USING fts5(ocrText, windowTitle, appName, content='screenshots', content_rowid='id');
          INSERT INTO screenshots VALUES
            (1, '2026-09-09 12:00:00.000', 'Editor', '', 'budget synthetic content', NULL),
            (2, '2026-09-09 12:00:00.000', 'Editor', '', 'budget synthetic content', NULL),
            (3, '2026-09-09 12:00:00.000', 'Editor', '', 'unrelated synthetic content', NULL);
          INSERT INTO screenshots_fts(screenshots_fts) VALUES('rebuild');
          """)
    }
    var migrator = DatabaseMigrator()
    LocalEmbeddingStore.registerMigration(on: &migrator)
    try migrator.migrate(pool)
    return (LocalEmbeddingStore(pool: pool), directory)
  }

  func testMigrationUniqueKeyModelIsolationAndInvalidation() async throws {
    let (store, directory) = try fixture()
    defer { try? FileManager.default.removeItem(at: directory) }
    try await store.write(
      sourceKind: .screenshot, sourceId: 1, modelID: "a", text: "[Editor]\nbudget synthetic content", vector: [1, 0],
      authorization: .unrestricted)
    try await store.write(
      sourceKind: .screenshot, sourceId: 1, modelID: "b", text: "[Editor]\nbudget synthetic content",
      vector: [0, 1, 0],
      authorization: .unrestricted)
    try await store.write(
      sourceKind: .screenshot, sourceId: 1, modelID: "a", text: "[Editor]\nbudget synthetic content", vector: [0, 1],
      authorization: .unrestricted)
    let rows = try await store.pool.read { db in
      XCTAssertTrue(try db.tableExists("local_embeddings"))
      XCTAssertEqual(try Int.fetchOne(db, sql: "SELECT COUNT(*) FROM local_embeddings"), 2)
      XCTAssertEqual(
        try String.fetchOne(db, sql: "SELECT textSha256 FROM local_embeddings LIMIT 1"),
        LocalEmbeddingStore.textHash("[Editor]\nbudget synthetic content"))
      XCTAssertNil(try Data.fetchOne(db, sql: "SELECT embedding FROM screenshots WHERE id = 1"))
      return try Int.fetchOne(db, sql: "SELECT COUNT(*) FROM local_embeddings")
    }
    XCTAssertEqual(rows, 2)
    do {
      try await store.pool.write { db in
        try db.execute(sql: "INSERT INTO local_embeddings SELECT * FROM local_embeddings WHERE modelId = 'a'")
      }
      XCTFail("duplicate source/model key must fail")
    } catch { XCTAssertTrue(error is DatabaseError) }
    XCTAssertEqual(
      try store.readBatch(modelID: "a", dimension: 2, startDate: nil, endDate: nil, appFilter: nil).first?.vector,
      [0, 1])
    XCTAssertTrue(try store.readBatch(modelID: "a", dimension: 3, startDate: nil, endDate: nil, appFilter: nil).isEmpty)
    try await store.pool.write { db in try db.execute(sql: "UPDATE screenshots SET ocrText = 'changed' WHERE id = 1") }
    let remaining = try await store.pool.read { db in try Int.fetchOne(db, sql: "SELECT COUNT(*) FROM local_embeddings")
    }
    XCTAssertEqual(remaining, 0)
  }

  func testStaleSourceCannotBeReintroducedAfterTextEditOrDelete() async throws {
    let (store, directory) = try fixture()
    defer { try? FileManager.default.removeItem(at: directory) }
    for sql in ["UPDATE screenshots SET ocrText = 'edited' WHERE id = 1", "DELETE FROM screenshots WHERE id = 1"] {
      try await store.pool.write { db in try db.execute(sql: sql) }
      do {
        try await store.write(
          sourceKind: .screenshot, sourceId: 1, modelID: "test",
          text: "[Editor]\nbudget synthetic content", vector: [1], authorization: .unrestricted)
        XCTFail("stale embedding accepted")
      } catch { XCTAssertTrue(error is LocalEmbeddingStoreError) }
    }
  }

  func testHybridFixtureReturnsBothVectorAndKeywordWithDeterministicTies() async throws {
    let (store, directory) = try fixture()
    defer { try? FileManager.default.removeItem(at: directory) }
    let engine = HashEmbeddingEngine()
    let vector = try await engine.embed(["budget"], task: .query)[0]
    for id: Int64 in [1, 3] {
      try await store.write(
        sourceKind: .screenshot, sourceId: id, modelID: engine.modelID,
        text: id == 1 ? "[Editor]\nbudget synthetic content" : "[Editor]\nunrelated synthetic content", vector: vector,
        authorization: .unrestricted)
    }
    let runtime = LocalEmbeddingRuntime(engines: [engine], defaultEngineID: engine.engineID, record: { _, _ in })
    let search = LocalHybridSearch(store: store, runtime: runtime, authorization: .unrestricted)
    let hits = try await search.search(query: "budget", engine: engine)
    XCTAssertEqual(hits.map(\.sourceId), [1, 3, 2])
    XCTAssertEqual(hits.map(\.matchedBy), [.both, .vector, .keyword])
    XCTAssertEqual(hits[0].fusedScore, 2.0 / 62, accuracy: 0.000001)
    let repeated = try await search.search(query: "budget", engine: engine)
    XCTAssertEqual(repeated, hits)
    let filtered = try await search.search(query: "budget", engine: engine, appFilter: "Missing")
    XCTAssertTrue(filtered.isEmpty)
    let outside = try await search.search(query: "budget", engine: engine, endDate: Date(timeIntervalSince1970: 1))
    XCTAssertTrue(outside.isEmpty)
    let keywordOnly = try await search.search(query: "budget", engine: nil)
    XCTAssertEqual(keywordOnly.map(\.sourceId), [2, 1])
    XCTAssertTrue(keywordOnly.allSatisfy { $0.matchedBy == .keyword })
    let bounded = try await search.search(query: "budget", engine: engine, maxScannedEmbeddings: 1)
    XCTAssertEqual(bounded.first?.sourceId, 3)
    XCTAssertFalse(bounded.contains { $0.matchedBy == .both })
  }

  func testOwnerRevocationRejectsWritesAndSearch() async throws {
    let (store, directory) = try fixture()
    defer { try? FileManager.default.removeItem(at: directory) }
    let revoked = LocalMutationAuthorization { false }
    do {
      try await store.write(
        sourceKind: .screenshot, sourceId: 1, modelID: "test", text: "[Editor]\nunrelated synthetic content",
        vector: [1], authorization: revoked)
      XCTFail("revoked write accepted")
    } catch { XCTAssertTrue(error is LocalMutationAuthorizationError) }
    let count = try await store.pool.read { db in try Int.fetchOne(db, sql: "SELECT COUNT(*) FROM local_embeddings") }
    XCTAssertEqual(count, 0)
    do {
      _ = try await LocalHybridSearch(store: store, runtime: .makeDefault(), authorization: revoked).search(
        query: "budget", engine: nil)
      XCTFail("revoked read accepted")
    } catch { XCTAssertTrue(error is LocalMutationAuthorizationError) }
  }

  func testCompactionSelectsCompletedWinnerIndependentlyOfGemini() async throws {
    let (store, directory) = try fixture()
    defer { try? FileManager.default.removeItem(at: directory) }
    let cutoff = ISO8601DateFormatter().date(from: "2026-09-09T12:05:00Z")!
    let before = try store.screenshotsNeedingEmbedding(modelID: "a", olderThan: cutoff.addingTimeInterval(-1))
    XCTAssertTrue(before.isEmpty)
    let winner = try store.screenshotsNeedingEmbedding(modelID: "a", olderThan: cutoff)
    XCTAssertEqual(winner.map(\.id), [3])
    try await store.write(
      sourceKind: .screenshot, sourceId: 3, modelID: "a", text: "[Editor]\nunrelated synthetic content", vector: [1],
      authorization: .unrestricted)
    XCTAssertTrue(try store.screenshotsNeedingEmbedding(modelID: "a", olderThan: cutoff).isEmpty)
    XCTAssertEqual(try store.screenshotsNeedingEmbedding(modelID: "b", olderThan: cutoff).count, 1)
  }

  func testDisabledLocalPreservesLegacySearchOutput() async throws {
    let runtime = LocalEmbeddingRuntime(
      engines: [],
      killSwitches: LocalEmbeddingKillSwitches(isDisabled: true, forcedEngineRaw: nil), record: { _, _ in })
    let result = try await ScreenHistorySearchRoute.search(
      runtime: runtime,
      local: { _ in
        XCTFail("disabled route called local search")
        return "local"
      }, legacy: { "unchanged legacy output" })
    XCTAssertEqual(result, "unchanged legacy output")
  }

  func testChatSemanticSearchDisabledKeepsLegacyThresholdParametersAndRendering() async {
    let runtime = LocalEmbeddingRuntime(
      engines: [],
      killSwitches: LocalEmbeddingKillSwitches(isDisabled: true, forcedEngineRaw: nil), record: { _, _ in })
    let dependencies = ChatToolExecutor.SemanticSearchDependencies(
      runtime: runtime,
      legacySearch: { query, start, end, app, topK in
        XCTAssertEqual(query, "budget")
        XCTAssertEqual(app, "Editor")
        XCTAssertLessThan(start, end)
        XCTAssertEqual(topK, 20)
        return [(2, 0.3), (1, 0.75)]
      },
      screenshot: { id in
        XCTAssertEqual(id, 1, "legacy 0.3 threshold must filter before loading a screenshot")
        return Screenshot(
          id: id, timestamp: Date(timeIntervalSince1970: 1_789_000_000), appName: "Editor",
          windowTitle: "Plan", ocrText: "budget\nreview")
      })
    let result = await ChatToolExecutor.executeSemanticSearch(
      ["query": "budget", "app_filter": "Editor", "limit": 1], runID: nil, attemptID: nil,
      expectedOwnerID: nil, dependencies: dependencies)
    XCTAssertTrue(result.hasPrefix("Found 1 screenshot(s) matching \"budget\":"))
    XCTAssertTrue(result.contains("Editor - Plan (screenshot_id: 1, similarity: 0.75)"))
    XCTAssertTrue(result.contains("Content: budget review"))
    XCTAssertFalse(result.contains("hybrid"))
  }

  func testSelectedLocalQueryFailureUsesKeywordsWithoutLegacyCall() async throws {
    let (store, directory) = try fixture()
    defer { try? FileManager.default.removeItem(at: directory) }
    let engine = FailingQueryEmbeddingEngine()
    let runtime = LocalEmbeddingRuntime(engines: [engine], defaultEngineID: engine.engineID, record: { _, _ in })
    let hits = try await ScreenHistorySearchRoute.search(
      runtime: runtime,
      local: { selected in
        try await LocalHybridSearch(store: store, runtime: runtime, authorization: .unrestricted)
          .search(query: "budget", engine: selected)
      },
      legacy: {
        XCTFail("selected local engine failure reached Gemini route")
        return [LocalHybridHit]()
      })
    XCTAssertEqual(hits.map(\.sourceId), [2, 1])
    XCTAssertTrue(hits.allSatisfy { $0.matchedBy == .keyword })
  }

  func testProbeFailureStaysOnLocalKeywordsWithoutLegacyCall() async throws {
    let (store, directory) = try fixture()
    defer { try? FileManager.default.removeItem(at: directory) }
    let engine = UnavailableAssetsEmbeddingEngine()
    let runtime = LocalEmbeddingRuntime(engines: [engine], defaultEngineID: engine.engineID, record: { _, _ in })
    let hits = try await ScreenHistorySearchRoute.search(
      runtime: runtime,
      local: { selected in
        XCTAssertNil(selected)
        return try await LocalHybridSearch(store: store, runtime: runtime, authorization: .unrestricted)
          .search(query: "budget", engine: selected)
      },
      legacy: {
        XCTFail("assets-unavailable probe reached Gemini route")
        return [LocalHybridHit]()
      })
    XCTAssertEqual(hits.map(\.sourceId), [2, 1])
    XCTAssertTrue(hits.allSatisfy { $0.matchedBy == .keyword })
  }

  func testSourceKindFilterKeepsScreenSearchSeparateFromTranscripts() async throws {
    let (store, directory) = try fixture()
    defer { try? FileManager.default.removeItem(at: directory) }
    let chunks = TranscriptChunker.chunks(
      sessionId: 9,
      segments: (0..<10).map {
        TranscriptChunker.Segment(text: "budget spoken segment \($0)", order: $0, startedAt: Date())
      })
    XCTAssertEqual(chunks.count, 2)
    XCTAssertEqual(chunks[0].chunkIndex, 0)
    XCTAssertEqual(chunks[1].chunkIndex, 1)
    try await store.pool.write { db in
      try db.execute(sql: "INSERT INTO transcription_sessions(id) VALUES (9)")
      try db.execute(
        sql: "INSERT INTO memories(content, deleted, createdAt, sourceApp) VALUES ('budget fact', 0, ?, 'Notes')",
        arguments: [Date()])
    }
    _ = try await store.upsertTranscriptChunks(chunks, authorization: .unrestricted)
    let search = LocalHybridSearch(store: store, runtime: .makeDefault(), authorization: .unrestricted)
    let screens = try await search.search(query: "budget", engine: nil, sourceKinds: [.screenshot])
    XCTAssertTrue(screens.allSatisfy { $0.sourceKind == .screenshot })
    let transcripts = try await search.search(query: "budget", engine: nil, sourceKinds: [.transcriptChunk])
    XCTAssertTrue(transcripts.contains { $0.sourceKind == .transcriptChunk })
    XCTAssertFalse(transcripts.contains { $0.sourceKind == .screenshot })
    let memories = try await search.search(query: "budget", engine: nil, sourceKinds: [.memory])
    XCTAssertTrue(memories.contains { $0.sourceKind == .memory })
    XCTAssertFalse(memories.contains { $0.sourceKind == .screenshot })
  }
}
