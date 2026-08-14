import Combine
import Foundation
@preconcurrency import GRDB

// MARK: - Screenshot Model

/// Represents a captured screenshot stored in the Rewind database
///
/// **`MutablePersistableRecord`, deliberately.** `didInsert` is how this row learns the rowid
/// SQLite generated for it, and capture keys everything that follows the insert — embeddings,
/// canonical-memory linkage — to that id. `PersistableRecord` declares `didInsert` non-mutating
/// and ships an empty default, so a `mutating func didInsert` on a `PersistableRecord` struct is
/// not a witness for it: it compiles, never runs, and every insert quietly returns `id == nil`.
struct Screenshot: Codable, FetchableRecord, MutablePersistableRecord, Identifiable, Equatable {
  /// Database row ID (auto-generated)
  var id: Int64?

  /// When the screenshot was captured
  var timestamp: Date

  /// Name of the application that was active
  var appName: String

  /// Title of the window (if available)
  var windowTitle: String?

  /// Relative path to the JPEG image file (legacy, nil for video storage)
  var imagePath: String?

  /// Relative path to the video chunk file (new video storage)
  var videoChunkPath: String?

  /// Frame index within the video chunk
  var frameOffset: Int?

  /// Extracted OCR text (nullable until indexed)
  var ocrText: String?

  /// JSON-encoded OCR data with bounding boxes
  var ocrDataJson: String?

  /// Whether OCR has been completed
  var isIndexed: Bool

  /// Focus status at capture time ("focused" | "distracted" | nil)
  var focusStatus: String?

  /// JSON-encoded array of extracted tasks
  var extractedTasksJson: String?

  /// JSON-encoded advice object
  var adviceJson: String?

  /// Whether OCR was skipped because the Mac was on battery (needs backfill when AC reconnects)
  var skippedForBattery: Bool

  /// User-facing computer name captured with this screenshot (nil when provenance is unknown)
  var deviceName: String?

  /// Stable per-installation capture identity used by the canonical memory system
  var clientDeviceId: String?

  static let databaseTableName = "screenshots"

  // MARK: - Storage Type

  /// Whether this screenshot uses video chunk storage (vs legacy JPEG)
  var usesVideoStorage: Bool {
    videoChunkPath != nil && frameOffset != nil
  }

  // MARK: - Initialization

  init(
    id: Int64? = nil,
    timestamp: Date = Date(),
    appName: String,
    windowTitle: String? = nil,
    imagePath: String? = nil,
    videoChunkPath: String? = nil,
    frameOffset: Int? = nil,
    ocrText: String? = nil,
    ocrDataJson: String? = nil,
    isIndexed: Bool = false,
    focusStatus: String? = nil,
    extractedTasksJson: String? = nil,
    adviceJson: String? = nil,
    skippedForBattery: Bool = false,
    deviceName: String? = nil,
    clientDeviceId: String? = nil
  ) {
    self.id = id
    self.timestamp = timestamp
    self.appName = appName
    self.windowTitle = windowTitle
    self.imagePath = imagePath
    self.videoChunkPath = videoChunkPath
    self.frameOffset = frameOffset
    self.ocrText = ocrText
    self.ocrDataJson = ocrDataJson
    self.isIndexed = isIndexed
    self.focusStatus = focusStatus
    self.extractedTasksJson = extractedTasksJson
    self.adviceJson = adviceJson
    self.skippedForBattery = skippedForBattery
    self.deviceName = deviceName
    self.clientDeviceId = clientDeviceId
  }

  // MARK: - Persistence Callbacks

  mutating func didInsert(_ inserted: InsertionSuccess) {
    id = inserted.rowID
  }

  // MARK: - OCR Data Access

  /// Decode the OCR result with bounding boxes
  var ocrResult: OCRResult? {
    guard let jsonString = ocrDataJson,
      let data = jsonString.data(using: .utf8)
    else {
      return nil
    }
    return try? JSONDecoder().decode(OCRResult.self, from: data)
  }

  /// Get text blocks that match a search query
  func matchingBlocks(for query: String) -> [OCRTextBlock] {
    return ocrResult?.blocksContaining(query) ?? []
  }

