import Foundation
import GRDB

// MARK: - Transcription Session Status

/// Status of a transcription session (upload/sync status)
enum TranscriptionSessionStatus: String, Codable, CaseIterable {
    case recording = "recording"
    case pendingUpload = "pending_upload"
    case uploading = "uploading"
    case completed = "completed"
    case failed = "failed"
}

/// Conversation processing status (from backend)
/// Matches ConversationStatus in APIClient.swift
enum LocalConversationStatus: String, Codable, CaseIterable {
    case inProgress = "in_progress"
    case processing = "processing"
    case merging = "merging"
    case completed = "completed"
    case failed = "failed"
}

// MARK: - Transcription Session Record

/// Database record for transcription recording sessions
/// Stores metadata about a transcription session for crash recovery and retry
/// Also serves as local cache for conversations synced from backend
struct TranscriptionSessionRecord: Codable, FetchableRecord, PersistableRecord, Identifiable {
    var id: Int64?
    var startedAt: Date
    var finishedAt: Date?
    var source: String                    // 'desktop', 'omi', etc.
    var language: String
    var timezone: String
    var inputDeviceName: String?
    var status: TranscriptionSessionStatus  // Upload/sync status
    var retryCount: Int
    var lastError: String?
    var backendId: String?                // Server conversation ID
    var backendSynced: Bool
    var createdAt: Date
    var updatedAt: Date

    // MARK: - Structured Data (from ServerConversation.Structured)
    var title: String?
    var overview: String?
    var emoji: String?
    var category: String?
    var actionItemsJson: String?          // JSON-encoded [ActionItem]
    var eventsJson: String?               // JSON-encoded [Event]

    // MARK: - Additional Conversation Data
    var geolocationJson: String?          // JSON-encoded Geolocation
    var photosJson: String?               // JSON-encoded [ConversationPhoto]
    var appsResultsJson: String?          // JSON-encoded [AppResponse]

    // MARK: - Conversation Status & Flags
    var conversationStatus: LocalConversationStatus  // Backend processing status
    var discarded: Bool
    var deleted: Bool
    var isLocked: Bool
    var starred: Bool
    var folderId: String?

    static let databaseTableName = "transcription_sessions"

    // MARK: - Initialization

    init(
        id: Int64? = nil,
        startedAt: Date = Date(),
        finishedAt: Date? = nil,
        source: String,
        language: String = "en",
        timezone: String = "UTC",
        inputDeviceName: String? = nil,
        status: TranscriptionSessionStatus = .recording,
        retryCount: Int = 0,
        lastError: String? = nil,
        backendId: String? = nil,
        backendSynced: Bool = false,
        createdAt: Date = Date(),
        updatedAt: Date = Date(),
        // Structured data
        title: String? = nil,
        overview: String? = nil,
        emoji: String? = nil,
        category: String? = nil,
        actionItemsJson: String? = nil,
        eventsJson: String? = nil,
        // Additional data
        geolocationJson: String? = nil,
        photosJson: String? = nil,
        appsResultsJson: String? = nil,
        // Status & flags
        conversationStatus: LocalConversationStatus = .inProgress,
        discarded: Bool = false,
        deleted: Bool = false,
        isLocked: Bool = false,
        starred: Bool = false,
        folderId: String? = nil
    ) {
        self.id = id
        self.startedAt = startedAt
        self.finishedAt = finishedAt
        self.source = source
        self.language = language
        self.timezone = timezone
        self.inputDeviceName = inputDeviceName
        self.status = status
        self.retryCount = retryCount
        self.lastError = lastError
        self.backendId = backendId
        self.backendSynced = backendSynced
        self.createdAt = createdAt
        self.updatedAt = updatedAt
        // Structured data
        self.title = title
        self.overview = overview
        self.emoji = emoji
        self.category = category
        self.actionItemsJson = actionItemsJson
        self.eventsJson = eventsJson
        // Additional data
        self.geolocationJson = geolocationJson
        self.photosJson = photosJson
        self.appsResultsJson = appsResultsJson
        // Status & flags
        self.conversationStatus = conversationStatus
        self.discarded = discarded
        self.deleted = deleted
        self.isLocked = isLocked
        self.starred = starred
        self.folderId = folderId
    }

