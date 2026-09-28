import Foundation

// Public service facades over `BackendTransport` — the seam the UI layer
// consumes. Signatures follow the TS client exports.

// MARK: - Chat

public protocol ChatServicing: Sendable {
    func loadNewestChatHistory() async throws -> ChatHistoryPage
    func loadOlderChatHistory(olderCursor: String) async throws -> ChatHistoryPage
    func sendChatMessage(
        _ text: String,
        now: Int64,
        onGenerationStarted: (@Sendable (String) -> Void)?,
        localMessage: ChatMessage?,
        onRequestStarted: (@Sendable (String) -> Bool)?,
        onAssistantText: (@Sendable (String) -> Void)?
    ) async throws -> ChatSendResult
    func cancelChatGeneration(_ generationId: String) async throws
}

public final class ChatService: ChatServicing {
    private let transport: BackendTransport

    public init(transport: BackendTransport) {
        self.transport = transport
    }

    public func loadNewestChatHistory() async throws -> ChatHistoryPage {
        try await OmiKit.loadNewestChatHistory(transport)
    }

    public func loadOlderChatHistory(olderCursor: String) async throws -> ChatHistoryPage {
        try await OmiKit.loadOlderChatHistory(transport, olderCursor: olderCursor)
    }

    public func sendChatMessage(
        _ text: String,
        now: Int64,
        onGenerationStarted: (@Sendable (String) -> Void)?,
        localMessage: ChatMessage?,
        onRequestStarted: (@Sendable (String) -> Bool)?,
        onAssistantText: (@Sendable (String) -> Void)?
    ) async throws -> ChatSendResult {
        try await OmiKit.sendChatMessage(
            transport, text, now: now,
            onGenerationStarted: onGenerationStarted,
            localMessage: localMessage,
            onRequestStarted: onRequestStarted,
            onAssistantText: onAssistantText)
    }

    public func cancelChatGeneration(_ generationId: String) async throws {
        await transport.cancelGenerationEvents(generationId: generationId)
    }
}

// MARK: - Reads

public protocol ReadsServicing: Sendable {
    func loadConversations(cursor: String?) async throws
        -> DomainRead<ConversationProjection>
    func loadMemories(cursor: String?) async throws -> DomainRead<MemoryProjection>
    func loadTasks(cursor: String?) async throws -> TaskRead
    func loadDesktopReads() async -> DesktopReadOutcomes
}

public final class ReadsService: ReadsServicing {
    private let transport: BackendTransport

    public init(transport: BackendTransport) {
        self.transport = transport
    }

    public func loadConversations(cursor: String?) async throws
        -> DomainRead<ConversationProjection>
    {
        try await OmiKit.loadConversations(transport, cursor: cursor)
    }

    public func loadMemories(cursor: String?) async throws
        -> DomainRead<MemoryProjection>
    {
        try await OmiKit.loadMemories(transport, cursor: cursor)
    }

    public func loadTasks(cursor: String?) async throws -> TaskRead {
        try await OmiKit.loadTasks(transport, cursor: cursor)
    }

    public func loadDesktopReads() async -> DesktopReadOutcomes {
        await OmiKit.loadDesktopReads(transport)
    }
}

// MARK: - Tasks

public protocol TasksServicing: Sendable {
    func prepareTaskPatch(
        recordId: String, apiContract: APIContract?, baseRevision: String?,
        accountEpoch: Int64?, patch: TaskPatch
    ) async throws -> PreparedTaskPatch
    func sendTaskPatch(_ prepared: PreparedTaskPatch) async -> TaskPatchResult
}

public final class TasksService: TasksServicing {
    private let transport: BackendTransport

    public init(transport: BackendTransport) {
        self.transport = transport
    }

    public func prepareTaskPatch(
        recordId: String, apiContract: APIContract?, baseRevision: String?,
        accountEpoch: Int64?, patch: TaskPatch
    ) async throws -> PreparedTaskPatch {
        try await OmiKit.prepareTaskPatch(
            transport, recordId: recordId, apiContract: apiContract,
            baseRevision: baseRevision, accountEpoch: accountEpoch, patch: patch)
    }

    public func sendTaskPatch(_ prepared: PreparedTaskPatch) async -> TaskPatchResult {
        await OmiKit.sendTaskPatch(transport, prepared)
    }
}

// MARK: - Cloud

