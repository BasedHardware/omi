import Foundation
import OmiCore
@testable import OmiService
import OmiTestSupport
import Testing

/// "Omi takes over" only where Omi can plausibly do the work on a screen, for the user's own tasks.
struct TakeOverEligibilityTests {
    private func task(_ text: String, owner: ActionItem.Owner = .user, done: Bool = false) -> ActionItem {
        var item = Fixtures.task(UUID().uuidString, text)
        item = ActionItem(
            id: item.id, description: text, isCompleted: done, dueAt: nil, conversationID: nil, owner: owner, workstreamID: nil,
            createdAt: Fixtures.now
        )
        return item
    }

    private func can(_ text: String, owner: ActionItem.Owner = .user) -> Bool {
        TakeOverEligibility.canTakeOver(task(text, owner: owner))
    }

    @Test func digitalTasksInEnglish() {
        for text in [
            "Send Anna the Thursday follow-up", "Draft agent roadmap memo", "Research competitor pricing",
            "Ask Leo for the firmware ETA", "Book physio session in two weeks", "Schedule follow-up with Anna on Thursday",
            "Look up ski chalets for February", "Plan trip to Palo Alto next Monday or Tuesday", "Send proof of income to landlord",
            "Email the landlord about the deposit", "Summarize the board call", "Order a new charging cable",
            "Remind Marco about the invoice", "Send Anna follow-up invite draft",
        ] {
            #expect(can(text), "\(text)")
        }
    }

    @Test func digitalTasksInGerman() {
        for text in [
            "Schreib Anna wegen Donnerstag", "Recherchiere Preise der Konkurrenz", "Buche einen Termin beim Physio",
            "Plane die Reise nach Lissabon", "Bestelle neue Kopfhörer", "Erinnere Marco an die Rechnung",
            "Frag Leo nach dem Firmware-Termin", "Entwirf eine Antwort an den Vermieter",
        ] {
            #expect(can(text), "\(text)")
        }
    }

    @Test func physicalAndPersonalTasksAreNot() {
        for text in [
            "Climb some rocks", "Purchase three items at a market", "Go to the gym", "Pick up the dry cleaning",
            "Stretch three times a week", "Klettern gehen", "Wohnung putzen", "Einkaufen auf dem Markt",
            "Ziehe Transkript von letzter Aufnahme auf Handy", "Implement yearly subscription option",
            "Maximize order values on front end to break even", "Choose a market for Chris's quest",
        ] {
            #expect(!can(text), "\(text)")
        }
    }

    @Test func otherPeoplesCommitmentsAreNot() {
        #expect(!can("Leo unblocks the firmware release", owner: .other))
        #expect(!can("Research competitor pricing", owner: .other))
        // The owner can be unknown; a name and a third-person verb still give it away.
        #expect(!can("Leo unblocks the firmware release", owner: .unknown))
        #expect(!can("Northwind sends term sheet draft", owner: .unknown))
        #expect(!can("Anna schickt die Folien", owner: .unknown))
        #expect(can("Send Anna follow-up invite draft", owner: .unknown))
    }

    @Test func finishedTasksAreNot() {
        #expect(!TakeOverEligibility.canTakeOver(task("Send the deck", done: true)))
    }
}
