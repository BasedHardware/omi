import Foundation
import OmiCore
import OmiNetwork
@testable import OmiService
import OmiTestSupport
import Testing

@MainActor
struct SearchFilterTests {
    func defaults() -> UserDefaults {
        UserDefaults(suiteName: "omi.test.\(UUID().uuidString)")!
    }

    func makeStore(_ api: FakeAPIClient, defaults: UserDefaults? = nil) -> (SearchStore, ConversationsStore) {
        let conversations = ConversationsStore(api: api)
        let store = SearchStore(
            api: api, conversations: conversations, tasks: TasksStore(api: api), memories: MemoriesStore(api: api),
            debounce: .milliseconds(20), defaults: defaults ?? self.defaults()
        )
        return (store, conversations)
    }

    @Test func recentSearchesKeepSixNewestFirstWithoutDuplicates() {
        let defaults = defaults()
        let (store, _) = makeStore(FakeAPIClient(), defaults: defaults)
        for query in ["one", "two", "three", "four", "five", "six", "seven", "TWO"] {
            store.update(query: query)
            store.remember()
        }
        #expect(store.recents == ["TWO", "seven", "six", "five", "four", "three"])
        let (reopened, _) = makeStore(FakeAPIClient(), defaults: defaults)
        #expect(reopened.recents == store.recents)
        reopened.removeRecent("six")
        #expect(reopened.recents.count == 5)
        reopened.clearRecents()
        #expect(reopened.recents.isEmpty)
    }

    @Test func aDateRangeGoesToTheBackendAndNarrowsLocalMatches() async {
        let api = FakeAPIClient()
        let (store, conversations) = makeStore(api)
        await conversations.load()
        store.update(query: "o")
        store.filter.start = Fixtures.now.addingTimeInterval(-6 * 3600)
        store.filter.end = Fixtures.now
        await store.pending?.value
        #expect(api.discover.searches.last?.filter.start != nil)
        #expect(store.conversations.map(\.id) == ["c1", "c2"])
        // A filter narrows to conversations.
        #expect(store.tasks.isEmpty && store.memories.isEmpty)
    }

    @Test func aPersonFilterBrowsesTheBackendWithoutAQuery() async {
        let api = FakeAPIClient()
        let (store, conversations) = makeStore(api)
        await conversations.load()
        store.filter.person = Person(id: "p-anna", name: "Anna", sampleCount: 0)
        #expect(store.isActive)
        await store.pending?.value
        #expect(api.discover.searches.map(\.query) == [""])
        #expect(api.discover.searches.first?.filter.speakerID == "p-anna")
        #expect(store.phase == .done)
    }

    @Test func starredAloneListsStarredConversations() async {
        var starred = Fixtures.conversations
        starred[2].isStarred = true
        let api = FakeAPIClient(conversations: starred)
        let (store, conversations) = makeStore(api)
        await conversations.load()
        store.filter.starred = true
        await store.pending?.value
        #expect(store.conversations.map(\.id) == ["c3"])
        #expect(api.discover.searches.isEmpty)
        store.filter = .init()
        #expect(store.phase == .idle)
    }

    @Test func recapsMatchTheQuery() async {
        let api = FakeAPIClient()
        api.discover.recaps = [DailySummary(
            id: "r1", date: "2026-10-05", headline: "Roadmap day", overview: "", emoji: nil,
            conversationCount: 2, highlights: [], decisions: []
        )]
        let (store, _) = makeStore(api)
        store.update(query: "roadmap")
        await store.pending?.value
        #expect(store.recaps.map(\.id) == ["r1"])
    }
}

@MainActor
struct AnnouncementsAndForYouTests {
    func defaults() -> UserDefaults {
        UserDefaults(suiteName: "omi.test.\(UUID().uuidString)")!
    }

