import Foundation
import OmiCore
import OmiNetwork
import OmiPersistence
@testable import OmiService
import OmiTestSupport
import Testing

@MainActor
final class FakeAuth: AuthServicing {
    var currentUserID: String?
    var failSignIn = false

    init(currentUserID: String? = nil) {
        self.currentUserID = currentUserID
    }

    func signIn(customToken: String) async throws -> AuthenticatedUser {
        if failSignIn { throw APIError.transport("down") }
        currentUserID = "uid-from-\(customToken)"
        return AuthenticatedUser(uid: currentUserID!, email: "\(customToken)@local.test", displayName: "Ada Lovelace")
    }

    func signIn(with _: ProviderCredential) async throws -> AuthenticatedUser {
        currentUserID = "apple-user"
        return AuthenticatedUser(uid: "apple-user", email: nil, displayName: nil)
    }

    func updateDisplayName(_: String) async throws {}

    func signOut() throws {
        currentUserID = nil
    }
}

func freshPreferences(onboarded: Bool = true) -> Preferences {
    let name = "omi.tests.\(UUID().uuidString)"
    let defaults = UserDefaults(suiteName: name)!
    let prefs = Preferences(defaults: defaults)
    if onboarded {
        defaults.set(true, forKey: "flutter.onboardingCompleted")
        defaults.set(true, forKey: "flutter.aiConsentGiven")
    }
    return prefs
}

@MainActor
struct SessionStoreTests {
    let localDev = AppConfiguration(
        profile: .localDev, apiBaseURL: URL(string: "http://127.0.0.1:8000/")!,
        authEmulator: ("127.0.0.1", 9099), appVersion: "2.0.0", appBuild: "1"
    )

    @Test func restoresPersistedSession() {
        let store = SessionStore(
            auth: FakeAuth(currentUserID: "u1"),
            api: FakeAPIClient(),
            configuration: localDev,
            preferences: freshPreferences()
        )
        store.restore()
        #expect(store.phase == .ready(userID: "u1"))
    }

    @Test func localDevSignInFlow() async {
        let api = FakeAPIClient()
        let store = SessionStore(auth: FakeAuth(), api: api, configuration: localDev, preferences: freshPreferences())
        store.restore()
        #expect(store.phase == .signedOut)
        await store.signInLocalDev(uid: "alice")
        // A different user than the one on disk starts fresh: consent first.
        #expect(store.phase == .consent(userID: "uid-from-token-for-alice"))
        #expect(api.customTokenRequests == ["alice"])
        store.signOut()
        #expect(store.phase == .signedOut)
    }

    @Test func missingHarnessExplainsItself() async {
        let store = SessionStore(
            auth: FakeAuth(),
            api: FakeAPIClient(error: .http(status: 404, body: "")),
            configuration: localDev,
            preferences: freshPreferences()
        )
        store.restore()
        await store.signInLocalDev()
        #expect(store.phase == .signedOut)
        #expect(store.errorMessage?.contains("make dev-up") == true)
    }

    @Test func flutterUserMidOnboardingResumesOnboarding() {
        let prefs = freshPreferences(onboarded: false)
        prefs.set(true, for: .aiConsentGiven) // agreed in the Flutter build
        let store = SessionStore(auth: FakeAuth(currentUserID: "u1"), api: FakeAPIClient(), configuration: localDev, preferences: prefs)
        store.restore()
        #expect(store.phase == .onboarding(userID: "u1"))
        store.completeOnboarding()
        #expect(store.phase == .ready(userID: "u1"))
        #expect(prefs.bool(.onboardingCompleted))
    }

    @Test func signInAsDifferentUserDropsPreviousUserData() async {
        let prefs = freshPreferences()
        prefs.set("old-user", for: .uid)
        prefs.set("Old Name", for: .givenName)
        let store = SessionStore(auth: FakeAuth(), api: FakeAPIClient(), configuration: localDev, preferences: prefs)
        await store.signInLocalDev(uid: "alice")
        #expect(prefs.string(.givenName) == "Ada")
        #expect(prefs.string(.uid) == "uid-from-token-for-alice")
        #expect(store.phase == .consent(userID: "uid-from-token-for-alice"))
    }

