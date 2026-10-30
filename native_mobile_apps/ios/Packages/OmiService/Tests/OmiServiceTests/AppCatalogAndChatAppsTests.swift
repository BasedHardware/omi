import Foundation
import OmiCore
import OmiNetwork
@testable import OmiService
import OmiTestSupport
import Testing

private func app(_ id: String, _ capabilities: Set<String> = [], enabled: Bool = true, paid: Bool = false) -> OmiApp {
    OmiApp(
        id: id, name: "App \(id)", description: "", author: nil, imageURL: nil, category: nil, rating: nil, installs: 0,
        isEnabled: enabled, capabilities: capabilities, isPaid: paid
    )
}

@MainActor
struct AppCatalogStoreTests {
    let api = FakeAPIClient()

    func make() -> AppCatalogStore {
        AppCatalogStore(api: api, capabilities: CapabilitiesStore(api: api), userID: { "alice" }, purchasePoll: .milliseconds(5))
    }

    @Test func searchSendsTheFiltersAndPagesOn() async {
        api.devApps.browsePages = [[app("1"), app("2")], [app("3")]]
        let store = make()
        store.query = AppQuery(text: "coach", category: "other", capability: "chat", sort: .rating)
        await store.search()
        #expect(store.results.map(\.id) == ["1", "2"])
        #expect(store.hasMore)
        #expect(api.devApps.browseQueries.last == AppQuery(text: "coach", category: "other", capability: "chat", sort: .rating))
        await store.loadMore()
        #expect(store.results.map(\.id) == ["1", "2", "3"])
        #expect(!store.hasMore)
    }

    @Test func aFirstReviewIsCreatedAndASecondOneUpdates() async {
        let store = make()
        api.devApps.details["a1"] = AppDetail(app: api.apps[0])
        await store.loadDetail("a1")
        #expect(await store.review("a1", score: 9, text: " Great "))
        #expect(api.devApps.log == ["review:a1:5:Great"])
        let mine = AppReview(uid: "alice", score: 5, text: "Great", username: nil, ratedAt: nil, response: nil)
        api.devApps.details["a1"] = AppDetail(app: api.apps[0], userReview: mine)
        await store.loadDetail("a1")
        #expect(await store.review("a1", score: 3, text: "Okay"))
        #expect(api.devApps.log.last == "update:a1:3:Okay")
    }

