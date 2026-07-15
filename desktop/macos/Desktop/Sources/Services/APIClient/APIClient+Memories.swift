import Foundation
import OmiWAL

// MARK: - Memory Models

enum MemoryCategory: String, Codable, CaseIterable {
  case system
  case interesting
  case manual
  case workflow

  var displayName: String {
    switch self {
    case .system: return "About You"
    case .interesting: return "Insights"
    case .manual: return "Manual"
    case .workflow: return "Workflow"
    }
  }

  var icon: String {
    switch self {
    case .system: return "person"
    case .interesting: return "lightbulb"
    case .manual: return "square.and.pencil"
    case .workflow: return "arrow.triangle.branch"
    }
  }

  /// Adapter from the generated wire enum (OmiAPI.MemoryCategory). The backend
  /// exposes a wider enum than the desktop renders; unknown values collapse to
  /// `.system` so the row still decodes.
  init(_ wire: OmiAPI.MemoryCategory) {
    self = MemoryCategory(rawValue: wire.rawValue) ?? .system
  }
}

enum MemoryLayer: String, Codable, CaseIterable, Identifiable {
  case shortTerm = "short_term"
  case longTerm = "long_term"
  case archive

  init(from decoder: Decoder) throws {
    let container = try decoder.singleValueContainer()
    let rawValue = try container.decode(String.self)
    guard let layer = MemoryLayer(rawValue: rawValue) else {
      throw DecodingError.dataCorruptedError(
        in: container,
        debugDescription: "Unknown ServerMemory layer '\(rawValue)'"
      )
    }
    self = layer
  }

  func encode(to encoder: Encoder) throws {
    var container = encoder.singleValueContainer()
    try container.encode(rawValue)
  }

  var id: String { rawValue }

  var displayName: String {
    switch self {
    case .shortTerm: return "Short-term"
    case .longTerm: return "Long-term"
    case .archive: return "Archive"
    }
  }

  var icon: String {
    switch self {
    case .shortTerm: return "clock"
    case .longTerm: return "brain.head.profile"
    case .archive: return "archivebox"
    }
  }

  var isDefaultAccessible: Bool {
    self == .shortTerm || self == .longTerm
  }

  var layerInfoText: String {
    switch self {
    case .shortTerm:
      return
        "Recent observations from your activity. May decay or promote to Long-term when corroborated."
    case .longTerm:
      return
        "Durable facts Omi keeps long-term - stable details about you, your preferences, and your life."
    case .archive:
      return "Aged-out long-term memories. Hidden by default; search Archive to find them."
    }
  }
}

/// Reversible alias during WS-G client rename.
typealias MemoryTier = MemoryLayer

struct MemoryLayerScope: Equatable {
  let tiers: [MemoryLayer]
  let requiresArchiveAcknowledgement: Bool

  static let defaultAccess = MemoryLayerScope(
    tiers: [.shortTerm, .longTerm],
    requiresArchiveAcknowledgement: false
  )
  static let archiveOnly = MemoryLayerScope(
    tiers: [.archive],
    requiresArchiveAcknowledgement: true
  )
  static let allIncludingArchive = MemoryLayerScope(
    tiers: [.shortTerm, .longTerm, .archive],
    requiresArchiveAcknowledgement: true
  )

  var includesArchive: Bool { tiers.contains(.archive) }
  var sqlTierRawValues: [String] { tiers.map { $0.rawValue } }
}

/// Reversible alias during WS-G client rename.
typealias MemoryTierScope = MemoryLayerScope

private enum ServerMemoryAliasDecodeError {
  static func conflict(
    _ firstField: String,
    _ firstValue: String,
    _ secondField: String,
    _ secondValue: String,
    codingPath: [CodingKey]
  ) -> DecodingError {
    DecodingError.dataCorrupted(
      DecodingError.Context(
        codingPath: codingPath,
        debugDescription: "Conflicting ServerMemory aliases: \(firstField)=\(firstValue) differs from \(secondField)=\(secondValue)"
      )
    )
  }
}

