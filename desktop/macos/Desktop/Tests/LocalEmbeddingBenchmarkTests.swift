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
}
