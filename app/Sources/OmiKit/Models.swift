import Foundation

// Shared product model types, ported from the ratified client layer
// (`react-native/src/desktopReadClient.ts`, `chatClient.ts`,
// `deviceSessionClient.ts`, `desktopCloudClient.ts`) and the native
// transport surface (`omiNativeTypes.ts`). Wire codecs and clients live in
// the Backend/Wire areas; this file is the type vocabulary every area uses.

// MARK: - Read projections

public struct ConversationProjection: Sendable, Hashable, Identifiable {
    public var capturedAtMs: Int64?
    public var id: String
    public var title: String
    public var summary: String
    public var searchableText: String
    public var createdAt: String
    public var updatedAt: String?
    public var startedAt: String?
    public var finishedAt: String?
    public var starred: Bool
    public var status: String
    public var source: String
    public var visibility: ProjectionVisibility
    public var folderId: String?
    public var locked: Bool
    public var discarded: Bool

    public init(
        capturedAtMs: Int64? = nil, id: String, title: String, summary: String,
        searchableText: String, createdAt: String, updatedAt: String? = nil,
        startedAt: String? = nil, finishedAt: String? = nil, starred: Bool,
        status: String, source: String, visibility: ProjectionVisibility,
        folderId: String? = nil, locked: Bool = false, discarded: Bool = false
    ) {
        self.capturedAtMs = capturedAtMs
        self.id = id
        self.title = title
        self.summary = summary
        self.searchableText = searchableText
        self.createdAt = createdAt
        self.updatedAt = updatedAt
        self.startedAt = startedAt
        self.finishedAt = finishedAt
        self.starred = starred
        self.status = status
        self.source = source
        self.visibility = visibility
        self.folderId = folderId
        self.locked = locked
        self.discarded = discarded
    }
}

public enum ProjectionVisibility: String, Sendable, Hashable {
    case pub = "public"
    case priv = "private"
    case shared
}

public struct MemoryProvenance: Sendable, Hashable {
    public var label: String?
    public var synthesisVersion: String?
    public var inputDigest: String?
    public var outputDigest: String?

    public init(
        label: String?, synthesisVersion: String?, inputDigest: String?,
        outputDigest: String?
    ) {
        self.label = label
        self.synthesisVersion = synthesisVersion
        self.inputDigest = inputDigest
        self.outputDigest = outputDigest
    }
}

public struct MemoryProjection: Sendable, Hashable, Identifiable {
    public var id: String
    public var title: String
    public var summary: String
    public var searchableText: String
    public var citations: [String]
    public var timestamp: Int64?
    public var provenance: MemoryProvenance

    public init(
        id: String, title: String, summary: String, searchableText: String,
        citations: [String], timestamp: Int64?, provenance: MemoryProvenance
    ) {
        self.id = id
        self.title = title
        self.summary = summary
        self.searchableText = searchableText
        self.citations = citations
        self.timestamp = timestamp
        self.provenance = provenance
    }
}

public struct TaskProjection: Sendable, Hashable, Identifiable {
    public var id: String
    public var title: String
    public var summary: String
    public var searchableText: String
    public var completed: Bool
    public var completedAt: Int64?
    public var dueAt: Int64?
    public var owner: String?
    public var source: String
    public var provenance: [String]
    public var sortOrder: Int
    public var indentLevel: Int
    public var createdAt: Int64?
    public var updatedAt: Int64?
    public var revision: String?

    public init(
        id: String, title: String, summary: String, searchableText: String,
        completed: Bool, completedAt: Int64? = nil, dueAt: Int64? = nil,
        owner: String? = nil, source: String, provenance: [String],
        sortOrder: Int, indentLevel: Int, createdAt: Int64? = nil,
        updatedAt: Int64? = nil, revision: String? = nil
    ) {
        self.id = id
        self.title = title
        self.summary = summary
        self.searchableText = searchableText
        self.completed = completed
        self.completedAt = completedAt
        self.dueAt = dueAt
        self.owner = owner
        self.source = source
        self.provenance = provenance
        self.sortOrder = sortOrder
        self.indentLevel = indentLevel
        self.createdAt = createdAt
        self.updatedAt = updatedAt
        self.revision = revision
    }
}

