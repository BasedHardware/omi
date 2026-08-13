import Foundation
@preconcurrency import GRDB

struct BucketExtraction: Codable, Equatable, Sendable {
  struct Fact: Codable, Equatable, Sendable {
    let statement: String
    let identifiers: [String]
    let evidenceText: String
    let evidenceRefs: [String]
    let confidence: Double
    let notifyWorthiness: Double

    enum CodingKeys: String, CodingKey {
      case statement, identifiers, confidence
      case evidenceText = "evidence_text"
      case evidenceRefs = "evidence_refs"
      case notifyWorthiness = "notify_worthiness"
    }
  }

  let narrative: String
  let facts: [Fact]
}

enum BucketFactValidity: String {
  case proposed, validated, rejected, superseded, expired
  case needsReview = "needs_review"
}
enum BucketFactDisposition: String {
  case none
  case candidatePending = "candidate_pending"
  case taskCreated = "task_created"
  case updateProposed = "update_proposed"
}

enum BucketFactValidator {
  struct ExistingFactIdentity: Equatable, Sendable {
    let statement: String
    let canonicalIdentifierSetKey: String?

    init(statement: String, identifiers: [String]) {
      self.statement = statement
      canonicalIdentifierSetKey = BucketFactValidator.canonicalIdentifierSetKey(identifiers)
    }
  }

  static func resolvableEvidenceRefs(_ refs: [String], allowed: Set<String>) -> [String] {
    refs.map { String($0.prefix(200)) }.filter { allowed.contains($0) }
  }

  /// Shadow-only identity candidate for measuring paraphrase repetition. This
  /// is intentionally not used for validity, suppression, or candidate writes:
  /// an identifier can name a subject while its status or claim changes.
  static func canonicalIdentifierSetKey(_ identifiers: [String]) -> String? {
    let normalized = identifiers.compactMap { identifier -> String? in
      let trimmed = identifier.trimmingCharacters(in: .whitespacesAndNewlines)
      guard !trimmed.isEmpty else { return nil }
      let collapsed = trimmed.split(whereSeparator: { $0.isWhitespace }).joined(separator: " ")
      guard !collapsed.isEmpty else { return nil }
      return collapsed.precomposedStringWithCanonicalMapping.lowercased()
    }
    let unique = Set(normalized)
    guard !unique.isEmpty else { return nil }
    let sorted = unique.sorted()
    guard let encoded = try? JSONEncoder().encode(sorted) else { return nil }
    return String(data: encoded, encoding: .utf8)
  }

  static func hasParaphraseMatch(
    statement: String,
    identifiers: [String],
    existingFacts: [ExistingFactIdentity]
  ) -> Bool {
    guard let identityKey = canonicalIdentifierSetKey(identifiers) else { return false }
    return existingFacts.contains { existing in
      existing.statement != statement
        && existing.canonicalIdentifierSetKey == identityKey
    }
  }

  static func validity(
    identifiers: [String], evidenceText: String, evidenceRefs: [String], duplicate: Bool
  ) -> BucketFactValidity {
    if duplicate { return .superseded }
    let hasIdentifier = identifiers.contains {
      !$0.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }
    let evidenceResolves =
      !evidenceText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
      && !evidenceRefs.isEmpty
    return hasIdentifier && evidenceResolves ? .validated : .needsReview
  }
}

enum ContextBucketPromptAssembler {
  static let injectionTokenBudget = 5_000
  static let ambientTailCompactionThreshold = 3_500
  static let frozenRankedByteBudget = 6_000

  static func assemble(_ snapshot: ContextBucketSnapshot) -> Data {
    var data = Data(("== BUCKET HEADER ==\n" + snapshot.header + "\n== FROZEN RANKED CONTEXT ==\n").utf8)
    // This exact byte segment is the stable cache prefix. Never decode/re-encode it.
    data.append(snapshot.frozenRankedSegment)
    let totalByteBudget = injectionTokenBudget * 4
    let facts =
      snapshot.validatedFacts.isEmpty
      ? "" : "\n== VALIDATED FACTS ==\n\(snapshot.validatedFacts.joined(separator: "\n"))"
    let factReservation = min(8_000, max(0, totalByteBudget - data.count))
    let tailBudget = max(0, totalByteBudget - data.count - factReservation)
    data.append(
      utf8Prefix(
        "\n== RECENT TAIL ==\n\(snapshot.tail.joined(separator: "\n"))",
        maxBytes: tailBudget))
    if !snapshot.validatedFacts.isEmpty {
      data.append(utf8Prefix(facts, maxBytes: max(0, totalByteBudget - data.count)))
    }
    return data
  }

