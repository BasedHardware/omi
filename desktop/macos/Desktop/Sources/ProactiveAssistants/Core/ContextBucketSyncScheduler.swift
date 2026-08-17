import Foundation
import GRDB

/// Reads the buckets and validated facts this device should publish.
///
/// Only `validated` facts are selected. The other validity states are working
/// state for the local validator, and publishing them would export exactly the
/// low-confidence content the validator exists to withhold.
///
/// The selected columns are deliberately narrow: `displayLabel`, `subjectID`,
/// and `identifiersJson` all hold text copied from the screen — window titles,
/// URLs, file paths, and literal on-screen handles — so they are never read
/// here and cannot reach a payload.
/// Keyset position of the last bucket this device published.
struct ContextBucketSyncCursor: Equatable, Sendable, Codable {
  let updatedAt: Date
  let bucketID: String
}

enum ContextBucketSyncSelection {
  static let bucketLimit = ContextBucketSyncPayload.bucketLimit
  static let factLimitPerBucket = 40

  /// Buckets after the cursor, oldest first.
  ///
  /// A plain "newest N" window would leave bucket N+1 permanently unpublishable
  /// and would re-transmit the same rows every pass. The cursor is a keyset on
  /// (updatedAt, id) rather than a bare timestamp: buckets written in the same
  /// batch share an updatedAt, and a timestamp-only cursor would step past all
  /// but the first `limit` of them and never come back.
  static func buckets(
    in db: Database,
    after cursor: ContextBucketSyncCursor?,
    limit: Int = bucketLimit
  ) throws -> [ContextBucketSyncBucket] {
    try Row.fetchAll(
      db,
      sql: """
        SELECT id, subjectKind, workstreamID,
               notifyWorthiness, visitCount, lastVisitedAt, updatedAt
        FROM context_buckets
        WHERE (updatedAt > ?) OR (updatedAt = ? AND id > ?)
        ORDER BY updatedAt ASC, id ASC LIMIT ?
        """,
      arguments: [
        cursor?.updatedAt ?? Date(timeIntervalSince1970: 0),
        cursor?.updatedAt ?? Date(timeIntervalSince1970: 0),
        cursor?.bucketID ?? "",
        limit,
      ]
    ).compactMap { row -> ContextBucketSyncBucket? in
      guard
        let bucketID: String = row["id"], let subjectKind: String = row["subjectKind"],
        let updatedAt: Date = row["updatedAt"]
      else { return nil }
      return ContextBucketSyncBucket(
        bucketID: bucketID,
        subjectKind: subjectKind,
        workstreamID: row["workstreamID"],
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
        SELECT id, bucketID, statement, confidence, notifyWorthiness,
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
        confidence: row["confidence"] ?? 0,
        notifyWorthiness: row["notifyWorthiness"] ?? 0,
        dispositionState: row["dispositionState"] ?? "none",
        workstreamTag: row["workstreamTag"],
        expiresAt: row["expiresAt"],
        updatedAt: updatedAt)
    }
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
  /// Persisted so a restart resumes instead of replaying from the beginning.
  ///
  /// An in-memory cursor restarts at epoch every launch, so a device restarted
  /// regularly would keep re-publishing its oldest buckets and never reach its
  /// newest ones.
  private var cursor: ContextBucketSyncCursor? {
    get {
      guard let data = UserDefaults.standard.data(forKey: Self.cursorDefaultsKey) else { return nil }
      return try? JSONDecoder().decode(ContextBucketSyncCursor.self, from: data)
    }
    set {
      let defaults = UserDefaults.standard
      guard let newValue, let data = try? JSONEncoder().encode(newValue) else {
        defaults.removeObject(forKey: Self.cursorDefaultsKey)
        return
      }
      defaults.set(data, forKey: Self.cursorDefaultsKey)
    }
  }

  private static let cursorDefaultsKey = "contextBucketSyncCursor"
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
    // The payload is read under this owner, so this is the snapshot the upload
    // must be fenced against — not whoever owns the process by the time it lands.
    guard let authorizationSnapshot = RuntimeOwnerIdentity.captureAuthorizationSnapshot() else { return }

    let (pool, _) = await RewindDatabase.shared.getDatabaseQueueWithGeneration()
    guard let pool else { return }

    let position = cursor
    let staged: ([ContextBucketSyncBucket], [ContextBucketSyncFact])
    do {
      staged = try await pool.read { db -> ([ContextBucketSyncBucket], [ContextBucketSyncFact]) in
        let buckets = try ContextBucketSyncSelection.buckets(in: db, after: position)
        var facts: [ContextBucketSyncFact] = []
        for bucket in buckets {
          facts.append(
            contentsOf: try ContextBucketSyncSelection.facts(in: db, bucketID: bucket.bucketID, now: now))
        }
        return (buckets, facts)
      }
    } catch {
      // Schema drift would otherwise make sync a permanent silent no-op.
      await RewindDatabase.shared.reportQueryError(error)
      log("ContextBucketSyncScheduler: staging failed \(error.localizedDescription)")
      return
    }
    guard !staged.0.isEmpty else { return }

    let deviceID = ClientDeviceService.shared.clientDeviceId
    let accountGeneration = await MainActor.run {
      AccountCutoverControlManager.shared.control.accountGeneration
    }
    do {
      try await client.sync(
        deviceID: deviceID,
        accountGeneration: accountGeneration,
        buckets: staged.0,
        facts: staged.1,
        authorizedBy: authorizationSnapshot)
      // Only advance past rows the server accepted, so a failure re-sends them.
      if let last = staged.0.last {
        cursor = ContextBucketSyncCursor(updatedAt: last.updatedAt, bucketID: last.bucketID)
      }
    } catch {
      log("ContextBucketSyncScheduler: sync failed \(error.localizedDescription)")
    }
  }
}
