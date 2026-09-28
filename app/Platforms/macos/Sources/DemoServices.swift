import Foundation
import OmiKit
import OmiUI

// Labeled in-memory demo bundle for `-omiDemoData` — screenshots and UI
// exploration only, never the default stack (see OmiBootstrap). Reads, chat,
// cloud, and settings are in-memory facades; task mutations run the REAL
// `TasksService` over an in-memory transport so the canonical write-op paths
// (prepare, send, accepted-shape verification, retry) execute unchanged.
// Every screen renders the same views it would against api.omi.me.

// MARK: - Shared demo state

final class DemoState: @unchecked Sendable {
    private let lock = NSLock()
    private var conversations: [ConversationProjection]
    private var memories: [MemoryProjection]
    private var tasks: [TaskProjection]
    private var chat: [ChatMessage]
    private var apps: [CloudApp]
    private var enabledIds: Set<String>
    private var account: AccountSettingsSnapshot
    private var counters: [String: Int] = [:]

    init() {
        let now = Int64(Date().timeIntervalSince1970 * 1000)
        let hour: Int64 = 3_600_000
        let iso = isoString(fromEpochMilliseconds:)

        func revision(_ seed: Int) -> String {
            let hex = String(format: "%064x", seed)
            return String(hex.suffix(64))
        }

        conversations = [
            ConversationProjection(
                capturedAtMs: now - 2 * hour, id: "conv-standup",
                title: "Sprint sync with the platform team",
                summary:
                    "Reviewed the release cutoff for Friday, agreed to freeze the schema migration behind a flag, and split the analytics backlog into two tracked streams.",
                searchableText:
                    "Sprint sync with the platform team release cutoff schema migration analytics backlog",
                createdAt: iso(now - 2 * hour), starred: false, status: "completed",
                source: "omi", visibility: .priv),
            ConversationProjection(
                capturedAtMs: now - 26 * hour, id: "conv-reading",
                title: "Reading group — chapters 6 and 7",
                summary:
                    "Discussed the second half of chapter 6 and the framing of chapter 7; next meeting covers the case studies and Priya volunteers the notes.",
                searchableText: "reading group chapters case studies notes",
                createdAt: iso(now - 26 * hour), starred: true, status: "completed",
                source: "omi", visibility: .priv),
            ConversationProjection(
                capturedAtMs: now - 50 * hour, id: "conv-trip",
                title: "Weekend trip planning",
                summary:
                    "Settled on the coast route, booked the Saturday tasting, and agreed to leave early to beat traffic.",
                searchableText: "weekend trip coast route tasting leave early",
                createdAt: iso(now - 50 * hour), starred: false, status: "completed",
                source: "omi", visibility: .priv),
        ]

        memories = [
            MemoryProjection(
                id: "mem-sprint", title: "Release cadence",
                summary:
                    "The team ships on a two-week cadence with Friday cutoffs; schema migrations always ship behind a flag.",
                searchableText: "release cadence friday cutoff schema migrations flag",
                citations: ["Sprint sync with the platform team"],
                timestamp: now - 2 * hour,
                provenance: MemoryProvenance(
                    label: "synthesized", synthesisVersion: "v5", inputDigest: nil,
                    outputDigest: nil)),
            MemoryProjection(
                id: "mem-reading", title: "Reading group rhythm",
                summary:
                    "The reading group meets every second Thursday; notes rotate between members and Priya took chapters 6–7.",
                searchableText: "reading group thursday notes rotate priya",
                citations: ["Reading group — chapters 6 and 7"],
                timestamp: now - 26 * hour,
                provenance: MemoryProvenance(
                    label: "synthesized", synthesisVersion: "v5", inputDigest: nil,
                    outputDigest: nil)),
            MemoryProjection(
                id: "mem-coast", title: "Coast trips",
                summary:
                    "Prefers the coast route over the inland highway and likes leaving before 8 to skip traffic.",
                searchableText: "coast route inland highway leave early traffic",
                citations: ["Weekend trip planning"], timestamp: now - 50 * hour,
                provenance: MemoryProvenance(
                    label: "extracted", synthesisVersion: nil, inputDigest: nil,
                    outputDigest: nil)),
        ]

        tasks = [
            TaskProjection(
                id: "task-flag", title: "Flag the schema migration before cutoff",
                summary: "Flag the schema migration before cutoff",
                searchableText: "flag schema migration cutoff",
                completed: false, dueAt: now + 20 * hour, source: "conversation",
                provenance: ["Sprint sync with the platform team"], sortOrder: 0,
                indentLevel: 0, createdAt: now - 2 * hour, updatedAt: now - 2 * hour,
                revision: revision(1)),
            TaskProjection(
                id: "task-notes", title: "Send reading-group notes to Priya",
                summary: "Send reading-group notes to Priya",
                searchableText: "send reading group notes priya",
                completed: false, dueAt: now + 40 * hour, source: "conversation",
                provenance: ["Reading group — chapters 6 and 7"], sortOrder: 1,
                indentLevel: 0, createdAt: now - 26 * hour, updatedAt: now - 26 * hour,
                revision: revision(2)),
            TaskProjection(
                id: "task-book", title: "Confirm the Saturday tasting booking",
                summary: "Confirm the Saturday tasting booking",
                searchableText: "confirm saturday tasting booking",
                completed: false, dueAt: now + 4 * 24 * hour, source: "conversation",
                provenance: ["Weekend trip planning"], sortOrder: 2, indentLevel: 0,
                createdAt: now - 50 * hour, updatedAt: now - 50 * hour,
                revision: revision(3)),
            TaskProjection(
                id: "task-done", title: "Share the analytics split with the team",
                summary: "Share the analytics split with the team",
                searchableText: "share analytics split team",
                completed: true, completedAt: now - hour, dueAt: now - 2 * hour,
                source: "conversation", provenance: ["Sprint sync with the platform team"],
                sortOrder: 3, indentLevel: 0, createdAt: now - 3 * hour,
                updatedAt: now - hour, revision: revision(4)),
        ]

        let welcomeHuman = ChatMessage(
            id: "chat-seed-1", text: "What did I talk about today?", sender: .human,
            createdAt: now - hour)
        let welcomeAI = ChatMessage(
            id: "chat-seed-2",
            text:
                "Two conversations today. The sprint sync set Friday's release cutoff and left you a task: flag the schema migration before it lands. The reading group covered chapters 6 and 7, and your notes are due to Priya.",
            sender: .ai, createdAt: now - hour + 4_000, generationOutcome: .completed)
        chat = [welcomeHuman, welcomeAI]

        apps = [
            CloudApp(
                id: "app-notion", name: "Notion Sync", description: "Push conversations and action items into a Notion database.",
                category: "Productivity", author: "Omi", enabled: false, uid: nil,
                isPrivate: false, official: true, installs: 4_211,
                hasExternalIntegration: true, connectedAccounts: []),
            CloudApp(
                id: "app-spotify", name: "Now Playing", description: "Attach the track you were listening to to each conversation.",
                category: "Music", author: "Omi", enabled: true, uid: nil,
                isPrivate: false, official: true, installs: 9_845,
                hasExternalIntegration: true, connectedAccounts: []),
            CloudApp(
                id: "app-github", name: "Commit Tracker", description: "Link discussion topics to the commits they produced.",
                category: "Developer Tools", author: "Omi", enabled: false, uid: nil,
                isPrivate: false, official: true, installs: 2_730,
                hasExternalIntegration: true, connectedAccounts: []),
            CloudApp(
                id: "app-slack", name: "Slack Digest", description: "Deliver a morning digest of open threads to a channel.",
                category: "Communication", author: "Kite", enabled: false, uid: nil,
                isPrivate: false, official: false, installs: 1_502,
                hasExternalIntegration: true, connectedAccounts: []),
            CloudApp(
                id: "app-review", name: "Weekly Review", description: "A Friday recap of conversations, memories, and open tasks.",
                category: "Productivity", author: "Omi", enabled: true, uid: nil,
                isPrivate: false, official: true, installs: 6_114,
                hasExternalIntegration: false, connectedAccounts: []),
        ]
        enabledIds = ["app-spotify", "app-review"]

        account = AccountSettingsSnapshot(
            profile: CloudProfile(
                uid: "demo", name: "Demo", email: "demo@omi.me", company: nil,
                job: nil, dataProtectionLevel: "e2ee"),
            subscription: CloudSubscription(
                plan: "basic", status: "active", transcriptionSecondsUsed: 1_284,
                transcriptionSecondsLimit: 6_000),
            storeRecordingPermission: true, trainingOptedIn: false,
            privateCloudSync: false,
            webhooks: [CloudWebhookStatus(type: "daily_digest", enabled: true, url: nil)])
    }