struct ServerMemory: Decodable, Identifiable {
  let id: String
  let content: String
  let category: MemoryCategory
  let createdAt: Date
  let updatedAt: Date
  let capturedAt: Date?
  let expiresAt: Date?
  let tier: MemoryLayer
  let tierIsExplicit: Bool
  let conversationId: String?
  let reviewed: Bool
  let userReview: Bool?
  var visibility: String
  let manuallyAdded: Bool
  let scoring: String?
  let source: String?
  // New fields for parity with Advice
  let confidence: Double?
  let sourceApp: String?
  let contextSummary: String?
  let isRead: Bool
  let isDismissed: Bool
  // Tags for filtering (e.g., ["tips", "productivity"])
  let tags: [String]
  // Reasoning behind the memory/tip (from advice system)
  let reasoning: String?
  // Description of user's activity when memory was generated
  let currentActivity: String?
  // Input device name (microphone) for desktop transcriptions
  let inputDeviceName: String?
  // Window title when memory was extracted
  let windowTitle: String?
  // Capture-device provenance (optional; absent on legacy memories)
  let primaryCaptureDevice: String?
  let captureDeviceIds: [String]
  // Short headline for notification preview (advice/tips only)
  let headline: String?

  enum CodingKeys: String, CodingKey {
    case id, content, category, reviewed, visibility, scoring, source, confidence, tags, reasoning,
      headline, tier, layer
    case memoryId = "memory_id"
    case memoryTier = "memory_tier"
    case createdAt = "created_at"
    case updatedAt = "updated_at"
    case capturedAt = "captured_at"
    case expiresAt = "expires_at"
    case conversationId = "conversation_id"
    case userReview = "user_review"
    case manuallyAdded = "manually_added"
    case sourceApp = "source_app"
    case contextSummary = "context_summary"
    case isRead = "is_read"
    case isDismissed = "is_dismissed"
    case currentActivity = "current_activity"
    case inputDeviceName = "input_device_name"
    case windowTitle = "window_title"
    case primaryCaptureDevice = "primary_capture_device"
    case captureDeviceIds = "capture_device_ids"
  }

