import Foundation
import OmiCore
@testable import OmiService
import OmiTestSupport
import Testing

/// Star, folders, filters, delete with undo, merge and reprocess on the conversation list.
@MainActor
struct ConversationActionsTests {
    private func loaded(_ api: FakeAPIClient = FakeAPIClient(), undo: Duration = .seconds(60)) async -> ConversationsStore {
        let store = ConversationsStore(api: api, undoWindow: undo, mergeRefreshDelay: .seconds(60))
        await store.load()
        return store
    }

    @Test func starsAndRollsBack() async {
        let api = FakeAPIClient()
        let store = await loaded(api)
        await store.setStarred("c1", true)
        #expect(store.conversations.first { $0.id == "c1" }?.isStarred == true)
        #expect(api.conversationActions.log == ["star:c1=true"])

        api.conversationActions.failing = ["star"]
        await store.setStarred("c2", true)
        #expect(store.conversations.first { $0.id == "c2" }?.isStarred == false)
    }

    @Test func starredFilterComesFromTheBackendAndDropsUnstarred() async {
        let api = FakeAPIClient()
        let store = await loaded(api)
        await store.setStarred("c3", true)
        await store.setFilter(.starred)
        #expect(store.visible.map(\.id) == ["c3"])
        #expect(store.sections.flatMap(\.conversations).map(\.id) == ["c3"])
        await store.setStarred("c3", false)
        #expect(store.visible.isEmpty)
        // The full list keeps every conversation for title lookups.
        #expect(store.conversations.count == 4)
        await store.setFilter(.all)
        #expect(store.visible.count == 4)
    }

    @Test func movesToFoldersAndFiltersByFolder() async {
        let api = FakeAPIClient()
        let store = await loaded(api)
        await store.loadFolders()
        #expect(store.folders.map(\.name) == ["Work", "Trips"])
        await store.move(["c1", "c2"], to: "f-trips")
        await store.move(["c4"], to: "f-work")
        #expect(api.conversationActions.log.contains("bulk-move:c1+c2>f-trips"))
        #expect(api.conversationActions.log.contains("move:c4>f-work"))
        await store.setFilter(.folder("f-trips"))
        #expect(Set(store.visible.map(\.id)) == ["c1", "c2"])
        // Moving out of the shown folder takes it off the filtered list.
        await store.move(["c1"], to: nil)
        #expect(store.visible.map(\.id) == ["c2"])
        #expect(store.conversations.first { $0.id == "c1" }?.folderID == nil)
    }

    @Test func failedMoveRestoresTheFolder() async {
        let api = FakeAPIClient()
        let store = await loaded(api)
        await store.move(["c1"], to: "f-work")
        await store.setFilter(.folder("f-work"))
        api.conversationActions.failing = ["move"]
        await store.move(["c1"], to: "f-trips")
        #expect(store.visible.map(\.id) == ["c1"])
        #expect(store.conversations.first { $0.id == "c1" }?.folderID == "f-work")
    }

    @Test func createsRenamesAndDeletesFolders() async throws {
        let api = FakeAPIClient()
        let store = await loaded(api)
        await store.loadFolders()
        #expect(await store.createFolder(FolderDraft(name: "  ")) == nil)
        let folder = await store.createFolder(FolderDraft(name: " Family ", icon: "🏠", color: "#10B981"))
        #expect(folder?.name == "Family")
        let id = try #require(folder?.id)
        #expect(await store.updateFolder(id, to: FolderDraft(name: "Kids", icon: "🎮", color: "#8B5CF6", description: " Just us ")))
        #expect(store.folders.last?.name == "Kids")
        #expect(store.folders.last?.icon == "🎮")
        #expect(store.folders.last?.color == "#8B5CF6")
        #expect(store.folders.last?.description == "Just us")

        api.conversationActions.failing = ["update-folder"]
        #expect(await !(store.updateFolder(id, to: FolderDraft(name: "Nope"))))
        #expect(store.folders.last?.name == "Kids")
        #expect(store.folders.last?.icon == "🎮")

        await store.setFilter(.folder(id))
        await store.deleteFolder(id, moveTo: "f-trips")
        #expect(api.conversationActions.log.contains("delete-folder:\(id)>f-trips"))
        #expect(!store.folders.contains { $0.id == id })
        #expect(store.filter == .all)
        // System folders stay.
        await store.deleteFolder("f-work")
        #expect(store.folders.contains { $0.id == "f-work" })
    }

