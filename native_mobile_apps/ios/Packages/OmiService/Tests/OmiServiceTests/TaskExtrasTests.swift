import Foundation
import OmiCore
@testable import OmiService
import OmiTestSupport
import Testing

@MainActor
struct TaskUndoAndBulkTests {
    @Test func deleteWaitsForTheUndoWindowAndUndoBringsTheTaskBack() async throws {
        let api = FakeAPIClient()
        let store = TasksStore(api: api, undoWindow: .seconds(60))
        await store.load()
        let order = store.tasks.map(\.id)

        store.deleteWithUndo(["t3"])
        #expect(!store.tasks.contains { $0.id == "t3" })
        #expect(store.pendingDeletion?.ids == ["t3"])
        #expect(api.editLog.isEmpty)

        store.undoDelete()
        #expect(store.tasks.map(\.id) == order)
        #expect(store.pendingDeletion == nil)
        #expect(api.editLog.isEmpty)
    }

    @Test func committedDeleteReachesTheBackend() async {
        let api = FakeAPIClient()
        let store = TasksStore(api: api, undoWindow: .milliseconds(20))
        await store.load()
        store.deleteWithUndo(["t3"])
        try? await Task.sleep(for: .milliseconds(200))
        #expect(api.editLog == ["delete-task:t3"])
        #expect(store.pendingDeletion == nil)
        // A reload does not bring it back.
        await store.load()
        #expect(!store.tasks.contains { $0.id == "t3" })
    }

    @Test func bulkDeleteUsesOneBatchAndRestoresWhatFailed() async {
        let api = FakeAPIClient()
        let store = TasksStore(api: api, undoWindow: .seconds(60))
        await store.load()
        store.deleteWithUndo(["t1", "t2"])
        await store.commitDeletion()
        #expect(api.taskExtras.log == ["batch-delete:t1+t2"])
        #expect(!store.tasks.contains { ["t1", "t2"].contains($0.id) })

        api.taskExtras.failing = ["batch-delete"]
        let order = store.tasks.map(\.id)
        store.deleteWithUndo(["t3", "t4"])
        await store.commitDeletion()
        #expect(store.tasks.map(\.id) == order)
        #expect(store.lastError != nil)
    }

    @Test func aSecondDeleteSendsTheFirst() async {
        let api = FakeAPIClient()
        let store = TasksStore(api: api, undoWindow: .seconds(60))
        await store.load()
        store.deleteWithUndo(["t1"])
        store.deleteWithUndo(["t2"])
        try? await Task.sleep(for: .milliseconds(50))
        #expect(api.editLog == ["delete-task:t1"])
        #expect(store.pendingDeletion?.ids == ["t2"])
    }

    @Test func clearCompletedDeletesOnlyFinishedTasks() async {
        let api = FakeAPIClient()
        let store = TasksStore(api: api, undoWindow: .seconds(60))
        await store.load()
        store.clearCompleted()
        #expect(store.pendingDeletion?.ids == ["t6"])
        #expect(store.tasks.allSatisfy { !$0.isCompleted })
    }

    @Test func bulkCompleteSkipsTasksAlreadyDone() async {
        let api = FakeAPIClient()
        let store = TasksStore(api: api)
        await store.load()
        await store.setCompleted(["t1", "t2", "t6"], true)
        #expect(api.taskUpdates.map(\.id) == ["t1", "t2"])
        #expect(store.tasks.filter { ["t1", "t2", "t6"].contains($0.id) }.allSatisfy { $0.isCompleted })
    }
}

@MainActor
struct SubtaskTests {
    /// Three open tasks without due dates land in one section ("Someday").
    private func store() async -> (FakeAPIClient, TasksStore) {
        let tasks = ["a", "b", "c"].enumerated().map { offset, id in
            ActionItem(
                id: id, description: id, isCompleted: false, dueAt: nil, conversationID: nil, owner: .user, workstreamID: nil,
                createdAt: Fixtures.now.addingTimeInterval(Double(offset))
            )
        }
        let api = FakeAPIClient(tasks: tasks)
        let store = TasksStore(api: api)
        await store.load()
        return (api, store)
    }

    @Test func indentFollowsFlutterRules() async {
        let (api, store) = await store()
        // The first row has no parent above it.
        #expect(!store.canIndent("a"))
        #expect(store.canIndent("b"))

        await store.indent("b")
        #expect(store.tasks.first { $0.id == "b" }?.indentLevel == 1)
        // Order is pinned so the parent stays above: a=1000, b=2000 (level 1), c=3000.
        #expect(api.taskExtras.log == ["layout:a#1000,b@1#2000,c#3000"])
        // Never deeper than one below the row above.
        #expect(!store.canIndent("b"))
        #expect(store.canIndent("c"))
        await store.indent("c")
        await store.indent("c")
        #expect(store.tasks.first { $0.id == "c" }?.indentLevel == 2)
        #expect(!store.canIndent("c"))
        #expect(store.descendants(of: "a") == ["b", "c"])
        #expect(store.descendants(of: "b") == ["c"])

        await store.outdent("c")
        #expect(store.tasks.first { $0.id == "c" }?.indentLevel == 1)
        #expect(!store.canOutdent("a"))
        #expect(api.taskExtras.log.last == "layout:c@1")
    }

