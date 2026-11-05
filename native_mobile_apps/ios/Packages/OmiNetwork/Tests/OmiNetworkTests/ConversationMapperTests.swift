import Foundation
@testable import OmiNetwork
import Testing

struct ConversationMapperTests {
    static let json = """
    {
      "id": "c1",
      "created_at": "2026-10-06T09:00:00.123456+00:00",
      "started_at": "2026-10-06T09:00:00+00:00",
      "finished_at": "2026-10-06T09:42:00+00:00",
      "status": "completed",
      "starred": true,
      "structured": {
        "title": "Q4 planning",
        "overview": "Agreed on launch dates.",
        "emoji": "📅",
        "category": "business",
        "action_items": [{"description": "Send deck", "completed": false}]
      },
      "transcript_segments": [],
      "some_future_field": 42
    }
    """

    @Test func mapsWireConversation() throws {
        let dto = try JSONDecoder().decode(OmiAPI.Conversation.self, from: Data(Self.json.utf8))
        let conversation = ConversationMapper.map(dto)
        #expect(conversation.title == "Q4 planning")
        #expect(conversation.emoji == "📅")
        #expect(conversation.status == .completed)
        #expect(conversation.isStarred)
        #expect(conversation.actionItemCount == 1)
        #expect(conversation.duration == TimeInterval(42 * 60))
    }

    @Test func unknownStatusDoesNotFail() throws {
        let patched = Self.json.replacingOccurrences(of: "\"completed\"", with: "\"teleporting\"")
        let dto = try JSONDecoder().decode(OmiAPI.Conversation.self, from: Data(patched.utf8))
        #expect(ConversationMapper.map(dto).status == .unknown)
    }
}
