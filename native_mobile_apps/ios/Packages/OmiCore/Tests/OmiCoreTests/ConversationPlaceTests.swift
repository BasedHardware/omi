import Foundation
@testable import OmiCore
import Testing

struct ConversationPlaceTests {
    static func conversation(_ id: String, _ location: ConversationLocation?) -> Conversation {
        Conversation(
            id: id, title: id, overview: "", emoji: nil, category: nil, createdAt: .distantPast, startedAt: nil, finishedAt: nil,
            status: .completed, isStarred: false, actionItemCount: 0, location: location
        )
    }

    @Test func pointsWithin100MetresShareAPlace() {
        let office = ConversationLocation(latitude: 52.5200, longitude: 13.4050)
        let nextDoor = ConversationLocation(latitude: 52.5203, longitude: 13.4052) // ~36 m
        let home = ConversationLocation(latitude: 52.5400, longitude: 13.4100) // ~2 km
        let places = ConversationPlace.group([
            Self.conversation("c3", nextDoor), Self.conversation("c1", office), Self.conversation("c2", home),
            Self.conversation("c4", nil), Self.conversation("c5", ConversationLocation(latitude: 120, longitude: 0)),
        ])
        #expect(places.map { $0.conversations.map(\.id) } == [["c1", "c3"], ["c2"]])
        #expect(places.first?.location == office)
        #expect(places.first?.id == "c1,c3")
    }

    @Test func groupingDoesNotDependOnArrivalOrder() {
        let points = (0 ..< 5).map { index in
            Self.conversation("c\(index)", ConversationLocation(latitude: 48.137 + Double(index) * 0.0006, longitude: 11.575))
        }
        #expect(ConversationPlace.group(points) == ConversationPlace.group(points.reversed()))
    }

    @Test func shortAddressKeepsAreaAndCity() {
        #expect(ConversationLocation(latitude: 0, longitude: 0, address: "Unter den Linden 1, Mitte, Berlin, 10117").shortAddress
            == "Mitte, Berlin")
        #expect(ConversationLocation(latitude: 0, longitude: 0, address: "Mitte, Berlin").shortAddress == "Mitte, Berlin")
        #expect(ConversationLocation(latitude: 0, longitude: 0, address: "Berlin").shortAddress == "Berlin")
        #expect(ConversationLocation(latitude: 0, longitude: 0, address: " ").shortAddress == nil)
    }

    @Test func headerCarriesTheBackendFields() throws {
        let snapshot = GeolocationSnapshot(
            latitude: 52.52, longitude: 13.405, altitude: 34, accuracy: -1,
            capturedAt: Date(timeIntervalSince1970: 1_791_400_000), source: .lastKnownPosition
        )
        let header = try #require(snapshot.headerValue)
        let object = try #require(JSONSerialization.jsonObject(with: Data(header.utf8)) as? [String: Any])
        #expect(object["latitude"] as? Double == 52.52)
        #expect(object["capture_source"] as? String == "last_known_position")
        #expect(object["captured_at"] as? String == "2026-10-07T19:06:40.000Z")
        #expect(object["accuracy"] == nil) // CoreLocation's "invalid" is never sent
        #expect(object["altitude"] as? Double == 34)
        #expect(header.count < 4096)
    }
}
