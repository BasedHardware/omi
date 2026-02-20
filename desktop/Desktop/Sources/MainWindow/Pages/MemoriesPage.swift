import SwiftUI
import AppKit
import Combine

/// All available tags for filtering memories
enum MemoryTag: String, CaseIterable, Identifiable {
    // Focus tags - shown first
    case focus
    case focused
    case distracted
    // Tips tag (from advice system)
    case tips
    // Memory categories
    case system
    case interesting
    case manual
    // Tip subcategories (from advice system)
    case productivity
    case health
    case communication
    case learning
    case other

    var id: String { rawValue }

    var displayName: String {
        switch self {
        case .focus: return "Focus"
        case .focused: return "Focused"
        case .distracted: return "Distracted"
        case .tips: return "Tips"
        case .system: return "System"
        case .interesting: return "Interesting"
        case .manual: return "Manual"
        case .productivity: return "Productivity"
        case .health: return "Health"
        case .communication: return "Communication"
        case .learning: return "Learning"
        case .other: return "Other"
        }
    }

    var icon: String {
        switch self {
        case .focus: return "eye"
        case .focused: return "eye.fill"
        case .distracted: return "eye.slash.fill"
        case .tips: return "lightbulb.fill"
        case .system: return "gearshape"
        case .interesting: return "sparkles"
        case .manual: return "square.and.pencil"
        case .productivity: return "chart.line.uptrend.xyaxis"
        case .health: return "heart.fill"
        case .communication: return "bubble.left.and.bubble.right.fill"
        case .learning: return "book.fill"
        case .other: return "ellipsis.circle"
        }
    }

    var color: Color {
        switch self {
        case .focus: return OmiColors.textSecondary
        case .focused: return OmiColors.textSecondary
        case .distracted: return OmiColors.textSecondary
        case .tips: return OmiColors.textSecondary
        case .system: return OmiColors.textSecondary
        case .interesting: return OmiColors.textSecondary
        case .manual: return OmiColors.textSecondary
        case .productivity: return OmiColors.textSecondary
        case .health: return OmiColors.textSecondary
        case .communication: return OmiColors.textSecondary
        case .learning: return OmiColors.textSecondary
        case .other: return OmiColors.textTertiary
        }
    }

    /// Check if a memory matches this tag
    func matches(_ memory: ServerMemory) -> Bool {
        switch self {
        case .focus:
            return memory.tags.contains("focus")
        case .focused:
            return memory.tags.contains("focused")
        case .distracted:
            return memory.tags.contains("distracted")
        case .tips:
            return memory.tags.contains("tips")
        case .system:
            // System memories that aren't tips or focus events
            return memory.category == .system && !memory.tags.contains("tips") && !memory.tags.contains("focus")
        case .interesting:
            return memory.category == .interesting && !memory.tags.contains("tips")
        case .manual:
            return memory.category == .manual && !memory.tags.contains("tips")
        case .productivity, .health, .communication, .learning, .other:
            return memory.tags.contains(rawValue)
        }
    }
}

// MARK: - Memories View Model

@MainActor
class MemoriesViewModel: ObservableObject {
    @Published var memories: [ServerMemory] = [] {
        didSet { recomputeCaches() }
    }
    @Published var isLoading = false
    @Published var isLoadingMore = false
    @Published var hasMoreMemories = true
    @Published var errorMessage: String?
    @Published var searchText = "" {
        didSet {
            if oldValue != searchText {
                displayLimit = pageSize
                Task { await performSearch() }
            }
        }
    }
    @Published private(set) var isSearching = false
    @Published private(set) var searchResults: [ServerMemory] = []
    @Published var selectedTags: Set<MemoryTag> = [] {
        didSet {
            // Reset display limit when filters change
            displayLimit = pageSize
            // When tags are selected, query SQLite directly
            if !selectedTags.isEmpty {
                Task { await loadFilteredMemoriesFromDatabase() }
            } else {
                filteredFromDatabase = []
                allFilteredResults = []
                hasMoreFilteredResults = false
                recomputeFilteredMemories()
            }
        }
    }

    /// Memories loaded from SQLite with filters applied
    @Published private(set) var filteredFromDatabase: [ServerMemory] = []
    @Published private(set) var isLoadingFiltered = false
    @Published var showingAddMemory = false
    @Published var newMemoryText = ""
    @Published var editingMemory: ServerMemory? = nil
    @Published var editText = ""
    @Published var selectedMemory: ServerMemory? = nil

    // Undo delete state
    @Published var pendingDeleteMemory: ServerMemory? = nil
    @Published var undoTimeRemaining: Double = 0
    private var deleteTask: Task<Void, Never>? = nil
    private var cancellables = Set<AnyCancellable>()
    private var hasLoadedInitially = false

    /// Whether the memories page is currently visible.
    /// Auto-refresh only runs when active to avoid unnecessary API calls.
    var isActive = false {
        didSet {
            if isActive && !oldValue && hasLoadedInitially {
                // Refresh immediately when becoming active
                Task { await refreshMemoriesIfNeeded() }
            }
        }
    }

    // Pagination state
    private var currentOffset = 0
    private let pageSize = 100  // Reduced from 500 for better performance

    // Bulk operations state
    @Published var showingDeleteAllConfirmation = false
    @Published var isBulkOperationInProgress = false

    // Conversation linking state
    @Published var linkedConversation: ServerConversation? = nil
    @Published var isLoadingConversation = false

    // Visibility toggle state
    @Published var isTogglingVisibility = false

    // MARK: - Cached Properties (avoid recomputation on every render)

    /// Cached filtered and sorted memories - only recomputed when inputs change
    @Published private(set) var filteredMemories: [ServerMemory] = []

    /// Cached tag counts - only recomputed when memories change
    @Published private(set) var tagCounts: [MemoryTag: Int] = [:]

    /// Total memory count from SQLite (not just loaded items)
    @Published private(set) var totalMemoriesCount: Int = 0

    /// Whether there are more filtered/search results beyond the display limit
    @Published private(set) var hasMoreFilteredResults = false

    /// Full filtered results before display cap (kept in memory for pagination)
    private var allFilteredResults: [ServerMemory] = []

    /// Current display limit for filtered/search results
    private var displayLimit = 100

    /// Count memories for a specific tag (uses cached value)
    func tagCount(_ tag: MemoryTag) -> Int {
        tagCounts[tag] ?? 0
    }

    // MARK: - Initialization

    init() {
        // Auto-refresh memories every 30 seconds
        Timer.publish(every: 30.0, on: .main, in: .common)
            .autoconnect()
            .sink { [weak self] _ in
                Task { await self?.refreshMemoriesIfNeeded() }
            }
            .store(in: &cancellables)
    }

    /// Refresh memories if already loaded (for auto-refresh)
    private func refreshMemoriesIfNeeded() async {
        // Skip if user is signed out (tokens are cleared)
        guard AuthState.shared.isSignedIn else { return }
        // Skip if page is not visible
        guard isActive else { return }

        // Skip if currently loading or haven't loaded initially
        guard !isLoading, !isLoadingMore, hasLoadedInitially else { return }

        // Skip if there's a pending delete (avoid interfering with undo)
        guard pendingDeleteMemory == nil else { return }

        // Silently sync from API and reload from local cache (local-first pattern)
        do {
            let reloadLimit = max(pageSize, memories.count)
            let apiMemories = try await APIClient.shared.getMemories(limit: reloadLimit, offset: 0)

            // Sync API results to local cache
            try await MemoryStorage.shared.syncServerMemories(apiMemories)

            // Reload from local cache to get merged data (local + synced)
            let mergedMemories = try await MemoryStorage.shared.getLocalMemories(
                limit: reloadLimit,
                offset: 0
            )
            log("MemoriesViewModel: Auto-refresh showing \(mergedMemories.count) memories (API had \(apiMemories.count))")
            memories = mergedMemories
            currentOffset = mergedMemories.count
            hasMoreMemories = mergedMemories.count >= reloadLimit
        } catch {
            // Silently ignore errors during auto-refresh
            logError("MemoriesViewModel: Auto-refresh failed", error: error)
        }
    }

    /// Recompute all caches when memories change
    private func recomputeCaches() {
        // Recompute filtered memories first (fast, in-memory)
        recomputeFilteredMemories()

        // Load true tag counts and unread tips count from SQLite asynchronously
        Task {
            await loadTagCountsFromDatabase()
        }
    }