  static func estimatedTokens(_ text: String) -> Int {
    max(1, Int(ceil(Double(text.utf8.count) / 4.0)))
  }

  private static func utf8Prefix(_ value: String, maxBytes: Int) -> Data {
    guard maxBytes > 0 else { return Data() }
    var result = Data()
    for scalar in value.unicodeScalars {
      let bytes = Data(String(scalar).utf8)
      guard result.count + bytes.count <= maxBytes else { break }
      result.append(bytes)
    }
    return result
  }
}

struct ContextDirectorTaskContext: Equatable, Sendable {
  static let maximumDescriptionLength = 600

  let description: String
  let dueAt: Date?

  init(description: String, dueAt: Date?) {
    self.description = String(description.prefix(Self.maximumDescriptionLength))
    self.dueAt = dueAt
  }
}

enum ContextProactivityPromptBuilder {
  static func extractionPrompt(frame: CapturedFrame, fence: ContextVisitFence) -> String {
    let evidenceRef = frame.screenshotId.map { "screenshot:\($0)" } ?? "visit:\(fence.visitID)"
    return extractionPrompt(appName: frame.appName, windowTitle: frame.windowTitle, evidenceRef: evidenceRef)
  }

  static func extractionPrompt(appName: String, windowTitle: String?, evidenceRef: String) -> String {
    """
    \(ScreenDerivedContent.untrustedPreamble)
    Produce a 150-400 token ambient narrative and discrete factual records. Facts are
    proposals; include an identifier, surviving evidence text, and evidence ref for each.
    App: \(appName)
    Window: \(windowTitle ?? "")
    Evidence ref: \(evidenceRef)
    """
  }

  static func directorPrompt(
    snapshot: ContextBucketSnapshot,
    tasks: [ContextDirectorTaskContext],
    frame: CapturedFrame
  ) -> String {
    "\(directorStablePrompt(snapshot: snapshot))\n\n\(directorVolatilePrompt(tasks: tasks, frame: frame))"
  }

  static func directorStablePrompt(snapshot: ContextBucketSnapshot) -> String {
    let stableBucket = String(data: ContextBucketPromptAssembler.assemble(snapshot), encoding: .utf8) ?? ""
    return """
      \(ScreenDerivedContent.untrustedPreamble)
      Decide whether interrupting now adds concrete value. Return silence unless the validated
      facts support a specific, timely action. Use only supplied bucket-entry refs.
      Use resurface or suggest for an actionable open task supplied below. Entries marked
      reference-only are identity context: do not notify about or recreate them yet. Use
      task_candidate only for a new validated commitment absent from the supplied task list.

      \(stableBucket)
      """
  }

  static func directorVolatilePrompt(
    tasks: [ContextDirectorTaskContext],
    frame: CapturedFrame
  ) -> String {
    let actionableCutoff = frame.captureTime.addingTimeInterval(
      ContextDirectorTaskSelection.futureHorizon)
    let taskLines: [String] = tasks.prefix(20).map { task -> String in
      guard let dueAt = task.dueAt else { return "- \(task.description)" }
      if dueAt > actionableCutoff {
        return
          "- \(task.description)\n  Due at (UTC): \(utcTimestamp(dueAt))\n  Reference only: already exists; do not resurface or create it yet."
      }
      return "- \(task.description)\n  Due at (UTC): \(utcTimestamp(dueAt))"
    }
    let taskContext = taskLines.joined(separator: "\n")
    return """
      == OPEN OR OVERDUE TASKS ==
      \(taskContext)

      == CURRENT FRAME METADATA ==
      App: \(frame.appName)
      Window: \(frame.windowTitle ?? "")
      Captured at (UTC): \(utcTimestamp(frame.captureTime))
      """
  }