public protocol CloudServicing: Sendable {
    func loadConnectors() async throws -> ConnectorsSnapshot
    func loadAccountSettings() async -> AccountSettingsSnapshot
    func enableCloudApp(appId: String) async throws
    func disableCloudApp(appId: String) async throws
    func setStoreRecordingPermission(_ value: Bool) async throws
    func setPrivateCloudSync(_ value: Bool) async throws
    func optInTrainingData() async throws
    func loadServiceSettings() async throws -> ServiceSettingsSnapshot
}

public final class CloudService: CloudServicing {
    private let transport: BackendTransport

    public init(transport: BackendTransport) {
        self.transport = transport
    }

    public func loadConnectors() async throws -> ConnectorsSnapshot {
        try await OmiKit.loadConnectors(transport)
    }

    public func loadAccountSettings() async -> AccountSettingsSnapshot {
        await OmiKit.loadAccountSettings(transport)
    }

    public func enableCloudApp(appId: String) async throws {
        try await OmiKit.enableCloudApp(transport, appId: appId)
    }

    public func disableCloudApp(appId: String) async throws {
        try await OmiKit.disableCloudApp(transport, appId: appId)
    }

    public func setStoreRecordingPermission(_ value: Bool) async throws {
        try await OmiKit.setStoreRecordingPermission(transport, value: value)
    }

    public func setPrivateCloudSync(_ value: Bool) async throws {
        try await OmiKit.setPrivateCloudSync(transport, value: value)
    }

    public func optInTrainingData() async throws {
        try await OmiKit.optInTrainingData(transport)
    }

    public func loadServiceSettings() async throws -> ServiceSettingsSnapshot {
        try await OmiKit.loadServiceSettings(transport)
    }
}

// MARK: - Settings

/// A typed preference value for the setters.
public enum PreferenceValue: Sendable, Equatable {
    case bool(Bool)
    case integer(Int)
    case string(String)
}

public protocol SettingsStoring: Sendable {
    func loadPreferences() async -> DesktopPreferences
    func setPreference(_ key: String, _ value: PreferenceValue) async -> DesktopPreferences
    func permissionStatus() async -> [PermissionKind: PermissionState]
    func requestPermission(_ kind: PermissionKind) async -> PermissionState
}

/// Key-value defaults backend for `SettingsStore` (native hosts bind
/// UserDefaults / Android SharedPreferences here).
public protocol KeyValueStoring: Sendable {
    func value(forKey key: String) -> PreferenceValue?
    func set(_ value: PreferenceValue?, forKey key: String)
}

public final class SettingsStore: SettingsStoring {
    private let storage: KeyValueStoring
    private let lock = NSLock()

    public init(storage: KeyValueStoring) {
        self.storage = storage
    }

    private func recordLocked() -> JSONValue {
        var members = [(String, JSONValue)]()
        func append(_ key: String, _ value: PreferenceValue?) {
            guard let value else { return }
            switch value {
            case .bool(let bool): members.append((key, JSONValue.bool(bool)))
            case .integer(let int): members.append((key, JSONValue.integer(Int64(int))))
            case .string(let string): members.append((key, JSONValue.string(string)))
            }
        }
        // Translate native defaults keys to JS record names (the upstream
        // `OmiDesktopCommandsModule.mm` record shape that snapshotFromRecord
        // parses). stampedV5Origin + the onboarding setup revision are
        // native-only keys appended under their record names.
        for (nativeKey, recordKey) in zip(
            desktopPreferenceKeys.all, desktopPreferenceKeys.recordNames)
        {
            append(recordKey, storage.value(forKey: nativeKey))
        }
        append("stampedV5Origin", storage.value(forKey: "stampedV5Origin"))
        append(
            "onboardingSetupRevision",
            storage.value(forKey: desktopPreferenceKeys.onboardingSetupRevision))
        return JSONValue.object(members)
    }

    public func loadPreferences() async -> DesktopPreferences {
        loadSync()
    }

    public func setPreference(
        _ key: String, _ value: PreferenceValue
    ) async -> DesktopPreferences {
        setSync(key, value)
    }

    private func loadSync() -> DesktopPreferences {
        lock.lock()
        defer { lock.unlock() }
        return snapshotFromRecord(recordLocked())
    }

    private func setSync(_ key: String, _ value: PreferenceValue) -> DesktopPreferences {
        lock.lock()
        storage.set(value, forKey: key)
        let snapshot = snapshotFromRecord(recordLocked())
        lock.unlock()
        return snapshot
    }

    public func permissionStatus() async -> [PermissionKind: PermissionState] {
        [:]
    }

    public func requestPermission(_ kind: PermissionKind) async -> PermissionState {
        .unknown
    }
}
