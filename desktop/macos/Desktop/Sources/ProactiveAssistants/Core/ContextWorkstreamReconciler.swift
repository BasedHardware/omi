import Foundation
@preconcurrency import GRDB

/// An armed, pre-written notification produced by the background reconciler.
/// Lookup is deterministic SQL; the hot path never asks a model to write one.
struct ContextProactiveCandidate: Equatable, Sendable, FetchableRecord, Decodable {
  let id: String
  let bucketID: String
  let workstreamTag: String?
  let message: String
  let groundingFactIDsJson: String
  let triggerNote: String
  let state: String
  let createdAt: Date
  let expiresAt: Date
  let consumedAt: Date?

  var groundingFactIDs: [String] {
    ContextProactiveCandidate.parseFactIDs(groundingFactIDsJson)
  }

  static func parseFactIDs(_ json: String) -> [String] {
    guard let data = json.data(using: .utf8),
      let ids = try? JSONDecoder().decode([String].self, from: data)
    else { return [] }
    return ids.map { $0.hasPrefix("fact:") ? String($0.dropFirst(5)) : $0 }.filter { !$0.isEmpty }
  }
}

struct ContextWorkstreamEligibleBucket: Equatable, Sendable {
  let bucketID: String
  let factCount: Int
  let newestFactAt: Date
  let tagged: Bool
}

struct ContextWorkstreamBatchFact: Equatable, Sendable {
  let id: String
  let bucketID: String
  let appName: String
  let statement: String
  let notifyWorthiness: Double
  let createdAt: Date
}

/// Deterministic batch ranking and exploration swap. No model.
enum ContextWorkstreamBatchSelection {
  static let minimumFacts = 3
  static let rankedTake = 12
  static let exploreCount = 2
  static let batchCap = 14
  static let factsPerBucket = 5
  static let candidateWorthinessFloor = 0.6
  /// SQL-side cap per bucket before `selectFacts` drops scaffolding and takes
  /// the top `factsPerBucket`. Generous headroom above that final count keeps
  /// selection behavior unchanged for realistic scaffolding ratios, while
  /// bounding how much a single dense bucket can pull into memory each pass.
  static let factFetchCapPerBucket = 20

  static func fetchEligible(in db: Database, now: Date) throws -> [ContextWorkstreamEligibleBucket] {
    try Row.fetchAll(
      db,
      sql: """
        SELECT b.id AS bucketID,
          COUNT(f.id) AS factCount,
          MAX(f.createdAt) AS newestFactAt,
          CASE WHEN EXISTS (
            SELECT 1 FROM bucket_workstreams w WHERE w.bucketID = b.id
          ) THEN 1 ELSE 0 END AS tagged
        FROM context_buckets b
        JOIN bucket_facts f ON f.bucketID = b.id
        WHERE f.validityState = 'validated'
          AND (f.expiresAt IS NULL OR f.expiresAt > ?)
        GROUP BY b.id
        HAVING COUNT(f.id) >= ?
        ORDER BY tagged ASC, factCount DESC, newestFactAt DESC, b.id ASC
        """,
      arguments: [now, minimumFacts]
    ).compactMap { row -> ContextWorkstreamEligibleBucket? in
      guard let bucketID: String = row["bucketID"],
        let newestFactAt: Date = row["newestFactAt"]
      else { return nil }
      return ContextWorkstreamEligibleBucket(
        bucketID: bucketID,
        factCount: row["factCount"] as Int? ?? 0,
        newestFactAt: newestFactAt,
        tagged: (row["tagged"] as Int64? ?? 0) != 0)
    }
  }

  /// Keep the top `rankedTake - exploreCount` by rank, then replace the last
  /// two slots with randomly chosen eligible buckets so the same head of the
  /// ranking is not visited forever. Hard-capped at `batchCap`.
  static func applyExploration(
    rankedIDs: [String],
    pick: ([String], Int) -> [String] = Self.randomPick
  ) -> [String] {
    if rankedIDs.count <= rankedTake {
      return Array(rankedIDs.prefix(batchCap))
    }
    let keepCount = rankedTake - exploreCount
    let keep = Array(rankedIDs.prefix(keepCount))
    let pool = Array(rankedIDs.dropFirst(keepCount))
    let replacements = pick(pool, exploreCount)
    return Array((keep + replacements).prefix(batchCap))
  }

  static func randomPick(_ pool: [String], count: Int) -> [String] {
    guard count > 0, !pool.isEmpty else { return [] }
    var remaining = pool
    var picked: [String] = []
    let n = min(count, remaining.count)
    for _ in 0..<n {
      let index = Int.random(in: 0..<remaining.count)
      picked.append(remaining.remove(at: index))
    }
    return picked
  }

