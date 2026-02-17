import Foundation
import SwiftUI
import Combine

/// View model for the Rewind page
@MainActor
class RewindViewModel: ObservableObject {
    // MARK: - Published State

    @Published var screenshots: [Screenshot] = []
    @Published var selectedScreenshot: Screenshot? = nil
    @Published var searchQuery: String = ""
    @Published var selectedApp: String? = nil
    @Published var selectedDate: Date = Date()
    @Published var availableApps: [String] = []

    @Published var isLoading = false
    @Published var isSearching = false
    @Published var errorMessage: String? = nil

    @Published var stats: (total: Int, indexed: Int, storageSize: Int64)? = nil

    /// The active search query (trimmed, non-empty) for highlighting
    @Published var activeSearchQuery: String? = nil

    // MARK: - Recovery Status

    /// Whether the database was recovered from corruption on this launch
    @Published var didRecoverFromCorruption = false

    /// Number of records recovered (0 if fresh database created)
    @Published var recoveredRecordCount = 0

    /// Whether the recovery banner should be shown
    @Published var showRecoveryBanner = false

    /// Whether a database rebuild is in progress
    @Published var isRebuilding = false

    /// Progress of database rebuild (0.0 to 1.0)
    @Published var rebuildProgress: Double = 0.0

    /// Time window in seconds for grouping search results
    var searchGroupingTimeWindow: TimeInterval = 30

    /// Grouped search results (computed from screenshots when searching)
    var groupedSearchResults: [SearchResultGroup] {
        guard activeSearchQuery != nil else { return [] }
        return screenshots.groupedByContext(timeWindowSeconds: searchGroupingTimeWindow)
    }

    /// Total number of individual screenshots across all groups
    var totalScreenshotCount: Int {
        screenshots.count
    }

    // MARK: - Private State

    private var searchTask: Task<Void, Never>?
    private var cancellables = Set<AnyCancellable>()

    /// Whether initial data has been loaded (prevents race condition with debounced search)
    private var isInitialized = false

    // MARK: - Initialization

    init() {
        // Debounce search queries
        $searchQuery
            .debounce(for: .milliseconds(300), scheduler: DispatchQueue.main)
            .sink { [weak self] query in
                Task { await self?.performSearch(query: query) }
            }
            .store(in: &cancellables)

        // Listen for new frame captures to update stats live
        NotificationCenter.default.publisher(for: .rewindFrameCaptured)
            .throttle(for: .seconds(2), scheduler: DispatchQueue.main, latest: true)
            .sink { [weak self] _ in
                Task { await self?.updateStatsOnly() }
            }
            .store(in: &cancellables)

        // Auto-refresh timeline every 3 seconds when viewing today
        Timer.publish(every: 3.0, on: .main, in: .common)
            .autoconnect()
            .sink { [weak self] _ in
                Task { await self?.refreshTimelineIfViewingToday() }
            }
            .store(in: &cancellables)
    }

    /// Refresh timeline only if viewing today and not actively searching
    private func refreshTimelineIfViewingToday() async {
        // Skip if not initialized or currently loading
        guard isInitialized, !isLoading, !isSearching else { return }

        // Skip if there's an active search query
        guard activeSearchQuery == nil else { return }

        // Only refresh if viewing today
        let calendar = Calendar.current
        guard calendar.isDateInToday(selectedDate) else { return }

        // Reload screenshots for today
        await loadScreenshotsForDate(selectedDate)
    }

    /// Update only the stats (for live frame count updates)
    private func updateStatsOnly() async {
        if let indexerStats = await RewindIndexer.shared.getStats() {
            stats = indexerStats
        }
    }

    // MARK: - Loading

    func loadInitialData() async {
        isLoading = true
        errorMessage = nil

        do {
            // Initialize the indexer if needed
            try await RewindIndexer.shared.initialize()

            // Check if database was recovered from corruption
            let recovered = await RewindDatabase.shared.didRecoverFromCorruption
            let recoveredCount = await RewindDatabase.shared.recoveredRecordCount

            if recovered {
                didRecoverFromCorruption = true
                recoveredRecordCount = recoveredCount
                showRecoveryBanner = true
                log("RewindViewModel: Database was recovered from corruption, \(recoveredCount) records salvaged")
            }

            // Load today's screenshots (date filter is always active)
            await loadScreenshotsForDate(selectedDate)

            // Load available apps for filtering
            availableApps = try await RewindDatabase.shared.getUniqueAppNames()

            // Mark as initialized after successful load
            isInitialized = true

        } catch {
            errorMessage = error.localizedDescription
            logError("RewindViewModel: Failed to load initial data: \(error)")
        }

        isLoading = false

        // Notify that Rewind page finished loading (for sidebar loading indicator)
        log("RewindViewModel: Posting rewindPageDidLoad notification")
        NotificationCenter.default.post(name: .rewindPageDidLoad, object: nil)

        // Load stats asynchronously (includes storage size calculation which can be slow)
        Task {
            if let indexerStats = await RewindIndexer.shared.getStats() {
                stats = indexerStats
            }
        }
    }

    /// Dismiss the recovery banner
    func dismissRecoveryBanner() {
        showRecoveryBanner = false
    }

    func refresh() async {
        await loadInitialData()
    }

    // MARK: - Search


