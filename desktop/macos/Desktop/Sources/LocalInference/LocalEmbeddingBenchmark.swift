import Foundation
@preconcurrency import GRDB

/// Synthetic local-embedding retrieval harness. Fixtures contain no personal data.
enum LocalEmbeddingBenchmark {
  static let reportKind = "local_embedding_benchmark"
  static let reportVersion = 1

  enum Slice: String, Codable, Sendable { case nameHeavy = "name_heavy", paraphrase, dateBounded = "date_bounded" }
  enum Mode: String, Codable, Sendable { case fts, vector, hybrid, gemini }

  struct Query: Sendable {
    var slice: Slice
    var query: String
    var relevantIDs: [Int64]
    var startDate: Date?
    var endDate: Date?
  }

  struct SliceMetrics: Codable, Equatable, Sendable {
    var slice: String
    var mode: String
    var recallAt10: Double
    var ndcgAt10: Double
    var queries: Int
  }

  struct Report: Codable, Equatable, Sendable {
    var kind: String
    var version: Int
    var generatedAt: String
    var engineID: String
    var fixture: String
    var metrics: [SliceMetrics]
  }

  static func makeSyntheticQueries(day: Date) -> [Query] {
    let start = day.addingTimeInterval(-3600)
    let end = day.addingTimeInterval(3600)
    return [
      Query(slice: .nameHeavy, query: "Northwind", relevantIDs: [1], startDate: nil, endDate: nil),
      Query(slice: .nameHeavy, query: "Zephyr", relevantIDs: [2], startDate: nil, endDate: nil),
      Query(slice: .nameHeavy, query: "Maplecrest", relevantIDs: [3], startDate: nil, endDate: nil),
      Query(slice: .nameHeavy, query: "Quillbrook", relevantIDs: [4], startDate: nil, endDate: nil),
      Query(slice: .nameHeavy, query: "Silverpine", relevantIDs: [5], startDate: nil, endDate: nil),
      Query(slice: .nameHeavy, query: "Harborlight", relevantIDs: [6], startDate: nil, endDate: nil),
      Query(slice: .nameHeavy, query: "Nimbus", relevantIDs: [7], startDate: nil, endDate: nil),
      Query(slice: .nameHeavy, query: "Cedarvale", relevantIDs: [8], startDate: nil, endDate: nil),
      Query(slice: .nameHeavy, query: "Ironleaf", relevantIDs: [9], startDate: nil, endDate: nil),
      Query(slice: .nameHeavy, query: "Brightwell", relevantIDs: [10], startDate: nil, endDate: nil),
      Query(
        slice: .paraphrase, query: "quarterly finance planning notes", relevantIDs: [11], startDate: nil,
        endDate: nil),
      Query(
        slice: .paraphrase, query: "design review for the landing page", relevantIDs: [12], startDate: nil,
        endDate: nil),
      Query(
        slice: .paraphrase, query: "python exception while running tests", relevantIDs: [13], startDate: nil,
        endDate: nil),
      Query(
        slice: .paraphrase, query: "travel itinerary for the conference", relevantIDs: [14], startDate: nil,
        endDate: nil),
      Query(
        slice: .paraphrase, query: "grocery list with oat milk", relevantIDs: [15], startDate: nil, endDate: nil),
      Query(
        slice: .paraphrase, query: "recipe for tomato soup", relevantIDs: [16], startDate: nil, endDate: nil),
      Query(
        slice: .paraphrase, query: "hiring loop for the staff engineer", relevantIDs: [17], startDate: nil,
        endDate: nil),
      Query(
        slice: .paraphrase, query: "garden watering schedule", relevantIDs: [18], startDate: nil, endDate: nil),
      Query(
        slice: .paraphrase, query: "piano practice for scales", relevantIDs: [19], startDate: nil, endDate: nil),
      Query(
        slice: .paraphrase, query: "board game night packing list", relevantIDs: [20], startDate: nil, endDate: nil),
      Query(
        slice: .dateBounded, query: "Northwind", relevantIDs: [1], startDate: start, endDate: end),
      Query(
        slice: .dateBounded, query: "Zephyr", relevantIDs: [2], startDate: start, endDate: end),
      Query(
        slice: .dateBounded, query: "Maplecrest", relevantIDs: [3], startDate: start, endDate: end),
      Query(
        slice: .dateBounded, query: "finance planning", relevantIDs: [11], startDate: start, endDate: end),
      Query(
        slice: .dateBounded, query: "landing page", relevantIDs: [12], startDate: start, endDate: end),
      Query(
        slice: .dateBounded, query: "python exception", relevantIDs: [13], startDate: start, endDate: end),
      Query(
        slice: .dateBounded, query: "conference itinerary", relevantIDs: [14], startDate: start, endDate: end),
      Query(
        slice: .dateBounded, query: "oat milk", relevantIDs: [15], startDate: start, endDate: end),
      Query(
        slice: .dateBounded, query: "tomato soup", relevantIDs: [16], startDate: start, endDate: end),
      Query(
        slice: .dateBounded, query: "staff engineer", relevantIDs: [17], startDate: start, endDate: end),
    ]
  }