    // MARK: - Persistence Callbacks

    mutating func didInsert(_ inserted: InsertionSuccess) {
        id = inserted.rowID
    }

    // MARK: - Relationships

    static let segments = hasMany(TranscriptionSegmentRecord.self)

    var segments: QueryInterfaceRequest<TranscriptionSegmentRecord> {
        request(for: TranscriptionSessionRecord.segments)
    }

    // MARK: - Computed Properties

    /// Check if this session can be retried (under max retry count)
    var canRetry: Bool {
        retryCount < 5
    }

    /// Calculate backoff delay in seconds based on retry count
    var retryBackoffSeconds: TimeInterval {
        // Exponential backoff: 2^retryCount minutes
        // 0 retries = 1 min, 1 = 2 min, 2 = 4 min, 3 = 8 min, 4 = 16 min
        return pow(2.0, Double(retryCount)) * 60.0
    }

    /// Check if enough time has passed since last update for retry
    func isReadyForRetry(now: Date = Date()) -> Bool {
        guard canRetry else { return false }
        let timeSinceUpdate = now.timeIntervalSince(updatedAt)
        return timeSinceUpdate >= retryBackoffSeconds
    }
}

// MARK: - Transcription Segment Record

/// Database record for individual transcription segments
/// Stores the actual transcribed text with speaker and timing info
/// Also serves as local cache for transcript segments synced from backend
struct TranscriptionSegmentRecord: Codable, FetchableRecord, PersistableRecord, Identifiable {
    var id: Int64?
    var sessionId: Int64
    var speaker: Int                      // Speaker ID (0, 1, 2, etc.)
    var text: String
    var startTime: Double
    var endTime: Double
    var segmentOrder: Int
    var createdAt: Date

    // MARK: - Backend Segment Data (from TranscriptSegment)
    var segmentId: String?                // Backend segment ID (different from local id)
    var speakerLabel: String?             // Speaker label (e.g., "SPEAKER_00")
    var isUser: Bool                      // Whether this segment is from the user
    var personId: String?                 // Associated person ID (if identified)

    static let databaseTableName = "transcription_segments"

    // MARK: - Initialization

    init(
        id: Int64? = nil,
        sessionId: Int64,
        speaker: Int,
        text: String,
        startTime: Double,
        endTime: Double,
        segmentOrder: Int,
        createdAt: Date = Date(),
        // Backend segment data
        segmentId: String? = nil,
        speakerLabel: String? = nil,
        isUser: Bool = false,
        personId: String? = nil
    ) {
        self.id = id
        self.sessionId = sessionId
        self.speaker = speaker
        self.text = text
        self.startTime = startTime
        self.endTime = endTime
        self.segmentOrder = segmentOrder
        self.createdAt = createdAt
        // Backend segment data
        self.segmentId = segmentId
        self.speakerLabel = speakerLabel
        self.isUser = isUser
        self.personId = personId
    }

    // MARK: - Persistence Callbacks

    mutating func didInsert(_ inserted: InsertionSuccess) {
        id = inserted.rowID
    }

    // MARK: - Relationships

    static let session = belongsTo(TranscriptionSessionRecord.self)

    var session: QueryInterfaceRequest<TranscriptionSessionRecord> {
        request(for: TranscriptionSegmentRecord.session)
    }
}

// MARK: - Session with Segments

/// Combined session and segments data for upload
struct TranscriptionSessionWithSegments {
    let session: TranscriptionSessionRecord
    let segments: [TranscriptionSegmentRecord]

    /// Check if this session has enough content to upload
    var hasContent: Bool {
        !segments.isEmpty
    }

    /// Total word count across all segments
    var wordCount: Int {
        segments.reduce(0) { $0 + $1.text.split(separator: " ").count }
    }

    /// Total duration in seconds
    var durationSeconds: TimeInterval? {
        guard let start = session.startedAt as Date?,
              let end = session.finishedAt else { return nil }
        return end.timeIntervalSince(start)
    }
}

// MARK: - Transcription Storage Error

/// Errors for TranscriptionStorage operations
enum TranscriptionStorageError: LocalizedError {
    case databaseNotInitialized
    case sessionNotFound
    case invalidState(String)
    case uploadFailed(String)

