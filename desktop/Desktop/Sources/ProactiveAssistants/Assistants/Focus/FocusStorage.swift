import Foundation

/// Stored focus session with additional metadata
struct StoredFocusSession: Codable, Identifiable {
    let id: String
    let status: FocusStatus
    let appOrSite: String
    let description: String
    let message: String?
    let createdAt: Date
    let durationSeconds: Int?
    let isSynced: Bool

    init(
        id: String = UUID().uuidString,
        status: FocusStatus,
        appOrSite: String,
        description: String,
        message: String? = nil,
        createdAt: Date = Date(),
        durationSeconds: Int? = nil,
        isSynced: Bool = false
    ) {
        self.id = id
        self.status = status
        self.appOrSite = appOrSite
        self.description = description
        self.message = message
        self.createdAt = createdAt
        self.durationSeconds = durationSeconds
        self.isSynced = isSynced
    }

    func withSynced(_ synced: Bool) -> StoredFocusSession {
        StoredFocusSession(
            id: id,
            status: status,
            appOrSite: appOrSite,
            description: description,
            message: message,
            createdAt: createdAt,
            durationSeconds: durationSeconds,
            isSynced: synced
        )
    }
}

/// Focus statistics for a day
struct FocusDayStats {
    let date: Date
    let focusedMinutes: Int
    let distractedMinutes: Int
    let sessionCount: Int
    let focusedCount: Int
    let distractedCount: Int
    let topDistractions: [(appOrSite: String, totalSeconds: Int, count: Int)]

    /// Focus rate as a percentage (0-100), based on time spent
    var focusRate: Double {
        let total = focusedMinutes + distractedMinutes
        guard total > 0 else { return 0 }
        return Double(focusedMinutes) / Double(total) * 100
    }
}

/// Local storage manager for focus session history
@MainActor
class FocusStorage: ObservableObject {
    static let shared = FocusStorage()

    @Published private(set) var sessions: [StoredFocusSession] = []
    @Published private(set) var currentStatus: FocusStatus?
    @Published private(set) var currentApp: String?

    // MARK: - Real-time Status Properties

    /// The currently detected app (updated immediately on app switch, before analysis)
    @Published private(set) var detectedAppName: String?

    /// When the analysis delay period will end (nil if not in delay)
    @Published private(set) var delayEndTime: Date?

    /// When the analysis cooldown period will end (nil if not in cooldown)
    @Published private(set) var cooldownEndTime: Date?

    private let storageKey = "omi.focus.sessions"
    private let maxStoredSessions = 500

    private init() {
        // First load from UserDefaults cache for quick startup
        loadFromUserDefaultsCache()

        // Then load from SQLite (authoritative source) in background
        Task {
            await loadFromSQLite()
        }
    }

    // MARK: - Real-time Status Updates

    /// Update the detected app name (called immediately on app switch)
    func updateDetectedApp(_ appName: String?) {
        detectedAppName = appName
    }

    /// Update the delay end time (called when delay period starts/ends)
    func updateDelayEndTime(_ endTime: Date?) {
        delayEndTime = endTime
    }

    /// Update the cooldown end time (called by FocusAssistant when cooldown starts/ends)
    func updateCooldownEndTime(_ endTime: Date?) {
        cooldownEndTime = endTime
    }

    /// Clear all real-time status (called when monitoring stops)
    func clearRealtimeStatus() {
        detectedAppName = nil
        delayEndTime = nil
        cooldownEndTime = nil
    }

    // MARK: - Public Methods

    /// Add a new session from screen analysis
    func addSession(from analysis: ScreenAnalysis) {
        let session = StoredFocusSession(
            status: analysis.status,
            appOrSite: analysis.appOrSite,
            description: analysis.description,
            message: analysis.message
        )

        // Update status before inserting session to reduce @Published change count
        // (insert triggers sessions change, so update others only if different)
        if currentStatus != analysis.status {
            currentStatus = analysis.status
        }
        if currentApp != analysis.appOrSite {
            currentApp = analysis.appOrSite
        }

        sessions.insert(session, at: 0)

        // Trim if needed
        if sessions.count > maxStoredSessions {
            sessions = Array(sessions.prefix(maxStoredSessions))
        }

        saveToStorage()
    }

