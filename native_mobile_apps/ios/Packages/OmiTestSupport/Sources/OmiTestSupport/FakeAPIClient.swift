import Foundation
import OmiCore
import OmiNetwork

/// In-memory backend for store tests and SwiftUI previews.
public final class FakeAPIClient: APIClientProtocol, @unchecked Sendable {
    let lock = NSLock()
    var _conversations: [Conversation]
    var _error: APIError?
    var _tasks: [ActionItem]
    var _memories: [Memory]
    public private(set) var customTokenRequests: [String] = []
    public private(set) var taskUpdates: [(id: String, completed: Bool)] = []
    /// `tasks:<offset>` / `memories:<offset>`, one per page fetched.
    public internal(set) var pageRequests: [String] = []
    /// Search and chat paging (`FakeAPIClient+Search.swift`).
    public internal(set) var searchRequests: [String] = []
    public nonisolated(unsafe) var searchDelays: [String: Duration] = [:]
    /// The whole chat, oldest first; `nil` answers every page with one greeting.
    public nonisolated(unsafe) var chatArchive: [ChatMessage]?
    public internal(set) var chatOffsets: [Int] = []
    /// Ratings, clear chat, uploads, speech (`FakeAPIClient+ChatExtras.swift`).
    public let chatExtras = FakeChatExtras()
    /// Star, folders, merge, reprocess, edits, audio (`FakeAPIClient+ConversationActions.swift`).
    public let conversationActions = FakeConversationActions()
    /// Summary templates, calendar, feedback, recordings, day queries (`FakeAPIClient+ConversationExtras.swift`).
    public let conversationExtras = FakeConversationExtras()
    /// Task extras and goals (`FakeAPIClient+TaskExtras.swift`, `+Goals.swift`).
    public let taskExtras = FakeTaskExtras(), goalsBackend = FakeGoals()
    /// Memory management, account data, what's new / For you (`FakeAPIClient+MemoryExtras/Profile/Discover.swift`).
    public let memoryExtras = FakeMemoryExtras(), accountData = FakeAccountData(), discover = FakeDiscover()

    public init(
        conversations: [Conversation] = Fixtures.conversations,
        tasks: [ActionItem] = Fixtures.tasks,
        memories: [Memory] = Fixtures.memories,
        error: APIError? = nil
    ) {
        _conversations = conversations
        _tasks = tasks
        _memories = memories
        _error = error
    }

    public func conversationDetail(id: String) async throws -> ConversationDetail {
        try lock.withLock {
            if let _error { throw _error }
            if let detail = conversationExtras.details[id] { return detail }
            guard let conversation = _conversations.first(where: { $0.id == id }) else {
                throw APIError.http(status: 404, body: "")
            }
            return ConversationDetail(
                conversation: conversation,
                summaryActionItems: [],
                transcript: [.init(id: 0, speaker: "You", isUser: true, text: conversation.overview, start: 0, segmentID: "seg-0")],
                hasAudio: conversationActions.audio != [.unavailable]
            )
        }
    }

    public func actionItems(limit: Int, offset: Int) async throws -> [ActionItem] {
        try lock.withLock {
            if let _error { throw _error }
            pageRequests.append("tasks:\(offset)")
            return Array(_tasks.dropFirst(offset).prefix(limit))
        }
    }

    public func setActionItem(id: String, completed: Bool) async throws {
        try lock.withLock {
            if let _error { throw _error }
            taskUpdates.append((id, completed))
            if let index = _tasks.firstIndex(where: { $0.id == id }) { _tasks[index].isCompleted = completed }
        }
    }

    public func memories(limit: Int, offset: Int) async throws -> [Memory] {
        try lock.withLock {
            if let _error { throw _error }
            pageRequests.append("memories:\(offset)")
            return Array(_memories.dropFirst(offset).prefix(limit))
        }
    }

    public func fail(with error: APIError?) {
        lock.withLock { _error = error }
    }

    public func conversations(limit: Int, offset: Int) async throws -> [Conversation] {
        try lock.withLock {
            if let _error { throw _error }
            return Array(_conversations.dropFirst(offset).prefix(limit))
        }
    }

    public func localDevCustomToken(uid: String) async throws -> String {
        try lock.withLock {
            if let _error { throw _error }
            customTokenRequests.append(uid)
            return "token-for-\(uid)"
        }
    }

    // MARK: Agent

    public private(set) var workstreamLog: [String] = []
    /// Agent-run extras: feedback, streams with device tools, event logs (`FakeAPIClient+AgentRuns.swift`).
    public let agentRuns = FakeAgentRuns()
    public nonisolated(unsafe) var chatReply = "Done. I drafted the follow-up and put it on your calendar."
    public var chatSteps = ["Searching your conversations", "Creating event..."]

    public private(set) var chatSessions: [String] = []

    public func createChatSession(title: String) async throws -> String {
        lock.withLock { chatSessions.append(title) }
        return "session-\(chatSessions.count)"
    }