    /// Load tag counts from SQLite database (shows true totals, not just loaded items)
    private func loadTagCountsFromDatabase() async {
        do {
            var counts: [MemoryTag: Int] = [:]

            // Get total count (no filters) and store for "All" badge
            let totalCount = try await MemoryStorage.shared.getLocalMemoriesCount()
            totalMemoriesCount = totalCount

            // Focus tags
            counts[.focus] = try await MemoryStorage.shared.getLocalMemoriesCount(tags: ["focus"])
            counts[.focused] = try await MemoryStorage.shared.getLocalMemoriesCount(tags: ["focused"])
            counts[.distracted] = try await MemoryStorage.shared.getLocalMemoriesCount(tags: ["distracted"])

            // Tips tag
            counts[.tips] = try await MemoryStorage.shared.getLocalMemoriesCount(tags: ["tips"])

            // Category counts - need to exclude tips and focus from system
            let systemTotal = try await MemoryStorage.shared.getLocalMemoriesCount(category: "system")
            let tipsCount = counts[.tips] ?? 0
            let focusCount = counts[.focus] ?? 0
            counts[.system] = max(0, systemTotal - tipsCount - focusCount)

            counts[.interesting] = try await MemoryStorage.shared.getLocalMemoriesCount(category: "interesting")
            counts[.manual] = try await MemoryStorage.shared.getLocalMemoriesCount(category: "manual")

            // Tip subcategories
            counts[.productivity] = try await MemoryStorage.shared.getLocalMemoriesCount(tags: ["productivity"])
            counts[.health] = try await MemoryStorage.shared.getLocalMemoriesCount(tags: ["health"])
            counts[.communication] = try await MemoryStorage.shared.getLocalMemoriesCount(tags: ["communication"])
            counts[.learning] = try await MemoryStorage.shared.getLocalMemoriesCount(tags: ["learning"])
            counts[.other] = try await MemoryStorage.shared.getLocalMemoriesCount(tags: ["other"])

            tagCounts = counts
            log("MemoriesViewModel: Loaded tag counts from database (total: \(totalCount))")
        } catch {
            logError("MemoriesViewModel: Failed to load tag counts from database", error: error)
            // Fall back to in-memory counts
            var counts: [MemoryTag: Int] = [:]
            for tag in MemoryTag.allCases {
                counts[tag] = memories.filter { tag.matches($0) }.count
            }
            tagCounts = counts
        }
    }

    /// Load filtered memories from SQLite when tag filters are applied
    private func loadFilteredMemoriesFromDatabase() async {
        guard !selectedTags.isEmpty else {
            filteredFromDatabase = []
            recomputeFilteredMemories()
            return
        }

        isLoadingFiltered = true

        // Build filter parameters from selected tags
        // Tags use OR logic - match ANY selected tag
        var matchAnyTag: [String] = []
        var matchAnyCategory: [String] = []

        for tag in selectedTags {
            switch tag {
            // Simple tag matches
            case .focus:
                matchAnyTag.append("focus")
            case .focused:
                matchAnyTag.append("focused")
            case .distracted:
                matchAnyTag.append("distracted")
            case .tips:
                matchAnyTag.append("tips")
            case .productivity:
                matchAnyTag.append("productivity")
            case .health:
                matchAnyTag.append("health")
            case .communication:
                matchAnyTag.append("communication")
            case .learning:
                matchAnyTag.append("learning")
            case .other:
                matchAnyTag.append("other")
            // Category matches (handled separately due to exclusions)
            case .system, .interesting, .manual:
                matchAnyCategory.append(tag.rawValue)
            }
        }

        do {
            // Query SQLite with OR logic for tags
            let results = try await MemoryStorage.shared.getFilteredMemories(
                limit: 10000,
                matchAnyTag: matchAnyTag.isEmpty ? nil : matchAnyTag,
                matchAnyCategory: matchAnyCategory.isEmpty ? nil : matchAnyCategory
            )

            // Apply complex tag matching (for system/interesting/manual exclusions)
            // These tags have special matching logic that can't be easily expressed in SQL
            let filteredResults = results.filter { memory in
                selectedTags.contains { tag in tag.matches(memory) }
            }

            filteredFromDatabase = filteredResults
            log("MemoriesViewModel: Loaded \(filteredResults.count) filtered memories from SQLite (raw: \(results.count))")
        } catch {
            logError("MemoriesViewModel: Failed to load filtered memories", error: error)
            filteredFromDatabase = []
        }

        isLoadingFiltered = false
        recomputeFilteredMemories()
    }

    /// Recompute filtered memories when search/tags change
    private func recomputeFilteredMemories() {
        let isInFilteredMode = !searchText.isEmpty || !selectedTags.isEmpty

        // Determine source based on current state
        var result: [ServerMemory]

        if !searchText.isEmpty {
            // Searching: use search results from SQLite
            result = searchResults
            // Apply tag filters to search results
            if !selectedTags.isEmpty {
                result = result.filter { memory in
                    selectedTags.contains { tag in tag.matches(memory) }
                }
            }
        } else if !filteredFromDatabase.isEmpty {
            // Tag filters applied: use SQLite filtered results
            result = filteredFromDatabase
        } else {
            // No filters: use loaded memories
            result = memories
        }

        // Sort by date (newest first)
        result.sort { $0.createdAt > $1.createdAt }

        if isInFilteredMode {
            // Store full results for pagination, apply display cap
            allFilteredResults = result
            filteredMemories = Array(result.prefix(displayLimit))
            hasMoreFilteredResults = result.count > displayLimit
        } else {
            allFilteredResults = []
            hasMoreFilteredResults = false
            filteredMemories = result
        }
    }

    /// Load more filtered/search results (pagination within already-queried results)
    func loadMoreFiltered() {
        displayLimit += pageSize
        filteredMemories = Array(allFilteredResults.prefix(displayLimit))
        hasMoreFilteredResults = allFilteredResults.count > displayLimit
    }

    /// Perform search against SQLite database for efficient full-text search
    private func performSearch() async {
        let query = searchText.trimmingCharacters(in: .whitespacesAndNewlines)

        // If search is empty, clear results and show all memories
        if query.isEmpty {
            searchResults = []
            isSearching = false
            recomputeFilteredMemories()
            return
        }

        isSearching = true

        do {
            let results = try await MemoryStorage.shared.searchLocalMemories(
                query: query,
                limit: 10000
            )
            searchResults = results
            log("MemoriesViewModel: Search for '\(query)' found \(results.count) results")
        } catch {
            logError("MemoriesViewModel: Search failed", error: error)
            // Fall back to in-memory filtering
            searchResults = memories.filter { $0.content.localizedCaseInsensitiveContains(query) }
        }

        isSearching = false
        recomputeFilteredMemories()
    }

    // MARK: - API Actions

    /// Load memories using local-first pattern:
    /// 1. Load from local cache first (instant display)
    /// 2. Fetch from API in background
    /// 3. Update UI with API data
    /// 4. Sync to local cache in background
    func loadMemories() async {
        guard !isLoading else { return }

        isLoading = true
        errorMessage = nil
        currentOffset = 0

        // Step 1: Load from local cache first for instant display
        // Use timeout to avoid blocking UI if database is initializing (e.g. recovery)
        do {
            let cachedMemories = try await withThrowingTaskGroup(of: [ServerMemory].self) { group in
                group.addTask {
                    try await MemoryStorage.shared.getLocalMemories(
                        limit: self.pageSize,
                        offset: 0
                    )
                }
                group.addTask {
                    try await Task.sleep(nanoseconds: 3_000_000_000) // 3 second timeout
                    throw CancellationError()
                }
                let result = try await group.next()!
                group.cancelAll()
                return result
            }

            if !cachedMemories.isEmpty {
                memories = cachedMemories
                currentOffset = cachedMemories.count
                hasMoreMemories = cachedMemories.count >= pageSize
                isLoading = false  // Show cached data immediately
                log("MemoriesViewModel: Loaded \(cachedMemories.count) memories from local cache")
            }
        } catch {
            log("MemoriesViewModel: Local cache unavailable, falling back to API")
            // Continue to API fetch even if cache fails
        }

        // Step 2: Fetch from API in background and sync to local cache
        do {
            let fetchedMemories = try await APIClient.shared.getMemories(limit: pageSize, offset: 0)
            hasLoadedInitially = true
            log("MemoriesViewModel: Fetched \(fetchedMemories.count) memories from API")

            // Step 3: Sync API results to local cache, then reload from cache
            // This ensures we show ALL local data (including locally-created memories)
            // merged with any updates from the server
            do {
                try await MemoryStorage.shared.syncServerMemories(fetchedMemories)
                log("MemoriesViewModel: Synced \(fetchedMemories.count) memories to local cache")

                // Reload from local cache to get merged data
                let mergedMemories = try await MemoryStorage.shared.getLocalMemories(
                    limit: pageSize,
                    offset: 0
                )
                memories = mergedMemories
                currentOffset = mergedMemories.count
                hasMoreMemories = mergedMemories.count >= pageSize
                log("MemoriesViewModel: Showing \(mergedMemories.count) memories from merged local cache")
            } catch {
                logError("MemoriesViewModel: Failed to sync/reload from local cache", error: error)
                // Fall back to API data if sync fails
                memories = fetchedMemories
                currentOffset = fetchedMemories.count
                hasMoreMemories = fetchedMemories.count >= pageSize
            }
        } catch {
            // Only show error if we don't have cached data
            if memories.isEmpty {
                errorMessage = error.localizedDescription
            }
            logError("Failed to load memories from API", error: error)
        }

        isLoading = false

        // Kick off one-time full sync in background (populates SQLite with all memories)
        Task { await performFullSyncIfNeeded() }
    }

    /// One-time background sync that fetches ALL memories from the API and stores in SQLite.
    /// Ensures filter/search queries have the full dataset. Keyed per user so it runs once per account.
    private func performFullSyncIfNeeded() async {
        let userId = UserDefaults.standard.string(forKey: "auth_userId") ?? "unknown"
        let syncKey = "memoriesFullSyncCompleted_v2_\(userId)"

        guard !UserDefaults.standard.bool(forKey: syncKey) else {
            log("MemoriesViewModel: Full sync already completed for user \(userId)")
            return
        }

        log("MemoriesViewModel: Starting one-time full sync for user \(userId)")

        var offset = 0
        var totalSynced = 0
        let batchSize = 500

        do {
            while true {
                let batch = try await APIClient.shared.getMemories(limit: batchSize, offset: offset)
                if batch.isEmpty { break }

                try await MemoryStorage.shared.syncServerMemories(batch)
                totalSynced += batch.count
                offset += batch.count
                log("MemoriesViewModel: Full sync progress - \(totalSynced) additional memories synced")

                if batch.count < batchSize { break }
            }

            UserDefaults.standard.set(true, forKey: syncKey)
            log("MemoriesViewModel: Full sync completed - \(totalSynced) additional memories synced")

            // Refresh tag counts now that SQLite has everything
            await loadTagCountsFromDatabase()
        } catch {
            logError("MemoriesViewModel: Full sync failed (will retry next launch)", error: error)
        }
    }