  static func selectFacts(
    _ facts: [ContextWorkstreamBatchFact], limit: Int = Self.factsPerBucket
  ) -> [ContextWorkstreamBatchFact] {
    facts
      .filter { !ContextWorkstreamPooling.isScaffolding($0.statement) }
      .sorted { lhs, rhs in
        if lhs.notifyWorthiness != rhs.notifyWorthiness {
          return lhs.notifyWorthiness > rhs.notifyWorthiness
        }
        if lhs.createdAt != rhs.createdAt { return lhs.createdAt > rhs.createdAt }
        return lhs.id < rhs.id
      }
      .prefix(limit)
      .map { $0 }
  }

  static func fetchFacts(
    bucketIDs: [String], now: Date, in db: Database
  ) throws -> [ContextWorkstreamBatchFact] {
    guard !bucketIDs.isEmpty else { return [] }
    let placeholders = bucketIDs.map { _ in "?" }.joined(separator: ",")
    var arguments: StatementArguments = [now]
    arguments += StatementArguments(bucketIDs)
    arguments += StatementArguments([factFetchCapPerBucket])
    // A dense bucket's full validated-fact corpus is unbounded; only the top
    // `factFetchCapPerBucket` per bucket by worthiness/recency are ever
    // useful to `selectFacts`, so the cap is applied here in SQL instead of
    // materializing everything and discarding most of it in Swift.
    return try Row.fetchAll(
      db,
      sql: """
        SELECT id, bucketID, appName, statement, notifyWorthiness, createdAt FROM (
          SELECT id, bucketID, appName, statement, notifyWorthiness, createdAt,
            ROW_NUMBER() OVER (
              PARTITION BY bucketID ORDER BY notifyWorthiness DESC, createdAt DESC
            ) AS rn
          FROM bucket_facts
          WHERE validityState = 'validated'
            AND (expiresAt IS NULL OR expiresAt > ?)
            AND bucketID IN (\(placeholders))
        )
        WHERE rn <= ?
        ORDER BY notifyWorthiness DESC, createdAt DESC
        """,
      arguments: arguments
    ).compactMap { row -> ContextWorkstreamBatchFact? in
      guard let id: String = row["id"], let bucketID: String = row["bucketID"],
        let statement: String = row["statement"], let createdAt: Date = row["createdAt"]
      else { return nil }
      return ContextWorkstreamBatchFact(
        id: id,
        bucketID: bucketID,
        appName: row["appName"] ?? "",
        statement: statement,
        notifyWorthiness: row["notifyWorthiness"] ?? 0,
        createdAt: createdAt)
    }
  }
}

/// Label acceptance: sanitize, reject generic nouns, require an observed term,
/// require two groups for a brand-new label, cap at six labels, INSERT OR IGNORE.
enum ContextWorkstreamTagging {
  static let maximumLabels = 6
  static let minimumGroupsForNewLabel = 2

  /// Technology and activity nouns that are not project names. A prompt clause
  /// already failed at this; membership here is the gate. Compounds whose every
  /// kebab token is in this set (cloud-meetings, config-management) are also
  /// generic. A mixed label (omi-api) is not: it still names a project.
  static let genericLabels: Set<String> = [
    "admin", "api", "browser", "calendar", "chat", "chats", "cloud", "collection",
    "config", "coordination", "dashboard", "docs", "download", "downloads", "email",
    "emails", "management", "meeting", "meetings", "notification", "notifications",
    "ops", "planning", "release", "releases", "research", "review", "reviews",
    "search", "searches", "setting", "settings", "standup", "standups", "task",
    "tasks", "team", "telecom", "terminal", "testing", "update", "updates",
  ]

  static func isGenericLabel(_ tag: String) -> Bool {
    if genericLabels.contains(tag) { return true }
    let tokens = tag.split(separator: "-").map(String.init).filter { !$0.isEmpty }
    guard !tokens.isEmpty else { return true }
    return tokens.allSatisfy { genericLabels.contains($0) }
  }

  struct Response: Decodable, Equatable {
    struct Workstream: Decodable, Equatable {
      let label: String
      let evidence: String
    }
    struct Assignment: Decodable, Equatable {
      let group: String
      let label: String?
    }
    let workstreams: [Workstream]
    let assignments: [Assignment]
  }

  struct AcceptedAssignment: Equatable {
    let bucketID: String
    let tag: String
  }

  static var schema: [String: Any] {
    [
      "type": "object",
      "properties": [
        "workstreams": [
          "type": "array",
          "items": [
            "type": "object",
            "properties": [
              "label": ["type": "string"],
              "evidence": ["type": "string"],
            ],
            "required": ["label", "evidence"],
            "additionalProperties": false,
          ],
        ],
        "assignments": [
          "type": "array",
          "items": [
            "type": "object",
            "properties": [
              "group": ["type": "string"],
              "label": ["type": ["string", "null"]],
            ],
            "required": ["group", "label"],
            "additionalProperties": false,
          ],
        ],
      ],
      "required": ["workstreams", "assignments"],
      "additionalProperties": false,
    ]
  }

