import Foundation
import OmiCore
@testable import OmiService
import Testing

struct EntityVisualTests {
    private func conversation(_ people: [ConversationPerson] = [], emoji: String? = "📈", category: String? = "business") -> Conversation {
        Conversation(
            id: "c", title: "Investor call with Northwind", overview: "", emoji: emoji, category: category,
            createdAt: .distantPast, startedAt: nil, finishedAt: nil, status: .completed, isStarred: false,
            actionItemCount: 0, people: people
        )
    }

    private func task(_ text: String) -> ActionItem {
        ActionItem(
            id: "t", description: text, isCompleted: false, dueAt: nil, conversationID: "c",
            owner: .user, workstreamID: nil, createdAt: nil
        )
    }

    @Test func namedServiceWins() {
        #expect(
            EntityVisual.forTask(task("Send the deck via Gmail"), source: conversation())
                == .brand(domain: "gmail.com", bundled: "gmail")
        )
        #expect(
            EntityVisual.forTask(task("Add it to Google Calendar"), source: nil)
                == .brand(domain: "calendar.google.com", bundled: "google_calendar")
        )
    }

    @Test func companyAddressGivesItsDomain() {
        let people = [ConversationPerson(name: "Maya", email: "maya@mail.stripe.com")]
        #expect(EntityVisual.forTask(task("Draft the memo"), source: conversation(people)) == .brand(domain: "stripe.com"))
    }

    @Test func freemailAndPlaceholdersNeverBrand() {
        let people = [
            ConversationPerson(name: "Anna Keller", email: "anna@example.com"),
            ConversationPerson(name: nil, email: "leo@gmail.com"),
            ConversationPerson(name: nil, email: "kim@acme.test"),
        ]
        #expect(
            EntityVisual.forTask(task("Send Anna the follow-up"), source: conversation(people))
                == .person(name: "Anna Keller", email: "anna@example.com")
        )
    }

    @Test func addressOnlyPersonIsNamedFromTheMailbox() {
        let people = [ConversationPerson(name: nil, email: "leo@gmail.com")]
        #expect(EntityVisual.forTask(task("Call Leo back"), source: conversation(people)) == .person(name: "Leo", email: "leo@gmail.com"))
    }

    @Test func titleGuessesAreNotBrands() {
        // "Northwind" alone is a name, not a domain: the emoji stays.
        #expect(EntityVisual.forTask(task("Northwind sends term sheet draft"), source: conversation()) == .emoji("📈", category: "business"))
        // A word that merely contains a service is not that service.
        #expect(EntityVisual.forTask(task("Renumber the slides"), source: conversation()) == .emoji("📈", category: "business"))
    }

    @Test func categoryGlyphWithoutEmoji() {
        #expect(EntityVisual.forTask(task("Book physio"), source: conversation(emoji: nil, category: "health")) == .symbol("heart"))
        #expect(EntityVisual.forTask(task("Book physio"), source: nil) == .symbol("checklist"))
    }

    @Test func conversationPicture() {
        #expect(EntityVisual.forConversation(conversation()) == .emoji("📈", category: "business"))
    }
}