    @Test func indentRollsBackWhenTheBackendRefuses() async {
        let (api, store) = await store()
        api.taskExtras.failing = ["layout"]
        await store.indent("b")
        #expect(store.tasks.allSatisfy { $0.indentLevel == 0 && $0.sortOrder == 0 })
        #expect(store.lastError != nil)
    }

    @Test func displayIndentNeverSkipsALevel() async {
        let (_, store) = await store()
        var rows = store.tasks.sorted(by: TasksStore.displayOrder)
        rows[0].indentLevel = 2
        rows[2].indentLevel = 3
        let levels = store.displayIndents(rows)
        #expect(levels["a"] == 0)
        #expect(levels["b"] == 0)
        #expect(levels["c"] == 1)
    }

    @Test func dayShowsDueAndAddedTasks() async {
        let api = FakeAPIClient()
        let store = TasksStore(api: api)
        await store.load()
        let today = store.tasks.first { $0.id == "t2" }!.dueAt!
        let day = store.day(today)
        #expect(day.due.map(\.id).contains("t2"))
        #expect(!day.added.contains { $0.id == "t2" })
    }
}

@MainActor
struct TaskExportAndShareTests {
    @Test func exportsToTheConnectedAppAndSkipsExportedTasks() async {
        let api = FakeAPIClient()
        let store = TasksStore(api: api)
        await store.load()

        #expect(await store.export(["t1", "t2"], to: "todoist") == .exported(app: "todoist", count: 2, failed: 0))
        #expect(api.taskExtras.log == [
            "export:todoist=Send proof of income", "mark-exported:t1>todoist",
            "export:todoist=Send roadmap deck", "mark-exported:t2>todoist",
        ])
        #expect(store.tasks.first { $0.id == "t1" }?.exportPlatform == "todoist")
        #expect(await store.export(["t1"], to: "todoist") == .alreadyExported)
    }

    @Test func exportAllOpenSendsOnlyMyOpenTasks() async {
        let api = FakeAPIClient()
        let store = TasksStore(api: api)
        await store.load()
        api.taskExtras.failing = ["export"]
        #expect(await store.exportAllOpen(to: "asana") == .exportFailed(app: "asana"))
        // t5 is someone else's, t6 is done.
        #expect(api.taskExtras.log.map { $0.split(separator: "=")[0] } == Array(repeating: "export:asana", count: 4))
        #expect(store.tasks.allSatisfy { !$0.isExported })
    }

    @Test func exportsToRemindersThroughTheExporter() async {
        let api = FakeAPIClient()
        let store = TasksStore(api: api)
        await store.load()
        store.reminderExporter = { task in "rem-\(task.id)" }
        #expect(await store.export(["t4"], to: TasksStore.appleReminders) == .exported(app: "apple_reminders", count: 1, failed: 0))
        #expect(api.taskExtras.log == ["mark-exported:t4>apple_reminders"])
        #expect(store.tasks.first { $0.id == "t4" }?.appleReminderID == "rem-t4")
    }

    @Test func sharesAndAcceptsTasks() async {
        let sender = FakeAPIClient()
        let senderStore = TasksStore(api: sender)
        await senderStore.load()
        let url = await senderStore.shareLink(for: ["t3"])
        #expect(url?.absoluteString == "https://h.omi.me/tasks/tok-t3")
        #expect(DeepLink(url: url!) == .sharedTasks(token: "tok-t3"))

        let recipient = FakeAPIClient(tasks: [])
        recipient.taskExtras.shares = sender.taskExtras.shares
        let store = TasksStore(api: recipient)
        await store.openShare(token: "tok-t3")
        #expect(store.incomingShare?.tasks.map(\.description) == ["Research competitor pricing"])
        #expect(await store.acceptShare())
        #expect(store.tasks.map(\.description) == ["Research competitor pricing"])
        #expect(store.notice?.kind == .sharedAdded(1))
        #expect(store.incomingShare == nil)

        // The same link twice: the backend says it was accepted already.
        await store.openShare(token: "tok-t3")
        #expect(!(await store.acceptShare()))
        #expect(store.notice?.kind == .shareFailed)
    }

    @Test func anExpiredLinkSaysSo() async {
        let store = TasksStore(api: FakeAPIClient())
        await store.openShare(token: "gone")
        #expect(store.incomingShare == nil)
        #expect(store.notice?.kind == .shareExpired)
    }
}
