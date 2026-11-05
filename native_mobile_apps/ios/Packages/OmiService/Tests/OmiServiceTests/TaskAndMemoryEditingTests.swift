import Foundation
import OmiCore
@testable import OmiService
import OmiTestSupport
import Testing

@MainActor
struct TaskAndMemoryEditingTests {
    @Test func editsTaskTextAndDueDate() async {
        let api = FakeAPIClient()
        let store = TasksStore(api: api)
        await store.load()
        let due = Fixtures.now.addingTimeInterval(3 * 86400)

        #expect(await store.update("t4", description: "  Book the ski chalet ", dueAt: due))
        let edited = store.tasks.first { $0.id == "t4" }
        #expect(edited?.description == "Book the ski chalet")
        #expect(edited?.dueAt == due)

        #expect(await store.update("t1", description: "Send proof of income", dueAt: nil))
        #expect(store.tasks.first { $0.id == "t1" }?.dueAt == nil)
        #expect(!(await store.update("t1", description: "   ", dueAt: nil)))
        #expect(api.editLog == ["update-task:t4=Book the ski chalet", "update-task:t1=Send proof of income"])
    }

    @Test func rollsBackTaskEditWhenBackendRefuses() async {
        let api = FakeAPIClient()
        let store = TasksStore(api: api)
        await store.load()
        let before = store.tasks.first { $0.id == "t2" }
        api.fail(with: .http(status: 500, body: ""))

        #expect(!(await store.update("t2", description: "Send the final deck", dueAt: nil)))
        #expect(store.tasks.first { $0.id == "t2" } == before)
        #expect(store.lastError != nil)
    }

    @Test func deletesTaskAndRestoresItOnFailure() async {
        let api = FakeAPIClient()
        let store = TasksStore(api: api)
        await store.load()
        await store.delete("t3")
        #expect(!store.tasks.contains { $0.id == "t3" })
        #expect(api.editLog == ["delete-task:t3"])

        let order = store.tasks.map(\.id)
        api.fail(with: .transport("offline"))
        await store.delete("t2")
        #expect(store.tasks.map(\.id) == order)
        #expect(store.lastError != nil)
    }

    @Test func addsMemoryByHand() async {
        let api = FakeAPIClient()
        let store = MemoriesStore(api: api)
        await store.load()
        #expect(await store.add("  Allergic to peanuts. "))
        #expect(store.memories.first?.content == "Allergic to peanuts.")
        #expect(store.memories.first?.category == "manual")
        #expect(!(await store.add("  ")))
        #expect(api.createdMemories == ["Allergic to peanuts."])

        api.fail(with: .http(status: 503, body: ""))
        #expect(!(await store.add("Lives in Berlin.")))
        #expect(store.memories.count == Fixtures.memories.count + 1)
        #expect(store.lastError != nil)
    }

    @Test func rollsBackMemoryEditAndDelete() async {
        let api = FakeAPIClient()
        let store = MemoriesStore(api: api)
        await store.load()
        api.fail(with: .transport("offline"))
        await store.edit("m1", content: "Prefers afternoon meetings.")
        #expect(store.memories.first { $0.id == "m1" }?.content == "Prefers morning meetings.")
        await store.delete("m2")
        #expect(store.memories.map(\.id) == Fixtures.memories.map(\.id))
    }

    @Test func loadsEveryPageOfTasksAndMemories() async {
        let tasks = (1 ... 7).map { Fixtures.task("p\($0)", "Task \($0)") }
        let memories = (1 ... 6).map {
            Memory(id: "pm\($0)", content: "Fact \($0)", headline: nil, category: "other", createdAt: Fixtures.now, conversationID: nil)
        }
        let api = FakeAPIClient(tasks: tasks, memories: memories)

        let taskStore = TasksStore(api: api, pageSize: 3)
        await taskStore.load()
        #expect(taskStore.tasks.map(\.id) == tasks.map(\.id))

        let memoryStore = MemoriesStore(api: api, pageSize: 3)
        await memoryStore.load()
        #expect(memoryStore.memories.map(\.id) == memories.map(\.id))

        // 7 tasks: 3 + 3 + 1 (short, stop). 6 memories: 3 + 3 + 0 (short, stop).
        #expect(api.pageRequests == ["tasks:0", "tasks:3", "tasks:6", "memories:0", "memories:3", "memories:6"])
    }
}