  init(from decoder: Decoder) throws {
    let container = try decoder.container(keyedBy: CodingKeys.self)
    // Schema authority: OmiAPI.MemoryDB (generated from app-client OpenAPI).
    // The wire DTO validates backend-owned fields against the generated
    // contract, but its required fields (uid, id, createdAt, updatedAt) are
    // stricter than the legacy decoder which used decodeIfPresent for
    // tolerance. We try the wire DTO and fall back to the container for any
    // field it rejects, preserving the old tolerant behavior.
    let wire = try? OmiAPI.MemoryDB(from: decoder)

    // id / memory_id alias resolution: wire.id is the backend authority
    // (required String); memory_id is an optional legacy alias. Preserve the
    // silent-mismatch behavior from the legacy decoder.
    let idValue = try wire?.id ?? container.decodeIfPresent(String.self, forKey: .id)
    let memoryIdValue = try wire?.memoryId ?? container.decodeIfPresent(String.self, forKey: .memoryId)
    switch (idValue, memoryIdValue) {
    case let (.some(id), .some(memoryId)) where id != memoryId:
      self.id = id
    case let (.some(id), _):
      self.id = id
    case let (_, .some(memoryId)):
      self.id = memoryId
    case (.none, .none):
      throw DecodingError.keyNotFound(
        CodingKeys.id,
        DecodingError.Context(
          codingPath: container.codingPath,
          debugDescription: "ServerMemory requires either id or memory_id"
        )
      )
    }

    content = try wire?.content ?? container.decode(String.self, forKey: .content)
    category = wire?.category.map(MemoryCategory.init) ?? .system
    capturedAt = try container.decodeIfPresent(Date.self, forKey: .capturedAt)
    let f = ISO8601DateFormatter()
    f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
    let std = ISO8601DateFormatter()
    let createdAtString = wire?.createdAt
    createdAt = (createdAtString.flatMap { f.date(from: $0) ?? std.date(from: $0) }) ?? capturedAt ?? Date()
    let updatedAtString = wire?.updatedAt
    updatedAt = (updatedAtString.flatMap { f.date(from: $0) ?? std.date(from: $0) }) ?? createdAt
    expiresAt = try container.decodeIfPresent(Date.self, forKey: .expiresAt)

    // layer / tier / memory_tier alias resolution. Prefer wire DTO fields
    // (schema-validated); fall back to container decoding when the wire DTO
    // could not be constructed (missing required fields like uid).
    let layerValue = try wire?.layer.flatMap(MemoryLayer.init(rawValue:))
      ?? container.decodeIfPresent(MemoryLayer.self, forKey: .layer)
    let tierValue = try container.decodeIfPresent(MemoryLayer.self, forKey: .tier)
    let memoryTierValue = try wire?.memoryTier.flatMap { MemoryLayer(rawValue: $0.rawValue) }
      ?? container.decodeIfPresent(MemoryLayer.self, forKey: .memoryTier)
    tierIsExplicit = layerValue != nil || tierValue != nil || memoryTierValue != nil

    let presentTierAliases: [(String, MemoryLayer)] = [
      layerValue.map { ("layer", $0) },
      tierValue.map { ("tier", $0) },
      memoryTierValue.map { ("memory_tier", $0) },
    ].compactMap { $0 }
    if presentTierAliases.count >= 2 {
      let first = presentTierAliases[0]
      for other in presentTierAliases.dropFirst() where other.1 != first.1 {
        throw ServerMemoryAliasDecodeError.conflict(
          first.0, first.1.rawValue, other.0, other.1.rawValue, codingPath: container.codingPath)
      }
    }

    switch (layerValue, tierValue, memoryTierValue) {
    case let (.some(layer), _, _):
      self.tier = layer
    case let (_, .some(tier), _):
      self.tier = tier
    case let (_, _, .some(memoryTier)):
      self.tier = memoryTier
    case (.none, .none, .none):
      self.tier = .longTerm
    }

    conversationId = wire?.conversationId
    reviewed = wire?.reviewed ?? false
    userReview = wire?.userReview
    visibility = wire?.visibility ?? "private"
    manuallyAdded = wire?.manuallyAdded ?? false
    scoring = wire?.scoring
    source = try container.decodeIfPresent(String.self, forKey: .source)
    confidence = wire?.captureConfidence
    sourceApp = wire?.appId
    contextSummary = try container.decodeIfPresent(String.self, forKey: .contextSummary)
    isRead = try container.decodeIfPresent(Bool.self, forKey: .isRead) ?? false
    isDismissed = try container.decodeIfPresent(Bool.self, forKey: .isDismissed) ?? false
    tags = wire?.tags ?? []
    reasoning = try container.decodeIfPresent(String.self, forKey: .reasoning)
    currentActivity = try container.decodeIfPresent(String.self, forKey: .currentActivity)
    inputDeviceName = try container.decodeIfPresent(String.self, forKey: .inputDeviceName)
    windowTitle = try container.decodeIfPresent(String.self, forKey: .windowTitle)
    primaryCaptureDevice = wire?.primaryCaptureDevice
    captureDeviceIds = wire?.captureDeviceIds ?? []
    headline = wire?.headline
  }

  var isPublic: Bool {
    visibility == "public"
  }

  /// Confidence as percentage string
  var confidenceString: String? {
    guard let confidence = confidence else { return nil }
    return "\(Int(confidence * 100))%"
  }

