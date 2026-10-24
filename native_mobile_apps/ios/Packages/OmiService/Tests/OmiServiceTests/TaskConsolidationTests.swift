import Foundation
import OmiCore
@testable import OmiService
import OmiTestSupport
import Testing

/// Home's condensed tasks, with titles as they come out of real conversations (en + de).
struct TaskConsolidationTests {
    private var utc: Calendar {
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = TimeZone(identifier: "UTC")!
        return calendar
    }

    private func task(
        _ id: String, _ text: String, due: Double? = nil, owner: ActionItem.Owner = .user, conversation: String? = "c1",
        createdDaysAgo: Double = 1, priority: ActionItem.Priority? = nil, status: ActionItem.Status? = nil, done: Bool = false,
        dueConfidence: Double? = nil
    ) -> ActionItem {
        ActionItem(
            id: id, description: text, isCompleted: done, dueAt: due.map { Fixtures.now.addingTimeInterval($0 * 86400) },
            conversationID: conversation, owner: owner, workstreamID: nil,
            createdAt: Fixtures.now.addingTimeInterval(-createdDaysAgo * 86400), status: status, priority: priority,
            dueConfidence: dueConfidence
        )
    }

    private func signals(_ change: (inout TaskConsolidation.Signals) -> Void = { _ in }) -> TaskConsolidation.Signals {
        var signals = TaskConsolidation.Signals(now: Fixtures.now, calendar: utc)
        change(&signals)
        return signals
    }

    // MARK: Duplicates

    /// Real doubles: the same task extracted twice.
    @Test func leonsDuplicatesMerge() {
        let groups = TaskConsolidation.groups([
            task("a", "Leo unblocks the firmware release", owner: .other, conversation: "demo-2"),
            task("b", "Leo unblocks the firmware release", owner: .other, conversation: "demo-2"),
            task("c", "Research competitor pricing", due: 5, conversation: "demo-1"),
            task("d", "Research competitor pricing", due: 5, conversation: "pricing-sync"),
            task("e", "Draft agent roadmap memo", due: 3),
        ])
        #expect(groups.map(\.ids) == [["a", "b"], ["c", "d"], ["e"]])
        #expect(groups[1].conversationIDs == ["demo-1", "pricing-sync"])
        // Two rows from one conversation are one source.
        #expect(groups[0].conversationIDs == ["demo-2"])
    }

    @Test func sameMeaningAcrossWordingMerges() {
        #expect(TaskConsolidation.isDuplicate("Send Anna the roadmap deck", "Send the roadmap deck to Anna"))
        #expect(TaskConsolidation.isDuplicate("Schicke Anna das Angebot", "Schick Anna das Angebot"))
        #expect(TaskConsolidation.isDuplicate("Book physio session in two weeks", "Book a physio session in two weeks"))
        #expect(TaskConsolidation.similarity("Research competitor pricing", "Research competitor pricing") == 1)
    }

