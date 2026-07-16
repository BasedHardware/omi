import Foundation
import GRDB

// MARK: - Memory Record

/// Database record for memories with bidirectional sync support
/// Stores all memories (extracted, insight, focus-tagged) from both local extraction and backend API
struct MemoryRecord: Codable, FetchableRecord, PersistableRecord, Identifiable {
  var id: Int64?

  // Backend sync fields
  var backendId: String?  // Server memory ID
  var backendSynced: Bool

  // Core ServerMemory fields
  var content: String
  var category: String  // system, interesting, manual
  var tier: String  // short_term, long_term, archive (canonical product layer; API field `layer`)
  var tierIsExplicit: Bool  // true when backend sent layer/tier/memory_tier (legacy rows: false → no badge)
  var tagsJson: String?  // JSON array: ["tips"], ["focus", "focused"]
  var visibility: String
  var reviewed: Bool
  var userReview: Bool?
  var manuallyAdded: Bool
  var scoring: String?
  var source: String?  // desktop, omi, screenshot, phone
  var conversationId: String?

  // Desktop extraction fields
  var screenshotId: Int64?
  var confidence: Double?
  var reasoning: String?
  var sourceApp: String?
  var windowTitle: String?
  var contextSummary: String?
  var currentActivity: String?
  var inputDeviceName: String?
  var headline: String?

  // Capture-device provenance (preserved through SQLite cache round-trip)
  var primaryCaptureDevice: String?
  var captureDeviceIdsJson: String?

  // Status flags
  var isRead: Bool
  var isDismissed: Bool
  var deleted: Bool

  // Timestamps
  var createdAt: Date
  var updatedAt: Date

  static let databaseTableName = "memories"

  // MARK: - Initialization

  init(
    id: Int64? = nil,
    backendId: String? = nil,
    backendSynced: Bool = false,
    content: String,
    category: String = "system",
    tier: String = MemoryLayer.longTerm.rawValue,
    tierIsExplicit: Bool = false,
    tagsJson: String? = nil,
    visibility: String = "private",
    reviewed: Bool = false,
    userReview: Bool? = nil,
    manuallyAdded: Bool = false,
    scoring: String? = nil,
    source: String? = nil,
    conversationId: String? = nil,
    screenshotId: Int64? = nil,
    confidence: Double? = nil,
    reasoning: String? = nil,
    sourceApp: String? = nil,
    windowTitle: String? = nil,
    contextSummary: String? = nil,
    currentActivity: String? = nil,
    inputDeviceName: String? = nil,
    headline: String? = nil,
    primaryCaptureDevice: String? = nil,
    captureDeviceIdsJson: String? = nil,
    isRead: Bool = false,
    isDismissed: Bool = false,
    deleted: Bool = false,
    createdAt: Date = Date(),
    updatedAt: Date = Date()
  ) {
    self.id = id
    self.backendId = backendId
    self.backendSynced = backendSynced
    self.content = content
    self.category = category
    self.tier = tier
    self.tierIsExplicit = tierIsExplicit
    self.tagsJson = tagsJson
    self.visibility = visibility
    self.reviewed = reviewed
    self.userReview = userReview
    self.manuallyAdded = manuallyAdded
    self.scoring = scoring
    self.source = source
    self.conversationId = conversationId
    self.screenshotId = screenshotId
    self.confidence = confidence
    self.reasoning = reasoning
    self.sourceApp = sourceApp
    self.windowTitle = windowTitle
    self.contextSummary = contextSummary
    self.currentActivity = currentActivity
    self.inputDeviceName = inputDeviceName
    self.headline = headline
    self.primaryCaptureDevice = primaryCaptureDevice
    self.captureDeviceIdsJson = captureDeviceIdsJson
    self.isRead = isRead
    self.isDismissed = isDismissed
    self.deleted = deleted
    self.createdAt = createdAt
    self.updatedAt = updatedAt
  }

  // MARK: - Persistence Callbacks

  mutating func didInsert(_ inserted: InsertionSuccess) {
    id = inserted.rowID
  }

