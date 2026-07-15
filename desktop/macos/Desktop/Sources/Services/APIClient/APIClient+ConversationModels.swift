import Foundation
import OmiWAL

// MARK: - Conversation Models (matching Flutter app)

enum ConversationStatus: String, Codable {
  case inProgress = "in_progress"
  case processing = "processing"
  case merging = "merging"
  case completed = "completed"
  case failed = "failed"
}

enum ConversationSource: String, Codable {
  case friend
  case omi
  case workflow
  case openglass
  case screenpipe
  case sdcard
  case fieldy
  case bee
  case xor
  case frame
  case friendCom = "friend_com"
  case appleWatch = "apple_watch"
  case phone
  case desktop
  case limitless
  case plaud
  case unknown

  init(from decoder: Decoder) throws {
    let container = try decoder.singleValueContainer()
    let rawValue = try container.decode(String.self)
    self = ConversationSource(rawValue: rawValue) ?? .unknown
  }
}

struct ConversationMutationResponse: Decodable {
  let status: String
  let conversation: ServerConversation
}

enum TranscriptPresenceState: Equatable {
  case omittedFromResponse
  case lockedOrRedacted
  case includedEmpty
  case includedNonEmpty
}

struct ServerConversation: Codable, Identifiable, Equatable {
  static func == (lhs: ServerConversation, rhs: ServerConversation) -> Bool {
    lhs.id == rhs.id && lhs.createdAt == rhs.createdAt && lhs.updatedAt == rhs.updatedAt
      && lhs.startedAt == rhs.startedAt
      && lhs.finishedAt == rhs.finishedAt && lhs.structured == rhs.structured
      && lhs.status == rhs.status && lhs.discarded == rhs.discarded && lhs.deleted == rhs.deleted
      && lhs.isLocked == rhs.isLocked && lhs.starred == rhs.starred && lhs.folderId == rhs.folderId
      && lhs.source == rhs.source
      && lhs.transcriptSegmentsIncluded == rhs.transcriptSegmentsIncluded
  }

  let id: String
  let createdAt: Date
  /// Canonical Firestore document revision. Never derived from recording timestamps.
  let updatedAt: Date?
  let startedAt: Date?
  let finishedAt: Date?

  var structured: Structured
  var transcriptSegments: [TranscriptSegment]
  var transcriptSegmentsIncluded: Bool
  let geolocation: Geolocation?
  let photos: [ConversationPhoto]

  let appsResults: [AppResponse]
  let source: ConversationSource?
  let language: String?

  let status: ConversationStatus
  let discarded: Bool
  let deleted: Bool
  let isLocked: Bool
  var starred: Bool
  let folderId: String?
  let inputDeviceName: String?
  // Lazy processing: true while only the raw transcript is stored (no LLM summary yet);
  // cleared once enriched on first open (get_conversation_by_id).
  let deferred: Bool

  enum CodingKeys: String, CodingKey {
    case id
    case createdAt = "created_at"
    case updatedAt = "updated_at"
    case startedAt = "started_at"
    case finishedAt = "finished_at"
    case structured
    case transcriptSegments = "transcript_segments"
    case geolocation
    case photos
    case appsResults = "apps_results"
    case source
    case language
    case status
    case discarded
    case deleted
    case isLocked = "is_locked"
    case starred
    case folderId = "folder_id"
    case inputDeviceName = "input_device_name"
    case deferred
  }