    @Test func enablingReportsTheBackendsReason() async {
        let store = make()
        api.fail(with: .http(status: 400, body: #"{"detail":"Finish the app's setup first"}"#))
        #expect(await store.setEnabled(api.apps[1], true) == "Finish the app's setup first")
        api.fail(with: nil)
        #expect(await store.setEnabled(api.apps[1], true) == nil)
        #expect(api.apps[1].isEnabled)
    }

    @Test func aPurchaseTurnsTheAppOnOncePaid() async {
        let store = make()
        let paid = app("a2", enabled: false, paid: true)
        api.devApps.details["a2"] = AppDetail(app: paid, isUserPaid: false)
        let waiting = Task { await store.awaitPurchase("a2", attempts: 50) }
        try? await Task.sleep(for: .milliseconds(20))
        #expect(store.awaitingPurchase.contains("a2"))
        api.devApps.details["a2"] = AppDetail(app: paid, isUserPaid: true)
        await waiting.value
        #expect(api.apps[1].isEnabled)
        #expect(store.awaitingPurchase.isEmpty)
    }

    @Test func cancellingASubscriptionKeepsItUntilThePeriodEnds() async {
        let store = make()
        api.devApps.subscriptions["a1"] = AppSubscription(status: "active", cancelAtPeriodEnd: false, periodEnd: nil)
        #expect(await store.cancelSubscription("a1"))
        #expect(store.subscriptions["a1"]?.cancelAtPeriodEnd == true)
        #expect(store.subscriptions["a1"]?.isActive == false)
    }
}

@MainActor
struct ChatAppsTests {
    let api = FakeAPIClient()

    init() {
        api.apps = [app("coach", ["chat"]), app("sync", ["memories"]), app("twin", ["persona"]), app("off", ["chat"], enabled: false)]
        api.existingSessions = [("main", "Chat")]
    }

    @Test func listsOnlyEnabledAppsThatChat() async {
        let chat = ChatStore(api: api, preferences: freshPreferences())
        await chat.loadChatApps()
        #expect(chat.chatApps.map(\.id) == ["coach", "twin"])
    }

    @Test func eachAppHasItsOwnSessionAndOmiStaysOnMain() async throws {
        let prefs = freshPreferences()
        let chat = ChatStore(api: api, preferences: prefs)
        await chat.loadHistory()
        await chat.loadChatApps()
        await chat.talk(to: chat.chatApps[0])
        #expect(chat.chatApp?.id == "coach")
        #expect(api.devApps.log == ["session:coach"])
        #expect(api.devApps.historySessions == ["main", "app-session-coach-1"])
        chat.send("Give me a tip")
        try await waitUntil { !chat.isStreaming }
        #expect(api.devApps.sentSessions == ["app-session-coach-1"])
        // Back to Omi: the main session; agent sessions and the main pin are untouched.
        await chat.talk(to: nil)
        #expect(api.devApps.historySessions.last == "main")
        #expect(prefs.string(.mainChatSessionID) == "main")
        // The app's thread is reused, not opened again.
        await chat.talk(to: chat.chatApps[0])
        #expect(api.devApps.log == ["session:coach"])
    }

    @Test func theChosenAppIsRestoredAfterARelaunch() async {
        let prefs = freshPreferences()
        api.devApps.appSessions["twin"] = [("twin-thread", "Twin")]
        let first = ChatStore(api: api, preferences: prefs)
        await first.loadChatApps()
        await first.talk(to: first.chatApps[1])
        let relaunched = ChatStore(api: api, preferences: prefs)
        await relaunched.loadHistory()
        #expect(relaunched.chatApp?.id == "twin")
        #expect(api.devApps.historySessions.last == "twin-thread")
    }

    @Test func aDisabledAppFallsBackToOmi() async {
        let prefs = freshPreferences()
        let chat = ChatStore(api: api, preferences: prefs)
        await chat.loadChatApps()
        await chat.talk(to: chat.chatApps[0])
        api.apps[0].isEnabled = false
        await chat.loadChatApps()
        #expect(chat.chatApp == nil)
        #expect(prefs.string(.selectedChatAppID) == nil)
    }
}

@MainActor
struct TaskAppSettingsTests {
    let api = FakeAPIClient()

    @Test func choosingAParentClearsTheLevelsBelowAndIsRemembered() async {
        let prefs = freshPreferences()
        api.devApps.options = [
            .clickupTeam: ["": [TaskAppOption(id: "t1", name: "Team")]],
            .clickupSpace: ["t1": [TaskAppOption(id: "s1", name: "Space")]],
            .clickupList: ["s1": [TaskAppOption(id: "l1", name: "Inbox")]],
        ]
        let store = TaskAppSettingsStore(api: api, preferences: prefs)
        await store.load("clickup")
        #expect(store.options[.clickupTeam]?.map(\.id) == ["t1"])
        await store.select("clickup", level: .clickupTeam, option: TaskAppOption(id: "t1", name: "Team"))
        #expect(store.options[.clickupSpace]?.map(\.id) == ["s1"])
        #expect(api.devApps.log.last == "select:clickup:clickupList=nil,clickupSpace=nil,clickupTeam=t1")
        await store.select("clickup", level: .clickupSpace, option: TaskAppOption(id: "s1", name: "Space"))
        await store.select("clickup", level: .clickupList, option: TaskAppOption(id: "l1", name: "Inbox"))
        let again = TaskAppSettingsStore(api: api, preferences: prefs)
        #expect(again.selection["clickup"]?[.clickupList]?.name == "Inbox")
        await again.load("clickup")
        #expect(again.options[.clickupList]?.map(\.id) == ["l1"])
    }

    @Test func aRefusedChoiceGoesBack() async {
        let store = TaskAppSettingsStore(api: api, preferences: freshPreferences())
        api.devApps.nextWriteError = .http(status: 500, body: "")
        await store.select("asana", level: .asanaWorkspace, option: TaskAppOption(id: "w", name: "Work"))
        #expect(store.selection["asana"]?[.asanaWorkspace] == nil)
        #expect(store.failed)
        await store.makeDefault("asana")
        #expect(store.defaultApp == "asana")
    }
}