    /// Whether we're currently in a filtered/search mode
    var isInFilteredMode: Bool {
        !searchText.isEmpty || !selectedTags.isEmpty
    }

    /// Load more memories (pagination) - triggered by scrolling near end
    func loadMoreIfNeeded(currentMemory: ServerMemory) async {
        let hasMore = isInFilteredMode ? hasMoreFilteredResults : hasMoreMemories
        guard hasMore, !isLoading, !isLoadingMore else { return }

        // Only load more when near the end of the list
        let thresholdIndex = filteredMemories.index(filteredMemories.endIndex, offsetBy: -10, limitedBy: filteredMemories.startIndex) ?? filteredMemories.startIndex
        guard let memoryIndex = filteredMemories.firstIndex(where: { $0.id == currentMemory.id }),
              memoryIndex >= thresholdIndex else {
            return
        }

        if isInFilteredMode {
            loadMoreFiltered()
        } else {
            await loadMore()
        }
    }

    /// Explicitly load more memories (for button tap)
    /// Uses local-first: try local cache first, then API
    func loadMore() async {
        guard hasMoreMemories, !isLoading, !isLoadingMore else { return }

        isLoadingMore = true

        // Step 1: Try to load more from local cache first
        do {
            let moreFromCache = try await MemoryStorage.shared.getLocalMemories(
                limit: pageSize,
                offset: currentOffset
            )

            if !moreFromCache.isEmpty {
                memories.append(contentsOf: moreFromCache)
                currentOffset += moreFromCache.count
                hasMoreMemories = moreFromCache.count >= pageSize
                log("MemoriesViewModel: Loaded \(moreFromCache.count) more from local cache (total: \(memories.count))")
                isLoadingMore = false
                return
            }
        } catch {
            log("MemoriesViewModel: Local cache pagination failed, trying API")
        }

        // Step 2: If local cache is exhausted, fetch from API
        do {
            let newMemories = try await APIClient.shared.getMemories(limit: pageSize, offset: currentOffset)

            // Sync to local cache first
            try await MemoryStorage.shared.syncServerMemories(newMemories)

            // Then append to display
            memories.append(contentsOf: newMemories)
            currentOffset += newMemories.count
            hasMoreMemories = newMemories.count >= pageSize
            log("MemoriesViewModel: Loaded \(newMemories.count) more from API (total: \(memories.count))")
        } catch {
            logError("Failed to load more memories", error: error)
        }

        isLoadingMore = false
    }

    func createMemory() async {
        guard !newMemoryText.isEmpty else { return }

        do {
            _ = try await APIClient.shared.createMemory(content: newMemoryText)
            showingAddMemory = false
            newMemoryText = ""
            await loadMemories()
        } catch {
            logError("Failed to create memory", error: error)
        }
    }

    func deleteMemory(_ memory: ServerMemory) async {
        // Cancel any existing pending delete
        deleteTask?.cancel()
        if let existingPending = pendingDeleteMemory {
            // Immediately delete the previous pending memory
            await performActualDelete(existingPending)
        }

        // Remove from UI immediately (optimistic) — must also remove from filter source arrays
        // so recomputeFilteredMemories() doesn't resurrect the deleted memory
        withAnimation(.easeInOut(duration: 0.2)) {
            memories.removeAll { $0.id == memory.id }
            filteredFromDatabase.removeAll { $0.id == memory.id }
            allFilteredResults.removeAll { $0.id == memory.id }
            searchResults.removeAll { $0.id == memory.id }
            pendingDeleteMemory = memory
            undoTimeRemaining = 4
        }

        // Start countdown timer
        deleteTask = Task {
            // Update countdown every 100ms
            for _ in 0..<40 {
                try? await Task.sleep(nanoseconds: 100_000_000) // 100ms
                if Task.isCancelled { return }
                await MainActor.run {
                    undoTimeRemaining = max(0, undoTimeRemaining - 0.1)
                }
            }

            if Task.isCancelled { return }

            // Timer expired, perform actual delete
            await MainActor.run {
                confirmDelete()
            }
        }
    }

    func undoDelete() {
        guard let memory = pendingDeleteMemory else { return }

        // Cancel the delete timer
        deleteTask?.cancel()
        deleteTask = nil

        // Restore the memory to all relevant lists (including filter sources)
        withAnimation(.easeInOut(duration: 0.2)) {
            memories.append(memory)
            memories.sort { $0.createdAt > $1.createdAt }
            if isInFilteredMode {
                filteredFromDatabase.append(memory)
                filteredFromDatabase.sort { $0.createdAt > $1.createdAt }
                allFilteredResults.append(memory)
                allFilteredResults.sort { $0.createdAt > $1.createdAt }
            }
            if !searchText.isEmpty {
                searchResults.append(memory)
                searchResults.sort { $0.createdAt > $1.createdAt }
            }
            pendingDeleteMemory = nil
            undoTimeRemaining = 0
        }
    }

    func confirmDelete() {
        guard let memory = pendingDeleteMemory else { return }

        // Cancel timer if still running
        deleteTask?.cancel()
        deleteTask = nil

        Task {
            await performActualDelete(memory)
        }

        withAnimation(.easeInOut(duration: 0.2)) {
            pendingDeleteMemory = nil
            undoTimeRemaining = 0
        }
    }

    private func performActualDelete(_ memory: ServerMemory) async {
        // Soft-delete in SQLite immediately so auto-refresh doesn't restore it
        do {
            try await MemoryStorage.shared.deleteMemoryByBackendId(memory.id)
        } catch {
            logError("Failed to soft-delete memory locally", error: error)
        }

        do {
            try await APIClient.shared.deleteMemory(id: memory.id)
            AnalyticsManager.shared.memoryDeleted(conversationId: memory.id)
        } catch {
            logError("Failed to delete memory", error: error)
            // Restore on failure
            await MainActor.run {
                withAnimation(.easeInOut(duration: 0.2)) {
                    if !memories.contains(where: { $0.id == memory.id }) {
                        memories.append(memory)
                        memories.sort { $0.createdAt > $1.createdAt }
                    }
                }
            }
        }
    }

    func saveEditedMemory(_ memory: ServerMemory) async {
        guard !editText.isEmpty else { return }

        do {
            try await APIClient.shared.editMemory(id: memory.id, content: editText)

            // Update content in SQLite so auto-refresh doesn't revert the edit
            try await MemoryStorage.shared.updateContentByBackendId(memory.id, content: editText)

            editingMemory = nil
            editText = ""
            await loadMemories()
        } catch {
            logError("Failed to edit memory", error: error)
        }
    }

    func toggleVisibility(_ memory: ServerMemory) async {
        isTogglingVisibility = true
        let newVisibility = memory.isPublic ? "private" : "public"
        do {
            try await APIClient.shared.updateMemoryVisibility(id: memory.id, visibility: newVisibility)

            // Sync to local SQLite cache so auto-refresh doesn't revert the change
            try await MemoryStorage.shared.updateVisibilityByBackendId(memory.id, visibility: newVisibility)

            // Update memory in place
            if let index = memories.firstIndex(where: { $0.id == memory.id }) {
                memories[index].visibility = newVisibility
            }
            // Update selectedMemory if it's the same memory (reassign to trigger SwiftUI update)
            if var selected = selectedMemory, selected.id == memory.id {
                selected.visibility = newVisibility
                selectedMemory = selected
            }
        } catch {
            logError("Failed to update memory visibility", error: error)
        }
        isTogglingVisibility = false
    }

    // MARK: - Bulk Operations

    func makeAllMemoriesPrivate() async {
        isBulkOperationInProgress = true
        do {
            try await APIClient.shared.updateAllMemoriesVisibility(visibility: "private")
            // Update all in SQLite so auto-refresh doesn't revert
            for memory in memories {
                try? await MemoryStorage.shared.updateVisibilityByBackendId(memory.id, visibility: "private")
            }
            await loadMemories()
        } catch {
            logError("Failed to make all memories private", error: error)
        }
        isBulkOperationInProgress = false
    }

    func makeAllMemoriesPublic() async {
        isBulkOperationInProgress = true
        do {
            try await APIClient.shared.updateAllMemoriesVisibility(visibility: "public")
            // Update all in SQLite so auto-refresh doesn't revert
            for memory in memories {
                try? await MemoryStorage.shared.updateVisibilityByBackendId(memory.id, visibility: "public")
            }
            await loadMemories()
        } catch {
            logError("Failed to make all memories public", error: error)
        }
        isBulkOperationInProgress = false
    }