  private static func utcTimestamp(_ date: Date) -> String {
    let formatter = ISO8601DateFormatter()
    formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
    formatter.timeZone = TimeZone(secondsFromGMT: 0)
    return formatter.string(from: date)
  }
}

enum ContextBucketCompactionPolicy {
  static let retainedTailCount = 5

  static func shouldCompact(uncompressedCount: Int) -> Bool {
    // Snapshot reads retain only the newest tail. Compact as soon as an older
    // entry would fall outside that read window, even when narratives are
    // short, so context cannot disappear between the tail and frozen segment.
    return uncompressedCount > retainedTailCount
  }
}

extension ContextBucketStore {
  func writeExtraction(
    _ extraction: BucketExtraction,
    for fence: ContextVisitFence,
    appName: String,
    rawContextKey: String,
    normalizedContextKey: String,
    now: Date = Date()
  ) async throws -> Int64? {
    guard let bucketID = fence.bucketID else { return nil }
    let pool = try await poolForRollup(fence)
    let evidenceEncoder = JSONEncoder()
    let safeNarrative = String(extraction.narrative.prefix(2_400))
    let result: (versionID: Int64, paraphraseObserved: Bool) = try await pool.write { db in
      guard
        let visit = try Row.fetchOne(
          db,
          sql: """
            SELECT lastScreenshotID FROM context_visits
            WHERE id = ? AND contextGeneration = ? AND poolEpoch = ? AND outcome = 'completed'
            """,
          arguments: [fence.visitID, fence.contextGeneration, fence.poolEpoch])
      else { throw ContextBucketStoreError.staleFence }

      var allowedEvidenceRefs: Set<String> = ["visit:\(fence.visitID)"]
      if let screenshotID: Int64 = visit["lastScreenshotID"] {
        allowedEvidenceRefs.insert("screenshot:\(screenshotID)")
      }

      let entryID = UUID().uuidString.lowercased()
      let entryRefs = Array(
        extraction.facts.prefix(20)
          .flatMap { BucketFactValidator.resolvableEvidenceRefs($0.evidenceRefs, allowed: allowedEvidenceRefs) }
          .prefix(40))
      try db.execute(
        sql: """
          INSERT INTO bucket_entries
            (id, bucketID, visitID, appName, rawContextKey, normalizedContextKey,
             narrative, evidenceRefsJson, tokenCount, createdAt)
          VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
          """,
        arguments: [
          entryID, bucketID, fence.visitID, appName, rawContextKey, normalizedContextKey,
          safeNarrative,
          String(data: try evidenceEncoder.encode(entryRefs), encoding: .utf8) ?? "[]",
          ContextBucketPromptAssembler.estimatedTokens(safeNarrative), now,
        ])

      var maximumWorthiness = 0.0
      var paraphraseObserved = false
      var existingFactIdentities = try Row.fetchAll(
        db,
        sql: """
          SELECT statement, identifiersJson FROM bucket_facts
          WHERE bucketID = ? AND validityState = 'validated'
            AND (expiresAt IS NULL OR expiresAt > ?)
          ORDER BY id DESC LIMIT 250
          """,
        arguments: [bucketID, now]
      ).compactMap { row -> BucketFactValidator.ExistingFactIdentity? in
        guard
          let existingStatement = row["statement"] as String?,
          let encodedIdentifiers = row["identifiersJson"] as String?,
          let data = encodedIdentifiers.data(using: .utf8),
          let existingIdentifiers = try? JSONDecoder().decode([String].self, from: data)
        else { return nil }
        return BucketFactValidator.ExistingFactIdentity(
          statement: existingStatement, identifiers: existingIdentifiers)
      }
      for fact in extraction.facts.prefix(20) {
        let statement = String(fact.statement.prefix(500))
        let evidenceText = String(fact.evidenceText.prefix(1_000))
        let evidenceRefs = BucketFactValidator.resolvableEvidenceRefs(
          Array(fact.evidenceRefs.prefix(10)), allowed: allowedEvidenceRefs)
        let identifiers = fact.identifiers.prefix(8).map {
          String($0.prefix(200)).trimmingCharacters(in: .whitespacesAndNewlines)
        }
        .filter { !$0.isEmpty }
        paraphraseObserved =
          paraphraseObserved
          || BucketFactValidator.hasParaphraseMatch(
            statement: statement, identifiers: identifiers, existingFacts: existingFactIdentities)
        let duplicate =
          try Bool.fetchOne(
            db,
            sql: "SELECT EXISTS(SELECT 1 FROM bucket_facts WHERE bucketID = ? AND statement = ?)",
            arguments: [bucketID, statement]) ?? false
        let validity = BucketFactValidator.validity(
          identifiers: identifiers,
          evidenceText: evidenceText,
          evidenceRefs: evidenceRefs,
          duplicate: duplicate)
        let worthiness = validity == .validated ? min(max(fact.notifyWorthiness, 0), 1) : 0
        maximumWorthiness = max(maximumWorthiness, worthiness)
        try db.execute(
          sql: """
            INSERT INTO bucket_facts
              (id, bucketID, entryID, appName, statement, identifiersJson, evidenceText,
               evidenceRefsJson, validityState, dispositionState, confidence,
               notifyWorthiness, createdAt, updatedAt)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'none', ?, ?, ?, ?)
            """,
          arguments: [
            UUID().uuidString.lowercased(), bucketID, entryID, appName, statement,
            String(data: try evidenceEncoder.encode(identifiers), encoding: .utf8) ?? "[]",
            evidenceText,
            String(data: try evidenceEncoder.encode(evidenceRefs), encoding: .utf8) ?? "[]",
            validity.rawValue, min(max(fact.confidence, 0), 1), worthiness, now, now,
          ])
        if validity == .validated {
          existingFactIdentities.append(
            BucketFactValidator.ExistingFactIdentity(statement: statement, identifiers: identifiers))
        }
      }
      try db.execute(
        sql: "UPDATE context_buckets SET notifyWorthiness = MAX(notifyWorthiness, ?), updatedAt = ? WHERE id = ?",
        arguments: [maximumWorthiness, now, bucketID])
      let versionID = try Self.publishVersion(in: db, bucketID: bucketID, now: now)
      try db.execute(
        sql: "UPDATE bucket_entries SET bucketVersionID = ? WHERE id = ?",
        arguments: [versionID, entryID])
      return (versionID: versionID, paraphraseObserved: paraphraseObserved)
    }
    if result.paraphraseObserved {
      await ContextProactivityTelemetry.recordFactIdentityShadow()
    }
    return result.versionID
  }