public enum TaskGroup: String, Sendable, Hashable {
    case today = "Today"
    case tomorrow = "Tomorrow"
    case later = "Later"
}

/// Port of `taskGroup` from `desktopReadClient.ts`.
public func taskGroup(dueAt: Int64?, nowMilliseconds: Int64) -> TaskGroup {
    guard let dueAt else { return .later }
    let today = nowMilliseconds / 86_400_000
    let dueDay = dueAt / 86_400_000
    if dueDay <= today { return .today }
    return dueDay == today + 1 ? .tomorrow : .later
}

public enum DesktopReadProjection: Sendable, Hashable, Identifiable {
    case conversation(ConversationProjection)
    case memory(MemoryProjection)
    case task(TaskProjection)

    public var id: String {
        switch self {
        case .conversation(let item): return item.id
        case .memory(let item): return item.id
        case .task(let item): return item.id
        }
    }

    public var title: String {
        switch self {
        case .conversation(let item): return item.title
        case .memory(let item): return item.title
        case .task(let item): return item.title
        }
    }

    public var summary: String {
        switch self {
        case .conversation(let item): return item.summary
        case .memory(let item): return item.summary
        case .task(let item): return item.summary
        }
    }

    public var searchableText: String {
        switch self {
        case .conversation(let item): return item.searchableText
        case .memory(let item): return item.searchableText
        case .task(let item): return item.searchableText
        }
    }

    /// Port of `projectionTimestamp` from `desktopReadClient.ts` —
    /// epoch milliseconds or nil when undateable.
    public var timestamp: Int64? {
        switch self {
        case .conversation(let item):
            let raw = item.startedAt ?? item.createdAt
            return parseEpochMilliseconds(raw)
        case .memory(let item):
            guard let seconds = item.timestamp else { return nil }
            return seconds * 1000
        case .task(let item):
            return item.createdAt
        }
    }
}

/// `Date.parse`-style ISO-ish parsing for projection timestamps; returns
/// epoch milliseconds, or nil when the value does not parse.
public func parseEpochMilliseconds(_ value: String) -> Int64? {
    if let seconds = ISO8601Reader.epochSeconds(value) {
        let millis = Int64(seconds * 1000)
        return millis
    }
    return nil
}

// MARK: - Read page envelopes

public enum ReadWindowStatus: String, Sendable, Hashable {
    case complete
    case more
    case incomplete
    case unknown
}

public enum ReadCompletenessStatus: String, Sendable, Hashable {
    case complete
    case incomplete
    case degraded
    case partial
    case unknown
}

public struct ReadPageState: Sendable, Hashable {
    public var windowStatus: ReadWindowStatus
    public var complete: Bool
    public var hasMore: Bool
    public var nextCursor: String?
    public var completenessStatus: ReadCompletenessStatus
    public var reasons: [String]

    public init(
        windowStatus: ReadWindowStatus, complete: Bool, hasMore: Bool,
        nextCursor: String?, completenessStatus: ReadCompletenessStatus,
        reasons: [String]
    ) {
        self.windowStatus = windowStatus
        self.complete = complete
        self.hasMore = hasMore
        self.nextCursor = nextCursor
        self.completenessStatus = completenessStatus
        self.reasons = reasons
    }
}

public struct DomainRead<T: Sendable & Hashable>: Sendable, Hashable {
    public var apiContract: APIContract?
    public var items: [T]
    public var page: ReadPageState

    public init(
        apiContract: APIContract? = nil, items: [T], page: ReadPageState
    ) {
        self.apiContract = apiContract
        self.items = items
        self.page = page
    }
}

// MARK: - Chat

