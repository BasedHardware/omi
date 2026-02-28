import Foundation
import FirebaseCore

/// Stored advice item with additional metadata
struct StoredAdvice: Codable, Identifiable {
    let id: String
    let advice: ExtractedAdvice
    let contextSummary: String
    let currentActivity: String
    let createdAt: Date
    var isRead: Bool
    var isDismissed: Bool

    init(
        id: String = UUID().uuidString,
        advice: ExtractedAdvice,
        contextSummary: String,
        currentActivity: String,
        createdAt: Date = Date(),
        isRead: Bool = false,
        isDismissed: Bool = false
    ) {
        self.id = id
        self.advice = advice
        self.contextSummary = contextSummary
        self.currentActivity = currentActivity
        self.createdAt = createdAt
        self.isRead = isRead
        self.isDismissed = isDismissed
    }

    /// Convert from server memory model (advice is stored as memories with "tips" tag)
    init(from memory: ServerMemory) {
        self.id = memory.id
        // Extract category from tags: ["tips", "productivity"] → .productivity
        let categoryTag = memory.tags.first(where: { $0 != "tips" })
        let category = AdviceCategory(rawValue: categoryTag ?? "other") ?? .other
        self.advice = ExtractedAdvice(
            advice: memory.content,
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

    func withRead(_ read: Bool) -> StoredAdvice {
        var copy = self
        copy.isRead = read
        return copy
    }

    func withDismissed(_ dismissed: Bool) -> StoredAdvice {
        var copy = self
        copy.isDismissed = dismissed
        return copy
    }
}

/// Local storage manager for advice history with backend sync
@MainActor
class AdviceStorage: ObservableObject {
    static let shared = AdviceStorage()

    @Published private(set) var adviceHistory: [StoredAdvice] = []
    @Published private(set) var isLoading = false
    @Published private(set) var lastSyncError: String?

    private let localStorageKey = "omi.advice.history"
    private let maxLocalAdvice = 100
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

    /// Add new advice to storage for UI display (backend sync handled by AdviceAssistant)
    func addAdvice(_ result: AdviceExtractionResult) {
        guard let advice = result.advice else { return }

        // Create local stored advice
        let storedAdvice = StoredAdvice(
            advice: advice,
            contextSummary: result.contextSummary,
            currentActivity: result.currentActivity
        )

        // Add locally for immediate UI update
        adviceHistory.insert(storedAdvice, at: 0)
        trimLocalCache()
        saveToLocalCache()
    }

    /// Mark advice as read
    func markAsRead(_ id: String) {
        guard let index = adviceHistory.firstIndex(where: { $0.id == id }) else { return }

        adviceHistory[index] = adviceHistory[index].withRead(true)
        saveToLocalCache()

        // Sync to backend
        Task {
            await updateAdviceOnBackend(id: id, isRead: true, isDismissed: nil)
        }
    }

    /// Mark all advice as read
    func markAllAsRead() {
        adviceHistory = adviceHistory.map { $0.withRead(true) }
        saveToLocalCache()

        // Sync to backend
        Task {
            await markAllReadOnBackend()
        }
    }

    /// Dismiss advice (hide from list)
    func dismissAdvice(_ id: String) {
        guard let index = adviceHistory.firstIndex(where: { $0.id == id }) else { return }

        adviceHistory[index] = adviceHistory[index].withDismissed(true)
        saveToLocalCache()

        // Sync to backend
        Task {
            await updateAdviceOnBackend(id: id, isRead: nil, isDismissed: true)
        }
    }

    /// Delete advice permanently
    func deleteAdvice(_ id: String) {
        adviceHistory.removeAll { $0.id == id }
        saveToLocalCache()

        // Sync to backend
        Task {
            await deleteAdviceOnBackend(id: id)
        }
    }

    /// Clear all advice history
    func clearAll() {
        let idsToDelete = adviceHistory.map { $0.id }
        adviceHistory = []
        saveToLocalCache()

        // Delete all from backend
        Task {
            for id in idsToDelete {
                await deleteAdviceOnBackend(id: id)
            }
        }
    }

    /// Refresh from backend
    func refresh() async {
        await syncFromBackend()
    }

    /// Get unread count
    var unreadCount: Int {
        adviceHistory.filter { !$0.isRead && !$0.isDismissed }.count
    }

    /// Get visible advice (not dismissed)
    var visibleAdvice: [StoredAdvice] {
        adviceHistory.filter { !$0.isDismissed }
    }

    // MARK: - Backend Sync

    private func syncFromBackend() async {
        guard !isSyncing else { return }

        // Don't sync if Firebase isn't configured yet (app still initializing)
        guard FirebaseApp.app() != nil else {
            log("Advice: Skipping sync - Firebase not configured yet")
            return
        }

        isSyncing = true
        isLoading = true
        lastSyncError = nil

        do {
            // Advice is stored as memories with "tips" tag
            let serverMemories = try await APIClient.shared.getMemories(
                limit: maxLocalAdvice,
                tags: ["tips"],
                includeDismissed: true
            )

            // Convert to local model
            let localAdvice = serverMemories.map { StoredAdvice(from: $0) }

            // Update local cache
            await MainActor.run {
                self.adviceHistory = localAdvice
                self.saveToLocalCache()
                self.isLoading = false
            }

            log("Advice: Synced \(localAdvice.count) items from backend (via memories)")
        } catch {
            await MainActor.run {
                self.lastSyncError = error.localizedDescription
                self.isLoading = false
            }
            logError("Advice: Failed to sync from backend", error: error)
        }

        isSyncing = false
    }

    private func updateAdviceOnBackend(id: String, isRead: Bool?, isDismissed: Bool?) async {
        do {
            _ = try await APIClient.shared.updateMemoryReadStatus(id: id, isRead: isRead, isDismissed: isDismissed)
            log("Advice: Updated on backend (id=\(id), isRead=\(String(describing: isRead)), isDismissed=\(String(describing: isDismissed)))")
        } catch {
            logError("Advice: Failed to update on backend", error: error)
        }
    }

    private func deleteAdviceOnBackend(id: String) async {
        do {
            try await APIClient.shared.deleteMemory(id: id)
            log("Advice: Deleted from backend (id=\(id))")
        } catch {
            logError("Advice: Failed to delete from backend", error: error)
        }
    }

    private func markAllReadOnBackend() async {
        do {
            try await APIClient.shared.markAllMemoriesRead()
            log("Advice: Marked all as read on backend")
        } catch {
            logError("Advice: Failed to mark all as read on backend", error: error)
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
            adviceHistory = try decoder.decode([StoredAdvice].self, from: data)
        } catch {
            logError("Failed to load advice from local cache", error: error)
        }
    }

    private func saveToLocalCache() {
        do {
            let encoder = JSONEncoder()
            encoder.dateEncodingStrategy = .iso8601
            let data = try encoder.encode(adviceHistory)
            UserDefaults.standard.set(data, forKey: localStorageKey)
        } catch {
            logError("Failed to save advice to local cache", error: error)
        }
    }

    private func trimLocalCache() {
        if adviceHistory.count > maxLocalAdvice {
            adviceHistory = Array(adviceHistory.prefix(maxLocalAdvice))
        }
    }
}

// MARK: - AdviceCategory Extensions

extension AdviceCategory: CaseIterable {
    public static var allCases: [AdviceCategory] {
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
