import Foundation
import GRDB

/// Reads the buckets and validated facts this device should publish.
///
/// Only `validated` facts are selected. The other validity states are working
/// state for the local validator, and publishing them would export exactly the
/// low-confidence content the validator exists to withhold.
enum ContextBucketSyncSelection {
  static let bucketLimit = ContextBucketSyncPayload.bucketLimit
  static let factLimitPerBucket = 40

  static func buckets(in db: Database, limit: Int = bucketLimit) throws -> [ContextBucketSyncBucket] {
    try Row.fetchAll(
      db,
      sql: """
        SELECT id, subjectKind, subjectID, workstreamID, displayLabel,
               notifyWorthiness, visitCount, lastVisitedAt, updatedAt
        FROM context_buckets
        ORDER BY updatedAt DESC LIMIT ?
        """,
      arguments: [limit]
    ).compactMap { row -> ContextBucketSyncBucket? in
      guard
        let bucketID: String = row["id"], let subjectKind: String = row["subjectKind"],
        let subjectID: String = row["subjectID"], let updatedAt: Date = row["updatedAt"]
      else { return nil }
      return ContextBucketSyncBucket(
        bucketID: bucketID,
        subjectKind: subjectKind,
        subjectID: subjectID,
        workstreamID: row["workstreamID"],
        displayLabel: row["displayLabel"],
        notifyWorthiness: row["notifyWorthiness"] ?? 0,
        visitCount: row["visitCount"] ?? 0,
        lastVisitedAt: row["lastVisitedAt"],
        updatedAt: updatedAt)
    }
  }

  static func facts(
    in db: Database,
    bucketID: String,
    now: Date,
    limit: Int = factLimitPerBucket
  ) throws -> [ContextBucketSyncFact] {
    try Row.fetchAll(
      db,
      sql: """
        SELECT id, bucketID, statement, identifiersJson, confidence, notifyWorthiness,
               dispositionState, workstreamTag, expiresAt, updatedAt
        FROM bucket_facts
        WHERE bucketID = ? AND validityState = 'validated'
          AND (expiresAt IS NULL OR expiresAt > ?)
        ORDER BY updatedAt DESC LIMIT ?
        """,
      arguments: [bucketID, now, limit]
    ).compactMap { row -> ContextBucketSyncFact? in
      guard
        let factID: String = row["id"], let rowBucketID: String = row["bucketID"],
        let statement: String = row["statement"], let updatedAt: Date = row["updatedAt"]
      else { return nil }
      return ContextBucketSyncFact(
        factID: factID,
        bucketID: rowBucketID,
        statement: statement,
        identifiers: decodeIdentifiers(row["identifiersJson"]),
        confidence: row["confidence"] ?? 0,
        notifyWorthiness: row["notifyWorthiness"] ?? 0,
        dispositionState: row["dispositionState"] ?? "none",
        workstreamTag: row["workstreamTag"],
        expiresAt: row["expiresAt"],
        updatedAt: updatedAt)
    }
  }

  static func decodeIdentifiers(_ json: String?) -> [String] {
    guard let json, let data = json.data(using: .utf8) else { return [] }
    return (try? JSONDecoder().decode([String].self, from: data)) ?? []
  }
}

/// Publishes this device's validated facts on a slow cadence.
///
/// The backend orders writes by `device_updated_at`, so republishing rows that
/// have not changed is harmless — it is skipped as stale rather than applied.
/// That makes a plain periodic pass safe without tracking a local sync cursor.
actor ContextBucketSyncScheduler {
  static let shared = ContextBucketSyncScheduler()
  static let interval: TimeInterval = 30 * 60

  private var timer: Task<Void, Never>?
  private var isRunning = false
  private let client: ContextBucketSyncClient

  init(client: ContextBucketSyncClient = .shared) {
    self.client = client
  }

  func start() {
    guard !isRunning else { return }
    isRunning = true
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
  }

  func runPass(now: Date = Date()) async {
    let enabled = await MainActor.run { ContextBucketsFeature.isBackendSyncEnabled }
    guard enabled else { return }
    guard RuntimeOwnerIdentity.captureAuthorizationSnapshot() != nil else { return }

    let (pool, _) = await RewindDatabase.shared.getDatabaseQueueWithGeneration()
    guard let pool else { return }

    let staged = try? await pool.read { db -> ([ContextBucketSyncBucket], [ContextBucketSyncFact]) in
      let buckets = try ContextBucketSyncSelection.buckets(in: db)
      var facts: [ContextBucketSyncFact] = []
      for bucket in buckets {
        facts.append(
          contentsOf: try ContextBucketSyncSelection.facts(in: db, bucketID: bucket.bucketID, now: now))
      }
      return (buckets, facts)
    }
    guard let staged, !staged.0.isEmpty else { return }

    let deviceID = ClientDeviceService.shared.clientDeviceId
    let accountGeneration = await MainActor.run {
      AccountCutoverControlManager.shared.control.accountGeneration
    }
    do {
      try await client.sync(
        deviceID: deviceID,
        accountGeneration: accountGeneration,
        buckets: staged.0,
        facts: staged.1)
    } catch {
      log("ContextBucketSyncScheduler: sync failed \(error.localizedDescription)")
    }
  }
}