public enum ChatSender: String, Sendable, Hashable {
    case human
    case ai
}

public enum GenerationOutcome: String, Sendable, Hashable {
    case completed
    case cancelled
    case failed
}

public struct ChatMessage: Sendable, Hashable, Identifiable {
    public var id: String
    public var text: String
    public var sender: ChatSender
    public var createdAt: Int64
    public var generationOutcome: GenerationOutcome?
    public var generationId: String?
    public var generationRetryable: Bool?
    public var localOnly: Bool?

    public init(
        id: String, text: String, sender: ChatSender, createdAt: Int64,
        generationOutcome: GenerationOutcome? = nil,
        generationId: String? = nil, generationRetryable: Bool? = nil,
        localOnly: Bool? = nil
    ) {
        self.id = id
        self.text = text
        self.sender = sender
        self.createdAt = createdAt
        self.generationOutcome = generationOutcome
        self.generationId = generationId
        self.generationRetryable = generationRetryable
        self.localOnly = localOnly
    }
}

public struct ChatHistoryPage: Sendable, Hashable {
    public var messages: [ChatMessage]
    public var olderCursor: String?
    public var hasOlder: Bool

    public init(messages: [ChatMessage], olderCursor: String?, hasOlder: Bool) {
        self.messages = messages
        self.olderCursor = olderCursor
        self.hasOlder = hasOlder
    }
}

// MARK: - Device sessions and recording journals

public enum DeviceSessionState: String, Sendable, Hashable {
    case open
    case complete
    case failed
}

public struct DeviceSessionRecord: Sendable, Hashable, Identifiable {
    public var capturedAtMs: Int64?
    public var id: String
    public var deviceId: String
    public var deviceName: String?
    public var codec: Int
    public var state: DeviceSessionState
    public var byteCount: Int
    public var chunkCount: Int
    public var startedAt: Int64
    public var endedAt: Int64?

    public init(
        capturedAtMs: Int64? = nil, id: String, deviceId: String,
        deviceName: String?, codec: Int, state: DeviceSessionState,
        byteCount: Int, chunkCount: Int, startedAt: Int64, endedAt: Int64?
    ) {
        self.capturedAtMs = capturedAtMs
        self.id = id
        self.deviceId = deviceId
        self.deviceName = deviceName
        self.codec = codec
        self.state = state
        self.byteCount = byteCount
        self.chunkCount = chunkCount
        self.startedAt = startedAt
        self.endedAt = endedAt
    }
}

public struct RecordingJournalInput: Sendable, Hashable {
    public var capturedAtMs: Int64?
    public var deviceId: String
    public var deviceName: String?
    public var codec: Int

    public init(
        capturedAtMs: Int64? = nil, deviceId: String, deviceName: String?,
        codec: Int
    ) {
        self.capturedAtMs = capturedAtMs
        self.deviceId = deviceId
        self.deviceName = deviceName
        self.codec = codec
    }
}

public struct RecordingJournalRecord: Sendable, Hashable, Identifiable {
    public var capturedAtMs: Int64?
    public var handle: String
    public var captureId: String
    public var deviceId: String
    public var deviceName: String?
    public var codec: Int
    public var sessionId: String?
    public var entries: [String]

    public var id: String { handle }

    public init(
        capturedAtMs: Int64? = nil, handle: String, captureId: String,
        deviceId: String, deviceName: String?, codec: Int,
        sessionId: String?, entries: [String]
    ) {
        self.capturedAtMs = capturedAtMs
        self.handle = handle
        self.captureId = captureId
        self.deviceId = deviceId
        self.deviceName = deviceName
        self.codec = codec
        self.sessionId = sessionId
        self.entries = entries
    }
}

// MARK: - Device transport vocabulary

public enum BluetoothState: String, Sendable, Hashable {
    case unknown
    case poweredOff
    case poweredOn
    case unauthorized
}