    var errorDescription: String? {
        switch self {
        case .databaseNotInitialized:
            return "Transcription storage database is not initialized"
        case .sessionNotFound:
            return "Transcription session not found"
        case .invalidState(let message):
            return "Invalid session state: \(message)"
        case .uploadFailed(let message):
            return "Upload failed: \(message)"
        }
    }
}

// MARK: - ServerConversation Conversion

extension TranscriptionSessionRecord {
    /// Create a local record from a ServerConversation
    /// Used when syncing conversations from backend to local storage
    static func from(_ conversation: ServerConversation) -> TranscriptionSessionRecord {
        let encoder = JSONEncoder()

        // Encode structured data as JSON
        let actionItemsJson = try? String(data: encoder.encode(conversation.structured.actionItems), encoding: .utf8)
        let eventsJson = try? String(data: encoder.encode(conversation.structured.events), encoding: .utf8)
        let geolocationJson = try? String(data: encoder.encode(conversation.geolocation), encoding: .utf8)
        let photosJson = try? String(data: encoder.encode(conversation.photos), encoding: .utf8)
        let appsResultsJson = try? String(data: encoder.encode(conversation.appsResults), encoding: .utf8)

        // Convert ConversationStatus to LocalConversationStatus
        let localStatus: LocalConversationStatus
        switch conversation.status {
        case .inProgress: localStatus = .inProgress
        case .processing: localStatus = .processing
        case .merging: localStatus = .merging
        case .completed: localStatus = .completed
        case .failed: localStatus = .failed
        }

        return TranscriptionSessionRecord(
            startedAt: conversation.startedAt ?? conversation.createdAt,
            finishedAt: conversation.finishedAt,
            source: conversation.source?.rawValue ?? "unknown",
            language: conversation.language ?? "en",
            timezone: "UTC",
            inputDeviceName: conversation.inputDeviceName,
            status: .completed,  // Synced from backend = already completed
            retryCount: 0,
            lastError: nil,
            backendId: conversation.id,
            backendSynced: true,
            createdAt: conversation.createdAt,
            updatedAt: Date(),
            title: conversation.structured.title,
            overview: conversation.structured.overview,
            emoji: conversation.structured.emoji,
            category: conversation.structured.category,
            actionItemsJson: actionItemsJson,
            eventsJson: eventsJson,
            geolocationJson: geolocationJson,
            photosJson: photosJson,
            appsResultsJson: appsResultsJson,
            conversationStatus: localStatus,
            discarded: conversation.discarded,
            deleted: conversation.deleted,
            isLocked: conversation.isLocked,
            starred: conversation.starred,
            folderId: conversation.folderId
        )
    }

    /// Update this record from a ServerConversation (preserving local id)
    mutating func updateFrom(_ conversation: ServerConversation) {
        let encoder = JSONEncoder()

        // Update timestamps — use server's latest timestamp so local mutations
        // (which set updatedAt = Date()) aren't overwritten by stale sync data
        self.startedAt = conversation.startedAt ?? conversation.createdAt
        self.finishedAt = conversation.finishedAt
        self.updatedAt = conversation.finishedAt ?? conversation.startedAt ?? conversation.createdAt

        // Update metadata
        self.source = conversation.source?.rawValue ?? self.source
        self.language = conversation.language ?? self.language
        self.inputDeviceName = conversation.inputDeviceName

        // Update structured data
        self.title = conversation.structured.title
        self.overview = conversation.structured.overview
        self.emoji = conversation.structured.emoji
        self.category = conversation.structured.category
        self.actionItemsJson = try? String(data: encoder.encode(conversation.structured.actionItems), encoding: .utf8)
        self.eventsJson = try? String(data: encoder.encode(conversation.structured.events), encoding: .utf8)

        // Update additional data
        self.geolocationJson = try? String(data: encoder.encode(conversation.geolocation), encoding: .utf8)
        self.photosJson = try? String(data: encoder.encode(conversation.photos), encoding: .utf8)
        self.appsResultsJson = try? String(data: encoder.encode(conversation.appsResults), encoding: .utf8)

        // Update status & flags
        switch conversation.status {
        case .inProgress: self.conversationStatus = .inProgress
        case .processing: self.conversationStatus = .processing
        case .merging: self.conversationStatus = .merging
        case .completed: self.conversationStatus = .completed
        case .failed: self.conversationStatus = .failed
        }
        self.discarded = conversation.discarded
        self.deleted = conversation.deleted
        self.isLocked = conversation.isLocked
        self.starred = conversation.starred
        self.folderId = conversation.folderId

        // Mark as synced
        self.backendId = conversation.id
        self.backendSynced = true
    }
}