  /// Get a context snippet for a search query
  func contextSnippet(for query: String) -> String? {
    return ocrResult?.contextSnippet(for: query)
  }
}

// MARK: - Search Result

/// A search result containing a screenshot and match information
struct ScreenshotSearchResult: Identifiable, Equatable {
  let screenshot: Screenshot
  let matchedText: String?
  let contextSnippet: String?
  let matchingBlocks: [OCRTextBlock]

  var id: Int64? { screenshot.id }

  init(screenshot: Screenshot, query: String? = nil) {
    self.screenshot = screenshot
    self.matchedText = query

    if let query = query, !query.isEmpty {
      self.contextSnippet = screenshot.contextSnippet(for: query)
      self.matchingBlocks = screenshot.matchingBlocks(for: query)
    } else {
      self.contextSnippet = nil
      self.matchingBlocks = []
    }
  }
}

// MARK: - Search Result Group

/// A group of search results from the same app/window context within a time window
struct SearchResultGroup: Identifiable, Equatable {
  /// Unique identifier for the group
  let id: String

  /// The representative screenshot (first encountered in relevance order)
  let representativeScreenshot: Screenshot

  /// All screenshots in this group, sorted by timestamp descending
  let screenshots: [Screenshot]

  /// App name for this group
  var appName: String { representativeScreenshot.appName }

  /// Window title for this group
  var windowTitle: String? { representativeScreenshot.windowTitle }

  /// Number of screenshots in the group
  var count: Int { screenshots.count }

  /// Earliest timestamp in the group
  var startTime: Date {
    screenshots.map { $0.timestamp }.min() ?? representativeScreenshot.timestamp
  }

  /// Latest timestamp in the group
  var endTime: Date {
    screenshots.map { $0.timestamp }.max() ?? representativeScreenshot.timestamp
  }

  /// Formatted time range for display
  var formattedTimeRange: String {
    let formatter = DateFormatter()
    formatter.dateStyle = .medium
    formatter.timeStyle = .short

    let start = formatter.string(from: startTime)

    // If same minute, just show one time
    let calendar = Calendar.current
    if calendar.isDate(startTime, equalTo: endTime, toGranularity: .minute) {
      return start
    }

    // If same day, show time range
    if calendar.isDate(startTime, inSameDayAs: endTime) {
      let timeFormatter = DateFormatter()
      timeFormatter.timeStyle = .short
      return "\(start) - \(timeFormatter.string(from: endTime))"
    }

    // Different days
    return "\(start) - \(formatter.string(from: endTime))"
  }

  static func == (lhs: SearchResultGroup, rhs: SearchResultGroup) -> Bool {
    lhs.id == rhs.id
  }
}

// MARK: - Search Result Grouping

/// Helper struct for tracking screenshot sessions during grouping
private struct ScreenshotSession {
  var screenshots: [Screenshot]
  var minTime: Date
  var maxTime: Date

  mutating func add(_ screenshot: Screenshot) {
    screenshots.append(screenshot)
    if screenshot.timestamp < minTime {
      minTime = screenshot.timestamp
    }
    if screenshot.timestamp > maxTime {
      maxTime = screenshot.timestamp
    }
  }

  func contains(timestamp: Date, within window: TimeInterval) -> Bool {
    let expandedMin = minTime.addingTimeInterval(-window)
    let expandedMax = maxTime.addingTimeInterval(window)
    return timestamp >= expandedMin && timestamp <= expandedMax
  }
}