  init(from decoder: Decoder) throws {
    // Schema authority: OmiAPI.Conversation (generated from app-client OpenAPI).
    // The domain model adapts wire string-dates into Date via the APIClient
    // decoder's ISO8601 strategy, preserves tolerant defaults, and tracks
    // whether transcript_segments was present in the response.
    let wire = try OmiAPI.Conversation(from: decoder)
    let container = try decoder.container(keyedBy: CodingKeys.self)

    id = wire.id
    createdAt = try Self.parseDate(wire.createdAt, decoder: decoder)
    updatedAt = try container.decodeIfPresent(Date.self, forKey: .updatedAt)
    startedAt = try Self.parseOptionalDate(wire.startedAt, decoder: decoder)
    finishedAt = try Self.parseOptionalDate(wire.finishedAt, decoder: decoder)
    structured = Structured(wire.structured)
    // container.contains distinguishes `"transcript_segments": null` (present,
    // empty) from the key being absent (omitted). wire.transcriptSegments is
    // nil for both, so we must check the container directly.
    transcriptSegmentsIncluded = container.contains(.transcriptSegments)
    transcriptSegments = (wire.transcriptSegments ?? []).map(TranscriptSegment.init)
    geolocation = wire.geolocation
    photos = (wire.photos ?? []).map(ConversationPhoto.init)
    appsResults = (wire.appsResults ?? []).map(AppResponse.init)
    source = wire.source.map { ConversationSource(rawValue: $0.rawValue) ?? .unknown }
    language = wire.language
    status = wire.status.map { ConversationStatus(rawValue: $0.rawValue) ?? .completed } ?? .completed
    discarded = wire.discarded ?? false
    deleted = false  // backend REST Conversation schema does not expose deleted
    isLocked = wire.isLocked ?? false
    starred = wire.starred ?? false
    folderId = wire.folderId
    inputDeviceName = wire.clientDeviceId
    deferred = wire.deferred ?? false
  }

  // Date helpers shared with Event/Structured adapters.
  private static let fractionalFormatter: ISO8601DateFormatter = {
    let f = ISO8601DateFormatter()
    f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
    return f
  }()
  private static let standardFormatter = ISO8601DateFormatter()

  private static func parseDate(_ s: String, decoder: Decoder) throws -> Date {
    if let d = fractionalFormatter.date(from: s) ?? standardFormatter.date(from: s) { return d }
    throw DecodingError.dataCorrupted(.init(
      codingPath: decoder.codingPath,
      debugDescription: "Conversation.created_at is not a valid ISO8601 date: \(s)"
    ))
  }

  private static func parseOptionalDate(_ s: String?, decoder: Decoder) throws -> Date? {
    guard let s else { return nil }
    return try parseDate(s, decoder: decoder)
  }

  /// Memberwise initializer for creating from local storage
  init(
    id: String,
    createdAt: Date,
    updatedAt: Date? = nil,
    startedAt: Date?,
    finishedAt: Date?,
    structured: Structured,
    transcriptSegments: [TranscriptSegment],
    transcriptSegmentsIncluded: Bool,
    geolocation: Geolocation?,
    photos: [ConversationPhoto],
    appsResults: [AppResponse],
    source: ConversationSource?,
    language: String?,
    status: ConversationStatus,
    discarded: Bool,
    deleted: Bool,
    isLocked: Bool,
    starred: Bool,
    folderId: String?,
    inputDeviceName: String?,
    deferred: Bool = false
  ) {
    self.id = id
    self.createdAt = createdAt
    self.updatedAt = updatedAt
    self.startedAt = startedAt
    self.finishedAt = finishedAt
    self.structured = structured
    self.transcriptSegments = transcriptSegments
    self.transcriptSegmentsIncluded = transcriptSegmentsIncluded
    self.geolocation = geolocation
    self.photos = photos
    self.appsResults = appsResults
    self.source = source
    self.language = language
    self.status = status
    self.discarded = discarded
    self.deleted = deleted
    self.isLocked = isLocked
    self.starred = starred
    self.folderId = folderId
    self.inputDeviceName = inputDeviceName
    self.deferred = deferred
  }

  /// Returns the title from structured data, or a fallback
  var title: String {
    structured.title.isEmpty ? "Untitled Conversation" : structured.title
  }

  /// Returns the overview/summary from structured data
  var overview: String {
    structured.overview
  }

  /// Returns duration in seconds based on start/finish times or transcript
  var durationInSeconds: Int {
    if let start = startedAt, let end = finishedAt {
      return Int(end.timeIntervalSince(start))
    }
    // Fallback to transcript duration
    guard let lastSegment = transcriptSegments.last else { return 0 }
    return Int(lastSegment.end)
  }

  /// Formatted duration string (e.g., "5m 30s")
  var formattedDuration: String {
    let duration = durationInSeconds
    let minutes = duration / 60
    let seconds = duration % 60
    if minutes > 0 {
      return "\(minutes)m \(seconds)s"
    }
    return "\(seconds)s"
  }