  static func parse(_ content: String) -> Response? {
    guard let data = content.data(using: .utf8) else { return nil }
    return try? JSONDecoder().decode(Response.self, from: data)
  }

  static func resolveGroup(_ group: String, batchIDs: [String]) -> String? {
    let trimmed = group.trimmingCharacters(in: .whitespacesAndNewlines)
    if let match = batchIDs.first(where: { $0 == trimmed }) { return match }
    let upper = trimmed.uppercased()
    if upper.hasPrefix("G"), let index = Int(upper.dropFirst()), index >= 1,
      index <= batchIDs.count
    {
      return batchIDs[index - 1]
    }
    if let index = Int(trimmed), index >= 1, index <= batchIDs.count {
      return batchIDs[index - 1]
    }
    return nil
  }

  static func labelAppearsInObservations(_ tag: String, observations: String) -> Bool {
    // Whole-word membership, not substring containment: an unbounded
    // `contains` would let incidental text (e.g. "cat" inside "concatenate")
    // falsely justify a durable workstream label.
    let haystackWords = Set(
      observations.lowercased()
        .split(whereSeparator: { !$0.isLetter && !$0.isNumber })
        .map(String.init))
    let tokens = tag.split(separator: "-").map(String.init).filter { $0.count >= 2 }
    guard !tokens.isEmpty else { return false }
    return tokens.contains { haystackWords.contains($0) }
  }

  static func acceptedAssignments(
    response: Response,
    batchIDs: [String],
    existingTags: Set<String>,
    observations: String
  ) -> [AcceptedAssignment] {
    var firstLabelByBucket: [(bucketID: String, tag: String)] = []
    var seenBuckets = Set<String>()
    for assignment in response.assignments {
      // Membership is checked (not claimed) here: a null or unsanitizable
      // first assignment for a bucket must not block a later valid one for
      // the same bucket, so `seenBuckets` is only marked once sanitization
      // has actually succeeded.
      guard let bucketID = resolveGroup(assignment.group, batchIDs: batchIDs),
        !seenBuckets.contains(bucketID),
        let tag = ContextWorkstreamTag.sanitize(assignment.label)
      else { continue }
      seenBuckets.insert(bucketID)
      firstLabelByBucket.append((bucketID, tag))
    }
    var counts: [String: Int] = [:]
    for item in firstLabelByBucket { counts[item.tag, default: 0] += 1 }

    func isAllowed(_ tag: String) -> Bool {
      guard !isGenericLabel(tag) else { return false }
      guard labelAppearsInObservations(tag, observations: observations) else { return false }
      if existingTags.contains(tag) { return true }
      return (counts[tag] ?? 0) >= minimumGroupsForNewLabel
    }

    var allowedTags = Set(firstLabelByBucket.map(\.tag).filter(isAllowed))
    if allowedTags.count > maximumLabels {
      let existingFirst = allowedTags.filter { existingTags.contains($0) }
        .sorted()
      let newByCount = allowedTags.filter { !existingTags.contains($0) }
        .sorted { lhs, rhs in
          if counts[lhs, default: 0] != counts[rhs, default: 0] {
            return counts[lhs, default: 0] > counts[rhs, default: 0]
          }
          return lhs < rhs
        }
      allowedTags = Set(
        Array((existingFirst + newByCount).prefix(maximumLabels)))
    }
    return firstLabelByBucket.filter { allowedTags.contains($0.tag) }.map {
      AcceptedAssignment(bucketID: $0.bucketID, tag: $0.tag)
    }
  }

  static func insertAssignment(
    bucketID: String, tag: String, now: Date, in db: Database
  ) throws {
    // The reconciler's batch was selected on a read snapshot. Deterministic GC
    // can delete a bucket before this write runs; inserting against a missing
    // parent is a foreign-key abort that would roll back every other
    // assignment in the same transaction.
    guard try bucketExists(bucketID, in: db) else { return }
    try db.execute(
      sql: """
        INSERT OR IGNORE INTO bucket_workstreams
          (id, bucketID, tag, source, assignedAt)
        VALUES (?, ?, ?, 'reconciler', ?)
        """,
      arguments: [UUID().uuidString.lowercased(), bucketID, tag, now])
  }

  static func bucketExists(_ bucketID: String, in db: Database) throws -> Bool {
    try Bool.fetchOne(
      db, sql: "SELECT EXISTS(SELECT 1 FROM context_buckets WHERE id = ?)", arguments: [bucketID]
    ) ?? false
  }