extension Array where Element == Screenshot {
  /// Group screenshots by app/window context within a time window
  /// - Parameter timeWindowSeconds: Maximum gap between screenshots to be considered same group
  /// - Returns: Array of grouped results, preserving relevance order
  func groupedByContext(timeWindowSeconds: TimeInterval = 30) -> [SearchResultGroup] {
    guard !isEmpty else { return [] }

    // Track groups by context key
    // Each context can have multiple sessions (separated by time gaps)
    var contextSessions: [String: [ScreenshotSession]] = [:]
    var groupOrder: [(key: String, sessionIndex: Int)] = []

    for screenshot in self {
      let key = "\(screenshot.appName)|\(screenshot.windowTitle ?? "")"

      if contextSessions[key] == nil {
        // First screenshot for this context - create new session
        let session = ScreenshotSession(
          screenshots: [screenshot],
          minTime: screenshot.timestamp,
          maxTime: screenshot.timestamp
        )
        contextSessions[key] = [session]
        groupOrder.append((key: key, sessionIndex: 0))
      } else {
        // Check if this screenshot fits in an existing session
        var foundSession = false
        for i in 0..<contextSessions[key]!.count {
          if contextSessions[key]![i].contains(timestamp: screenshot.timestamp, within: timeWindowSeconds) {
            contextSessions[key]![i].add(screenshot)
            foundSession = true
            break
          }
        }

        if !foundSession {
          // Start a new session for this context
          let session = ScreenshotSession(
            screenshots: [screenshot],
            minTime: screenshot.timestamp,
            maxTime: screenshot.timestamp
          )
          let newIndex = contextSessions[key]!.count
          contextSessions[key]!.append(session)
          groupOrder.append((key: key, sessionIndex: newIndex))
        }
      }
    }

    // Build result groups in the order they were first encountered
    return groupOrder.compactMap { order -> SearchResultGroup? in
      guard let session = contextSessions[order.key]?[order.sessionIndex] else { return nil }

      // Sort screenshots by timestamp descending (most recent first)
      let sortedScreenshots = session.screenshots.sorted { $0.timestamp > $1.timestamp }
      guard let representative = sortedScreenshots.first else { return nil }

      return SearchResultGroup(
        id: "\(order.key)|\(order.sessionIndex)",
        representativeScreenshot: representative,
        screenshots: sortedScreenshots
      )
    }
  }
}

// MARK: - Rewind Error Types

enum RewindError: LocalizedError {
  case databaseNotInitialized
  case databaseCorrupted(message: String)
  case invalidImage
  case storageError(String)
  /// A storage failure that preserves the underlying OS error (e.g. an
  /// AVAssetWriter disk-out-of-space failure). Keeping the wrapped `NSError`
  /// lets the Sentry classifier recognize environmental disk failures
  /// ("The file couldn't be saved") and collapse them into breadcrumbs instead
  /// of flooding Sentry with unactionable error clusters.
  case storageWriteFailed(String, underlying: Error)
  case ocrFailed(String)
  case screenshotNotFound
  case corruptedVideoChunk(String)

  /// The wrapped OS error, when this error carries one.
  var underlyingError: Error? {
    if case .storageWriteFailed(_, let underlying) = self { return underlying }
    return nil
  }

  var errorDescription: String? {
    switch self {
    case .databaseNotInitialized:
      return "Rewind database is not initialized"
    case .databaseCorrupted(let message):
      return "Database corrupted: \(message)"
    case .invalidImage:
      return "Invalid image data"
    case .storageError(let message):
      return "Storage error: \(message)"
    case .storageWriteFailed(let message, let underlying):
      return "Storage error: \(message): \(underlying.localizedDescription)"
    case .ocrFailed(let message):
      return "OCR failed: \(message)"
    case .screenshotNotFound:
      return "Screenshot not found"
    case .corruptedVideoChunk(let path):
      return "Video chunk corrupted: \(path)"
    }
  }
}

// MARK: - Video Chunk Info

/// Info about a video chunk file for database rebuild
struct VideoChunkInfo {
  let filename: String
  let relativePath: String
  let fullPath: URL
}

// MARK: - Rewind Settings

/// Settings for the Rewind feature
class RewindSettings: ObservableObject {
  nonisolated(unsafe) static let shared = RewindSettings()

  private let defaults = UserDefaults.standard
  private var ownerChangeCancellable: AnyCancellable?
  static let batteryCaptureIntervalMultiplier = 3.0

