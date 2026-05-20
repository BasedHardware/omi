import Foundation
import GRDB

// MARK: - Memory wiki page

struct MemoryWikiPageRecord: Codable, FetchableRecord, PersistableRecord, Identifiable {
  var id: Int64?
  var slug: String
  var title: String
  var body: String
  var tagsJson: String?
  var linksJson: String?
  var category: String
  var sourceType: String?
  var sourceId: String?
  var createdAt: Date
  var updatedAt: Date

  static let databaseTableName = "memory_pages"
}

struct MemoryWikiSearchHit: Identifiable, Equatable {
  let id: Int64
  let slug: String
  let title: String
  let snippet: String
  let category: String
  let rank: Double
}

/// Local structured wiki + FTS5 search (no embedding API).
actor MemoryWikiStorage {
  static let shared = MemoryWikiStorage()

  private var dbQueue: DatabasePool?

  private init() {}

  func invalidateCache() {
    dbQueue = nil
  }

  private func ensureDB() async throws -> DatabasePool {
    if let dbQueue { return dbQueue }
    try await RewindDatabase.shared.initialize()
    guard let queue = await RewindDatabase.shared.getDatabaseQueue() else {
      throw MemoryWikiError.databaseNotInitialized
    }
    dbQueue = queue
    return queue
  }

  func upsertPage(
    slug: String,
    title: String,
    body: String,
    tags: [String] = [],
    links: [String] = [],
    category: String = "system",
    sourceType: String? = nil,
    sourceId: String? = nil
  ) async throws -> Int64 {
    let db = try await ensureDB()
    let now = Date()
    let tagsJson = tags.isEmpty ? nil : String(data: try JSONEncoder().encode(tags), encoding: .utf8)
    let linksJson = links.isEmpty ? nil : String(data: try JSONEncoder().encode(links), encoding: .utf8)

    return try await db.write { database in
      if let existing = try MemoryWikiPageRecord
        .filter(Column("slug") == slug)
        .fetchOne(database)
      {
        var row = existing
        row.title = title
        row.body = body
        row.tagsJson = tagsJson
        row.linksJson = linksJson
        row.category = category
        row.sourceType = sourceType
        row.sourceId = sourceId
        row.updatedAt = now
        try row.update(database)
        return existing.id ?? 0
      }
      var row = MemoryWikiPageRecord(
        id: nil,
        slug: slug,
        title: title,
        body: body,
        tagsJson: tagsJson,
        linksJson: linksJson,
        category: category,
        sourceType: sourceType,
        sourceId: sourceId,
        createdAt: now,
        updatedAt: now
      )
      try row.insert(database)
      return row.id ?? 0
    }
  }

  func search(query: String, limit: Int = 20) async throws -> [MemoryWikiSearchHit] {
    let trimmed = query.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !trimmed.isEmpty else { return [] }

    let words = trimmed.components(separatedBy: .whitespaces)
      .map { $0.filter { $0.isLetter || $0.isNumber } }
      .filter { $0.count >= 2 }
    guard !words.isEmpty else { return [] }
    let ftsQuery = words.map { "\($0)*" }.joined(separator: " OR ")

    let db = try await ensureDB()
    return try await db.read { database in
      let rows = try Row.fetchAll(
        database,
        sql: """
          SELECT memory_pages.id, memory_pages.slug, memory_pages.title, memory_pages.category,
                 snippet(memory_pages_fts, 1, '', '', '…', 12) AS snippet,
                 bm25(memory_pages_fts) AS rank
          FROM memory_pages_fts
          JOIN memory_pages ON memory_pages.id = memory_pages_fts.rowid
          WHERE memory_pages_fts MATCH ?
          ORDER BY rank
          LIMIT ?
          """,
        arguments: [ftsQuery, limit]
      )
      return rows.compactMap { row -> MemoryWikiSearchHit? in
        guard let id: Int64 = row["id"],
          let slug: String = row["slug"],
          let title: String = row["title"],
          let category: String = row["category"]
        else { return nil }
        let snippet: String = row["snippet"] ?? title
        let rank: Double = row["rank"] ?? 0
        return MemoryWikiSearchHit(
          id: id, slug: slug, title: title, snippet: snippet, category: category, rank: rank
        )
      }
    }
  }

  static func slugify(_ title: String) -> String {
    let lowered = title.lowercased()
    let allowed = lowered.map { char -> Character in
      if char.isLetter || char.isNumber { return char }
      if char == " " || char == "-" || char == "_" { return "-" }
      return "-"
    }
    let collapsed = String(allowed)
      .replacingOccurrences(of: "--+", with: "-", options: .regularExpression)
      .trimmingCharacters(in: CharacterSet(charactersIn: "-"))
    return collapsed.isEmpty ? "page-\(UUID().uuidString.prefix(8))" : collapsed
  }
}

enum MemoryWikiError: Error {
  case databaseNotInitialized
}

/// Feature flag: local wiki search instead of vector embeddings.
enum MemorySearchMode {
  case localWiki
  case vectorEmbeddings

  static var current: MemorySearchMode {
    if CodexAuthService.isActive {
      return .localWiki
    }
    let raw = UserDefaults.standard.string(forKey: "memory_search_mode") ?? "local_wiki"
    return raw == "vector" ? .vectorEmbeddings : .localWiki
  }

  static var usesVectorEmbeddings: Bool {
    current == .vectorEmbeddings
  }
}