  static func existingTags(in db: Database) throws -> Set<String> {
    Set(try String.fetchAll(db, sql: "SELECT DISTINCT tag FROM bucket_workstreams"))
  }

  static func tags(for bucketID: String, in db: Database) throws -> [String] {
    try String.fetchAll(
      db,
      sql: "SELECT tag FROM bucket_workstreams WHERE bucketID = ? ORDER BY assignedAt ASC, tag ASC",
      arguments: [bucketID])
  }
}

enum ContextProactiveCandidateWriter {
  static let lifetime: TimeInterval = 12 * 60 * 60

  struct Response: Decodable, Equatable {
    struct Candidate: Decodable, Equatable {
      let bucket: String
      let message: String
      let factIDs: [String]
      let triggerNote: String

      enum CodingKeys: String, CodingKey {
        case bucket, message
        case factIDs = "fact_ids"
        case triggerNote = "trigger_note"
      }
    }
    let candidates: [Candidate]
  }

  static var schema: [String: Any] {
    [
      "type": "object",
      "properties": [
        "candidates": [
          "type": "array",
          "items": [
            "type": "object",
            "properties": [
              "bucket": ["type": "string"],
              "message": ["type": "string"],
              "fact_ids": ["type": "array", "items": ["type": "string"]],
              "trigger_note": ["type": "string"],
            ],
            "required": ["bucket", "message", "fact_ids", "trigger_note"],
            "additionalProperties": false,
          ],
        ]
      ],
      "required": ["candidates"],
      "additionalProperties": false,
    ]
  }

  static func parse(_ content: String) -> Response? {
    guard let data = content.data(using: .utf8) else { return nil }
    return try? JSONDecoder().decode(Response.self, from: data)
  }

  static func validatedFactIDs(
    _ ids: [String], bucketID: String, now: Date, in db: Database
  ) throws -> [String] {
    let normalized = ids.map { $0.hasPrefix("fact:") ? String($0.dropFirst(5)) : $0 }
      .filter { !$0.isEmpty }
    guard !normalized.isEmpty else { return [] }
    var arguments: StatementArguments = [bucketID, now]
    arguments += StatementArguments(normalized)
    let rows = try String.fetchAll(
      db,
      sql: """
        SELECT id FROM bucket_facts
        WHERE bucketID = ? AND validityState = 'validated'
          AND (expiresAt IS NULL OR expiresAt > ?)
          AND id IN (\(normalized.map { _ in "?" }.joined(separator: ",")))
        """,
      arguments: arguments)
    let allowed = Set(rows)
    return normalized.filter { allowed.contains($0) }
  }

  static func hasArmedCandidate(bucketID: String, now: Date, in db: Database) throws -> Bool {
    let armed = try ContextProactiveCandidateLookup.lookupArmed(
      bucketID: bucketID, tags: [], now: now, in: db)
    for candidate in armed {
      let ids = candidate.groundingFactIDs
      guard !ids.isEmpty else { continue }
      let valid = try validatedFactIDs(ids, bucketID: bucketID, now: now, in: db)
      if Set(valid) == Set(ids) { return true }
    }
    return false
  }

  static func insertValidatedCandidates(
    _ proposed: [Response.Candidate],
    groups: [ContextWorkstreamReconcileGroup],
    now: Date,
    in db: Database
  ) throws {
    var seen = Set<String>()
    for candidate in proposed {
      _ = try insertValidatedCandidate(
        candidate, groups: groups, seen: &seen, now: now, in: db)
    }
  }

  /// Validates one model-proposed candidate and, if it is the first valid one
  /// for its bucket in this response, writes it. `seen` is only marked after
  /// every check succeeds, so an invalid earlier proposal cannot shadow a
  /// later valid one for the same bucket.
  @discardableResult
  static func insertValidatedCandidate(
    _ candidate: Response.Candidate,
    groups: [ContextWorkstreamReconcileGroup],
    seen: inout Set<String>,
    now: Date,
    in db: Database
  ) throws -> Bool {
    let groupByID = Dictionary(
      groups.map { ($0.bucketID, $0) }, uniquingKeysWith: { _, last in last })
    let bucketID =
      ContextWorkstreamTagging.resolveGroup(candidate.bucket, batchIDs: groups.map(\.bucketID))
      ?? (groupByID[candidate.bucket] != nil ? candidate.bucket : nil)
    guard let bucketID, !seen.contains(bucketID) else { return false }
    let message = candidate.message.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !message.isEmpty else { return false }
    let cited = candidate.factIDs.map { $0.hasPrefix("fact:") ? String($0.dropFirst(5)) : $0 }
      .filter { !$0.isEmpty }
    let factIDs = try validatedFactIDs(cited, bucketID: bucketID, now: now, in: db)
    guard !cited.isEmpty, Set(factIDs) == Set(cited) else { return false }
    let trigger = candidate.triggerNote.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !trigger.isEmpty else { return false }
    seen.insert(bucketID)
    try insertArmed(
      bucketID: bucketID,
      workstreamTag: groupByID[bucketID]?.workstreamTag,
      message: String(message.prefix(600)),
      factIDs: factIDs,
      triggerNote: String(trigger.prefix(300)),
      now: now,
      in: db)
    return true
  }

