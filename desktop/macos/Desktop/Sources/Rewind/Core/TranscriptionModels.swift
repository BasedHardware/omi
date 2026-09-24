import Foundation
@preconcurrency import GRDB

// MARK: - Transcription Session Status

/// Status of a transcription session (upload/sync status)
enum TranscriptionSessionStatus: String, Codable, CaseIterable {
  case recording = "recording"
  case pendingUpload = "pending_upload"
  case uploading = "uploading"
  case completed = "completed"
  case failed = "failed"
}

enum TranscriptionFinalizationStrategy: String, Codable, CaseIterable {
  case localSegments = "local_segments"
  case cloudReconcile = "cloud_reconcile"
}

/// The logical kind of conversation captured by one local recording session.
/// This is persisted at session creation so later retries do not have to infer
/// meeting provenance from whichever finalization event happened to win.
enum TranscriptionConversationRole: String, Codable, CaseIterable {
  case ambient
  case meeting
}

enum TranscriptionFinalizationReason: String, Codable, CaseIterable {
  case userStop = "user_stop"
  case finishAndContinue = "finish_and_continue"
  case meetingStarted = "meeting_started"
  case meetingEnded = "meeting_ended"
  case maxDurationRotation = "max_duration_rotation"
  case crashRecovery = "crash_recovery"
  case retry = "retry"
  /// Audio Recording mode switched to Off (user or settings sync).
  case recordingDisabled = "recording_disabled"
  /// System sleep tore the session down; the wake handler re-arms it.
  case systemSleep = "system_sleep"
  /// App termination teardown.
  case appTerminated = "app_terminated"
  /// `freemium_threshold_reached` admission stop.
  case paywall = "paywall"
  /// Microphone could not start or lost authorization mid-session.
  case microphoneUnavailable = "microphone_unavailable"
  /// BLE audio source had no live connection when capture armed.
  case deviceUnavailable = "device_unavailable"
  /// Repeated silent-mic recoveries failed and the session was stopped.
  case silentMicExhausted = "silent_mic_exhausted"
  /// A meeting-boundary conversation rotation failed and the session was
  /// torn down rather than left half-rotated.
  case rotationFailed = "rotation_failed"
  /// Session stopped to switch STT engines (local↔cloud fallback restart).
  case sttFallback = "stt_fallback"
  /// Settings-driven capture restart (e.g. input-device change) stopped the
  /// old session before re-arming.
  case settingsChange = "settings_change"

  /// Reasons that name a forced termination rather than an intended boundary:
  /// the attempt died because capture could not continue, so the outcome funnel
  /// must count it as `error` even if the call site forgot `noteErrorTerminal()`.
  var isForcedTermination: Bool {
    switch self {
    case .paywall, .microphoneUnavailable, .deviceUnavailable, .silentMicExhausted,
      .rotationFailed, .sttFallback:
      return true
    case .userStop, .finishAndContinue, .meetingStarted, .meetingEnded, .maxDurationRotation,
      .crashRecovery, .retry, .recordingDisabled, .systemSleep, .appTerminated, .settingsChange:
      return false
    }
  }
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

enum ConversationCacheCompleteness: String, Codable, CaseIterable {
  case list
  case detail
}

// MARK: - Transcription Session Record

/// Database record for transcription recording sessions
/// Stores metadata about a transcription session for crash recovery and retry
/// Also serves as local cache for conversations synced from backend
struct TranscriptionSessionRecord: Codable, FetchableRecord, PersistableRecord, Identifiable {
  var id: Int64?
  var startedAt: Date
  var finishedAt: Date?
  var source: String  // 'desktop', 'omi', etc.
  var language: String
  var timezone: String
  var inputDeviceName: String?
  var status: TranscriptionSessionStatus  // Upload/sync status
  var retryCount: Int
  var lastError: String?
  var backendId: String?  // Server conversation ID
  var clientConversationId: String?  // Client-generated stable conversation ID for listen reconciliation
  var backendSynced: Bool
  var createdAt: Date
  var updatedAt: Date
  var serverUpdatedAt: Date?
  var cacheCompleteness: ConversationCacheCompleteness
  /// Role is captured when the session starts. Older rows decode as ambient
  /// through the migration default and therefore remain backward compatible.
  var conversationRole: TranscriptionConversationRole
  var finalizationStrategy: TranscriptionFinalizationStrategy?
  var finalizationReason: TranscriptionFinalizationReason?
  var finalizationStartedAt: Date?
  var finalizationCompletedAt: Date?
  /// Opaque id of the armed capture attempt this session belongs to (see
  /// `CaptureAttemptOutcomeState`). Nullable: pre-instrumentation rows and the
  /// hermetic automation session have no attempt identity.
  var captureAttemptId: String?