    @Test func returningUserOnFreshInstallSkipsOnboardingAfterConsent() async {
        let api = FakeAPIClient()
        api.serverOnboarding = OnboardingState(completed: true, acquisitionSource: "Reddit")
        api.serverLanguage = "de"
        let prefs = freshPreferences(onboarded: false)
        let store = SessionStore(auth: FakeAuth(), api: api, configuration: localDev, preferences: prefs)
        await store.signInLocalDev(uid: "alice")
        #expect(store.phase == .consent(userID: "uid-from-token-for-alice"))
        #expect(prefs.string(.userPrimaryLanguage) == "de")
        store.giveConsent()
        #expect(store.phase == .ready(userID: "uid-from-token-for-alice"))
        #expect(api.accountLog == ["timezone"])
    }

    @Test func appleSignInKeepsFirstTimeName() async {
        let prefs = freshPreferences(onboarded: false)
        let store = SessionStore(auth: FakeAuth(), api: FakeAPIClient(), configuration: localDev, preferences: prefs)
        await store.signIn(with: .apple(idToken: "t", rawNonce: "n", givenName: "Grace", familyName: "Hopper"))
        #expect(prefs.string(.givenName) == "Grace")
        #expect(prefs.string(.familyName) == "Hopper")
        #expect(store.phase == .consent(userID: "apple-user"))
    }

    @Test func productionNeverOffersLocalSignIn() async {
        let prod = AppConfiguration.fromInfoDictionary([:])
        let api = FakeAPIClient()
        let store = SessionStore(auth: FakeAuth(), api: api, configuration: prod, preferences: freshPreferences())
        await store.signInLocalDev()
        #expect(api.customTokenRequests.isEmpty)
    }
}

@MainActor
struct ConversationsStoreTests {
    @Test func groupsByDayNewestFirst() async throws {
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = try #require(TimeZone(identifier: "UTC"))
        let store = ConversationsStore(api: FakeAPIClient(), calendar: calendar)
        await store.load()
        #expect(store.phase == .loaded)
        #expect(store.sections.map { $0.conversations.map(\.id) } == [["c1", "c2"], ["c3"], ["c4"]])
        #expect(store.today(now: Fixtures.now).map(\.id) == ["c1", "c2"])
    }

    @Test func pagesUntilExhausted() async {
        let many = (0 ..< 120).map { Fixtures.conversation(id: "p\($0)", title: "C\($0)", minutesAgo: Double($0) * 10) }
        let store = ConversationsStore(api: FakeAPIClient(conversations: many))
        await store.load()
        #expect(store.conversations.count == 50)
        await store.loadMore()
        await store.loadMore()
        #expect(store.conversations.count == 120)
        #expect(!store.hasMore)
    }

    @Test func failureKeepsExistingItems() async {
        let api = FakeAPIClient()
        let store = ConversationsStore(api: api)
        await store.load()
        api.fail(with: .transport("offline"))
        await store.load()
        #expect(store.conversations.count == 4)
        #expect(store.phase != .loaded)
    }
}

@MainActor
struct TasksStoreTests {
    func store(_ api: FakeAPIClient = FakeAPIClient()) -> TasksStore {
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = TimeZone(identifier: "UTC")!
        return TasksStore(api: api, calendar: calendar)
    }

    @Test func bucketsByDueDateAndOwner() async {
        let tasks = store()
        await tasks.load()
        let sections = tasks.sections(now: Fixtures.now)
        #expect(sections.map(\.bucket) == [.overdue, .today, .upcoming, .someday, .waitingOnOthers, .completed])
        #expect(sections.first { $0.bucket == .waitingOnOthers }?.tasks.map(\.id) == ["t5"])
        #expect(tasks.focus(now: Fixtures.now).map(\.id) == ["t1", "t2"])
    }

    @Test func completionIsOptimisticAndPersisted() async {
        let api = FakeAPIClient()
        let tasks = store(api)
        await tasks.load()
        await tasks.setCompleted("t3", true)
        #expect(tasks.tasks.first { $0.id == "t3" }?.isCompleted == true)
        #expect(api.taskUpdates.map(\.id) == ["t3"])
    }

    @Test func failedCompletionRollsBack() async {
        let api = FakeAPIClient()
        let tasks = store(api)
        await tasks.load()
        api.fail(with: .http(status: 500, body: ""))
        await tasks.setCompleted("t3", true)
        #expect(tasks.tasks.first { $0.id == "t3" }?.isCompleted == false)
        #expect(tasks.lastError != nil)
    }