  static func insertArmed(
    bucketID: String,
    workstreamTag: String?,
    message: String,
    factIDs: [String],
    triggerNote: String,
    now: Date,
    in db: Database
  ) throws {
    guard try ContextWorkstreamTagging.bucketExists(bucketID, in: db) else { return }
    let data = try JSONEncoder().encode(factIDs)
    let json = String(data: data, encoding: .utf8) ?? "[]"
    try db.execute(
      sql: """
        INSERT INTO proactive_candidates
          (id, bucketID, workstreamTag, message, groundingFactIDsJson, triggerNote,
           state, createdAt, expiresAt)
        VALUES (?, ?, ?, ?, ?, ?, 'armed', ?, ?)
        """,
      arguments: [
        UUID().uuidString.lowercased(), bucketID, workstreamTag, message, json,
        triggerNote, now, now.addingTimeInterval(lifetime),
      ])
  }
}

/// Hot-path lookup, duplicate skip, and the small yes/no gate.
enum ContextProactiveCandidateLookup {
  static func lookupArmed(
    bucketID: String, tags: [String], now: Date, in db: Database
  ) throws -> [ContextProactiveCandidate] {
    if tags.isEmpty {
      return try ContextProactiveCandidate.fetchAll(
        db,
        sql: """
          SELECT id, bucketID, workstreamTag, message, groundingFactIDsJson, triggerNote,
                 state, createdAt, expiresAt, consumedAt
          FROM proactive_candidates
          WHERE state = 'armed' AND expiresAt > ? AND bucketID = ?
          ORDER BY createdAt DESC
          """,
        arguments: [now, bucketID])
    }
    let placeholders = tags.map { _ in "?" }.joined(separator: ",")
    var arguments: StatementArguments = [now, bucketID]
    arguments += StatementArguments(tags)
    arguments += StatementArguments([bucketID])
    return try ContextProactiveCandidate.fetchAll(
      db,
      sql: """
        SELECT id, bucketID, workstreamTag, message, groundingFactIDsJson, triggerNote,
               state, createdAt, expiresAt, consumedAt
        FROM proactive_candidates
        WHERE state = 'armed' AND expiresAt > ?
          AND (
            bucketID = ?
            OR (workstreamTag IS NOT NULL AND workstreamTag IN (\(placeholders)))
          )
        ORDER BY CASE WHEN bucketID = ? THEN 0 ELSE 1 END, createdAt DESC
        """,
      arguments: arguments)
  }

  static func firstDeliverable(
    candidates: [ContextProactiveCandidate],
    recentMessages: [String]
  ) -> ContextProactiveCandidate? {
    candidates.first { candidate in
      let message = candidate.message.trimmingCharacters(in: .whitespacesAndNewlines)
      guard !message.isEmpty else { return false }
      return !SuggestionDeduplication.isDuplicate(message, of: recentMessages)
    }
  }

  @discardableResult
  static func consume(id: String, now: Date, in db: Database) throws -> Bool {
    try db.execute(
      sql: """
        UPDATE proactive_candidates
        SET state = 'consumed', consumedAt = ?
        WHERE id = ? AND state = 'armed' AND expiresAt > ?
        """,
      arguments: [now, id, now])
    return db.changesCount > 0
  }

  /// Retires a gated-down candidate immediately by collapsing its expiry,
  /// rather than leaving it armed to be re-selected — and re-billed for
  /// another paid gate call — on every later visit until it naturally
  /// expires.
  @discardableResult
  static func decline(id: String, now: Date, in db: Database) throws -> Bool {
    try db.execute(
      sql: """
        UPDATE proactive_candidates
        SET expiresAt = ?
        WHERE id = ? AND state = 'armed' AND expiresAt > ?
        """,
      arguments: [now, id, now])
    return db.changesCount > 0
  }

  /// Re-arms a candidate that was claimed for presentation but never shown.
  /// `onDropped` is the only caller: it fires for sync refusals and for a
  /// queued card that is later evicted, and it does not fire after
  /// `onPresented` (those callbacks are consumed at present time).
  @discardableResult
  static func restore(id: String, now: Date, in db: Database) throws -> Bool {
    try db.execute(
      sql: """
        UPDATE proactive_candidates
        SET state = 'armed', consumedAt = NULL
        WHERE id = ? AND state = 'consumed' AND expiresAt > ?
        """,
      arguments: [id, now])
    return db.changesCount > 0
  }