    // MARK: Reads

    func conversationsRead() -> DomainRead<ConversationProjection> {
        lock.lock(); defer { lock.unlock() }
        return DomainRead(items: conversations, page: DemoState.completePage)
    }

    func memoriesRead() -> DomainRead<MemoryProjection> {
        lock.lock(); defer { lock.unlock() }
        return DomainRead(items: memories, page: DemoState.completePage)
    }

    func tasksRead() -> TaskRead {
        lock.lock(); defer { lock.unlock() }
        return TaskRead(
            apiContract: .canonical, items: tasks, page: DemoState.completePage,
            accountEpoch: 7)
    }

    static let completePage = ReadPageState(
        windowStatus: .complete, complete: true, hasMore: false, nextCursor: nil,
        completenessStatus: .complete, reasons: [])

    // MARK: Chat

    func chatSnapshot() -> [ChatMessage] {
        lock.lock(); defer { lock.unlock() }
        return chat
    }

    func appendChat(human: ChatMessage, assistant: ChatMessage) {
        lock.lock(); defer { lock.unlock() }
        chat.append(contentsOf: [human, assistant])
    }

    func nextCounter(_ key: String) -> Int {
        lock.lock(); defer { lock.unlock() }
        counters[key, default: 0] += 1
        return counters[key]!
    }

