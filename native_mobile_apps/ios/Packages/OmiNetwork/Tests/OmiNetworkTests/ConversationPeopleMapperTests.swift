import Foundation
import OmiCore
@testable import OmiNetwork
import Testing

struct ConversationPeopleMapperTests {
    private func event(attendees: [String], emails: [String]) -> OmiAPI.CalendarEventLink {
        OmiAPI.CalendarEventLink(
            attendeeEmails: emails, attendees: attendees, endTime: "2026-10-06T10:00:00Z", eventId: "e",
            startTime: "2026-10-06T09:00:00Z", title: "Sync"
        )
    }

    @Test func participantsFirstWithoutAgents() {
        let people = ConversationMapper.people(
            [
                OmiAPI.Participant(email: "maya@stripe.com", name: "Maya", organization: "Stripe", source: "summary"),
                OmiAPI.Participant(isAiAgent: true, name: "Omi", source: "summary"),
            ],
            event: nil
        )
        #expect(people == [ConversationPerson(name: "Maya", email: "maya@stripe.com", organization: "Stripe")])
    }

    @Test func attendeeNamesTakeTheirAddressAndDuplicatesDrop() {
        let people = ConversationMapper.people(
            [OmiAPI.Participant(email: "Maya@stripe.com", name: "Maya", source: "summary")],
            event: event(
                attendees: ["Anna Keller", "maya@stripe.com"],
                emails: ["anna.keller@northwind.io", "maya@stripe.com", "ben@acme.com"]
            )
        )
        #expect(people == [
            ConversationPerson(name: "Maya", email: "Maya@stripe.com"),
            ConversationPerson(name: "Anna Keller", email: "anna.keller@northwind.io"),
            ConversationPerson(name: nil, email: "ben@acme.com"),
        ])
    }

    @Test func mapsThroughTheConversation() throws {
        let json = ConversationMapperTests.json.replacingOccurrences(
            of: "\"emoji\": \"📅\",",
            with: "\"emoji\": \"📅\", \"participants\": [{\"name\": \"Lee\", \"email\": \" \", \"source\": \"summary\"}],"
        )
        let dto = try JSONDecoder().decode(OmiAPI.Conversation.self, from: Data(json.utf8))
        #expect(ConversationMapper.map(dto).people == [ConversationPerson(name: "Lee", email: nil)])
    }
}
