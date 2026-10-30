import Foundation

/// The latest local task values admitted by the existing generic task-create
/// endpoint. Local execution state and server-owned identity never become a
/// new task's authority when recovering an unsynced row.
struct UnsyncedTaskCreateProjection {
  enum ProjectionError: LocalizedError, Equatable {
    case invalidPriority
    case invalidOwner
    case invalidStatus
    case invalidMetadata
    case invalidProvenance

    var errorDescription: String? {
      switch self {
      case .invalidPriority: return "The saved task has an unsupported priority"
      case .invalidOwner: return "The saved task has an unsupported owner"
      case .invalidStatus: return "The saved task has an unsupported status"
      case .invalidMetadata: return "The saved task's metadata could not be read"
      case .invalidProvenance: return "The saved task's evidence could not be read"
      }
    }
  }

  let description: String
  let completed: Bool
  let dueAt: Date?
  let source: String?
  let priority: OmiAPI.TaskPriority?
  let category: String?
  let metadataBox: ActionItemMetadataBox?
  let relevanceScore: Int?
  let recurrenceRule: String?
  let recurrenceParentId: String?
  let goalId: String?
  let workstreamId: String?
  let owner: OmiAPI.TaskOwner?
  let dueConfidence: Double?
  let provenance: [OmiAPI.EvidenceRef]?
  let status: OmiAPI.TaskStatus?
  let sortOrder: Int?
  let indentLevel: Int?
  let conversationId: String?
  let isLocked: Bool?

  init(record: ActionItemRecord) throws {
    description = record.description
    completed = record.completed
    dueAt = record.dueAt
    source = record.source
    if let raw = record.priority {
      guard let value = OmiAPI.TaskPriority(rawValue: raw), value != ._unknown else {
        throw ProjectionError.invalidPriority
      }
      priority = value
    } else {
      priority = nil
    }
    category = record.category
    metadataBox = try Self.decodeMetadata(record.metadataJson)
    relevanceScore = record.relevanceScore
    recurrenceRule = record.recurrenceRule
    recurrenceParentId = record.recurrenceParentId
    goalId = record.goalId
    workstreamId = record.workstreamId
    if let raw = record.taskOwner {
      guard let value = OmiAPI.TaskOwner(rawValue: raw), value != ._unknown else {
        throw ProjectionError.invalidOwner
      }
      owner = value
    } else {
      owner = nil
    }
    dueConfidence = record.dueConfidence
    provenance = try Self.decodeProvenance(record.provenanceJson)
    if let raw = record.taskStatus {
      guard let value = OmiAPI.TaskStatus(rawValue: raw), value != ._unknown else {
        throw ProjectionError.invalidStatus
      }
      switch value {
      case .active, .completed:
        // updateCompletionStatus persists the newest local completed flag but
        // retains cached taskStatus. CanonicalTaskCreate requires agreement,
        // so completion and undo must use that flag for this live status pair.
        status = record.completed ? .completed : .active
      case .cancelled, .superseded:
        guard !record.completed else { throw ProjectionError.invalidStatus }
        status = value
      case ._unknown:
        throw ProjectionError.invalidStatus
      }
    } else {
      status = nil
    }
    sortOrder = record.sortOrder
    indentLevel = record.indentLevel
    conversationId = record.conversationId
    isLocked = record.isLocked
  }

  @MainActor
  func create(
    using client: APIClient = .shared,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot
  ) async throws -> TaskActionItem {
    try await client.createActionItem(
      description: description,
      dueAt: dueAt,
      source: source,
      priority: priority?.rawValue,
      category: category,
      metadataBox: metadataBox,
      relevanceScore: relevanceScore,
      recurrenceRule: recurrenceRule,
      recurrenceParentId: recurrenceParentId,
      goalId: goalId,
      workstreamId: workstreamId,
      owner: owner?.rawValue,
      dueConfidence: dueConfidence,
      provenance: provenance,
      status: status?.rawValue,
      completed: completed ? true : nil,
      sortOrder: sortOrder,
      indentLevel: indentLevel,
      conversationId: conversationId,
      isLocked: isLocked == true ? true : nil,
      expectedOwnerId: authorizationSnapshot.ownerID,
      authorizationSnapshot: authorizationSnapshot)
  }

  private static func decodeMetadata(_ json: String?) throws -> ActionItemMetadataBox? {
    guard let json else { return nil }
    guard let data = json.data(using: .utf8) else { throw ProjectionError.invalidMetadata }
    do {
      guard let value = try JSONSerialization.jsonObject(with: data) as? [String: Any] else {
        throw ProjectionError.invalidMetadata
      }
      return ActionItemMetadataBox(value)
    } catch {
      throw ProjectionError.invalidMetadata
    }
  }

  private static func decodeProvenance(_ json: String?) throws -> [OmiAPI.EvidenceRef]? {
    guard let json else { return nil }
    guard let data = json.data(using: .utf8) else { throw ProjectionError.invalidProvenance }
    do {
      let value = try JSONDecoder().decode([OmiAPI.EvidenceRef].self, from: data)
      guard value.allSatisfy({ $0.kind != ._unknown && $0.scope != ._unknown }) else {
        throw ProjectionError.invalidProvenance
      }
      return value
    } catch {
      throw ProjectionError.invalidProvenance
    }
  }
}
