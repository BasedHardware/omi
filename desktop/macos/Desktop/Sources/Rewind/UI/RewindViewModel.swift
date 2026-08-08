import Combine
import Foundation
import SwiftUI

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

  // MARK: - History Span (all time)

  /// Every local day that holds capture, newest first.
  ///
  /// Days are labels and jump targets only; the timeline itself is continuous.
  @Published private(set) var capturedDays: [Date] = []

  /// Exact global bounds of retained capture. The visible track window pans and zooms inside them.
  @Published private(set) var historyRange: ClosedRange<Double>?

  /// Whether the walk over the capture database's own days has finished at least once.
  ///
  /// **`false` is not the same claim as "no history".** An empty `capturedDays` before the survey
  /// finishes means "not looked yet" and must render as such; only after this flips is an empty
  /// list an honest "there is no capture". Collapsing the two is how a surface ends up telling a
  /// user with months of history that they have none.
  @Published private(set) var didSurveyHistory = false

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

  /// Each visible viewport stays bounded even when capture contains hundreds of thousands of rows.
  /// Zooming or panning issues a fresh evenly sampled query for that continuous time window.
  static let timelineSampleTarget = 500
  typealias TimelineScreenshotLoader =
    @Sendable (_ start: Date, _ end: Date, _ targetCount: Int, _ appFilter: String?) async throws -> [Screenshot]

  private var visibleTimelineRange: ClosedRange<Double>?
  private var timelineLoadID = UUID()
  private let timelineScreenshotLoader: TimelineScreenshotLoader

  /// Set by RewindPage when the transcript/notes panel is expanded.
  /// Auto-refresh skips when true so the view tree stays stable and @State is preserved.
  var isTranscriptExpanded = false

  // MARK: - Initialization

  init(
    timelineScreenshotLoader: @escaping TimelineScreenshotLoader = { start, end, targetCount, appFilter in
      try RewindDatabase.shared.getScreenshotsSampled(
        from: start, to: end, targetCount: targetCount, appFilter: appFilter)
    }
  ) {
    self.timelineScreenshotLoader = timelineScreenshotLoader
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

  /// Refresh timeline only if viewing today and not actively searching.
  /// Uses a silent path that never sets isLoading and only updates screenshots
  /// when the data actually changed, preventing view-tree destruction.
  private func refreshTimelineIfViewingToday() async {
    // Skip if not initialized or currently loading
    guard isInitialized, !isLoading, !isSearching else { return }

    // Skip if there's an active search query
    guard activeSearchQuery == nil else { return }

    // Skip if transcript/notes panel is expanded — refreshing would
    // destroy the expanded view tree and lose @State (typed notes).
    guard !isTranscriptExpanded else { return }

    // Only refresh if viewing today
    let calendar = Calendar.current
    guard calendar.isDateInToday(selectedDate) else { return }

    // Silent refresh: append newly finalized frames without rescanning the retained history.
    await silentlyRefreshNewestFrames()
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

      // Ensure database is ready — RewindIndexer.initialize() may return early
      // (already initialized) while the database is being re-opened for a different
      // user by ViewModelContainer. This call waits for any in-progress init.
      try await RewindDatabase.shared.initialize()

      // Check if database was recovered from corruption
      let recovered = await RewindDatabase.shared.didRecoverFromCorruption
      let recoveredCount = await RewindDatabase.shared.recoveredRecordCount

      if recovered {
        didRecoverFromCorruption = true
        recoveredRecordCount = recoveredCount
        showRecoveryBanner = true
        log("RewindViewModel: Database was recovered from corruption, \(recoveredCount) records salvaged")
      }

      // Load today's screenshots for a fast first paint.
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

    // Discover the continuous retained bounds behind the newest day's first paint.
    //
    // **Deliberately not awaited above.** The newest day is the one the user opened the page to
    // see, and it must be drawable before anything else finishes; the survey is one index seek per
    // captured day. The track keeps today's first paint as its initial viewport and loads other
    // windows only as zoom or pan reaches them.
    Task { await self.surveyCapturedHistory() }

    // Load stats asynchronously (includes storage size calculation which can be slow)
    Task {
      if let indexerStats = await RewindIndexer.shared.getStats() {
        stats = indexerStats
      }
    }
  }

  /// Ask the capture database which days it holds and publish the exact continuous history bounds.
  ///
  /// Capture stops when the Mac sleeps, when screen recording permission is revoked, and when the
  /// user turns it off, so a one-day source regularly looks empty despite months of retained data.
  /// The day list powers labels and jumps; exact database extrema bound one time-linear track.
  /// - Parameter attempts: how many times a database that is still opening is re-asked.
  ///
  /// **A failed read is never reported as "no capture".** Rewind's pool opens asynchronously, and
  /// swallowing the error into an empty list would flip `didSurveyHistory` and print a confident
  /// "No screen capture yet" over an account with months of it — the same class of defect as an
  /// unread day rendering as a zero rather than an unknown. On exhaustion the flag stays `false`,
  /// so the label keeps saying "checking", which remains true.
  func surveyCapturedHistory(attempts: Int = 3) async {
    for attempt in 0..<max(1, attempts) {
      do {
        let days = try await RewindDatabase.shared.capturedDayStarts()
        let stats = try await RewindDatabase.shared.getStats()
        capturedDays = days
        historyRange = RewindTrackWindow.historyRange(oldest: stats.oldestDate, newest: stats.newestDate)
        didSurveyHistory = true
        return
      } catch {
        if attempt + 1 < attempts { try? await Task.sleep(for: .milliseconds(500)) }
      }
    }
    logError("RewindViewModel: Could not survey captured history; leaving the span unknown rather than empty")
  }

  /// The oldest day Rewind can still reach, or `nil` while the survey has not run.
  var oldestCapturedDay: Date? { capturedDays.last }

  /// The newest day that holds capture, or `nil` while the survey has not run.
  var newestCapturedDay: Date? { capturedDays.first }

  /// The next captured day strictly older than `day` — what "step back" means when most calendar
  /// days hold nothing.
  func capturedDay(before day: Date) -> Date? {
    let start = Calendar.current.startOfDay(for: day)
    return capturedDays.first { $0 < start }
  }

  /// The next captured day strictly newer than `day`.
  func capturedDay(after day: Date) -> Date? {
    let start = Calendar.current.startOfDay(for: day)
    return capturedDays.last { $0 > start }
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
      // Restore the viewport that was visible before search.
      isSearching = false
      activeSearchQuery = nil
      await reloadVisibleTimeline(showLoading: true)
      return
    }

    isSearching = true
    activeSearchQuery = trimmedQuery

    // Track rewind search
    AnalyticsManager.shared.rewindSearchPerformed(queryLength: trimmedQuery.count)

    // **Searching Rewind searches all of Rewind.** This used to clamp both queries to the day the
    // timeline happened to be showing, which made the one control that could reach the whole
    // history the one control that could not: a phrase you read last week returned nothing, and
    // returned it in a way indistinguishable from never having read it. The result groups already
    // carry a full date (`SearchResultGroup.formattedTimeRange` is `.medium` + time), so an
    // all-time result set reads correctly without the caller having to know which day it came from.
    // Cost is bounded by the same limits as before — FTS `limit: 100`, vector `topK: 50` — not by
    // the width of the window.

    searchTask = Task {
      do {
        // Run FTS and vector search in parallel
        async let ftsResults = RewindDatabase.shared.search(
          query: trimmedQuery,
          appFilter: selectedApp,
          startDate: nil,
          endDate: nil,
          limit: 100
        )
        async let vectorResults = OCREmbeddingService.shared.searchSimilar(
          query: trimmedQuery,
          startDate: nil,
          endDate: nil,
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
      await reloadVisibleTimeline(showLoading: true)
    }
  }

  /// Move the date control without replacing the all-time timeline source.
  func chooseDate(_ date: Date) {
    selectedDate = Calendar.current.startOfDay(for: date)
  }

  /// Point the day control at `date` without reloading the timeline.
  ///
  /// Opening an all-time search result plays frames from whatever day the result came from, and
  /// the day control has to agree with the picture — otherwise the page says "today" over a frame
  /// from three weeks ago. Reloading here would be wrong: the search results *are* the timeline
  /// while a search is active, so re-reading the day would throw them away.
  func alignSelectedDay(to date: Date) {
    let day = Calendar.current.startOfDay(for: date)
    guard !Calendar.current.isDate(day, inSameDayAs: selectedDate) else { return }
    selectedDate = day
  }

  /// Load a bounded sample for the current continuous viewport. Queries are overscanned by one
  /// quarter-window on either side so a continuing pan keeps drawing while the next read is pending.
  func loadTimelineWindow(from start: Double, to end: Double, showLoading: Bool = false) async {
    guard activeSearchQuery == nil, end > start else { return }
    if showLoading { isLoading = true }
    defer {
      if showLoading { isLoading = false }
    }

    let requested = RewindTrackWindow.clamp(
      start: start,
      span: end - start,
      within: historyRange ?? (start...end))
    let overscan = requested.span / 4
    let queryStart = max(historyRange?.lowerBound ?? requested.start, requested.start - overscan)
    let queryEnd = min(historyRange?.upperBound ?? end, requested.start + requested.span + overscan)
    let loadID = UUID()
    timelineLoadID = loadID

    do {
      let results = try await timelineScreenshotLoader(
        Date(timeIntervalSince1970: queryStart),
        Date(timeIntervalSince1970: queryEnd),
        Self.timelineSampleTarget,
        selectedApp)
      guard timelineLoadID == loadID, activeSearchQuery == nil else { return }
      visibleTimelineRange = requested.start...(requested.start + requested.span)
      screenshots = await displayableScreenshots(from: results)
    } catch {
      guard timelineLoadID == loadID, activeSearchQuery == nil else { return }
      logError("RewindViewModel: Failed to load timeline viewport: \(error)")
    }
  }

  private func reloadVisibleTimeline(showLoading: Bool = false) async {
    guard let range = visibleTimelineRange ?? historyRange else { return }
    await loadTimelineWindow(from: range.lowerBound, to: range.upperBound, showLoading: showLoading)
  }

  private func loadScreenshotsForDate(_ date: Date) async {
    isLoading = true

    let calendar = Calendar.current
    let startOfDay = calendar.startOfDay(for: date)
    let endOfDay = calendar.date(byAdding: .day, value: 1, to: startOfDay)!
    visibleTimelineRange = startOfDay.timeIntervalSince1970...endOfDay.timeIntervalSince1970

    do {
      var results = try await RewindDatabase.shared.getScreenshotsSampled(
        from: startOfDay,
        to: endOfDay,
        targetCount: 500
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

  /// Append newly finalized captures without repeating the all-time sample query every three seconds.
  private func silentlyRefreshNewestFrames() async {
    guard let newest = screenshots.last else {
      await reloadVisibleTimeline()
      return
    }

    let calendar = Calendar.current
    let startOfToday = calendar.startOfDay(for: Date())
    guard let endOfToday = calendar.date(byAdding: .day, value: 1, to: startOfToday) else { return }

    do {
      let fetched = try await RewindDatabase.shared.getScreenshots(
        from: newest.timestamp,
        to: endOfToday,
        limit: Self.timelineSampleTarget
      )
      let candidates = await displayableScreenshots(from: fetched.reversed())
      let existingIDs = Set(screenshots.compactMap(\.id))
      let additions = candidates.filter { screenshot in
        if let id = screenshot.id { return !existingIDs.contains(id) }
        return screenshot.timestamp > newest.timestamp
      }
      guard !additions.isEmpty else { return }
      screenshots.append(contentsOf: additions)

      let today = calendar.startOfDay(for: additions[additions.count - 1].timestamp)
      if !capturedDays.contains(where: { calendar.isDate($0, inSameDayAs: today) }) {
        capturedDays.insert(today, at: 0)
      }
    } catch {
      logError("RewindViewModel: Failed to refresh newest timeline frames: \(error)")
    }
  }

  private func displayableScreenshots<S: Sequence>(from source: S) async -> [Screenshot]
  where S.Element == Screenshot {
    var results = Array(source)
    if let activeChunk = await VideoChunkEncoder.shared.currentChunkPath {
      results.removeAll { $0.videoChunkPath == activeChunk }
    }
    if let app = selectedApp {
      results.removeAll { $0.appName != app }
    }
    return results
  }

  // MARK: - Screenshot Selection

  func selectScreenshot(_ screenshot: Screenshot) {
    selectedScreenshot = screenshot
    alignSelectedDay(to: screenshot.timestamp)
    AnalyticsManager.shared.rewindScreenshotViewed(timestamp: screenshot.timestamp)
  }

  func selectNextScreenshot() {
    guard let current = selectedScreenshot,
      let currentIndex = screenshots.firstIndex(where: { $0.id == current.id }),
      currentIndex < screenshots.count - 1
    else { return }

    selectedScreenshot = screenshots[currentIndex + 1]
    AnalyticsManager.shared.rewindTimelineNavigated(direction: "next")
  }

  func selectPreviousScreenshot() {
    guard let current = selectedScreenshot,
      let currentIndex = screenshots.firstIndex(where: { $0.id == current.id }),
      currentIndex > 0
    else { return }

    selectedScreenshot = screenshots[currentIndex - 1]
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