    func deleteAllMemories() async {
        isBulkOperationInProgress = true

        // Cancel any pending single delete
        deleteTask?.cancel()
        pendingDeleteMemory = nil

        // Soft-delete all in SQLite immediately so auto-refresh doesn't restore them
        do {
            try await MemoryStorage.shared.deleteAllMemories()
        } catch {
            logError("Failed to soft-delete all memories locally", error: error)
        }

        do {
            try await APIClient.shared.deleteAllMemories()
            withAnimation(.easeInOut(duration: 0.3)) {
                memories.removeAll()
            }
        } catch {
            logError("Failed to delete all memories", error: error)
            // Reload to restore state
            await loadMemories()
        }
        isBulkOperationInProgress = false
    }

    // MARK: - Conversation Linking

    func navigateToConversation(id: String) async {
        isLoadingConversation = true
        do {
            linkedConversation = try await APIClient.shared.getConversation(id: id)
        } catch {
            logError("Failed to load conversation", error: error)
        }
        isLoadingConversation = false
    }

    func dismissConversation() {
        linkedConversation = nil
    }
}

// MARK: - Memories Page

struct MemoriesPage: View {
    @ObservedObject var viewModel: MemoriesViewModel
    @State private var showingMemoryGraph = false
    @State private var showCategoryFilter = false
    @State private var categorySearchText = ""
    @State private var pendingSelectedTags: Set<MemoryTag> = []
    @State private var showManagementMenu = false

    var body: some View {
        Group {
            if let conversation = viewModel.linkedConversation {
                // Show conversation detail view
                ConversationDetailView(
                    conversation: conversation,
                    onBack: { viewModel.dismissConversation() }
                )
            } else {
                // Main memories view
                mainMemoriesView
            }
        }
    }

    private var mainMemoriesView: some View {
        VStack(spacing: 0) {
            // Header (includes search, filters, and action buttons)
            header

            // Content
            if viewModel.isLoading && viewModel.memories.isEmpty {
                loadingView
            } else if let error = viewModel.errorMessage {
                errorView(error)
            } else if viewModel.memories.isEmpty {
                emptyState
            } else if viewModel.filteredMemories.isEmpty {
                noResultsView
            } else {
                memoryList
            }
        }
        .background(Color.clear)
        .dismissableSheet(isPresented: $viewModel.showingAddMemory) {
            AddMemorySheet(viewModel: viewModel, onDismiss: { viewModel.showingAddMemory = false })
                .frame(width: 400)
        }
        .dismissableSheet(item: $viewModel.editingMemory) { memory in
            EditMemorySheet(memory: memory, viewModel: viewModel, onDismiss: { viewModel.editingMemory = nil })
                .frame(width: 400)
        }
        .dismissableSheet(item: $viewModel.selectedMemory) { memory in
            MemoryDetailSheet(
                memory: memory,
                viewModel: viewModel,
                categoryIcon: categoryIcon,
                categoryColor: categoryColor,
                tagColorFor: tagColorFor,
                formatDate: formatDate,
                onDismiss: { viewModel.selectedMemory = nil }
            )
            .frame(width: 450, height: 600)
        }
        .sheet(isPresented: $showingMemoryGraph) {
            MemoryGraphPage()
                .frame(minWidth: 800, minHeight: 600)
        }
        .overlay(alignment: .bottom) {
            undoDeleteToast
        }
        .overlay {
            // Loading overlay for conversation fetch
            if viewModel.isLoadingConversation {
                Color.black.opacity(0.3)
                    .ignoresSafeArea()
                    .overlay {
                        ProgressView()
                            .scaleEffect(1.2)
                            .tint(.white)
                    }
            }
        }
    }

    // MARK: - Undo Delete Toast

    @ViewBuilder
    private var undoDeleteToast: some View {
        if viewModel.pendingDeleteMemory != nil {
            HStack(spacing: 12) {
                Image(systemName: "trash")
                    .scaledFont(size: 14)
                    .foregroundColor(OmiColors.textSecondary)

                Text("Memory deleted")
                    .scaledFont(size: 14)
                    .foregroundColor(OmiColors.textPrimary)

                Spacer()

                // Progress indicator
                Text(String(format: "%.0fs", viewModel.undoTimeRemaining))
                    .scaledFont(size: 12, weight: .medium)
                    .foregroundColor(OmiColors.textTertiary)
                    .monospacedDigit()

                Button {
                    viewModel.undoDelete()
                } label: {
                    Text("Undo")
                        .scaledFont(size: 14, weight: .semibold)
                        .foregroundColor(OmiColors.textPrimary)
                }
                .buttonStyle(.plain)

                Button {
                    // Dismiss immediately and delete now
                    viewModel.confirmDelete()
                } label: {
                    Image(systemName: "xmark")
                        .scaledFont(size: 12, weight: .medium)
                        .foregroundColor(OmiColors.textTertiary)
                }
                .buttonStyle(.plain)
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 12)
            .background(OmiColors.backgroundTertiary)
            .cornerRadius(12)
            .overlay(
                RoundedRectangle(cornerRadius: 12)
                    .stroke(OmiColors.textQuaternary.opacity(0.5), lineWidth: 1)
            )
            .shadow(color: Color.black.opacity(0.15), radius: 8, x: 0, y: 4)
            .padding(.horizontal, 24)
            .padding(.bottom, 24)
            .transition(.move(edge: .bottom).combined(with: .opacity))
            .animation(.spring(response: 0.3, dampingFraction: 0.8), value: viewModel.pendingDeleteMemory != nil)
        }
    }

    // MARK: - Header

    private var header: some View {
        HStack(spacing: 8) {
            // Search field
            HStack(spacing: 10) {
                if viewModel.isSearching || viewModel.isLoadingFiltered {
                    ProgressView()
                        .scaleEffect(0.7)
                        .frame(width: 14, height: 14)
                } else {
                    Image(systemName: "magnifyingglass")
                        .foregroundColor(OmiColors.textTertiary)
                }

                TextField("Search memories...", text: $viewModel.searchText)
                    .textFieldStyle(.plain)
                    .foregroundColor(OmiColors.textPrimary)

                if !viewModel.searchText.isEmpty {
                    Button {
                        viewModel.searchText = ""
                    } label: {
                        Image(systemName: "xmark.circle.fill")
                            .foregroundColor(OmiColors.textTertiary)
                    }
                    .buttonStyle(.plain)
                }
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 8)
            .background(OmiColors.backgroundTertiary)
            .cornerRadius(8)

            // Category filter dropdown
            Button {
                pendingSelectedTags = viewModel.selectedTags
                categorySearchText = ""
                showCategoryFilter = true
            } label: {
                HStack(spacing: 6) {
                    Image(systemName: "line.3.horizontal.decrease")
                        .scaledFont(size: 12)
                    Text(categoryFilterLabel)
                        .scaledFont(size: 13, weight: viewModel.selectedTags.isEmpty ? .regular : .medium)
                    Image(systemName: "chevron.down")
                        .scaledFont(size: 10)
                }
                .foregroundColor(viewModel.selectedTags.isEmpty ? OmiColors.textSecondary : OmiColors.textPrimary)
                .padding(.horizontal, 12)
                .padding(.vertical, 8)
                .background(OmiColors.backgroundTertiary)
                .cornerRadius(8)
                .overlay(
                    RoundedRectangle(cornerRadius: 8)
                        .stroke(viewModel.selectedTags.isEmpty ? Color.clear : OmiColors.border, lineWidth: 1)
                )
            }
            .buttonStyle(.plain)
            .popover(isPresented: $showCategoryFilter, arrowEdge: .bottom) {
                categoryFilterPopover
            }

            // Memory Graph button
            Button {
                showingMemoryGraph = true
            } label: {
                Image(systemName: "brain")
                    .scaledFont(size: 14)
                    .foregroundColor(OmiColors.textSecondary)
                    .frame(width: 32, height: 32)
                    .background(OmiColors.backgroundTertiary)
                    .cornerRadius(8)
            }
            .buttonStyle(.plain)
            .help("View Memory Graph")

            // Add Memory button (icon only)
            Button {
                viewModel.showingAddMemory = true
            } label: {
                Image(systemName: "plus")
                    .scaledFont(size: 14)
                    .foregroundColor(.black)
                    .frame(width: 32, height: 32)
                    .background(Color.white)
                    .cornerRadius(8)
                    .overlay(
                        RoundedRectangle(cornerRadius: 8)
                            .stroke(OmiColors.border, lineWidth: 1)
                    )
            }
            .buttonStyle(.plain)
            .help("Add Memory")

            // Management menu
            Button {
                showManagementMenu = true
            } label: {
                Image(systemName: "chevron.down")
                    .scaledFont(size: 12, weight: .medium)
                    .foregroundColor(.black)
                    .frame(width: 32, height: 32)
                    .background(Color.white)
                    .cornerRadius(8)
                    .overlay(
                        RoundedRectangle(cornerRadius: 8)
                            .stroke(OmiColors.border, lineWidth: 1)
                    )
            }
            .buttonStyle(.plain)
            .popover(isPresented: $showManagementMenu, arrowEdge: .bottom) {
                managementMenuPopover
            }
        }
        .padding(.horizontal, 24)
        .padding(.top, 20)
        .padding(.bottom, 16)
        .alert("Delete All Memories?", isPresented: $viewModel.showingDeleteAllConfirmation) {
            Button("Cancel", role: .cancel) { }
            Button("Delete All", role: .destructive) {
                Task { await viewModel.deleteAllMemories() }
            }
        } message: {
            Text("This will permanently delete all \(viewModel.memories.count) memories. This action cannot be undone.")
        }
    }