    @Test func aFreshInstallShowsNothingAndRemembersTheVersion() async {
        let api = FakeAPIClient()
        let defaults = defaults()
        let store = AnnouncementsStore(api: api, defaults: defaults)
        await store.checkAfterLaunch(appVersion: "1.1.0+5")
        #expect(store.current == nil)
        #expect(api.discover.log.isEmpty)
        #expect(defaults.string(forKey: "flutter.lastKnownAppVersion") == "1.1.0+5")
    }

    @Test func anUpdateShowsTheChangesThenPendingItemsOneAtATime() async {
        let api = FakeAPIClient()
        api.discover.pending = [Announcement(id: "a1", title: "Meet Omi", kind: .message(
            body: "Hi", imageURL: nil, buttonTitle: "Open", buttonURL: URL(string: "omi://wrapped")
        ))]
        let defaults = defaults()
        defaults.set("1.0.0+1", forKey: "flutter.lastKnownAppVersion")
        let store = AnnouncementsStore(api: api, defaults: defaults)
        await store.checkAfterLaunch(appVersion: "1.1.0+5")
        #expect(store.current?.id == "cl-1")
        await store.dismiss()
        #expect(store.current?.id == "a1")
        await store.dismiss(buttonTapped: true)
        #expect(store.current == nil)
        #expect(api.discover.log == ["changelogs:1.0.0+1>1.1.0+5", "pending:version_upgrade", "dismiss:a1=true"])
        // Once per launch.
        await store.checkAfterLaunch(appVersion: "1.1.0+5")
        #expect(api.discover.log.count == 3)
    }

    @Test func notNowLeavesItPending() async {
        let api = FakeAPIClient()
        api.discover.pending = [Announcement(id: "a1", title: "Tour", kind: .feature(steps: []))]
        let defaults = defaults()
        defaults.set("1.1.0+5", forKey: "flutter.lastKnownAppVersion")
        let store = AnnouncementsStore(api: api, defaults: defaults)
        await store.checkAfterLaunch(appVersion: "1.1.0+5")
        #expect(store.current?.id == "a1")
        store.later()
        #expect(store.current == nil)
        #expect(!api.discover.log.contains { $0.hasPrefix("dismiss") })
    }

    @Test func whatsNewListsRecentVersions() async {
        let api = FakeAPIClient()
        let store = AnnouncementsStore(api: api, defaults: defaults())
        await store.loadRecent()
        #expect(store.recent.map(\.id) == ["cl-1"])
        api.discover.failing = ["changelogs"]
        await store.loadRecent()
        #expect(store.recentFailed)
    }

    @Test func forYouFeedbackThumbsDismissAndStopThese() async {
        let api = FakeAPIClient()
        let defaults = defaults()
        let store = ForYouStore(api: api, defaults: defaults)
        await store.load()
        #expect(store.items.map(\.id) == ["fy1", "fy2", "fy3"])

        await store.send(.helpful, for: store.items[0])
        #expect(store.items[0].feedback == "thumbs_up")
        await store.send(.helpful, for: store.items[0])
        await store.send(.dismissed, for: store.items[2])
        #expect(store.items.map(\.id) == ["fy1", "fy2"])
        await store.send(.stopThese, for: store.items[1])
        #expect(store.items.isEmpty)
        #expect(api.discover.log == ["feed", "feedback:fy1=thumbs_up", "feedback:fy3=dismissed", "feedback:fy2=producer_disabled"])

        // A stopped producer stays hidden on the next load.
        let next = ForYouStore(api: api, defaults: defaults)
        await next.load()
        #expect(next.items.map(\.id) == ["fy3"])
    }

    @Test func forYouThumbRollsBackAndAnOffFeedHidesTheSection() async {
        let api = FakeAPIClient()
        let store = ForYouStore(api: api, defaults: defaults())
        await store.load()
        api.discover.failing = ["feedback"]
        await store.send(.notHelpful, for: store.items[0])
        #expect(store.items[0].feedback == "none")
        api.discover.forYou = nil
        await store.load()
        #expect(store.items.isEmpty)
    }
}
