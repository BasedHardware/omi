import Foundation
import OmiCore

/// Editing what a conversation says and how the list is organized: the summary text, folders
/// with their look, "Was this helpful?", recaps, and the meetings Omi did not capture.
public protocol ConversationContentAPI: Sendable {
    /// `appID` `nil` edits Omi's own summary; otherwise that app's result.
    func updateConversationSummary(conversationID: String, appID: String?, content: String) async throws
    /// Calendar meetings in `[start, end]` without a kept conversation; empty without a calendar.
    func captureGaps(from start: Date, to end: Date) async throws -> [CaptureGap]
    func createFolder(_ draft: FolderDraft) async throws -> Folder
    func updateFolder(id: String, _ draft: FolderDraft) async throws -> Folder
    /// `moveTo` `nil`: the folder's conversations leave every folder.
    func deleteFolder(id: String, moveTo folderID: String?) async throws
    /// True when the backend's receipt says the answer was stored.
    func sendConversationFeedback(
        conversationID: String, kind: ConversationFeedbackKind, helpful: Bool, reason: SummaryFeedbackReason?, feedbackID: String
    ) async throws -> Bool
    func deleteDailySummary(id: String) async throws
}

/// Contracts from `backend/routers/conversations.py`, `folders.py`, `mobile_feedback.py`,
/// `users.py` and `google_calendar.py`.
public extension APIClient {
    /// `PATCH v1/conversations/{id}/summary` `{app_id, content}` (the backend drops the generated
    /// sections when Omi's own summary changes).
    func updateConversationSummary(conversationID: String, appID: String?, content: String) async throws {
        let body = try JSONSerialization.data(withJSONObject: ["app_id": appID.map { $0 as Any } ?? NSNull(), "content": content])
        _ = try await data(.patch, "v1/conversations/\(conversationID)/summary", body: .json(body))
    }

    /// `GET v1/calendar/capture-gaps?start=&end=` (at most 31 days). A 400 means no Google
    /// Calendar is connected: nothing was missed that Omi could know about.
    func captureGaps(from start: Date, to end: Date) async throws -> [CaptureGap] {
        let items = [URLQueryItem(name: "start", value: Self.utc(start)), URLQueryItem(name: "end", value: Self.utc(end))]
        do {
            let array = try await JSONSerialization.jsonObject(
                with: data(.get, "v1/calendar/capture-gaps", query: items)
            ) as? [[String: Any]]
            return (array ?? []).compactMap(ConversationContentMapper.captureGap)
        } catch let APIError.http(status, _) where status == 400 {
            return []
        }
    }

    /// `POST v1/folders` `{name, icon, color, description}`.
    func createFolder(_ draft: FolderDraft) async throws -> Folder {
        let body = try JSONSerialization.data(withJSONObject: ConversationContentMapper.folderBody(draft))
        return try await ConversationContentMapper.folder(data(.post, "v1/folders", body: .json(body)))
    }

    /// `PATCH v1/folders/{id}` with the edited fields.
    func updateFolder(id: String, _ draft: FolderDraft) async throws -> Folder {
        let body = try JSONSerialization.data(withJSONObject: ConversationContentMapper.folderBody(draft))
        return try await ConversationContentMapper.folder(data(.patch, "v1/folders/\(id)", body: .json(body)))
    }

    /// `DELETE v1/folders/{id}?move_to_folder_id=`.
    func deleteFolder(id: String, moveTo folderID: String?) async throws {
        _ = try await data(.delete, "v1/folders/\(id)", query: folderID.map { [URLQueryItem(name: "move_to_folder_id", value: $0)] } ?? [])
    }

    /// `POST v1/mobile/feedback`: +1, or -1 with a reason, about the summary or the recording.
    /// `feedbackID` is reused on retry.
    func sendConversationFeedback(
        conversationID: String, kind: ConversationFeedbackKind, helpful: Bool, reason: SummaryFeedbackReason?, feedbackID: String
    ) async throws -> Bool {
        var body: [String: Any] = [
            "schema_version": "mobile_feedback.v1",
            "feedback_id": feedbackID,
            "kind": kind.rawValue,
            "target_kind": "conversation",
            "target_id": conversationID,
            "value": helpful ? 1 : -1,
            "client_app_namespace": "omi-native-ios",
        ]
        if let reason, !helpful { body["reason"] = reason.rawValue }
        let receipt = try await JSONSerialization.jsonObject(
            with: data(.post, "v1/mobile/feedback", body: .json(JSONSerialization.data(withJSONObject: body)))
        ) as? [String: Any]
        return receipt?["schema_version"] as? String == "mobile_feedback_receipt.v1" && receipt?["persisted"] as? Bool == true
            && receipt?["feedback_id"] as? String == feedbackID
    }

    /// `DELETE v1/users/daily-summaries/{id}`; a recap already gone counts as deleted.
    func deleteDailySummary(id: String) async throws {
        do {
            _ = try await data(.delete, "v1/users/daily-summaries/\(id)")
        } catch let APIError.http(status, _) where status == 404 {
            return
        }
    }
}

enum ConversationContentMapper {
    static func captureGap(_ json: [String: Any]) -> CaptureGap? {
        guard let id = json["event_id"] as? String, let start = BackendDate.parse(json["start_time"] as? String),
              let end = BackendDate.parse(json["end_time"] as? String) else { return nil }
        let title = (json["title"] as? String ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        return CaptureGap(id: id, title: title, start: start, end: end)
    }

    static func folderBody(_ draft: FolderDraft) -> [String: Any] {
        ["name": draft.name, "icon": draft.icon, "color": draft.color, "description": draft.description]
    }

    static func folder(_ data: Data) throws -> Folder {
        guard let object = try JSONSerialization.jsonObject(with: data) as? [String: Any], let folder = FolderMapper.map(object) else {
            throw APIError.decoding("folder")
        }
        return folder
    }
}
