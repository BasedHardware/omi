import Foundation
import OmiCore
@testable import OmiService
import OmiTestSupport
import Testing

@MainActor
struct GoalsStoreTests {
    @Test func createsEditsAndTracksProgress() async {
        let api = FakeAPIClient()
        let store = GoalsStore(api: api)
        await store.load()
        #expect(store.goals.isEmpty)

        #expect(await store.create(title: "  Run 5k  ", current: 1, target: 5))
        #expect(!(await store.create(title: "  ", current: 0, target: 1)))
        let id = store.goals[0].id
        #expect(store.goals[0].title == "Run 5k")
        #expect(store.goals[0].progress == 0.2)

        #expect(await store.update(id, title: "Run 10k", current: 2, target: 10))
        #expect(await store.setProgress(id, current: 12))
        #expect(store.goals[0].progress == 1)
        #expect(api.goalsBackend.log == ["list:all", "create:Run 5k", "update:g1=Run 10k", "progress:g1=12.0"])
    }

    @Test func allowsFourGoals() async {
        let api = FakeAPIClient()
        let store = GoalsStore(api: api)
        for index in 1 ... 4 {
            #expect(await store.create(title: "Goal \(index)", current: 0, target: 1))
        }
        #expect(!store.canAdd)
        #expect(!(await store.create(title: "Fifth", current: 0, target: 1)))
    }

    @Test func rollsBackAFailedEdit() async {
        let api = FakeAPIClient()
        api.goalsBackend.goals = [Goal(id: "g1", title: "Read", current: 3, target: 12)]
        let store = GoalsStore(api: api)
        await store.load()
        api.goalsBackend.failing = ["progress"]
        #expect(!(await store.setProgress("g1", current: 4)))
        #expect(store.goals[0].current == 3)
        #expect(store.lastError != nil)
    }

    @Test func deleteHasUndo() async {
        let api = FakeAPIClient()
        api.goalsBackend.goals = [
            Goal(id: "g1", title: "Read", current: 3, target: 12), Goal(id: "g2", title: "Save", current: 1, target: 2),
        ]
        let store = GoalsStore(api: api, undoWindow: .seconds(60))
        await store.load()
        store.deleteWithUndo("g1")
        #expect(store.goals.map(\.id) == ["g2"])
        store.undoDelete()
        #expect(store.goals.map(\.id) == ["g1", "g2"])

        store.deleteWithUndo("g2")
        await store.commitDeletion()
        #expect(api.goalsBackend.log.last == "delete:g2")
        #expect(api.goalsBackend.goals.map(\.id) == ["g1"])
    }
}

/// Reminders in memory, standing in for EventKit.
@MainActor
final class FakeReminders: RemindersAdapter {
    var hasAccess: Bool
    var grantsAccess = true
    var reminders: [String: ReminderSnapshot] = [:]
    private(set) var log: [String] = []

    init(hasAccess: Bool = true) {
        self.hasAccess = hasAccess
    }

    func requestAccess() async -> Bool {
        log.append("request")
        hasAccess = grantsAccess
        return grantsAccess
    }

    func add(title: String, notes _: String?, dueAt: Date?) throws -> String {
        let id = "rem-\(reminders.count + 1)"
        reminders[id] = ReminderSnapshot(title: title, isCompleted: false, dueAt: dueAt, lastModified: Fixtures.now)
        log.append("add:\(title)")
        return id
    }

    func reminder(_ id: String) -> ReminderSnapshot? {
        reminders[id]
    }

    func update(_ id: String, title: String?, due: TaskSyncUpdate.Due, completed: Bool?) throws {
        guard let old = reminders[id] else { return }
        var dueAt = old.dueAt
        if case let .set(date) = due { dueAt = date }
        reminders[id] = ReminderSnapshot(
            title: title ?? old.title, isCompleted: completed ?? old.isCompleted, dueAt: dueAt, lastModified: Fixtures.now
        )
        log.append("update:\(id)" + (title.map { " title=\($0)" } ?? "") + (completed.map { " done=\($0)" } ?? ""))
    }
}

@MainActor
struct RemindersSyncTests {
    private func linked(_ id: String, _ text: String, reminder: String, done: Bool = false, updated: TimeInterval = 0) -> ActionItem {
        ActionItem(
            id: id, description: text, isCompleted: done, dueAt: nil, conversationID: nil, owner: .user, workstreamID: nil,
            createdAt: Fixtures.now, exportPlatform: "apple_reminders", appleReminderID: reminder,
            updatedAt: Fixtures.now.addingTimeInterval(updated)
        )
    }

