import Foundation
import OmiCore

public extension APIClient {
    /// `GET v1/action-items` (open and completed; the store splits them). Offset paging, at most 500 per page.
    func actionItems(limit: Int, offset: Int) async throws -> [ActionItem] {
        let data = try await data(.get, "v1/action-items", query: [
            URLQueryItem(name: "limit", value: String(limit)),
            URLQueryItem(name: "offset", value: String(offset)),
        ])
        return try decode(OmiAPI.ActionItemsResponse.self, from: data).actionItems.map(TaskMapper.map)
    }

    /// `PATCH v1/action-items/{id}` with only the completion flag.
    func setActionItem(id: String, completed: Bool) async throws {
        let body = try JSONSerialization.data(withJSONObject: ["completed": completed])
        _ = try await data(.patch, "v1/action-items/\(id)", body: .json(body))
    }

    /// `PATCH v1/action-items/{id}` with new text and due date; `nil` clears the due date (`clear_due_at`).
    func updateActionItem(id: String, description: String, dueAt: Date?) async throws -> ActionItem {
        var fields: [String: Any] = ["description": description]
        if let dueAt {
            fields["due_at"] = ISO8601DateFormatter().string(from: dueAt)
        } else {
            fields["clear_due_at"] = true
        }
        let body = try JSONSerialization.data(withJSONObject: fields)
        let data = try await data(.patch, "v1/action-items/\(id)", body: .json(body))
        return TaskMapper.map(try decode(OmiAPI.ActionItemResponse.self, from: data))
    }

    /// `PATCH v1/action-items/{id}` with a new canonical status: `cancelled` ("Not a task", the
    /// learning signal), `superseded` with the task it was merged into, `completed`. The backend
    /// derives `completed` from it.
    func setActionItemStatus(id: String, status: ActionItem.Status, supersededBy: String?) async throws {
        var fields: [String: Any] = ["status": status.rawValue]
        if let supersededBy { fields["superseded_by"] = supersededBy }
        let body = try JSONSerialization.data(withJSONObject: fields)
        _ = try await data(.patch, "v1/action-items/\(id)", body: .json(body))
    }

    /// `DELETE v1/action-items/{id}` (204, no body).
    func deleteActionItem(id: String) async throws {
        _ = try await data(.delete, "v1/action-items/\(id)")
    }
}

enum TaskMapper {
    static func map(_ dto: OmiAPI.ActionItemResponse) -> ActionItem {
        ActionItem(
            id: dto.id,
            description: dto.description_,
            isCompleted: dto.completed,
            dueAt: BackendDate.parse(dto.dueAt),
            conversationID: dto.conversationId,
            owner: owner(dto.owner),
            workstreamID: dto.workstreamId,
            createdAt: BackendDate.parse(dto.createdAt),
            indentLevel: min(max(dto.indentLevel ?? 0, 0), 3),
            sortOrder: dto.sortOrder ?? 0,
            exportPlatform: dto.exported == true ? (dto.exportPlatform ?? "unknown") : nil,
            appleReminderID: dto.appleReminderId,
            updatedAt: BackendDate.parse(dto.updatedAt),
            status: status(dto.status, completed: dto.completed),
            supersededBy: dto.supersededBy,
            priority: dto.priority.flatMap { ActionItem.Priority(rawValue: $0.rawValue) },
            dueConfidence: dto.dueConfidence,
            provenance: (dto.provenance ?? []).map { ActionItem.Evidence(kind: $0.kind.rawValue, id: $0.id) },
            goalID: dto.goalId
        )
    }

    /// Older rows have no status: completion decides, as on the backend.
    static func status(_ status: OmiAPI.TaskStatus?, completed: Bool) -> ActionItem.Status {
        switch status {
        case .active: .active
        case .completed: .completed
        case .cancelled: .cancelled
        case .superseded: .superseded
        case ._unknown, nil: completed ? .completed : .active
        }
    }

    static func owner(_ owner: OmiAPI.TaskOwner?) -> ActionItem.Owner {
        switch owner {
        case .user, nil: .user
        case .other: .other
        case .unknown, ._unknown: .unknown
        }
    }
}