  /// Default apps that should be excluded from screen capture for privacy
  static let defaultExcludedApps: Set<String> = [
    "Omi Computer",  // Our own app - no point capturing ourselves (legacy name)
    "Omi Beta",  // Legacy production app name
    "Omi",  // Production app name
    "Omi Dev",  // Development app name
    "Passwords",  // macOS Passwords app
    "1Password",  // 1Password (various versions)
    "1Password 7",
    "Bitwarden",  // Bitwarden
    "LastPass",  // LastPass
    "Dashlane",  // Dashlane
    "Keeper",  // Keeper Password Manager
    "Enpass",  // Enpass
    "KeePassXC",  // KeePassXC
    "Keychain Access",  // macOS Keychain Access
  ]

  /// The retention setting that means "never delete a captured frame".
  ///
  /// **This is what makes an all-time Rewind possible at all.** Every other value here is a
  /// deletion window: the cleanup pass runs `DELETE FROM screenshots WHERE timestamp < cutoff` and
  /// removes the backing video chunks from disk, so on the shipped 7-day default a Rewind timeline
  /// physically cannot reach further back than a week no matter what the UI is willing to draw.
  /// Zero is the sentinel rather than a large day count because "3,650 days" is still a promise the
  /// cleanup would eventually break, and because it stores as a plain `Int` in the same key.
  static let unlimitedRetentionDays = 0

  @Published var retentionDays: Int {
    didSet {
      defaults.set(retentionDays, forKey: "rewindRetentionDays")
    }
  }

  /// Whether capture is kept forever.
  var keepsEverything: Bool { Self.isUnlimited(retentionDays: retentionDays) }

  /// A retention day count that promises never to delete.
  ///
  /// Non-positive rather than `== 0` so a value that arrives from an older build, a corrupted
  /// default, or a hand-edited plist can only ever fail *safe* — an unreadable retention setting
  /// keeps the user's history instead of silently erasing it.
  static func isUnlimited(retentionDays: Int) -> Bool { retentionDays <= unlimitedRetentionDays }

  /// The instant before which capture may be deleted — or `nil` when nothing may be.
  ///
  /// Pure and static so the boundary between "keep everything" and "prune at N days" is testable
  /// without a database, a clock, or the indexer that calls it.
  static func retentionCutoff(
    retentionDays: Int,
    now: Date = Date(),
    calendar: Calendar = .current
  ) -> Date? {
    guard !isUnlimited(retentionDays: retentionDays) else { return nil }
    return calendar.date(byAdding: .day, value: -retentionDays, to: now)
  }

  @Published var captureInterval: Double {
    didSet {
      defaults.set(captureInterval, forKey: "rewindCaptureInterval")
    }
  }

  @Published var excludedApps: Set<String> {
    didSet {
      for appName in oldValue.symmetricDifference(excludedApps) {
        RewindCaptureExclusionGeneration.setExcluded(
          appName, excluded: excludedApps.contains(appName))
      }
      let array = Array(excludedApps)
      defaults.set(array, forKey: "rewindExcludedApps")
    }
  }

  /// Tracks default apps the user explicitly chose to un-exclude.
  /// This prevents them from being re-added on future launches.
  private var removedDefaults: Set<String> {
    didSet {
      defaults.set(Array(removedDefaults), forKey: "rewindRemovedDefaultApps")
    }
  }

