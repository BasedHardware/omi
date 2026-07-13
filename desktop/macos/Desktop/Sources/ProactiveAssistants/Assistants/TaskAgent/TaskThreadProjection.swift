import Foundation

protocol TaskWorkstreamAPI {
  func workflowControl(
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot
  ) async throws -> OmiAPI.TaskWorkflowControl
  func resolveTaskIntent(
    taskId: String,
    title: String?,
    objective: String?,
    idempotencyKey: String,
    accountGeneration: Int,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot
  ) async throws -> OmiAPI.WorkIntentReceipt
  func resolveGoalIntent(
    goalId: String,
    title: String,
    objective: String,
    anchorTaskDescription: String,
    idempotencyKey: String,
    accountGeneration: Int,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot
  ) async throws -> OmiAPI.WorkIntentReceipt
  func detail(
    workstreamId: String,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot
  ) async throws -> OmiAPI.WorkstreamDetailProjection
  func createArtifact(
    workstreamId: String,
    artifact: OmiAPI.ArtifactDescriptorCreate,
    idempotencyKey: String,
    accountGeneration: Int,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot
  ) async throws -> OmiAPI.ArtifactDescriptor
  func upsertCheckpoint(
    workstreamId: String,
    runtimeId: String,
    checkpoint: OmiAPI.ContinuationCheckpointUpsert,
    idempotencyKey: String,
    accountGeneration: Int,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot
  ) async throws -> OmiAPI.ContinuationCheckpoint
}

extension TaskWorkstreamAPI {
  func createArtifact(
    workstreamId: String,
    artifact: OmiAPI.ArtifactDescriptorCreate,
    idempotencyKey: String,
    accountGeneration: Int,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot
  ) async throws -> OmiAPI.ArtifactDescriptor {
    throw TaskWorkstreamContinuityError.invalidRuntimeResponse
  }

  func upsertCheckpoint(
    workstreamId: String,
    runtimeId: String,
    checkpoint: OmiAPI.ContinuationCheckpointUpsert,
    idempotencyKey: String,
    accountGeneration: Int,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot
  ) async throws -> OmiAPI.ContinuationCheckpoint {
    throw TaskWorkstreamContinuityError.invalidRuntimeResponse
  }
}

struct LiveTaskWorkstreamAPI: TaskWorkstreamAPI {
  func workflowControl(
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot
  ) async throws -> OmiAPI.TaskWorkflowControl {
    try await APIClient.shared.getCandidateWorkflowControl(
      expectedOwnerId: authorizationSnapshot.ownerID,
      authorizationSnapshot: authorizationSnapshot
    )
  }

  func resolveTaskIntent(
    taskId: String,
    title: String?,
    objective: String?,
    idempotencyKey: String,
    accountGeneration: Int,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot
  ) async throws -> OmiAPI.WorkIntentReceipt {
    try await APIClient.shared.resolveTaskWorkIntent(
      taskId: taskId,
      title: title,
      objective: objective,
      idempotencyKey: idempotencyKey,
      accountGeneration: accountGeneration,
      authorizationSnapshot: authorizationSnapshot
    )
  }

  func resolveGoalIntent(
    goalId: String,
    title: String,
    objective: String,
    anchorTaskDescription: String,
    idempotencyKey: String,
    accountGeneration: Int,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot
  ) async throws -> OmiAPI.WorkIntentReceipt {
    try await APIClient.shared.resolveGoalWorkIntent(
      goalId: goalId,
      title: title,
      objective: objective,
      anchorTaskDescription: anchorTaskDescription,
      idempotencyKey: idempotencyKey,
      accountGeneration: accountGeneration,
      authorizationSnapshot: authorizationSnapshot
    )
  }

  func detail(
    workstreamId: String,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot
  ) async throws -> OmiAPI.WorkstreamDetailProjection {
    try await APIClient.shared.getWorkstreamDetail(
      workstreamId: workstreamId,
      authorizationSnapshot: authorizationSnapshot
    )
  }

  func createArtifact(
    workstreamId: String,
    artifact: OmiAPI.ArtifactDescriptorCreate,
    idempotencyKey: String,
    accountGeneration: Int,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot
  ) async throws -> OmiAPI.ArtifactDescriptor {
    try await APIClient.shared.createWorkstreamArtifact(
      workstreamId: workstreamId,
      artifact: artifact,
      idempotencyKey: idempotencyKey,
      accountGeneration: accountGeneration,
      authorizationSnapshot: authorizationSnapshot
    )
  }