  // MARK: - Tag Helpers

  /// Get tags as array
  var tags: [String] {
    guard let json = tagsJson,
      let data = json.data(using: .utf8),
      let array = try? JSONDecoder().decode([String].self, from: data)
    else { return [] }
    return array
  }

  /// Get capture device IDs as array (decoded from JSON column)
  var captureDeviceIds: [String] {
    guard let json = captureDeviceIdsJson,
      let data = json.data(using: .utf8),
      let array = try? JSONDecoder().decode([String].self, from: data)
    else { return [] }
    return array
  }

  /// Encode capture device IDs array to JSON string for persistence (nil if empty)
  private static func encodeCaptureDeviceIds(_ ids: [String]) -> String? {
    guard !ids.isEmpty,
      let data = try? JSONEncoder().encode(ids),
      let json = String(data: data, encoding: .utf8)
    else { return nil }
    return json
  }

  /// Set tags from array
  mutating func setTags(_ tags: [String]) {
    if tags.isEmpty {
      tagsJson = nil
    } else if let data = try? JSONEncoder().encode(tags),
      let json = String(data: data, encoding: .utf8)
    {
      tagsJson = json
    }
  }

  /// Check if memory has a specific tag
  func hasTag(_ tag: String) -> Bool {
    tags.contains(tag)
  }

  /// Check if this is a insight memory
  var isTips: Bool {
    hasTag("insights")
  }

  /// Check if this is a focus memory
  var isFocus: Bool {
    hasTag("focus")
  }

  /// Check if this is a regular memory (not insight or focus)
  var isRegularMemory: Bool {
    !isTips && !isFocus
  }

  // MARK: - Relationships

  static let screenshot = belongsTo(Screenshot.self)

  var screenshot: QueryInterfaceRequest<Screenshot> {
    request(for: MemoryRecord.screenshot)
  }
}

// MARK: - ServerMemory Conversion

extension MemoryRecord {
  /// Create a local record from a ServerMemory (for caching API responses)
  static func from(_ memory: ServerMemory) -> MemoryRecord {
    let tagsJson: String?
    if !memory.tags.isEmpty,
      let data = try? JSONEncoder().encode(memory.tags),
      let json = String(data: data, encoding: .utf8)
    {
      tagsJson = json
    } else {
      tagsJson = nil
    }

    return MemoryRecord(
      backendId: memory.id,
      backendSynced: true,
      content: memory.content,
      category: memory.category.rawValue,
      tier: memory.tier.rawValue,
      tierIsExplicit: memory.tierIsExplicit,
      tagsJson: tagsJson,
      visibility: memory.visibility,
      reviewed: memory.reviewed,
      userReview: memory.userReview,
      manuallyAdded: memory.manuallyAdded,
      scoring: memory.scoring,
      source: memory.source,
      conversationId: memory.conversationId,
      screenshotId: nil,  // Not available from API
      confidence: memory.confidence,
      reasoning: memory.reasoning,
      sourceApp: memory.sourceApp,
      windowTitle: memory.windowTitle,
      contextSummary: memory.contextSummary,
      currentActivity: memory.currentActivity,
      inputDeviceName: memory.inputDeviceName,
      headline: memory.headline,
      primaryCaptureDevice: memory.primaryCaptureDevice,
      captureDeviceIdsJson: encodeCaptureDeviceIds(memory.captureDeviceIds),
      isRead: memory.isRead,
      isDismissed: memory.isDismissed,
      deleted: false,
      createdAt: memory.createdAt,
      updatedAt: memory.updatedAt
    )
  }

