import Foundation

/// Effects used by the existing owner-fenced retry loop. Tests can drive the
/// actual loop without touching a customer database or backend.
@MainActor
struct UnsyncedTaskSyncOperations {
  let allowsUpload: @MainActor () async -> Bool
  let loadPending: @MainActor (Bool) async throws -> [ActionItemRecord]
  let reloadCurrent: @MainActor (Int64) async throws -> ActionItemRecord?
  let createRemote:
    @MainActor (UnsyncedTaskCreateProjection, RuntimeOwnerAuthorizationSnapshot) async throws -> TaskActionItem
  private let markSyncedOperation: @MainActor (Int64, String, LocalMutationAuthorization) async throws -> Void
  let flushDeletions: (@MainActor () async -> Void)?

  init(
    allowsUpload: @escaping @MainActor () async -> Bool = {
      await AccountCutoverOfflineUploadAdmission.allowsUploadOffMainActor()
    },
    loadPending: @escaping @MainActor (Bool) async throws -> [ActionItemRecord] = {
      try await ActionItemStorage.shared.getUnsyncedActionItems(includeRecent: $0)
    },
    reloadCurrent: @escaping @MainActor (Int64) async throws -> ActionItemRecord? = {
      try await ActionItemStorage.shared.getActionItem(id: $0)
    },
    createRemote:
      @escaping @MainActor (UnsyncedTaskCreateProjection, RuntimeOwnerAuthorizationSnapshot) async throws ->
      TaskActionItem = {
        try await $0.create(authorizationSnapshot: $1)
      },
    markSynced: @escaping @MainActor (Int64, String, LocalMutationAuthorization) async throws -> Void = {
      try await ActionItemStorage.shared.markSynced(
        id: $0,
        backendId: $1,
        authorization: $2)
    },
    flushDeletions: (@MainActor () async -> Void)? = nil
  ) {
    self.allowsUpload = allowsUpload
    self.loadPending = loadPending
    self.reloadCurrent = reloadCurrent
    self.createRemote = createRemote
    self.markSyncedOperation = markSynced
    self.flushDeletions = flushDeletions
  }

  func markSynced(id: Int64, backendId: String, authorization: LocalMutationAuthorization) async throws {
    try await markSyncedOperation(id, backendId, authorization)
  }
}
