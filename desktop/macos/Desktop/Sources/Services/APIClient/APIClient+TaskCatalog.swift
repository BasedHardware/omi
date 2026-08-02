import Foundation
import OmiWAL

// MARK: - Action Items API

/// Response wrapper for paginated action items list
/// Accepts both "action_items" (/v1/action-items) and "items" (/v1/staged-tasks) keys.
struct ActionItemsListResponse: Decodable {
  let items: [TaskActionItem]
  let hasMore: Bool

  enum CodingKeys: String, CodingKey {
    case actionItems = "action_items"
    case items
    case hasMore = "has_more"
  }

  init(from decoder: Decoder) throws {
    let container = try decoder.container(keyedBy: CodingKeys.self)
    if let actionItems = try container.decodeIfPresent([TaskActionItem].self, forKey: .actionItems) {
      self.items = actionItems
    } else {
      self.items = try container.decode([TaskActionItem].self, forKey: .items)
    }
    self.hasMore = try container.decode(Bool.self, forKey: .hasMore)
  }
}
extension APIClient {

  /// Fetches one action item by backend ID.
  func getActionItem(id: String) async throws -> TaskActionItem {
    try await getActionItem(id: id, expectedOwnerId: nil)
  }

  func getActionItem(
    id: String,
    expectedOwnerId: String?,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot? = nil
  ) async throws -> TaskActionItem {
    try await get(
      "v1/action-items/\(id)",
      expectedOwnerId: expectedOwnerId,
      authorizationSnapshot: authorizationSnapshot)
  }

  /// Updates an action item
  func updateActionItem(
    id: String,
    completed: Bool? = nil,
    description: String? = nil,
    dueAt: Date? = nil,
    clearDueAt: Bool = false,
    priority: String? = nil,
    metadata: [String: Any]? = nil,
    metadataBox: ActionItemMetadataBox? = nil,
    goalId: String? = nil,
    clearGoalId: Bool = false,
    workstreamId: String? = nil,
    clearWorkstreamId: Bool = false,
    owner: String? = nil,
    dueConfidence: Double? = nil,
    provenance: [OmiAPI.EvidenceRef]? = nil,
    status: String? = nil,
    supersededBy: String? = nil,
    source: String? = nil,
    sortOrder: Int? = nil,
    indentLevel: Int? = nil,
    relevanceScore: Int? = nil,
    recurrenceRule: String? = nil,
    recurrenceParentId: String? = nil,
    expectedOwnerId: String? = nil,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot? = nil
  ) async throws -> TaskActionItem {
    let formatter = ISO8601DateFormatter()
    formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]

    var metadataString: String? = nil
    if let metadata = metadataBox?.value ?? metadata {
      if let data = try? JSONSerialization.data(withJSONObject: metadata),
        let str = String(data: data, encoding: .utf8)
      {
        metadataString = str
      }
    }

    let wire = OmiAPI.ActionItemUpdateRequest(
      clearDueAt: taskPatchField(clearDueAt ? true : nil),
      completed: taskPatchField(completed),
      description_: taskPatchField(description),
      dueAt: taskPatchField(dueAt.map { formatter.string(from: $0) }),
      dueConfidence: taskPatchField(dueConfidence),
      goalId: clearGoalId ? .null : taskPatchField(goalId),
      indentLevel: taskPatchField(indentLevel),
      owner: taskPatchField(owner.flatMap(OmiAPI.TaskOwner.init(rawValue:))),
      priority: taskPatchField(priority.flatMap(OmiAPI.TaskPriority.init(rawValue:))),
      provenance: taskPatchField(provenance),
      recurrenceParentId: taskPatchField(recurrenceParentId),
      recurrenceRule: taskPatchField(recurrenceRule),
      sortOrder: taskPatchField(sortOrder),
      source: taskPatchField(source),
      status: taskPatchField(status.flatMap(OmiAPI.TaskStatus.init(rawValue:))),
      supersededBy: taskPatchField(supersededBy),
      workstreamId: clearWorkstreamId ? .null : taskPatchField(workstreamId)
    )
    let request = try taskMutationBody(
      wire,
      metadata: metadataString,
      relevanceScore: relevanceScore
    )