// MARK: - TableDocumented

extension TranscriptionSessionRecord: TableDocumented {
    static var tableDescription: String { ChatPrompts.tableAnnotations["transcription_sessions"]! }
    static var columnDescriptions: [String: String] { ChatPrompts.columnAnnotations["transcription_sessions"] ?? [:] }
}

extension TranscriptionSegmentRecord: TableDocumented {
    static var tableDescription: String { ChatPrompts.tableAnnotations["transcription_segments"]! }
    static var columnDescriptions: [String: String] { ChatPrompts.columnAnnotations["transcription_segments"] ?? [:] }
}

extension TranscriptionSegmentRecord {
    /// Create a local record from a TranscriptSegment
    static func from(_ segment: TranscriptSegment, sessionId: Int64, segmentOrder: Int) -> TranscriptionSegmentRecord {
        return TranscriptionSegmentRecord(
            sessionId: sessionId,
            speaker: segment.speakerId,
            text: segment.text,
            startTime: segment.start,
            endTime: segment.end,
            segmentOrder: segmentOrder,
            segmentId: segment.id,
            speakerLabel: segment.speaker,
            isUser: segment.isUser,
            personId: segment.personId
        )
    }

    /// Convert back to TranscriptSegment for UI display
    func toTranscriptSegment() -> TranscriptSegment {
        return TranscriptSegment(
            id: segmentId ?? UUID().uuidString,
            text: text,
            speaker: speakerLabel,
            isUser: isUser,
            personId: personId,
            start: startTime,
            end: endTime
        )
    }
}

// MARK: - Convert to ServerConversation

extension TranscriptionSessionRecord {
    /// Convert local record back to ServerConversation for UI display
    /// Requires segments to be passed in (fetched separately)
    func toServerConversation(segments: [TranscriptionSegmentRecord]) -> ServerConversation? {
        guard let backendId = backendId else { return nil }

        let decoder = JSONDecoder()

        // Decode JSON fields
        let actionItems: [ActionItem] = (actionItemsJson?.data(using: .utf8))
            .flatMap { try? decoder.decode([ActionItem].self, from: $0) } ?? []
        let events: [Event] = (eventsJson?.data(using: .utf8))
            .flatMap { try? decoder.decode([Event].self, from: $0) } ?? []
        let geolocation: Geolocation? = (geolocationJson?.data(using: .utf8))
            .flatMap { try? decoder.decode(Geolocation.self, from: $0) }
        let photos: [ConversationPhoto] = (photosJson?.data(using: .utf8))
            .flatMap { try? decoder.decode([ConversationPhoto].self, from: $0) } ?? []
        let appsResults: [AppResponse] = (appsResultsJson?.data(using: .utf8))
            .flatMap { try? decoder.decode([AppResponse].self, from: $0) } ?? []

        // Convert conversation status
        let status: ConversationStatus
        switch conversationStatus {
        case .inProgress: status = .inProgress
        case .processing: status = .processing
        case .merging: status = .merging
        case .completed: status = .completed
        case .failed: status = .failed
        }

        // Convert segments
        let transcriptSegments = segments.map { $0.toTranscriptSegment() }

        return ServerConversation(
            id: backendId,
            createdAt: createdAt,
            startedAt: startedAt,
            finishedAt: finishedAt,
            structured: Structured(
                title: title ?? "",
                overview: overview ?? "",
                emoji: emoji ?? "",
                category: category ?? "other",
                actionItems: actionItems,
                events: events
            ),
            transcriptSegments: transcriptSegments,
            geolocation: geolocation,
            photos: photos,
            appsResults: appsResults,
            source: ConversationSource(rawValue: source),
            language: language,
            status: status,
            discarded: discarded,
            deleted: deleted,
            isLocked: isLocked,
            starred: starred,
            folderId: folderId,
            inputDeviceName: inputDeviceName
        )
    }
}
