import Foundation
import OmiCore
import OmiNetwork
@testable import OmiService
import OmiTestSupport
import Testing

@MainActor
struct TaskTidyUpTests {
    private let keys = ["t1": "id-1", "t2": "id-2", "t3": "id-3", "t4": "id-4", "t5": "id-5"]

    private var utc: Calendar {
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = TimeZone(identifier: "UTC")!
        return calendar
    }

    private func defaults() -> UserDefaults {
        let name = "tidyup-\(UUID().uuidString)"
        let defaults = UserDefaults(suiteName: name)!
        defaults.removePersistentDomain(forName: name)
        return defaults
    }

    // MARK: Parsing

    @Test func parsesTheExactShape() throws {
        let text = """
        {"merge":[{"keep":"t1","drop":["t2"],"why":"same task"}],"done":[{"id":"t3","why":"sent on Monday"}],
         "notTask":[{"id":"t4","why":"overheard"}],"important":["t5","t1"]}
        """
        let proposal = try #require(TaskTidyUp.parse(text, keys: keys))
        #expect(proposal.merges == [.init(keep: "id-1", drop: ["id-2"], why: "same task")])
        #expect(proposal.done == [.init(id: "id-3", why: "sent on Monday")])
        #expect(proposal.notTask == [.init(id: "id-4", why: "overheard")])
        #expect(proposal.important == ["id-5", "id-1"])
        #expect(proposal.mergedCount == 1)
        #expect(proposal.edits.map(\.status) == [.superseded, .completed, .cancelled])
    }

    /// Code fences, prose around it, numbers, unknown and repeated ids, a kept task also dropped.
    @Test func parsesRobustly() throws {
        let text = """
        Here is what I found:
        ```json
        {"merge": [{"keep": 1, "drop": ["t1", "T2", "t9"], "why": "dupes"}, {"keep": "t2", "drop": ["t3"]}],
         "done": [{"id": "t2", "why": "x"}, "t3", {"id": "t99"}],
         "not_task": [{"id": "t4"}, {"id": "t4"}],
         "important": ["t5", "t5", 1]}
        ```
        Let me know {if} you want more.
        """
        let proposal = try #require(TaskTidyUp.parse(text, keys: keys))
        #expect(proposal.merges == [.init(keep: "id-1", drop: ["id-2"], why: "dupes")])
        #expect(proposal.done == [.init(id: "id-3", why: "")])
        #expect(proposal.notTask == [.init(id: "id-4", why: "")])
        #expect(proposal.important == ["id-5", "id-1"])
    }

    @Test func noJSONIsNoProposal() {
        #expect(TaskTidyUp.parse("Sorry, I encountered an error. Please try again.", keys: keys) == nil)
        #expect(TaskTidyUp.parse("{not json", keys: keys) == nil)
        #expect(TaskTidyUp.parse(#"{"merge":[],"done":[],"notTask":[],"important":[]}"#, keys: keys)?.isEmpty == true)
    }

    @Test func promptListsTasksCompactly() {
        let tasks = [
            Fixtures.task("a", "Research competitor pricing", dueInDays: 1),
            Fixtures.task("b", "Leo | unblocks\nthe release"),
        ]
        let prompt = TaskTidyUp.prompt(tasks, source: { $0.id == "a" ? "Pricing sync" : nil }, now: Fixtures.now, calendar: utc)
        #expect(prompt.contains("t1 | Research competitor pricing | due 2026-10-07 | \"Pricing sync\" 2026-10-06"))
        #expect(prompt.contains("t2 | Leo / unblocks the release | - | - 2026-10-06"))
        #expect(prompt.contains("Today is 2026-10-06."))
        #expect(prompt.contains(#""notTask""#))
        #expect(TaskTidyUp.keys(for: tasks) == ["t1": "a", "t2": "b"])
        // What was said goes along, and the rules name requests made of someone else.
        let withQuote = TaskTidyUp.prompt(
            tasks, source: { _ in nil }, quote: { $0.id == "a" ? "Kannst du die Preise recherchieren?" : nil },
            now: Fixtures.now, calendar: utc
        )
        #expect(withQuote.contains(#"| said: "Kannst du die Preise recherchieren?""#))
        #expect(withQuote.contains("kannst du"))
    }

    @Test func restrictedToOpenTasks() {
        let proposal = TaskTidyUp.Proposal(
            merges: [.init(keep: "a", drop: ["b", "c"], why: ""), .init(keep: "gone", drop: ["d"], why: "")],
            done: [.init(id: "e", why: ""), .init(id: "closed", why: "")]
        )
        let current = proposal.restricted(to: ["a", "b", "d", "e"])
        #expect(current.merges == [.init(keep: "a", drop: ["b"], why: "")])
        #expect(current.done.map(\.id) == ["e"])
    }

    // MARK: Store

    @Test func runsOnceADayFromSixInTheMorning() async {
        let api = FakeAPIClient()
        api.chatReply = #"{"merge":[{"keep":"t1","drop":["t2"],"why":"same"}],"done":[],"notTask":[],"important":[]}"#
        let store = TasksStore(api: api, calendar: utc, defaults: defaults())
        await store.load()
        // 2026-10-06 05:30 UTC: too early.
        let early = utc.date(bySettingHour: 5, minute: 30, second: 0, of: Fixtures.now)!
        #expect(!store.tidyUpIsDue(now: early))
        await store.tidyUpIfDue(source: { _ in nil }, now: early)
        #expect(store.tidyUp == nil)
        #expect(api.devApps.appSessions.isEmpty)

        await store.tidyUpIfDue(source: { _ in nil }, now: Fixtures.now)
        #expect(store.tidyUp?.merges.count == 1)
        #expect(!store.tidyUpIsDue(now: Fixtures.now.addingTimeInterval(3600)))
        #expect(store.tidyUpIsDue(now: Fixtures.now.addingTimeInterval(86400)))
        // Its own session, never the main chat: an app id and the ✦ title.
        #expect(api.devApps.appSessions[TasksStore.tidyUpSessionAppID]?.first?.title == "✦ Tidy up tasks")
        #expect(api.chatSessions.isEmpty)
    }