    return try await patch(
      "v1/action-items/\(id)",
      body: request,
      expectedOwnerId: expectedOwnerId,
      authorizationSnapshot: authorizationSnapshot)
  }

  /// Deletes an action item
  func deleteActionItem(
    id: String,
    expectedOwnerId: String? = nil,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot? = nil
  ) async throws {
    try await delete(
      "v1/action-items/\(id)",
      authPolicy: expectedOwnerId.map { .ownerBound($0) } ?? .default,
      expectedAuthOwnerId: expectedOwnerId,
      authorizationSnapshot: authorizationSnapshot)
  }

  /// Creates a new action item
  func createActionItem(
    description: String,
    dueAt: Date? = nil,
    source: String? = nil,
    priority: String? = nil,
    category: String? = nil,
    metadata: [String: Any]? = nil,
    metadataBox: ActionItemMetadataBox? = nil,
    relevanceScore: Int? = nil,
    recurrenceRule: String? = nil,
    recurrenceParentId: String? = nil,
    goalId: String? = nil,
    workstreamId: String? = nil,
    owner: String? = nil,
    dueConfidence: Double? = nil,
    provenance: [OmiAPI.EvidenceRef]? = nil,
    status: String? = nil,
    sortOrder: Int? = nil,
    indentLevel: Int? = nil,
    expectedOwnerId: String? = nil,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot? = nil
  ) async throws -> TaskActionItem {
    let formatter = ISO8601DateFormatter()
    formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]

    var metadataString: String? = nil
    if let metadata = metadataBox?.value ?? metadata {
      if let data = try? JSONSerialization.data(withJSONObject: metadata),
        let str = String(data: data, encoding: .utf8)
      {
        metadataString = str
      }
    }

    let wire = OmiAPI.ActionItemCreateRequest(
      appleReminderId: nil,
      completed: nil,
      conversationId: nil,
      description_: description,
      dueAt: dueAt.map { formatter.string(from: $0) },
      dueConfidence: dueConfidence,
      exportDate: nil,
      exportPlatform: nil,
      exported: nil,
      goalId: goalId,
      indentLevel: indentLevel,
      isLocked: nil,
      owner: owner.flatMap(OmiAPI.TaskOwner.init(rawValue:)),
      priority: priority.flatMap(OmiAPI.TaskPriority.init(rawValue:)),
      provenance: provenance,
      recurrenceParentId: recurrenceParentId,
      recurrenceRule: recurrenceRule,
      sortOrder: sortOrder,
      source: source,
      status: status.flatMap(OmiAPI.TaskStatus.init(rawValue:)),
      workstreamId: workstreamId
    )
    let request = try taskMutationBody(
      wire,
      category: category,
      metadata: metadataString,
      relevanceScore: relevanceScore
    )

    return try await post(
      "v1/action-items",
      body: request,
      expectedOwnerId: expectedOwnerId,
      authorizationSnapshot: authorizationSnapshot)
  }

  private func taskMutationBody<Wire: Encodable>(
    _ wire: Wire,
    category: String? = nil,
    metadata: String? = nil,
    relevanceScore: Int? = nil
  ) throws -> OmiAnyCodable {
    let data = try JSONEncoder().encode(wire)
    guard var body = try JSONSerialization.jsonObject(with: data) as? [String: Any] else {
      throw APIError.invalidResponse
    }
    // Released desktop clients still send these compatibility-only fields.
    // Canonical fields remain owned by the generated OpenAPI request DTO.
    if let category { body["category"] = category }
    if let metadata { body["metadata"] = metadata }
    if let relevanceScore { body["relevance_score"] = relevanceScore }
    return OmiAnyCodable(body)
  }

  private func taskPatchField<Value: Codable>(_ value: Value?) -> OmiAPI.OmiPatchField<Value> {
    value.map(OmiAPI.OmiPatchField.value) ?? .omitted
  }

  // MARK: - Task Sharing

  /// Shares tasks and returns a shareable URL
  func shareTasks(taskIds: [String]) async throws -> ShareTasksResponse {
    struct ShareRequest: Encodable {
      let taskIds: [String]
      enum CodingKeys: String, CodingKey {
        case taskIds = "task_ids"
      }
    }
    return try await post("v1/action-items/share", body: ShareRequest(taskIds: taskIds))
  }

}

// MARK: - Canonical Candidates API

extension APIClient {
  func getCandidateWorkflowControl() async throws -> OmiAPI.TaskWorkflowControl {
    try await get("v1/candidates/control")
  }

  func getCandidateWorkflowControl(
    expectedOwnerId: String,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot? = nil
  ) async throws
    -> OmiAPI.TaskWorkflowControl
  {
    try await get(
      "v1/candidates/control",
      expectedOwnerId: expectedOwnerId,
      authorizationSnapshot: authorizationSnapshot)
  }