  /// Sibling-bucket deliveries for durable workstream assignments. Lookup can
  /// return a candidate written against another bucket that shares a tag, so
  /// dedup must see those buckets' delivered messages too — `bucket_facts.workstreamTag`
  /// is dormant and cannot be this source.
  static func recentDeliveredForAssignedTags(
    tags: [String],
    excludingBucketID: String,
    now: Date,
    limit: Int,
    in db: Database
  ) throws -> [ContextBucketRecentDelivery] {
    let cap = max(0, min(limit, ContextBucketRecentDelivery.promptCap))
    guard !tags.isEmpty, cap > 0 else { return [] }
    let placeholders = tags.map { _ in "?" }.joined(separator: ",")
    var arguments: StatementArguments = [excludingBucketID]
    arguments += StatementArguments(tags)
    // Annotated: a mixed [Date, Int] literal is ambiguous to the type checker.
    let cutoff = now.addingTimeInterval(-ContextBucketRecentDelivery.memoryLookback)
    arguments += StatementArguments([cutoff, cap] as [any DatabaseValueConvertible])
    return try ContextBucketRecentDelivery.fetchAll(
      db,
      sql: """
        SELECT decisionType, message, deliveredAt FROM proactive_deliveries
        WHERE bucketID <> ?
          AND bucketID IN (
            SELECT DISTINCT bucketID FROM bucket_workstreams WHERE tag IN (\(placeholders))
          )
          AND lifecycleState = 'delivered'
          AND deliveredAt IS NOT NULL
          AND deliveredAt >= ?
        ORDER BY deliveredAt DESC
        LIMIT ?
        """,
      arguments: arguments)
  }

  static func expireStale(now: Date, in db: Database) throws {
    try db.execute(
      sql: """
        UPDATE proactive_candidates SET state = 'expired'
        WHERE state = 'armed' AND expiresAt <= ?
        """,
      arguments: [now])
  }
}

enum ContextProactiveCandidateGate {
  struct Decision: Decodable, Equatable {
    let show: Bool
    let reason: String
  }

  static var schema: [String: Any] {
    [
      "type": "object",
      "properties": [
        "show": ["type": "boolean"],
        "reason": ["type": "string"],
      ],
      "required": ["show", "reason"],
      "additionalProperties": false,
    ]
  }

  static func parse(_ content: String) -> Decision? {
    guard let data = content.data(using: .utf8) else { return nil }
    return try? JSONDecoder().decode(Decision.self, from: data)
  }

  static func prompt(
    message: String,
    validatedFacts: [String],
    recentDeliveries: [ContextBucketRecentDelivery],
    timeZone: TimeZone = .current
  ) -> String {
    let facts =
      validatedFacts.isEmpty
      ? "(none)" : validatedFacts.map { String($0.prefix(400)) }.joined(separator: "\n")
    let recent =
      ContextProactivityPromptBuilder.recentDeliveriesSection(recentDeliveries, timeZone: timeZone)
      ?? "== RECENTLY DELIVERED FOR THIS BUCKET ==\n(none)"
    return """
      \(ScreenDerivedContent.untrustedPreamble)
      You are a yes/no delivery gate for a pre-written notification. Do not rewrite the
      message. Set show to true only if the candidate is accurate for what is on screen
      now, adds something not already visible, and repeats nothing in the recent list.
      Answering false is common and correct.

      == CANDIDATE ==
      \(String(message.prefix(600)))

      == VALIDATED FACTS ON THIS VISIT ==
      \(facts)

      \(recent)
      """
  }
}

