import Foundation
@preconcurrency import GRDB

private struct ScreenActivityRowsPayload: @unchecked Sendable {
  let rows: [[String: Any]]
}

struct ScreenActivitySyncCandidate: @unchecked Sendable {
  let id: Int64
  let priorState: ScreenActivitySyncState
  let hasEmbedding: Bool
  let payload: [String: Any]
}

enum ScreenActivitySyncState: Int {
  case pending = 0
  case textSynced = 1
  case fullySynced = 2
  case compacted = 3
}

enum ScreenActivityLosslessSyncFeature {
  static let flagName = "screen_activity_lossless_sync"
  static let killSwitchFlagName = "screen_activity_lossless_sync_kill"
  private static let localOverrideName = "OMI_FORCE_LOSSLESS_SCREEN_SYNC"

  /// Development bundles dogfood by default. Beta is on unless killed — it is the channel this
  /// is meant to be exercised on, and its backend is the one carrying the rest of the rollout.
  /// Stable stays on the legacy path until the PostHog flag is explicitly enabled, so the
  /// migration ships dark without changing production traffic.
  @MainActor static var isEnabled: Bool {
    if AppBuild.isNonProduction {
      return ProcessInfo.processInfo.environment[localOverrideName] != "0"
    }
    return BetaDogfoodRollout.isEnabled(
      flagName: flagName,
      killSwitchFlagName: killSwitchFlagName,
      localOverrideName: localOverrideName
    )
  }
}