  func purgeExcludedApp(_ appName: String, now: Date = Date()) async throws -> Set<String> {
    let (pool, _) = await RewindDatabase.shared.getDatabaseQueueWithGeneration()
    guard let pool else { throw ContextBucketStoreError.databaseUnavailable }

    // A chunk is time-based rather than app-based, so privacy-first cleanup may
    // discard allowed frames sharing the same file.  Capture exclusion is set
    // synchronously by the caller; cancel only a writer whose current path is
    // known to contain an excluded row, avoiding unrelated chunk rotation.
    let existingArtifacts = try await pool.read { db in
      try ContextBucketPurger.artifacts(appName: appName, in: db)
    }
    if let activeChunk = await VideoChunkEncoder.shared.currentChunkPath,
      existingArtifacts.videoChunkPaths.contains(activeChunk)
    {
      switch await VideoChunkEncoder.shared.cancel() {
      case .markerWriteFailed:
        throw ContextBucketStoreError.purgeFailed
      case .markerRecorded, .noActiveChunk:
        break
      }
    }
    // Remove the bytes before deleting their database rows.  If storage is
    // temporarily unavailable, the rows remain discoverable and the durable
    // app marker retries this same artifact set on the next launch.
    try await RewindStorage.shared.deleteScreenshots(relativePaths: existingArtifacts.imagePaths)
    try await RewindStorage.shared.deleteVideoChunks(relativePaths: existingArtifacts.videoChunkPaths)

    let result = try await pool.write { db in
      let result = try ContextBucketPurger.deleteWithArtifacts(appName: appName, in: db, now: now)
      for bucketID in result.affectedBucketIDs {
        _ = try Self.publishVersion(in: db, bucketID: bucketID, now: now)
      }
      return result
    }
    // The transaction also removes every row sharing a privacy-deleted chunk,
    // so no surviving screenshot row can reference the removed file.
    return result.affectedBucketIDs
  }