  /// Update this record from a ServerMemory (preserving local id and screenshotId)
  mutating func updateFrom(_ memory: ServerMemory) {
    // Update backend sync
    self.backendId = memory.id
    self.backendSynced = true

    // Update core fields
    self.content = memory.content
    self.category = memory.category.rawValue
    self.tier = memory.tier.rawValue
    self.tierIsExplicit = memory.tierIsExplicit
    self.visibility = memory.visibility
    self.reviewed = memory.reviewed
    self.userReview = memory.userReview
    self.manuallyAdded = memory.manuallyAdded
    self.scoring = memory.scoring
    self.source = memory.source
    self.conversationId = memory.conversationId

    // Update tags
    if !memory.tags.isEmpty,
      let data = try? JSONEncoder().encode(memory.tags),
      let json = String(data: data, encoding: .utf8)
    {
      self.tagsJson = json
    } else {
      self.tagsJson = nil
    }

    // Update extraction fields (if provided by API)
    if let confidence = memory.confidence {
      self.confidence = confidence
    }
    if let reasoning = memory.reasoning {
      self.reasoning = reasoning
    }
    if let sourceApp = memory.sourceApp {
      self.sourceApp = sourceApp
    }
    if let contextSummary = memory.contextSummary {
      self.contextSummary = contextSummary
    }
    if let currentActivity = memory.currentActivity {
      self.currentActivity = currentActivity
    }
    if let inputDeviceName = memory.inputDeviceName {
      self.inputDeviceName = inputDeviceName
    }
    if let windowTitle = memory.windowTitle {
      self.windowTitle = windowTitle
    }
    if let headline = memory.headline {
      self.headline = headline
    }

    // Preserve capture-device provenance through cache sync/reload
    self.primaryCaptureDevice = memory.primaryCaptureDevice
    self.captureDeviceIdsJson = Self.encodeCaptureDeviceIds(memory.captureDeviceIds)

    // Update status
    self.isRead = memory.isRead
    self.isDismissed = memory.isDismissed

    // Update timestamp
    self.updatedAt = memory.updatedAt
  }

  /// Merge server-authoritative tier fields without overwriting newer local edits.
  /// Legacy/untiered server rows clear any previously cached canonical tier so
  /// stale rollout metadata cannot keep Short-term/Long-term UI visible.
  @discardableResult
  mutating func mergeAuthoritativeTierFrom(_ memory: ServerMemory) -> Bool {
    guard memory.tierIsExplicit else {
      let changed = tierIsExplicit || tier != MemoryLayer.longTerm.rawValue
      if changed {
        tier = MemoryLayer.longTerm.rawValue
        tierIsExplicit = false
      }
      return changed
    }

    let authoritativeTier = memory.tier.rawValue
    let changed = tier != authoritativeTier || !tierIsExplicit
    if changed {
      tier = authoritativeTier
      tierIsExplicit = true
    }
    return changed
  }

  /// Convert to ServerMemory for UI display
  /// Uses backendId if available, otherwise generates a local ID for unsynced memories
  func toServerMemory() -> ServerMemory? {
    // Use backendId if available, otherwise use local ID prefixed with "local_"
    let memoryId = backendId ?? "local_\(id ?? 0)"

    // Parse category
    let memoryCategory = MemoryCategory(rawValue: category) ?? .system
    guard let memoryLayer = MemoryLayer(rawValue: tier) else {
      logError(
        "MemoryRecord: excluding memory with malformed persisted tier '\(tier)'",
        error: MemoryStorageError.syncFailed("Malformed persisted memory tier")
      )
      return nil
    }

    return ServerMemory(
      id: memoryId,
      content: content,
      category: memoryCategory,
      tier: memoryLayer,
      tierIsExplicit: tierIsExplicit,
      createdAt: createdAt,
      updatedAt: updatedAt,
      conversationId: conversationId,
      reviewed: reviewed,
      userReview: userReview,
      visibility: visibility,
      manuallyAdded: manuallyAdded,
      scoring: scoring,
      source: source,
      confidence: confidence,
      sourceApp: sourceApp,
      contextSummary: contextSummary,
      isRead: isRead,
      isDismissed: isDismissed,
      tags: tags,
      reasoning: reasoning,
      currentActivity: currentActivity,
      inputDeviceName: inputDeviceName,
      windowTitle: windowTitle,
      headline: headline,
      primaryCaptureDevice: primaryCaptureDevice,
      captureDeviceIds: captureDeviceIds
    )
  }
}

