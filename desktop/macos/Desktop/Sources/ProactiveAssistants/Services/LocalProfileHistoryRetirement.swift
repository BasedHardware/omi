import Foundation
@preconcurrency import GRDB

/// Retirement of the local profile history table that released builds wrote.
///
/// Released builds committed every generation and edit to `ai_user_profiles` first and mirrored
/// it to the backend with a fire-and-forget PATCH whose failure was only logged, so the newest
/// row can be the only copy of a profile or a user correction. The table is therefore not
/// dropped by a migration: after the first successful backend read for an owner, the profile
/// service uploads that row when the backend lacks it, and drops the table only once nothing in
/// it is newer than the backend. A failed upload keeps the table for the next launch.
///
/// The Rewind database is per owner, so every step is bound to the owner whose read started it
/// (INV-AUTH-1): rows are read, uploaded and dropped only while that owner, with that session,
/// is still the one signed in.
enum LocalProfileHistoryRetirement {
  static let table = "ai_user_profiles"

  /// A failed read or an owner change; the table stays for the next attempt.
  enum Failure: Error, Equatable {
    case databaseUnavailable
  }

  /// What the owner's database holds.
  enum Contents: Equatable, Sendable {
    /// The table is gone: nothing to salvage or drop.
    case retired
    /// The table exists; its newest row, or nil when it is empty.
    case history(newest: Row?)
  }

  /// The newest row of the retired table.
  struct Row: Equatable, Sendable {
    let text: String
    let generatedAt: Date
    let backendSynced: Bool

    /// Whether this row holds text the backend does not have.
    ///
    /// - An unsynced row newer than the backend's profile (or with no backend profile) is a
    ///   generation or correction whose mirror PATCH failed.
    /// - A row of the same generation as a profile the released mirror wrote (`source` nil or
    ///   `client`) but with different text is an edit whose mirror PATCH failed: released builds
    ///   edited the row in place and never cleared `backendSynced`.
    func needsUpload(over cloud: CloudState?) -> Bool {
      let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
      guard !trimmed.isEmpty else { return false }
      guard let cloud else { return !backendSynced }
      guard let cloudGeneratedAt = cloud.generatedAt else { return false }
      let delta = generatedAt.timeIntervalSince(cloudGeneratedAt)
      // The released mirror sent milliseconds; generations are a day apart.
      let sameGeneration = abs(delta) < 1
      if !backendSynced, !sameGeneration, delta > 0 { return true }
      let mirrored = cloud.source == nil || cloud.source == "client"
      return sameGeneration && mirrored
        && trimmed != cloud.text.trimmingCharacters(in: .whitespacesAndNewlines)
    }
  }

  /// The backend's profile, as far as the salvage decision needs it.
  struct CloudState: Equatable, Sendable {
    let text: String
    let generatedAt: Date?
    let source: String?
  }

  /// The owner a salvage is bound to.
  struct Owner: Sendable {
    /// Pins the upload's transport auth; nil only for a test binding.
    let snapshot: RuntimeOwnerAuthorizationSnapshot?
    /// Whether that owner, with that session, is still the one signed in.
    let isCurrent: @Sendable () -> Bool
  }

  /// How one salvage attempt ended.
  enum Outcome: Equatable, Sendable {
    /// The table was already gone.
    case retired
    /// Nothing needed uploading and the table was dropped.
    case dropped
    /// The newest row was uploaded; `dropped` is false when the drop must wait for a later launch.
    case restored(AIUserProfile?, dropped: Bool)
    /// The read or upload failed, or the owner or profile changed: the table stays.
    case kept
  }

  // MARK: Database

  static func contents(_ db: Database) throws -> Contents {
    guard try db.tableExists(table) else { return .retired }
    guard
      let row = try GRDB.Row.fetchOne(
        db,
        sql: """
          SELECT profileText, generatedAt, backendSynced FROM \(table)
          ORDER BY generatedAt DESC, id DESC LIMIT 1
          """)
    else { return .history(newest: nil) }
    // Non-trapping conversions: a malformed legacy cell must not crash the app.
    guard let text = String.fromDatabaseValue(row["profileText"] as DatabaseValue),
      let generatedAt = Date.fromDatabaseValue(row["generatedAt"] as DatabaseValue)
    else { return .history(newest: nil) }
    let backendSynced = Bool.fromDatabaseValue(row["backendSynced"] as DatabaseValue) ?? false
    return .history(newest: Row(text: text, generatedAt: generatedAt, backendSynced: backendSynced))
  }

