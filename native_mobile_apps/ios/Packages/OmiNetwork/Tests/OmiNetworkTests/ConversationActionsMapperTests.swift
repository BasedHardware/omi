import Foundation
import OmiCore
@testable import OmiNetwork
import Testing

/// The structured summary, folder/visibility fields, folders and audio URLs, shaped like the local
/// backend's responses (2026-10-07).
struct ConversationActionsMapperTests {
    static let json = """
    {
      "id": "c9", "created_at": "2026-10-07T15:22:15.707195Z", "status": "completed",
      "folder_id": "f-personal", "visibility": "shared", "is_locked": false, "summary_retryable": true,
      "structured": {
        "title": "Groceries", "overview": "",
        "sections": [{"heading": "List", "body_markdown": "Milk, eggs.", "source_segment_ids": []},
                     {"heading": "Empty", "body_markdown": "  "}],
        "insights": [{"kind": "key_point", "text": "Shop at ten"}],
        "events": [{"title": "Grocery Shopping", "description": "Buy milk.", "start": "2026-10-08T10:00:00Z", "duration": 60}]
      },
      "apps_results": [{"app_id": "a1", "content": "  "}, {"app_id": "a2", "content": "## Coach\\nGood pace."},
                       {"app_id": "a3", "content": "Other take."}],
      "transcript_segments": [{"id": "s1", "text": "Hi", "is_user": true, "start": 0, "end": 1}],
      "audio_files": [{"id": "af1", "uid": "u", "conversation_id": "c9", "chunk_timestamps": [], "duration": 8}]
    }
    """

    @Test func mapsTheStructuredSummary() throws {
        let detail = try ConversationMapper.detail(JSONDecoder().decode(OmiAPI.Conversation.self, from: Data(Self.json.utf8)))
        // The first app result with content wins; the rest follow.
        #expect(detail.summary == "## Coach\nGood pace.")
        #expect(detail.otherSummaries.map(\.appID) == ["a3"])
        #expect(detail.keyPoints == ["Shop at ten"])
        #expect(detail.events.first?.title == "Grocery Shopping")
        #expect(detail.events.first?.duration == 60)
        #expect(detail.hasAudio)
        #expect(detail.transcript.first?.segmentID == "s1")
        #expect(detail.conversation.folderID == "f-personal")
        #expect(detail.conversation.visibility == .shared)
        #expect(detail.conversation.summaryFailed)
    }

    @Test func sectionsStandInForAMissingOverview() {
        let sections = [OmiAPI.Section(bodyMarkdown: "Milk.", heading: "List", kind: nil, sourceSegmentIds: nil)]
        #expect(ConversationMapper.summary(overview: " ", sections: sections) == "## List\n\nMilk.")
        #expect(ConversationMapper.summary(overview: "Plan.", sections: sections) == "Plan.")
    }

    @Test func mapsFolders() {
        let folder = FolderMapper.map(["id": "f1", "name": "Work", "icon": "💼", "is_system": true, "order": 2, "conversation_count": 4])
        #expect(folder == Folder(id: "f1", name: "Work", icon: "💼", color: "#6B7280", isSystem: true, order: 2, conversationCount: 4))
        #expect(FolderMapper.map(["name": "No id"]) == nil)
    }

    @Test func picksThePlayableAudio() throws {
        let url = "https://storage.example/c.mp3"
        let dense: [String: Any] = ["audio_files": [], "conversation_audio": ["status": "cached", "signed_url": url, "duration": 12.0]]
        #expect(try ConversationAudioMapper.map(dense) == .ready(#require(URL(string: url)), duration: 12))
        let building: [String: Any] = ["audio_files": [["id": "a", "status": "pending"]], "poll_after_ms": 1500]
        #expect(ConversationAudioMapper.map(building) == .pending(retryAfter: 1.5))
        #expect(ConversationAudioMapper.map(["audio_files": [], "conversation_audio": NSNull()]) == .unavailable)
    }

    @Test func shareLinkCarriesSourceAndAFreshID() {
        let first = Conversation.shareURL(id: "c9")
        #expect(first.absoluteString.hasPrefix("https://h.omi.me/conversations/c9?s=ios&sid="))
        #expect(first != Conversation.shareURL(id: "c9"))
    }
}