  private init() {
    // Load settings with defaults
    self.retentionDays = defaults.object(forKey: "rewindRetentionDays") as? Int ?? 7
    self.captureInterval = defaults.object(forKey: "rewindCaptureInterval") as? Double ?? 3.0
    self.removedDefaults = Set(defaults.array(forKey: "rewindRemovedDefaultApps") as? [String] ?? [])

    // Load excluded apps, merging in any new defaults
    if let savedApps = defaults.array(forKey: "rewindExcludedApps") as? [String] {
      var apps = Set(savedApps)
      // Add any new defaults that the user hasn't explicitly removed
      let newDefaults = Self.defaultExcludedApps.subtracting(apps).subtracting(removedDefaults)
      apps.formUnion(newDefaults)
      self.excludedApps = apps
    } else {
      self.excludedApps = Self.defaultExcludedApps
    }
    RewindCaptureExclusionGeneration.setInitialExcludedApps(self.excludedApps)

    // A purge is local and deterministic, but file cleanup can fail transiently
    // (for example while RewindStorage is still initializing).  Retry durable
    // work from the next launch instead of silently leaving excluded pixels on
    // disk.  This does not alter capture cadence or retention behavior.
    // Pending markers are owner-scoped so a failed purge for account A cannot
    // run against account B's store after an account switch.
    if let ownerID = RuntimeOwnerIdentity.currentOwnerId() {
      let pending = RewindPendingContextBucketPurgeJournal.pending(ownerID: ownerID)
      if !pending.isEmpty {
        Task { @MainActor in
          await Self.retryPendingContextBucketPurges(pending, ownerID: ownerID)
        }
      }
    }

    ownerChangeCancellable = NotificationCenter.default.publisher(for: .runtimeOwnerDidChange)
      .receive(on: DispatchQueue.main)
      .sink { _ in
        Task { @MainActor in
          await Self.rearmPendingContextBucketPurgesForCurrentOwner()
        }
      }
  }

  /// Check if an app is excluded from screen capture
  func isAppExcluded(_ appName: String) -> Bool {
    excludedApps.contains(appName)
  }

  func effectiveCaptureInterval(isOnBattery: Bool) -> Double {
    isOnBattery ? captureInterval * Self.batteryCaptureIntervalMultiplier : captureInterval
  }

  /// Add an app to the exclusion list
  @MainActor
  func excludeApp(_ appName: String) {
    excludedApps.insert(appName)
    // If re-excluding a default app, stop tracking it as removed
    if Self.defaultExcludedApps.contains(appName) {
      removedDefaults.remove(appName)
    }
    guard ContextBucketsFeature.isEnabled else { return }
    guard let ownerID = RuntimeOwnerIdentity.currentOwnerId() else { return }
    // Persist the retry marker before scheduling async storage work.
    RewindPendingContextBucketPurgeJournal.enqueue(appName: appName, ownerID: ownerID)
    Task { @MainActor in
      do {
        _ = try await ContextBucketStore.shared.purgeExcludedApp(appName)
        RewindPendingContextBucketPurgeJournal.complete(appName: appName, ownerID: ownerID)
      } catch {
        logError("RewindSettings: purge-on-exclude failed", error: error)
      }
    }
  }

  @MainActor
  static func rearmPendingContextBucketPurgesForCurrentOwner() async {
    guard let ownerID = RuntimeOwnerIdentity.currentOwnerId() else { return }
    let pending = RewindPendingContextBucketPurgeJournal.pending(ownerID: ownerID)
    guard !pending.isEmpty else { return }
    await retryPendingContextBucketPurges(pending, ownerID: ownerID)
  }

  private static func retryPendingContextBucketPurges(_ pending: Set<String>, ownerID: String) async {
    guard await MainActor.run(body: { ContextBucketsFeature.isEnabled }) else { return }
    guard RuntimeOwnerIdentity.currentOwnerId() == ownerID else { return }
    for appName in pending {
      guard RuntimeOwnerIdentity.currentOwnerId() == ownerID else { return }
      do {
        _ = try await ContextBucketStore.shared.purgeExcludedApp(appName)
        RewindPendingContextBucketPurgeJournal.complete(appName: appName, ownerID: ownerID)
      } catch {
        logError("RewindSettings: deferred purge-on-exclude failed", error: error)
      }
    }
  }

  /// Remove an app from the exclusion list
  func includeApp(_ appName: String) {
    excludedApps.remove(appName)
    // Track removal of default apps so they don't get re-added on next launch
    if Self.defaultExcludedApps.contains(appName) {
      removedDefaults.insert(appName)
    }
    // A flag-off caller may have recorded the crash-safe marker before the
    // asynchronous feature check ran.  Do not leave inert test/legacy markers;
    // retain a real flag-on marker so a failed purge is still retried.
    Task { @MainActor in
      guard !ContextBucketsFeature.isEnabled else { return }
      if let ownerID = RuntimeOwnerIdentity.currentOwnerId() {
        RewindPendingContextBucketPurgeJournal.complete(appName: appName, ownerID: ownerID)
      }
    }
  }

