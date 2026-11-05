import Foundation
import OmiCore
import OmiNetwork
@testable import OmiService
import OmiTestSupport
import Testing

@MainActor
struct MemoryManagementTests {
    static let memories = [
        Memory(id: "a", content: "Lives in Berlin.", headline: nil, category: "system", createdAt: Fixtures.now, conversationID: "c1"),
        Memory(id: "b", content: "Anna leads the launch.", headline: nil, category: "interesting",
               createdAt: Fixtures.now.addingTimeInterval(-60), conversationID: nil, visibility: .public),
        Memory(id: "c", content: "Allergic to peanuts.", headline: nil, category: "manual",
               createdAt: Fixtures.now.addingTimeInterval(-120), conversationID: nil),
        Memory(id: "d", content: "Likes jazz.", headline: nil, category: "habits",
               createdAt: Fixtures.now.addingTimeInterval(-30 * 86400), conversationID: nil, reviewed: true, userReview: true),
    ]

    func makeStore(_ api: FakeAPIClient = FakeAPIClient(memories: memories)) async -> MemoriesStore {
        let store = MemoriesStore(api: api, undoWindow: .milliseconds(40))
        await store.load()
        return store
    }

    @Test func filterChipsOfferTheThreeKindsFirstThenOtherCategories() async {
        let store = await makeStore()
        #expect(store.filterChips().map(\.category) == ["system", "interesting", "manual", "habits"])
        #expect(store.filterChips(matching: "peanut").map(\.count) == [0, 0, 1])
        #expect(store.visible(category: "interesting").map(\.id) == ["b"])
        #expect(store.visible().map(\.id) == ["a", "b", "c", "d"])
    }

    @Test func deleteWaitsForUndoAndCanBeTakenBack() async throws {
        let api = FakeAPIClient(memories: Self.memories)
        let store = await makeStore(api)
        store.deleteWithUndo("b")
        #expect(store.pendingDeletion?.memory.id == "b")
        #expect(!store.memories.contains { $0.id == "b" })
        store.undoDelete()
        #expect(store.memories.map(\.id) == ["a", "b", "c", "d"])
        #expect(api.editLog.isEmpty)

        store.deleteWithUndo("c")
        let deadline = ContinuousClock.now + .seconds(3)
        while api.editLog.isEmpty, ContinuousClock.now < deadline {
            try await Task.sleep(for: .milliseconds(10))
        }
        #expect(api.editLog == ["delete-memory:c"])
        #expect(store.pendingDeletion == nil)
    }

    @Test func aSecondDeleteCommitsTheFirst() async throws {
        let api = FakeAPIClient(memories: Self.memories)
        let store = await makeStore(api)
        store.deleteWithUndo("a")
        store.deleteWithUndo("b")
        try await Task.sleep(for: .milliseconds(10))
        #expect(api.editLog == ["delete-memory:a"])
        await store.commitPendingDeletion()
        #expect(api.editLog == ["delete-memory:a", "delete-memory:b"])
        #expect(store.memories.map(\.id) == ["c", "d"])
    }

    @Test func visibilityPerMemoryAndForAll() async {
        let api = FakeAPIClient(memories: Self.memories)
        let store = await makeStore(api)
        #expect((store.publicCount, store.privateCount) == (1, 3))
        await store.setVisibility("a", .public)
        #expect(store.memories.first { $0.id == "a" }?.visibility == .public)

        #expect(await store.setAllVisibility(.private))
        #expect(store.publicCount == 0)
        // Only the ones that differed were sent.
        #expect(api.memoryExtras.log == ["visibility:a=public", "visibility:a=private", "visibility:b=private"])
    }

    @Test func visibilityRollsBackWhenRefused() async {
        let api = FakeAPIClient(memories: Self.memories)
        api.memoryExtras.failing = ["visibility"]
        let store = await makeStore(api)
        await store.setVisibility("c", .public)
        #expect(store.memories.first { $0.id == "c" }?.visibility == .private)
        #expect(store.lastError != nil)
        #expect(!(await store.setAllVisibility(.public)))
    }