  // MARK: - Structured Data (from ServerConversation.Structured)
  var title: String?
  var overview: String?
  var emoji: String?
  var category: String?
  var actionItemsJson: String?  // JSON-encoded [ActionItem]
  var eventsJson: String?  // JSON-encoded [Event]
  var sectionsJson: String?  // JSON-encoded [SummarySection]
  var localSummaryJson: String?  // Selected display attribution; never the upload/retry blob
  var captureGroupJson: String?  // Server-owned cross-surface event membership (ServerCaptureGroup)

  // MARK: - Additional Conversation Data
  var geolocationJson: String?  // JSON-encoded Geolocation
  var photosJson: String?  // JSON-encoded [ConversationPhoto]
  var appsResultsJson: String?  // JSON-encoded [AppResponse]
  /// Stored `client_processing` JSON. Retry sends this blob; it is never regenerated.
  var clientProcessingJson: String?

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
    clientConversationId: String? = nil,
    backendSynced: Bool = false,
    createdAt: Date = Date(),
    updatedAt: Date = Date(),
    serverUpdatedAt: Date? = nil,
    cacheCompleteness: ConversationCacheCompleteness = .list,
    conversationRole: TranscriptionConversationRole = .ambient,
    finalizationStrategy: TranscriptionFinalizationStrategy? = nil,
    finalizationReason: TranscriptionFinalizationReason? = nil,
    finalizationStartedAt: Date? = nil,
    finalizationCompletedAt: Date? = nil,
    captureAttemptId: String? = nil,
    // Structured data
    title: String? = nil,
    overview: String? = nil,
    emoji: String? = nil,
    category: String? = nil,
    actionItemsJson: String? = nil,
    eventsJson: String? = nil,
    sectionsJson: String? = nil,
    localSummaryJson: String? = nil,
    captureGroupJson: String? = nil,
    // Additional data
    geolocationJson: String? = nil,
    photosJson: String? = nil,
    appsResultsJson: String? = nil,
    clientProcessingJson: String? = nil,
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
    self.clientConversationId = clientConversationId
    self.backendSynced = backendSynced
    self.createdAt = createdAt
    self.updatedAt = updatedAt
    self.serverUpdatedAt = serverUpdatedAt
    self.cacheCompleteness = cacheCompleteness
    self.conversationRole = conversationRole
    self.finalizationStrategy = finalizationStrategy
    self.finalizationReason = finalizationReason
    self.finalizationStartedAt = finalizationStartedAt
    self.finalizationCompletedAt = finalizationCompletedAt
    self.captureAttemptId = captureAttemptId
    // Structured data
    self.title = title
    self.overview = overview
    self.emoji = emoji
    self.category = category
    self.actionItemsJson = actionItemsJson
    self.eventsJson = eventsJson
    self.sectionsJson = sectionsJson
    self.localSummaryJson = localSummaryJson
    self.captureGroupJson = captureGroupJson
    // Additional data
    self.geolocationJson = geolocationJson
    self.photosJson = photosJson
    self.appsResultsJson = appsResultsJson
    self.clientProcessingJson = clientProcessingJson
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

  /// True once the local session has been associated with a backend conversation.
  var hasSyncedBackendIdentity: Bool {
    backendSynced || !(backendId?.isEmpty ?? true)
  }