  func createCanonicalCandidate(
    _ candidate: OmiAPI.CandidateCreate,
    idempotencyKey: String,
    accountGeneration: Int
  ) async throws -> OmiAPI.CandidateRecord {
    try await taskIntelligenceMutation(
      endpoint: "v1/candidates",
      method: "POST",
      body: candidate,
      idempotencyKey: idempotencyKey,
      accountGeneration: accountGeneration
    )
  }

  func acceptCanonicalCandidate(
    candidateID: String,
    accountGeneration: Int
  ) async throws -> OmiAPI.CandidateResolutionReceipt {
    try await taskIntelligenceMutation(
      endpoint: "v1/candidates/\(candidateID)/accept",
      method: "POST",
      body: Optional<String>.none,
      idempotencyKey: nil,
      accountGeneration: accountGeneration
    )
  }

  func getCanonicalCandidate(candidateID: String) async throws -> OmiAPI.CandidateRecord {
    try await get("v1/candidates/\(candidateID)")
  }

  func taskIntelligenceMutation<Response: Decodable, Body: Encodable>(
    endpoint: String,
    method: String,
    body: Body?,
    idempotencyKey: String?,
    accountGeneration: Int?,
    expectedOwnerId: String? = nil,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot? = nil
  ) async throws -> Response {
    let authPolicy = try resolvedRequestAuthPolicy(
      expectedOwnerId: expectedOwnerId,
      authorizationSnapshot: authorizationSnapshot)
    let authOwnerId = authPolicy.expectedAuthOwnerId
    try validateExpectedOwner(authPolicy)
    guard let url = URL(string: baseURL + endpoint) else { throw APIError.invalidResponse }
    var request = URLRequest(url: url)
    request.httpMethod = method
    request.allHTTPHeaderFields = try await buildHeaders(
      expectedAuthOwnerId: authOwnerId)
    try validateExpectedOwner(authPolicy)
    if let accountGeneration {
      request.setValue(String(accountGeneration), forHTTPHeaderField: "X-Account-Generation")
    }
    if let idempotencyKey {
      request.setValue(idempotencyKey, forHTTPHeaderField: "Idempotency-Key")
    }
    if let body { request.httpBody = try JSONEncoder().encode(body) }
    return try await performRequest(
      request,
      authPolicy: authPolicy)
  }
}

// MARK: - Suggested task review and feedback

extension APIClient {
  func listCanonicalCandidates(status: String, limit: Int) async throws -> [OmiAPI.CandidateRecord] {
    let encodedStatus = status.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? status
    let response: OmiAPI.CandidateListResponse = try await get(
      "v1/candidates?status=\(encodedStatus)&limit=\(limit)&offset=0&surface=suggested")
    return response.candidates
  }

  func rejectCanonicalCandidate(
    candidateID: String,
    reason: String?,
    accountGeneration: Int
  ) async throws -> OmiAPI.CandidateResolutionReceipt {
    try await taskIntelligenceMutation(
      endpoint: "v1/candidates/\(candidateID)/reject",
      method: "POST",
      body: OmiAPI.CandidateResolutionRequest(reason: reason),
      idempotencyKey: nil,
      accountGeneration: accountGeneration
    )
  }

  func registerTaskIntervention(
    _ request: OmiAPI.InterventionCreate,
    idempotencyKey: String,
    accountGeneration: Int
  ) async throws -> OmiAPI.InterventionRecord {
    try await taskIntelligenceMutation(
      endpoint: "v1/task-intelligence/interventions",
      method: "POST",
      body: request,
      idempotencyKey: idempotencyKey,
      accountGeneration: accountGeneration
    )
  }

  func recordTaskFeedback(
    _ request: OmiAPI.FeedbackCreate,
    idempotencyKey: String,
    accountGeneration: Int
  ) async throws -> OmiAPI.FeedbackRecord {
    try await taskIntelligenceMutation(
      endpoint: "v1/task-intelligence/feedback",
      method: "POST",
      body: request,
      idempotencyKey: idempotencyKey,
      accountGeneration: accountGeneration
    )
  }

  func createTaskOutcome(
    _ request: OmiAPI.OutcomeCreate,
    idempotencyKey: String,
    accountGeneration: Int
  ) async throws -> OmiAPI.OutcomeRecord {
    try await taskIntelligenceMutation(
      endpoint: "v1/task-intelligence/outcomes",
      method: "POST",
      body: request,
      idempotencyKey: idempotencyKey,
      accountGeneration: accountGeneration
    )
  }

  func updateSuggestedTaskDescription(id: String, description: String) async throws {
    _ = try await updateActionItem(id: id, description: description)
  }
}

// MARK: - What Matters Now and canonical Goals

