import Foundation
@testable import OmiCore
import Testing

/// Source chips under an answer: evidence knows the moment, references fill in the rest.
struct ChatCitationTests {
    let start = Date(timeIntervalSince1970: 1_800_000_000)

    @Test func evidenceFirstThenUncoveredReferences() {
        var message = ChatMessage(id: "m", text: "", sender: .omi, createdAt: start)
        message.references = [
            .init(conversationID: "c1", title: "Roadmap", emoji: "🗺️", createdAt: start),
            .init(conversationID: "c2", title: "Standup", emoji: nil, createdAt: start.addingTimeInterval(-3600)),
        ]
        message.evidence = [
            ChatEvidence(id: "e1", kind: .conversationSegment, state: .available, conversationID: "c1", segmentID: "s", startMs: 60000),
            ChatEvidence(id: "e2", kind: .conversationSegment, state: .available, conversationID: "c1", segmentID: "t", startMs: 60000),
            ChatEvidence(id: "e3", kind: .screen, state: .available),
        ]
        let citations = message.citations()
        #expect(citations.map(\.conversationID) == ["c1", "c2"])
        #expect(citations[0].time == start.addingTimeInterval(60))
        #expect(citations[0].offset == 60)
        #expect(citations[1].time == start.addingTimeInterval(-3600))
        #expect(citations[1].offset == nil)
    }

    @Test func evidenceWithoutAReferenceKeepsItsTitle() {
        var message = ChatMessage(id: "m", text: "", sender: .omi, createdAt: start)
        message.evidence = [
            ChatEvidence(id: "e", kind: .conversationSummary, state: .available, title: "Call with Bo", conversationID: "c9"),
        ]
        #expect(message.citations().map(\.title) == ["Call with Bo"])
        #expect(message.citations().first?.time == nil)
    }
}