    public func sendMessage(_: String, context _: ChatContext?, sessionID _: String?) -> AsyncThrowingStream<ChatStreamEvent, any Error> {
        let steps = chatSteps
        let reply = chatReply
        let failure = lock.withLock { _error }
        return AsyncThrowingStream { continuation in
            if let failure {
                continuation.finish(throwing: failure)
                return
            }
            for step in steps {
                continuation.yield(.step(step))
            }
            for word in reply.split(separator: " ") {
                continuation.yield(.delta(word + " "))
            }
            continuation.yield(.done(ChatMessage(id: "reply-1", text: reply, sender: .omi, createdAt: Fixtures.now)))
            continuation.finish()
        }
    }

    public nonisolated(unsafe) var existingSessions: [(id: String, title: String)] = []

    public func chatSessions() async throws -> [(id: String, title: String)] {
        existingSessions
    }

    public func chatHistory(limit _: Int, sessionID: String?) async throws -> [ChatMessage] {
        if let sessionID, let history = agentRuns.sessionHistories[sessionID] { return history }
        return [ChatMessage(id: "h1", text: "Hi! How can I help?", sender: .omi, createdAt: Fixtures.now)]
    }

    public func accountGeneration() async throws -> Int {
        0
    }

    public func startWork(onTask taskID: String, title _: String, generation _: Int) async throws -> String {
        lock.withLock { workstreamLog.append("intent:\(taskID)") }
        return "ws-\(taskID)"
    }

    public func recordWorkstreamEvent(
        _: WorkstreamRef,
        kind _: String,
        summary: String,
        evidence: [[String: String]],
        idempotencyKey: String
    ) async throws -> String {
        lock.withLock {
            workstreamLog.append("event:\(summary)")
            agentRuns.eventEvidence.append(evidence)
            agentRuns.eventKeys.append(idempotencyKey)
        }
        return "ev-\(workstreamLog.count)"
    }

    public func recordResultArtifact(
        _: WorkstreamRef,
        messageID: String,
        resultText _: String,
        evidenceEventID _: String,
        runID _: String
    ) async throws {
        lock.withLock { workstreamLog.append("artifact:\(messageID)") }
    }

    public func updateWorkstream(_: WorkstreamRef, status: Workstream.Status?, summary _: String?) async throws {
        lock.withLock { workstreamLog.append("status:\(status?.rawValue ?? "-")") }
    }

    public nonisolated(unsafe) var workstreamsByID: [String: Workstream] = [:]
    public nonisolated(unsafe) var recommendations: [Recommendation] = []

    // MARK: Edits (methods in FakeAPIClient+Edits.swift)

    public internal(set) var editLog: [String] = []
    public nonisolated(unsafe) var summaries: [DailySummary] = []
    public internal(set) var uploadedVoice: Data?
    public internal(set) var createdMemories: [String] = []

    // MARK: Firmware (methods in FakeAPIClient+Firmware.swift)

    public nonisolated(unsafe) var latestFirmwareRelease: FirmwareRelease?
    public internal(set) var firmwareChecks: [String] = []

    public func workstream(_ workstreamID: String) async throws -> Workstream {
        workstreamsByID[workstreamID] ?? Workstream(id: workstreamID, title: "Task", status: .open, summary: nil, events: [])
    }

    public func whatMattersNow() async throws -> [Recommendation] {
        let decided = lock.withLock { Set(agentRuns.recommendationFeedback.compactMap { $0.split(separator: "=").first.map(String.init) }) }
        return recommendations.filter { !decided.contains($0.id) }
    }

    // MARK: Account

    public nonisolated(unsafe) var serverOnboarding = OnboardingState(completed: false, acquisitionSource: nil)
    public nonisolated(unsafe) var serverLanguage: String?
    public private(set) var accountLog: [String] = []

    public func onboardingState() async throws -> OnboardingState {
        serverOnboarding
    }

    public func updateOnboarding(completed: Bool?, acquisitionSource: String?) async throws {
        lock.withLock { accountLog.append("onboarding:\(completed.map(String.init) ?? "-"):\(acquisitionSource ?? "-")") }
    }

    public func primaryLanguage() async throws -> String? {
        serverLanguage
    }

    public func setPrimaryLanguage(_ code: String) async throws {
        lock.withLock { accountLog.append("language:\(code)") }
    }

    public func setTimeZone(_: String) async throws {
        lock.withLock { accountLog.append("timezone") }
    }

    public func deleteAccount(reason _: String?) async throws {
        lock.withLock { accountLog.append("delete") }
    }

    public func availableLanguages() async throws -> [(name: String, code: String)] {
        [("English", "en"), ("German", "de"), ("Spanish", "es")]
    }

    // MARK: Settings

    public nonisolated(unsafe) var settingsLog: [String] = []

    func failIfNeeded() throws {
        if let failure = lock.withLock({ _error }) { throw failure }
    }

    public nonisolated(unsafe) var fakePeople: [Person] = []
    /// Speaker labels, prompts and voice settings (`FakeAPIClient+Speakers.swift`).
    public nonisolated(unsafe) var speakers = FakeSpeakerBackend()