  func upsertCheckpoint(
    workstreamId: String,
    runtimeId: String,
    checkpoint: OmiAPI.ContinuationCheckpointUpsert,
    idempotencyKey: String,
    accountGeneration: Int,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot
  ) async throws -> OmiAPI.ContinuationCheckpoint {
    try await APIClient.shared.upsertWorkstreamCheckpoint(
      workstreamId: workstreamId,
      runtimeId: runtimeId,
      checkpoint: checkpoint,
      idempotencyKey: idempotencyKey,
      accountGeneration: accountGeneration,
      authorizationSnapshot: authorizationSnapshot
    )
  }
}

enum TaskWorkIntentIdentity {
  static func task(taskId: String) -> String { "work-intent:task:\(taskId)" }
  static func goal(goalId: String, occurrenceId: String) -> String {
    "work-intent:goal:\(goalId):\(occurrenceId)"
  }
}

struct TaskThreadProjection {
  let detail: OmiAPI.WorkstreamDetailProjection
  let activeTaskID: String

  var workstreamID: String { detail.workstream.workstreamId }
  var title: String { detail.workstream.title }
  var currentSummary: String {
    detail.workstream.currentStateSummary ?? detail.workstream.objective
  }

  var scopedTasks: [OmiAPI.ActionItemResponse] {
    detail.tasks.sorted { lhs, rhs in
      if lhs.id == activeTaskID { return true }
      if rhs.id == activeTaskID { return false }
      return (lhs.updatedAt ?? lhs.createdAt ?? "") > (rhs.updatedAt ?? rhs.createdAt ?? "")
    }
  }

  var recentEvents: [OmiAPI.WorkstreamEvent] {
    Array(detail.recentEvents.sorted { $0.sequence > $1.sequence }.prefix(12))
  }

  var artifactVersions: [OmiAPI.ArtifactDescriptor] {
    detail.artifacts.sorted { lhs, rhs in
      if lhs.logicalKey != rhs.logicalKey { return lhs.logicalKey < rhs.logicalKey }
      return lhs.version > rhs.version
    }
  }

  var artifactHeads: [OmiAPI.ArtifactDescriptor] {
    var seen = Set<String>()
    return artifactVersions.filter { seen.insert($0.logicalKey).inserted }
  }

  func selecting(taskID: String) -> Self {
    Self(detail: detail, activeTaskID: taskID)
  }
}

enum TaskThreadContextPacket {
  private struct Packet: Encodable {
    let schemaVersion: Int
    let workstream: WorkstreamContext
    let currentTask: TaskContext?
    let scopedTasks: [TaskContext]
    let recentEvents: [EventContext]
    let artifactHeads: [ArtifactContext]

    enum CodingKeys: String, CodingKey {
      case schemaVersion = "schema_version"
      case workstream
      case currentTask = "current_task"
      case scopedTasks = "scoped_tasks"
      case recentEvents = "recent_events"
      case artifactHeads = "artifact_heads"
    }
  }

  private struct WorkstreamContext: Encodable {
    let id: String
    let title: String
    let objective: String
    let currentSummary: String
    let latestEventSequence: Int?

    enum CodingKeys: String, CodingKey {
      case id
      case title
      case objective
      case currentSummary = "current_summary"
      case latestEventSequence = "latest_event_sequence"
    }
  }

  private struct TaskContext: Encodable {
    let id: String
    let description: String
    let status: String
    let dueAt: String?
    let evidenceRefs: [OmiAPI.EvidenceRef]

    enum CodingKeys: String, CodingKey {
      case id
      case description
      case status
      case dueAt = "due_at"
      case evidenceRefs = "evidence_refs"
    }
  }

  private struct EventContext: Encodable {
    let id: String
    let sequence: Int
    let kind: String
    let summary: String
    let evidenceRefs: [OmiAPI.EvidenceRef]

    enum CodingKeys: String, CodingKey {
      case id
      case sequence
      case kind
      case summary
      case evidenceRefs = "evidence_refs"
    }
  }

  private struct ArtifactContext: Encodable {
    let id: String
    let logicalKey: String
    let version: Int
    let kind: String
    let status: String
    let evidenceRefs: [OmiAPI.EvidenceRef]

    enum CodingKeys: String, CodingKey {
      case id
      case logicalKey = "logical_key"
      case version
      case kind
      case status
      case evidenceRefs = "evidence_refs"
    }
  }