  private func poolForRollup(_ fence: ContextVisitFence) async throws -> DatabasePool {
    let (pool, generation) = await RewindDatabase.shared.getDatabaseQueueWithGeneration()
    guard let pool, generation == fence.poolEpoch else { throw ContextBucketStoreError.staleFence }
    return pool
  }

  private static func publishVersion(in db: Database, bucketID: String, now: Date) throws -> Int64 {
    let previous = try Row.fetchOne(
      db,
      sql: """
          SELECT version, frozenRankedSegment FROM bucket_versions
          WHERE bucketID = ? ORDER BY version DESC LIMIT 1
        """,
      arguments: [bucketID])
    let version = (previous?["version"] as Int? ?? 0) + 1
    var frozen: Data = previous?["frozenRankedSegment"] ?? Data()
    let uncompressed = try Row.fetchAll(
      db,
      sql: """
          SELECT id, narrative, tokenCount FROM bucket_entries
          WHERE bucketID = ? AND isCompacted = 0 ORDER BY createdAt ASC
        """,
      arguments: [bucketID])
    if ContextBucketCompactionPolicy.shouldCompact(uncompressedCount: uncompressed.count) {
      let compacted = uncompressed.dropLast(ContextBucketCompactionPolicy.retainedTailCount)
      var rankedLines = (String(data: frozen, encoding: .utf8) ?? "")
        .split(separator: "\n", omittingEmptySubsequences: true)
        .map { String($0) + "\n" }
      for row in compacted {
        // Ranked exactly once at compaction. The compact deterministic ranking is
        // currently chronology-within-subject; later writes append after this breakpoint.
        rankedLines.append("- entry:\(row["id"] as String) \(row["narrative"] as String)\n")
        try db.execute(
          sql: "UPDATE bucket_entries SET isCompacted = 1 WHERE id = ?", arguments: [row["id"] as String])
      }
      while rankedLines.reduce(0, { $0 + $1.utf8.count }) > ContextBucketPromptAssembler.frozenRankedByteBudget,
        rankedLines.count > 1
      {
        rankedLines.removeFirst()
      }
      frozen = Data(rankedLines.joined().utf8)
    }
    let visitCount =
      try Int.fetchOne(
        db, sql: "SELECT visitCount FROM context_buckets WHERE id = ?", arguments: [bucketID]) ?? 0
    let header = "Persistent work context; \(visitCount) qualifying visits."
    try db.execute(
      sql: """
        INSERT INTO bucket_versions
          (bucketID, version, header, frozenRankedSegment, rankedTokenCount, createdAt)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
      arguments: [
        bucketID, version, header, frozen,
        ContextBucketPromptAssembler.estimatedTokens(String(data: frozen, encoding: .utf8) ?? ""), now,
      ])
    return db.lastInsertedRowID
  }
}

struct ContextBucketPurgeArtifacts: Sendable {
  let affectedBucketIDs: Set<String>
  let imagePaths: [String]
  let videoChunkPaths: [String]
}

enum ContextBucketPurger {
  /// Compatibility seam for deterministic SQL-only tests and callers that do
  /// not need to remove files. Production uses `deleteWithArtifacts` below.
  static func delete(appName: String, in db: Database) throws -> Set<String> {
    try deleteWithArtifacts(appName: appName, in: db).affectedBucketIDs
  }

  static func artifacts(appName: String, in db: Database) throws -> ContextBucketPurgeArtifacts {
    let affected = try affectedBucketIDs(appName: appName, in: db)
    guard try db.tableExists("screenshots") else {
      return ContextBucketPurgeArtifacts(
        affectedBucketIDs: affected, imagePaths: [], videoChunkPaths: [])
    }
    let columns = Set(
      try Row.fetchAll(db, sql: "PRAGMA table_info(screenshots)").compactMap { $0["name"] as String? })
    guard columns.contains("appName") else {
      return ContextBucketPurgeArtifacts(
        affectedBucketIDs: affected, imagePaths: [], videoChunkPaths: [])
    }
    let imagePaths: [String] =
      columns.contains("imagePath")
      ? try String.fetchAll(
        db,
        sql:
          "SELECT imagePath FROM screenshots WHERE appName = ? AND imagePath IS NOT NULL AND imagePath != ''",
        arguments: [appName])
      : []
    let videoChunkPaths: [String] =
      columns.contains("videoChunkPath")
      ? try String.fetchAll(
        db,
        sql:
          "SELECT DISTINCT videoChunkPath FROM screenshots WHERE appName = ? AND videoChunkPath IS NOT NULL AND videoChunkPath != ''",
        arguments: [appName])
      : []
    return ContextBucketPurgeArtifacts(
      affectedBucketIDs: affected,
      imagePaths: imagePaths,
      videoChunkPaths: videoChunkPaths)
  }

  static func deleteWithArtifacts(
    appName: String, in db: Database, now: Date = Date()
  ) throws -> ContextBucketPurgeArtifacts {
    let result = try artifacts(appName: appName, in: db)
    let affected = result.affectedBucketIDs
    // Invalidate every fence before deleting entries.  Extraction checks both
    // `fenceIsValid` and the completed visit row, so a completed request that
    // resumes after this transaction can no longer repopulate the bucket.
    if try db.tableExists("context_visits") {
      try db.execute(
        sql: "DELETE FROM context_visits WHERE appName = ?", arguments: [appName])
    }
    if try db.tableExists("observations") {
      try db.execute(sql: "DELETE FROM observations WHERE appName = ?", arguments: [appName])
    }
    try db.execute(sql: "DELETE FROM bucket_facts WHERE appName = ?", arguments: [appName])
    try db.execute(sql: "DELETE FROM bucket_entries WHERE appName = ?", arguments: [appName])
    if try db.tableExists("screenshots") {
      try db.execute(sql: "DELETE FROM screenshots WHERE appName = ?", arguments: [appName])
      // A video chunk is shared by time, not by app.  The privacy-first file
      // deletion above removes the whole chunk, so remove every row that still
      // points at it rather than leaving allowed-app rows with dangling media
      // references (and, more importantly, no hidden path to deleted bytes).
      for videoChunkPath in result.videoChunkPaths {
        try db.execute(
          sql: "DELETE FROM screenshots WHERE videoChunkPath = ?", arguments: [videoChunkPath])
      }
      for imagePath in result.imagePaths {
        try db.execute(sql: "DELETE FROM screenshots WHERE imagePath = ?", arguments: [imagePath])
      }
    }
    if !affected.isEmpty {
      // Historical versions contain the frozen bytes that cannot be attributed
      // to individual rows. Remove all versions and republish only surviving
      // entries, so deleted text cannot survive in a previous cache prefix.
      for bucketID in affected {
        try db.execute(
          sql: "DELETE FROM bucket_versions WHERE bucketID = ?", arguments: [bucketID])
        try db.execute(
          sql: "UPDATE bucket_entries SET isCompacted = 0, bucketVersionID = NULL WHERE bucketID = ?",
          arguments: [bucketID])
        try db.execute(
          sql: "DELETE FROM proactive_deliveries WHERE bucketID = ?", arguments: [bucketID])
        // Recompute visit metadata from surviving completed visits so the
        // bucket no longer reports deleted activity as recent or count it.
        let survivingCount =
          try
          (Int.fetchOne(
            db,
            sql: "SELECT COUNT(*) FROM context_visits WHERE bucketID = ? AND outcome = 'completed'",
            arguments: [bucketID]) ?? 0)
        try db.execute(
          sql: """
            UPDATE context_buckets
            SET visitCount = ?,
                lastVisitedAt = (SELECT MAX(endedAt) FROM context_visits WHERE bucketID = ? AND outcome = 'completed'),
                notifyWorthiness = COALESCE(
                  (SELECT MAX(notifyWorthiness) FROM bucket_facts
                   WHERE bucket_facts.bucketID = context_buckets.id AND validityState = 'validated'
                     AND (expiresAt IS NULL OR expiresAt > ?)), 0),
                updatedAt = ?
            WHERE id = ?
            """,
          arguments: [survivingCount, bucketID, now, now, bucketID])
      }
    }
    if try db.tableExists("ocr_texts"), try db.tableExists("ocr_occurrences") {
      try db.execute(sql: "DELETE FROM ocr_texts WHERE id NOT IN (SELECT DISTINCT ocrTextId FROM ocr_occurrences)")
    }
    return result
  }

  private static func affectedBucketIDs(appName: String, in db: Database) throws -> Set<String> {
    var affected = Set(
      try String.fetchAll(
        db, sql: "SELECT DISTINCT bucketID FROM bucket_entries WHERE appName = ?", arguments: [appName]))
    if try db.tableExists("bucket_facts") {
      affected.formUnion(
        try String.fetchAll(
          db, sql: "SELECT DISTINCT bucketID FROM bucket_facts WHERE appName = ?", arguments: [appName]))
    }
    if try db.tableExists("context_visits") {
      affected.formUnion(
        try String.fetchAll(
          db, sql: "SELECT DISTINCT bucketID FROM context_visits WHERE appName = ? AND bucketID IS NOT NULL",
          arguments: [appName]))
    }
    return affected
  }
}

actor ContextBucketRollupWriter {
  static let shared = ContextBucketRollupWriter()
  private let client: ProactiveLaneClient
  private let store: ContextBucketStore

  init(client: ProactiveLaneClient = .shared, store: ContextBucketStore = .shared) {
    self.client = client
    self.store = store
  }

  func extract(frame: CapturedFrame, fence: ContextVisitFence) async {
    guard
      fence.bucketID != nil,
      let authorizationSnapshot = RuntimeOwnerIdentity.captureAuthorizationSnapshot(),
      RuntimeOwnerIdentity.isAuthorizationCurrent(authorizationSnapshot),
      await store.fenceIsValid(fence)
    else { return }
    let prompt = ContextProactivityPromptBuilder.extractionPrompt(frame: frame, fence: fence)
    do {
      let result = try await client.complete(
        operation: ModelQoS.Proactivity.extractionOperation,
        prompt: prompt,
        imageData: frame.jpegData,
        jsonSchema: Self.schema,
        maxCompletionTokens: 1200,
        authorizationSnapshot: authorizationSnapshot)
      await ContextProactivityTelemetry.record(result)
      let extraction = try JSONDecoder().decode(BucketExtraction.self, from: Data(result.content.utf8))
      guard
        RuntimeOwnerIdentity.isAuthorizationCurrent(authorizationSnapshot),
        await store.fenceIsValid(fence)
      else { return }
      _ = try await store.writeExtraction(
        extraction,
        for: fence,
        appName: frame.appName,
        rawContextKey: "\(frame.appName)\n\(frame.windowTitle ?? "")",
        normalizedContextKey: ContextTitleNormalizer.identityKey(
          appName: frame.appName, windowTitle: frame.windowTitle) ?? "")
    } catch {
      log("Context bucket extraction failed silently: \(error.localizedDescription)")
    }
  }

  static var schema: [String: Any] {
    [
      "type": "object",
      "properties": [
        "narrative": ["type": "string"],
        "facts": [
          "type": "array",
          "items": [
            "type": "object",
            "properties": [
              "statement": ["type": "string"],
              "identifiers": ["type": "array", "items": ["type": "string"]],
              "evidence_text": ["type": "string"],
              "evidence_refs": ["type": "array", "items": ["type": "string"]],
              "confidence": ["type": "number"],
              "notify_worthiness": ["type": "number"],
            ],
            "required": [
              "statement", "identifiers", "evidence_text", "evidence_refs", "confidence",
              "notify_worthiness",
            ],
            "additionalProperties": false,
          ],
        ],
      ],
      "required": ["narrative", "facts"],
      "additionalProperties": false,
    ]
  }
}