    @Test func pinsAsBaseline() async {
        let api = FakeAPIClient(memories: Self.memories)
        let store = await makeStore(api)
        await store.setBaseline("a", pinned: true)
        #expect(store.memories.first { $0.id == "a" }?.isBaseline == true)
        api.memoryExtras.failing = ["baseline"]
        await store.setBaseline("a", pinned: false)
        #expect(store.memories.first { $0.id == "a" }?.isBaseline == true)
    }

    @Test func reviewKeepsRightAndDiscardsWrong() async {
        let api = FakeAPIClient(memories: Self.memories)
        let store = await makeStore(api)
        let now = Fixtures.now
        // New memories without a backend doubt are not questions (MemoryReviewTests has the rule).
        #expect(store.memories.allSatisfy { !store.needsReview($0, now: now) })
        await store.review("a", isRight: true)
        #expect(store.memories.first { $0.id == "a" }?.userReview == true)
        #expect(!store.needsReview(store.memories[0], now: now))
        await store.review("b", isRight: false)
        #expect(!store.memories.contains { $0.id == "b" })
        #expect(api.memoryExtras.log == ["review:a=true", "review:b=false"])

        api.memoryExtras.failing = ["review"]
        await store.review("c", isRight: false)
        #expect(store.memories.contains { $0.id == "c" })
    }

    /// The chat's review card holds an id from the message, which may not be on the loaded list.
    @Test func reviewOfAnUnloadedMemoryStillVotes() async {
        let api = FakeAPIClient(memories: Self.memories)
        let store = await makeStore(api)
        await store.review("nowhere", isRight: false)
        #expect(api.memoryExtras.log == ["review:nowhere=false"])
        #expect(store.memories.map(\.id) == ["a", "b", "c", "d"])
        #expect(store.lastError == nil)

        // A failed vote leaves the list exactly as it was, with no row to put back.
        api.memoryExtras.failing = ["review"]
        await store.review("nowhere", isRight: true)
        #expect(store.memories.map(\.id) == ["a", "b", "c", "d"])
        #expect(store.lastError != nil)
    }

    @Test func deleteAllEmptiesTheListOnlyWhenTheBackendTookIt() async {
        let api = FakeAPIClient(memories: Self.memories)
        let store = await makeStore(api)
        api.memoryExtras.failing = ["delete-all"]
        #expect(!(await store.deleteAll()))
        #expect(store.memories.count == 4)
        api.memoryExtras.failing = []
        #expect(await store.deleteAll())
        #expect(store.memories.isEmpty)
        #expect(api.memoryExtras.log == ["delete-all", "delete-all"])
    }

    @Test func graphCentersOnTheUserAndLaysOutEveryNode() async {
        let api = FakeAPIClient()
        let graph = KnowledgeGraphStore(api: api, userName: "Alex")
        await graph.load()
        #expect(graph.phase == .loaded)
        #expect(graph.nodes.first?.isUser == true)
        #expect(graph.nodes.first.map { ($0.x, $0.y) } ?? (1, 1) == (0, 0))
        #expect(graph.nodes.allSatisfy { abs($0.x) <= 1 && abs($0.y) <= 1 })
        #expect(graph.neighbors(of: GraphLayout.userID) == ["kg-anna", "kg-berlin"])
        #expect(!graph.isEmpty)
    }

    @Test func graphMergesUserDuplicatesAndDropsSelfLoops() {
        let raw = KnowledgeGraph(
            nodes: [.init(id: "u1", label: "Alex", kind: "person"), .init(id: "u2", label: "me", kind: "concept"),
                    .init(id: "x", label: "Chess", kind: "thing")],
            edges: [.init(source: "u1", target: "u2", label: "is"), .init(source: "u1", target: "x", label: "plays"),
                    .init(source: "u2", target: "x", label: "likes")]
        )
        let centered = GraphLayout.centered(on: "Alex", raw)
        #expect(centered.nodes.map(\.id) == [GraphLayout.userID, "x"])
        #expect(centered.nodes.first?.label == "Alex")
        #expect(centered.edges == [.init(source: GraphLayout.userID, target: "x", label: "plays")])
    }
}