    /// What `subscription()` reports as `transcription_allowance` (nil: the field is missing).
    public nonisolated(unsafe) var transcriptionAllowance: TranscriptionAllowance?

    /// Plans, prices and checkout calls (`FakeAPIClient+Payments.swift`).
    public nonisolated(unsafe) var payments = FakePayments()

    public func dailySummary() async throws -> (enabled: Bool, hour: Int) {
        (true, 22)
    }

    public func setDailySummary(enabled: Bool, hour: Int) async throws {
        try failIfNeeded(); settingsLog.append("daily:\(enabled):\(hour)")
    }

    public func notificationFrequency() async throws -> Int {
        0
    }

    public func setNotificationFrequency(_ value: Int) async throws {
        try failIfNeeded(); settingsLog.append("frequency:\(value)")
    }

    public func storesRecordings() async throws -> Bool {
        false
    }

    public func setStoresRecordings(_ value: Bool) async throws {
        try failIfNeeded(); settingsLog.append("recordings:\(value)")
    }

    public func assistantVoices() async throws -> (voices: [(id: String, name: String)], selected: String?) {
        ([("Puck", "Puck"), ("Charon", "Charon")], "Charon")
    }

    public func setAssistantVoice(_ id: String) async throws {
        try failIfNeeded(); settingsLog.append("voice:\(id)")
    }

    public func vocabulary() async throws -> [String] {
        ["Omi"]
    }

    public func setVocabulary(_ words: [String]) async throws {
        try failIfNeeded(); settingsLog.append("vocabulary:\(words.joined(separator: ","))")
    }

    public func people() async throws -> [Person] {
        fakePeople
    }

    public func addPerson(_ name: String) async throws {
        fakePeople.append(Person(id: "p\(fakePeople.count)", name: name, sampleCount: 0))
    }

    public func renamePerson(_ id: String, to name: String) async throws {
        if let index = fakePeople.firstIndex(where: { $0.id == id }) { fakePeople[index].name = name }
    }

    public func deletePerson(_ id: String) async throws {
        fakePeople.removeAll { $0.id == id }
    }

    public func phoneNumbers() async throws -> [PhoneNumber] {
        []
    }

    // MARK: Capabilities

    public nonisolated(unsafe) var connectedIntegrations: Set<String> = ["google_calendar"]

    public func integrationConnected(_ key: String) async throws -> Bool {
        connectedIntegrations.contains(key)
    }

    /// Set to make `integrationOAuthURL` fail the way the backend does (e.g. an app it has no OAuth client for).
    public nonisolated(unsafe) var oauthURLError: APIError?

    public func integrationOAuthURL(_ integration: Integration) async throws -> URL {
        if let oauthURLError { throw oauthURLError }
        return URL(string: "https://auth.example/\(integration.id)")!
    }

    public func disconnectIntegration(_ integration: Integration) async throws {
        connectedIntegrations.remove(integration.id)
    }

    public func connectedTaskApps() async throws -> Set<String> {
        connectedIntegrations.intersection(["todoist", "asana", "clickup", "google_tasks", "apple_reminders"])
    }

    public nonisolated(unsafe) var apps: [OmiApp] = [
        OmiApp(id: "a1", name: "Meeting Coach", description: "Feedback on how you run meetings", author: "Omi",
               imageURL: nil, category: "productivity", rating: 4.7, installs: 1200, isEnabled: true),
        OmiApp(id: "a2", name: "Notion Sync", description: "Send summaries to Notion", author: "Community",
               imageURL: nil, category: "integrations", rating: 4.2, installs: 800, isEnabled: false),
    ]

    public func searchApps(query: String, installedOnly: Bool, offset _: Int) async throws -> [OmiApp] {
        apps.filter { (!installedOnly || $0.isEnabled) && (query.isEmpty || $0.name.localizedCaseInsensitiveContains(query)) }
    }

    public func setApp(_ id: String, enabled: Bool) async throws {
        try failIfNeeded()
        if let index = apps.firstIndex(where: { $0.id == id }) { apps[index].isEnabled = enabled }
    }

    // MARK: Capture

    public let liveChannel = FakeLiveChannel()
    /// Finalizing by id, call order, a slow socket (`FakeAPIClient+Listen.swift`).
    public let listenBackend = FakeListenBackend()
    public let syncBackend = FakeSyncBackend(), placesAndHealth = FakePlacesAndHealth() // + location, health (`+Location.swift`)
    /// Developer settings, app store, chat apps, task app settings (`FakeAPIClient+Developer.swift`).
    public let devApps = FakeDevAppsBackend()
    public let deviceActions = FakeDeviceActions()
    /// Diagnostics bundles sent to support (`FakeAPIClient+DeviceActions.swift`).
    public let diagnosticsUploads = FakeDiagnosticsUploads()
    /// Numbers, verification, tokens, call sockets (`FakeAPIClient+PhoneCalls.swift`).
    public let phoneCalls = FakePhoneCalls()
    public internal(set) var finalizeCalls = 0
    /// Every `/v4/listen` opened, in order.
    public internal(set) var listenOptions: [ListenSocket.Options] = []
}