  /// Whether a completion event can attach this backend conversation ID.
  func canAcceptCompletion(backendId incomingBackendId: String) -> Bool {
    guard let existingBackendId = backendId, !existingBackendId.isEmpty else {
      return true
    }
    return existingBackendId == incomingBackendId
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
  var speaker: Int  // Speaker ID (0, 1, 2, etc.)
  var text: String
  var startTime: Double
  var endTime: Double
  var segmentOrder: Int
  var createdAt: Date

  // MARK: - Backend Segment Data (from TranscriptSegment)
  var segmentId: String?  // Backend segment ID (different from local id)
  var speakerLabel: String?  // Speaker label (e.g., "SPEAKER_00")
  var isUser: Bool  // Whether this segment is from the user
  var personId: String?  // Associated person ID (if identified)
  var translationsJson: String?  // JSON-encoded [TranscriptTranslation]

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
    personId: String? = nil,
    translationsJson: String? = nil
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
    self.translationsJson = translationsJson
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

  var hasSpeakerAssignment: Bool {
    isUser || personId != nil
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
      let end = session.finishedAt
    else { return nil }
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
    let sectionsJson = try? String(data: encoder.encode(conversation.structured.sections), encoding: .utf8)
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
      serverUpdatedAt: conversation.updatedAt,
      cacheCompleteness: conversation.transcriptSegmentsIncluded ? .detail : .list,
      conversationRole: .ambient,
      finalizationStrategy: nil,
      finalizationReason: nil,
      finalizationStartedAt: nil,
      finalizationCompletedAt: localStatus == .completed ? (conversation.finishedAt ?? Date()) : nil,
      title: conversation.structured.title,
      overview: conversation.structured.overview,
      emoji: conversation.structured.emoji,
      category: conversation.structured.category,
      actionItemsJson: actionItemsJson,
      eventsJson: eventsJson,
      sectionsJson: sectionsJson,
      localSummaryJson: conversation.localSummary.flatMap { try? String(data: encoder.encode($0), encoding: .utf8) },
      captureGroupJson: conversation.captureGroup.flatMap { try? String(data: encoder.encode($0), encoding: .utf8) },
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

  /// Update this record from a versioned server snapshot while preserving its local id.
  mutating func updateFrom(_ conversation: ServerConversation) {
    let encoder = JSONEncoder()

    // `updatedAt` is local cache bookkeeping. Server freshness is tracked
    // independently by `serverUpdatedAt` and never inferred from recording time.
    self.startedAt = conversation.startedAt ?? conversation.createdAt
    self.finishedAt = conversation.finishedAt
    self.updatedAt = Date()
    self.serverUpdatedAt = conversation.updatedAt ?? self.serverUpdatedAt
    if conversation.transcriptSegmentsIncluded {
      self.cacheCompleteness = .detail
    }

    // Update metadata
    self.source = conversation.source?.rawValue ?? self.source
    self.language = conversation.language ?? self.language
    self.inputDeviceName = conversation.inputDeviceName

    updateSummary(from: conversation)
    // Membership is server-owned and independent of the summary's projection rules.
    self.captureGroupJson = conversation.captureGroup.flatMap { try? String(data: encoder.encode($0), encoding: .utf8) }

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

  private mutating func updateSummary(from conversation: ServerConversation) {
    let encoder = JSONEncoder()
    self.title = conversation.structured.title
    self.overview = conversation.structured.overview
    self.emoji = conversation.structured.emoji
    self.category = conversation.structured.category
    self.actionItemsJson = try? String(data: encoder.encode(conversation.structured.actionItems), encoding: .utf8)
    self.eventsJson = try? String(data: encoder.encode(conversation.structured.events), encoding: .utf8)
    self.sectionsJson = try? String(data: encoder.encode(conversation.structured.sections), encoding: .utf8)

    self.localSummaryJson = conversation.localSummary.flatMap { try? String(data: encoder.encode($0), encoding: .utf8) }

  }

  /// Enrich an unversioned or older projection without allowing it to
  /// overwrite fields from a newer canonical snapshot.
  mutating func hydrateMissingFields(from conversation: ServerConversation) {
    let encoder = JSONEncoder()
    if canHydrateSummary(from: conversation), conversation.localSummary != nil {
      updateSummary(from: conversation)
    } else if canHydrateSummary(from: conversation) {
      if Self.isEmpty(title), !conversation.structured.title.isEmpty {
        title = conversation.structured.title
      }
      if Self.isEmpty(overview), !conversation.structured.overview.isEmpty {
        overview = conversation.structured.overview
      }
      if Self.isEmpty(emoji), !conversation.structured.emoji.isEmpty {
        emoji = conversation.structured.emoji
      }
      if Self.isDefaultCategory(category), !Self.isDefaultCategory(conversation.structured.category) {
        category = conversation.structured.category
      }
      if Self.isEmptyJsonCollection(actionItemsJson), !conversation.structured.actionItems.isEmpty {
        actionItemsJson = try? String(
          data: encoder.encode(conversation.structured.actionItems),
          encoding: .utf8
        )
      }
      if Self.isEmptyJsonCollection(eventsJson), !conversation.structured.events.isEmpty {
        eventsJson = try? String(data: encoder.encode(conversation.structured.events), encoding: .utf8)
      }
      // Nil identifies a pre-migration cache entry. An encoded empty array is an
      // authoritative absence and must not be refilled by an older response.
      if sectionsJson == nil, !conversation.structured.sections.isEmpty {
        sectionsJson = try? String(data: encoder.encode(conversation.structured.sections), encoding: .utf8)
      }
    }
    if Self.isEmptyJsonCollection(photosJson), !conversation.photos.isEmpty {
      photosJson = try? String(data: encoder.encode(conversation.photos), encoding: .utf8)
    }
    if Self.isEmptyJsonCollection(appsResultsJson), !conversation.appsResults.isEmpty {
      appsResultsJson = try? String(data: encoder.encode(conversation.appsResults), encoding: .utf8)
    }
    if conversation.transcriptSegmentsIncluded {
      cacheCompleteness = .detail
    }
    updatedAt = Date()
    backendId = conversation.id
    backendSynced = true
  }

  /// True when the server response can fill at least one empty local server-owned field.
  func hasHydratableServerFields(from conversation: ServerConversation) -> Bool {
    guard backendSynced, backendId == conversation.id else { return false }
    return canHydrateSummary(from: conversation)
      && (Self.isEmpty(title) && !conversation.structured.title.isEmpty
        || Self.isEmpty(overview) && !conversation.structured.overview.isEmpty
        || Self.isEmpty(emoji) && !conversation.structured.emoji.isEmpty
        || Self.isDefaultCategory(category) && !Self.isDefaultCategory(conversation.structured.category)
        || Self.isEmptyJsonCollection(actionItemsJson) && !conversation.structured.actionItems.isEmpty
        || Self.isEmptyJsonCollection(eventsJson) && !conversation.structured.events.isEmpty
        || sectionsJson == nil && !conversation.structured.sections.isEmpty)
      || Self.isEmptyJsonCollection(photosJson) && !conversation.photos.isEmpty
      || Self.isEmptyJsonCollection(appsResultsJson) && !conversation.appsResults.isEmpty
  }

  /// Older/unversioned snapshots cannot mix projected and canonical summaries. A genuinely
  /// empty, unversioned shell can still hydrate; a revision-bearing summary is authoritative.
  private func canHydrateSummary(from conversation: ServerConversation) -> Bool {
    guard localSummaryJson != nil || conversation.localSummary != nil else { return true }
    return serverUpdatedAt == nil && Self.isEmpty(title) && Self.isEmpty(overview) && Self.isDefaultCategory(category)
      && Self.isEmptyJsonCollection(sectionsJson) && Self.isEmptyJsonCollection(actionItemsJson)
      && Self.isEmptyJsonCollection(eventsJson)
  }

  private static func isEmpty(_ value: String?) -> Bool {
    value?.isEmpty ?? true
  }

  private static func isDefaultCategory(_ value: String?) -> Bool {
    isEmpty(value) || value == "other"
  }

  private static func isEmptyJsonCollection(_ value: String?) -> Bool {
    guard let value, !value.isEmpty else { return true }
    return value.trimmingCharacters(in: .whitespacesAndNewlines) == "[]"
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
    var translationsJson: String?
    if !segment.translations.isEmpty,
      let data = try? JSONEncoder().encode(segment.translations)
    {
      translationsJson = String(data: data, encoding: .utf8)
    }
    return TranscriptionSegmentRecord(
      sessionId: sessionId,
      speaker: segment.speakerId,
      text: segment.text,
      startTime: segment.start,
      endTime: segment.end,
      segmentOrder: segmentOrder,
      segmentId: segment.backendId,
      speakerLabel: segment.speaker,
      isUser: segment.isUser,
      personId: segment.personId,
      translationsJson: translationsJson
    )
  }

  /// Convert back to TranscriptSegment for UI display.
  func toTranscriptSegment() -> TranscriptSegment {
    var translations: [TranscriptTranslation] = []
    if let json = translationsJson, let data = json.data(using: .utf8) {
      translations = (try? JSONDecoder().decode([TranscriptTranslation].self, from: data)) ?? []
    }
    return TranscriptSegment(
      id: segmentId ?? UUID().uuidString,
      backendId: segmentId,
      text: text,
      speaker: speakerLabel,
      isUser: isUser,
      personId: personId,
      start: startTime,
      end: endTime,
      translations: translations
    )
  }
}

// MARK: - Convert to ServerConversation

extension TranscriptionSessionRecord {
  /// Convert local record back to ServerConversation for UI display
  /// Requires segments to be passed in (fetched separately)
  func toServerConversation(
    segments: [TranscriptionSegmentRecord],
    transcriptIncluded: Bool? = nil
  ) -> ServerConversation? {
    guard let backendId = backendId else { return nil }

    let decoder = JSONDecoder()

    // Decode JSON fields
    let actionItems: [ActionItem] =
      (actionItemsJson?.data(using: .utf8))
      .flatMap { try? decoder.decode([ActionItem].self, from: $0) } ?? []
    let events: [Event] =
      (eventsJson?.data(using: .utf8))
      .flatMap { try? decoder.decode([Event].self, from: $0) } ?? []
    let sections: [SummarySection] =
      (sectionsJson?.data(using: .utf8))
      .flatMap { try? decoder.decode([SummarySection].self, from: $0) } ?? []
    let geolocation: Geolocation? = (geolocationJson?.data(using: .utf8))
      .flatMap { try? decoder.decode(Geolocation.self, from: $0) }
    let photos: [ConversationPhoto] =
      (photosJson?.data(using: .utf8))
      .flatMap { try? decoder.decode([ConversationPhoto].self, from: $0) } ?? []
    let appsResults: [AppResponse] =
      (appsResultsJson?.data(using: .utf8))
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

    var localSummary = localSummaryJson?.data(using: .utf8).flatMap {
      try? decoder.decode(ConversationLocalSummary.self, from: $0)
    }
    // A newer list projection can arrive before its detail transcript. Cached segments from
    // the preceding revision must not appear underneath it; fetch detail to reunite the pair.
    let transcriptMatches =
      localSummary.map {
        TranscriptHash.sha256(segments: segments.map(\.hashSegment)) == $0.transcriptSha256
      } ?? true
    let transcriptSegments = transcriptMatches ? segments.map { $0.toTranscriptSegment() } : []
    let hasTranscript = transcriptIncluded ?? (cacheCompleteness == .detail || !segments.isEmpty)
    localSummary?.transcriptVerified = transcriptMatches && hasTranscript

    return ServerConversation(
      id: backendId,
      createdAt: createdAt,
      updatedAt: serverUpdatedAt,
      startedAt: startedAt,
      finishedAt: finishedAt,
      structured: Structured(
        title: title ?? "",
        overview: overview ?? "",
        emoji: emoji ?? "",
        category: category ?? "other",
        actionItems: actionItems,
        events: events,
        sections: sections
      ),
      transcriptSegments: transcriptSegments,
      transcriptSegmentsIncluded: transcriptMatches && hasTranscript,
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
      inputDeviceName: inputDeviceName,
      localSummary: localSummary,
      captureGroup: captureGroupJson?.data(using: .utf8).flatMap {
        try? decoder.decode(ServerCaptureGroup.self, from: $0)
      }
    )
  }
}