  /// Human-readable source name
  var sourceName: String? {
    guard let source = source else { return nil }
    switch source {
    case "screenshot": return "Screenshot"
    case "omi": return "OMI"
    case "desktop": return "Desktop"
    case "phone": return "Phone"
    case "frame": return "Frame"
    case "friend", "friend_com": return "Friend"
    case "apple_watch": return "Apple Watch"
    case "bee": return "Bee"
    case "plaud": return "Plaud"
    case "limitless": return "Limitless"
    case "screenpipe": return "Screenpipe"
    case "workflow": return "Integration"
    case "openglass": return "OpenGlass"
    default: return source.capitalized
    }
  }

  /// SF Symbol for source device
  var sourceIcon: String {
    guard let source = source else { return "questionmark.circle" }
    switch source {
    case "screenshot": return "camera.viewfinder"
    case "omi": return "wave.3.right.circle"
    case "desktop": return "desktopcomputer"
    case "phone": return "iphone"
    case "frame": return "eyeglasses"
    case "friend", "friend_com": return "person.wave.2"
    case "apple_watch": return "applewatch"
    case "bee": return "ant"
    case "plaud": return "mic"
    case "limitless": return "infinity"
    case "screenpipe": return "rectangle.on.rectangle"
    case "workflow": return "arrow.triangle.branch"
    case "openglass": return "eyeglasses"
    default: return "circle"
    }
  }

  /// Whether this memory is a tip (from advice system)
  var isTip: Bool {
    tags.contains("tips")
  }

  /// Get the tip subcategory (productivity, health, etc.) if this is a tip
  var tipCategory: String? {
    guard isTip else { return nil }
    let subcategories = ["productivity", "health", "communication", "learning", "other"]
    return tags.first { subcategories.contains($0) }
  }

  /// Icon for tip subcategory
  var tipCategoryIcon: String {
    switch tipCategory {
    case "productivity": return "chart.line.uptrend.xyaxis"
    case "health": return "heart.fill"
    case "communication": return "bubble.left.and.bubble.right.fill"
    case "learning": return "book.fill"
    case "other": return "lightbulb.fill"
    default: return "lightbulb.fill"
    }
  }
}

// MARK: - Force Process Conversation API

extension APIClient {

  /// Response from Python POST /v1/conversations (force-process)
  struct ForceProcessConversationResponse: Decodable {
    let conversation: ServerConversation
  }

  /// Force-process the current in-progress conversation on the Python backend.
  /// Endpoint: POST /v1/conversations (Python backend)
  /// This is the same endpoint the mobile app uses when stopping phone mic recording.
  /// The Python backend finds the in-progress conversation via Redis and processes it.
  /// Returns the processed conversation on success, nil on 404 (already processed).
  /// Throws on other errors.
  func forceProcessConversation() async throws -> ServerConversation? {
    struct EmptyBody: Encodable {}

    do {
      let response: ForceProcessConversationResponse = try await post(
        "v1/conversations",
        body: EmptyBody(),
        customBaseURL: nil
      )
      return response.conversation
    } catch APIError.httpError(statusCode: let statusCode, detail: _) where statusCode == 404 {
      // 404 = no in-progress conversation found — WS close handler already processed it
      return nil
    }
  }

  /// Finalize a specific backend conversation id. This avoids the global Redis-backed
  /// force-process endpoint, which can act on a newer in-progress recording after rotation.
  func finalizeConversation(id conversationId: String) async throws -> ServerConversation {
    struct EmptyBody: Encodable {}

    let response: ForceProcessConversationResponse = try await post(
      "v1/conversations/\(conversationId)/finalize",
      body: EmptyBody(),
      customBaseURL: nil
    )
    return response.conversation
  }
}

// MARK: - Create Conversation From Segments (on-device transcription upload)

extension APIClient {
  /// One transcript segment for the from-segments upload (matches backend DevTranscriptSegment).
  struct UploadSegment: Encodable {
    let text: String
    let speaker: String
    let speaker_id: Int?
    let is_user: Bool
    let person_id: String?
    let start: Double
    let end: Double
  }

