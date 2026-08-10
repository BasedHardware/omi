import Foundation

/// Response wrapper for GET v1/action-items/ids (lightweight reconcile source).
struct ActionItemIdsResponse: Decodable {
  let ids: [String]
}

/// One bounded page from the marker-scoped legacy task recovery endpoint.
/// `nextCursor` is present only when `hasMore` is true, so callers can make
/// finite forward progress without marking recovery complete mid-sweep.
struct LegacyConversationRecoveryPage: Decodable, Equatable, Sendable {
  let restored: Int
  let skippedExisting: Int
  let hasMore: Bool
  let nextCursor: String?

  private enum CodingKeys: String, CodingKey {
    case restored
    case skippedExisting = "skipped_existing"
    case hasMore = "has_more"
    case nextCursor = "next_cursor"
  }
}

extension APIClient {
  /// The backend's action-item list orders every non-null `due_at` before the
  /// null bucket. Firestore inequality filters also exclude documents where
  /// `due_at` is missing/null, so this lower bound is the smallest supported
  /// query that returns only dated action items without materializing the
  /// No Deadline universe.
  static let earliestActionItemDueDate = Date(timeIntervalSince1970: -62_135_596_800)

  /// Matches `backend/database/action_items.py::_ACTION_ITEMS_LIST_HARD_MAX`.
  /// Offset pagination cannot scan beyond this many raw rows per query window.
  static let actionItemsListHardMax = 2000

  struct DatedActionItemsScanResult: Sendable {
    let items: [TaskActionItem]
    /// Raw rows consumed from the dated incomplete bucket in general list order.
    let boundaryOffset: Int
  }

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

  /// Fetch one page from the complete dated active/completed bucket. The
  /// lower-bound query intentionally has no upper bound: dated tasks in Today,
  /// Tomorrow, and Later must all be represented regardless of their year.
  func getDatedActionItems(
    limit: Int = 500,
    offset: Int = 0,
    completed: Bool,
    dueStartDate: Date? = nil,
    expectedOwnerId: String? = nil,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot? = nil
  ) async throws -> ActionItemsListResponse {
    try await getActionItems(
      limit: limit,
      offset: offset,
      completed: completed,
      dueStartDate: dueStartDate ?? Self.earliestActionItemDueDate,
      expectedOwnerId: expectedOwnerId,
      authorizationSnapshot: authorizationSnapshot
    )
  }

  /// Scan every dated row in the incomplete bucket. Offset pagination alone
  /// cannot cross `actionItemsListHardMax`, so this helper continues with a
  /// keyset window on `due_at` when the read cap is reached.
  func scanDatedIncompleteActionItems(
    completed: Bool,
    pageLimit: Int = 500,
    expectedOwnerId: String? = nil,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot? = nil
  ) async throws -> DatedActionItemsScanResult {
    var items: [TaskActionItem] = []
    var seenIDs = Set<String>()
    var dueStart = Self.earliestActionItemDueDate
    var boundaryOffset = 0

    while true {
      var pageOffset = 0
      var chunkHasMore = false
      var lastChunkDueAt: Date?

      while true {
        let page = try await getDatedActionItems(
          limit: pageLimit,
          offset: pageOffset,
          completed: completed,
          dueStartDate: dueStart,
          expectedOwnerId: expectedOwnerId,
          authorizationSnapshot: authorizationSnapshot
        )
        chunkHasMore = page.hasMore
        boundaryOffset += page.items.count
        lastChunkDueAt = page.items.compactMap(\.dueAt).max() ?? lastChunkDueAt

        for item in page.items where !seenIDs.contains(item.id) {
          seenIDs.insert(item.id)
          items.append(item)
        }

        if page.items.isEmpty || !page.hasMore { break }
        pageOffset += page.items.count
        if pageOffset + pageLimit > Self.actionItemsListHardMax { break }
      }

      if !chunkHasMore { break }
      guard let nextDueStart = lastChunkDueAt?.addingTimeInterval(0.001) else { break }
      if nextDueStart <= dueStart { break }
      dueStart = nextDueStart
    }

    return DatedActionItemsScanResult(items: items, boundaryOffset: boundaryOffset)
  }

  /// Fetch one No Deadline page from the general action-item ordering.
  ///
  /// The current backend has no `due_at IS NULL` query parameter. Its stable
  /// product ordering places all dated rows before null rows, so callers first
  /// count the dated bucket, then page from that boundary. `datedBoundaryOffset`
  /// must count raw API rows in general list order (including rows the caller
  /// later filters), not a deduplicated or client-filtered projection. The
  /// caller must still reject any non-null rows defensively because concurrent
  /// server mutations can change a page between requests.
  func getNoDeadlineActionItems(
    limit: Int = 100,
    offset: Int = 0,
    datedBoundaryOffset: Int,
    completed: Bool,
    expectedOwnerId: String? = nil,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot? = nil
  ) async throws -> ActionItemsListResponse {
    guard datedBoundaryOffset >= 0, offset >= 0 else { throw APIError.invalidResponse }
    let (generalOffset, overflow) = datedBoundaryOffset.addingReportingOverflow(offset)
    guard !overflow else { throw APIError.invalidResponse }
    return try await getActionItems(
      limit: limit,
      offset: generalOffset,
      completed: completed,
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

  /// Restore rows the retired migration moved out of action_items. A pre-fix
  /// backend returns a safe 404 for this new route, so a client update can never
  /// trigger the old destructive migration during a staggered rollout.
  func restoreLegacyConversationItems(
    limit: Int = 100,
    cursor: String? = nil,
    expectedOwnerId: String? = nil,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot? = nil
  ) async throws -> LegacyConversationRecoveryPage {
    precondition((1...100).contains(limit), "Legacy recovery page limit must be between 1 and 100")
    var path = "v1/action-items/restore-legacy-conversation-items?limit=\(limit)"
    if let cursor {
      let unreservedCharacters = CharacterSet(
        charactersIn: "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~"
      )
      guard let escapedCursor = cursor.addingPercentEncoding(withAllowedCharacters: unreservedCharacters) else {
        throw URLError(.badURL)
      }
      path += "&cursor=\(escapedCursor)"
    }
    return try await post(
      path,
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
    // The backend validates this endpoint's request body at 500 items. A
    // user's local task database can contain more rows than one request can
    // carry, so preserve order while sending bounded sequential requests. The
    // endpoint applies each document independently, so replay the complete
    // absolute update set once after a later chunk fails. Replaying an earlier
    // chunk is safe and can heal a transient failure without leaving the
    // caller with only the prefix applied; a second failure still propagates.
    let updateBatches = updates.chunked(maxSize: 500)
    var didRetry = false
    while true {
      do {
        for updateBatch in updateBatches {
          let request = BatchRequest(
            items: updateBatch.map {
              SortUpdate(id: $0.id, sort_order: $0.sortOrder, indent_level: $0.indentLevel)
            })
          let _: StatusResponse = try await patch(
            "v1/action-items/batch",
            body: request,
            expectedOwnerId: expectedOwnerId,
            authorizationSnapshot: authorizationSnapshot)
        }
        return
      } catch {
        guard !didRetry, Self.isRetryableSortOrderBatchError(error) else { throw error }
        didRetry = true
      }
    }
  }

  private static func isRetryableSortOrderBatchError(_ error: Error) -> Bool {
    if let apiError = error as? APIError {
      if case .httpError(let statusCode, _) = apiError {
        return statusCode >= 500
      }
      return false
    }
    if let urlError = error as? URLError {
      return urlError.code != .cancelled
    }
    return false
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