/// Syncs screenshot metadata + embeddings from the local GRDB database
/// to the backend API (`POST /v1/screen-activity/sync`), which stores them
/// in Firestore + Pinecone so the normal Flutter chat can answer screen
/// activity questions.
///
/// The lossless path uses durable per-row delivery state and treats embeddings as an optional,
/// later projection. The legacy cursor remains only as the flag-off rollback path.
actor ScreenActivitySyncService {
  static let shared = ScreenActivitySyncService()

  // MARK: - State

  private var lastSyncedId: Int64 = 0
  private var isRunning = false
  private var syncTask: Task<Void, Never>?
  private var consecutiveFailures = 0
  private var didStartEmbeddingRecovery = false

  private let batchSize = 100
  private let baseSyncInterval: UInt64 = 60_000_000_000  // 60s in nanoseconds
  private let maxSyncInterval: UInt64 = 300_000_000_000  // 300s max backoff

  private let cursorKey = "screenActivitySync_lastId"
  private let compactionDelay: TimeInterval = 5 * 60
  /// How long a closed bucket's winner waits for its embedding before shipping text-only.
  /// Without it every row ships twice: once when compaction sweeps it, and again when the
  /// vector lands — a second byte-identical Firestore document write plus a full rewrite of
  /// its index entries, for no data change.
  private let embeddingGrace: TimeInterval = 15 * 60

  // MARK: - Public API

  /// Start the sync loop. Call after auth is established and database is ready.
  func start(initialDelay: TimeInterval = 0) {
    guard !isRunning else {
      log("ScreenActivitySync: already running")
      return
    }
    isRunning = true
    loadCursor()
    log("ScreenActivitySync: starting (lastSyncedId=\(lastSyncedId), initialDelay=\(initialDelay)s)")
    syncLoop(initialDelay: initialDelay)
  }

  /// Stop the sync loop.
  func stop() {
    guard isRunning else { return }
    isRunning = false
    syncTask?.cancel()
    syncTask = nil
    didStartEmbeddingRecovery = false
    log("ScreenActivitySync: stopped")
  }

  // MARK: - Sync loop

  private func syncLoop(initialDelay: TimeInterval) {
    syncTask = Task {
      if initialDelay > 0 {
        try? await Task.sleep(nanoseconds: UInt64(initialDelay * 1_000_000_000))
      }
      while !Task.isCancelled && isRunning {
        // Skip if user is signed out
        guard await AuthState.shared.isSignedIn else {
          try? await Task.sleep(nanoseconds: baseSyncInterval)
          continue
        }
        await syncTick()
        let interval = currentSyncInterval()
        try? await Task.sleep(nanoseconds: interval)
      }
    }
  }

  private func currentSyncInterval() -> UInt64 {
    if consecutiveFailures > 0 {
      // Exponential backoff: 10s, 20s, 40s, 80s, capped at 120s
      let backoff = baseSyncInterval * UInt64(1 << min(consecutiveFailures, 4))
      return min(backoff, maxSyncInterval)
    }
    return baseSyncInterval
  }

  private func syncTick() async {
    guard let dbPool = await getDBPool() else { return }

    let losslessEnabled = await MainActor.run { ScreenActivityLosslessSyncFeature.isEnabled }
    if losslessEnabled {
      await losslessSyncTick(dbPool: dbPool)
    } else {
      await legacySyncTick(dbPool: dbPool)
    }
  }

  private func losslessSyncTick(dbPool: DatabasePool) async {
    if !didStartEmbeddingRecovery {
      didStartEmbeddingRecovery = true
      Task(priority: .utility) {
        await OCREmbeddingService.shared.backfillIfNeeded()
      }
    }
    do {
      let now = Date()
      let candidates = try await dbPool.write { [batchSize, compactionDelay, embeddingGrace] db in
        try Self.compactClosedBuckets(db: db, now: now, slack: compactionDelay)
        return try Self.fetchSyncCandidates(
          db: db, limit: batchSize, now: now, slack: compactionDelay, embeddingGrace: embeddingGrace)
      }
      guard !candidates.isEmpty else { return }

      let success = await pushRows(candidates.map(\.payload))
      if success {
        try await dbPool.write { db in
          try Self.markCandidatesSynced(db: db, candidates: candidates)
        }
        if consecutiveFailures > 0 {
          log("ScreenActivitySync: lossless path reconnected after \(consecutiveFailures) failures")
        }
        consecutiveFailures = 0
        log("ScreenActivitySync: lossless path synced \(candidates.count) rows")
      } else {
        recordPushFailure(path: "lossless")
      }
    } catch {
      log("ScreenActivitySync: lossless read/write error — \(error.localizedDescription)")
    }
  }

  private func legacySyncTick(dbPool: DatabasePool) async {

    do {
      // Query screenshots that have embeddings and are newer than our cursor
      let rowsPayload: ScreenActivityRowsPayload = try await dbPool.read { [lastSyncedId, batchSize] db in
        let dbRows = try Row.fetchAll(db, sql: Self.syncRowsSQL, arguments: [lastSyncedId, batchSize])
        let rows = dbRows.compactMap(Self.payloadRow)
        return ScreenActivityRowsPayload(rows: rows)
      }
      let rows = rowsPayload.rows

      guard !rows.isEmpty else { return }

      // Push to backend
      let success = await pushRows(rows)
      if success {
        if let maxId = rows.compactMap({ $0["id"] as? Int64 }).max() {
          lastSyncedId = maxId
          saveCursor()
        }
        if consecutiveFailures > 0 {
          log("ScreenActivitySync: reconnected after \(consecutiveFailures) failures")
        }
        consecutiveFailures = 0
        log("ScreenActivitySync: synced \(rows.count) rows (lastId=\(lastSyncedId))")
      } else {
        recordPushFailure(path: "legacy")
      }
    } catch {
      log("ScreenActivitySync: read error — \(error.localizedDescription)")
    }
  }

  private func recordPushFailure(path: String) {
    consecutiveFailures += 1
    if consecutiveFailures == 1 || consecutiveFailures % 10 == 0 {
      log("ScreenActivitySync: \(path) push failed (failures=\(consecutiveFailures))")
    }
  }

  static let syncRowsSQL = """
    SELECT id, timestamp, appName, windowTitle, ocrText, embedding, deviceName, clientDeviceId
    FROM screenshots
    WHERE id > ? AND embedding IS NOT NULL
    ORDER BY id ASC
    LIMIT ?
    """

  static let compactionBucketSeconds = 300

  /// A row is eligible once the five-minute bucket *containing* it has closed, plus slack.
  ///
  /// Comparing each row's own timestamp against `now - slack` instead would make eligibility
  /// slide: the early rows of a bucket become ready while its later rows do not, so a single
  /// bucket is ranked more than once and emits more than one winner. Measured against 7,346
  /// real OCR-bearing rows, the sliding form shipped 5,517 rows where bucket-aligned ranking
  /// ships 3,842 — 44% more than the design intends, which is most of the saving.
  static func bucketEligibilityCutoffEpoch(now: Date, slack: TimeInterval) -> Int64 {
    Int64((now.timeIntervalSince1970 - slack).rounded(.down))
  }

  /// Close completed five-minute buckets before delivery. Rows remain intact; only the durable
  /// delivery disposition changes. Ranking uses OCR length and then row id for deterministic ties.
  static func compactClosedBuckets(db: Database, now: Date, slack: TimeInterval) throws {
    try db.execute(
      sql: """
        WITH ranked AS (
          SELECT id,
                 ROW_NUMBER() OVER (
                   PARTITION BY appName, COALESCE(windowTitle, ''),
                                CAST(strftime('%s', timestamp) AS INTEGER) / 300
                   ORDER BY LENGTH(ocrText) DESC, id DESC
                 ) AS bucketRank
          FROM screenshots
          WHERE screenActivitySyncState = ?
            AND ocrText IS NOT NULL
            AND LENGTH(TRIM(ocrText)) > 0
            AND (CAST(strftime('%s', timestamp) AS INTEGER) / ? + 1) * ? <= ?
        )
        UPDATE screenshots
        SET screenActivitySyncState = ?
        WHERE id IN (SELECT id FROM ranked WHERE bucketRank > 1)
        """,
      arguments: [
        ScreenActivitySyncState.pending.rawValue,
        Self.compactionBucketSeconds, Self.compactionBucketSeconds,
        Self.bucketEligibilityCutoffEpoch(now: now, slack: slack),
        ScreenActivitySyncState.compacted.rawValue,
      ])
  }

  static func fetchSyncCandidates(
    db: Database, limit: Int, now: Date, slack: TimeInterval, embeddingGrace: TimeInterval
  ) throws -> [ScreenActivitySyncCandidate] {
    let rows = try Row.fetchAll(
      db,
      sql: """
        SELECT id, timestamp, appName, windowTitle, ocrText, embedding, deviceName, clientDeviceId,
               screenActivitySyncState
        FROM screenshots
        WHERE (
          screenActivitySyncState = ?
          AND ocrText IS NOT NULL
          AND LENGTH(TRIM(ocrText)) > 0
          AND (CAST(strftime('%s', timestamp) AS INTEGER) / ? + 1) * ? <= ?
          AND (
            embedding IS NOT NULL
            OR (CAST(strftime('%s', timestamp) AS INTEGER) / ? + 1) * ? <= ?
          )
        ) OR (
          screenActivitySyncState = ?
          AND embedding IS NOT NULL
        )
        ORDER BY CASE screenActivitySyncState WHEN 0 THEN 0 ELSE 1 END, id ASC
        LIMIT ?
        """,
      arguments: [
        ScreenActivitySyncState.pending.rawValue,
        Self.compactionBucketSeconds, Self.compactionBucketSeconds,
        Self.bucketEligibilityCutoffEpoch(now: now, slack: slack),
        Self.compactionBucketSeconds, Self.compactionBucketSeconds,
        Self.bucketEligibilityCutoffEpoch(now: now, slack: embeddingGrace),
        ScreenActivitySyncState.textSynced.rawValue, limit,
      ])

    return rows.compactMap { row in
      guard let id = row["id"] as? Int64,
        let stateRaw = row["screenActivitySyncState"] as? Int64,
        let state = ScreenActivitySyncState(rawValue: Int(stateRaw)),
        let payload = payloadRow(from: row)
      else { return nil }
      let blobValue = row["embedding"] as DatabaseValue
      let hasEmbedding: Bool
      if case .blob = blobValue.storage { hasEmbedding = true } else { hasEmbedding = false }
      return ScreenActivitySyncCandidate(id: id, priorState: state, hasEmbedding: hasEmbedding, payload: payload)
    }
  }

  static func markCandidatesSynced(db: Database, candidates: [ScreenActivitySyncCandidate]) throws {
    for candidate in candidates {
      let nextState: ScreenActivitySyncState = candidate.hasEmbedding ? .fullySynced : .textSynced
      try db.execute(
        sql: """
          UPDATE screenshots
          SET screenActivitySyncState = ?
          WHERE id = ? AND screenActivitySyncState = ?
          """,
        arguments: [nextState.rawValue, candidate.id, candidate.priorState.rawValue])
    }
  }

  static func payloadRow(from row: Row) -> [String: Any]? {
    guard let id = row["id"] as? Int64 else { return nil }

    var dict: [String: Any] = ["id": id]
    if let ts = row["timestamp"] as? String {
      dict["timestamp"] = canonicalTimestamp(ts) ?? ts
    } else if let ts = row["timestamp"] as? Double {
      dict["timestamp"] = canonicalTimestamp(Date(timeIntervalSince1970: ts))
    }
    dict["appName"] = (row["appName"] as? String) ?? ""
    dict["windowTitle"] = (row["windowTitle"] as? String) ?? ""
    dict["ocrText"] = (row["ocrText"] as? String) ?? ""
    if let deviceName = row["deviceName"] as? String, !deviceName.isEmpty {
      dict["deviceName"] = deviceName
    }
    if let clientDeviceId = row["clientDeviceId"] as? String, !clientDeviceId.isEmpty {
      dict["clientDeviceId"] = clientDeviceId
    }

    let blobValue = row["embedding"] as DatabaseValue
    if case .blob(let data) = blobValue.storage {
      let floatCount = data.count / MemoryLayout<Float>.size
      let floats = data.withUnsafeBytes { ptr in
        Array(
          UnsafeBufferPointer(
            start: ptr.baseAddress?.assumingMemoryBound(to: Float.self),
            count: floatCount
          ))
      }
      dict["embedding"] = floats.map { Double($0) }
    }
    return dict
  }

  static func canonicalTimestamp(_ value: String) -> String? {
    if let date = makeCanonicalTimestampFormatter().date(from: value) {
      return canonicalTimestamp(date)
    }
    let fractionalISOFormatter = ISO8601DateFormatter()
    fractionalISOFormatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
    if let date = fractionalISOFormatter.date(from: value) {
      return canonicalTimestamp(date)
    }
    return ISO8601DateFormatter().date(from: value).map(canonicalTimestamp)
  }

  static func canonicalTimestamp(_ date: Date) -> String {
    makeCanonicalTimestampFormatter().string(from: date)
  }

  private static func makeCanonicalTimestampFormatter() -> DateFormatter {
    let formatter = DateFormatter()
    formatter.calendar = Calendar(identifier: .gregorian)
    formatter.locale = Locale(identifier: "en_US_POSIX")
    formatter.timeZone = TimeZone(secondsFromGMT: 0)
    formatter.dateFormat = "yyyy-MM-dd HH:mm:ss.SSS"
    return formatter
  }

  // MARK: - HTTP push

  private func pushRows(_ rows: [[String: Any]]) async -> Bool {
    let payload: [String: Any] = ["rows": rows]

    guard let jsonData = try? JSONSerialization.data(withJSONObject: payload) else {
      log("ScreenActivitySync: JSON serialization error")
      return false
    }

    do {
      let headers = try await APIClient.shared.buildHeaders()
      let baseURL = await APIClient.shared.rustBackendURL
      guard let url = URL(string: baseURL + "v1/screen-activity/sync") else {
        log("ScreenActivitySync: invalid URL")
        return false
      }

      var request = URLRequest(url: url)
      request.httpMethod = "POST"
      request.httpBody = jsonData
      request.timeoutInterval = 60
      for (key, value) in headers {
        request.setValue(value, forHTTPHeaderField: key)
      }

      let (data, response) = try await URLSession.shared.data(for: request)
      guard let httpResponse = response as? HTTPURLResponse else { return false }

      if httpResponse.statusCode == 200 {
        return true
      } else {
        let body = String(data: data, encoding: .utf8) ?? ""
        log("ScreenActivitySync: HTTP \(httpResponse.statusCode): \(body)")
        return false
      }
    } catch {
      log("ScreenActivitySync: network error — \(error.localizedDescription)")
      return false
    }
  }

  // MARK: - Database access

  private func getDBPool() async -> DatabasePool? {
    try? await RewindDatabase.shared.initialize()
    return await RewindDatabase.shared.getDatabaseQueue()
  }

  // MARK: - Cursor persistence

  private func loadCursor() {
    lastSyncedId = Int64(UserDefaults.standard.integer(forKey: cursorKey))
    log("ScreenActivitySync: loaded cursor lastSyncedId=\(lastSyncedId)")
  }

  private func saveCursor() {
    UserDefaults.standard.set(Int(lastSyncedId), forKey: cursorKey)
  }
}