  struct CreateConversationFromSegmentsRequest: Encodable {
    let transcript_segments: [UploadSegment]
    let source: String
    let started_at: String?  // ISO8601
    let finished_at: String?  // ISO8601
    let language: String
    let client_conversation_id: String?
  }

  struct CreateConversationFromSegmentsResponse: Decodable {
    let id: String
    let status: String
    let discarded: Bool

    enum CodingKeys: String, CodingKey {
      case id
      case status
      case discarded
    }

    init(from decoder: Decoder) throws {
      let container = try decoder.container(keyedBy: CodingKeys.self)
      id = try container.decode(String.self, forKey: .id)
      status = try container.decodeIfPresent(String.self, forKey: .status) ?? ConversationStatus.processing.rawValue
      discarded = try container.decodeIfPresent(Bool.self, forKey: .discarded) ?? false
    }
  }

  /// Upload an already-transcribed (on-device Parakeet) conversation to the backend so it is
  /// persisted, processed (memories/summaries), and synced to every device — the same pipeline a
  /// cloud-transcribed conversation goes through, without the live `/v4/listen` websocket.
  /// Endpoint: POST /v1/conversations/from-segments (Firebase-authed).
  func createConversationFromSegments(_ request: CreateConversationFromSegmentsRequest)
    async throws -> CreateConversationFromSegmentsResponse
  {
    let response: CreateConversationFromSegmentsResponse = try await post(
      "v1/conversations/from-segments", body: request, customBaseURL: nil)
    invalidateConversationsCountCache()
    return response
  }
}

// MARK: - Memories API

extension APIClient {
  private static let canonicalLifecycleExposedHeader = "X-Omi-Memory-Canonical-Lifecycle-Exposed"
  private static let deviceScopeSupportedHeader = "X-Omi-Memory-Device-Scope-Supported"

  struct MemoryListPage {
    let memories: [ServerMemory]
    let canonicalLifecycleExposed: Bool
    let deviceScopeSupported: Bool?
  }

  /// Fetches memories from the API with optional filtering
  func getMemories(
    limit: Int = 100,
    offset: Int = 0,
    category: String? = nil,
    tags: [String]? = nil,
    includeDismissed: Bool = false,
    deviceScope: String? = nil
  ) async throws -> [ServerMemory] {
    var endpoint = "v3/memories?limit=\(limit)&offset=\(offset)"
    if let category = category {
      endpoint += "&category=\(category)"
    }
    if let tags = tags, !tags.isEmpty {
      endpoint += "&tags=\(tags.joined(separator: ","))"
    }
    if includeDismissed {
      endpoint += "&include_dismissed=true"
    }
    if let deviceScope = deviceScope {
      endpoint += "&device_scope=\(deviceScope)"
    }
    return try await get(endpoint)
  }

  /// Fetches memories plus server-authoritative capability headers.
  func getMemoriesPage(
    limit: Int = 100,
    offset: Int = 0,
    category: String? = nil,
    tags: [String]? = nil,
    includeDismissed: Bool = false,
    deviceScope: String? = nil
  ) async throws -> MemoryListPage {
    var endpoint = "v3/memories?limit=\(limit)&offset=\(offset)"
    if let category = category {
      endpoint += "&category=\(category)"
    }
    if let tags = tags, !tags.isEmpty {
      endpoint += "&tags=\(tags.joined(separator: ","))"
    }
    if includeDismissed {
      endpoint += "&include_dismissed=true"
    }
    if let deviceScope = deviceScope {
      endpoint += "&device_scope=\(deviceScope)"
    }

    let url = URL(string: baseURL + endpoint)!
    var request = URLRequest(url: url)
    request.httpMethod = "GET"
    request.allHTTPHeaderFields = try await buildHeaders(requireAuth: true)
    let (data, httpResponse) = try await performAuthenticatedData(for: request)

    guard (200...299).contains(httpResponse.statusCode) else {
      let detail = OmiHTTPTransport.extractErrorDetail(from: data)
      throw APIError.httpError(statusCode: httpResponse.statusCode, detail: detail)
    }

    let memories = try decoder.decode([ServerMemory].self, from: data)
    let lifecycleHeader = httpResponse.value(forHTTPHeaderField: Self.canonicalLifecycleExposedHeader)
    let canonicalLifecycleExposed = lifecycleHeader == "true"
    let deviceScopeHeader = httpResponse.value(forHTTPHeaderField: Self.deviceScopeSupportedHeader)
    let deviceScopeSupported = deviceScopeHeader.map { $0.caseInsensitiveCompare("true") == .orderedSame }
    return MemoryListPage(
      memories: memories,
      canonicalLifecycleExposed: canonicalLifecycleExposed,
      deviceScopeSupported: deviceScopeSupported
    )
  }