    /// Get today's sessions
    var todaySessions: [StoredFocusSession] {
        let calendar = Calendar.current
        let today = calendar.startOfDay(for: Date())
        return sessions.filter { calendar.isDate($0.createdAt, inSameDayAs: today) }
    }

    /// Compute duration for each session based on time until the next session.
    /// Sessions array is newest-first; the most recent session's duration is `now - createdAt`.
    private func computeStats(for sessionList: [StoredFocusSession]) -> FocusDayStats {
        var focusedSeconds = 0
        var distractedSeconds = 0
        var focusedCount = 0
        var distractedCount = 0
        var distractionMap: [String: (seconds: Int, count: Int)] = [:]

        // Sessions are newest-first, so iterate and compute duration from each session
        // to the next one (which is the one that came before it chronologically).
        let now = Date()
        for i in 0..<sessionList.count {
            let session = sessionList[i]
            // Duration = time from this session's start until the next session starts (or now)
            let endTime: Date
            if i == 0 {
                // Most recent session — duration extends to now
                endTime = now
            } else {
                // Ended when the next (more recent) session started
                endTime = sessionList[i - 1].createdAt
            }
            let duration = max(0, Int(endTime.timeIntervalSince(session.createdAt)))

            switch session.status {
            case .focused:
                focusedCount += 1
                focusedSeconds += duration
            case .distracted:
                distractedCount += 1
                distractedSeconds += duration
                let current = distractionMap[session.appOrSite] ?? (0, 0)
                distractionMap[session.appOrSite] = (current.seconds + duration, current.count + 1)
            }
        }

        let topDistractions = distractionMap
            .map { (appOrSite: $0.key, totalSeconds: $0.value.seconds, count: $0.value.count) }
            .sorted { $0.totalSeconds > $1.totalSeconds }
            .prefix(5)

        return FocusDayStats(
            date: Date(),
            focusedMinutes: focusedSeconds / 60,
            distractedMinutes: distractedSeconds / 60,
            sessionCount: sessionList.count,
            focusedCount: focusedCount,
            distractedCount: distractedCount,
            topDistractions: Array(topDistractions)
        )
    }

    /// Get all-time statistics
    var allTimeStats: FocusDayStats {
        computeStats(for: sessions)
    }

    /// Get today's statistics
    var todayStats: FocusDayStats {
        computeStats(for: todaySessions)
    }

    /// Delete a session
    func deleteSession(_ id: String) {
        if let index = sessions.firstIndex(where: { $0.id == id }) {
            let session = sessions[index]
            sessions.remove(at: index)
            saveToStorage()

            Task {
                // Delete from SQLite (focus_sessions and memories tables)
                if let sqliteId = Int64(id) {
                    // Unsynced session — id is the SQLite row ID
                    try? await ProactiveStorage.shared.deleteFocusSession(id: sqliteId)
                } else if session.isSynced {
                    // Synced session — id is the backend memory ID
                    try? await MemoryStorage.shared.deleteMemoryByBackendId(id)
                }

                // Delete from backend
                if session.isSynced {
                    await deleteFromBackend(id)
                }
            }
        }
    }

    /// Clear all sessions
    func clearAll() {
        sessions = []
        currentStatus = nil
        currentApp = nil
        saveToStorage()
    }

    /// Get sessions for a specific date
    func sessions(for date: Date) -> [StoredFocusSession] {
        let calendar = Calendar.current
        return sessions.filter { calendar.isDate($0.createdAt, inSameDayAs: date) }
    }

    /// Refresh focus sessions from local SQLite database
    /// Note: SQLite is the authoritative local source. Backend sync happens when new events are created.
    func refreshFromBackend() async {
        await loadFromSQLite()
    }

    // MARK: - Private Methods

    /// Quick load from UserDefaults cache (called synchronously on init)
    private func loadFromUserDefaultsCache() {
        guard let data = UserDefaults.standard.data(forKey: storageKey) else {
            return
        }

        do {
            let decoder = JSONDecoder()
            decoder.dateDecodingStrategy = .iso8601
            sessions = try decoder.decode([StoredFocusSession].self, from: data)

            // Update current status from most recent session
            if let latest = sessions.first {
                currentStatus = latest.status
                currentApp = latest.appOrSite
            }
        } catch {
            logError("Failed to load focus sessions from cache", error: error)
        }
    }