public enum CaptureMode: String, Sendable, Hashable {
    case stream
    case batch
}

public enum ConnectionPhase: String, Sendable, Hashable {
    case disconnected
    case connecting
    case connected
}

// MARK: - Cloud account surface (Settings / Connectors)

public struct CloudApp: Sendable, Hashable, Identifiable {
    public var id: String
    public var name: String
    public var description: String
    public var category: String
    public var author: String
    public var enabled: Bool
    public var uid: String?
    public var isPrivate: Bool
    public var official: Bool
    public var installs: Int
    public var hasExternalIntegration: Bool
    public var connectedAccounts: [String]

    public init(
        id: String, name: String, description: String, category: String,
        author: String, enabled: Bool, uid: String?, isPrivate: Bool,
        official: Bool, installs: Int, hasExternalIntegration: Bool,
        connectedAccounts: [String]
    ) {
        self.id = id
        self.name = name
        self.description = description
        self.category = category
        self.author = author
        self.enabled = enabled
        self.uid = uid
        self.isPrivate = isPrivate
        self.official = official
        self.installs = installs
        self.hasExternalIntegration = hasExternalIntegration
        self.connectedAccounts = connectedAccounts
    }
}

public struct ConnectorsSnapshot: Sendable, Hashable {
    public var apps: [CloudApp]
    public var enabledIds: [String]?
    public var enabledError: String?
    public var ownerUid: String?

    public init(
        apps: [CloudApp], enabledIds: [String]?, enabledError: String?,
        ownerUid: String?
    ) {
        self.apps = apps
        self.enabledIds = enabledIds
        self.enabledError = enabledError
        self.ownerUid = ownerUid
    }
}

public struct CloudProfile: Sendable, Hashable {
    public var uid: String
    public var name: String?
    public var email: String?
    public var company: String?
    public var job: String?
    public var dataProtectionLevel: String?

    public init(
        uid: String, name: String?, email: String?, company: String?,
        job: String?, dataProtectionLevel: String?
    ) {
        self.uid = uid
        self.name = name
        self.email = email
        self.company = company
        self.job = job
        self.dataProtectionLevel = dataProtectionLevel
    }
}

public struct CloudSubscription: Sendable, Hashable {
    public var plan: String
    public var status: String
    public var transcriptionSecondsUsed: Int?
    public var transcriptionSecondsLimit: Int?

    public init(
        plan: String, status: String, transcriptionSecondsUsed: Int?,
        transcriptionSecondsLimit: Int?
    ) {
        self.plan = plan
        self.status = status
        self.transcriptionSecondsUsed = transcriptionSecondsUsed
        self.transcriptionSecondsLimit = transcriptionSecondsLimit
    }
}

public struct CloudWebhookStatus: Sendable, Hashable {
    public var type: String
    public var enabled: Bool?
    public var url: String?

    public init(type: String, enabled: Bool?, url: String?) {
        self.type = type
        self.enabled = enabled
        self.url = url
    }
}

public struct AccountSettingsSnapshot: Sendable, Hashable {
    public var profile: CloudProfile?
    public var profileError: String?
    public var subscription: CloudSubscription?
    public var subscriptionError: String?
    public var storeRecordingPermission: Bool?
    public var storeRecordingError: String?
    public var trainingOptedIn: Bool?
    public var trainingError: String?
    public var privateCloudSync: Bool?
    public var privateCloudSyncError: String?
    public var webhooks: [CloudWebhookStatus]?
    public var webhooksError: String?