  /// Full transcript as a single string
  var transcript: String {
    transcriptSegments.map { segment in
      let speaker = segment.isUser ? "You" : "Speaker \(segment.speakerId)"
      return "\(speaker): \(segment.text)"
    }.joined(separator: "\n\n")
  }

  var transcriptPresenceState: TranscriptPresenceState {
    if isLocked {
      return .lockedOrRedacted
    }
    if !transcriptSegmentsIncluded {
      return .omittedFromResponse
    }
    if transcriptSegments.isEmpty {
      return .includedEmpty
    }
    return .includedNonEmpty
  }

  var shouldFetchDetailForTranscript: Bool {
    transcriptPresenceState == .omittedFromResponse
  }
}

struct Structured: Codable, Equatable {
  var title: String
  let overview: String
  let emoji: String
  let category: String
  let actionItems: [ActionItem]
  let events: [Event]

  init(from decoder: Decoder) throws {
    // Schema authority: OmiAPI.Structured (generated from app-client OpenAPI).
    // The domain model adds tolerant defaults the wire DTO does not guarantee.
    let wire = try OmiAPI.Structured(from: decoder)
    title = wire.title ?? ""
    overview = wire.overview ?? ""
    emoji = wire.emoji ?? ""
    // CategoryEnum is the backend's strict union; fall back to "other" when the
    // backend returns a value outside it (decoded as ._unknown).
    if let cat = wire.category, cat != ._unknown {
      category = cat.rawValue
    } else {
      category = "other"
    }
    actionItems = (wire.actionItems ?? []).map(ActionItem.init)
    events = (wire.events ?? []).map(Event.init)
  }

  init(_ wire: OmiAPI.Structured) {
    title = wire.title ?? ""
    overview = wire.overview ?? ""
    emoji = wire.emoji ?? ""
    if let cat = wire.category, cat != ._unknown {
      category = cat.rawValue
    } else {
      category = "other"
    }
    actionItems = (wire.actionItems ?? []).map(ActionItem.init)
    events = (wire.events ?? []).map(Event.init)
  }

  func encode(to encoder: Encoder) throws {
    let actionItemsWire = actionItems.map {
      OmiAPI.ActionItem(candidateAction: nil, captureConfidence: nil, captureKind: nil, captureOwner: nil, completed: $0.completed, completedAt: nil, concreteDeliverable: nil, conversationId: nil, createdAt: nil, description_: $0.description, dueAt: nil, ownershipConfidence: nil, targetTaskId: nil, updatedAt: nil)
    }
    let eventsWire = events.map {
      OmiAPI.Event(
        created: $0.created,
        description_: $0.description,
        duration: $0.duration,
        start: Event.encodeDateForWire($0.startsAt),
        title: $0.title
      )
    }
    let wire = OmiAPI.Structured(
      actionItems: actionItemsWire,
      category: OmiAPI.CategoryEnum(rawValue: category),
      emoji: emoji,
      events: eventsWire,
      overview: overview,
      title: title
    )
    try wire.encode(to: encoder)
  }

  /// Memberwise initializer for creating from local storage
  init(
    title: String,
    overview: String,
    emoji: String,
    category: String,
    actionItems: [ActionItem],
    events: [Event]
  ) {
    self.title = title
    self.overview = overview
    self.emoji = emoji
    self.category = category
    self.actionItems = actionItems
    self.events = events
  }
}

struct ActionItem: Codable, Identifiable, Equatable {
  var id: String { description }
  let description: String
  let completed: Bool
  let deleted: Bool

  init(description: String, completed: Bool, deleted: Bool) {
    self.description = description
    self.completed = completed
    self.deleted = deleted
  }

  /// Adapter from the generated wire DTO (OmiAPI.ActionItem). `deleted` is a
  /// desktop-only field the backend REST schema does not expose; it defaults
  /// to false on decode.
  init(_ wire: OmiAPI.ActionItem) {
    self.description = wire.description_
    self.completed = wire.completed ?? false
    self.deleted = false
  }

  init(from decoder: Decoder) throws {
    let wire = try OmiAPI.ActionItem(from: decoder)
    self.description = wire.description_
    self.completed = wire.completed ?? false
    self.deleted = false
  }

