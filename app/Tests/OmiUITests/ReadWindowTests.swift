import OmiKit
import XCTest

@testable import OmiUI

@MainActor
final class ReadWindowTests: XCTestCase {
    private func extendedStore(
        lastCursor: String? = nil
    ) async -> (AppStore, ScriptedWindowReads) {
        let reads = ScriptedWindowReads()
        let store = AppStore(services: AppServices(reads: reads))
        store.onboardingRequired = false
        await store.refreshReads()
        await reads.setPages([windowTasks(1, count: 1, cursor: lastCursor)])
        await store.loadOlderTasks()
        XCTAssertEqual(store.tasksRead?.items.map { $0.id }, ["task-0", "task-1"])
        return (store, reads)
    }

    func testTaskRefreshRejectsMixedEpochs() async {
        let (store, reads) = await extendedStore()
        let first = windowTasks(100, count: 1, epoch: 8)
        await reads.setPages([first, first, windowTasks(101, count: 1, epoch: 9, cursor: nil)])
        let result = await store.refreshTasks()
        XCTAssertNil(result)
        XCTAssertEqual(store.tasksRead?.accountEpoch, 7)
        XCTAssertEqual(store.tasksRead?.items.map { $0.id }, ["task-0", "task-1"])
    }

    func testFullRefreshRejectsMixedEpochs() async {
        let (store, reads) = await extendedStore()
        await reads.setPages([
            windowTasks(100, count: 1, epoch: 8),
            windowTasks(101, count: 1, epoch: 9, cursor: nil),
        ])
        await store.refreshReads()
        XCTAssertEqual(store.readsPhase, .savedButRefreshFailed)
        XCTAssertEqual(store.tasksRead?.accountEpoch, 7)
        XCTAssertEqual(store.tasksRead?.items.map { $0.id }, ["task-0", "task-1"])
    }

    func testTaskRefreshRejectsChangedAPIContract() async {
        let (store, reads) = await extendedStore()
        let first = windowTasks(100, count: 1)
        var second = windowTasks(101, count: 1, cursor: nil)
        second.apiContract = .omi
        await reads.setPages([first, first, second])
        let result = await store.refreshTasks()
        XCTAssertNil(result)
        XCTAssertEqual(store.tasksRead?.items.map { $0.id }, ["task-0", "task-1"])
    }

    func testConsistentNewEpochReplacesWholeWindow() async {
        let (store, reads) = await extendedStore()
        let first = windowTasks(100, count: 1, epoch: 8)
        await reads.setPages([first, first, windowTasks(101, count: 1, epoch: 8, cursor: nil)])
        let result = await store.refreshTasks()
        XCTAssertEqual(result?.accountEpoch, 8)
        XCTAssertEqual(result?.items.map { $0.id }, ["task-100", "task-101"])
        XCTAssertEqual(store.tasksRead, result)
    }

    func testEmptyCursorCycleStopsWithoutPublishing() async {
        let (store, reads) = await extendedStore()
        let empty = windowTasks(100, count: 0)
        await reads.setPages([empty, empty, windowTasks(101, count: 0, cursor: "other"), empty])
        let result = await store.refreshTasks()
        let calls = await reads.requestedCursors()
        XCTAssertNil(result)
        XCTAssertEqual(calls.count, 4)
        XCTAssertEqual(store.tasksRead?.items.map { $0.id }, ["task-0", "task-1"])
    }

    func testMissingCursorStopsWithoutPublishing() async {
        let (store, reads) = await extendedStore()
        var malformed = windowTasks(100, count: 0)
        malformed.page.nextCursor = nil
        await reads.setPages([malformed, malformed])
        let result = await store.refreshTasks()
        XCTAssertNil(result)
        XCTAssertEqual(store.tasksRead?.items.map { $0.id }, ["task-0", "task-1"])
    }

    func testTaskPaginationRejectsDuplicateIDsAndKeepsSavedRows() async {
        let (store, reads) = await extendedStore(lastCursor: "more")
        // task-0 is already in the loaded window; a later page cannot repeat it.
        await reads.setPages([windowTasks(0, count: 1, cursor: nil)])

        await store.loadOlderTasks()

        XCTAssertEqual(store.tasksRead?.items.map { $0.id }, ["task-0", "task-1"])
        XCTAssertEqual(store.taskNotice, "More tasks could not be loaded. Try again.")
    }

    func testOversizedWindowStopsWithoutPublishing() async {
        let (store, reads) = await extendedStore()
        let oversized = windowTasks(100, count: 10_001)
        await reads.setPages([oversized, oversized])
        let result = await store.refreshTasks()
        XCTAssertNil(result)
        XCTAssertEqual(store.tasksRead?.items.map { $0.id }, ["task-0", "task-1"])
    }