  /// Creates a new memory (manual or extracted)
  func createMemory(
    content: String,
    visibility: String = "private",
    category: MemoryCategory? = nil,
    confidence: Double? = nil,
    sourceApp: String? = nil,
    contextSummary: String? = nil,
    tags: [String] = [],
    reasoning: String? = nil,
    currentActivity: String? = nil,
    source: String? = nil,
    windowTitle: String? = nil,
    headline: String? = nil,
    expectedOwnerId: String? = nil
  ) async throws -> CreateMemoryResponse {
    struct CreateRequest: Encodable {
      let content: String
      let visibility: String
      let category: String?
      let confidence: Double?
      let sourceApp: String?
      let contextSummary: String?
      let tags: [String]
      let reasoning: String?
      let currentActivity: String?
      let source: String?
      let windowTitle: String?
      let headline: String?

      enum CodingKeys: String, CodingKey {
        case content, visibility, category, confidence, tags, reasoning, source, headline
        case sourceApp = "source_app"
        case contextSummary = "context_summary"
        case currentActivity = "current_activity"
        case windowTitle = "window_title"
      }
    }
    let body = CreateRequest(
      content: content,
      visibility: visibility,
      category: category?.rawValue,
      confidence: confidence,
      sourceApp: sourceApp,
      contextSummary: contextSummary,
      tags: tags,
      reasoning: reasoning,
      currentActivity: currentActivity,
      source: source,
      windowTitle: windowTitle,
      headline: headline
    )
    return try await post("v3/memories", body: body, expectedOwnerId: expectedOwnerId)
  }

  /// Max memories per POST /v3/memories/batch call. Must match the
  /// `MEMORIES_BATCH_MAX` constant in backend/routers/memories.py.
  static let memoriesBatchMaxSize = 100
  static let memoryImportBatchMaxSize = 100

  /// Creates many product memories in a single HTTP call.
  ///
  /// Caller is responsible for chunking input into groups of at most
  /// `memoriesBatchMaxSize`. Returns the created count from the server.
  func createMemoriesBatch(_ memories: [MemoryBatchItem]) async throws -> BatchMemoriesResponse {
    precondition(
      memories.count <= Self.memoriesBatchMaxSize,
      "createMemoriesBatch received \(memories.count) memories, max is \(Self.memoriesBatchMaxSize)"
    )
    struct BatchRequest: Encodable {
      let memories: [MemoryBatchItem]
    }
    let body = BatchRequest(memories: memories)
    return try await post("v3/memories/batch", body: body)
  }

  func createMemoryImportBatch(_ batch: ImportEvidenceBatch) async throws -> ImportEvidenceBatchResponse {
    precondition(
      batch.items.count <= Self.memoryImportBatchMaxSize,
      "createMemoryImportBatch received \(batch.items.count) artifacts, max is \(Self.memoryImportBatchMaxSize)"
    )
    return try await post("v3/memory-imports/batch", body: batch, includeBYOK: false)
  }

  /// Deletes a memory by ID
  func deleteMemory(id: String) async throws {
    try await delete("v3/memories/\(id)")
  }