    // MARK: - Filter Bar

    /// Label for the category filter button
    private var categoryFilterLabel: String {
        if viewModel.selectedTags.isEmpty {
            return "All"
        } else if viewModel.selectedTags.count == 1 {
            return viewModel.selectedTags.first!.displayName
        } else {
            return "\(viewModel.selectedTags.count) selected"
        }
    }

    /// Filtered and sorted categories (by count, highest first)
    private var filteredCategories: [MemoryTag] {
        let categories: [MemoryTag]
        if categorySearchText.isEmpty {
            categories = Array(MemoryTag.allCases)
        } else {
            categories = MemoryTag.allCases.filter { $0.displayName.localizedCaseInsensitiveContains(categorySearchText) }
        }
        // Sort by count (highest first)
        return categories.sorted { viewModel.tagCount($0) > viewModel.tagCount($1) }
    }

    private var categoryFilterPopover: some View {
        VStack(spacing: 0) {
            // Search field
            HStack(spacing: 8) {
                Image(systemName: "magnifyingglass")
                    .foregroundColor(OmiColors.textTertiary)
                    .scaledFont(size: 12)

                TextField("Search categories...", text: $categorySearchText)
                    .textFieldStyle(.plain)
                    .scaledFont(size: 13)
                    .foregroundColor(OmiColors.textPrimary)

                if !categorySearchText.isEmpty {
                    Button {
                        categorySearchText = ""
                    } label: {
                        Image(systemName: "xmark.circle.fill")
                            .foregroundColor(OmiColors.textTertiary)
                            .scaledFont(size: 12)
                    }
                    .buttonStyle(.plain)
                }
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 8)
            .background(OmiColors.backgroundTertiary)
            .cornerRadius(6)
            .padding(.horizontal, 12)
            .padding(.top, 12)
            .padding(.bottom, 8)

            Divider()
                .padding(.horizontal, 12)

            // Category list
            ScrollView {
                VStack(spacing: 2) {
                    // "All" option
                    Button {
                        pendingSelectedTags.removeAll()
                    } label: {
                        HStack {
                            Image(systemName: "tray.full")
                                .scaledFont(size: 12)
                                .frame(width: 20)
                            Text("All")
                                .scaledFont(size: 13)
                            Spacer()
                            Text("\(viewModel.totalMemoriesCount)")
                                .scaledFont(size: 11)
                                .foregroundColor(OmiColors.textTertiary)
                                .padding(.horizontal, 6)
                                .padding(.vertical, 2)
                                .background(OmiColors.backgroundTertiary)
                                .cornerRadius(4)
                            if pendingSelectedTags.isEmpty {
                                Image(systemName: "checkmark")
                                    .scaledFont(size: 12, weight: .medium)
                                    .foregroundColor(.white)
                            }
                        }
                        .foregroundColor(OmiColors.textPrimary)
                        .padding(.horizontal, 12)
                        .padding(.vertical, 8)
                        .background(pendingSelectedTags.isEmpty ? OmiColors.backgroundTertiary.opacity(0.5) : Color.clear)
                        .cornerRadius(6)
                        .contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)

                    Divider()
                        .padding(.vertical, 4)

                    // Category items
                    ForEach(filteredCategories) { tag in
                        let isSelected = pendingSelectedTags.contains(tag)
                        let count = viewModel.tagCount(tag)

                        Button {
                            if isSelected {
                                pendingSelectedTags.remove(tag)
                            } else {
                                pendingSelectedTags.insert(tag)
                            }
                        } label: {
                            HStack {
                                Image(systemName: tag.icon)
                                    .scaledFont(size: 12)
                                    .frame(width: 20)
                                Text(tag.displayName)
                                    .scaledFont(size: 13)
                                Spacer()
                                Text("\(count)")
                                    .scaledFont(size: 11)
                                    .foregroundColor(OmiColors.textTertiary)
                                    .padding(.horizontal, 6)
                                    .padding(.vertical, 2)
                                    .background(OmiColors.backgroundTertiary)
                                    .cornerRadius(4)
                                if isSelected {
                                    Image(systemName: "checkmark")
                                        .scaledFont(size: 12, weight: .medium)
                                        .foregroundColor(.white)
                                }
                            }
                            .foregroundColor(OmiColors.textPrimary)
                            .padding(.horizontal, 12)
                            .padding(.vertical, 8)
                            .background(isSelected ? OmiColors.backgroundTertiary.opacity(0.5) : Color.clear)
                            .cornerRadius(6)
                            .contentShape(Rectangle())
                        }
                        .buttonStyle(.plain)
                    }
                }
                .padding(.horizontal, 12)
                .padding(.vertical, 8)
            }
            .frame(maxHeight: 300)

            Divider()
                .padding(.horizontal, 12)

            // Action buttons
            HStack(spacing: 8) {
                Button {
                    pendingSelectedTags.removeAll()
                } label: {
                    Text("Clear")
                        .scaledFont(size: 13, weight: .medium)
                        .foregroundColor(OmiColors.textSecondary)
                        .padding(.horizontal, 16)
                        .padding(.vertical, 8)
                        .background(OmiColors.backgroundTertiary)
                        .cornerRadius(6)
                }
                .buttonStyle(.plain)

                Button {
                    viewModel.selectedTags = pendingSelectedTags
                    showCategoryFilter = false
                } label: {
                    Text("Apply")
                        .scaledFont(size: 13, weight: .medium)
                        .foregroundColor(.black)
                        .padding(.horizontal, 16)
                        .padding(.vertical, 8)
                        .background(Color.white)
                        .cornerRadius(6)
                }
                .buttonStyle(.plain)
            }
            .padding(12)
        }
        .frame(width: 280)
        .background(OmiColors.backgroundSecondary)
    }

    // MARK: - Management Menu Popover

    private var managementMenuPopover: some View {
        VStack(alignment: .leading, spacing: 0) {
            // Visibility section
            Text("Visibility")
                .scaledFont(size: 11, weight: .medium)
                .foregroundColor(OmiColors.textTertiary)
                .padding(.horizontal, 12)
                .padding(.top, 12)
                .padding(.bottom, 6)

            Button {
                showManagementMenu = false
                Task { await viewModel.makeAllMemoriesPrivate() }
            } label: {
                HStack(spacing: 10) {
                    Image(systemName: "lock")
                        .scaledFont(size: 13)
                        .frame(width: 20)
                    Text("Make All Private")
                        .scaledFont(size: 13)
                    Spacer()
                }
                .foregroundColor(OmiColors.textPrimary)
                .padding(.horizontal, 12)
                .padding(.vertical, 8)
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .disabled(viewModel.memories.isEmpty || viewModel.isBulkOperationInProgress)
            .opacity(viewModel.memories.isEmpty || viewModel.isBulkOperationInProgress ? 0.5 : 1)

            Button {
                showManagementMenu = false
                Task { await viewModel.makeAllMemoriesPublic() }
            } label: {
                HStack(spacing: 10) {
                    Image(systemName: "globe")
                        .scaledFont(size: 13)
                        .frame(width: 20)
                    Text("Make All Public")
                        .scaledFont(size: 13)
                    Spacer()
                }
                .foregroundColor(OmiColors.textPrimary)
                .padding(.horizontal, 12)
                .padding(.vertical, 8)
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .disabled(viewModel.memories.isEmpty || viewModel.isBulkOperationInProgress)
            .opacity(viewModel.memories.isEmpty || viewModel.isBulkOperationInProgress ? 0.5 : 1)

            Divider()
                .padding(.vertical, 8)
                .padding(.horizontal, 12)

            // Danger section
            Button {
                showManagementMenu = false
                viewModel.showingDeleteAllConfirmation = true
            } label: {
                HStack(spacing: 10) {
                    Image(systemName: "trash")
                        .scaledFont(size: 13)
                        .frame(width: 20)
                    Text("Delete All Memories")
                        .scaledFont(size: 13)
                    Spacer()
                }
                .foregroundColor(OmiColors.error)
                .padding(.horizontal, 12)
                .padding(.vertical, 8)
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .disabled(viewModel.memories.isEmpty || viewModel.isBulkOperationInProgress)
            .opacity(viewModel.memories.isEmpty || viewModel.isBulkOperationInProgress ? 0.5 : 1)
        }
        .padding(.vertical, 4)
        .frame(width: 200)
        .background(OmiColors.backgroundSecondary)
    }

    // MARK: - Memory List

    private var memoryList: some View {
        ScrollView {
            LazyVStack(spacing: 8) {
                ForEach(viewModel.filteredMemories) { memory in
                    MemoryCardView(
                        memory: memory,
                        onTap: {
                            viewModel.selectedMemory = memory
                        },
                        categoryIcon: categoryIcon,
                        categoryColor: categoryColor,
                        tagColorFor: tagColorFor,
                        formatDate: formatDate
                    )
                    .onAppear {
                        // Load more when approaching the end of the list
                        Task { await viewModel.loadMoreIfNeeded(currentMemory: memory) }
                    }
                }

                // Loading more indicator
                if viewModel.isLoadingMore {
                    HStack(spacing: 8) {
                        ProgressView()
                            .scaleEffect(0.8)
                        Text("Loading more...")
                            .scaledFont(size: 13)
                            .foregroundColor(OmiColors.textTertiary)
                    }
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 16)
                }

                // "Load more" button if there are more memories
                if !viewModel.filteredMemories.isEmpty && !viewModel.isLoadingMore {
                    if viewModel.isInFilteredMode && viewModel.hasMoreFilteredResults {
                        Button {
                            viewModel.loadMoreFiltered()
                        } label: {
                            HStack(spacing: 6) {
                                Image(systemName: "arrow.down.circle")
                                Text("Load more memories")
                            }
                            .scaledFont(size: 13, weight: .medium)
                            .foregroundColor(OmiColors.textSecondary)
                            .padding(.horizontal, 16)
                            .padding(.vertical, 10)
                            .background(OmiColors.backgroundTertiary)
                            .cornerRadius(8)
                        }
                        .buttonStyle(.plain)
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 8)
                    } else if !viewModel.isInFilteredMode && viewModel.hasMoreMemories {
                        Button {
                            Task { await viewModel.loadMore() }
                        } label: {
                            HStack(spacing: 6) {
                                Image(systemName: "arrow.down.circle")
                                Text("Load more memories")
                            }
                            .scaledFont(size: 13, weight: .medium)
                            .foregroundColor(OmiColors.textSecondary)
                            .padding(.horizontal, 16)
                            .padding(.vertical, 10)
                            .background(OmiColors.backgroundTertiary)
                            .cornerRadius(8)
                        }
                        .buttonStyle(.plain)
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 8)
                    }
                }
            }
            .padding(.horizontal, 24)
            .padding(.bottom, 24)
        }
    }