  /// Reset excluded apps to defaults
  func resetToDefaults() {
    excludedApps = Self.defaultExcludedApps
    removedDefaults = []
  }
}

/// Owner-scoped retry journal for context-bucket purge-on-exclude. A global
/// string-array marker would let account A's failed purge run against account B
/// after an owner switch; this map keeps retries bound to the originating owner.
enum RewindPendingContextBucketPurgeJournal {
  private static let defaultsKey = "rewindPendingContextBucketPurges"

  private final class State: @unchecked Sendable {
    let lock = NSLock()
  }

  private static let state = State()

  static func enqueue(appName: String, ownerID: String) {
    let name = appName.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !name.isEmpty, !ownerID.isEmpty else { return }
    withLock {
      var pending = loadOwnerScoped(migratingLegacyTo: ownerID)
      pending[ownerID, default: []].append(name)
      pending[ownerID] = Array(Set(pending[ownerID] ?? [])).sorted()
      save(pending)
    }
  }

  static func pending(ownerID: String) -> Set<String> {
    withLock {
      Set(loadOwnerScoped(migratingLegacyTo: ownerID)[ownerID] ?? [])
    }
  }

  static func complete(appName: String, ownerID: String) {
    let name = appName.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !name.isEmpty, !ownerID.isEmpty else { return }
    withLock {
      var pending = loadOwnerScoped(migratingLegacyTo: ownerID)
      guard var ownerPending = pending[ownerID] else { return }
      ownerPending.removeAll { $0 == name }
      if ownerPending.isEmpty {
        pending.removeValue(forKey: ownerID)
      } else {
        pending[ownerID] = ownerPending
      }
      save(pending)
    }
  }

  private static func withLock<T>(_ body: () -> T) -> T {
    state.lock.lock()
    defer { state.lock.unlock() }
    return body()
  }

  private static func loadOwnerScoped(migratingLegacyTo ownerID: String = "") -> [String: [String]] {
    let defaults = UserDefaults.standard
    if let legacy = defaults.stringArray(forKey: defaultsKey) {
      let names = Set(legacy.map { $0.trimmingCharacters(in: .whitespacesAndNewlines) })
        .filter { !$0.isEmpty }
      let migrated = names.isEmpty || ownerID.isEmpty ? [:] : [ownerID: names.sorted()]
      save(migrated)
      return migrated
    }
    guard let data = defaults.data(forKey: defaultsKey),
      let pending = try? JSONDecoder().decode([String: [String]].self, from: data)
    else { return [:] }
    return pending
  }

  private static func save(_ pending: [String: [String]]) {
    let defaults = UserDefaults.standard
    guard !pending.isEmpty,
      let data = try? JSONEncoder().encode(pending)
    else {
      defaults.removeObject(forKey: defaultsKey)
      return
    }
    defaults.set(data, forKey: defaultsKey)
  }
}

// MARK: - Date Formatting Extensions

extension Screenshot {
  /// Formatted date string for display
  var formattedDate: String {
    let formatter = DateFormatter()
    formatter.dateStyle = .medium
    formatter.timeStyle = .short
    return formatter.string(from: timestamp)
  }

  /// Compact formatted date for bottom controls (shorter format)
  var formattedDateCompact: String {
    let formatter = DateFormatter()
    formatter.dateFormat = "MMM d, h:mm a"
    return formatter.string(from: timestamp)
  }

  /// Time-only string for timeline display
  var formattedTime: String {
    let formatter = DateFormatter()
    formatter.dateFormat = "HH:mm:ss"
    return formatter.string(from: timestamp)
  }

  /// Day string for grouping
  var dayString: String {
    let formatter = DateFormatter()
    formatter.dateFormat = "yyyy-MM-dd"
    return formatter.string(from: timestamp)
  }
}

// MARK: - TableDocumented

extension Screenshot: TableDocumented {
  static var tableDescription: String { ChatPrompts.tableAnnotations["screenshots"]! }
  static var columnDescriptions: [String: String] { ChatPrompts.columnAnnotations["screenshots"] ?? [:] }
}