    @Test func deleteWaitsForTheUndoWindow() async {
        let api = FakeAPIClient()
        let store = await loaded(api)
        store.deleteWithUndo(["c1", "c2"])
        #expect(store.conversations.map(\.id) == ["c3", "c4"])
        #expect(store.pendingDeletion?.ids == ["c1", "c2"])
        #expect(api.editLog.isEmpty)
        store.undoDelete()
        #expect(store.conversations.map(\.id) == ["c1", "c2", "c3", "c4"])
        #expect(store.pendingDeletion == nil)

        store.deleteWithUndo(["c2"])
        await store.commitDeletion()
        #expect(api.editLog == ["delete-conversation:c2"])
        #expect(!store.conversations.contains { $0.id == "c2" })
    }

    @Test func deleteCommitsAfterTheWindowAndRestoresRefusals() async throws {
        let api = FakeAPIClient()
        let store = await loaded(api, undo: .milliseconds(20))
        store.deleteWithUndo(["c3"])
        try await Task.sleep(for: .milliseconds(200))
        #expect(api.editLog == ["delete-conversation:c3"])
        #expect(store.pendingDeletion == nil)

        api.fail(with: .transport("offline"))
        store.deleteWithUndo(["c4"])
        await store.commitDeletion()
        #expect(store.conversations.contains { $0.id == "c4" })
    }

    @Test func secondDeleteSendsTheFirst() async throws {
        let api = FakeAPIClient()
        let store = await loaded(api)
        store.deleteWithUndo(["c1"])
        store.deleteWithUndo(["c2"])
        try await Task.sleep(for: .milliseconds(50))
        #expect(api.editLog == ["delete-conversation:c1"])
        store.undoDelete()
        #expect(store.conversations.contains { $0.id == "c2" })
        #expect(!store.conversations.contains { $0.id == "c1" })
    }

    @Test func mergeChecksTheBackendRules() async {
        let api = FakeAPIClient()
        let store = await loaded(api)
        #expect(await store.merge(["c1"]) == .needsTwo)
        #expect(await store.merge(["c1", "c1"]) == .needsTwo)
        api.conversationActions.mergeWarning = "Large gap"
        #expect(await store.merge(["c1", "c2"]) == .started(warning: "Large gap"))
        #expect(api.conversationActions.log == ["merge:c1+c2"])
        #expect(store.conversations.prefix(2).allSatisfy { $0.status == .merging })
        // Already merging: not again.
        #expect(await store.merge(["c1", "c3"]) == .notReady)

        api.conversationActions.failing = ["merge"]
        #expect(await store.merge(["c3", "c4"]) == .failed)
        #expect(store.conversations.suffix(2).allSatisfy { $0.status == .completed })
    }

    @Test func reprocessShowsProcessingAndRollsBack() async {
        let api = FakeAPIClient()
        let store = await loaded(api)
        let detail = await store.reprocess("c1")
        #expect(detail?.summary == "Reprocessed overview.")
        #expect(store.conversations.first { $0.id == "c1" }?.status == .completed)

        api.conversationActions.failing = ["reprocess"]
        #expect(await store.reprocess("c2") == nil)
        #expect(store.conversations.first { $0.id == "c2" }?.status == .completed)
    }

    @Test func visibilityRollsBack() async {
        let api = FakeAPIClient()
        let store = await loaded(api)
        #expect(await store.setVisibility("c1", .shared))
        #expect(store.conversations[0].visibility == .shared)
        api.conversationActions.failing = ["visibility"]
        #expect(await !(store.setVisibility("c1", .private)))
        #expect(store.conversations[0].visibility == .shared)
    }

    @Test func remembersConversationsOutsideTheList() async {
        let api = FakeAPIClient()
        let store = ConversationsStore(api: api)
        let outside = Fixtures.conversation(id: "c1", title: "Old", minutesAgo: 9000)
        store.remember(outside)
        await store.setStarred("c1", true)
        await store.rename("c1", to: "Renamed")
        #expect(store.current(outside).isStarred)
        #expect(store.current(outside).title == "Renamed")
    }
}