  /// Edits a memory's content
  func editMemory(id: String, content: String) async throws {
    struct EditRequest: Encodable {
      let value: String
    }
    let body = EditRequest(value: content)
    let _: MemoryStatusResponse = try await patch("v3/memories/\(id)", body: body)
  }

  /// Updates a memory's visibility
  func updateMemoryVisibility(id: String, visibility: String) async throws {
    struct VisibilityRequest: Encodable {
      let value: String
    }
    let body = VisibilityRequest(value: visibility)
    let _: MemoryStatusResponse = try await patch("v3/memories/\(id)/visibility", body: body)
  }

  /// Updates memory read/dismissed status
  func updateMemoryReadStatus(id: String, isRead: Bool? = nil, isDismissed: Bool? = nil)
    async throws -> ServerMemory
  {
    struct UpdateReadRequest: Encodable {
      let isRead: Bool?
      let isDismissed: Bool?

      enum CodingKeys: String, CodingKey {
        case isRead = "is_read"
        case isDismissed = "is_dismissed"
      }
    }
    let body = UpdateReadRequest(isRead: isRead, isDismissed: isDismissed)
    return try await patch("v3/memories/\(id)/read", body: body)
  }

  /// Marks all memories as read
  func markAllMemoriesRead() async throws {
    let _: MemoryStatusResponse = try await post("v3/memories/mark-all-read", body: EmptyBody())
  }

  /// Layer/archive scoped bulk read-state mutations remain disabled until backend semantics exist.
  func markAllMemoriesRead(scope: MemoryLayerScope) async throws {
    throw APIError.unsupportedTierScopedBulkMutation("read-state updates")
  }

  /// Updates visibility of all memories
  func updateAllMemoriesVisibility(visibility: String) async throws {
    struct VisibilityRequest: Encodable {
      let value: String
    }
    let body = VisibilityRequest(value: visibility)
    let _: MemoryStatusResponse = try await patch("v3/memories/visibility", body: body)
  }

  /// Updates visibility of all default-scope memories.
  /// Layer/archive scoped bulk mutations remain disabled until backend semantics exist.
  func updateAllMemoriesVisibility(scope: MemoryLayerScope, visibility: String) async throws {
    if scope == .defaultAccess {
      try await updateAllMemoriesVisibility(visibility: visibility)
      return
    }
    throw APIError.unsupportedTierScopedBulkMutation("visibility updates")
  }

  /// Deletes all memories
  func deleteAllMemories() async throws {
    try await delete("v3/memories")
  }

  /// Deletes all default-scope memories.
  /// Layer/archive scoped bulk mutations remain disabled until backend semantics exist.
  func deleteAllMemories(scope: MemoryLayerScope) async throws {
    if scope == .defaultAccess {
      try await deleteAllMemories()
      return
    }
    throw APIError.unsupportedTierScopedBulkMutation("deletion")
  }

}

/// The create endpoint returns the stored memory, including its authoritative
/// canonical lifecycle. Keep the historical name so callers do not mistake a
/// successful response for an ID-only receipt.
typealias CreateMemoryResponse = ServerMemory

/// One item in a POST /v3/memories/batch payload. Mirrors the `Memory` model
/// in `backend/models/memories.py`. The server honors `category`, so batch
/// imports default to `.system` ("About You") rather than landing in "Manual".
struct MemoryBatchItem: Encodable {
  let content: String
  let visibility: String
  let category: String
  let tags: [String]
  let headline: String?
  let source: String?
  let windowTitle: String?

  init(
    content: String,
    visibility: String = "private",
    category: MemoryCategory = .system,
    tags: [String] = [],
    headline: String? = nil,
    source: String? = nil,
    windowTitle: String? = nil
  ) {
    self.content = content
    self.visibility = visibility
    self.category = category.rawValue
    self.tags = tags
    self.headline = headline
    self.source = source
    self.windowTitle = windowTitle
  }

  enum CodingKeys: String, CodingKey {
    case content, visibility, category, tags, headline, source
    case windowTitle = "window_title"
  }
}

