import Foundation
@preconcurrency import GRDB

/// Synthetic local-embedding retrieval harness. Fixtures contain no personal data.
enum LocalEmbeddingBenchmark {
  static let reportKind = "local_embedding_benchmark"
  static let reportVersion = 1

  enum Slice: String, Codable, Sendable {
    case nameHeavy = "name_heavy"
    case paraphrase
    case dateBounded = "date_bounded"
  }
  enum Mode: String, Codable, Sendable {
    case fts
    case vector
    case hybrid
  }

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
    var recallAt1: Double
  }

  struct Report: Codable, Equatable, Sendable {
    var kind: String
    var version: Int
    var generatedAt: String
    var engineID: String
    var modelID: String
    var dimension: Int
    var fixture: String
    var chipClass: String
    var ramClass: String
    var sampledRows: Int
    var geminiEmbeddedRows: Int
    var indexedRows: Int
    var embedMsP50: Double
    var embedMsP95: Double
    var indexMs: Double
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
      let distractorDay = day.addingTimeInterval(10 * 24 * 3600)
      for (index, name) in names.enumerated() {
        let id = Int64(index + 21)
        try db.execute(
          sql: "INSERT INTO screenshots VALUES (?, ?, 'Editor', '', ?, NULL)",
          arguments: [id, distractorDay, "\(name) distractor"])
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
        dimension: engine.dimension, authorization: authorization)
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
          let retrieval: LocalHybridSearch.RetrievalMode
          let engineOrNil: (any LocalEmbeddingService)?
          switch mode {
          case .fts:
            retrieval = .keyword
            engineOrNil = nil
          case .vector:
            retrieval = .vector
            engineOrNil = engine
          case .hybrid:
            retrieval = .hybrid
            engineOrNil = engine
          }
          let hits = try await search.search(
            query: item.query, engine: engineOrNil, startDate: item.startDate, endDate: item.endDate, limit: 10,
            retrieval: retrieval)
          let ranked = hits.map(\.sourceId)
          recalls.append(recallAt10(relevant: item.relevantIDs, ranked: ranked))
          ndcgs.append(ndcgAt10(relevant: item.relevantIDs, ranked: ranked))
        }
        metrics.append(
          SliceMetrics(
            slice: slice.rawValue, mode: mode.rawValue,
            recallAt10: average(recalls), ndcgAt10: average(ndcgs), queries: sliceQueries.count,
            recallAt1: 0))
      }
    }
    let machine = machineClass()
    return Report(
      kind: reportKind, version: reportVersion,
      generatedAt: ISO8601DateFormatter().string(from: now), engineID: engine.engineID,
      modelID: engine.modelID, dimension: engine.dimension, fixture: "synthetic",
      chipClass: machine.chip, ramClass: machine.ram, sampledRows: 30, geminiEmbeddedRows: 0,
      indexedRows: 30, embedMsP50: 0, embedMsP95: 0, indexMs: 0, metrics: metrics)
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

  static func machineClass() -> (chip: String, ram: String) {
    #if arch(arm64)
      let chip = "apple_silicon"
    #else
      let chip = "intel"
    #endif
    let gb = Int(ProcessInfo.processInfo.physicalMemory / 1_073_741_824)
    let ram: String
    switch gb {
    case ..<12: ram = "8gb"
    case 12..<24: ram = "16gb"
    case 24..<48: ram = "32gb"
    default: ram = "64gb_plus"
    }
    return (chip, ram)
  }

  /// Distinct 6–12 word span from after the first line. Returns nil when OCR is too short.
  /// Callers must not log the result.
  static func heldOutSpan(ocrText: String) -> String? {
    let lines = ocrText.split(omittingEmptySubsequences: false, whereSeparator: \.isNewline)
    let rest = lines.dropFirst().joined(separator: " ")
    let words = rest.split { $0.isWhitespace || $0.isNewline }.map(String.init).filter { !$0.isEmpty }
    guard words.count >= 6 else { return nil }
    let length = min(12, words.count)
    let origin = (words.count - length) / 2
    return words[origin..<(origin + length)].joined(separator: " ")
  }

  static func floats(from data: Data) -> [Float]? {
    let count = data.count / MemoryLayout<Float>.size
    guard count > 0, data.count == count * MemoryLayout<Float>.size else { return nil }
    return data.withUnsafeBytes { buffer in
      guard let base = buffer.baseAddress?.assumingMemoryBound(to: Float.self) else { return nil }
      return Array(UnsafeBufferPointer(start: base, count: count))
    }
  }

  static func rankByCosine(query: [Float], corpus: [(id: Int64, vector: [Float])], limit: Int) -> [Int64] {
    var scored: [(id: Int64, score: Float)] = []
    scored.reserveCapacity(min(corpus.count, 512))
    for row in corpus {
      guard let score = LocalHybridSearch.cosine(query, row.vector), score > 0 else { continue }
      scored.append((row.id, score))
    }
    scored.sort { lhs, rhs in
      if lhs.score == rhs.score { return lhs.id > rhs.id }
      return lhs.score > rhs.score
    }
    return Array(scored.prefix(max(0, min(limit, 50)))).map(\.id)
  }

  static func copyDatabase(from source: URL, to directory: URL) throws -> URL {
    let dest = directory.appendingPathComponent("omi.db")
    let fm = FileManager.default
    for suffix in ["", "-wal", "-shm"] {
      let file = URL(fileURLWithPath: source.path + suffix)
      guard fm.fileExists(atPath: file.path) else { continue }
      try fm.copyItem(at: file, to: URL(fileURLWithPath: dest.path + suffix))
    }
    return dest
  }

  static func discoverBetaDatabase() -> URL? {
    let support =
      FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask).first
      ?? URL(fileURLWithPath: NSHomeDirectory()).appendingPathComponent("Library/Application Support")
    let users = support.appendingPathComponent("Omi Beta/users", isDirectory: true)
    guard
      let enumerator = FileManager.default.enumerator(
        at: users, includingPropertiesForKeys: [.fileSizeKey],
        options: [.skipsHiddenFiles])
    else { return nil }
    var best: (url: URL, size: Int)?
    while let item = enumerator.nextObject() as? URL {
      guard item.lastPathComponent == "omi.db" else { continue }
      let size = (try? item.resourceValues(forKeys: [.fileSizeKey]).fileSize) ?? 0
      if best.map({ size > $0.size }) ?? true { best = (item, size) }
    }
    return best?.url
  }

  static func runReal(
    pool: DatabasePool, runtime: LocalEmbeddingRuntime, engine: any LocalEmbeddingService,
    sampleLimit: Int = 500, selfRetrievalLimit: Int = 100, now: Date = Date()
  ) async throws -> Report {
    let store = LocalEmbeddingStore(pool: pool)
    // A copied Rewind DB already has RewindDatabase's migration identifiers.
    // A fresh DatabaseMigrator that only knows `createLocalEmbeddings` would
    // reject them. Create the table only when this copy predates local embeddings.
    try await pool.write { db in
      guard try db.tableExists("local_embeddings") == false else { return }
      try db.execute(
        sql: """
          CREATE TABLE local_embeddings (
            sourceKind TEXT NOT NULL CHECK(sourceKind IN ('screenshot', 'transcript_chunk', 'memory')),
            sourceId INTEGER NOT NULL,
            modelId TEXT NOT NULL,
            dimension INTEGER NOT NULL CHECK(dimension > 0),
            textSha256 TEXT NOT NULL,
            vector BLOB NOT NULL CHECK(length(vector) = dimension * 4),
            createdAt DOUBLE NOT NULL,
            UNIQUE(sourceKind, sourceId, modelId)
          );
          CREATE INDEX local_embeddings_model ON local_embeddings(modelId, dimension, sourceKind, sourceId);
          """)
    }
    let cap = max(0, min(sampleLimit, 500))
    let rows: [(id: Int64, ocr: String, app: String, title: String, gemini: [Float])] = try await pool.read { db in
      try Row.fetchAll(
        db,
        sql: """
          SELECT id, ocrText, appName, windowTitle, embedding FROM screenshots
          WHERE embedding IS NOT NULL AND ocrText IS NOT NULL AND LENGTH(TRIM(ocrText)) > 0
          ORDER BY id DESC LIMIT ?
          """,
        arguments: [cap]
      ).compactMap { row in
        guard let id = row["id"] as? Int64, let ocr = row["ocrText"] as? String, !ocr.isEmpty
        else { return nil }
        let blobValue = row["embedding"] as DatabaseValue
        guard case .blob(let blob) = blobValue.storage, let vector = floats(from: blob),
          LocalEmbeddingProbe.valid(vector, dimension: vector.count)
        else { return nil }
        return (
          id, ocr, (row["appName"] as? String) ?? "", (row["windowTitle"] as? String) ?? "",
          vector
        )
      }
    }
    let geminiCount = rows.count
    var embedMs: [Double] = []
    let indexStarted = ContinuousClock.now
    for row in rows {
      let doc = LocalEmbeddingDocument(id: row.id, ocrText: row.ocr, appName: row.app, windowTitle: row.title)
      let pending = try store.filterNeedingEmbedding(
        items: [(row.id, doc.text)], sourceKind: .screenshot, modelID: engine.modelID)
      guard !pending.isEmpty else { continue }
      let started = ContinuousClock.now
      guard let vector = await runtime.embed([doc.text], task: .document, using: engine)?.first else {
        continue
      }
      embedMs.append(durationMilliseconds(from: started, to: ContinuousClock.now))
      try await store.write(
        sourceKind: .screenshot, sourceId: row.id, modelID: engine.modelID, text: doc.text,
        vector: vector, dimension: engine.dimension, authorization: .unrestricted)
    }
    let indexMs = durationMilliseconds(from: indexStarted, to: ContinuousClock.now)
    let indexed = try await pool.read { db in
      try Int.fetchOne(
        db,
        sql: """
          SELECT COUNT(*) FROM local_embeddings
          WHERE sourceKind = 'screenshot' AND modelId = ?
          """,
        arguments: [engine.modelID]) ?? 0
    }
    let search = LocalHybridSearch(store: store, runtime: runtime, authorization: .unrestricted)
    let corpus = rows.map { (id: $0.id, vector: $0.gemini) }
    let targets = Array(rows.prefix(max(0, min(selfRetrievalLimit, 100))))
    var agreementOverlap: [String: [Double]] = ["fts": [], "vector": [], "hybrid": [], "gemini": []]
    var agreementNdcg: [String: [Double]] = ["fts": [], "vector": [], "hybrid": [], "gemini": []]
    var selfR1: [String: [Double]] = ["fts": [], "vector": [], "hybrid": [], "gemini": []]
    var selfR10: [String: [Double]] = ["fts": [], "vector": [], "hybrid": [], "gemini": []]
    for target in targets {
      guard let span = heldOutSpan(ocrText: target.ocr) else { continue }
      let geminiTop = rankByCosine(query: target.gemini, corpus: corpus, limit: 10)
      let modes: [(String, LocalHybridSearch.RetrievalMode, (any LocalEmbeddingService)?)] = [
        ("fts", .keyword, nil), ("vector", .vector, engine), ("hybrid", .hybrid, engine),
      ]
      for (name, retrieval, engineOrNil) in modes {
        let hits = try await search.search(
          query: span, engine: engineOrNil, limit: 10, retrieval: retrieval)
        let ranked = hits.map(\.sourceId)
        agreementOverlap[name, default: []].append(recallAt10(relevant: geminiTop, ranked: ranked))
        agreementNdcg[name, default: []].append(ndcgAt10(relevant: geminiTop, ranked: ranked))
        selfR1[name, default: []].append(ranked.first == target.id ? 1 : 0)
        selfR10[name, default: []].append(ranked.prefix(10).contains(target.id) ? 1 : 0)
      }
      selfR1["gemini", default: []].append(geminiTop.first == target.id ? 1 : 0)
      selfR10["gemini", default: []].append(geminiTop.prefix(10).contains(target.id) ? 1 : 0)
      agreementOverlap["gemini", default: []].append(1)
      agreementNdcg["gemini", default: []].append(1)
    }
    func packAgreement(_ mode: String) -> SliceMetrics {
      let overlap = agreementOverlap[mode] ?? []
      return SliceMetrics(
        slice: "agreement", mode: mode, recallAt10: average(overlap),
        ndcgAt10: average(agreementNdcg[mode] ?? []), queries: overlap.count, recallAt1: 0)
    }
    func packSelf(_ mode: String) -> SliceMetrics {
      let r10 = selfR10[mode] ?? []
      return SliceMetrics(
        slice: "self_retrieval", mode: mode, recallAt10: average(r10), ndcgAt10: 0,
        queries: r10.count, recallAt1: average(selfR1[mode] ?? []))
    }
    let machine = machineClass()
    return Report(
      kind: reportKind, version: reportVersion,
      generatedAt: ISO8601DateFormatter().string(from: now), engineID: engine.engineID,
      modelID: engine.modelID, dimension: engine.dimension, fixture: "real",
      chipClass: machine.chip, ramClass: machine.ram, sampledRows: rows.count,
      geminiEmbeddedRows: geminiCount, indexedRows: indexed,
      embedMsP50: percentile(embedMs, 0.50), embedMsP95: percentile(embedMs, 0.95),
      indexMs: indexMs,
      metrics: [
        packAgreement("fts"), packAgreement("vector"), packAgreement("hybrid"), packAgreement("gemini"),
        packSelf("fts"), packSelf("vector"), packSelf("hybrid"), packSelf("gemini"),
      ])
  }

  private static func durationMilliseconds(from start: ContinuousClock.Instant, to end: ContinuousClock.Instant)
    -> Double
  {
    let duration = start.duration(to: end)
    return Double(duration.components.seconds) * 1000 + Double(duration.components.attoseconds) / 1e15
  }

  private static func percentile(_ values: [Double], _ p: Double) -> Double {
    guard !values.isEmpty else { return 0 }
    let sorted = values.sorted()
    let idx = min(sorted.count - 1, max(0, Int((Double(sorted.count - 1) * p).rounded())))
    return sorted[idx]
  }

  private static func average(_ values: [Double]) -> Double {
    guard !values.isEmpty else { return 0 }
    return values.reduce(0, +) / Double(values.count)
  }
}
