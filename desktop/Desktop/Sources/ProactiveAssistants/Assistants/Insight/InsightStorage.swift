import Foundation
import FirebaseCore

/// Stored insight item with additional metadata
struct StoredInsight: Codable, Identifiable {
    let id: String
    let insight: ExtractedInsight
    let contextSummary: String
    let currentActivity: String
    let createdAt: Date
    var isRead: Bool
    var isDismissed: Bool

    init(
        id: String = UUID().uuidString,
        insight: ExtractedInsight,
        contextSummary: String,
        currentActivity: String,
        createdAt: Date = Date(),
        isRead: Bool = false,
        isDismissed: Bool = false
    ) {
        self.id = id
        self.insight = insight
        self.contextSummary = contextSummary
        self.currentActivity = currentActivity
        self.createdAt = createdAt
        self.isRead = isRead
        self.isDismissed = isDismissed
    }

    /// Convert from server memory model (insights are stored as memories with "tips" tag)
    init(from memory: ServerMemory) {
        self.id = memory.id
        // Extract category from tags: ["tips", "productivity"] → .productivity
        let categoryTag = memory.tags.first(where: { $0 != "tips" })
        let category = InsightCategory(rawValue: categoryTag ?? "other") ?? .other
        self.insight = ExtractedInsight(
            insight: memory.content,
            headline: memory.headline,
            reasoning: memory.reasoning,
            category: category,
            sourceApp: memory.sourceApp ?? "Unknown",
            confidence: memory.confidence ?? 0.5
        )
        self.contextSummary = memory.contextSummary ?? ""
        self.currentActivity = memory.currentActivity ?? ""
        self.createdAt = memory.createdAt
        self.isRead = memory.isRead
        self.isDismissed = memory.isDismissed
    }

    func withRead(_ read: Bool) -> StoredInsight {
        var copy = self
        copy.isRead = read
        return copy
    }

    func withDismissed(_ dismissed: Bool) -> StoredInsight {
        var copy = self
        copy.isDismissed = dismissed
        return copy
    }
}

/// Local storage manager for advice history with backend sync
@MainActor
class InsightStorage: ObservableObject {
    static let shared = InsightStorage()

    @Published private(set) var insightHistory: [StoredInsight] = []
    @Published private(set) var isLoading = false
    @Published private(set) var lastSyncError: String?

    private let localStorageKey = "omi.advice.history"
    private let maxLocalInsights = 100
    private var isSyncing = false

    private init() {
        // Load from local cache first for immediate display
        loadFromLocalCache()

        // Then sync with backend
        Task {
            await syncFromBackend()
        }
    }

    // MARK: - Public Methods

    /// Add new insight to storage for UI display (backend sync handled by InsightAssistant)
    func addInsight(_ result: InsightExtractionResult) {
        guard let insight = result.insight else { return }

        // Create local stored insight
        let storedInsight = StoredInsight(
            insight: insight,
            contextSummary: result.contextSummary,
            currentActivity: result.currentActivity
        )

        // Add locally for immediate UI update
        insightHistory.insert(storedInsight, at: 0)
        trimLocalCache()
        saveToLocalCache()
    }

    /// Mark advice as read
    func markAsRead(_ id: String) {
        guard let index = insightHistory.firstIndex(where: { $0.id == id }) else { return }

        insightHistory[index] = insightHistory[index].withRead(true)
        saveToLocalCache()

        // Sync to backend
        Task {
            await updateInsightOnBackend(id: id, isRead: true, isDismissed: nil)
        }
    }

    /// Mark all advice as read
    func markAllAsRead() {
        insightHistory = insightHistory.map { $0.withRead(true) }
        saveToLocalCache()

        // Sync to backend
        Task {
            await markAllReadOnBackend()
        }
    }

    /// Dismiss advice (hide from list)
    func dismissInsight(_ id: String) {
        guard let index = insightHistory.firstIndex(where: { $0.id == id }) else { return }

        insightHistory[index] = insightHistory[index].withDismissed(true)
        saveToLocalCache()

        // Sync to backend
        Task {
            await updateInsightOnBackend(id: id, isRead: nil, isDismissed: true)
        }
    }

    /// Delete advice permanently
    func deleteInsight(_ id: String) {
        insightHistory.removeAll { $0.id == id }
        saveToLocalCache()

        // Sync to backend
        Task {
            await deleteInsightOnBackend(id: id)
        }
    }