/// Background workstream tagging and candidate pre-writing. Never on the
/// delivery path. Cadence is fifteen minutes while the app is running and the
/// feature flag is on; a pass with no new validated facts is a no-op.
actor ContextWorkstreamReconciler {
  static let shared = ContextWorkstreamReconciler()
  /// Freshness on the delivery path is served by the fifteen-minute
  /// recent-context channel, not by how often this background pass runs, so the
  /// cadence is set by what durable workstream labels actually need. Fifteen
  /// minutes still sits inside the gateway's thirty-minute cache TTL, which is
  /// what lets consecutive passes share an instruction prefix.
  static let interval: TimeInterval = 15 * 60

  private let client: ProactiveLaneClient
  private let store: ContextBucketStore
  private var timer: Task<Void, Never>?
  private var isRunning = false
  private var lastPassAt: Date?

  init(client: ProactiveLaneClient = .shared, store: ContextBucketStore = .shared) {
    self.client = client
    self.store = store
  }

  func start() {
    guard !isRunning else { return }
    isRunning = true
    log("ContextWorkstreamReconciler: started")
    timer = Task { [weak self] in
      guard let self else { return }
      while !Task.isCancelled {
        await self.runPass()
        try? await Task.sleep(nanoseconds: UInt64(Self.interval * 1_000_000_000))
      }
    }
  }

  func stop() {
    timer?.cancel()
    timer = nil
    isRunning = false
    log("ContextWorkstreamReconciler: stopped")
  }

  func runPass(now: Date = Date()) async {
    let enabled = await MainActor.run { ContextBucketsFeature.isProactiveCandidatesEnabled }
    guard enabled else { return }
    guard let authorizationSnapshot = RuntimeOwnerIdentity.captureAuthorizationSnapshot() else {
      return
    }
    do {
      let outcome = try await store.runWorkstreamReconcilePass(
        lastPassAt: lastPassAt, now: now)
      switch outcome {
      case .skippedNoNewFacts, .skippedEmptyBatch:
        return
      case .ready(let batch):
        // Both stages must fully succeed before the pass is recorded done:
        // a malformed model response or lost authorization must not advance
        // `lastPassAt`, or the ten-minute loop would silently stop retrying
        // this batch.
        guard
          let taggedBatch = try await performTagging(
            batch: batch, authorizationSnapshot: authorizationSnapshot, now: now)
        else { return }
        guard
          try await performCandidateWriting(
            batch: taggedBatch, authorizationSnapshot: authorizationSnapshot, now: now)
        else { return }
        lastPassAt = now
      }
    } catch {
      log("ContextWorkstreamReconciler: pass failed: \(error.localizedDescription)")
    }
  }

  /// Runs tagging and, on success, returns the batch with each newly-tagged
  /// group's `workstreamTag` refreshed to this pass's assignment — so
  /// `performCandidateWriting` (which runs right after, in the same pass)
  /// sees a bucket's brand-new tag instead of the pre-tagging snapshot, and
  /// the candidate it writes is visible to that tag's sibling buckets.
  /// Returns nil only on genuine failure (malformed model output or lost
  /// authorization); an empty-groups batch or a pass with nothing accepted is
  /// success with the batch unchanged.
  private func performTagging(
    batch: ContextWorkstreamReconcileBatch,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot,
    now: Date
  ) async throws -> ContextWorkstreamReconcileBatch? {
    guard !batch.groups.isEmpty else { return batch }
    guard RuntimeOwnerIdentity.isAuthorizationCurrent(authorizationSnapshot) else { return nil }
    let result = try await client.complete(
      operation: ModelQoS.Proactivity.reasoningOperation,
      prompt: Self.taggingInstructions,
      uncachedPrompt: Self.taggingData(batch: batch),
      jsonSchema: ContextWorkstreamTagging.schema,
      cacheKey: ContextPromptCacheKey.reconcilerTagging,
      maxCompletionTokens: 800,
      authorizationSnapshot: authorizationSnapshot)
    guard let parsed = ContextWorkstreamTagging.parse(result.content) else {
      log("ContextWorkstreamReconciler: tagging response malformed")
      return nil
    }
    let accepted = ContextWorkstreamTagging.acceptedAssignments(
      response: parsed,
      batchIDs: batch.groups.map(\.bucketID),
      existingTags: batch.existingTags,
      observations: batch.observations)
    try await store.insertWorkstreamAssignments(accepted, now: now)
    guard !accepted.isEmpty else { return batch }
    let newlyTagged = Dictionary(
      accepted.map { ($0.bucketID, $0.tag) }, uniquingKeysWith: { first, _ in first })
    let refreshedGroups = batch.groups.map { group -> ContextWorkstreamReconcileGroup in
      guard group.workstreamTag == nil, let tag = newlyTagged[group.bucketID] else { return group }
      return ContextWorkstreamReconcileGroup(
        bucketID: group.bucketID, facts: group.facts, needsCandidate: group.needsCandidate,
        workstreamTag: tag)
    }
    return ContextWorkstreamReconcileBatch(groups: refreshedGroups, existingTags: batch.existingTags)
  }

  /// Returns whether the stage succeeded: true on a no-op (nothing eligible)
  /// or a completed write, false on malformed model output or lost
  /// authorization so `runPass` does not advance `lastPassAt`.
  private func performCandidateWriting(
    batch: ContextWorkstreamReconcileBatch,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot,
    now: Date
  ) async throws -> Bool {
    let eligible = batch.groups.filter(\.needsCandidate)
    guard !eligible.isEmpty else { return true }
    guard RuntimeOwnerIdentity.isAuthorizationCurrent(authorizationSnapshot) else { return false }
    let result = try await client.complete(
      operation: ModelQoS.Proactivity.reasoningOperation,
      prompt: Self.candidateInstructions,
      uncachedPrompt: Self.candidateData(groups: eligible),
      jsonSchema: ContextProactiveCandidateWriter.schema,
      cacheKey: ContextPromptCacheKey.reconcilerCandidates,
      maxCompletionTokens: 800,
      authorizationSnapshot: authorizationSnapshot)
    guard let parsed = ContextProactiveCandidateWriter.parse(result.content) else {
      log("ContextWorkstreamReconciler: candidate response malformed")
      return false
    }
    try await store.insertArmedCandidates(parsed.candidates, groups: eligible, now: now)
    return true
  }

  /// Byte-identical on every pass, so it is the only part of the tagging call
  /// worth sending as the cached prefix. Kept as one constant rather than
  /// interpolated per pass precisely so it cannot drift.
  static let taggingInstructions = """
    \(ScreenDerivedContent.untrustedPreamble)
    Assign these observation groups to durable workstream labels.

    A workstream is an ongoing project, product, or goal that spans multiple
    applications and persists over days or weeks. Name it after the thing being
    worked on — a product, repository, company, customer, or person — never after
    an activity, a tool, or the app the observations were seen in.

    Prefer an existing label from the vocabulary when one fits. Propose at most
    six labels in total. Propose a NEW label only when at least two groups in this
    batch support it. Every label must use a term that actually appears in the
    observations. Assign each group to one label or to null; null is correct and
    expected for many groups. Do not invent a workstream to cover leftovers.
    """

  /// The per-pass half: vocabulary and observation groups. Sits below the
  /// instructions, and therefore below `untrustedPreamble`, so the captured
  /// statements it quotes stay framed as untrusted data.
  static func taggingData(batch: ContextWorkstreamReconcileBatch) -> String {
    let vocabulary =
      batch.existingTags.sorted().isEmpty
      ? "(none yet)" : batch.existingTags.sorted().map { "- \($0)" }.joined(separator: "\n")
    let groups = batch.groups.enumerated().map { index, group in
      let facts = group.facts.map { "- \($0.statement)" }.joined(separator: "\n")
      return """
        == GROUP G\(index + 1) (id: \(group.bucketID)) ==
        Apps: \(Set(group.facts.map(\.appName)).sorted().joined(separator: ", "))
        \(facts)
        """
    }.joined(separator: "\n\n")
    return """
      == CURRENT WORKSTREAM VOCABULARY ==
      \(vocabulary)

      \(groups)
      """
  }

  /// The whole tagging prompt, as the model sees it once the gateway
  /// concatenates the cached and uncached blocks.
  static func taggingPrompt(batch: ContextWorkstreamReconcileBatch) -> String {
    taggingInstructions + "\n\n" + taggingData(batch: batch)
  }

  /// Distinct instructions from tagging, hence its own key: two prompt shapes
  /// under one key would only ever evict each other.
  static let candidateInstructions = """
    \(ScreenDerivedContent.untrustedPreamble)
    For each bucket below, write at most one short notification the user would find
    worth an interruption, or omit the bucket. Ground it in the supplied fact ids
    and add a one-line trigger_note describing when it should fire.

    Do not restate what is already visible on the user's screen. Speak only when
    you add something they cannot currently see: a commitment, a deadline, a
    conflict, or a connection to other work. Must add one of those; otherwise omit
    the bucket.
    """

  static func candidateData(groups: [ContextWorkstreamReconcileGroup]) -> String {
    groups.enumerated().map { index, group in
      let facts = group.facts.map { fact in
        "- fact:\(fact.id) w=\(fact.notifyWorthiness) \(fact.statement)"
      }.joined(separator: "\n")
      return """
        == BUCKET \(group.bucketID) (G\(index + 1)) ==
        \(facts)
        """
    }.joined(separator: "\n\n")
  }

  static func candidatePrompt(groups: [ContextWorkstreamReconcileGroup]) -> String {
    candidateInstructions + "\n\n" + candidateData(groups: groups)
  }
}

struct ContextWorkstreamReconcileGroup: Equatable, Sendable {
  let bucketID: String
  let facts: [ContextWorkstreamBatchFact]
  let needsCandidate: Bool
  let workstreamTag: String?
}

struct ContextWorkstreamReconcileBatch: Equatable, Sendable {
  let groups: [ContextWorkstreamReconcileGroup]
  let existingTags: Set<String>
  var observations: String {
    groups.flatMap(\.facts).map(\.statement).joined(separator: "\n")
  }
}

enum ContextWorkstreamReconcileOutcome: Equatable {
  case skippedNoNewFacts
  case skippedEmptyBatch
  case ready(ContextWorkstreamReconcileBatch)
}