    func freshRevision() -> String {
        String(format: "%064x", nextCounter("revision") + 16)
    }

    // MARK: Write ops (canonical envelope from the real TasksService path)

    /// Applies one canonical write-op envelope; returns the applied record id
    /// (mirroring the server's accepted shape) or nil for a stale epoch.
    func applyWriteOps(_ envelope: JSONValue) -> String? {
        guard envelope["domain"]?.stringValue == "tasks",
            envelope["account_epoch"]?.numberValue == 7,
            let op = envelope["op"]
        else { return nil }
        lock.lock(); defer { lock.unlock() }
        switch op["op"]?.stringValue {
        case "create":
            guard let recordId = op["record_id"]?.stringValue else { return nil }
            let description = op["content"]?["description"]?.stringValue ?? recordId
            let createdAt = op["content"]?["createdAt"]?.numberValue
            tasks.append(
                TaskProjection(
                    id: recordId, title: description, summary: description,
                    searchableText: description, completed: false, source: "manual",
                    provenance: [], sortOrder: tasks.count, indentLevel: 0,
                    createdAt: createdAt.map { Int64($0) },
                    updatedAt: createdAt.map { Int64($0) }, revision: freshRevision()))
            return recordId
        case "patch":
            guard let recordId = op["record_id"]?.stringValue,
                let index = tasks.firstIndex(where: { $0.id == recordId })
            else { return nil }
            let patch = op["patch"]
            if let completed = patch?["completed"]?.boolValue {
                tasks[index].completed = completed
                tasks[index].completedAt =
                    completed ? patch?["completedAt"]?.numberValue.map { Int64($0) } : nil
            }
            if let description = patch?["description"]?.stringValue {
                tasks[index].title = description
                tasks[index].summary = description
                tasks[index].searchableText = description
            }
            tasks[index].revision = freshRevision()
            return recordId
        case "delete":
            guard let recordId = op["record_id"]?.stringValue else { return nil }
            tasks.removeAll { $0.id == recordId }
            return recordId
        default:
            return nil
        }
    }

    // MARK: Cloud

    func connectorsSnapshot() -> ConnectorsSnapshot {
        lock.lock(); defer { lock.unlock() }
        return ConnectorsSnapshot(
            apps: apps, enabledIds: Array(enabledIds).sorted(), enabledError: nil,
            ownerUid: "demo")
    }

    func accountSnapshot() -> AccountSettingsSnapshot {
        lock.lock(); defer { lock.unlock() }
        return account
    }

    func setAppEnabled(_ appId: String, _ enabled: Bool) {
        lock.lock(); defer { lock.unlock() }
        if enabled { enabledIds.insert(appId) } else { enabledIds.remove(appId) }
    }

    func setStoreRecordingPermission(_ value: Bool) {
        lock.lock(); defer { lock.unlock() }
        account.storeRecordingPermission = value
        account.storeRecordingError = nil
    }

    func setPrivateCloudSync(_ value: Bool) {
        lock.lock(); defer { lock.unlock() }
        account.privateCloudSync = value
        account.privateCloudSyncError = nil
    }

