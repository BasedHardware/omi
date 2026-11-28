import Foundation
import OmiCore
@testable import OmiNetwork
import Testing

/// Sources of an answer (`memories` and the `evidence` envelope, backend `ChatEvidenceReference`).
struct ChatEvidenceMapperTests {
    @Test func decodesEvidenceAndConversationTimes() throws {
        let json = #"{"id":"m9","text":"You promised Anna the deck.","sender":"ai","created_at":"2026-10-07T15:00:00Z","#
            + #""memories":[{"id":"c1","structured":{"title":"Q4 roadmap","emoji":"🗺️"},"created_at":"2026-10-07T14:00:00Z"}],"#
            + #""evidence":{"schema_version":1,"request_id":"r1","references":["#
            + #"{"id":"e1","kind":"conversation_segment","state":"available","title":"Q4 roadmap","conversation_id":"c1","#
            + #""segment_id":"s4","start_ms":305000,"end_ms":312000,"metadata":{}},"#
            + #"{"id":"e2","kind":"conversation_summary","state":"pruned","conversation_id":"c2"},"#
            + #"{"id":"e3","kind":"hologram","state":"later"},"#
            + #"{"id":" ","kind":"request","state":"available"}]}}"#
        let message = try #require(ChatMessageMapper.message(fromJSON: Data(json.utf8)))
        #expect(message.references.first?.createdAt == BackendDate.parse("2026-10-07T14:00:00Z"))
        #expect(message.evidence.map(\.id) == ["e1", "e2", "e3"])
        let segment = try #require(message.evidence.first)
        #expect(segment.kind == .conversationSegment && segment.state == .available)
        #expect(segment.conversationID == "c1" && segment.segmentID == "s4")
        #expect(segment.startMs == 305_000 && segment.endMs == 312_000)
        #expect(message.evidence[1].state == .pruned && !message.evidence[1].opensConversation)
        #expect(message.evidence[2].kind == .unknown && message.evidence[2].state == .unknown)

        // The chip: the conversation's start plus the moment, at 14:05.
        let citations = message.citations()
        #expect(citations.count == 1)
        #expect(citations.first?.title == "Q4 roadmap")
        #expect(citations.first?.offset == 305)
        #expect(citations.first?.time == BackendDate.parse("2026-10-07T14:05:05Z"))
    }

    @Test func noEvidenceIsNoChips() throws {
        let json = #"{"id":"m1","text":"Hi","sender":"ai","evidence":null,"memories":[]}"#
        let message = try #require(ChatMessageMapper.message(fromJSON: Data(json.utf8)))
        #expect(message.evidence.isEmpty)
        #expect(message.citations().isEmpty)
    }
}