  func encode(to encoder: Encoder) throws {
    let wire = OmiAPI.ActionItem(
      candidateAction: nil,
      captureConfidence: nil,
      captureKind: nil,
      captureOwner: nil,
      completed: completed,
      completedAt: nil,
      concreteDeliverable: nil,
      conversationId: nil,
      createdAt: nil,
      description_: description,
      dueAt: nil,
      ownershipConfidence: nil,
      targetTaskId: nil,
      updatedAt: nil
    )
    try wire.encode(to: encoder)
  }
}

struct Event: Codable, Identifiable, Equatable {
  var id: String { title + startsAt.description }
  let title: String
  let startsAt: Date
  let duration: Int
  let description: String
  let created: Bool

  /// Adapter from the generated wire DTO (OmiAPI.Event). The backend `Event`
  /// model exposes `start` (not `starts_at`); this adapter maps the field and
  /// parses the ISO8601 string into a Date using the APIClient decoder's
  /// strategy via JSONDecoder reuse.
  init(_ wire: OmiAPI.Event) {
    self.title = wire.title
    self.startsAt = Self.parseDate(wire.start) ?? Date()
    self.duration = wire.duration ?? 0
    self.description = wire.description_ ?? ""
    self.created = wire.created ?? false
  }

  init(from decoder: Decoder) throws {
    // Decode via the generated wire shape, then adapt. `start` is the backend
    // field name (generated); cached rows may still use legacy `starts_at`.
    if let wire = try? OmiAPI.Event(from: decoder) {
      self.title = wire.title
      self.startsAt = Self.parseDate(wire.start) ?? Date()
      self.duration = wire.duration ?? 0
      self.description = wire.description_ ?? ""
      self.created = wire.created ?? false
      return
    }

    enum LegacyKeys: String, CodingKey {
      case title, start, startsAt = "starts_at", duration, description, created
    }
    let container = try decoder.container(keyedBy: LegacyKeys.self)
    self.title = try container.decode(String.self, forKey: .title)
    let startString = try container.decodeIfPresent(String.self, forKey: .start)
      ?? container.decodeIfPresent(String.self, forKey: .startsAt)
    self.startsAt = startString.flatMap(Self.parseDate) ?? Date()
    self.duration = try container.decodeIfPresent(Int.self, forKey: .duration) ?? 0
    self.description = try container.decodeIfPresent(String.self, forKey: .description) ?? ""
    self.created = try container.decodeIfPresent(Bool.self, forKey: .created) ?? false
  }

  func encode(to encoder: Encoder) throws {
    let startString = Self.encodeDate(startsAt)
    let wire = OmiAPI.Event(
      created: created,
      description_: description,
      duration: duration,
      start: startString,
      title: title
    )
    try wire.encode(to: encoder)
  }

  // Date helpers — reuse the APIClient decoder's ISO8601-with-fractional strategy.
  private static let fractionalFormatter: ISO8601DateFormatter = {
    let f = ISO8601DateFormatter()
    f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
    return f
  }()
  private static let standardFormatter = ISO8601DateFormatter()

  private static func parseDate(_ s: String) -> Date? {
    fractionalFormatter.date(from: s) ?? standardFormatter.date(from: s)
  }

  private static func decodeDate(_ s: String, using decoder: Decoder) throws -> Date {
    if let date = parseDate(s) { return date }
    let context = DecodingError.Context(
      codingPath: decoder.codingPath,
      debugDescription: "Event.start is not a valid ISO8601 date: \(s)"
    )
    throw DecodingError.dataCorrupted(context)
  }

  private static func encodeDate(_ date: Date) -> String {
    fractionalFormatter.string(from: date)
  }

  fileprivate static func encodeDateForWire(_ date: Date) -> String {
    encodeDate(date)
  }
}

/// Schema authority: OmiAPI.Translation (generated from app-client OpenAPI).
/// Field-for-field identical to the wire DTO, so this is a thin alias.
typealias TranscriptTranslation = OmiAPI.Translation