  static func installSyntheticFixture(in pool: DatabasePool, day: Date) throws {
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
    let names = [
      "Northwind ledger", "Zephyr prototype", "Maplecrest invoice", "Quillbrook agenda",
      "Silverpine roadmap", "Harborlight notes", "Nimbus checklist", "Cedarvale timeline",
      "Ironleaf budget", "Brightwell roster",
    ]
    let paraphrases = [
      (11, "Q3 financial planning memo for the budget committee"),
      (12, "website homepage mockups awaiting design critique"),
      (13, "unittest traceback and assertion failure in the runner"),
      (14, "flight hotel and badge plan for the industry summit"),
      (15, "shopping list: oats, oat milk, berries"),
      (16, "how to simmer a simple tomato basil soup"),
      (17, "interview loop and rubric for a staff software engineer"),
      (18, "when to water the backyard vegetable beds"),
      (19, "daily chromatic scale routine at the keyboard"),
      (20, "cards snacks and extra chairs for game night"),
    ]
    try pool.write { db in
      for (index, name) in names.enumerated() {
        let id = Int64(index + 1)
        try db.execute(
          sql: "INSERT INTO screenshots VALUES (?, ?, 'Editor', '', ?, NULL)",
          arguments: [id, day, name])
      }
      for (id, text) in paraphrases {
        try db.execute(
          sql: "INSERT INTO screenshots VALUES (?, ?, 'Editor', '', ?, NULL)",
          arguments: [id, day, text])
      }
      try db.execute(sql: "INSERT INTO screenshots_fts(screenshots_fts) VALUES('rebuild')")
    }
  }

  static func embedFixture(
    store: LocalEmbeddingStore, engine: any LocalEmbeddingService, authorization: LocalMutationAuthorization
  ) async throws {
    let docs: [LocalEmbeddingDocument] = try await store.pool.read { db in
      try Row.fetchAll(db, sql: "SELECT id, ocrText, appName, windowTitle FROM screenshots").map { row in
        LocalEmbeddingDocument(
          id: row["id"], ocrText: row["ocrText"], appName: row["appName"], windowTitle: row["windowTitle"])
      }
    }
    for doc in docs {
      let vector = try await engine.embed([doc.text], task: .document)[0]
      try await store.write(
        sourceKind: .screenshot, sourceId: doc.id, modelID: engine.modelID, text: doc.text, vector: vector,
        authorization: authorization)
    }
  }

