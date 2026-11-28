import Foundation
import OmiCore
@testable import OmiNetwork
import Testing

struct ChatStreamParsingTests {
    @Test func parsesFrames() {
        #expect(ChatStreamEvent.parse("think: Searching the web|app_id:abc") == .step("Searching the web"))
        #expect(ChatStreamEvent.parse("data: Hello__CRLF__world") == .delta("Hello\nworld"))
        #expect(ChatStreamEvent.parse("memory: saved") == .memorySaved)
        #expect(ChatStreamEvent.parse(#"error: {"error":"quota_exceeded","message":"Out of minutes"}"#) == .failed("Out of minutes"))
        #expect(ChatStreamEvent.parse("error: The response took too long.") == .failed("The response took too long."))
        #expect(ChatStreamEvent.parse("nonsense") == nil)
    }

    @Test func parsesDoneMessage() {
        let json = #"{"id":"m1","text":"Booked.","sender":"ai","created_at":"2026-10-06T10:00:00Z","#
            + #""memories":[{"id":"c1","structured":{"title":"Q4","emoji":"🗺️"}}]}"#
        guard case let .done(message) = ChatStreamEvent.parse("done: " + Data(json.utf8).base64EncodedString()) else {
            Issue.record("expected done")
            return
        }
        #expect(message.id == "m1")
        #expect(message.sender == .omi)
        #expect(message.references.first?.title == "Q4")
    }
}

struct ListenEventTests {
    @Test func parsesSegmentsAndEvents() {
        let segments = ListenEvent
            .parse(#"[{"id":"s1","text":"hi","speaker":"SPEAKER_00","speaker_id":0,"is_user":true,"start":0,"end":1.2}]"#)
        #expect(segments == .segments([LiveSegment(
            id: "s1",
            text: "hi",
            speaker: "SPEAKER_00",
            speakerID: 0,
            isUser: true,
            start: 0,
            end: 1.2
        )]))
        #expect(ListenEvent.parse(#"{"type":"service_status","status":"ready"}"#) == .status("ready"))
        #expect(ListenEvent
            .parse(#"{"type":"conversation_session","conversation_id":"c9","status":"in_progress"}"#) == .conversationStarted(id: "c9"))
        #expect(ListenEvent
            .parse(#"{"type":"memory_created","memory":{"id":"c9"},"conversation_id":"c9"}"#) == .conversationCreated(id: "c9"))
        #expect(ListenEvent.parse("ping") == nil)
    }
}