extension APIClient {
  func getWhatMattersNow(deviceID: String? = nil) async throws -> OmiAPI.WhatMattersNowProjection {
    // Device identity is bound by X-App-Platform + X-Device-Id-Hash. Do not
    // duplicate it in a caller-controlled query parameter; the optional input
    // stays source-compatible for existing callers during the rollout.
    _ = deviceID
    return try await get("v1/what-matters-now")
  }

  func replaceTaskContextSnapshot(
    _ snapshot: OmiAPI.NormalizedContextSnapshot,
    accountGeneration: Int,
    expectedOwnerId: String? = nil,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot? = nil
  ) async throws -> OmiAPI.SnapshotReceipt {
    try await taskIntelligenceMutation(
      endpoint: "v1/task-intelligence/context-snapshot",
      method: "PUT",
      body: snapshot,
      idempotencyKey: snapshot.snapshotId,
      accountGeneration: accountGeneration,
      expectedOwnerId: expectedOwnerId,
      authorizationSnapshot: authorizationSnapshot
    )
  }

  func evaluateWhatMattersNow(
    _ request: OmiAPI.EvaluationRequest,
    expectedOwnerId: String? = nil,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot? = nil
  ) async throws -> OmiAPI.WhatMattersNowProjection {
    try await taskIntelligenceMutation(
      endpoint: "v1/what-matters-now/evaluate",
      method: "POST",
      body: request,
      idempotencyKey: nil,
      accountGeneration: nil,
      expectedOwnerId: expectedOwnerId,
      authorizationSnapshot: authorizationSnapshot
    )
  }

  func getCanonicalGoals(includeEnded: Bool = true) async throws -> [OmiAPI.GoalResponse] {
    try await getCanonicalGoals(
      includeEnded: includeEnded,
      expectedOwnerId: nil,
      authorizationSnapshot: nil
    )
  }

  func getCanonicalGoals(
    includeEnded: Bool,
    expectedOwnerId: String?,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot?
  ) async throws -> [OmiAPI.GoalResponse] {
    try await get(
      "v1/goals/canonical/list?include_ended=\(includeEnded ? "true" : "false")",
      expectedOwnerId: expectedOwnerId,
      authorizationSnapshot: authorizationSnapshot
    )
  }

  func getCanonicalGoalDetail(goalID: String) async throws -> OmiAPI.GoalDetailProjection {
    try await getCanonicalGoalDetail(
      goalID: goalID,
      expectedOwnerId: nil,
      authorizationSnapshot: nil
    )
  }

  func getCanonicalGoalDetail(
    goalID: String,
    expectedOwnerId: String?,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot?
  ) async throws -> OmiAPI.GoalDetailProjection {
    try await get(
      "v1/goals/\(goalID)/detail",
      expectedOwnerId: expectedOwnerId,
      authorizationSnapshot: authorizationSnapshot
    )
  }

  func createCanonicalGoal(
    title: String,
    desiredOutcome: String,
    whyItMatters: String?,
    successCriteria: [String],
    accountGeneration: Int,
    idempotencyKey: String
  ) async throws -> OmiAPI.GoalResponse {
    struct Request: Encodable {
      let title: String
      let desired_outcome: String
      let why_it_matters: String?
      let success_criteria: [String]
      let status: String
      let source: String
    }
    return try await taskIntelligenceMutation(
      endpoint: "v1/goals/canonical",
      method: "POST",
      body: Request(
        title: title,
        desired_outcome: desiredOutcome,
        why_it_matters: whyItMatters,
        success_criteria: successCriteria,
        status: "background",
        source: "user"
      ),
      idempotencyKey: idempotencyKey,
      accountGeneration: accountGeneration
    )
  }

  func focusCanonicalGoal(
    goalID: String,
    replacementGoalID: String?,
    focusRank: Int?,
    accountGeneration: Int,
    idempotencyKey: String
  ) async throws -> OmiAPI.GoalResponse {
    try await focusCanonicalGoal(
      goalID: goalID,
      replacementGoalID: replacementGoalID,
      focusRank: focusRank,
      accountGeneration: accountGeneration,
      idempotencyKey: idempotencyKey,
      expectedOwnerId: nil,
      authorizationSnapshot: nil
    )
  }

  func focusCanonicalGoal(
    goalID: String,
    replacementGoalID: String?,
    focusRank: Int?,
    accountGeneration: Int,
    idempotencyKey: String,
    expectedOwnerId: String?,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot?
  ) async throws -> OmiAPI.GoalResponse {
    struct Request: Encodable {
      let replacement_goal_id: String?
      let focus_rank: Int?
    }
    return try await taskIntelligenceMutation(
      endpoint: "v1/goals/\(goalID)/focus",
      method: "POST",
      body: Request(replacement_goal_id: replacementGoalID, focus_rank: focusRank),
      idempotencyKey: idempotencyKey,
      accountGeneration: accountGeneration,
      expectedOwnerId: expectedOwnerId,
      authorizationSnapshot: authorizationSnapshot
    )
  }