    func optInTrainingData() {
        lock.lock(); defer { lock.unlock() }
        account.trainingOptedIn = true
        account.trainingError = nil
    }
}

// MARK: - Reads

private final class DemoReadsService: ReadsServicing {
    let state: DemoState

    init(state: DemoState) {
        self.state = state
    }

    func loadConversations(cursor: String?) async throws
        -> DomainRead<ConversationProjection>
    {
        state.conversationsRead()
    }

    func loadMemories(cursor: String?) async throws -> DomainRead<MemoryProjection> {
        state.memoriesRead()
    }

    func loadTasks(cursor: String?) async throws -> TaskRead {
        state.tasksRead()
    }

    func loadDesktopReads() async -> DesktopReadOutcomes {
        DesktopReadOutcomes(
            conversations: .success(state.conversationsRead()),
            memories: .success(state.memoriesRead()),
            tasks: .success(state.tasksRead()))
    }
}

// MARK: - Chat

private final class DemoChatService: ChatServicing {
    static let replyPrefix =
        "Here's the shape of your day: the sprint sync set Friday's release cutoff, "
        + "the reading group notes are due to Priya, and the coast trip is settled. "
        + "The most time-sensitive item is flagging the schema migration before the cutoff."

    let state: DemoState
    /// Request ids the Stop button cancelled (bridged through the transport).
    let cancelledRequestIds: CancelledRequestIds

    init(state: DemoState, cancelledRequestIds: CancelledRequestIds) {
        self.state = state
        self.cancelledRequestIds = cancelledRequestIds
    }

    func loadNewestChatHistory() async throws -> ChatHistoryPage {
        ChatHistoryPage(
            messages: state.chatSnapshot(), olderCursor: nil, hasOlder: false)
    }

    func loadOlderChatHistory(olderCursor: String) async throws -> ChatHistoryPage {
        ChatHistoryPage(messages: [], olderCursor: nil, hasOlder: false)
    }

    func sendChatMessage(
        _ text: String,
        now: Int64,
        onGenerationStarted: (@Sendable (String) -> Void)?,
        localMessage: ChatMessage?,
        onRequestStarted: (@Sendable (String) -> Bool)?,
        onAssistantText: (@Sendable (String) -> Void)?
    ) async throws -> ChatSendResult {
        let human = localMessage ?? createLocalChatMessage(text, now: now)
        let generation = state.nextCounter("generation")
        let generationId = "demo-gen-\(generation)"
        let requestId = human.id
        _ = onRequestStarted?(requestId)
        onGenerationStarted?(generationId)
        var visible = ""
        for word in DemoChatService.replyPrefix.split(separator: " ") {
            if cancelledRequestIds.contains(requestId) { throw TransportFailure.cancelled }
            visible += visible.isEmpty ? String(word) : " \(word)"
            onAssistantText?(visible)
            try? await Task.sleep(nanoseconds: 45_000_000)
        }
        let assistant = ChatMessage(
            id: "generation:\(generationId)", text: visible, sender: .ai,
            createdAt: now + Int64(generation) * 1_000 + 4_000,
            generationOutcome: .completed, generationId: generationId,
            localOnly: false)
        state.appendChat(human: human, assistant: assistant)
        return (human: human, assistant: assistant)
    }

    func cancelChatGeneration(_ generationId: String) async {}
}

/// Shared Stop-button cancellation registry (the transport and the demo chat
/// service both see it).
final class CancelledRequestIds: @unchecked Sendable {
    private let lock = NSLock()
    private var ids: Set<String> = []

    func cancel(_ requestId: String) {
        lock.lock(); defer { lock.unlock() }
        ids.insert(requestId)
    }

    func contains(_ requestId: String) -> Bool {
        lock.lock(); defer { lock.unlock() }
        return ids.contains(requestId)
    }
}

// MARK: - Cloud

private final class DemoCloudService: CloudServicing {
    let state: DemoState

    init(state: DemoState) {
        self.state = state
    }

    func loadConnectors() async throws -> ConnectorsSnapshot {
        state.connectorsSnapshot()
    }

    func loadAccountSettings() async -> AccountSettingsSnapshot {
        state.accountSnapshot()
    }

    func enableCloudApp(appId: String) async throws {
        state.setAppEnabled(appId, true)
    }

    func disableCloudApp(appId: String) async throws {
        state.setAppEnabled(appId, false)
    }

    func setStoreRecordingPermission(_ value: Bool) async throws {
        state.setStoreRecordingPermission(value)
    }