    private func tagBadge(_ title: String, _ icon: String, _ color: Color) -> some View {
        HStack(spacing: 4) {
            Image(systemName: icon)
                .scaledFont(size: 10)
            Text(title)
                .scaledFont(size: 11, weight: .medium)
        }
        .foregroundColor(OmiColors.textSecondary)
    }

    private func categoryIcon(_ category: MemoryCategory) -> String {
        switch category {
        case .system: return "gearshape"
        case .interesting: return "sparkles"
        case .manual: return "square.and.pencil"
        }
    }

    private func categoryColor(_ category: MemoryCategory) -> Color {
        switch category {
        case .system: return OmiColors.textSecondary
        case .interesting: return OmiColors.textSecondary
        case .manual: return OmiColors.textSecondary
        }
    }

    private func tagColorFor(_ tag: String) -> Color {
        return OmiColors.textSecondary
    }

    private func formatDate(_ date: Date) -> String {
        let relativeFormatter = RelativeDateTimeFormatter()
        relativeFormatter.unitsStyle = .abbreviated
        let relativeTime = relativeFormatter.localizedString(for: date, relativeTo: Date())

        let dateFormatter = DateFormatter()
        dateFormatter.dateFormat = "MMM d, h:mm a"
        let absoluteTime = dateFormatter.string(from: date)

        return "\(relativeTime) · \(absoluteTime)"
    }


    // MARK: - Empty States