struct TranscriptSegment: Codable, Identifiable {
  let id: String
  let backendId: String?
  let text: String
  let speaker: String?
  let isUser: Bool
  let personId: String?
  let start: Double
  let end: Double
  let translations: [TranscriptTranslation]

  var speakerId: Int {
    guard let speaker = speaker else { return 0 }
    let parts = speaker.split(separator: "_")
    if parts.count > 1, let id = Int(parts[1]) {
      return id
    }
    return 0
  }

  enum CodingKeys: String, CodingKey {
    case id, text, speaker
    case isUser = "is_user"
    case personId = "person_id"
    case start, end, translations
  }

  init(from decoder: Decoder) throws {
    let container = try decoder.container(keyedBy: CodingKeys.self)
    let decodedId = try container.decodeIfPresent(String.self, forKey: .id)
    id = decodedId ?? UUID().uuidString
    backendId = decodedId
    text = try container.decodeIfPresent(String.self, forKey: .text) ?? ""
    speaker = try container.decodeIfPresent(String.self, forKey: .speaker)
    isUser = try container.decodeIfPresent(Bool.self, forKey: .isUser) ?? false
    personId = try container.decodeIfPresent(String.self, forKey: .personId)
    start = try container.decodeIfPresent(Double.self, forKey: .start) ?? 0
    end = try container.decodeIfPresent(Double.self, forKey: .end) ?? 0
    translations =
      try container.decodeIfPresent([TranscriptTranslation].self, forKey: .translations) ?? []
  }

  /// Adapter from the generated wire DTO (OmiAPI.TranscriptSegment). The
  /// generated wire exposes `speaker_id` directly; the domain derives it from
  /// `speaker` to preserve legacy behavior.
  init(_ wire: OmiAPI.TranscriptSegment) {
    let decodedId = wire.id
    self.id = decodedId ?? UUID().uuidString
    self.backendId = decodedId
    self.text = wire.text
    self.speaker = wire.speaker
    self.isUser = wire.isUser
    self.personId = wire.personId
    self.start = wire.start
    self.end = wire.end
    self.translations = []  // wire translations map omitted; legacy field
  }

  /// Memberwise initializer for creating from local storage
  init(
    id: String,
    backendId: String? = nil,
    text: String,
    speaker: String?,
    isUser: Bool,
    personId: String?,
    start: Double,
    end: Double,
    translations: [TranscriptTranslation] = []
  ) {
    self.id = id
    self.backendId = backendId
    self.text = text
    self.speaker = speaker
    self.isUser = isUser
    self.personId = personId
    self.start = start
    self.end = end
    self.translations = translations
  }

  /// Formatted timestamp string (e.g., "00:01:30 - 00:01:45")
  var timestampString: String {
    let startTime = formatTime(start)
    let endTime = formatTime(end)
    return "\(startTime) - \(endTime)"
  }

  private func formatTime(_ seconds: Double) -> String {
    let totalSeconds = Int(seconds)
    let hours = totalSeconds / 3600
    let minutes = (totalSeconds % 3600) / 60
    let secs = totalSeconds % 60
    return String(format: "%02d:%02d:%02d", hours, minutes, secs)
  }
}

/// Schema authority: OmiAPI.Geolocation (generated from app-client OpenAPI).
/// Field-for-field identical to the wire DTO; the prior adapter only passed
/// the four exposed fields through with no transformation (no Date parsing,
/// no defaults, no computed properties), so this is a thin alias.
typealias Geolocation = OmiAPI.Geolocation

struct ConversationPhoto: Codable, Identifiable {
  let id: String
  let base64: String
  let description: String?
  let createdAt: Date
  let discarded: Bool

  enum CodingKeys: String, CodingKey {
    case id, base64, description
    case createdAt = "created_at"
    case discarded
  }

  init(from decoder: Decoder) throws {
    let container = try decoder.container(keyedBy: CodingKeys.self)
    id = try container.decodeIfPresent(String.self, forKey: .id) ?? UUID().uuidString
    base64 = try container.decodeIfPresent(String.self, forKey: .base64) ?? ""
    description = try container.decodeIfPresent(String.self, forKey: .description)
    createdAt = try container.decodeIfPresent(Date.self, forKey: .createdAt) ?? Date()
    discarded = try container.decodeIfPresent(Bool.self, forKey: .discarded) ?? false
  }

