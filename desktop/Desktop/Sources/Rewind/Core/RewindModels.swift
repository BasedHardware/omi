import Foundation
import GRDB

// MARK: - Screenshot Model

/// Represents a captured screenshot stored in the Rewind database
struct Screenshot: Codable, FetchableRecord, PersistableRecord, Identifiable, Equatable {
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
        skippedForBattery: Bool = false
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
    }

    // MARK: - Persistence Callbacks

    mutating func didInsert(_ inserted: InsertionSuccess) {
        id = inserted.rowID
    }

    // MARK: - OCR Data Access

    /// Decode the OCR result with bounding boxes
    var ocrResult: OCRResult? {
        guard let jsonString = ocrDataJson,
              let data = jsonString.data(using: .utf8) else {
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
    case ocrFailed(String)
    case screenshotNotFound
    case corruptedVideoChunk(String)

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
    static let shared = RewindSettings()

    private let defaults = UserDefaults.standard

    /// Default apps that should be excluded from screen capture for privacy
    static let defaultExcludedApps: Set<String> = [
        "Omi Computer",        // Our own app - no point capturing ourselves (legacy name)
        "Omi Beta",            // Production app name
        "Omi Dev",             // Development app name
        "Passwords",           // macOS Passwords app
        "1Password",           // 1Password (various versions)
        "1Password 7",
        "Bitwarden",           // Bitwarden
        "LastPass",            // LastPass
        "Dashlane",            // Dashlane
        "Keeper",              // Keeper Password Manager
        "Enpass",              // Enpass
        "KeePassXC",           // KeePassXC
        "Keychain Access",     // macOS Keychain Access
    ]

    @Published var retentionDays: Int {
        didSet {
            defaults.set(retentionDays, forKey: "rewindRetentionDays")
        }
    }

    @Published var captureInterval: Double {
        didSet {
            defaults.set(captureInterval, forKey: "rewindCaptureInterval")
        }
    }

    @Published var ocrRecognitionFast: Bool {
        didSet {
            defaults.set(ocrRecognitionFast, forKey: "rewindOCRFast")
        }
    }

    /// When true, OCR is paused while on battery power to save energy.
    /// Screenshots are still captured but stored without OCR text (isIndexed=false).
    /// OCR backfill runs automatically when AC power is reconnected.
    @Published var pauseOCROnBattery: Bool {
        didSet {
            defaults.set(pauseOCROnBattery, forKey: "rewindPauseOCROnBattery")
        }
    }

    @Published var excludedApps: Set<String> {
        didSet {
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
        self.captureInterval = defaults.object(forKey: "rewindCaptureInterval") as? Double ?? 1.0
        self.ocrRecognitionFast = defaults.object(forKey: "rewindOCRFast") as? Bool ?? true
        self.pauseOCROnBattery = defaults.object(forKey: "rewindPauseOCROnBattery") as? Bool ?? true
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
    }

    /// Check if an app is excluded from screen capture
    func isAppExcluded(_ appName: String) -> Bool {
        excludedApps.contains(appName)
    }

    /// Add an app to the exclusion list
    func excludeApp(_ appName: String) {
        excludedApps.insert(appName)
        // If re-excluding a default app, stop tracking it as removed
        if Self.defaultExcludedApps.contains(appName) {
            removedDefaults.remove(appName)
        }
    }

    /// Remove an app from the exclusion list
    func includeApp(_ appName: String) {
        excludedApps.remove(appName)
        // Track removal of default apps so they don't get re-added on next launch
        if Self.defaultExcludedApps.contains(appName) {
            removedDefaults.insert(appName)
        }
    }

    /// Reset excluded apps to defaults
    func resetToDefaults() {
        excludedApps = Self.defaultExcludedApps
        removedDefaults = []
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