    private func performSearch(query: String) async {
        // Skip if not yet initialized (prevents race condition with debounced publisher)
        guard isInitialized else { return }

        // Cancel any existing search
        searchTask?.cancel()

        let trimmedQuery = query.trimmingCharacters(in: .whitespacesAndNewlines)

        if trimmedQuery.isEmpty {
            // Reset to date-filtered view (date filter is always active)
            isSearching = false
            activeSearchQuery = nil
            await loadScreenshotsForDate(selectedDate)
            return
        }

        isSearching = true
        activeSearchQuery = trimmedQuery

        // Track rewind search
        AnalyticsManager.shared.rewindSearchPerformed(queryLength: trimmedQuery.count)

        // Calculate date range (date filter is always active)
        let calendar = Calendar.current
        let startDate = calendar.startOfDay(for: selectedDate)
        let endDate = calendar.date(byAdding: .day, value: 1, to: startDate)!

        searchTask = Task {
            do {
                // Run FTS and vector search in parallel
                async let ftsResults = RewindDatabase.shared.search(
                    query: trimmedQuery,
                    appFilter: selectedApp,
                    startDate: startDate,
                    endDate: endDate,
                    limit: 100
                )
                async let vectorResults = OCREmbeddingService.shared.searchSimilar(
                    query: trimmedQuery,
                    startDate: startDate,
                    endDate: endDate,
                    appFilter: selectedApp,
                    topK: 50
                )

                let fts = try await ftsResults
                // Vector search failures are non-fatal — FTS results still show
                let vector = (try? await vectorResults) ?? []

                if !Task.isCancelled {
                    // Merge: FTS first, then add vector-only results above threshold
                    let ftsIds = Set(fts.compactMap { $0.id })
                    var merged = fts
                    for result in vector where result.similarity > 0.5 && !ftsIds.contains(result.screenshotId) {
                        if let screenshot = try? await RewindDatabase.shared.getScreenshot(id: result.screenshotId) {
                            merged.append(screenshot)
                        }
                    }
                    screenshots = merged
                }
            } catch {
                if !Task.isCancelled {
                    logError("RewindViewModel: Search failed: \(error)")
                }
            }

            if !Task.isCancelled {
                isSearching = false
            }
        }
    }

    // MARK: - Filtering

    func filterByApp(_ app: String?) async {
        selectedApp = app

        if !searchQuery.isEmpty {
            await performSearch(query: searchQuery)
        } else {
            await loadScreenshotsForDate(selectedDate)
        }
    }

    func filterByDate(_ date: Date) async {
        selectedDate = date

        if !searchQuery.isEmpty {
            await performSearch(query: searchQuery)
        } else {
            await loadScreenshotsForDate(date)
        }
    }

    private func loadScreenshotsForDate(_ date: Date) async {
        isLoading = true

        let calendar = Calendar.current
        let startOfDay = calendar.startOfDay(for: date)
        let endOfDay = calendar.date(byAdding: .day, value: 1, to: startOfDay)!

        do {
            var results = try await RewindDatabase.shared.getScreenshots(
                from: startOfDay,
                to: endOfDay,
                limit: 500
            )

            // Filter out frames from the active (unfinalized) video chunk — they can't be displayed yet
            let activeChunk = await VideoChunkEncoder.shared.currentChunkPath
            if let activeChunk = activeChunk {
                results = results.filter { $0.videoChunkPath != activeChunk }
            }

            // Apply app filter if set
            if let app = selectedApp {
                results = results.filter { $0.appName == app }
            }

            screenshots = results

        } catch {
            logError("RewindViewModel: Failed to load screenshots for date: \(error)")
        }

        isLoading = false
    }

    // MARK: - Screenshot Selection

    func selectScreenshot(_ screenshot: Screenshot) {
        selectedScreenshot = screenshot
        AnalyticsManager.shared.rewindScreenshotViewed(timestamp: screenshot.timestamp)
    }

    func selectNextScreenshot() {
        guard let current = selectedScreenshot,
              let currentIndex = screenshots.firstIndex(where: { $0.id == current.id }),
              currentIndex > 0 else { return }

        selectedScreenshot = screenshots[currentIndex - 1]
        AnalyticsManager.shared.rewindTimelineNavigated(direction: "next")
    }

    func selectPreviousScreenshot() {
        guard let current = selectedScreenshot,
              let currentIndex = screenshots.firstIndex(where: { $0.id == current.id }),
              currentIndex < screenshots.count - 1 else { return }

        selectedScreenshot = screenshots[currentIndex + 1]
        AnalyticsManager.shared.rewindTimelineNavigated(direction: "previous")
    }

    // MARK: - Search Result Helpers

    /// Get a context snippet for the current search query on a screenshot
    func contextSnippet(for screenshot: Screenshot) -> String? {
        guard let query = activeSearchQuery else { return nil }
        return screenshot.contextSnippet(for: query)
    }

    /// Get matching text blocks for highlighting
    func matchingBlocks(for screenshot: Screenshot) -> [OCRTextBlock] {
        guard let query = activeSearchQuery else { return [] }
        return screenshot.matchingBlocks(for: query)
    }

    // MARK: - Delete

    func deleteScreenshot(_ screenshot: Screenshot) async {
        guard let id = screenshot.id else { return }

        do {
            // Delete from database (returns storage info)
            if let result = try await RewindDatabase.shared.deleteScreenshot(id: id) {
                // Delete legacy JPEG if present
                if let imagePath = result.imagePath {
                    try await RewindStorage.shared.deleteScreenshot(relativePath: imagePath)
                }
                // Delete video chunk if this was the last frame in it
                if result.isLastFrameInChunk, let videoChunkPath = result.videoChunkPath {
                    try await RewindStorage.shared.deleteVideoChunk(relativePath: videoChunkPath)
                }
            }

            // Remove from local array
            screenshots.removeAll { $0.id == id }

            // Clear selection if deleted
            if selectedScreenshot?.id == id {
                selectedScreenshot = nil
            }

        } catch {
            logError("RewindViewModel: Failed to delete screenshot: \(error)")
        }
    }

    // MARK: - Stats

    func refreshStats() async {
        if let indexerStats = await RewindIndexer.shared.getStats() {
            stats = indexerStats
        }
    }
}
