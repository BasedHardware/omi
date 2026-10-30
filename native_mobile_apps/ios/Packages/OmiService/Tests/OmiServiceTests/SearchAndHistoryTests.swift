import Foundation
import OmiCore
import OmiNetwork
@testable import OmiService
import OmiTestSupport
import Testing

@MainActor
struct SearchStoreTests {
    /// `local` feeds the loaded lists, `server` answers the backend search.
    func makeStore(
        local: FakeAPIClient = FakeAPIClient(),
        server: FakeAPIClient = FakeAPIClient()
    ) -> (SearchStore, ConversationsStore) {
        let conversations = ConversationsStore(api: local)
        let store = SearchStore(
            api: server, conversations: conversations,
            tasks: TasksStore(api: local), memories: MemoriesStore(api: local),
            debounce: .milliseconds(40)
        )
        return (store, conversations)
    }

    @Test func typingAsksTheBackendOnceItPauses() async {
        let server = FakeAPIClient()
        let (store, _) = makeStore(server: server)
        for prefix in ["r", "ro", "road", "roadmap"] {
            store.update(query: prefix)
        }
        #expect(store.phase == .searching)
        await store.pending?.value
        #expect(server.searchRequests == ["roadmap"])
        #expect(store.phase == .done)
        #expect(store.conversations.map(\.id) == ["c1"])
    }

    @Test func loadedMatchesShowFirstAndBackendHitsJoinWithoutDuplicates() async {
        let local = FakeAPIClient(conversations: Array(Fixtures.conversations.prefix(2)))
        let (store, conversations) = makeStore(local: local)
        await conversations.load()
        store.update(query: "overview")
        // Before the backend answers: what is loaded.
        #expect(store.conversations.map(\.id) == ["c1", "c2"])
        await store.pending?.value
        #expect(store.conversations.map(\.id) == ["c1", "c2", "c3", "c4"])
    }

    @Test func anAnswerForAnOlderQueryIsDropped() async throws {
        let server = FakeAPIClient()
        server.searchDelays["dinner"] = .milliseconds(150)
        let (store, _) = makeStore(server: server)
        store.update(query: "dinner")
        let stale = store.pending
        while server.searchRequests.isEmpty {
            try await Task.sleep(for: .milliseconds(5))
        }
        store.update(query: "roadmap")
        await store.pending?.value
        await stale?.value
        #expect(server.searchRequests == ["dinner", "roadmap"])
        #expect(store.conversations.map(\.id) == ["c1"])
        #expect(store.phase == .done)
    }

    @Test func tasksAndMemoriesMatchLocally() async {
        let (store, _) = makeStore()
        await store.loadSources()
        store.update(query: "ski")
        #expect(store.tasks.map(\.id) == ["t4"])
        #expect(store.memories.map(\.id) == ["m3"])
        store.update(query: "  ")
        #expect(store.phase == .idle)
        #expect(!store.hasResults)
        #expect(store.pending == nil)
    }

    @Test func aFailedBackendKeepsTheLoadedMatches() async {
        let server = FakeAPIClient(error: .transport("offline"))
        let (store, conversations) = makeStore(server: server)
        await conversations.load()
        store.update(query: "roadmap")
        await store.pending?.value
        #expect(store.phase == .failed)
        #expect(store.conversations.map(\.id) == ["c1"])
    }
}

@MainActor
struct ChatHistoryPagingTests {
    func message(_ index: Int) -> ChatMessage {
        ChatMessage(
            id: "m\(index)", text: "Message \(index)", sender: index.isMultiple(of: 2) ? .user : .omi,
            createdAt: Fixtures.now.addingTimeInterval(Double(index))
        )
    }

    @Test func olderPagesPrependInOrderWithoutDuplicates() async {
        let api = FakeAPIClient()
        api.chatArchive = (0 ..< 120).map(message)
        let chat = ChatStore(api: api, preferences: freshPreferences())
        await chat.loadHistory()
        #expect(chat.messages.map(\.id) == (70 ..< 120).map { "m\($0)" })
        #expect(chat.hasEarlier)

        // Two messages arrive elsewhere: the next page overlaps the loaded one by two.
        api.chatArchive?.append(contentsOf: [message(120), message(121)])
        await chat.loadEarlier()
        #expect(chat.messages.map(\.id) == (22 ..< 120).map { "m\($0)" })
        #expect(chat.hasEarlier)

        await chat.loadEarlier()
        #expect(chat.messages.map(\.id) == (0 ..< 120).map { "m\($0)" })
        #expect(!chat.hasEarlier)
        await chat.loadEarlier()
        #expect(api.chatOffsets == [0, 50, 100])
    }

    @Test func aShortHistoryHasNothingEarlier() async {
        let chat = ChatStore(api: FakeAPIClient(), preferences: freshPreferences())
        await chat.loadHistory()
        #expect(chat.messages.map(\.id) == ["h1"])
        #expect(!chat.hasEarlier)
    }
}

@MainActor
struct MemorySourceLookupTests {
    @Test func fetchesASourceThatIsNotLoaded() async {
        let store = ConversationsStore(api: FakeAPIClient())
        #expect(store.conversations.isEmpty)
        #expect(await store.conversation(id: "c3")?.title == "Dinner plans")
        #expect(await store.conversation(id: "gone") == nil)
    }

    @Test func usesTheLoadedCopyWithoutAskingTheBackend() async {
        let api = FakeAPIClient()
        let store = ConversationsStore(api: api)
        await store.load()
        await store.rename("c1", to: "Roadmap, renamed")
        api.fail(with: .transport("offline"))
        #expect(await store.conversation(id: "c1")?.title == "Roadmap, renamed")
    }
}