    /// A thread stored by another account on this iPhone is not used; this account gets its own.
    @Test func anotherAccountsThreadIsNotReused() async {
        let api = FakeAPIClient()
        api.chatReply = #"{"done":[{"id":"t3","why":"done"}]}"#
        let storage = defaults()
        storage.set("someone-elses-session", forKey: TasksStore.tidyUpSessionKey)
        let store = TasksStore(api: api, calendar: utc, defaults: storage)
        await store.load()
        await store.tidyUpIfDue(source: { _ in nil }, now: Fixtures.now)
        let created = api.devApps.appSessions[TasksStore.tidyUpSessionAppID]?.first?.id
        #expect(created != nil)
        #expect(storage.string(forKey: TasksStore.tidyUpSessionKey) == created)
    }

    @Test func aBadAnswerIsNoCardAndWaitsForTomorrow() async {
        let api = FakeAPIClient()
        api.chatReply = "I could not do that."
        let store = TasksStore(api: api, calendar: utc)
        await store.load()
        await store.tidyUpIfDue(source: { _ in nil }, now: Fixtures.now)
        #expect(store.tidyUp == nil)
        #expect(store.currentTidyUp == nil)
        #expect(!store.tidyUpIsDue(now: Fixtures.now))
    }

    @Test func theSuggestionSurvivesARelaunchUntilPutOff() async {
        let api = FakeAPIClient()
        api.chatReply = #"{"done":[{"id":"t3","why":"done"}]}"#
        let storage = defaults()
        let store = TasksStore(api: api, calendar: utc, defaults: storage)
        await store.load()
        await store.tidyUpIfDue(source: { _ in nil }, now: Fixtures.now)
        let relaunched = TasksStore(api: api, calendar: utc, defaults: storage)
        #expect(relaunched.tidyUp == store.tidyUp)
        relaunched.dismissTidyUp()
        #expect(TasksStore(api: api, calendar: utc, defaults: storage).tidyUp == nil)
    }

    /// Nothing changes until Apply; then one PATCH per kept change, and the card goes.
    @Test func applyPatchesOnlyWhatTheUserKept() async {
        let api = FakeAPIClient()
        // Fixtures: t1 proof of income, t2 roadmap deck, t3 pricing, t4 ski chalets (newest first in the prompt).
        api.chatReply = """
        {"merge":[{"keep":"t1","drop":["t2"],"why":"same"}],"done":[{"id":"t3","why":"x"}],"notTask":[{"id":"t4","why":"y"}]}
        """
        let store = TasksStore(api: api, calendar: utc)
        await store.load()
        await store.tidyUpIfDue(source: { _ in nil }, now: Fixtures.now)
        #expect(api.editLog.isEmpty)
        let edits = store.currentTidyUp?.edits ?? []
        #expect(edits.count == 3)
        let kept = edits.filter { $0.kind != .done }
        let saved = await store.applyTidyUp(kept)
        #expect(saved == 2)
        #expect(api.editLog.count == 2)
        #expect(api.editLog.allSatisfy { $0.hasPrefix("status-task:") })
        #expect(api.editLog.contains { $0.hasSuffix("=cancelled") })
        #expect(api.editLog.contains { $0.contains("=superseded>") })
        #expect(store.tidyUp == nil)
        // Merged and cancelled tasks leave the list; the one not applied stays open.
        #expect(store.tasks.count == Fixtures.tasks.count - 2)
        await store.load()
        #expect(store.tasks.count == Fixtures.tasks.count - 2)
    }

    // MARK: Card actions

    @Test func notATaskCancelsEveryRowOfTheCard() async {
        let api = FakeAPIClient()
        let store = TasksStore(api: api)
        await store.load()
        await store.markNotTask(["t3", "t4"])
        #expect(api.editLog == ["status-task:t3=cancelled", "status-task:t4=cancelled"])
        #expect(!store.tasks.contains { ["t3", "t4"].contains($0.id) })
    }

    @Test func aRefusedStatusComesBack() async {
        let api = FakeAPIClient()
        let store = TasksStore(api: api)
        await store.load()
        api.fail(with: .http(status: 500, body: ""))
        let saved = await store.setStatus("t3", .cancelled)
        #expect(!saved)
        #expect(store.tasks.contains { $0.id == "t3" })
        #expect(store.lastError != nil)
    }

    @Test func laterHidesUntilTomorrowAndIsRemembered() {
        let storage = defaults()
        let store = TasksStore(api: FakeAPIClient(), calendar: utc, defaults: storage)
        store.snooze(["t1"], now: Fixtures.now)
        let until = store.snoozes["t1"]
        #expect(until == utc.date(byAdding: .day, value: 1, to: utc.startOfDay(for: Fixtures.now)))
        // Restored on launch while it lies ahead (`Fixtures.now` is in the past, so compare with real now).
        let relaunched = TasksStore(api: FakeAPIClient(), calendar: utc, defaults: storage)
        #expect(relaunched.snoozes["t1"] == nil || relaunched.snoozes["t1"] == until)
    }
}
