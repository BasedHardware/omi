import Foundation
import OmiCore
@testable import OmiService
import OmiTestSupport
import Testing

@MainActor
struct EditingTests {
    @Test func addsAndSearchesTasks() async {
        let api = FakeAPIClient()
        let store = TasksStore(api: api)
        await store.load()
        #expect(await store.add("  Call the plumber ", dueAt: nil))
        #expect(store.tasks.first?.description == "Call the plumber")
        #expect(!(await store.add("   ", dueAt: nil)))
        #expect(store.matching("plumb").map(\.description) == ["Call the plumber"])
        #expect(api.editLog == ["task:Call the plumber"])
    }

    @Test func editsAndDeletesMemoriesWithRollback() async {
        let api = FakeAPIClient()
        let store = MemoriesStore(api: api)
        await store.load()
        await store.edit("m1", content: "Prefers afternoon meetings.")
        #expect(store.memories.first { $0.id == "m1" }?.content == "Prefers afternoon meetings.")
        await store.delete("m2")
        #expect(!store.memories.contains { $0.id == "m2" })

        let failing = MemoriesStore(api: FakeAPIClient(error: .transport("offline")))
        await failing.load()
        #expect(failing.memories.isEmpty)
    }

    @Test func renamesAndDeletesConversations() async {
        let api = FakeAPIClient()
        let store = ConversationsStore(api: api)
        await store.load()
        let id = store.conversations[0].id
        await store.rename(id, to: "Launch plan")
        #expect(store.conversations[0].title == "Launch plan")
        await store.delete(id)
        #expect(!store.conversations.contains { $0.id == id })
        #expect(api.editLog == ["rename:\(id)=Launch plan", "delete-conversation:\(id)"])
    }
}