    func setPrivateCloudSync(_ value: Bool) async throws {
        state.setPrivateCloudSync(value)
    }

    func optInTrainingData() async throws {
        state.optInTrainingData()
    }

    func loadServiceSettings() async throws -> ServiceSettingsSnapshot {
        ServiceSettingsSnapshot(
            identity: ServiceIdentity(displayName: "Demo", email: "demo@omi.me"),
            entitlement: ServiceEntitlement(limitKey: "transcription_seconds", used: 1_284, limit: 6_000))
    }
}

// MARK: - Settings

/// In-memory `SettingsStoring` seeded so the demo opens on the completed-
/// onboarding path, parsed through the same tolerant parsers as production.
private final class DemoSettingsStore: SettingsStoring {
    static let onboardingMarker = "completed"

    private let lock = NSLock()
    private var values: [String: PreferenceValue] = [
        SOFTWARE_PLANE_DEFAULTS_KEY: .string("old"),
        desktopPreferenceKeys.screenCapture: .bool(true),
        desktopPreferenceKeys.audioMode: .string("always"),
        desktopPreferenceKeys.fontScale: .integer(100),
        desktopPreferenceKeys.rewindRetentionDays: .integer(14),
        desktopPreferenceKeys.liveVoiceProvider: .string("gpt_live"),
        desktopPreferenceKeys.exploreProgress: .string(DemoSettingsStore.onboardingMarker),
    ]

    func loadPreferences() async -> DesktopPreferences {
        snapshot()
    }

    func setPreference(_ key: String, _ value: PreferenceValue) async -> DesktopPreferences {
        lock.lock()
        values[key] = value
        lock.unlock()
        return snapshot()
    }

    func permissionStatus() async -> [PermissionKind: PermissionState] {
        [
            PermissionKind.screen: .granted,
            PermissionKind.microphone: .granted,
            PermissionKind.notifications: .granted,
        ]
    }

    func requestPermission(_ kind: PermissionKind) async -> PermissionState {
        .granted
    }

    private func snapshot() -> DesktopPreferences {
        lock.lock(); defer { lock.unlock() }
        var preferences = DesktopPreferences()
        for (key, value) in values {
            switch (key, value) {
            case (SOFTWARE_PLANE_DEFAULTS_KEY, .string(let text)):
                preferences.softwarePlane = parseSoftwarePlane(.string(text))
            case (desktopPreferenceKeys.screenCapture, .bool(let bool)):
                preferences.screenCapture = bool
            case (desktopPreferenceKeys.audioMode, .string(let text)):
                preferences.audioMode = parseAudioRecordingMode(.string(text))
            case (desktopPreferenceKeys.interfaceSounds, .bool(let bool)):
                preferences.interfaceSounds = bool
            case (desktopPreferenceKeys.fontScale, .integer(let int)):
                preferences.fontScale = int
            case (desktopPreferenceKeys.notificationsEnabled, .bool(let bool)):
                preferences.notificationsEnabled = bool
            case (desktopPreferenceKeys.rewindRetentionDays, .integer(let int)):
                preferences.rewindRetentionDays = int
            case (desktopPreferenceKeys.meetingNoteScreenshots, .bool(let bool)):
                preferences.meetingNoteScreenshots = bool
            case (desktopPreferenceKeys.floatingBar, .bool(let bool)):
                preferences.floatingBar = bool
            case (desktopPreferenceKeys.transcriptionAutoDetect, .bool(let bool)):
                preferences.transcriptionAutoDetect = bool
            case (desktopPreferenceKeys.vadGate, .bool(let bool)):
                preferences.vadGate = bool
            case (desktopPreferenceKeys.openOmiShortcut, .bool(let bool)):
                preferences.openOmiShortcut = bool
            case (desktopPreferenceKeys.pushToTalk, .bool(let bool)):
                preferences.pushToTalk = bool
            case (desktopPreferenceKeys.liveVoiceProvider, .string(let text)):
                preferences.liveVoiceProvider = parseLiveVoiceProvider(.string(text))
            case (desktopPreferenceKeys.appearance, .string(let text)):
                preferences.appearance = parseDesktopAppearance(.string(text))
            case (desktopPreferenceKeys.uiVersion, .string(let text)):
                preferences.uiVersion = parseDesktopUiVersion(.string(text))
            case (desktopPreferenceKeys.exploreProgress, .string(let text)):
                preferences.exploreProgress = text
            default: break
            }
        }
        return preferences
    }
}

