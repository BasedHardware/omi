import Foundation

/// Response wrapper for GET v1/action-items/ids (lightweight reconcile source).
struct ActionItemIdsResponse: Decodable {
  let ids: [String]
}

extension APIClient {
  /// Fetch action items through an immutable owner-bound request. Callers that
  /// span pagination must pass the same owner to every page.
  func getActionItems(
    limit: Int = 100,
    offset: Int = 0,
    completed: Bool? = nil,
    startDate: Date? = nil,
    endDate: Date? = nil,
    dueStartDate: Date? = nil,
    dueEndDate: Date? = nil,
    sortBy: String? = nil,
    deleted: Bool? = nil,
    expectedOwnerId: String? = nil,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot? = nil
  ) async throws -> ActionItemsListResponse {
    let formatter = ISO8601DateFormatter()
    formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
    var queryItems = ["limit=\(limit)", "offset=\(offset)"]
    if let completed { queryItems.append("completed=\(completed)") }
    if let startDate { queryItems.append("start_date=\(formatter.string(from: startDate))") }
    if let endDate { queryItems.append("end_date=\(formatter.string(from: endDate))") }
    if let dueStartDate { queryItems.append("due_start_date=\(formatter.string(from: dueStartDate))") }
    if let dueEndDate { queryItems.append("due_end_date=\(formatter.string(from: dueEndDate))") }
    if let sortBy { queryItems.append("sort_by=\(sortBy)") }
    if let deleted { queryItems.append("deleted=\(deleted)") }
    return try await get(
      "v1/action-items?\(queryItems.joined(separator: "&"))",
      expectedOwnerId: expectedOwnerId,
      authorizationSnapshot: authorizationSnapshot
    )
  }

  /// Fetch every action-item ID for the signed-in user (IDs only, no fields).
  /// Used as an independent confirmation before an empty incomplete-task page
  /// is allowed to reconcile (wipe) synced local rows.
  func getActionItemIds(
    expectedOwnerId: String? = nil,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot? = nil
  ) async throws -> [String] {
    let response: ActionItemIdsResponse = try await get(
      "v1/action-items/ids",
      expectedOwnerId: expectedOwnerId,
      authorizationSnapshot: authorizationSnapshot
    )
    return response.ids
  }

  func migrateStagedTasks(
    expectedOwnerId: String? = nil,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot? = nil
  ) async throws {
    struct StatusResponse: Decodable { let status: String }
    let _: StatusResponse = try await post(
      "v1/staged-tasks/migrate",
      expectedOwnerId: expectedOwnerId,
      authorizationSnapshot: authorizationSnapshot
    )
  }

  func migrateConversationItemsToStaged(
    expectedOwnerId: String? = nil,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot? = nil
  ) async throws {
    struct MigrateResponse: Decodable {
      let status: String
      let migrated: Int
      let deleted: Int
    }
    let _: MigrateResponse = try await post(
      "v1/staged-tasks/migrate-conversation-items",
      expectedOwnerId: expectedOwnerId,
      authorizationSnapshot: authorizationSnapshot
    )
  }

  func batchUpdateScores(
    _ scores: [(id: String, score: Int)],
    expectedOwnerId: String? = nil,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot? = nil
  ) async throws {
    struct ScoreUpdate: Encodable {
      let id: String
      let relevance_score: Int
    }
    struct BatchRequest: Encodable { let scores: [ScoreUpdate] }
    struct StatusResponse: Decodable { let status: String }
    let request = BatchRequest(
      scores: scores.map { ScoreUpdate(id: $0.id, relevance_score: $0.score) })
    let _: StatusResponse = try await patch(
      "v1/action-items/batch-scores",
      body: request,
      expectedOwnerId: expectedOwnerId,
      authorizationSnapshot: authorizationSnapshot)
  }