/// Response from POST /v3/memories/batch. The server returns the full
/// created memories list; we only care about `createdCount` for onboarding
/// telemetry, but keep `memories` available for future callers.
struct BatchMemoriesResponse: Decodable {
  let memories: [BatchMemory]
  let createdCount: Int

  enum CodingKeys: String, CodingKey {
    case memories
    case createdCount = "created_count"
  }

  struct BatchMemory: Decodable {
    let id: String
    let content: String
  }
}

struct ImportEvidenceBatch: Encodable {
  let sourceType: String
  let importRunId: String?
  let sourceAccountHash: String?
  let importerVersion: String
  let extractorVersion: String?
  let items: [ImportEvidenceBatchItem]

  init(
    sourceType: String,
    importRunId: String? = nil,
    sourceAccountHash: String? = nil,
    importerVersion: String = "desktop-import-v1",
    extractorVersion: String? = nil,
    items: [ImportEvidenceBatchItem]
  ) {
    self.sourceType = sourceType
    self.importRunId = importRunId
    self.sourceAccountHash = sourceAccountHash
    self.importerVersion = importerVersion
    self.extractorVersion = extractorVersion
    self.items = items
  }

  enum CodingKeys: String, CodingKey {
    case sourceType = "source_type"
    case importRunId = "import_run_id"
    case sourceAccountHash = "source_account_hash"
    case importerVersion = "importer_version"
    case extractorVersion = "extractor_version"
    case items
  }
}

struct ImportEvidenceBatchItem: Encodable, Hashable {
  let externalId: String?
  let occurredAt: Date?
  let title: String?
  let snippet: String?
  let content: String?
  let contentHash: String?
  let metadata: [String: String]
  let clientDeviceId: String?

  init(
    externalId: String? = nil,
    occurredAt: Date? = nil,
    title: String? = nil,
    snippet: String? = nil,
    content: String? = nil,
    contentHash: String? = nil,
    metadata: [String: String] = [:],
    clientDeviceId: String? = nil
  ) {
    self.externalId = externalId
    self.occurredAt = occurredAt
    self.title = title
    self.snippet = snippet
    self.content = content
    self.contentHash = contentHash
    self.metadata = metadata
    self.clientDeviceId = clientDeviceId
  }

  enum CodingKeys: String, CodingKey {
    case externalId = "external_id"
    case occurredAt = "occurred_at"
    case title
    case snippet
    case content
    case contentHash = "content_hash"
    case metadata
    case clientDeviceId = "client_device_id"
  }

  func encode(to encoder: Encoder) throws {
    var container = encoder.container(keyedBy: CodingKeys.self)
    try container.encodeIfPresent(externalId, forKey: .externalId)
    if let occurredAt {
      let formatter = ISO8601DateFormatter()
      formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
      try container.encode(formatter.string(from: occurredAt), forKey: .occurredAt)
    }
    try container.encodeIfPresent(title, forKey: .title)
    try container.encodeIfPresent(snippet, forKey: .snippet)
    try container.encodeIfPresent(content, forKey: .content)
    try container.encodeIfPresent(contentHash, forKey: .contentHash)
    try container.encode(metadata, forKey: .metadata)
    try container.encodeIfPresent(clientDeviceId, forKey: .clientDeviceId)
  }
}

struct ImportEvidenceBatchResponse: Decodable {
  let runId: String
  let artifactsReceived: Int
  let artifactsCreated: Int
  let artifactsDeduped: Int
  let candidatesCreated: Int
  let status: String

  enum CodingKeys: String, CodingKey {
    case runId = "run_id"
    case artifactsReceived = "artifacts_received"
    case artifactsCreated = "artifacts_created"
    case artifactsDeduped = "artifacts_deduped"
    case candidatesCreated = "candidates_created"
    case status
  }
}

struct MemoryStatusResponse: Codable {
  let status: String
}