  static func drop(_ db: Database) throws {
    try db.execute(sql: "DROP TABLE IF EXISTS \(table)")
  }

  // MARK: Salvage

  /// One salvage attempt. `mayWrite` is the service's own fence (same owner session, no profile
  /// mutation since the read that `cloud` came from); it is checked before the upload.
  static func salvage(
    cloud: CloudState?,
    owner: Owner,
    store: Store,
    mayWrite: @Sendable () async -> Bool
  ) async -> Outcome {
    do {
      guard case .history(let newest) = try await store.contents(owner) else { return .retired }
      guard let newest, newest.needsUpload(over: cloud) else {
        guard owner.isCurrent() else { return .kept }
        try await store.drop(owner)
        log("LocalProfileHistory: nothing newer than the backend; dropped the retired table")
        return .dropped
      }
      guard await mayWrite(), owner.isCurrent() else {
        log("LocalProfileHistory: owner or profile changed before upload; keeping the retired table")
        return .kept
      }
      let restored = try await store.upload(newest, owner)
      log("LocalProfileHistory: uploaded the unsynced local profile (\(newest.text.count) chars)")
      do {
        guard owner.isCurrent() else { return .restored(restored, dropped: false) }
        try await store.drop(owner)
        return .restored(restored, dropped: true)
      } catch {
        log("LocalProfileHistory: drop after upload failed: \(error.localizedDescription)")
        return .restored(restored, dropped: false)
      }
    } catch {
      log("LocalProfileHistory: salvage deferred to the next launch: \(error.localizedDescription)")
      return .kept
    }
  }

  /// Database and network seam for the salvage; tests inject a fake.
  struct Store: Sendable {
    var bindOwner: @Sendable () -> Owner?
    var contents: @Sendable (Owner) async throws -> Contents
    var upload: @Sendable (Row, Owner) async throws -> AIUserProfile?
    var drop: @Sendable (Owner) async throws -> Void

    /// Never binds an owner, so no salvage runs.
    static let inert = Store(
      bindOwner: { nil },
      contents: { _ in .retired },
      upload: { _, _ in nil },
      drop: { _ in })

    static let live = Store(
      bindOwner: {
        guard let snapshot = RuntimeOwnerIdentity.captureAuthorizationSnapshot() else { return nil }
        return Owner(snapshot: snapshot, isCurrent: { RuntimeOwnerIdentity.isAuthorizationCurrent(snapshot) })
      },
      contents: { owner in
        let pool = try await ownerPool(owner)
        let contents = try await pool.read { db in try LocalProfileHistoryRetirement.contents(db) }
        // The pool is the owner's only if the owner was still signed in after the read.
        guard owner.isCurrent() else { throw LocalMutationAuthorizationError.revoked }
        return contents
      },
      upload: { row, owner in
        guard let snapshot = owner.snapshot, owner.isCurrent() else { throw AuthError.userChangedDuringRequest }
        return AIUserProfile(
          try await APIClient.shared.restoreLocalProfile(
            profileText: row.text, generatedAt: row.generatedAt, authorizationSnapshot: snapshot))
      },
      drop: { owner in
        let pool = try await ownerPool(owner)
        let mutation = LocalMutationAuthorization(owner.isCurrent)
        try await mutation.withCommitLease {
          try await pool.write { db in
            try mutation.require()
            try LocalProfileHistoryRetirement.drop(db)
          }
        }
      })

    private static func ownerPool(_ owner: Owner) async throws -> DatabasePool {
      guard owner.isCurrent() else { throw LocalMutationAuthorizationError.revoked }
      guard let pool = try await RewindRepository(owner: "LocalProfileHistory").databasePool() else {
        throw Failure.databaseUnavailable
      }
      return pool
    }
  }
}

extension LocalProfileHistoryRetirement.CloudState {
  init(_ profile: AIUserProfile) {
    self.init(text: profile.profileText, generatedAt: profile.generatedAt, source: profile.source)
  }
}
