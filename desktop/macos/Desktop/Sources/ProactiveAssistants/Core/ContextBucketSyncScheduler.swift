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

/// Owner-scoped persistence for the sync watermark.
///
/// A global key lets account B inherit account A's far-ahead cursor and skip
/// its older buckets until they are touched again.
enum ContextBucketSyncCursorStore {
  static let legacyKey = "contextBucketSyncCursor"

  static func key(ownerID: String) -> String {
    "contextBucketSyncCursor.\(ownerID)"
  }

  static func load(ownerID: String, from defaults: UserDefaults = .standard) -> ContextBucketSyncCursor? {
    guard !ownerID.isEmpty, let data = defaults.data(forKey: key(ownerID: ownerID)) else { return nil }
    return try? JSONDecoder().decode(ContextBucketSyncCursor.self, from: data)
  }

  static func save(
    _ cursor: ContextBucketSyncCursor?,
    ownerID: String,
    to defaults: UserDefaults = .standard
  ) {
    guard !ownerID.isEmpty else { return }
    defaults.removeObject(forKey: legacyKey)
    let defaultsKey = key(ownerID: ownerID)
    guard let cursor, let data = try? JSONEncoder().encode(cursor) else {
      defaults.removeObject(forKey: defaultsKey)
      return
    }
    defaults.set(data, forKey: defaultsKey)
  }
}

/// Serializes a sync pass against exclude-driven purge.
///
/// Actor isolation alone is not enough: `runPass` suspends on the network, and
/// Swift actors are reentrant at `await`. Without this gate, exclude can finish
/// local delete + backend retract (and clear the journal) while a staged POST
/// is still in flight, then that POST recreates the retracted facts.
actor ContextBucketSyncPassGate {
  private var held = false
  private var waiters: [CheckedContinuation<Void, Never>] = []

  func acquire() async {
    if !held {
      held = true
      return
    }
    await withCheckedContinuation { waiters.append($0) }
  }

  func release() {
    if waiters.isEmpty {
      held = false
      return
    }
    waiters.removeFirst().resume()
  }

  func withExclusive<T: Sendable>(_ body: @Sendable () async throws -> T) async throws -> T {
    await acquire()
    defer { release() }
    return try await body()
  }
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
  private let passGate = ContextBucketSyncPassGate()
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

  func withExclusivePass<T: Sendable>(_ body: @Sendable () async throws -> T) async throws -> T {
    try await passGate.withExclusive(body)
  }

  func runPass(now: Date = Date()) async {
    let enabled = await MainActor.run { ContextBucketsFeature.isBackendSyncEnabled }
    guard enabled else { return }
    // The payload is read under this owner, so this is the snapshot the upload
    // must be fenced against — not whoever owns the process by the time it lands.
    guard let authorizationSnapshot = RuntimeOwnerIdentity.captureAuthorizationSnapshot() else { return }

    let (pool, _) = await RewindDatabase.shared.getDatabaseQueueWithGeneration()
    guard let pool else { return }

    try? await withExclusivePass {
      await self.publishStagedBuckets(
        pool: pool,
        authorizationSnapshot: authorizationSnapshot,
        now: now)
    }
  }

  private func publishStagedBuckets(
    pool: DatabasePool,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot,
    now: Date
  ) async {
    let position = ContextBucketSyncCursorStore.load(ownerID: authorizationSnapshot.ownerID)
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
        ContextBucketSyncCursorStore.save(
          ContextBucketSyncCursor(updatedAt: last.updatedAt, bucketID: last.bucketID),
          ownerID: authorizationSnapshot.ownerID)
      }
    } catch {
      log("ContextBucketSyncScheduler: sync failed \(error.localizedDescription)")
    }
  }
}