// MARK: - ServerMemory Initializer Extension

extension ServerMemory {
  /// Return a display copy that hides canonical lifecycle state for legacy or
  /// not-yet-confirmed users. The persisted cache may briefly contain stale
  /// explicit tiers from earlier builds; UI must not render those until the
  /// current server response confirms canonical lifecycle support.
  func hidingLifecycleExposure() -> ServerMemory {
    guard tierIsExplicit || tier != .longTerm else { return self }
    return ServerMemory(
      id: id,
      content: content,
      category: category,
      tier: .longTerm,
      tierIsExplicit: false,
      createdAt: createdAt,
      updatedAt: updatedAt,
      capturedAt: capturedAt,
      expiresAt: expiresAt,
      conversationId: conversationId,
      reviewed: reviewed,
      userReview: userReview,
      visibility: visibility,
      manuallyAdded: manuallyAdded,
      scoring: scoring,
      source: source,
      confidence: confidence,
      sourceApp: sourceApp,
      contextSummary: contextSummary,
      isRead: isRead,
      isDismissed: isDismissed,
      tags: tags,
      reasoning: reasoning,
      currentActivity: currentActivity,
      inputDeviceName: inputDeviceName,
      windowTitle: windowTitle,
      headline: headline,
      primaryCaptureDevice: primaryCaptureDevice,
      captureDeviceIds: captureDeviceIds
    )
  }

  /// Initialize from individual fields (for creating from MemoryRecord)
  init(
    id: String,
    content: String,
    category: MemoryCategory,
    tier: MemoryLayer = .longTerm,
    tierIsExplicit: Bool = false,
    createdAt: Date,
    updatedAt: Date,
    capturedAt: Date? = nil,
    expiresAt: Date? = nil,
    conversationId: String?,
    reviewed: Bool,
    userReview: Bool?,
    visibility: String,
    manuallyAdded: Bool,
    scoring: String?,
    source: String?,
    confidence: Double?,
    sourceApp: String?,
    contextSummary: String?,
    isRead: Bool,
    isDismissed: Bool,
    tags: [String],
    reasoning: String?,
    currentActivity: String?,
    inputDeviceName: String?,
    windowTitle: String? = nil,
    headline: String? = nil,
    primaryCaptureDevice: String? = nil,
    captureDeviceIds: [String] = []
  ) {
    self.id = id
    self.content = content
    self.category = category
    self.tier = tier
    self.tierIsExplicit = tierIsExplicit
    self.createdAt = createdAt
    self.updatedAt = updatedAt
    self.capturedAt = capturedAt
    self.expiresAt = expiresAt
    self.conversationId = conversationId
    self.reviewed = reviewed
    self.userReview = userReview
    self.visibility = visibility
    self.manuallyAdded = manuallyAdded
    self.scoring = scoring
    self.source = source
    self.confidence = confidence
    self.sourceApp = sourceApp
    self.contextSummary = contextSummary
    self.isRead = isRead
    self.isDismissed = isDismissed
    self.tags = tags
    self.reasoning = reasoning
    self.currentActivity = currentActivity
    self.inputDeviceName = inputDeviceName
    self.windowTitle = windowTitle
    self.headline = headline
    self.primaryCaptureDevice = primaryCaptureDevice
    self.captureDeviceIds = captureDeviceIds
  }
}

// MARK: - TableDocumented

extension MemoryRecord: TableDocumented {
  static var tableDescription: String { ChatPrompts.tableAnnotations["memories"]! }
  static var columnDescriptions: [String: String] { ChatPrompts.columnAnnotations["memories"] ?? [:] }
}

// MARK: - Memory Storage Error

enum MemoryStorageError: LocalizedError {
  case databaseNotInitialized
  case recordNotFound
  case syncFailed(String)

  var errorDescription: String? {
    switch self {
    case .databaseNotInitialized:
      return "Memory storage database is not initialized"
    case .recordNotFound:
      return "Memory record not found"
    case .syncFailed(let message):
      return "Sync failed: \(message)"
    }
  }
}