    public init(
        profile: CloudProfile? = nil, profileError: String? = nil,
        subscription: CloudSubscription? = nil,
        subscriptionError: String? = nil,
        storeRecordingPermission: Bool? = nil,
        storeRecordingError: String? = nil, trainingOptedIn: Bool? = nil,
        trainingError: String? = nil, privateCloudSync: Bool? = nil,
        privateCloudSyncError: String? = nil,
        webhooks: [CloudWebhookStatus]? = nil, webhooksError: String? = nil
    ) {
        self.profile = profile
        self.profileError = profileError
        self.subscription = subscription
        self.subscriptionError = subscriptionError
        self.storeRecordingPermission = storeRecordingPermission
        self.storeRecordingError = storeRecordingError
        self.trainingOptedIn = trainingOptedIn
        self.trainingError = trainingError
        self.privateCloudSync = privateCloudSync
        self.privateCloudSyncError = privateCloudSyncError
        self.webhooks = webhooks
        self.webhooksError = webhooksError
    }
}

// MARK: - Shared date helpers

/// Minimal ISO-8601 timestamp reader (`YYYY-MM-DDTHH:MM:SS[.fff]Z` and
/// numeric epochs), sufficient for backend projection timestamps and
/// independent of platform date-parsing quirks.
public enum ISO8601Reader {
    /// Returns epoch seconds (fractional) for an ISO string, or nil.
    public static func epochSeconds(_ value: String) -> Double? {
        let bytes = Array(value.utf8)
        // Numeric epoch passthrough (seconds or milliseconds heuristics are
        // the caller's concern; projections carry ISO strings).
        if !bytes.isEmpty,
            bytes.allSatisfy({ ($0 >= 48 && $0 <= 57) || $0 == 46 }),
            let numeric = Double(value), numeric > 0
        {
            return numeric > 1_000_000_000_000 ? numeric / 1000 : numeric
        }
        let chars = bytes
        // YYYY-MM-DDTHH:MM:SS at minimum (19 chars).
        guard chars.count >= 19 else { return nil }
        func digits(_ range: ClosedRange<Int>) -> Int? {
            var result = 0
            for index in range {
                let byte = chars[index]
                guard byte >= 48, byte <= 57 else { return nil }
                result = result * 10 + Int(byte - 48)
            }
            return result
        }
        guard
            chars[4] == 45, chars[7] == 45,
            chars[10] == 84 || chars[10] == 116 || chars[10] == 32,
            chars[13] == 58, chars[16] == 58,
            let year = digits(0...3), let month = digits(5...6),
            let day = digits(8...9), let hour = digits(11...12),
            let minute = digits(14...15), let second = digits(17...18)
        else { return nil }
        var fractional = 0.0
        if chars.count > 19, chars[19] == 46 {
            var scale = 0.1
            var index = 20
            while index < chars.count, chars[index] >= 48, chars[index] <= 57 {
                fractional += Double(chars[index] - 48) * scale
                scale /= 10
                index += 1
            }
        }
        var components = DateComponents()
        components.year = year
        components.month = month
        components.day = day
        components.hour = hour
        components.minute = minute
        components.second = second
        var calendar = Calendar(identifier: Calendar.Identifier.gregorian)
        guard let utc = TimeZone(identifier: "UTC") else { return nil }
        calendar.timeZone = utc
        guard let date = calendar.date(from: components) else { return nil }
        return date.timeIntervalSince1970 + fractional
    }
}

/// Port of `conversationGroupLabel` from `desktopReadClient.ts`:
/// Today / Yesterday / localized date for older items.
public func conversationGroupLabel(
    _ value: String, nowEpochMilliseconds: Int64
) -> String {
    guard let seconds = ISO8601Reader.epochSeconds(value) else { return value }
    func utcDay(_ milliseconds: Int64) -> Int64 {
        Int64(floor(Double(milliseconds) / 86_400_000.0))
    }
    let nowDay = utcDay(nowEpochMilliseconds)
    let dateDay = utcDay(Int64(seconds * 1000))
    let difference = nowDay - dateDay
    if difference == 0 { return "Today" }
    if difference == 1 { return "Yesterday" }
    let formatter = DateFormatter()
    formatter.timeStyle = DateFormatter.Style.none
    formatter.dateStyle = DateFormatter.Style.medium
    return formatter.string(from: Date(timeIntervalSince1970: seconds))
}
