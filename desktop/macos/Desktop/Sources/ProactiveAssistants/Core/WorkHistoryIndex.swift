import Foundation
@preconcurrency import GRDB

struct WorkHistoryVisitRecord: Equatable, Sendable {
  var startedAt: Date
  var endedAt: Date?
  var appName: String
  var title: String
  var handles: [WorkHistoryHandle]
  var bucketID: String?
  var outcome: String

  /// - Parameter now: the instant `minutes_ago` is measured against — the same `generated_at`
  ///   the payload reports, so every visit in one payload is anchored to one clock.
  func jsonObject(clock: (Date) -> String, now: Date) -> [String: Any] {
    // A bare "15:25" cannot be turned into "how long ago" by anything reading this payload, which
    // is how a visit that had not yet ended got reported as hours old. Two ISO-8601 strings per
    // visit fixed that and cost ~50 tokens each — up to 724 on a full 20-visit payload, most of
    // the saving the handles-first path exists to produce. One integer says the same thing in
    // four, and says it more directly than a timestamp the reader has to subtract.
    let minutesAgo = max(0, Int(now.timeIntervalSince(endedAt ?? startedAt) / 60))
    var object: [String: Any] = [
      "start": clock(startedAt),
      "end": clock(endedAt ?? startedAt),
      "minutes_ago": minutesAgo,
      "app": appName,
      "title": title,
      "handles": handles.map { $0.jsonObject() },
      "outcome": outcome,
    ]
    if let bucketID {
      object["bucket_id"] = bucketID
    }
    if endedAt == nil {
      // An open visit is the answer to "what am I in right now". Saying so beats letting a
      // reader infer that it ended the moment it started.
      object["ongoing"] = true
    }
    return object
  }
}

struct WorkstreamBrief: Equatable, Sendable {
  var bucketID: String
  var name: String
  var lastVisitAt: Date?
  var handles: [WorkHistoryHandle]
  var facts: [String]

  func jsonObject() -> [String: Any] {
    var object: [String: Any] = [
      "bucket_id": bucketID,
      "name": name,
      "handles": handles.map { $0.jsonObject() },
      "facts": facts,
    ]
    if let lastVisitAt {
      object["last_visit"] = ISO8601DateFormatter().string(from: lastVisitAt)
    }
    return object
  }

  func recapLine() -> String {
    let handleText =
      handles.first(where: \.isDurable).map(\.value)
      ?? handles.first?.value.split(separator: "\n").last.map(String.init)
      ?? name
    return "- \(name): \(handleText)"
  }
}

enum WorkHistoryIndex {
  static func decodeVisits(from rows: [Row]) -> [WorkHistoryVisitRecord] {
    rows.compactMap { row in
      guard let startedAt = row["startedAt"] as Date?,
        let appName = row["appName"] as String?
      else { return nil }
      let rawKey = row["rawContextKey"] as String? ?? ""
      let title = rawKey.split(separator: "\n", maxSplits: 1).dropFirst().first.map(String.init) ?? rawKey
      return WorkHistoryVisitRecord(
        startedAt: startedAt,
        endedAt: row["endedAt"] as Date?,
        appName: appName,
        title: title,
        handles: WorkHistoryHandle.decodeList(from: row["handlesJson"] as String?),
        bucketID: row["bucketID"] as String?,
        outcome: row["outcome"] as String? ?? "completed"
      )
    }
  }

  static func fetchRecentVisits(
    in db: Database,
    from start: Date,
    to end: Date,
    limit: Int,
    excludedApps: Set<String> = []
  ) throws -> [WorkHistoryVisitRecord] {
    guard try db.tableExists("context_visits") else { return [] }
    let columns = try db.columns(in: "context_visits").map(\.name)
    guard columns.contains("handlesJson") else { return [] }
    let rows = try Row.fetchAll(
      db,
      sql: """
        SELECT startedAt, endedAt, appName, rawContextKey, handlesJson, bucketID, outcome
        FROM context_visits
        WHERE startedAt >= ? AND startedAt <= ?
          AND outcome IN ('completed', 'interrupted', 'active')
        ORDER BY startedAt DESC
        LIMIT ?
        """,
      arguments: [start, end, max(1, limit)])
    let visits = decodeVisits(from: rows)
    if excludedApps.isEmpty { return visits }
    return visits.filter { !excludedApps.contains($0.appName) }
  }