    /// Load sessions from SQLite (authoritative source)
    private func loadFromSQLite() async {
        do {
            // Get all focus sessions from SQLite (not just today - get recent ones)
            let calendar = Calendar.current
            let startDate = calendar.date(byAdding: .day, value: -30, to: Date()) ?? Date()
            let endDate = Date()

            let sqliteSessions = try await ProactiveStorage.shared.getFocusSessions(
                from: startDate,
                to: endDate,
                limit: maxStoredSessions
            )

            // Convert to StoredFocusSession
            let converted = sqliteSessions.map { record in
                StoredFocusSession(
                    id: record.backendId ?? String(record.id ?? 0),
                    status: record.isFocused ? .focused : .distracted,
                    appOrSite: record.appOrSite,
                    description: record.description,
                    message: record.message,
                    createdAt: record.createdAt,
                    durationSeconds: record.durationSeconds,
                    isSynced: record.backendSynced
                )
            }

            // Update on main thread — skip if data hasn't changed to avoid unnecessary re-renders
            await MainActor.run {
                let newStatus = converted.first?.status
                let newApp = converted.first?.appOrSite

                // Only update if data actually changed
                let sessionsChanged = self.sessions.map(\.id) != converted.map(\.id)
                if sessionsChanged {
                    self.sessions = converted
                }
                if self.currentStatus != newStatus {
                    self.currentStatus = newStatus
                }
                if self.currentApp != newApp {
                    self.currentApp = newApp
                }

                // Update UserDefaults cache if data changed
                if sessionsChanged {
                    self.saveToStorage()
                }

                log("FocusStorage: Loaded \(converted.count) sessions from SQLite (changed: \(sessionsChanged))")
            }
        } catch {
            logError("Failed to load focus sessions from SQLite", error: error)
        }
    }

    private func saveToStorage() {
        do {
            let encoder = JSONEncoder()
            encoder.dateEncodingStrategy = .iso8601
            let data = try encoder.encode(sessions)
            UserDefaults.standard.set(data, forKey: storageKey)
        } catch {
            logError("Failed to save focus sessions", error: error)
        }
    }

    private func deleteFromBackend(_ id: String) async {
        do {
            // Focus sessions are now stored as memories, so delete the memory
            try await APIClient.shared.deleteMemory(id: id)
        } catch {
            logError("Failed to delete focus memory from backend", error: error)
        }
    }
}

// MARK: - API Models

struct CreateFocusSessionRequest: Codable {
    let status: String
    let appOrSite: String
    let description: String
    let message: String?

    enum CodingKeys: String, CodingKey {
        case status
        case appOrSite = "app_or_site"
        case description
        case message
    }
}

struct FocusSessionResponse: Codable {
    let id: String
    let status: String
    let appOrSite: String
    let description: String
    let message: String?
    let createdAt: Date
    let durationSeconds: Int?

    enum CodingKeys: String, CodingKey {
        case id
        case status
        case appOrSite = "app_or_site"
        case description
        case message
        case createdAt = "created_at"
        case durationSeconds = "duration_seconds"
    }
}

struct FocusStatsResponse: Codable {
    let date: String
    let focusedMinutes: Int
    let distractedMinutes: Int
    let sessionCount: Int
    let focusedCount: Int
    let distractedCount: Int
    let topDistractions: [DistractionEntryResponse]

    enum CodingKeys: String, CodingKey {
        case date
        case focusedMinutes = "focused_minutes"
        case distractedMinutes = "distracted_minutes"
        case sessionCount = "session_count"
        case focusedCount = "focused_count"
        case distractedCount = "distracted_count"
        case topDistractions = "top_distractions"
    }
}

struct DistractionEntryResponse: Codable {
    let appOrSite: String
    let totalSeconds: Int
    let count: Int

    enum CodingKeys: String, CodingKey {
        case appOrSite = "app_or_site"
        case totalSeconds = "total_seconds"
        case count
    }
}
