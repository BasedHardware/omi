import Foundation

/// Only owner-scoped cursors carry provenance. The retired global key is never read.
final class ScreenActivityCursorStore: @unchecked Sendable {
  private let defaults: UserDefaults
  private let authority: EmbeddingOwnerAuthority
  private let lock = NSLock()

  init(defaults: UserDefaults = .standard, authority: EmbeddingOwnerAuthority = .runtime) {
    self.defaults = defaults
    self.authority = authority
  }

  func load(authorization: RuntimeOwnerAuthorizationSnapshot) throws -> Int64 {
    try lock.withLock {
      guard authority.isCurrent(authorization) else { throw LocalMutationAuthorizationError.revoked }
      return Int64(defaults.integer(forKey: .screenActivitySyncCursor(ownerID: authorization.ownerID)))
    }
  }

  /// A late vector can acknowledge an older row, but never move a cursor backwards.
  func save(_ candidate: Int64, authorization: RuntimeOwnerAuthorizationSnapshot) async throws -> Int64 {
    let mutation = LocalMutationAuthorization { [authority] in authority.isCurrent(authorization) }
    return try await mutation.withCommitLease { [self] in
      try lock.withLock {
        try mutation.require()
        let key = ScopedDefaultsKey.screenActivitySyncCursor(ownerID: authorization.ownerID)
        let cursor = max(Int64(defaults.integer(forKey: key)), candidate)
        defaults.set(Int(cursor), forKey: key)
        return cursor
      }
    }
  }
}