    @Test func nextStepsExcludeOthersCommitments() async {
        let tasks = store()
        await tasks.load()
        #expect(tasks.tasks(forConversation: "c2").isEmpty)
        #expect(tasks.tasks(forConversation: "c1").count == 4)
    }
}

@MainActor
struct MemoriesStoreTests {
    @Test func groupsAndFilters() async {
        let memories = MemoriesStore(api: FakeAPIClient())
        await memories.load()
        #expect(memories.grouped().count == 3)
        #expect(memories.grouped(matching: "ski").map(\.category) == ["interests"])
    }
}

@MainActor
struct AgentStoreTests {
    @Test func takeOverRunsTheFullWorkstreamLifecycle() async {
        let api = FakeAPIClient()
        let agent = AgentStore(api: api, preferences: freshPreferences())
        await agent.takeOver(Fixtures.tasks[2], conversationTitle: "Q4 roadmap")
        let run = agent.runs["t3"]
        #expect(run?.state == .done(result: api.chatReply))
        #expect(run?.workstreamID == "ws-t3")
        #expect(run?.steps == api.chatSteps)
        #expect(api.workstreamLog == [
            "intent:t3",
            "event:Omi started working on this task.",
            // Think steps reach the workstream throttled: the second follows too soon.
            "event:Searching your conversations",
            "event:Done: \(api.chatReply)",
            "artifact:reply-1",
            "status:completed",
        ])
    }

    @Test func runsInItsOwnChatSession() async throws {
        let api = FakeAPIClient()
        await AgentStore(api: api, preferences: freshPreferences()).takeOver(Fixtures.tasks[2], conversationTitle: nil)
        #expect(try await api.chatSessions(appID: AgentStore.runSessionAppID).map(\.title) == ["✦ Research competitor pricing"])
    }

    @Test func cannedBackendFailureIsNotAResult() async {
        let api = FakeAPIClient()
        api.chatReply = "Sorry, I encountered an error. Please try again."
        let agent = AgentStore(api: api, preferences: freshPreferences())
        await agent.takeOver(Fixtures.tasks[2], conversationTitle: nil)
        if case .failed = agent.runs["t3"]?.state {} else { Issue.record("expected failed run") }
        #expect(!api.workstreamLog.contains("status:completed"))
    }

    @Test func promptKeepsOutgoingActionsAsDrafts() {
        let prompt = AgentStore.prompt(for: Fixtures.tasks[2], conversationTitle: "Q4 roadmap")
        #expect(prompt.contains("Research competitor pricing"))
        #expect(prompt.contains("Q4 roadmap"))
        #expect(prompt.contains("prepare those as drafts"))
    }

    @Test func homeShowsRecentRunsAndCannedAnswersAsFailures() async {
        let api = FakeAPIClient()
        let event = { (days: Double) in
            [Workstream.Event(id: "e", kind: "note", summary: "x", createdAt: Fixtures.now.addingTimeInterval(-days * 86400))]
        }
        api.workstreamsByID = [
            "w1": Workstream(id: "w1", title: "a", status: .completed, summary: "Drafted the email.", events: event(0.5)),
            "w2": Workstream(id: "w2", title: "b", status: .completed, summary: "Drafted it.", events: event(3)),
            "w3": Workstream(
                id: "w3", title: "c", status: .completed,
                summary: ChatStreamEvent.serviceFailureTexts[3], events: event(3)
            ),
        ]
        let tasks = [
            Fixtures.task("t1", "Recent", workstream: "w1"),
            Fixtures.task("t2", "Old", workstream: "w2"),
            Fixtures.task("t3", "Stuck", workstream: "w3"),
        ]
        let agent = AgentStore(api: api, preferences: freshPreferences(), now: { Fixtures.now })
        await agent.loadWorkstreams(for: tasks)
        let items = agent.workItems(tasks: tasks)
        #expect(items.map(\.id) == ["t1", "t3"])
        #expect(items.first?.state == .done(result: "Drafted the email."))
        if case .failed = items.last?.state {} else { Issue.record("a canned guard answer is a failure") }
    }

    @Test func recommendationsSkipTasksOmiAlreadyHas() async {
        let api = FakeAPIClient()
        api.recommendations = [
            Recommendation(id: "r1", headline: "Proof", whyNow: "Overdue", action: "Send", taskID: "t1"),
            Recommendation(id: "r2", headline: "Deck", whyNow: "Today", action: "Send", taskID: "t2"),
            Recommendation(id: "r3", headline: "Sleep", whyNow: "Late", action: "Rest", taskID: nil),
        ]
        let agent = AgentStore(api: api, preferences: freshPreferences())
        await agent.loadRecommendations()
        let tasks = [Fixtures.task("t1", "Proof"), Fixtures.task("t2", "Deck", workstream: "w2")]
        #expect(agent.openRecommendations(tasks: tasks).map(\.id) == ["r1", "r3"])
    }

    @Test func failureIsReported() async {
        let api = FakeAPIClient(error: .transport("offline"))
        let agent = AgentStore(api: api, preferences: freshPreferences())
        await agent.takeOver(Fixtures.tasks[0], conversationTitle: nil)
        if case .failed = agent.runs["t1"]?.state {} else { Issue.record("expected failed run") }
    }
}