  /// Adapter from the generated wire DTO (OmiAPI.ConversationPhoto). The wire
  /// exposes `created_at` as a string; this adapter parses it via the shared
  /// ISO8601 strategy.
  init(_ wire: OmiAPI.ConversationPhoto) {
    self.id = wire.id ?? UUID().uuidString
    self.base64 = wire.base64
    self.description = wire.description_
    let f = ISO8601DateFormatter()
    f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
    let std = ISO8601DateFormatter()
    if let s = wire.createdAt, let d = f.date(from: s) ?? std.date(from: s) {
      self.createdAt = d
    } else {
      self.createdAt = Date()
    }
    self.discarded = wire.discarded ?? false
  }
}

struct AppResponse: Codable, Identifiable {
  var id: String { appId ?? UUID().uuidString }
  let appId: String?
  let content: String

  enum CodingKeys: String, CodingKey {
    case appId = "app_id"
    case content
  }

  /// Adapter from the generated wire DTO (OmiAPI.AppResult).
  init(_ wire: OmiAPI.AppResult) {
    self.appId = wire.appId
    self.content = wire.content
  }

  init(from decoder: Decoder) throws {
    let container = try decoder.container(keyedBy: CodingKeys.self)
    appId = try container.decodeIfPresent(String.self, forKey: .appId)
    content = try container.decodeIfPresent(String.self, forKey: .content) ?? ""
  }
}

struct ConversationSearchResult: Codable {
  let items: [ServerConversation]
  let currentPage: Int
  let totalPages: Int

  enum CodingKeys: String, CodingKey {
    case items
    case currentPage = "current_page"
    case totalPages = "total_pages"
  }
}

// MARK: - Merge Response

/// Response from merge conversations API
struct MergeConversationsResponse: Decodable {
  let status: String
  let message: String
  let warning: String?
  let conversationIds: [String]
  let newConversationId: String?

  enum CodingKeys: String, CodingKey {
    case status, message, warning
    case conversationIds = "conversation_ids"
    case newConversationId = "new_conversation_id"
  }
}

// MARK: - Folder Models

struct Folder: Codable, Identifiable {
  let id: String
  var name: String
  var description: String?
  var color: String
  let createdAt: Date
  let updatedAt: Date
  var order: Int
  let isDefault: Bool
  let isSystem: Bool
  let categoryMapping: String?
  let conversationCount: Int

  enum CodingKeys: String, CodingKey {
    case id, name, description, color, order
    case createdAt = "created_at"
    case updatedAt = "updated_at"
    case isDefault = "is_default"
    case isSystem = "is_system"
    case categoryMapping = "category_mapping"
    case conversationCount = "conversation_count"
  }

  init(from decoder: Decoder) throws {
    let container = try decoder.container(keyedBy: CodingKeys.self)
    id = try container.decode(String.self, forKey: .id)
    name = try container.decode(String.self, forKey: .name)
    description = try container.decodeIfPresent(String.self, forKey: .description)
    color = try container.decodeIfPresent(String.self, forKey: .color) ?? "#6B7280"
    createdAt = try container.decodeIfPresent(Date.self, forKey: .createdAt) ?? Date()
    updatedAt = try container.decodeIfPresent(Date.self, forKey: .updatedAt) ?? Date()
    order = try container.decodeIfPresent(Int.self, forKey: .order) ?? 0
    isDefault = try container.decodeIfPresent(Bool.self, forKey: .isDefault) ?? false
    isSystem = try container.decodeIfPresent(Bool.self, forKey: .isSystem) ?? false
    categoryMapping = try container.decodeIfPresent(String.self, forKey: .categoryMapping)
    conversationCount = try container.decodeIfPresent(Int.self, forKey: .conversationCount) ?? 0
  }
}

struct CreateFolderRequest: Encodable {
  let name: String
  let description: String?
  let color: String?
}

struct UpdateFolderRequest: Encodable {
  let name: String?
  let description: String?
  let color: String?
  let order: Int?
}

struct MoveToFolderRequest: Encodable {
  let folderId: String?

  enum CodingKeys: String, CodingKey {
    case folderId = "folder_id"
  }
}