    private var emptyState: some View {
        VStack(spacing: 16) {
            Image(systemName: "brain.head.profile")
                .scaledFont(size: 48)
                .foregroundColor(OmiColors.textTertiary)

            Text("No Memories Yet")
                .scaledFont(size: 20, weight: .semibold)
                .foregroundColor(OmiColors.textPrimary)

            Text("Your memories and tips will appear here.\nMemories are extracted from your conversations.")
                .scaledFont(size: 14)
                .foregroundColor(OmiColors.textTertiary)
                .multilineTextAlignment(.center)

            Button {
                viewModel.showingAddMemory = true
            } label: {
                HStack(spacing: 6) {
                    Image(systemName: "plus")
                    Text("Add Your First Memory")
                }
                .scaledFont(size: 14, weight: .medium)
                .foregroundColor(OmiColors.textPrimary)
                .padding(.horizontal, 20)
                .padding(.vertical, 10)
                .background(Color.white)
                .cornerRadius(8)
                .overlay(
                    RoundedRectangle(cornerRadius: 8)
                        .stroke(OmiColors.border, lineWidth: 1)
                )
            }
            .buttonStyle(.plain)
            .padding(.top, 8)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    private var noResultsView: some View {
        VStack(spacing: 12) {
            Image(systemName: "magnifyingglass")
                .scaledFont(size: 36)
                .foregroundColor(OmiColors.textTertiary)

            Text("No Results")
                .scaledFont(size: 18, weight: .semibold)
                .foregroundColor(OmiColors.textPrimary)

            Text("Try a different search or filter")
                .scaledFont(size: 14)
                .foregroundColor(OmiColors.textTertiary)

            if !viewModel.selectedTags.isEmpty {
                Button {
                    viewModel.selectedTags.removeAll()
                } label: {
                    Text("Clear Filters")
                        .scaledFont(size: 13, weight: .medium)
                        .foregroundColor(OmiColors.textSecondary)
                }
                .buttonStyle(.plain)
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    private var loadingView: some View {
        VStack(spacing: 12) {
            ProgressView()
                .progressViewStyle(.circular)
                .scaleEffect(1.2)

            Text("Loading memories...")
                .scaledFont(size: 14)
                .foregroundColor(OmiColors.textTertiary)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    private func errorView(_ message: String) -> some View {
        VStack(spacing: 16) {
            Image(systemName: "exclamationmark.triangle")
                .scaledFont(size: 36)
                .foregroundColor(OmiColors.error)

            Text("Failed to Load Memories")
                .scaledFont(size: 18, weight: .semibold)
                .foregroundColor(OmiColors.textPrimary)

            Text(message)
                .scaledFont(size: 14)
                .foregroundColor(OmiColors.textTertiary)

            Button {
                Task { await viewModel.loadMemories() }
            } label: {
                HStack(spacing: 6) {
                    Image(systemName: "arrow.clockwise")
                    Text("Retry")
                }
                .scaledFont(size: 14, weight: .medium)
                .foregroundColor(OmiColors.textPrimary)
                .padding(.horizontal, 20)
                .padding(.vertical, 10)
                .background(Color.white)
                .cornerRadius(8)
                .overlay(
                    RoundedRectangle(cornerRadius: 8)
                        .stroke(OmiColors.border, lineWidth: 1)
                )
            }
            .buttonStyle(.plain)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    // MARK: - Sheets

}

// MARK: - Memory Card View

private struct MemoryCardView: View {
    let memory: ServerMemory
    let onTap: () -> Void
    let categoryIcon: (MemoryCategory) -> String
    let categoryColor: (MemoryCategory) -> Color
    let tagColorFor: (String) -> Color
    let formatDate: (Date) -> String

    @State private var isHovered = false

    /// Check if memory was created less than 1 minute ago (newly added)
    private var isNewlyCreated: Bool {
        Date().timeIntervalSince(memory.createdAt) < 60
    }

    var body: some View {
        HStack(spacing: 8) {
            // Content
            Text(memory.content)
                .scaledFont(size: 14)
                .foregroundColor(OmiColors.textPrimary)
                .lineLimit(nil)
                .fixedSize(horizontal: false, vertical: true)

            // New badge
            if isNewlyCreated {
                NewBadge()
            }

            Spacer(minLength: 4)

            // Date
            Text(formatDate(memory.createdAt))
                .scaledFont(size: 11)
                .foregroundColor(OmiColors.textSecondary)
                .fixedSize()

            // Info icon with hover popover for details
            MemoryDetailButton(
                memory: memory,
                categoryIcon: categoryIcon,
                categoryColor: categoryColor,
                tagColorFor: tagColorFor
            )

            // Click hint on hover
            if isHovered {
                Image(systemName: "arrow.up.right")
                    .scaledFont(size: 10, weight: .medium)
                    .foregroundColor(OmiColors.textTertiary)
            }
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 8)
        .background(isHovered ? OmiColors.backgroundSecondary : (isNewlyCreated ? OmiColors.purplePrimary.opacity(0.15) : OmiColors.backgroundTertiary))
        .cornerRadius(8)
        .overlay(
            RoundedRectangle(cornerRadius: 8)
                .stroke(isNewlyCreated ? OmiColors.purplePrimary.opacity(0.3) : OmiColors.border, lineWidth: 1)
        )
        .contentShape(Rectangle())
        .onHover { hovering in
            // No animation wrapper - simple state update for instant response
            isHovered = hovering
            // Change cursor to pointing hand on hover
            if hovering {
                NSCursor.pointingHand.push()
            } else {
                NSCursor.pop()
            }
        }
        .onTapGesture {
            onTap()
        }
    }
}

// MARK: - Memory Detail Button (info icon with hover popover)

/// Small inline info button with hover preview showing memory metadata.
/// Follows the same pattern as TaskDetailButton in TaskDetailViews.swift.
private struct MemoryDetailButton: View {
    let memory: ServerMemory
    let categoryIcon: (MemoryCategory) -> String
    let categoryColor: (MemoryCategory) -> Color
    let tagColorFor: (String) -> Color

    @State private var showTooltip = false
    @State private var isButtonHovered = false
    @State private var isPopoverHovered = false
    @State private var dismissWork: DispatchWorkItem?

    var body: some View {
        Image(systemName: "info.circle")
            .scaledFont(size: 10)
            .foregroundColor(showTooltip ? OmiColors.textSecondary : OmiColors.textTertiary)
            .frame(width: 20, height: 20)
            .contentShape(Rectangle())
            .onHover { hovering in
                isButtonHovered = hovering
                scheduleHoverUpdate()
            }
            .popover(isPresented: $showTooltip, attachmentAnchor: .rect(.bounds), arrowEdge: .bottom) {
                MemoryDetailTooltip(
                    memory: memory,
                    categoryIcon: categoryIcon,
                    categoryColor: categoryColor,
                    tagColorFor: tagColorFor
                )
                .onHover { hovering in
                    isPopoverHovered = hovering
                    scheduleHoverUpdate()
                }
            }
    }

    private func scheduleHoverUpdate() {
        dismissWork?.cancel()
        if isButtonHovered || isPopoverHovered {
            showTooltip = true
        } else {
            let work = DispatchWorkItem { showTooltip = false }
            dismissWork = work
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.25, execute: work)
        }
    }
}

// MARK: - Memory Detail Tooltip

/// Compact hover preview showing memory metadata (category, tags, source, etc.)
private struct MemoryDetailTooltip: View {
    let memory: ServerMemory
    let categoryIcon: (MemoryCategory) -> String
    let categoryColor: (MemoryCategory) -> Color
    let tagColorFor: (String) -> Color

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            // Category
            if memory.isTip {
                tooltipRow("Category", "Tips")
                if let tipCat = memory.tipCategory {
                    tooltipRow("Subcategory", tipCat.capitalized)
                }
            } else {
                tooltipRow("Category", memory.category.displayName)
            }

            // Tags
            let displayTags = memory.tags.filter { tag in
                let lower = tag.lowercased()
                if lower == memory.category.rawValue { return false }
                if lower == "tips" || lower == (memory.tipCategory ?? "") { return false }
                if lower == "has-message" { return false }
                return true
            }
            if !displayTags.isEmpty {
                tooltipRow("Tags", displayTags.joined(separator: ", "))
            }

            // Source
            if let sourceApp = memory.sourceApp {
                tooltipRow("App", sourceApp)
            }
            if let sourceName = memory.sourceName {
                tooltipRow("Source", sourceName)
            }
            if let window = memory.windowTitle {
                tooltipRow("Window", window)
            }

            // Context
            if let ctx = memory.contextSummary, !ctx.isEmpty {
                tooltipBlock("Context", ctx)
            }
            if let activity = memory.currentActivity, !activity.isEmpty {
                tooltipBlock("Activity", activity)
            }

            // Confidence
            if let conf = memory.confidenceString {
                tooltipRow("Confidence", conf)
            }

            // Reasoning
            if let reasoning = memory.reasoning, !reasoning.isEmpty {
                tooltipBlock("Reasoning", reasoning)
            }

            // Created date
            tooltipRow("Created", {
                let f = DateFormatter()
                f.dateStyle = .medium
                f.timeStyle = .short
                return f.string(from: memory.createdAt)
            }())
        }
        .padding(10)
        .frame(maxWidth: 350, maxHeight: 400)
    }

    private func tooltipRow(_ label: String, _ value: String) -> some View {
        HStack(alignment: .top, spacing: 6) {
            Text(label)
                .scaledFont(size: 11, weight: .medium)
                .foregroundColor(OmiColors.textTertiary)
                .frame(width: 70, alignment: .trailing)

            Text(value)
                .scaledFont(size: 11)
                .foregroundColor(OmiColors.textPrimary)
        }
    }

    private func tooltipBlock(_ label: String, _ value: String) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(label)
                .scaledFont(size: 11, weight: .medium)
                .foregroundColor(OmiColors.textTertiary)
                .padding(.leading, 76)

            Text(value)
                .scaledFont(size: 11)
                .foregroundColor(OmiColors.textPrimary)
                .padding(.leading, 76)
                .lineLimit(3)
        }
    }
}

// MARK: - Memory Detail Sheet

struct MemoryDetailSheet: View {
    let memory: ServerMemory
    @ObservedObject var viewModel: MemoriesViewModel
    let categoryIcon: (MemoryCategory) -> String
    let categoryColor: (MemoryCategory) -> Color
    let tagColorFor: (String) -> Color
    let formatDate: (Date) -> String
    var onDismiss: (() -> Void)? = nil

    @Environment(\.dismiss) private var environmentDismiss
    @State private var isEditingContent = false
    @State private var editContentText = ""

    private func dismissSheet() {
        if let onDismiss = onDismiss {
            onDismiss()
        } else {
            environmentDismiss()
        }
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                // Header with tags, visibility toggle, delete, and dismiss
                HStack(spacing: 8) {
                    if memory.isTip {
                        tagBadge("Tips", "lightbulb.fill", OmiColors.textSecondary)
                        if let tipCat = memory.tipCategory {
                            tagBadge(tipCat.capitalized, memory.tipCategoryIcon, tagColorFor(tipCat))
                        }
                    } else {
                        tagBadge(memory.category.displayName, categoryIcon(memory.category), categoryColor(memory.category))
                    }

                    Spacer()

                    // Public toggle
                    HStack(spacing: 6) {
                        Text("Public")
                            .scaledFont(size: 13)
                            .foregroundColor(OmiColors.textSecondary)
                        if viewModel.isTogglingVisibility {
                            ProgressView()
                                .scaleEffect(0.7)
                        } else {
                            Toggle("", isOn: Binding(
                                get: { memory.isPublic },
                                set: { _ in
                                    Task { await viewModel.toggleVisibility(memory) }
                                }
                            ))
                            .toggleStyle(.switch)
                            .labelsHidden()
                        }
                    }

                    // Delete icon
                    Button {
                        NSApp.keyWindow?.makeFirstResponder(nil)
                        Task { @MainActor in
                            try? await Task.sleep(nanoseconds: 100_000_000)
                            dismissSheet()
                            await viewModel.deleteMemory(memory)
                        }
                    } label: {
                        Image(systemName: "trash")
                            .scaledFont(size: 14)
                            .foregroundColor(OmiColors.error)
                    }
                    .buttonStyle(.plain)

                    DismissButton(action: dismissSheet)
                }

                // Content (click to edit)
                if isEditingContent {
                    VStack(alignment: .trailing, spacing: 8) {
                        TextEditor(text: $editContentText)
                            .scaledFont(size: 15)
                            .foregroundColor(OmiColors.textPrimary)
                            .scrollContentBackground(.hidden)
                            .padding(8)
                            .background(OmiColors.backgroundTertiary)
                            .cornerRadius(8)
                            .frame(minHeight: 80)

                        HStack(spacing: 8) {
                            Button {
                                isEditingContent = false
                            } label: {
                                Text("Cancel")
                                    .scaledFont(size: 13)
                                    .foregroundColor(OmiColors.textSecondary)
                            }
                            .buttonStyle(.plain)

                            Button {
                                viewModel.editText = editContentText
                                Task {
                                    await viewModel.saveEditedMemory(memory)
                                    isEditingContent = false
                                }
                            } label: {
                                Text("Save")
                                    .scaledFont(size: 13, weight: .medium)
                                    .foregroundColor(.black)
                                    .padding(.horizontal, 12)
                                    .padding(.vertical, 4)
                                    .background(Color.white)
                                    .cornerRadius(6)
                            }
                            .buttonStyle(.plain)
                            .disabled(editContentText.isEmpty)
                        }
                    }
                } else {
                    Text(memory.content)
                        .scaledFont(size: 15)
                        .foregroundColor(OmiColors.textPrimary)
                        .fixedSize(horizontal: false, vertical: true)
                        .contentShape(Rectangle())
                        .onTapGesture {
                            editContentText = memory.content
                            isEditingContent = true
                        }
                }

                // Reasoning
                if let reasoning = memory.reasoning, !reasoning.isEmpty {
                    VStack(alignment: .leading, spacing: 8) {
                        Text("Why this tip?")
                            .scaledFont(size: 13, weight: .semibold)
                            .foregroundColor(OmiColors.textSecondary)

                        Text(reasoning)
                            .scaledFont(size: 14)
                            .foregroundColor(OmiColors.textPrimary)
                            .textSelection(.enabled)
                    }
                    .padding(12)
                    .background(OmiColors.backgroundTertiary)
                    .cornerRadius(8)
                }

                // Context
                if memory.currentActivity != nil || memory.contextSummary != nil {
                    VStack(alignment: .leading, spacing: 8) {
                        Text("Context")
                            .scaledFont(size: 13, weight: .semibold)
                            .foregroundColor(OmiColors.textSecondary)

                        if let activity = memory.currentActivity {
                            HStack(spacing: 6) {
                                Image(systemName: "figure.walk")
                                    .scaledFont(size: 12)
                                Text(activity)
                                    .scaledFont(size: 13)
                                    .textSelection(.enabled)
                            }
                            .foregroundColor(OmiColors.textTertiary)
                        }

                        if let context = memory.contextSummary {
                            Text(context)
                                .scaledFont(size: 13)
                                .foregroundColor(OmiColors.textTertiary)
                                .textSelection(.enabled)
                        }
                    }
                    .padding(12)
                    .background(OmiColors.backgroundTertiary)
                    .cornerRadius(8)
                }

                // Metadata
                VStack(alignment: .leading, spacing: 8) {
                    if let confidence = memory.confidenceString {
                        HStack {
                            Text("Confidence")
                                .foregroundColor(OmiColors.textSecondary)
                            Spacer()
                            Text(confidence)
                                .foregroundColor(OmiColors.textPrimary)
                        }
                        .scaledFont(size: 13)
                    }

                    if let sourceApp = memory.sourceApp {
                        HStack {
                            Text("Source App")
                                .foregroundColor(OmiColors.textSecondary)
                            Spacer()
                            Text(sourceApp)
                                .foregroundColor(OmiColors.textPrimary)
                        }
                        .scaledFont(size: 13)
                    }

                    if let sourceName = memory.sourceName {
                        HStack {
                            Text("Device")
                                .foregroundColor(OmiColors.textSecondary)
                            Spacer()
                            HStack(spacing: 4) {
                                Image(systemName: memory.sourceIcon)
                                Text(sourceName)
                            }
                            .foregroundColor(OmiColors.textPrimary)
                        }
                        .scaledFont(size: 13)
                    }

                    if let micName = memory.inputDeviceName, memory.source == "desktop" {
                        HStack {
                            Text("Microphone")
                                .foregroundColor(OmiColors.textSecondary)
                            Spacer()
                            HStack(spacing: 4) {
                                Image(systemName: "mic")
                                Text(micName)
                            }
                            .foregroundColor(OmiColors.textPrimary)
                        }
                        .scaledFont(size: 13)
                    }

                    HStack {
                        Text("Created")
                            .foregroundColor(OmiColors.textSecondary)
                        Spacer()
                        Text(formatDate(memory.createdAt))
                            .foregroundColor(OmiColors.textPrimary)
                    }
                    .scaledFont(size: 13)

                    if !memory.tags.isEmpty {
                        HStack(alignment: .top) {
                            Text("Tags")
                                .foregroundColor(OmiColors.textSecondary)
                                .scaledFont(size: 13)
                            Spacer()
                            FlowLayout(spacing: 4) {
                                ForEach(memory.tags, id: \.self) { tag in
                                    Text(tag)
                                        .scaledFont(size: 11, weight: .medium)
                                        .foregroundColor(tagColorFor(tag))
                                }
                            }
                        }
                    }
                }
                .padding(12)
                .background(OmiColors.backgroundTertiary)
                .cornerRadius(8)

                // Action Buttons
                VStack(spacing: 10) {
                    // View conversation (if linked)
                    if let conversationId = memory.conversationId {
                        MemoryActionRow(
                            icon: "bubble.left.and.bubble.right",
                            title: "View Source Conversation",
                            iconColor: OmiColors.textPrimary,
                            textColor: OmiColors.textPrimary,
                            backgroundColor: OmiColors.backgroundTertiary,
                            trailingIcon: "arrow.up.right"
                        ) {
                            NSApp.keyWindow?.makeFirstResponder(nil)
                            Task { @MainActor in
                                try? await Task.sleep(nanoseconds: 100_000_000)
                                dismissSheet()
                                await viewModel.navigateToConversation(id: conversationId)
                            }
                        }
                    }
                }
                .padding(.top, 8)
            }
            .padding(24)
        }
        .frame(width: 450)
        .frame(maxHeight: 600)
        .background(OmiColors.backgroundSecondary)
    }

    private func tagBadge(_ title: String, _ icon: String, _ color: Color) -> some View {
        HStack(spacing: 4) {
            Image(systemName: icon)
                .scaledFont(size: 10)
            Text(title)
                .scaledFont(size: 11, weight: .medium)
        }
        .foregroundColor(OmiColors.textSecondary)
    }
}

// MARK: - Memory Action Row
/// A row button that prevents click-through when tapped, using the same pattern as SafeDismissButton.
/// Sends a synthetic mouse-up event before executing the action.
private struct MemoryActionRow: View {
    let icon: String
    let title: String
    let iconColor: Color
    let textColor: Color
    let backgroundColor: Color
    var trailingIcon: String? = nil
    let action: () -> Void

    @State private var isPressed = false

    var body: some View {
        HStack {
            Image(systemName: icon)
                .foregroundColor(iconColor)
            Text(title)
            Spacer()
            if let trailing = trailingIcon {
                Image(systemName: trailing)
                    .scaledFont(size: 12)
                    .foregroundColor(OmiColors.textTertiary)
            }
        }
        .scaledFont(size: 14)
        .foregroundColor(textColor)
        .padding(12)
        .background(backgroundColor)
        .cornerRadius(8)
        .opacity(isPressed ? 0.7 : 1.0)
        .contentShape(Rectangle())
        .onTapGesture {
            guard !isPressed else { return } // Prevent double-tap
            isPressed = true

            log("MEMORY ACTION: \(title) tapped at mouse position: \(NSEvent.mouseLocation)")

            // Consume the click by resigning first responder
            NSApp.keyWindow?.makeFirstResponder(nil)

            // Post a mouse-up event to ensure any pending click is consumed
            if let window = NSApp.keyWindow {
                let event = NSEvent.mouseEvent(
                    with: .leftMouseUp,
                    location: window.mouseLocationOutsideOfEventStream,
                    modifierFlags: [],
                    timestamp: ProcessInfo.processInfo.systemUptime,
                    windowNumber: window.windowNumber,
                    context: nil,
                    eventNumber: 0,
                    clickCount: 1,
                    pressure: 0
                )
                if let event = event {
                    window.sendEvent(event)
                    log("MEMORY ACTION: Sent synthetic mouse-up event for \(title)")
                }
            }

            // Execute the action (which should handle its own delays for dismiss)
            action()
        }
    }
}

// MARK: - Add Memory Sheet

struct AddMemorySheet: View {
    @ObservedObject var viewModel: MemoriesViewModel
    var onDismiss: (() -> Void)? = nil

    @Environment(\.dismiss) private var environmentDismiss

    private func dismissSheet() {
        viewModel.newMemoryText = ""
        if let onDismiss = onDismiss {
            onDismiss()
        } else {
            environmentDismiss()
        }
    }

    var body: some View {
        VStack(spacing: 20) {
            // Header with close button
            HStack {
                Text("Add Memory")
                    .scaledFont(size: 18, weight: .semibold)
                    .foregroundColor(OmiColors.textPrimary)
                Spacer()
                DismissButton(action: dismissSheet)
            }

            TextEditor(text: $viewModel.newMemoryText)
                .scaledFont(size: 14)
                .foregroundColor(OmiColors.textPrimary)
                .scrollContentBackground(.hidden)
                .padding(12)
                .background(OmiColors.backgroundTertiary)
                .cornerRadius(8)
                .frame(height: 150)

            HStack(spacing: 12) {
                // Cancel button
                Button(action: dismissSheet) {
                    Text("Cancel")
                        .foregroundColor(OmiColors.textSecondary)
                }

                Spacer()

                Button {
                    Task { await viewModel.createMemory() }
                } label: {
                    Text("Save")
                        .scaledFont(size: 14, weight: .medium)
                        .foregroundColor(viewModel.newMemoryText.isEmpty ? OmiColors.textTertiary : .black)
                        .padding(.horizontal, 20)
                        .padding(.vertical, 8)
                        .background(viewModel.newMemoryText.isEmpty ? OmiColors.backgroundTertiary : Color.white)
                        .cornerRadius(8)
                        .overlay(
                            RoundedRectangle(cornerRadius: 8)
                                .stroke(viewModel.newMemoryText.isEmpty ? Color.clear : OmiColors.border, lineWidth: 1)
                        )
                }
                .buttonStyle(.plain)
                .disabled(viewModel.newMemoryText.isEmpty)
            }
        }
        .padding(24)
        .frame(width: 400)
        .background(OmiColors.backgroundSecondary)
    }
}

// MARK: - Edit Memory Sheet

struct EditMemorySheet: View {
    let memory: ServerMemory
    @ObservedObject var viewModel: MemoriesViewModel
    var onDismiss: (() -> Void)? = nil

    @Environment(\.dismiss) private var environmentDismiss

    private func dismissSheet() {
        viewModel.editText = ""
        if let onDismiss = onDismiss {
            onDismiss()
        } else {
            environmentDismiss()
        }
    }

    var body: some View {
        VStack(spacing: 20) {
            // Header with close button
            HStack {
                Text("Edit Memory")
                    .scaledFont(size: 18, weight: .semibold)
                    .foregroundColor(OmiColors.textPrimary)
                Spacer()
                DismissButton(action: dismissSheet)
            }

            TextEditor(text: $viewModel.editText)
                .scaledFont(size: 14)
                .foregroundColor(OmiColors.textPrimary)
                .scrollContentBackground(.hidden)
                .padding(12)
                .background(OmiColors.backgroundTertiary)
                .cornerRadius(8)
                .frame(height: 150)

            HStack(spacing: 12) {
                // Cancel button
                Button(action: dismissSheet) {
                    Text("Cancel")
                        .foregroundColor(OmiColors.textSecondary)
                }

                Spacer()

                Button {
                    Task { await viewModel.saveEditedMemory(memory) }
                } label: {
                    Text("Save")
                        .scaledFont(size: 14, weight: .medium)
                        .foregroundColor(viewModel.editText.isEmpty ? OmiColors.textTertiary : .black)
                        .padding(.horizontal, 20)
                        .padding(.vertical, 8)
                        .background(viewModel.editText.isEmpty ? OmiColors.backgroundTertiary : Color.white)
                        .cornerRadius(8)
                        .overlay(
                            RoundedRectangle(cornerRadius: 8)
                                .stroke(viewModel.editText.isEmpty ? Color.clear : OmiColors.border, lineWidth: 1)
                        )
                }
                .buttonStyle(.plain)
                .disabled(viewModel.editText.isEmpty)
            }
        }
        .padding(24)
        .frame(width: 400)
        .background(OmiColors.backgroundSecondary)
    }
}