@MainActor
struct ChatStoreTests {
    @Test func streamsIntoOnePlaceholder() async throws {
        let chat = ChatStore(api: FakeAPIClient(), preferences: freshPreferences())
        chat.send("Schedule the follow-up")
        for _ in 0 ..< 50 where chat.isStreaming {
            try await Task.sleep(for: .milliseconds(10))
        }
        // history greeting + user message + streamed reply
        #expect(chat.messages.count == 3)
        #expect(chat.messages[1].sender == .user)
        // The bubble keeps its local id when the final message arrives (no rebuild as it ends).
        #expect(chat.messages[2].id.hasPrefix("pending-"))
        #expect(chat.messages[2].failure == nil)
        #expect(chat.messages[2].steps.count == 2)
    }

    @Test func stoppingIsNotAnError() async throws {
        let api = FakeAPIClient()
        let chat = ChatStore(api: api, preferences: freshPreferences())
        await chat.loadHistory()
        chat.send("Long question")
        chat.cancel()
        for _ in 0 ..< 50 where chat.isStreaming {
            try await Task.sleep(for: .milliseconds(10))
        }
        #expect(chat.messages.last?.failure == .stopped)
    }

    @Test func historyLoadsOnceEvenWhenAskedTwice() async {
        let chat = ChatStore(api: FakeAPIClient(), preferences: freshPreferences())
        async let first: Void = chat.loadHistory()
        async let second: Void = chat.loadHistory()
        _ = await (first, second)
        #expect(Set(chat.messages.map(\.id)).count == chat.messages.count)
        #expect(chat.hasLoaded)
    }
}

@MainActor
struct AgentWorkItemsTests {
    @Test func recoversEarlierRunsFromTaskWorkstreams() async {
        var task = Fixtures.task("t9", "Book the venue")
        task = ActionItem(
            id: task.id, description: task.description, isCompleted: false, dueAt: nil, conversationID: nil,
            owner: .user, workstreamID: "ws-9", createdAt: nil
        )
        let agent = AgentStore(api: FakeAPIClient(), preferences: freshPreferences())
        #expect(agent.workItems(tasks: [task]).isEmpty)
        await agent.loadWorkstreams(for: [task])
        #expect(agent.workItems(tasks: [task]).map(\.id) == ["t9"])
    }
}

@MainActor
struct ChatSessionPinningTests {
    @Test func mainChatSkipsAgentSessions() async {
        let api = FakeAPIClient()
        let prefs = freshPreferences()
        let agent = AgentStore(api: api, preferences: prefs)
        await agent.takeOver(Fixtures.tasks[2], conversationTitle: nil) // "app-session-omi-agent-run-1"
        api.existingSessions = [("app-session-omi-agent-run-1", "Research competitor pricing"), ("main", "Chat")]
        let chat = ChatStore(api: api, preferences: prefs)
        #expect(await chat.resolveMainSession() == "main")
        #expect(prefs.string(.mainChatSessionID) == "main")
    }

    @Test func mainChatSkipsAgentSessionsFromOtherDevices() async {
        let api = FakeAPIClient()
        let prefs = freshPreferences()
        // Signed in fresh: no local list of run sessions, and a pin that points at a run.
        prefs.set("run-elsewhere", for: .mainChatSessionID)
        prefs.append("run-elsewhere", to: .agentChatSessionIDs)
        api.existingSessions = [("run-new", "✦ Book the venue"), ("run-elsewhere", "✦ Deck"), ("main", "Chat")]
        let chat = ChatStore(api: api, preferences: prefs)
        #expect(await chat.resolveMainSession() == "main")
    }
}