// MARK: - Transport (canonical write-op path for the real TasksService)

/// In-memory transport serving only the canonical tasks write-op path, so
/// task toggle/rename/add run the real prepare → send → classify pipeline.
final class DemoBackendTransport: BackendTransport, OmiChatStreaming, @unchecked Sendable {
    let state: DemoState
    let cancelledRequestIds: CancelledRequestIds

    init(state: DemoState, cancelledRequestIds: CancelledRequestIds) {
        self.state = state
        self.cancelledRequestIds = cancelledRequestIds
    }

    func request(_ request: BackendRequest) async throws -> BackendResponse {
        guard request.method == .post, request.path == writeOpsPath("tasks"),
            let body = request.body,
            let envelope = JSON.parseOrNull(body)
        else {
            throw TransportFailure.unconfigured
        }
        if let recordId = state.applyWriteOps(envelope) {
            let revision = state.freshRevision()
            return BackendResponse(
                id: request.id, status: 200,
                body:
                    "{\"applied\":{\"record_id\":\"\(recordId)\",\"revision\":\"\(revision)\"},\"idempotent\":false}"
            )
        }
        return BackendResponse(
            id: request.id, status: 409,
            body: "{\"error\":\"stale_epoch\",\"refusal_outcome\":\"stale_epoch\"}")
    }

    func generationEvents(
        generationId: String, lastEventId: String?,
        onFrame: @escaping @Sendable (String) -> Void
    ) async throws -> BackendResponse {
        throw TransportFailure.unconfigured
    }

    func cancelGenerationEvents(generationId: String) async {}

    func createWriteId() async throws -> String {
        var entropy = [UInt8](repeating: 0, count: WRITE_ID_ENTROPY_BYTES)
        for index in entropy.indices {
            entropy[index] = UInt8.random(in: 0...255)
        }
        guard let writeId = mintWriteId(entropy) else {
            throw TransportFailure.unconfigured
        }
        return writeId
    }

    func createRecordingId() async throws -> String {
        UUID().uuidString.lowercased()
    }

    func apiContract() async -> APIContract? { .canonical }
    func softwarePlane() async -> SoftwarePlane? { .old }
    func setSoftwarePlane(_ plane: SoftwarePlane) async -> SoftwarePlane? { plane }
    func stampedBackendOrigin() async -> String? { nil }

    // OmiChatStreaming: the store's Stop path probes this capability.
    func sendOmiChat(
        requestId: String, text: String, onFrame: (@Sendable (String) -> Void)?
    ) async throws -> BackendResponse {
        throw TransportFailure.unconfigured
    }

    func cancelOmiChat(requestId: String) async {
        cancelledRequestIds.cancel(requestId)
    }
}

// MARK: - Auth

/// Signs in immediately (the optimistic `Authenticating` default the store
/// probes with), so the demo opens on the ready shell.
final class DemoAuthSession: Authenticating, @unchecked Sendable {
    private let handoffs = AsyncStream<DesktopHandoff>.makeStream()
    private let invalidations = AsyncStream<Void>.makeStream()

    var desktopHandoffs: AsyncStream<DesktopHandoff> { handoffs.stream }
    var sessionInvalidated: AsyncStream<Void> { invalidations.stream }

    func signIn() async throws -> Bool {
        try? await Task.sleep(nanoseconds: 350_000_000)
        return true
    }

    func cancelSignIn() async {}

    func signOut() async throws -> Bool {
        invalidations.continuation.yield(())
        true
    }
}

// MARK: - Bundle assembly

enum DemoServices {
    /// The labeled demo bundle. The explore-progress marker seeds the
    /// completed-onboarding path; the capture toggle drives the real host
    /// engine because the demo settings report Screen Recording granted.
    static func makeServices() -> AppServices {
        let state = DemoState()
        let cancelled = CancelledRequestIds()
        let transport = DemoBackendTransport(state: state, cancelledRequestIds: cancelled)
        return AppServices(
            auth: DemoAuthSession(),
            chat: DemoChatService(state: state, cancelledRequestIds: cancelled),
            reads: DemoReadsService(state: state),
            tasks: TasksService(transport: transport),
            cloud: DemoCloudService(state: state),
            settings: DemoSettingsStore(),
            devices: nil,
            rewindCapture: OmiRewindEngine.shared.bridge,
            transport: transport)
    }
}