  static func encode(_ projection: TaskThreadProjection) -> String? {
    let taskContexts = Array(projection.scopedTasks.prefix(20)).map(taskContext)
    let packet = Packet(
      schemaVersion: 1,
      workstream: WorkstreamContext(
        id: projection.workstreamID,
        title: projection.detail.workstream.title,
        objective: projection.detail.workstream.objective,
        currentSummary: projection.currentSummary,
        latestEventSequence: projection.detail.workstream.latestEventSequence
      ),
      currentTask: projection.scopedTasks.first(where: { $0.id == projection.activeTaskID }).map(taskContext),
      scopedTasks: taskContexts,
      recentEvents: projection.recentEvents.map {
        EventContext(
          id: $0.eventId,
          sequence: $0.sequence,
          kind: $0.kind.rawValue,
          summary: $0.sensitivity == .normal ? $0.summary : "[Sensitive update omitted]",
          evidenceRefs: Array(($0.evidenceRefs ?? []).prefix(12))
        )
      },
      artifactHeads: projection.artifactHeads.prefix(12).map {
        ArtifactContext(
          id: $0.artifactId,
          logicalKey: $0.logicalKey,
          version: $0.version,
          kind: $0.kind,
          status: ($0.status ?? .draft).rawValue,
          evidenceRefs: Array(($0.evidenceRefs ?? []).prefix(12))
        )
      }
    )
    let encoder = JSONEncoder()
    encoder.outputFormatting = [.sortedKeys]
    guard let data = try? encoder.encode(packet) else { return nil }
    return String(data: data, encoding: .utf8)
  }

  private static func taskContext(_ task: OmiAPI.ActionItemResponse) -> TaskContext {
    TaskContext(
      id: task.id,
      description: task.description_,
      status: (task.status ?? (task.completed ? .completed : .active)).rawValue,
      dueAt: task.dueAt,
      evidenceRefs: Array((task.provenance ?? []).prefix(12))
    )
  }
}

/// Privacy-safe product context for the scenario harness. Artifact state is
/// supplied by the running kernel bridge rather than frozen in this fixture.
#if DEBUG
enum TaskThreadScenario13Fixture {
  static let workstreamID = "scenario-13-workstream"
  static let firstTaskID = "scenario-13-task-draft"
  static let secondTaskID = "scenario-13-task-review"

  static var baseDetail: OmiAPI.WorkstreamDetailProjection {
    let json = """
      {
        "workstream": {
          "workstream_id": "scenario-13-workstream",
          "title": "Prepare the launch email",
          "objective": "Draft, revise, and approve the launch email",
          "status": "open",
          "current_state_summary": "The Friday date is incorporated in v2; approval is still pending.",
          "latest_event_sequence": 3,
          "created_at": "2026-07-09T10:00:00Z",
          "updated_at": "2026-07-09T12:00:00Z"
        },
        "tasks": [
          {
            "id": "scenario-13-task-draft",
            "description": "Draft the launch email",
            "completed": true,
            "status": "completed",
            "workstream_id": "scenario-13-workstream",
            "created_at": "2026-07-09T10:00:00Z",
            "updated_at": "2026-07-09T11:00:00Z"
          },
          {
            "id": "scenario-13-task-review",
            "description": "Review and approve the launch email",
            "completed": false,
            "status": "active",
            "workstream_id": "scenario-13-workstream",
            "created_at": "2026-07-09T10:05:00Z",
            "updated_at": "2026-07-09T12:00:00Z",
            "provenance": [
              {"kind":"conversation","id":"conversation-friday","scope":"canonical","version":"conversation.v1"}
            ]
          }
        ],
        "recent_events": [
          {
            "event_id": "event-created",
            "workstream_id": "scenario-13-workstream",
            "sequence": 1,
            "kind": "user_note",
            "summary": "Draft requested",
            "sensitivity": "normal",
            "created_at": "2026-07-09T10:00:00Z"
          },
          {
            "event_id": "event-friday",
            "workstream_id": "scenario-13-workstream",
            "sequence": 3,
            "kind": "conversation",
            "summary": "Launch date changed to Friday",
            "sensitivity": "normal",
            "created_at": "2026-07-09T12:00:00Z",
            "evidence_refs": [
              {"kind":"conversation","id":"conversation-friday","scope":"canonical","version":"conversation.v1"}
            ]
          },
          {
            "event_id": "event-sensitive",
            "workstream_id": "scenario-13-workstream",
            "sequence": 2,
            "kind": "user_note",
            "summary": "Confidential acquisition detail",
            "sensitivity": "sensitive",
            "created_at": "2026-07-09T11:30:00Z"
          }
        ],
        "artifacts": [],
        "checkpoints": []
      }
      """
    do {
      return try JSONDecoder().decode(
        OmiAPI.WorkstreamDetailProjection.self,
        from: Data(json.utf8)
      )
    } catch {
      preconditionFailure("Invalid scenario-13 task-thread fixture: \(error)")
    }
  }

  static func detail(artifacts: [OmiAPI.ArtifactDescriptor]) -> OmiAPI.WorkstreamDetailProjection {
    let base = baseDetail
    return OmiAPI.WorkstreamDetailProjection(
      artifacts: artifacts,
      checkpoints: base.checkpoints,
      recentEvents: base.recentEvents,
      tasks: base.tasks,
      workstream: base.workstream
    )
  }
}
#endif