  func unfocusCanonicalGoal(
    goalID: String,
    accountGeneration: Int,
    idempotencyKey: String
  ) async throws -> OmiAPI.GoalResponse {
    try await taskIntelligenceMutation(
      endpoint: "v1/goals/\(goalID)/focus",
      method: "DELETE",
      body: Optional<String>.none,
      idempotencyKey: idempotencyKey,
      accountGeneration: accountGeneration
    )
  }

  func transitionCanonicalGoal(
    goalID: String,
    status: OmiAPI.GoalStatus,
    relationshipDisposition: String = "retain",
    accountGeneration: Int,
    idempotencyKey: String
  ) async throws -> OmiAPI.GoalResponse {
    struct Request: Encodable {
      let status: OmiAPI.GoalStatus
      let relationship_disposition: String
    }
    return try await taskIntelligenceMutation(
      endpoint: "v1/goals/\(goalID)/lifecycle",
      method: "POST",
      body: Request(status: status, relationship_disposition: relationshipDisposition),
      idempotencyKey: idempotencyKey,
      accountGeneration: accountGeneration
    )
  }
}

/// Response types for task sharing
struct ShareTasksResponse: Codable {
  let url: String
  let token: String
}
// MARK: - Staged Tasks API

extension APIClient {

  /// Creates a new staged task
  func createStagedTask(
    description: String,
    dueAt: Date? = nil,
    source: String? = nil,
    priority: String? = nil,
    category: String? = nil,
    metadata: [String: Any]? = nil,
    relevanceScore: Int? = nil
  ) async throws -> TaskActionItem {
    struct CreateRequest: Encodable {
      let description: String
      let dueAt: String?
      let source: String?
      let priority: String?
      let category: String?
      let metadata: String?
      let relevanceScore: Int?

      enum CodingKeys: String, CodingKey {
        case description
        case dueAt = "due_at"
        case source, priority, category, metadata
        case relevanceScore = "relevance_score"
      }
    }

    let formatter = ISO8601DateFormatter()
    formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]

    var metadataString: String? = nil
    if let metadata = metadata {
      if let data = try? JSONSerialization.data(withJSONObject: metadata),
        let str = String(data: data, encoding: .utf8)
      {
        metadataString = str
      }
    }

    let request = CreateRequest(
      description: description,
      dueAt: dueAt.map { formatter.string(from: $0) },
      source: source,
      priority: priority,
      category: category,
      metadata: metadataString,
      relevanceScore: relevanceScore
    )

    return try await post("v1/staged-tasks", body: request)
  }

  /// Fetches staged tasks ordered by relevance score
  func getStagedTasks(limit: Int = 100, offset: Int = 0) async throws -> ActionItemsListResponse {
    let params = "limit=\(limit)&offset=\(offset)"
    return try await get("v1/staged-tasks?\(params)")
  }

  /// Hard-deletes a staged task
  func deleteStagedTask(id: String) async throws {
    try await delete("v1/staged-tasks/\(id)")
  }

  /// Batch update relevance scores for staged tasks
  func batchUpdateStagedScores(_ scores: [(id: String, score: Int)]) async throws {
    struct ScoreUpdate: Encodable {
      let id: String
      let relevance_score: Int
    }
    struct BatchRequest: Encodable {
      let scores: [ScoreUpdate]
    }
    struct StatusResponse: Decodable {
      let status: String
    }
    for scoreBatch in scores.chunked(maxSize: 500) {
      let request = BatchRequest(
        scores: scoreBatch.map { ScoreUpdate(id: $0.id, relevance_score: $0.score) })
      let _: StatusResponse = try await patch("v1/staged-tasks/batch-scores", body: request)
    }
  }

  /// Promotes the top-ranked staged task to action_items
  func promoteTopStagedTask(
    expectedOwnerId: String? = nil,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot? = nil
  ) async throws -> PromoteResponse {
    return try await post(
      "v1/staged-tasks/promote",
      expectedOwnerId: expectedOwnerId,
      authorizationSnapshot: authorizationSnapshot)
  }

}

/// Response for staged task promotion
struct PromoteResponse: Codable {
  let promoted: Bool
  let reason: String?
  let promotedTask: TaskActionItem?

  enum CodingKeys: String, CodingKey {
    case promoted, reason
    case promotedTask = "promoted_task"
  }
}