    func testUniqueEmptyTaskCursorsStopAtPageLimit() async {
        let (store, reads) = await extendedStore()
        // One page feeds refreshTasks' fresh result; 200 more feed the
        // full-window replay through its final guarded iteration.
        let pages = (0..<201).map { index in
            windowTasks(100, count: 0, cursor: "empty-\(index)")
        }
        await reads.setPages(pages)

        let result = await store.refreshTasks()
        let calls = await reads.requestedCursors()

        XCTAssertNil(result)
        // refreshTasks performs one fresh read before replaying the 200-page
        // loaded window; the replay itself stops at the configured ceiling.
        XCTAssertEqual(calls.count, 201)
        XCTAssertEqual(store.tasksRead?.items.map { $0.id }, ["task-0", "task-1"])
    }

    func testUniqueEmptyConversationCursorsStopAtPageLimit() async {
        let reads = ScriptedWindowReads()
        let store = AppStore(services: AppServices(reads: reads))
        store.onboardingRequired = false
        await store.refreshReads()
        await reads.setConversationPages([conversationRead("conversation-1", page: .complete)])
        await store.loadOlderConversations()
        XCTAssertEqual(conversationItems(store), ["conversation-0", "conversation-1"])

        let pages = (0..<200).map { index in
            conversationRead(nil, page: .more("empty-\(index)"))
        }
        await reads.setConversationPages(pages)
        await store.refreshReads()

        let calls = await reads.requestedConversationCursors()
        XCTAssertEqual(calls.count, 200)
        XCTAssertEqual(store.readsPhase, .savedButRefreshFailed)
        XCTAssertEqual(conversationItems(store), ["conversation-0", "conversation-1"])
    }

    private func conversationItems(_ store: AppStore) -> [String]? {
        guard let outcome = store.outcomes?.conversations,
            case .success(let value) = outcome
        else { return nil }
        return value.items.map(\.id)
    }
}

private func windowTasks(
    _ start: Int, count: Int, epoch: Int64 = 7, cursor: String? = "next"
) -> TaskRead {
    TaskRead(
        apiContract: .canonical,
        items: (start..<(start + count)).map { index in
            TaskProjection(
                id: "task-\(index)", title: "Task \(index)", summary: "Pending",
                searchableText: "", completed: false, source: "assistant",
                provenance: [], sortOrder: index, indentLevel: 0, revision: "revision")
        },
        page: ReadPageState(
            windowStatus: cursor == nil ? .complete : .more, complete: cursor == nil,
            hasMore: cursor != nil, nextCursor: cursor,
            completenessStatus: .complete, reasons: []),
        accountEpoch: epoch)
}

private actor ScriptedWindowReads: ReadsServicing {
    private var pages: [TaskRead] = []
    private var cursors: [String?] = []
    private var conversationPages: [DomainRead<ConversationProjection>] = []
    private var conversationCursors: [String?] = []

    func setPages(_ pages: [TaskRead]) {
        self.pages = pages
        cursors = []
    }

    func requestedCursors() -> [String?] { cursors }

    func setConversationPages(_ pages: [DomainRead<ConversationProjection>]) {
        conversationPages = pages
        conversationCursors = []
    }

    func requestedConversationCursors() -> [String?] { conversationCursors }

    func loadTasks(cursor: String?) async throws -> TaskRead {
        cursors.append(cursor)
        guard !pages.isEmpty else { throw ReadCopyError("Fixture exhausted") }
        return pages.removeFirst()
    }

    func loadConversations(cursor: String?) async throws -> DomainRead<ConversationProjection> {
        conversationCursors.append(cursor)
        guard !conversationPages.isEmpty else { throw ReadCopyError("Fixture exhausted") }
        return conversationPages.removeFirst()
    }

    func loadMemories(cursor: String?) async throws -> DomainRead<MemoryProjection> {
        DomainRead(items: [], page: windowTasks(0, count: 0, cursor: nil).page)
    }

    func loadDesktopReads() async -> DesktopReadOutcomes {
        DesktopReadOutcomes(
            conversations: .success(homeConversationRead()),
            memories: .success(try! await loadMemories(cursor: nil)),
            tasks: .success(windowTasks(0, count: 1)))
    }
}

private func conversationRead(
    _ id: String?, page: ConversationPage
) -> DomainRead<ConversationProjection> {
    DomainRead(
        items: id.map { [conversationProjection($0)] } ?? [],
        page: page.readPage)
}

private func homeConversationRead() -> DomainRead<ConversationProjection> {
    conversationRead("conversation-0", page: .more("more-conversations"))
}

private func conversationProjection(_ id: String) -> ConversationProjection {
    ConversationProjection(
        id: id, title: id, summary: id, searchableText: id,
        createdAt: "2026-09-01T10:00:00.000Z", starred: false,
        status: "completed", source: "desktop", visibility: .priv)
}

private enum ConversationPage {
    case complete
    case more(String)

    var readPage: ReadPageState {
        switch self {
        case .complete:
            ReadPageState(
                windowStatus: .complete, complete: true, hasMore: false,
                nextCursor: nil, completenessStatus: .complete, reasons: [])
        case .more(let cursor):
            ReadPageState(
                windowStatus: .more, complete: false, hasMore: true,
                nextCursor: cursor, completenessStatus: .complete, reasons: [])
        }
    }
}
