import Foundation
import OmiCore
@testable import OmiNetwork
import Testing

struct PlacesWireTests {
    @Test func conversationKeepsItsGeolocation() throws {
        let geolocated = ConversationMapperTests.json.replacingOccurrences(of: "\"some_future_field\": 42", with: """
        "geolocation": {"latitude": 52.52, "longitude": 13.405, "address": "Unter den Linden 1, Mitte, Berlin, 10117",
          "google_place_id": "abc", "captured_at": "2026-10-07T17:08:40Z", "capture_source": "current_position"}
        """)
        let conversation = try ConversationMapper.map(JSONDecoder().decode(OmiAPI.Conversation.self, from: Data(geolocated.utf8)))
        #expect(conversation.location == ConversationLocation(
            latitude: 52.52, longitude: 13.405, address: "Unter den Linden 1, Mitte, Berlin, 10117", googlePlaceID: "abc"
        ))
        #expect(conversation.location?.shortAddress == "Mitte, Berlin")
    }

    @Test func liveSegmentsCarryTheMatchedPerson() {
        let event = ListenEvent.parse(#"[{"id":"s1","text":"Hi","speaker_id":1,"is_user":false,"start":0,"end":1,"person_id":"p1"}]"#)
        guard case let .segments(segments) = event else {
            Issue.record("not segments")
            return
        }
        #expect(segments.first?.personID == "p1")
        #expect(ListenEvent.parse(#"[{"id":"s2","text":"Hi","person_id":""}]"#) == .segments([
            LiveSegment(id: "s2", text: "Hi", speaker: nil, speakerID: nil, isUser: false, start: 0, end: 0),
        ]))
    }
}
