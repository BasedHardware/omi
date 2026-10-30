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

  /// Pure lifecycle decisions keep the recovery contract testable without
  /// invoking Firestore/GCS or a network session. Claimed rows may have lost a
  /// response after a prior claim and therefore remain uploadable; uploaded
  /// rows skip pixel upload and only retry promotion.
  static func shouldClaimFrameRequest(state: String) -> Bool {
    state == "requested"
  }

  static func shouldUploadFrameRequest(state: String) -> Bool {
    state != "uploaded"
  }

  static func boundedDeviceRetentionSeconds(retentionDays: Int) -> Int? {
    RewindSettings.isUnlimited(retentionDays: retentionDays)
      ? nil : min(6, max(1, retentionDays)) * 24 * 60 * 60
  }

  static func frameRequestSyncPayload(
    rows: [[String: Any]], accountGeneration: Int, retentionDays: Int
  ) -> [String: Any] {
    let eligibleRows = rows.map { row in
      var admitted = row
      // A sync row exists only after Rewind's exclusion policy admitted and
      // persisted the capture. Never synthesize this for an arbitrary image.
      admitted["captureEligible"] = true
      return admitted
    }
    var payload: [String: Any] = ["rows": eligibleRows, "account_generation": accountGeneration]
    if let seconds = boundedDeviceRetentionSeconds(retentionDays: retentionDays) {
      payload["deviceRetentionSeconds"] = seconds
    }
    return payload
  }

  // MARK: - State

  private var cursorOwner: RuntimeOwnerAuthorizationSnapshot?
  private var lastSyncedId: Int64 = 0
  private var isRunning = false
  private var syncTask: Task<Void, Never>?
  private var consecutiveFailures = 0
  private let cursorStore = ScreenActivityCursorStore()

  private let batchSize = 100
  private let baseSyncInterval: UInt64 = 60_000_000_000  // 60s in nanoseconds
  private let maxSyncInterval: UInt64 = 300_000_000_000  // 300s max backoff

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
    loadCursor(authorization: RuntimeOwnerIdentity.captureAuthorizationSnapshot())
    log("ScreenActivitySync: starting (lastSyncedId=\(lastSyncedId), initialDelay=\(initialDelay)s)")
    syncLoop(initialDelay: initialDelay)
  }

  /// Stop the sync loop.
  func stop(logStopped: Bool = true) {
    guard isRunning else { return }
    isRunning = false
    syncTask?.cancel()
    syncTask = nil
    if logStopped { log("ScreenActivitySync: stopped") }
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
    guard let authorization = RuntimeOwnerIdentity.captureAuthorizationSnapshot(),
      let dbPool = await getDBPool(), RuntimeOwnerIdentity.isAuthorizationCurrent(authorization)
    else { return }
    if cursorOwner != authorization { loadCursor(authorization: authorization) }
    let lossless = await MainActor.run { ScreenActivityLosslessSyncFeature.isEnabled }
    guard RuntimeOwnerIdentity.isAuthorizationCurrent(authorization) else { return }
    // The OCR actor owns coalescing, retry cooldowns and the process-wide launch budget.
    // Cold/expired entitlement must not consume a once-per-launch scheduling flag.
    Task(priority: .utility) { await OCREmbeddingService.shared.backfillIfNeeded() }
    let mutation = LocalMutationAuthorization { RuntimeOwnerIdentity.isAuthorizationCurrent(authorization) }
    do {
      let cursor = try await Self.deliverPeriodicBatch(
        database: dbPool, afterId: lossless ? nil : lastSyncedId, limit: batchSize, now: Date(),
        authorizationIsCurrent: { RuntimeOwnerIdentity.isAuthorizationCurrent(authorization) },
        cloudAllowed: { ScreenCloudEntitlementService.shared.allowsCloud(authorization) },
        mutation: mutation,
        push: { rows in
          await self.pushRows(rows, authorizationSnapshot: authorization, periodic: true)
        })
      guard RuntimeOwnerIdentity.isAuthorizationCurrent(authorization) else { return }
      if let cursor, !lossless {
        try await saveCursor(cursor, authorization: authorization)
      }
      consecutiveFailures = 0
    } catch {
      if isRunning { recordPushFailure(path: lossless ? "lossless" : "legacy") }
    }
  }

  /// Durable optional-projection receipt. Text can advance the legacy cursor while a later
  /// vector remains eligible independently of that cursor. A failed/revoked push never acks.
  static func deliverPeriodicBatch(
    database: any DatabaseWriter, afterId: Int64?, limit: Int, now: Date,
    authorizationIsCurrent: @escaping @Sendable () -> Bool,
    cloudAllowed: @escaping @Sendable () -> Bool,
    mutation: LocalMutationAuthorization,
    push: ([[String: Any]]) async -> Bool,
    isolation: isolated (any Actor)? = #isolation
  ) async throws -> Int64? {
    guard authorizationIsCurrent() else { throw LocalMutationAuthorizationError.revoked }
    let allowsCloud = cloudAllowed()
    let candidates: [ScreenActivitySyncCandidate] = try await mutation.withCommitLease {
      try await database.write { db in
        try mutation.require()
        if let afterId {
          return try fetchLegacySyncRows(db: db, afterId: afterId, limit: limit, now: now, cloudAllowed: allowsCloud)
            .compactMap(syncCandidate(from:))
        }
        try compactClosedBuckets(db: db, now: now, slack: 300)
        return try fetchSyncCandidates(
          db: db, limit: limit, now: now, slack: 300,
          embeddingGrace: allowsCloud ? 900 : 300, cloudAllowed: allowsCloud)
      }
    }
    guard authorizationIsCurrent() else { throw LocalMutationAuthorizationError.revoked }
    // Re-project at the last non-suspending boundary before transport. Fresh downgrades beat
    // stored vectors, but keep their local blob for a later upgrade.
    let includeVectors = cloudAllowed()
    let delivery = candidates.compactMap { candidate -> ScreenActivitySyncCandidate? in
      if candidate.priorState == .textSynced && !includeVectors { return nil }
      var payload = candidate.payload
      if !includeVectors { payload.removeValue(forKey: "embedding") }
      return ScreenActivitySyncCandidate(
        id: candidate.id, priorState: candidate.priorState,
        hasEmbedding: includeVectors && candidate.hasEmbedding, payload: payload)
    }
    guard !delivery.isEmpty else { return nil }
    guard authorizationIsCurrent() else { throw LocalMutationAuthorizationError.revoked }
    guard await push(delivery.map(\.payload)) else { throw URLError(.cannotConnectToHost) }
    guard authorizationIsCurrent() else { throw LocalMutationAuthorizationError.revoked }
    try await mutation.withCommitLease {
      try await database.write { db in
        try mutation.require()
        try markCandidatesSynced(db: db, candidates: delivery)
      }
    }
    return delivery.map(\.id).max()
  }

  /// Push a just-finished meeting's OCR text now, before its notes are written.
  ///
  /// The periodic lossless path holds a row until its five-minute bucket has closed plus five
  /// minutes of slack (fifteen without an embedding), so at finalization the backend's screen-text
  /// digest is missing the last ten to twenty minutes of the call — usually where the decisions
  /// are. This closes the meeting's own rows early: one winner per `(app, window, bucket)` inside
  /// the meeting interval, shipped text-first like any other winner. Rows of the same bucket
  /// captured after the meeting ended stay pending and may later ship one more winner for that
  /// bucket; that bounded extra document is the price of notes that see the end of the call.
  /// Legacy (cursor) sync is left alone. Best effort: every failure leaves the periodic path to it.
  func flushMeetingWindow(_ interval: DateInterval, deadline: Date) async {
    let losslessEnabled = await MainActor.run { ScreenActivityLosslessSyncFeature.isEnabled }
    guard losslessEnabled else { return }
    // Owner-bound (auth-session invariant): bind before touching this owner's database, recheck
    // after every read, and send every batch under that owner's session only.
    guard let authorization = MeetingEvidenceAuthorization.captureCurrentOwner(),
      let dbPool = await getDBPool()
    else { return }
    await Self.flushMeetingWindow(
      interval, database: dbPool,
      push: { await self.pushRows($0, authorizationSnapshot: authorization.snapshot) },
      authorizationIsCurrent: { authorization.isCurrent },
      cloudAllowed: { authorization.snapshot.map { ScreenCloudEntitlementService.shared.allowsCloud($0) } ?? false },
      // INV-AUTH-1: each sync-state write holds an owner mutation lease through its commit, and
      // re-requires the owner inside the transaction, so a pool opened for the owner who was
      // signed in when this began can never mutate a replacement owner's rows.
      mutation: LocalMutationAuthorization { authorization.isCurrent },
      shouldContinue: { Date() < deadline },
      recordFallback: { reason in
        DesktopDiagnosticsManager.shared.recordFallback(
          area: "meeting_screen_evidence", from: "ocr_flush", to: "periodic_sync", reason: reason,
          outcome: .degraded)
      })
  }

  /// `POST /v1/screen-activity/sync` rejects a body of more than 100 rows with a 400.
  static let meetingFlushBatchSize = 100

  /// Result of one meeting flush, for the caller's log and for tests.
  enum MeetingFlushResult: Equatable {
    case nothingPending
    case synced(Int)
    /// Degraded from here on: notes are written without the rest, which the periodic path ships.
    case pushFailed(synced: Int)
    case databaseFailed(synced: Int)
    case deadlineReached(synced: Int)
    /// The signed-in account changed mid-flush: nothing further is sent or marked.
    case ownerChanged(synced: Int)
  }

  /// The flush itself, over any database and transport: compact once, then ship the meeting's
  /// pending rows in batches the sync route accepts, until none remain or `shouldContinue` (the pass
  /// deadline) says stop. Stopping early is a fail-open path — the notes proceed without the rest of
  /// the call's screen text — so every early stop records degraded telemetry.
  @discardableResult
  static func flushMeetingWindow(
    _ interval: DateInterval,
    batchSize: Int = meetingFlushBatchSize,
    database: any DatabaseWriter,
    push: ([[String: Any]]) async -> Bool,
    authorizationIsCurrent: () -> Bool = { true },
    cloudAllowed: () -> Bool = { true },
    mutation: LocalMutationAuthorization = .unrestricted,
    shouldContinue: () -> Bool,
    recordFallback: (String) -> Void,
    isolation: isolated (any Actor)? = #isolation
  ) async -> MeetingFlushResult {
    var synced = 0
    do {
      // `getDBPool()` may have suspended across an account switch: nothing is written, not even
      // compaction, unless the captured owner is still the signed-in one.
      guard authorizationIsCurrent() else {
        log("ScreenActivitySync: meeting flush not started; signed-in account changed")
        recordFallback("auth")
        return .ownerChanged(synced: 0)
      }
      try await mutation.withCommitLease {
        try await database.write { db in
          try mutation.require()
          try compactMeetingWindow(db: db, interval: interval)
          try mutation.require()
        }
      }
      while true {
        let fetched = try await database.read { db in
          try fetchMeetingWindowCandidates(db: db, interval: interval, limit: batchSize)
        }
        let includeVectors = cloudAllowed()
        let candidates = fetched.map { candidate in
          var payload = candidate.payload
          if !includeVectors { payload.removeValue(forKey: "embedding") }
          return ScreenActivitySyncCandidate(
            id: candidate.id, priorState: candidate.priorState,
            hasEmbedding: includeVectors && candidate.hasEmbedding, payload: payload)
        }
        guard !candidates.isEmpty else { break }
        guard authorizationIsCurrent() else {
          log("ScreenActivitySync: meeting flush stopped; signed-in account changed")
          recordFallback("auth")
          return .ownerChanged(synced: synced)
        }
        guard shouldContinue() else {
          log("ScreenActivitySync: meeting flush stopped at the deadline after \(synced) rows")
          recordFallback("timeout")
          return .deadlineReached(synced: synced)
        }
        guard await push(candidates.map(\.payload)) else {
          if !authorizationIsCurrent() {
            log("ScreenActivitySync: meeting flush push abandoned; signed-in account changed")
            recordFallback("auth")
            return .ownerChanged(synced: synced)
          }
          log("ScreenActivitySync: meeting flush push failed; periodic sync will retry")
          recordFallback("upload_failed")
          return .pushFailed(synced: synced)
        }
        guard authorizationIsCurrent() else {
          log("ScreenActivitySync: meeting flush stopped after a push; signed-in account changed")
          recordFallback("auth")
          return .ownerChanged(synced: synced)
        }
        try await mutation.withCommitLease {
          try await database.write { db in
            try mutation.require()
            try markCandidatesSynced(db: db, candidates: candidates)
            try mutation.require()
          }
        }
        synced += candidates.count
      }
    } catch LocalMutationAuthorizationError.revoked {
      log("ScreenActivitySync: meeting flush write refused; signed-in account changed")
      recordFallback("auth")
      return .ownerChanged(synced: synced)
    } catch {
      log("ScreenActivitySync: meeting flush read/write error — \(error.localizedDescription)")
      recordFallback("other")
      return .databaseFailed(synced: synced)
    }
    guard synced > 0 else { return .nothingPending }
    log("ScreenActivitySync: meeting flush synced \(synced) rows")
    return .synced(synced)
  }

  /// `compactClosedBuckets` restricted to one meeting interval, without waiting for the bucket to
  /// close. Same partition and ranking, so a row it keeps is a row the periodic path would rank.
  static func compactMeetingWindow(db: Database, interval: DateInterval) throws {
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
            AND timestamp >= ? AND timestamp <= ?
        )
        UPDATE screenshots
        SET screenActivitySyncState = ?
        WHERE id IN (SELECT id FROM ranked WHERE bucketRank > 1)
        """,
      arguments: [
        ScreenActivitySyncState.pending.rawValue,
        interval.start, interval.end,
        ScreenActivitySyncState.compacted.rawValue,
      ])
  }

  static func fetchMeetingWindowCandidates(
    db: Database, interval: DateInterval, limit: Int
  ) throws -> [ScreenActivitySyncCandidate] {
    let rows = try Row.fetchAll(
      db,
      sql: """
        SELECT id, timestamp, appName, windowTitle, ocrText, embedding, deviceName, clientDeviceId,
               screenActivitySyncState
        FROM screenshots
        WHERE screenActivitySyncState = ?
          AND ocrText IS NOT NULL
          AND LENGTH(TRIM(ocrText)) > 0
          AND timestamp >= ? AND timestamp <= ?
        ORDER BY id ASC
        LIMIT ?
        """,
      arguments: [ScreenActivitySyncState.pending.rawValue, interval.start, interval.end, limit])
    return rows.compactMap(syncCandidate(from:))
  }

  private func recordPushFailure(path: String) {
    consecutiveFailures += 1
    if consecutiveFailures == 1 || consecutiveFailures % 10 == 0 {
      log("ScreenActivitySync: \(path) push failed (failures=\(consecutiveFailures))")
    }
  }

  /// Deliver finalized OCR independently of vectors. The cursor waits for open
  /// buckets; rows with no OCR are valid empty captures and must not stall it.
  static func fetchLegacySyncRows(
    db: Database, afterId: Int64, limit: Int, now: Date, cloudAllowed: Bool = true
  ) throws -> [Row] {
    try Row.fetchAll(
      db,
      sql: """
        SELECT id, timestamp, appName, windowTitle, ocrText, embedding, deviceName, clientDeviceId,
               screenActivitySyncState
        FROM screenshots
        WHERE (screenActivitySyncState = 0 AND id > ? AND ocrText IS NOT NULL AND LENGTH(TRIM(ocrText)) > 0
          AND id < COALESCE((SELECT MIN(id) FROM screenshots WHERE id > ? AND
            (CAST(strftime('%s', timestamp) AS INTEGER) / 300 + 1) * 300 > ?), 9223372036854775807))
          OR (screenActivitySyncState = 1 AND embedding IS NOT NULL AND ?)
        ORDER BY CASE screenActivitySyncState WHEN 1 THEN 0 ELSE 1 END, id ASC LIMIT ?
        """, arguments: [afterId, afterId, now.timeIntervalSince1970, cloudAllowed, max(0, min(limit, 100))])
  }

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
    db: Database, limit: Int, now: Date, slack: TimeInterval, embeddingGrace: TimeInterval, cloudAllowed: Bool = true
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
          AND embedding IS NOT NULL AND ?
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
        ScreenActivitySyncState.textSynced.rawValue, cloudAllowed, limit,
      ])

    return rows.compactMap(syncCandidate(from:))
  }

  static func syncCandidate(from row: Row) -> ScreenActivitySyncCandidate? {
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

  /// Whether a push continues into frame-request delivery. Only the periodic path does; the
  /// owner-bound meeting flush leaves delivery to it.
  static func deliversFrameRequests(ownerBoundPush: Bool) -> Bool { !ownerBoundPush }

  static func terminalStopReason(statusCode: Int, responseBody: String) -> String? {
    if statusCode == 401 { return "unauthorized_after_refresh" }
    if statusCode == 403 && responseBody.contains("account_deletion_in_progress") {
      return "account_deletion_in_progress"
    }
    return nil
  }

  /// With `authorizationSnapshot` the push is owner-bound: headers are minted for that owner only,
  /// and the request is abandoned if the session changed while they were built.
  private func pushRows(
    _ rows: [[String: Any]], authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot? = nil, periodic: Bool = false
  ) async -> Bool {
    let accountGeneration = await MainActor.run {
      AccountCutoverControlManager.shared.control.accountGeneration
    }
    let retentionDays = RewindSettings.shared.retentionDays
    // This generation is read from the server-authoritative cutover
    // projection, never inferred from local queue state.
    let payload = Self.frameRequestSyncPayload(
      rows: rows, accountGeneration: accountGeneration, retentionDays: retentionDays)

    guard let jsonData = try? JSONSerialization.data(withJSONObject: payload) else {
      log("ScreenActivitySync: JSON serialization error")
      return false
    }

    do {
      if let authorizationSnapshot, !RuntimeOwnerIdentity.isAuthorizationCurrent(authorizationSnapshot) {
        return false
      }
      let headers = try await APIClient.shared.buildHeaders(expectedAuthOwnerId: authorizationSnapshot?.ownerID)
      if let authorizationSnapshot, !RuntimeOwnerIdentity.isAuthorizationCurrent(authorizationSnapshot) {
        log("ScreenActivitySync: signed-in account changed while preparing a push; not sent")
        return false
      }
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

      if let authorizationSnapshot {
        guard RuntimeOwnerIdentity.isAuthorizationCurrent(authorizationSnapshot) else { return false }
        if rows.contains(where: { $0["embedding"] != nil }),
          !ScreenCloudEntitlementService.shared.allowsCloud(authorizationSnapshot)
        {
          return false
        }
      }
      var (data, response) = try await URLSession.shared.data(for: request)
      if let authorizationSnapshot, !RuntimeOwnerIdentity.isAuthorizationCurrent(authorizationSnapshot) { return false }
      guard var httpResponse = response as? HTTPURLResponse else { return false }

      if httpResponse.statusCode == 401 {
        let refreshedHeaders = try await APIClient.shared.buildHeaders(
          forceRefreshAuth: true, expectedAuthOwnerId: authorizationSnapshot?.ownerID)
        if let authorizationSnapshot {
          guard RuntimeOwnerIdentity.isAuthorizationCurrent(authorizationSnapshot) else {
            log("ScreenActivitySync: signed-in account changed during auth refresh; not retried")
            return false
          }
          if rows.contains(where: { $0["embedding"] != nil }),
            !ScreenCloudEntitlementService.shared.allowsCloud(authorizationSnapshot)
          {
            return false
          }
        }
        request.allHTTPHeaderFields = refreshedHeaders
        (data, response) = try await URLSession.shared.data(for: request)
        if let authorizationSnapshot, !RuntimeOwnerIdentity.isAuthorizationCurrent(authorizationSnapshot) {
          return false
        }
        guard let refreshedResponse = response as? HTTPURLResponse else { return false }
        httpResponse = refreshedResponse
      }

      if httpResponse.statusCode == 200 {
        let syncResponse = try JSONDecoder().decode(OmiAPI.ScreenActivitySyncResponse.self, from: data)
        guard let delivered = syncResponse.frameRequests, !delivered.isEmpty else {
          return true
        }
        guard Self.deliversFrameRequests(ownerBoundPush: authorizationSnapshot != nil && !periodic) else {
          // The rows landed. The owner-bound meeting flush never continues into pixel claims and
          // uploads: those read the Rewind store across further awaits, where an account switch
          // could pair one owner's pixels with another's session. The backend returns recoverable
          // requests on every sync response, so the periodic path delivers them.
          return true
        }
        let deviceID = ClientDeviceService.shared.clientDeviceId
        // Validate the entire batch before claiming any row. A mixed-device or
        // mixed-generation response must never partially move the queue.
        guard delivered.count <= 32,
          delivered.allSatisfy({
            $0.deviceId == deviceID && $0.accountGeneration == accountGeneration
              && ["requested", "claimed", "uploaded"].contains($0.state)
          }),
          Set(delivered.map(\.requestId)).count == delivered.count
        else {
          log("ScreenActivitySync: rejected malformed frame-request batch")
          return false
        }
        guard
          await claimFrameRequests(
            delivered,
            deviceID: deviceID,
            accountGeneration: accountGeneration,
            headers: headers,
            baseURL: baseURL, authorizationSnapshot: authorizationSnapshot
          )
        else { return false }
        // Claiming is the queue ownership fence. Only after the whole batch is
        // claimed do we read local pixels and upload/promote them.
        return await uploadAndPromoteFrameRequests(
          delivered,
          deviceID: deviceID,
          accountGeneration: accountGeneration,
          headers: headers,
          baseURL: baseURL, authorizationSnapshot: authorizationSnapshot
        )
      } else {
        let body = String(data: data, encoding: .utf8) ?? ""
        if let reason = Self.terminalStopReason(statusCode: httpResponse.statusCode, responseBody: body) {
          log("ScreenActivitySync: stopping after terminal response (\(reason))")
          stop(logStopped: false)
          return false
        }
        log("ScreenActivitySync: HTTP \(httpResponse.statusCode)")
        return false
      }
    } catch {
      log("ScreenActivitySync: network error — \(error.localizedDescription)")
      return false
    }
  }

  private func claimFrameRequests(
    _ requests: [OmiAPI.FrameRequestDelivery],
    deviceID: String,
    accountGeneration: Int,
    headers: [String: String],
    baseURL: String, authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot? = nil
  ) async -> Bool {
    for item in requests {
      if let authorizationSnapshot, !RuntimeOwnerIdentity.isAuthorizationCurrent(authorizationSnapshot) { return false }
      if !Self.shouldClaimFrameRequest(state: item.state) { continue }
      guard let url = URL(string: baseURL + "v1/frame-requests/\(item.requestId)/state") else { return false }
      let body: [String: Any] = [
        "state": "claimed",
        "device_id": deviceID,
        "account_generation": accountGeneration,
      ]
      guard let encoded = try? JSONSerialization.data(withJSONObject: body) else { return false }
      var claim = URLRequest(url: url)
      claim.httpMethod = "POST"
      claim.httpBody = encoded
      claim.timeoutInterval = 30
      for (key, value) in headers {
        claim.setValue(value, forHTTPHeaderField: key)
      }
      if let authorizationSnapshot, !RuntimeOwnerIdentity.isAuthorizationCurrent(authorizationSnapshot) { return false }
      guard let result = try? await URLSession.shared.data(for: claim),
        (result.1 as? HTTPURLResponse)?.statusCode == 200
      else {
        log("ScreenActivitySync: frame-request claim failed")
        return false
      }
    }
    return true
  }

  private func uploadAndPromoteFrameRequests(
    _ requests: [OmiAPI.FrameRequestDelivery],
    deviceID: String,
    accountGeneration: Int,
    headers: [String: String],
    baseURL: String, authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot? = nil
  ) async -> Bool {
    for item in requests {
      if let authorizationSnapshot, !RuntimeOwnerIdentity.isAuthorizationCurrent(authorizationSnapshot) { return false }
      // Requested/claimed are recoverable uploads. Uploaded rows are
      // recoverable promotions and must not upload a second pixel object.
      if Self.shouldUploadFrameRequest(state: item.state) {
        guard let screenshotID = item.screenshotId.flatMap(Int64.init),
          let screenshot = try? await RewindDatabase.shared.getScreenshot(id: screenshotID),
          let data = try? await RewindStorage.shared.loadScreenshotData(for: screenshot),
          data.count <= 10 * 1024 * 1024,
          let uploadURL = URL(
            string: baseURL
              + "v1/frame-requests/\(item.requestId)/upload?device_id=\(deviceID.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? deviceID)&account_generation=\(accountGeneration)"
          )
        else {
          // A request may target an already-pruned local capture. Never hide
          // a terminal-update failure; leaving it claimed lets the next sync
          // retry or the retention worker reap it safely.
          guard
            await failFrameRequest(
              item, deviceID: deviceID, accountGeneration: accountGeneration,
              reason: "screenshot_unavailable", headers: headers, baseURL: baseURL,
              authorizationSnapshot: authorizationSnapshot
            )
          else { return false }
          continue
        }
        let boundary = "omi-frame-\(UUID().uuidString)"
        var body = Data()
        body.append(Data("--\(boundary)\r\n".utf8))
        body.append(Data("Content-Disposition: form-data; name=\"file\"; filename=\"frame.jpg\"\r\n".utf8))
        body.append(Data("Content-Type: image/jpeg\r\n\r\n".utf8))
        body.append(data)
        body.append(Data("\r\n--\(boundary)--\r\n".utf8))
        var upload = URLRequest(url: uploadURL)
        upload.httpMethod = "POST"
        upload.httpBody = body
        upload.timeoutInterval = 60
        upload.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")
        for (key, value) in headers { upload.setValue(value, forHTTPHeaderField: key) }
        if let authorizationSnapshot, !RuntimeOwnerIdentity.isAuthorizationCurrent(authorizationSnapshot) {
          return false
        }
        guard let uploadResult = try? await URLSession.shared.data(for: upload),
          (uploadResult.1 as? HTTPURLResponse)?.statusCode == 200
        else { return false }
      }

      if let authorizationSnapshot, !RuntimeOwnerIdentity.isAuthorizationCurrent(authorizationSnapshot) { return false }
      if let conversationID = item.conversationId,
        let promoteURL = URL(string: baseURL + "v1/frame-requests/\(item.requestId)/promote")
      {
        let promoteBody: [String: Any] = [
          "device_id": deviceID,
          "account_generation": accountGeneration,
          "conversation_id": conversationID,
        ]
        guard let promoteData = try? JSONSerialization.data(withJSONObject: promoteBody) else { return false }
        var promote = URLRequest(url: promoteURL)
        promote.httpMethod = "POST"
        promote.httpBody = promoteData
        promote.timeoutInterval = 30
        promote.setValue("application/json", forHTTPHeaderField: "Content-Type")
        for (key, value) in headers { promote.setValue(value, forHTTPHeaderField: key) }
        guard let promoteResult = try? await URLSession.shared.data(for: promote),
          (promoteResult.1 as? HTTPURLResponse)?.statusCode == 200
        else { return false }
      }
    }
    return true
  }

  private func failFrameRequest(
    _ item: OmiAPI.FrameRequestDelivery,
    deviceID: String,
    accountGeneration: Int,
    reason: String,
    headers: [String: String],
    baseURL: String, authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot? = nil
  ) async -> Bool {
    guard let url = URL(string: baseURL + "v1/frame-requests/\(item.requestId)/state"),
      let data = try? JSONSerialization.data(withJSONObject: [
        "state": reason == "screenshot_unavailable" ? "pruned" : "failed",
        "device_id": deviceID,
        "account_generation": accountGeneration,
        "terminal_reason": reason,
      ])
    else { return false }
    var request = URLRequest(url: url)
    request.httpMethod = "POST"
    request.httpBody = data
    for (key, value) in headers { request.setValue(value, forHTTPHeaderField: key) }
    if let authorizationSnapshot, !RuntimeOwnerIdentity.isAuthorizationCurrent(authorizationSnapshot) { return false }
    guard let result = try? await URLSession.shared.data(for: request) else { return false }
    return (result.1 as? HTTPURLResponse)?.statusCode == 200
  }

  // MARK: - Database access

  private func getDBPool() async -> DatabasePool? {
    try? await RewindDatabase.shared.initialize()
    return await RewindDatabase.shared.getDatabaseQueue()
  }

  // MARK: - Cursor persistence

  private func loadCursor(authorization: RuntimeOwnerAuthorizationSnapshot?) {
    cursorOwner = authorization
    lastSyncedId = authorization.flatMap { try? cursorStore.load(authorization: $0) } ?? 0
  }

  private func saveCursor(_ cursor: Int64, authorization: RuntimeOwnerAuthorizationSnapshot) async throws {
    guard cursorOwner == authorization, RuntimeOwnerIdentity.isAuthorizationCurrent(authorization) else { return }
    let saved = try await cursorStore.save(cursor, authorization: authorization)
    guard cursorOwner == authorization, RuntimeOwnerIdentity.isAuthorizationCurrent(authorization) else { return }
    lastSyncedId = max(lastSyncedId, saved)
  }
}