    @Test func enablingAsksForAccessAndConnectsReminders() async {
        let api = FakeAPIClient()
        let adapter = FakeReminders(hasAccess: false)
        let store = RemindersSyncStore(api: api, adapter: adapter)
        #expect(await store.setEnabled(true))
        #expect(adapter.log.first == "request")
        #expect(api.taskExtras.log.prefix(2) == ["connect:apple_reminders", "pending-sync:apple_reminders"])
        #expect(store.isEnabled)

        await store.refresh()
        #expect(store.isEnabled)
        await store.setEnabled(false)
        #expect(!store.isEnabled)
        await store.refresh()
        #expect(!store.isEnabled)
    }

    @Test func refusedAccessLeavesItOff() async {
        let api = FakeAPIClient()
        let adapter = FakeReminders(hasAccess: false)
        adapter.grantsAccess = false
        let store = RemindersSyncStore(api: api, adapter: adapter)
        #expect(!(await store.setEnabled(true)))
        #expect(store.accessDenied)
        #expect(!api.taskExtras.log.contains("connect:apple_reminders"))
    }

    @Test func addsRequestedTasksOnceAndLinksThem() async throws {
        let api = FakeAPIClient()
        let task = Fixtures.tasks[3]
        api.taskExtras.pendingExport = [task]
        let adapter = FakeReminders()
        let store = RemindersSyncStore(api: api, adapter: adapter, cooldown: 0)

        let stats = await store.sync(try api.pendingReminderSync())
        #expect(stats.added == 1)
        #expect(adapter.log == ["add:\(task.description)"])
        #expect(api.taskExtras.syncUpdates == [TaskSyncUpdate(id: task.id, exportPlatform: "apple_reminders", appleReminderID: "rem-1")])
        // Exported now: a second sync adds nothing.
        _ = await store.sync(try api.pendingReminderSync())
        #expect(adapter.log == ["add:\(task.description)"])
    }

    @Test func doneWinsOnBothSides() async throws {
        let api = FakeAPIClient(tasks: [
            linked("a", "Call mom", reminder: "r-a"),
            linked("b", "Pay rent", reminder: "r-b", done: true),
        ])
        let adapter = FakeReminders()
        adapter.reminders = [
            "r-a": ReminderSnapshot(title: "Call mom", isCompleted: true, dueAt: nil, lastModified: Fixtures.now),
            "r-b": ReminderSnapshot(title: "Pay rent", isCompleted: false, dueAt: nil, lastModified: Fixtures.now),
        ]
        let store = RemindersSyncStore(api: api, adapter: adapter)
        let stats = await store.sync(try api.pendingReminderSync())
        #expect(stats.completionsPulled == 1)
        #expect(stats.completionsPushed == 1)
        #expect(api.taskExtras.syncUpdates == [TaskSyncUpdate(id: "a", completed: true)])
        #expect(adapter.reminders["r-b"]?.isCompleted == true)
    }

    @Test func titleAndDueFollowTheLaterChange() async throws {
        let later = Fixtures.now.addingTimeInterval(600)
        let api = FakeAPIClient(tasks: [
            // Changed in Reminders after Omi: pull.
            linked("a", "Old title", reminder: "r-a", updated: -600),
            // Changed in Omi after Reminders: push.
            linked("b", "New in Omi", reminder: "r-b", updated: 1200),
        ])
        let adapter = FakeReminders()
        adapter.reminders = [
            "r-a": ReminderSnapshot(title: "New in Reminders", isCompleted: false, dueAt: later, lastModified: Fixtures.now),
            "r-b": ReminderSnapshot(title: "Old in Reminders", isCompleted: false, dueAt: nil, lastModified: Fixtures.now),
        ]
        let store = RemindersSyncStore(api: api, adapter: adapter)
        let stats = await store.sync(try api.pendingReminderSync())
        #expect(stats.pulled == 1)
        #expect(stats.pushed == 1)
        #expect(api.taskExtras.syncUpdates == [TaskSyncUpdate(id: "a", description: "New in Reminders", due: .set(later))])
        #expect(adapter.reminders["r-b"]?.title == "New in Omi")
    }

    @Test func aDeletedReminderDeletesItsTask() async throws {
        let api = FakeAPIClient(tasks: [linked("a", "Gone", reminder: "r-missing")])
        let store = RemindersSyncStore(api: api, adapter: FakeReminders())
        let stats = await store.sync(try api.pendingReminderSync())
        #expect(stats.unlinked == 1)
        #expect(api.editLog == ["delete-task:a"])
    }

    @Test func foregroundSyncWaitsOutTheCooldown() async {
        let api = FakeAPIClient()
        api.connectedIntegrations.insert("apple_reminders")
        var now = Fixtures.now
        let store = RemindersSyncStore(api: api, adapter: FakeReminders(), cooldown: 30, clock: { now })
        await store.refresh()
        await store.syncIfDue()
        await store.syncIfDue()
        #expect(api.taskExtras.log.filter { $0.hasPrefix("pending-sync") }.count == 1)
        now = now.addingTimeInterval(31)
        await store.syncIfDue()
        #expect(api.taskExtras.log.filter { $0.hasPrefix("pending-sync") }.count == 2)
    }
}