  static func run(
    store: LocalEmbeddingStore, runtime: LocalEmbeddingRuntime, engine: any LocalEmbeddingService,
    queries: [Query], now: Date = Date()
  ) async throws -> Report {
    let search = LocalHybridSearch(store: store, runtime: runtime, authorization: .unrestricted)
    var metrics: [SliceMetrics] = []
    for slice in [Slice.nameHeavy, .paraphrase, .dateBounded] {
      let sliceQueries = queries.filter { $0.slice == slice }
      for mode in [Mode.fts, .vector, .hybrid] {
        var recalls: [Double] = []
        var ndcgs: [Double] = []
        for item in sliceQueries {
          let engineOrNil: (any LocalEmbeddingService)? = mode == .fts ? nil : engine
          var hits = try await search.search(
            query: item.query, engine: engineOrNil, startDate: item.startDate, endDate: item.endDate, limit: 10)
          if mode == .vector {
            hits = hits.filter { $0.matchedBy == .vector || $0.matchedBy == .both }
          }
          let ranked = hits.map(\.sourceId)
          recalls.append(recallAt10(relevant: item.relevantIDs, ranked: ranked))
          ndcgs.append(ndcgAt10(relevant: item.relevantIDs, ranked: ranked))
        }
        metrics.append(
          SliceMetrics(
            slice: slice.rawValue, mode: mode.rawValue,
            recallAt10: average(recalls), ndcgAt10: average(ndcgs), queries: sliceQueries.count))
      }
    }
    return Report(
      kind: reportKind, version: reportVersion,
      generatedAt: ISO8601DateFormatter().string(from: now), engineID: engine.engineID,
      fixture: "synthetic", metrics: metrics)
  }

  static func write(_ report: Report, to url: URL) throws {
    let encoder = JSONEncoder()
    encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
    let data = try encoder.encode(report)
    try FileManager.default.createDirectory(
      at: url.deletingLastPathComponent(), withIntermediateDirectories: true)
    try data.write(to: url, options: .atomic)
  }

  static func defaultReportURL(now: Date = Date()) -> URL {
    let stamp = ISO8601DateFormatter().string(from: now).replacingOccurrences(of: ":", with: "")
    let support =
      FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask).first
      ?? URL(fileURLWithPath: NSTemporaryDirectory(), isDirectory: true)
    let bundle = Bundle.main.bundleIdentifier ?? "com.omi.desktop"
    return support.appendingPathComponent(bundle, isDirectory: true)
      .appendingPathComponent("local-embedding-benchmark", isDirectory: true)
      .appendingPathComponent("report-\(stamp).json")
  }

  static func recallAt10(relevant: [Int64], ranked: [Int64]) -> Double {
    guard !relevant.isEmpty else { return 0 }
    let found = Set(ranked.prefix(10)).intersection(Set(relevant)).count
    return Double(found) / Double(relevant.count)
  }

  static func ndcgAt10(relevant: [Int64], ranked: [Int64]) -> Double {
    let relevantSet = Set(relevant)
    var dcg = 0.0
    for (index, id) in ranked.prefix(10).enumerated() where relevantSet.contains(id) {
      dcg += 1.0 / log2(Double(index + 2))
    }
    let idealCount = min(10, relevant.count)
    var idcg = 0.0
    if idealCount > 0 {
      for index in 0..<idealCount {
        idcg += 1.0 / log2(Double(index + 2))
      }
    }
    return idcg == 0 ? 0 : dcg / idcg
  }

  static func runSynthetic(
    engine: any LocalEmbeddingService, runtime: LocalEmbeddingRuntime, now: Date = Date()
  ) async throws -> Report {
    let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
    try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: directory) }
    let pool = try DatabasePool(path: directory.appendingPathComponent("synthetic.sqlite").path)
    let day = Date(timeIntervalSince1970: 1_789_000_000)
    try installSyntheticFixture(in: pool, day: day)
    let store = LocalEmbeddingStore(pool: pool)
    try await embedFixture(store: store, engine: engine, authorization: .unrestricted)
    return try await run(
      store: store, runtime: runtime, engine: engine,
      queries: makeSyntheticQueries(day: day), now: now)
  }

  private static func average(_ values: [Double]) -> Double {
    guard !values.isEmpty else { return 0 }
    return values.reduce(0, +) / Double(values.count)
  }
}
