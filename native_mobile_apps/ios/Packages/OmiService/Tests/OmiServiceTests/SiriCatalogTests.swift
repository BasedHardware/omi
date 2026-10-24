import Foundation
import OmiCore
import OmiNetwork
@testable import OmiService
import OmiTestSupport
import Testing

/// What the App Intents entity queries and intents run on.
@MainActor
struct SiriCatalogTests {
    let api = FakeAPIClient()

    func make() -> SiriCatalog {
        SiriCatalog(
            conversations: ConversationsStore(api: api), tasks: TasksStore(api: api),
            memories: MemoriesStore(api: api), chat: ChatStore(api: api, preferences: freshPreferences())
        )
    }

    // MARK: Entity queries

    @Test func entitiesByIdKeepTheOrderAndSkipWhatIsGone() async {
        let catalog = make()
        #expect(await catalog.conversations(ids: ["c3", "gone", "c1"]).map(\.id) == ["c3", "c1"])
        #expect(await catalog.tasks(ids: ["t2", "nope", "t1"]).map(\.id) == ["t2", "t1"])
        #expect(await catalog.memories(ids: ["m3", "m1"]).map(\.id) == ["m3", "m1"])
        #expect(await catalog.folders(ids: ["f-trips"]).map(\.name) == ["Trips"])
    }

    @Test func taskSearchOffersOnlyMyOpenTasksSoonestFirst() async {
        let catalog = make()
        // t5 belongs to someone else, t6 is done; no due date sorts last.
        #expect(await catalog.tasks(matching: "").map(\.id) == ["t1", "t2", "t3", "t4"])
        #expect(await catalog.tasks(matching: "send").map(\.id) == ["t1", "t2"])
        #expect(await catalog.tasks(matching: "book").isEmpty)
        #expect(await catalog.tasks(matching: "book", includeCompleted: true).map(\.id) == ["t6"])
    }

    @Test func conversationMemoryAndFolderSearch() async {
        let catalog = make()
        #expect(await catalog.conversations(matching: "anna").map(\.id) == ["c1"])
        #expect(await catalog.conversations(matching: "overview of dinner").map(\.id) == ["c3"])
        #expect(await catalog.conversations(matching: "  ").count == 4)
        #expect(await catalog.memories(matching: "ski").map(\.id) == ["m3"])
        #expect(await catalog.folders(matching: "").map(\.id) == ["f-work", "f-trips"])
        #expect(await catalog.folders(matching: "trip").map(\.id) == ["f-trips"])
    }

    // MARK: Intents

    @Test func rememberDropsThatAndSaves() async throws {
        let catalog = make()
        let saved = try await catalog.remember("  that I parked on level 3 ")
        #expect(saved.content == "I parked on level 3")
        #expect(api.createdMemories == ["I parked on level 3"])
        await #expect(throws: SiriCatalog.Failure.empty) { try await catalog.remember("  ") }
        api.fail(with: .http(status: 500, body: ""))
        await #expect(throws: SiriCatalog.Failure.notSaved) { try await catalog.remember("Anything") }
    }

    @Test func createAndCompleteTasks() async throws {
        let catalog = make()
        let due = Fixtures.now.addingTimeInterval(3600)
        let task = try await catalog.createTask(" Call Anna ", dueAt: due)
        #expect(task.description == "Call Anna")
        #expect(task.dueAt == due)
        await #expect(throws: SiriCatalog.Failure.empty) { try await catalog.createTask("   ", dueAt: nil) }

        try await catalog.complete(taskID: "t2")
        #expect(catalog.tasks.tasks.first { $0.id == "t2" }?.isCompleted == true)
        // Already done: nothing to send.
        try await catalog.complete(taskID: "t6")
        #expect(api.taskUpdates.map(\.id) == ["t2"])
        await #expect(throws: SiriCatalog.Failure.unknownTask) { try await catalog.complete(taskID: "nope") }
    }

    @Test func failedCompletionReports() async {
        let catalog = make()
        await catalog.tasks.load()
        api.fail(with: .http(status: 500, body: ""))
        await #expect(throws: SiriCatalog.Failure.notSaved) { try await catalog.complete(taskID: "t3") }
        #expect(catalog.tasks.tasks.first { $0.id == "t3" }?.isCompleted == false)
    }

    @Test func askWaitsForTheWholeAnswerAndKeepsItInTheChat() async {
        api.chatReply = "You met Anna about the Q4 roadmap."
        let catalog = make()
        #expect(await catalog.ask("Ask Omi what did I do today") == .answered("You met Anna about the Q4 roadmap."))
        #expect(catalog.chat.messages.suffix(2).map(\.text) == ["what did I do today", "You met Anna about the Q4 roadmap."])
    }

    @Test func askRefusesWhatItShouldNotAnswer() async {
        let catalog = make()
        #expect(await catalog.ask("   ") == .empty)
        #expect(await catalog.ask("remember that I like tea") == .useRemember)
        #expect(catalog.chat.messages.isEmpty)
    }

    @Test func askReportsAFailedAnswer() async {
        api.chatExtras.streamError = APIError.http(status: 500, body: "")
        let catalog = make()
        guard case .failed = await catalog.ask("What's next?") else {
            Issue.record("expected a failure")
            return
        }
    }

    // MARK: Text

    @Test func spokenAnswersAreCutAtAWord() {
        #expect(SiriText.spoken("  Short. ", more: "More in Omi.") == "Short.")
        let long = Array(repeating: "word", count: 200).joined(separator: " ")
        let spoken = SiriText.spoken(long, more: "More in Omi.")
        #expect(spoken.count <= SiriText.spokenLimit)
        #expect(spoken.hasSuffix("word… More in Omi."))
        #expect(SiriText.question("frag Omi nach dem Termin") == "dem Termin")
        #expect(SiriText.memory("dass ich Tee mag") == "ich Tee mag")
    }

    @Test func spotlightRecordsCarryShortTextsAndTheirLinks() {
        let memory = Memory(
            id: "m9", content: String(repeating: "Lange Erinnerung ", count: 40), headline: nil,
            category: "x", createdAt: Fixtures.now, conversationID: nil
        )
        let records = SpotlightRecord.records(
            conversations: Fixtures.conversations, tasks: Fixtures.tasks, memories: Fixtures.memories + [memory]
        )
        #expect(records.filter { $0.kind == .conversation }.count == 4)
        // Someone else's task stays out.
        #expect(!records.contains { $0.id == "t5" })
        #expect(records.first { $0.id == "c1" }?.identifier == "omi://conversation/c1")
        #expect(records.first { $0.id == "t1" }?.link == .task(id: "t1"))
        let long = records.first { $0.id == "m9" }
        #expect(long?.link == .memory(id: "m9"))
        #expect((long?.text.count ?? 0) <= SpotlightRecord.textLimit)
        #expect(long?.title.hasSuffix("…") == true)
    }
}
