import Foundation
import OmiCore

/// Naming a voice while the conversation is still being recorded (Flutter `capture_controller`
/// `assignSpeakerToConversation`): the in-progress conversation gets the same REST assignment as a
/// finished one (`assignSpeaker`), then the listen socket hears `speaker_assigned`.
public extension APIClient {
    /// `GET v1/conversations?statuses=in_progress&limit=1` (Flutter `_loadInProgressConversation`).
    func inProgressConversationID() async throws -> String? {
        let data = try await data(.get, "v1/conversations", query: [
            URLQueryItem(name: "statuses", value: "in_progress"), URLQueryItem(name: "limit", value: "1"),
        ])
        let list = try JSONSerialization.jsonObject(with: data) as? [[String: Any]]
        return list?.first?["id"] as? String
    }
}