    /// Related but different work stays apart (the AI tidy-up may still propose merging them).
    @Test func differentTasksStayApart() {
        #expect(!TaskConsolidation.isDuplicate(
            "Research other software to improve app", "Research possibilities for instinct and other software"
        ))
        #expect(!TaskConsolidation.isDuplicate(
            "Maximize customer value and shorten payback period", "Figure out strategies to maximize payback period"
        ))
        #expect(!TaskConsolidation.isDuplicate("Email Anna", "Email Ben"))
        // Same words, another verb: not the same task.
        #expect(!TaskConsolidation.isDuplicate("Send the pricing deck", "Review the pricing deck"))
        #expect(!TaskConsolidation.isDuplicate("Ask Leo for the firmware ETA", "Leo unblocks the firmware release"))
    }

    @Test func theKeptTaskHasTheDueDate() {
        let groups = TaskConsolidation.groups([
            task("a", "Research competitor pricing"),
            task("b", "Research competitor pricing", due: 2),
        ])
        #expect(groups.first?.task.id == "b")
        #expect(groups.first?.duplicates.map(\.id) == ["a"])
    }

    // MARK: Hiding

    @Test func onlyTheUsersOwnOpenTasks() {
        #expect(TaskConsolidation.isCandidate(task("a", "Plan trip to Palo Alto next Monday or Tuesday")))
        #expect(TaskConsolidation.isCandidate(task("a", "Ziehe Transkript von letzter Aufnahme auf Handy", owner: .user)))
        #expect(!TaskConsolidation.isCandidate(task("a", "Send proof of income to landlord", done: true)))
        #expect(!TaskConsolidation.isCandidate(task("a", "Update product pages for app store", owner: .other)))
        // Someone else's commitment even when the owner is unknown.
        #expect(!TaskConsolidation.isCandidate(task("a", "Leo unblocks the firmware release", owner: .unknown)))
        #expect(!TaskConsolidation.isCandidate(task("a", "Northwind sends term sheet draft", owner: .unknown)))
        #expect(!TaskConsolidation.isCandidate(task("a", "Anna schickt das Angebot", owner: .unknown)))
        // An English imperative whose object ends in "-t" is not a German third person.
        #expect(TaskConsolidation.isCandidate(task("a", "Renew passport", owner: .unknown)))
        // Gone for the user: merged or "Not a task".
        #expect(!TaskConsolidation.isCandidate(task("a", "Research competitor pricing", status: .superseded)))
        #expect(!TaskConsolidation.isCandidate(task("a", "Climb some rocks", status: .cancelled)))
    }

    @Test func fragmentsAreNotTasks() {
        #expect(TaskConsolidation.isFragment("Okay"))
        #expect(TaskConsolidation.isFragment("Do it"))
        #expect(TaskConsolidation.isFragment("Um send the thing"))
        #expect(TaskConsolidation.isFragment("Und dann noch"))
        #expect(TaskConsolidation.isFragment("Talk to the guy about the…"))
        #expect(!TaskConsolidation.isFragment("Handle the battery"))
        #expect(!TaskConsolidation.isFragment("Pay rent"))
        #expect(!TaskConsolidation.isFragment("Frag Anna nach dem Termin"))
    }

    // MARK: Requests to someone else

    /// A user dictating to an assistant on their laptop: the extracted task is the assistant's job.
    @Test func aRequestToAnAssistantIsNotTheUsersTask() {
        let text = "Ziehe Transkript von letzter Aufnahme auf Handy"
        let quote = "Boah, kannst Du dir mal das Transkript ziehen von meiner letzten Aufnahme?"
        #expect(TaskConsolidation.isRequestToSomeoneElse(text, quote: quote))
        #expect(TaskConsolidation.isRequestToSomeoneElse("Send the deck", quote: "Could you send me the deck before Friday?"))
        #expect(TaskConsolidation.isRequestToSomeoneElse("Book a table", quote: "Can you book us a table for eight?"))
        #expect(TaskConsolidation.isRequestToSomeoneElse("Rechnung schicken", quote: "Könntest du mir bitte die Rechnung schicken?"))
        // About himself: still his.
        #expect(!TaskConsolidation.isRequestToSomeoneElse("Call mom", quote: "Can you remind me to call mom tonight?"))
        let aboutHimself = "Kannst du dir vorstellen, ich muss noch die Steuer machen."
        #expect(!TaskConsolidation.isRequestToSomeoneElse("Steuer machen", quote: aboutHimself))
        #expect(!TaskConsolidation.isRequestToSomeoneElse(text, quote: "Ich ziehe nachher das Transkript auf mein Handy."))
        #expect(!TaskConsolidation.isRequestToSomeoneElse(text, quote: nil))
    }

    @Test func requestsToSomeoneElseStayOutOfNeedsYou() {
        let tasks = [
            task("ask", "Ziehe Transkript von letzter Aufnahme auf Handy", due: -1),
            task("own", "Send Anna follow-up invite draft", due: -1),
        ]
        let quotes = ["ask": "Boah, kannst Du dir mal das Transkript ziehen von meiner letzten Aufnahme?"]
        let cards = TaskConsolidation.cards(tasks, signals: signals { $0.quotes = quotes }).active
        #expect(cards.map(\.id) == ["own"])
        // Without the words it is a task like any other.
        #expect(TaskConsolidation.cards(tasks, signals: signals()).active.count == 2)
    }

    // MARK: Deadlines

    /// The backend filled in 23:59 of the day it was heard (Berlin), no time was said: not overdue
    /// the next day.
    @Test func endOfCreationDayIsNoRealDeadline() throws {
        var berlin = Calendar(identifier: .gregorian)
        berlin.timeZone = try #require(TimeZone(identifier: "Europe/Berlin"))
        let created = try #require(ISO8601DateFormatter().date(from: "2026-10-07T12:40:00Z"))
        let due = try #require(ISO8601DateFormatter().date(from: "2026-10-07T21:59:00Z")) // 23:59 in Berlin
        let now = try #require(ISO8601DateFormatter().date(from: "2026-10-08T09:00:00Z"))
        let guessed = ActionItem(
            id: "z", description: "Ziehe Transkript von letzter Aufnahme auf Handy", isCompleted: false, dueAt: due,
            conversationID: "cb5bbc97", owner: .user, workstreamID: nil, createdAt: created, dueConfidence: 1
        )
        let quote = "Boah, kannst Du dir mal das Transkript ziehen von meiner letzten Aufnahme?"
        #expect(TaskConsolidation.deadline(guessed, quote: quote, calendar: berlin) == nil)
        #expect(TaskConsolidation.deadline(guessed, quote: nil, calendar: berlin) == nil)
        // A time said out loud keeps it.
        #expect(TaskConsolidation.deadline(guessed, quote: "Das muss heute noch raus", calendar: berlin) == due)
        #expect(TaskConsolidation.deadline(guessed, quote: "Send it by end of day", calendar: berlin) == due)
        // Another day, or another time: a real date.
        var later = guessed
        later.dueAt = due.addingTimeInterval(86400)
        #expect(TaskConsolidation.deadline(later, quote: nil, calendar: berlin) == later.dueAt)
        var noon = guessed
        noon.dueAt = due.addingTimeInterval(-10 * 3600)
        #expect(TaskConsolidation.deadline(noon, quote: nil, calendar: berlin) == noon.dueAt)
        // On Home the next morning it is no "Overdue" card.
        let signals = TaskConsolidation.Signals(now: now, calendar: berlin)
        #expect(TaskConsolidation.cards([guessed], signals: signals).active.isEmpty)
    }

    // MARK: Ranking

    /// Overdue, someone waits, picked, due within two days, high priority, Omi can do it, newest.
    @Test func rankOrder() {
        let tasks = [
            task("new", "Integrate with AI and enable export for conversations", createdDaysAgo: 0, priority: .high),
            task("soon", "Climb some rocks", due: 1.5),
            task("omi", "Draft agent roadmap memo", due: 1.5),
            task("pick", "Implement yearly subscription option"),
            task("waits", "Reply to Anna about the offsite"),
            task("late", "Ziehe Transkript von letzter Aufnahme auf Handy", due: -1),
            task("calm", "Copy every step from the successful campaign template"),
        ]
        let cards = TaskConsolidation.cards(tasks, signals: signals { $0.picks = ["pick"] }).active
        #expect(cards.map(\.id) == ["late", "waits", "pick", "omi", "soon", "new"])
        #expect(cards.map(\.kicker) == [.overdue, .waiting, .suggestion, .dueSoon(tasks[2].dueAt!), .dueSoon(tasks[1].dueAt!), .suggestion])
    }

    @Test func dueTodayAndGuessedDueDates() {
        let tasks = [
            task("today", "Send Anna follow-up invite draft", due: 0.2),
            // The backend guessed the date: not urgent.
            task("guess", "Archive how to measure retention and spending", due: -1, dueConfidence: 0.2),
        ]
        let cards = TaskConsolidation.cards(tasks, signals: signals()).active
        #expect(cards.map(\.id) == ["today"])
        #expect(cards.first?.kicker == .dueToday)
    }

    @Test func handledAndSnoozedTasksLeaveNeedsYou() {
        let tasks = [
            task("a", "Draft agent roadmap memo", due: -1), task("b", "Draft agent roadmap memo", due: -1),
            task("c", "Book physio session", due: -1), task("d", "Send the deck", due: -1),
        ]
        let result = TaskConsolidation.cards(tasks, signals: signals {
            // Omi works on the duplicate: the whole card goes, not just that row.
            $0.handled = ["b"]
            $0.snoozes = ["c": Fixtures.now.addingTimeInterval(3600), "d": Fixtures.now.addingTimeInterval(-3600)]
        })
        #expect(result.active.map(\.id) == ["d"])
        #expect(result.snoozed.map(\.id) == ["c"])
    }

    /// A real list (2026-10-08): five overdue and the merged memo matter; someday ideas and
    /// someone else's jobs do not.
    @Test func leonsListCondensed() {
        let now = Fixtures.now
        let tasks = [
            task("1", "Ask Leo for the firmware ETA", due: -1, conversation: "demo-2"),
            task("2", "Send Anna follow-up invite draft", due: -1, owner: .unknown, createdDaysAgo: 0.5),
            task("3", "Climb some rocks", due: -1),
            task("4", "Leo unblocks the firmware release", due: 0.5, owner: .other, conversation: "demo-2"),
            task("5", "Leo unblocks the firmware release", due: 0.5, owner: .other, conversation: "demo-2"),
            task("6", "Draft agent roadmap memo", due: 1.5, conversation: "demo-5"),
            task("7", "Draft agent roadmap memo", due: 1.5, conversation: "demo-5"),
            task("8", "Research competitor pricing", due: 5, conversation: "demo-1"),
            task("9", "Research competitor pricing", due: 5, conversation: "demo-1"),
            task("10", "Northwind sends term sheet draft", due: 8, owner: .other),
            task("11", "Maximize LTV on back end through email marketing and subscriptions"),
            task("12", "Send proof of income to landlord", due: -3, done: true),
        ]
        let cards = TaskConsolidation.cards(tasks, signals: TaskConsolidation.Signals(now: now, calendar: utc)).active
        #expect(cards.map(\.id) == ["2", "1", "3", "6"])
        #expect(cards.last?.group.ids == ["6", "7"])
    }
}