    /// Clear all advice history
    func clearAll() {
        let idsToDelete = insightHistory.map { $0.id }
        insightHistory = []
        saveToLocalCache()

        // Delete all from backend
        Task {
            for id in idsToDelete {
                await deleteInsightOnBackend(id: id)
            }
        }
    }

    /// Refresh from backend
    func refresh() async {
        await syncFromBackend()
    }

    /// Get unread count
    var unreadCount: Int {
        insightHistory.filter { !$0.isRead && !$0.isDismissed }.count
    }

    /// Get visible advice (not dismissed)
    var visibleInsights: [StoredInsight] {
        insightHistory.filter { !$0.isDismissed }
    }

    // MARK: - Backend Sync

    private func syncFromBackend() async {
        guard !isSyncing else { return }

        // Don't sync if Firebase isn't configured yet (app still initializing)
        guard FirebaseApp.app() != nil else {
            log("Insight: Skipping sync - Firebase not configured yet")
            return
        }

        isSyncing = true
        isLoading = true
        lastSyncError = nil

        do {
            // Insights are stored as memories with "tips" tag
            let serverMemories = try await APIClient.shared.getMemories(
                limit: maxLocalInsights,
                tags: ["tips"],
                includeDismissed: true
            )

            // Convert to local model
            let localInsight = serverMemories.map { StoredInsight(from: $0) }

            // Update local cache
            await MainActor.run {
                self.insightHistory = localInsight
                self.saveToLocalCache()
                self.isLoading = false
            }

            log("Insight: Synced \(localInsight.count) items from backend (via memories)")
        } catch {
            await MainActor.run {
                self.lastSyncError = error.localizedDescription
                self.isLoading = false
            }
            logError("Insight: Failed to sync from backend", error: error)
        }

        isSyncing = false
    }

    private func updateInsightOnBackend(id: String, isRead: Bool?, isDismissed: Bool?) async {
        do {
            _ = try await APIClient.shared.updateMemoryReadStatus(id: id, isRead: isRead, isDismissed: isDismissed)
            log("Insight: Updated on backend (id=\(id), isRead=\(String(describing: isRead)), isDismissed=\(String(describing: isDismissed)))")
        } catch {
            logError("Insight: Failed to update on backend", error: error)
        }
    }

    private func deleteInsightOnBackend(id: String) async {
        do {
            try await APIClient.shared.deleteMemory(id: id)
            log("Insight: Deleted from backend (id=\(id))")
        } catch {
            logError("Insight: Failed to delete from backend", error: error)
        }
    }

    private func markAllReadOnBackend() async {
        do {
            try await APIClient.shared.markAllMemoriesRead()
            log("Insight: Marked all as read on backend")
        } catch {
            logError("Insight: Failed to mark all as read on backend", error: error)
        }
    }

    // MARK: - Local Cache

    private func loadFromLocalCache() {
        guard let data = UserDefaults.standard.data(forKey: localStorageKey) else {
            return
        }

        do {
            let decoder = JSONDecoder()
            decoder.dateDecodingStrategy = .iso8601
            insightHistory = try decoder.decode([StoredInsight].self, from: data)
        } catch {
            logError("Failed to load insights from local cache", error: error)
        }
    }

    private func saveToLocalCache() {
        do {
            let encoder = JSONEncoder()
            encoder.dateEncodingStrategy = .iso8601
            let data = try encoder.encode(insightHistory)
            UserDefaults.standard.set(data, forKey: localStorageKey)
        } catch {
            logError("Failed to save insights to local cache", error: error)
        }
    }

    private func trimLocalCache() {
        if insightHistory.count > maxLocalInsights {
            insightHistory = Array(insightHistory.prefix(maxLocalInsights))
        }
    }
}

// MARK: - InsightCategory Extensions

extension InsightCategory: CaseIterable {
    public static var allCases: [InsightCategory] {
        [.productivity, .health, .communication, .learning, .other]
    }

    var displayName: String {
        switch self {
        case .productivity: return "Productivity"
        case .health: return "Health"
        case .communication: return "Communication"
        case .learning: return "Learning"
        case .other: return "Other"
        }
    }

    var icon: String {
        switch self {
        case .productivity: return "chart.line.uptrend.xyaxis"
        case .health: return "heart.fill"
        case .communication: return "bubble.left.and.bubble.right.fill"
        case .learning: return "book.fill"
        case .other: return "lightbulb.fill"
        }
    }
}
