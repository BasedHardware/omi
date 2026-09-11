import Foundation
@preconcurrency import GRDB
import XCTest

@testable import Omi_Computer

@MainActor
final class LocalEmbeddingBenchmarkTests: XCTestCase {
  func testSyntheticParaphraseHybridAtLeastMatchesFTS() async throws {
    let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
    try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: directory) }
    let pool = try DatabasePool(path: directory.appendingPathComponent("fixture.sqlite").path)
    let day = Date(timeIntervalSince1970: 1_789_000_000)
    try LocalEmbeddingBenchmark.installSyntheticFixture(in: pool, day: day)
    let store = LocalEmbeddingStore(pool: pool)
    let engine = HashEmbeddingEngine()
    try await LocalEmbeddingBenchmark.embedFixture(store: store, engine: engine, authorization: .unrestricted)
    let runtime = LocalEmbeddingRuntime(engines: [engine], defaultEngineID: engine.engineID, record: { _, _ in })
    let report = try await LocalEmbeddingBenchmark.run(
      store: store, runtime: runtime, engine: engine,
      queries: LocalEmbeddingBenchmark.makeSyntheticQueries(day: day), now: day)
    XCTAssertEqual(report.kind, LocalEmbeddingBenchmark.reportKind)
    XCTAssertEqual(report.fixture, "synthetic")
    XCTAssertEqual(report.engineID, engine.engineID)
    XCTAssertEqual(report.modelID, engine.modelID)
    XCTAssertEqual(report.dimension, engine.dimension)
    XCTAssertFalse(report.chipClass.isEmpty)
    XCTAssertFalse(report.ramClass.isEmpty)
    XCTAssertEqual(LocalEmbeddingBenchmark.makeSyntheticQueries(day: day).count, 30)
    let paraphraseFTS = try XCTUnwrap(
      report.metrics.first { $0.slice == "paraphrase" && $0.mode == "fts" })
    let paraphraseHybrid = try XCTUnwrap(
      report.metrics.first { $0.slice == "paraphrase" && $0.mode == "hybrid" })
    XCTAssertGreaterThanOrEqual(paraphraseHybrid.recallAt10, paraphraseFTS.recallAt10)
    let dateHits = try await LocalHybridSearch(
      store: store, runtime: runtime, authorization: .unrestricted
    ).search(
      query: "Northwind", engine: engine,
      startDate: day.addingTimeInterval(-3600), endDate: day.addingTimeInterval(3600), limit: 10)
    XCTAssertTrue(dateHits.contains { $0.sourceId == 1 })
    XCTAssertFalse(dateHits.contains { $0.sourceId == 21 })
    let unbounded = try await LocalHybridSearch(
      store: store, runtime: runtime, authorization: .unrestricted
    ).search(query: "Northwind", engine: engine, limit: 10)
    XCTAssertTrue(unbounded.contains { $0.sourceId == 21 })
    let url = directory.appendingPathComponent("report.json")
    try LocalEmbeddingBenchmark.write(report, to: url)
    let decoded = try JSONDecoder().decode(LocalEmbeddingBenchmark.Report.self, from: Data(contentsOf: url))
    XCTAssertEqual(decoded.kind, report.kind)
  }

  func testHeldOutSpanSkipsTheFirstLineAndStaysInWordBounds() {
    XCTAssertNil(LocalEmbeddingBenchmark.heldOutSpan(ocrText: "only one line of words here for padding extra"))
    let span = LocalEmbeddingBenchmark.heldOutSpan(
      ocrText: "WINDOW TITLE LINE\nalpha bravo charlie delta echo foxtrot golf hotel")
    XCTAssertEqual(span, "alpha bravo charlie delta echo foxtrot golf hotel")
    XCTAssertNil(LocalEmbeddingBenchmark.heldOutSpan(ocrText: "title\none two three four five"))
  }

  func testRealFixtureReportIsCountsOnlyAndNeverContainsOCR() async throws {
    let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
    try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: directory) }
    let pool = try DatabasePool(path: directory.appendingPathComponent("real-shaped.sqlite").path)
    let secret = "UNIQUESECRETTOKEN should never appear in the report output file"
    try installRealShapedFixture(in: pool, marker: secret)
    let engine = HashEmbeddingEngine()
    let runtime = LocalEmbeddingRuntime(engines: [engine], defaultEngineID: engine.engineID, record: { _, _ in })
    let report = try await LocalEmbeddingBenchmark.runReal(
      pool: pool, runtime: runtime, engine: engine, sampleLimit: 8, selfRetrievalLimit: 8,
      now: Date(timeIntervalSince1970: 1_789_000_000))
    XCTAssertEqual(report.fixture, "real")
    XCTAssertEqual(report.geminiEmbeddedRows, 4)
    XCTAssertGreaterThanOrEqual(report.indexedRows, 4)
    XCTAssertTrue(report.metrics.contains { $0.slice == "agreement" && $0.mode == "hybrid" })
    XCTAssertTrue(report.metrics.contains { $0.slice == "self_retrieval" && $0.mode == "fts" })
    let url = directory.appendingPathComponent("report.json")
    try LocalEmbeddingBenchmark.write(report, to: url)
    let json = try XCTUnwrap(String(data: Data(contentsOf: url), encoding: .utf8))
    XCTAssertFalse(json.contains(secret))
    XCTAssertFalse(json.contains("WINDOW"))
    XCTAssertFalse(json.contains("SyntheticWindow"))
    XCTAssertTrue(json.contains("\"fixture\" : \"real\""))
  }

  func testOptInCopiedRealDatabaseUsesAppleEngineAndCountsOnly() async throws {
    guard ProcessInfo.processInfo.environment["OMI_REAL_EMBEDDING_BENCH"] == "1" else {
      throw XCTSkip("set OMI_REAL_EMBEDDING_BENCH=1 to run against a copied Rewind DB")
    }
    let dbPath = try XCTUnwrap(ProcessInfo.processInfo.environment["OMI_REAL_EMBEDDING_BENCH_DB"])
    let output =
      ProcessInfo.processInfo.environment["OMI_REAL_EMBEDDING_BENCH_OUT"]
      ?? FileManager.default.temporaryDirectory.appendingPathComponent("real-bench.json").path
    let runtime = LocalEmbeddingRuntime.makeDefault()
    guard case .engine(let engine) = await runtime.selectEngine() else {
      return XCTFail("local_engine_unavailable")
    }
    XCTAssertEqual(engine.engineID, AppleNLContextualEmbeddingEngine.defaultEngineID)
    let pool = try DatabasePool(path: dbPath)
    let report = try await LocalEmbeddingBenchmark.runReal(pool: pool, runtime: runtime, engine: engine)
    let url = URL(fileURLWithPath: output)
    try LocalEmbeddingBenchmark.write(report, to: url)
    let json = try XCTUnwrap(String(data: Data(contentsOf: url), encoding: .utf8))
    XCTAssertEqual(report.fixture, "real")
    XCTAssertEqual(report.engineID, engine.engineID)
    XCTAssertFalse(json.contains("ocrText"))
    XCTAssertFalse(json.contains("windowTitle"))
  }

  private func installRealShapedFixture(in pool: DatabasePool, marker: String) throws {
    try pool.write { db in
      try db.execute(
        sql: """
          CREATE TABLE screenshots(id INTEGER PRIMARY KEY, timestamp DATETIME NOT NULL, appName TEXT NOT NULL,
            windowTitle TEXT, ocrText TEXT, embedding BLOB);
          CREATE VIRTUAL TABLE screenshots_fts USING fts5(ocrText, windowTitle, appName, content='screenshots', content_rowid='id');
          CREATE TABLE transcription_sessions(id INTEGER PRIMARY KEY);
          CREATE TABLE memories(id INTEGER PRIMARY KEY, content TEXT NOT NULL, deleted INTEGER NOT NULL DEFAULT 0,
            createdAt DATETIME NOT NULL, sourceApp TEXT);
          """)
    }
    var migrator = DatabaseMigrator()
    LocalEmbeddingStore.registerMigration(on: &migrator)
    try migrator.migrate(pool)
    let day = Date(timeIntervalSince1970: 1_789_000_000)
    try pool.write { db in
      for index in 1...4 {
        var vector = [Float](repeating: 0, count: 8)
        vector[index % 8] = 1
        let blob = vector.withUnsafeBytes { Data($0) }
        let text =
          "WINDOW \(index)\n\(marker) row\(index) alpha bravo charlie delta echo foxtrot golf hotel india"
        try db.execute(
          sql: "INSERT INTO screenshots VALUES (?, ?, 'Editor', 'SyntheticWindow', ?, ?)",
          arguments: [Int64(index), day, text, blob])
      }
      try db.execute(sql: "INSERT INTO screenshots_fts(screenshots_fts) VALUES('rebuild')")
    }
  }
}