  func batchUpdateSortOrders(
    _ updates: [(id: String, sortOrder: Int, indentLevel: Int)],
    expectedOwnerId: String? = nil,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot? = nil
  ) async throws {
    struct SortUpdate: Encodable {
      let id: String
      let sort_order: Int
      let indent_level: Int
    }
    struct BatchRequest: Encodable { let items: [SortUpdate] }
    struct StatusResponse: Decodable { let status: String }
    let request = BatchRequest(
      items: updates.map {
        SortUpdate(id: $0.id, sort_order: $0.sortOrder, indent_level: $0.indentLevel)
      })
    let _: StatusResponse = try await patch(
      "v1/action-items/batch",
      body: request,
      expectedOwnerId: expectedOwnerId,
      authorizationSnapshot: authorizationSnapshot)
  }

  // MARK: - Workstream-backed task threads

  func resolveTaskWorkIntent(
    taskId: String,
    title: String?,
    objective: String?,
    idempotencyKey: String,
    accountGeneration: Int,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot? = nil
  ) async throws -> OmiAPI.WorkIntentReceipt {
    try await taskIntelligenceMutation(
      endpoint: "v1/work-intents",
      method: "POST",
      body: OmiAPI.TaskOriginWorkIntent(
        objective: objective,
        origin: "task",
        taskId: taskId,
        title: title
      ),
      idempotencyKey: idempotencyKey,
      accountGeneration: accountGeneration,
      expectedOwnerId: authorizationSnapshot?.ownerID,
      authorizationSnapshot: authorizationSnapshot
    )
  }

  func resolveGoalWorkIntent(
    goalId: String,
    title: String,
    objective: String,
    anchorTaskDescription: String,
    idempotencyKey: String,
    accountGeneration: Int,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot? = nil
  ) async throws -> OmiAPI.WorkIntentReceipt {
    try await taskIntelligenceMutation(
      endpoint: "v1/work-intents",
      method: "POST",
      body: OmiAPI.GoalOriginWorkIntent(
        anchorTaskDescription: anchorTaskDescription,
        goalId: goalId,
        objective: objective,
        origin: "goal",
        title: title
      ),
      idempotencyKey: idempotencyKey,
      accountGeneration: accountGeneration,
      expectedOwnerId: authorizationSnapshot?.ownerID,
      authorizationSnapshot: authorizationSnapshot
    )
  }

  func getWorkstreamDetail(
    workstreamId: String,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot? = nil
  ) async throws -> OmiAPI.WorkstreamDetailProjection {
    try await get(
      "v1/workstreams/\(workstreamId)",
      expectedOwnerId: authorizationSnapshot?.ownerID,
      authorizationSnapshot: authorizationSnapshot)
  }

  func createWorkstreamArtifact(
    workstreamId: String,
    artifact: OmiAPI.ArtifactDescriptorCreate,
    idempotencyKey: String,
    accountGeneration: Int,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot? = nil
  ) async throws -> OmiAPI.ArtifactDescriptor {
    try await taskIntelligenceMutation(
      endpoint: "v1/workstreams/\(workstreamId)/artifacts",
      method: "POST",
      body: artifact,
      idempotencyKey: idempotencyKey,
      accountGeneration: accountGeneration,
      expectedOwnerId: authorizationSnapshot?.ownerID,
      authorizationSnapshot: authorizationSnapshot
    )
  }

  func upsertWorkstreamCheckpoint(
    workstreamId: String,
    runtimeId: String,
    checkpoint: OmiAPI.ContinuationCheckpointUpsert,
    idempotencyKey: String,
    accountGeneration: Int,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot? = nil
  ) async throws -> OmiAPI.ContinuationCheckpoint {
    try await taskIntelligenceMutation(
      endpoint: "v1/workstreams/\(workstreamId)/checkpoints/\(runtimeId)",
      method: "PUT",
      body: checkpoint,
      idempotencyKey: idempotencyKey,
      accountGeneration: accountGeneration,
      expectedOwnerId: authorizationSnapshot?.ownerID,
      authorizationSnapshot: authorizationSnapshot
    )
  }
}