  static func fetchBriefs(in db: Database, limit: Int, excludedApps: Set<String> = []) throws -> [WorkstreamBrief] {
    guard try db.tableExists("context_buckets") else { return [] }
    let buckets = try Row.fetchAll(
      db,
      sql: """
        SELECT id, displayLabel, subjectKind, subjectID, lastVisitedAt
        FROM context_buckets
        ORDER BY COALESCE(lastVisitedAt, updatedAt) DESC
        LIMIT ?
        """,
      arguments: [max(1, limit)])
    return try buckets.compactMap { row -> WorkstreamBrief? in
      guard let id = row["id"] as String? else { return nil }
      if !excludedApps.isEmpty {
        let visitApps = try String.fetchAll(
          db,
          sql: "SELECT DISTINCT appName FROM context_visits WHERE bucketID = ?",
          arguments: [id])
        if !visitApps.isEmpty, visitApps.allSatisfy({ excludedApps.contains($0) }) {
          return nil
        }
      }
      let subjectKind = row["subjectKind"] as String? ?? "context"
      let subjectID = row["subjectID"] as String? ?? id
      let display = row["displayLabel"] as String?
      let name = (display?.isEmpty == false ? display : nil) ?? defaultName(kind: subjectKind, subjectID: subjectID)
      let handles = try handles(forBucket: id, subjectKind: subjectKind, subjectID: subjectID, in: db)
      let facts = try String.fetchAll(
        db,
        sql: """
          SELECT statement FROM bucket_facts
          WHERE bucketID = ? AND validityState = 'validated'
          ORDER BY updatedAt DESC
          LIMIT 5
          """,
        arguments: [id])
      return WorkstreamBrief(
        bucketID: id,
        name: name,
        lastVisitAt: row["lastVisitedAt"] as Date?,
        handles: handles,
        facts: facts
      )
    }
  }

  static func recapSection(from briefs: [WorkstreamBrief]) -> String {
    guard !briefs.isEmpty else { return "" }
    var out = "\n## Workstreams (\(briefs.count))\n"
    for brief in briefs.prefix(8) {
      out += brief.recapLine() + "\n"
    }
    return out
  }

  private static func handles(
    forBucket id: String,
    subjectKind: String,
    subjectID: String,
    in db: Database
  ) throws -> [WorkHistoryHandle] {
    var handles: [WorkHistoryHandle] = []
    if subjectKind == WorkHistoryHandleKind.url.rawValue, let handle = WorkHistoryHandle.url(subjectID) {
      handles.append(handle)
    } else if subjectKind == WorkHistoryHandleKind.file.rawValue, let handle = WorkHistoryHandle.file(subjectID) {
      handles.append(handle)
    }
    if try db.columns(in: "context_visits").map(\.name).contains("handlesJson") {
      let encoded = try String.fetchAll(
        db,
        sql: """
          SELECT handlesJson FROM context_visits
          WHERE bucketID = ? AND handlesJson IS NOT NULL AND handlesJson != '[]'
          ORDER BY startedAt DESC
          LIMIT 5
          """,
        arguments: [id])
      for json in encoded {
        handles.append(contentsOf: WorkHistoryHandle.decodeList(from: json))
      }
    }
    var seen = Set<WorkHistoryHandle>()
    return handles.filter { seen.insert($0).inserted }
  }

  private static func defaultName(kind: String, subjectID: String) -> String {
    if kind == WorkHistoryHandleKind.url.rawValue, let url = URL(string: subjectID) {
      return url.host.map { "\($0)\(url.path)" } ?? subjectID
    }
    if kind == WorkHistoryHandleKind.file.rawValue {
      return URL(fileURLWithPath: subjectID).lastPathComponent
    }
    if let title = subjectID.split(separator: "\n").last, !title.isEmpty {
      return String(title)
    }
    return "Workstream"
  }
}
