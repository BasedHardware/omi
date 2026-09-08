import Combine
import Foundation
import SwiftUI

enum RewindCitationFocusResolution: Equatable {
  case found(Screenshot)
  case unavailable
  case staleOwner
}

enum RewindCitationFocusAdmission: Equatable {
  case focused
  case unavailable
  case staleOwner
}

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
  private var ownerReloadTask: Task<Void, Never>?
  private var cancellables = Set<AnyCancellable>()

  /// Whether initial data has been loaded (prevents race condition with debounced search)
  private var isInitialized = false

  /// Citation jumps temporarily own the screenshot list. Search and viewport callbacks must not
  /// replace that list while the exact target is being admitted, or a sampled response can win the
  /// race and leave the playhead on the old frame.
  private var isCitationFocusInProgress = false
  private var pinnedCitationScreenshot: Screenshot?
  private var suppressNextEmptySearch = false

  /// Each visible viewport stays bounded even when capture contains hundreds of thousands of rows.
  /// Zooming or panning issues a fresh evenly sampled query for that continuous time window.
  static let timelineSampleTarget = 500
  typealias TimelineScreenshotLoader =
    @Sendable (_ start: Date, _ end: Date, _ targetCount: Int, _ appFilter: String?) async throws -> [Screenshot]
  typealias CitationScreenshotLoader = @Sendable (_ screenshotID: Int64) async throws -> Screenshot?

  private var visibleTimelineRange: ClosedRange<Double>?
  private var timelineLoadID = UUID()
  private let timelineScreenshotLoader: TimelineScreenshotLoader
  private let citationScreenshotLoader: CitationScreenshotLoader

  /// Set by RewindPage when the transcript/notes panel is expanded.
  /// Auto-refresh skips when true so the view tree stays stable and @State is preserved.
  var isTranscriptExpanded = false

  /// The page may consume a pending citation only after the owner's initial database load has
  /// completed. This prevents an early notification from consuming a request before Rewind is ready.
  var isReadyForCitationFocus: Bool { isInitialized }

  // MARK: - Initialization

  init(
    timelineScreenshotLoader: @escaping TimelineScreenshotLoader = { start, end, targetCount, appFilter in
      try RewindDatabase.shared.getScreenshotsSampled(
        from: start, to: end, targetCount: targetCount, appFilter: appFilter)
    },
    citationScreenshotLoader: @escaping CitationScreenshotLoader = { screenshotID in
      try RewindDatabase.shared.getScreenshot(id: screenshotID)
    }
  ) {
    self.timelineScreenshotLoader = timelineScreenshotLoader
    self.citationScreenshotLoader = citationScreenshotLoader
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

    NotificationCenter.default.publisher(for: .runtimeOwnerDidChange)
      .sink { [weak self] _ in
        Task { @MainActor [weak self] in
          self?.resetForOwnerChange()
        }
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

  private func resetForOwnerChange() {
    searchTask?.cancel()
    ownerReloadTask?.cancel()
    invalidateCitationFocus()
    screenshots = []
    selectedScreenshot = nil
    searchQuery = ""
    activeSearchQuery = nil
    selectedApp = nil
    availableApps = []
    stats = nil
    capturedDays = []
    historyRange = nil
    visibleTimelineRange = nil
    didSurveyHistory = false
    didRecoverFromCorruption = false
    recoveredRecordCount = 0
    showRecoveryBanner = false
    isRebuilding = false
    rebuildProgress = 0
    isInitialized = false
    isLoading = false
    isSearching = false
    errorMessage = nil

    // The notification is intentionally posted while the exclusive owner
    // transition is still finishing. Yield until the new local owner generation
    // is admissible, then reload this persistent StateObject for that owner.
    ownerReloadTask = Task { @MainActor [weak self] in
      while RewindCaptureOwnerSnapshot.capture() == nil {
        guard !Task.isCancelled else { return }
        await Task.yield()
      }
      guard !Task.isCancelled else { return }
      await self?.loadInitialData()
    }
  }

  /// Cancel any in-flight citation admission immediately when the owner changes. The exact owner
  /// lease is still checked at every async boundary, but this also stops a pending timeline read
  /// from re-admitting a row after the page has reset for the next owner.
  func invalidateCitationFocus() {
    searchTask?.cancel()
    timelineLoadID = UUID()
    isCitationFocusInProgress = false
    pinnedCitationScreenshot = nil
    suppressNextEmptySearch = false
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

    // A today label can remain selected while the continuous viewport is panned into older history.
    // Only append live frames when the visible window contains now or is parked at the live edge.
    guard
      RewindTrackWindow.shouldRefreshLiveFrames(
        visibleRange: visibleTimelineRange,
        newestLoadedTimestamp: screenshots.last?.timestamp.timeIntervalSince1970,
        now: Date(),
        isPlayerParkedOnNewestFrame: selectedScreenshot?.id != nil
          && selectedScreenshot?.id == screenshots.last?.id)
    else { return }

    // Silent refresh: append newly finalized frames without rescanning the retained history.
    await silentlyRefreshNewestFrames()
  }

  /// Update only the stats (for live frame count updates)
  private func updateStatsOnly() async {
    guard let ownerSnapshot = RewindCaptureOwnerSnapshot.capture() else { return }
    if let indexerStats = await RewindIndexer.shared.getStats() {
      guard ownerSnapshot.isCurrent() else { return }
      stats = indexerStats
    }
  }

  // MARK: - Loading

  func loadInitialData() async {
    guard let ownerSnapshot = RewindCaptureOwnerSnapshot.capture() else { return }
    isLoading = true
    errorMessage = nil

    do {
      // Initialize the indexer if needed
      try await RewindIndexer.shared.initialize()
      guard ownerSnapshot.isCurrent() else { return }

      // Ensure database is ready — RewindIndexer.initialize() may return early
      // (already initialized) while the database is being re-opened for a different
      // user by ViewModelContainer. This call waits for any in-progress init.
      try await RewindDatabase.shared.initialize()
      guard ownerSnapshot.isCurrent() else { return }

      // Check if database was recovered from corruption
      let recovered = await RewindDatabase.shared.didRecoverFromCorruption
      let recoveredCount = await RewindDatabase.shared.recoveredRecordCount
      guard ownerSnapshot.isCurrent() else { return }

      if recovered {
        didRecoverFromCorruption = true
        recoveredRecordCount = recoveredCount
        showRecoveryBanner = true
        log("RewindViewModel: Database was recovered from corruption, \(recoveredCount) records salvaged")
      }

      // Load today's screenshots for a fast first paint.
      await loadScreenshotsForDate(selectedDate)
      guard ownerSnapshot.isCurrent() else { return }

      // Load available apps for filtering
      let loadedApps = try await RewindDatabase.shared.getUniqueAppNames()
      guard ownerSnapshot.isCurrent() else { return }
      availableApps = loadedApps

      // Mark as initialized after successful load
      isInitialized = true

    } catch {
      guard ownerSnapshot.isCurrent() else { return }
      errorMessage = error.localizedDescription
      logError("RewindViewModel: Failed to load initial data: \(error)")
    }

    guard ownerSnapshot.isCurrent() else { return }
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
    Task { await self.surveyCapturedHistory(ownerSnapshot: ownerSnapshot) }

    // Load stats asynchronously (includes storage size calculation which can be slow)
    Task {
      if let indexerStats = await RewindIndexer.shared.getStats() {
        guard ownerSnapshot.isCurrent() else { return }
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
  func surveyCapturedHistory(
    attempts: Int = 3,
    ownerSnapshot suppliedOwnerSnapshot: RewindCaptureOwnerSnapshot? = nil
  ) async {
    guard let ownerSnapshot = suppliedOwnerSnapshot ?? RewindCaptureOwnerSnapshot.capture() else {
      return
    }
    for attempt in 0..<max(1, attempts) {
      do {
        let days = try await RewindDatabase.shared.capturedDayStarts()
        let stats = try await RewindDatabase.shared.getStats()
        guard ownerSnapshot.isCurrent() else { return }
        capturedDays = days
        historyRange = RewindTrackWindow.historyRange(oldest: stats.oldestDate, newest: stats.newestDate)
        didSurveyHistory = true
        return
      } catch {
        guard ownerSnapshot.isCurrent() else { return }
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
    let trimmedQuery = query.trimmingCharacters(in: .whitespacesAndNewlines)
    if trimmedQuery.isEmpty, suppressNextEmptySearch {
      // Citation focus clears the visible query itself. The debounced publisher still delivers that
      // write, but must not immediately reload a sampled viewport over the exact target.
      suppressNextEmptySearch = false
      return
    }

    // Skip if not yet initialized (prevents race condition with debounced publisher)
    guard isInitialized, !isCitationFocusInProgress,
      let ownerSnapshot = RewindCaptureOwnerSnapshot.capture()
    else { return }

    // Cancel any existing search
    searchTask?.cancel()

    if trimmedQuery.isEmpty {
      // Restore the viewport that was visible before search.
      isSearching = false
      activeSearchQuery = nil
      await reloadVisibleTimeline(showLoading: true)
      return
    }

    isSearching = true
    activeSearchQuery = trimmedQuery

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
        guard ownerSnapshot.isCurrent() else { return }

        if !Task.isCancelled {
          // Merge: FTS first, then add vector-only results above threshold
          let ftsIds = Set(fts.compactMap { $0.id })
          var merged = fts
          for result in vector where result.similarity > 0.5 && !ftsIds.contains(result.screenshotId) {
            if let screenshot = try? await RewindDatabase.shared.getScreenshot(id: result.screenshotId) {
              guard ownerSnapshot.isCurrent() else { return }
              merged.append(screenshot)
            }
          }
          guard ownerSnapshot.isCurrent() else { return }
          screenshots = merged
          emitRewindSearchAnalytics(query: trimmedQuery, resultsCount: merged.count)
        }
      } catch {
        if !Task.isCancelled {
          logError("RewindViewModel: Search failed: \(error)")
          emitRewindSearchAnalytics(query: trimmedQuery, resultsCount: 0)
        }
      }

      if !Task.isCancelled, ownerSnapshot.isCurrent() {
        isSearching = false
      }
    }
  }

  // MARK: - Filtering

  private func emitRewindSearchAnalytics(query: String, resultsCount: Int) {
    SearchAnalytics.queryEntered(surface: .rewind, query: query, resultsCount: resultsCount)
    AnalyticsManager.shared.rewindSearchPerformed(queryLength: query.count)
  }

  func filterByApp(_ app: String?) async {
    guard !isCitationFocusInProgress else { return }
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

  /// Preserve the viewport chosen while search results temporarily own `screenshots`, so clearing
  /// the query restores the opened result's time instead of the pre-search window.
  func rememberTimelineWindow(from start: Double, to end: Double) {
    guard end > start else { return }
    let requested = RewindTrackWindow.clamp(
      start: start,
      span: end - start,
      within: historyRange ?? (start...end))
    visibleTimelineRange = requested.start...(requested.start + requested.span)
  }

  /// Load a bounded sample for the current continuous viewport. Queries are overscanned by one
  /// quarter-window on either side so a continuing pan keeps drawing while the next read is pending.
  func loadTimelineWindow(from start: Double, to end: Double, showLoading: Bool = false) async {
    guard activeSearchQuery == nil, !isCitationFocusInProgress, end > start,
      let ownerSnapshot = RewindCaptureOwnerSnapshot.capture()
    else { return }
    if showLoading { isLoading = true }
    defer {
      if showLoading, ownerSnapshot.isCurrent() { isLoading = false }
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
      guard timelineLoadID == loadID, activeSearchQuery == nil, ownerSnapshot.isCurrent() else {
        return
      }
      var displayable = await displayableScreenshots(from: results)
      guard ownerSnapshot.isCurrent() else { return }
      if let pinned = pinnedCitationScreenshot,
        let pinnedID = pinned.id,
        pinned.timestamp.timeIntervalSince1970 >= queryStart,
        pinned.timestamp.timeIntervalSince1970 <= queryEnd,
        !displayable.contains(where: { $0.id == pinnedID }),
        (await VideoChunkEncoder.shared.currentChunkPath) != pinned.videoChunkPath
      {
        displayable = Self.insertingCitationTarget(pinned, into: displayable)
      }
      // A successful viewport read has had its chance to preserve the one exact citation target.
      // Keeping the value until this point also lets a delayed pan callback repair a sampled list.
      if pinnedCitationScreenshot != nil {
        pinnedCitationScreenshot = nil
      }
      visibleTimelineRange = requested.start...(requested.start + requested.span)
      screenshots = displayable
    } catch {
      guard timelineLoadID == loadID, activeSearchQuery == nil, ownerSnapshot.isCurrent() else {
        return
      }
      logError("RewindViewModel: Failed to load timeline viewport: \(error)")
    }
  }

  private func reloadVisibleTimeline(showLoading: Bool = false) async {
    guard let range = visibleTimelineRange ?? historyRange else { return }
    await loadTimelineWindow(from: range.lowerBound, to: range.upperBound, showLoading: showLoading)
  }

  private func loadScreenshotsForDate(
    _ date: Date,
    ownerSnapshot suppliedOwnerSnapshot: RewindCaptureOwnerSnapshot? = nil
  ) async {
    guard let ownerSnapshot = suppliedOwnerSnapshot ?? RewindCaptureOwnerSnapshot.capture() else { return }
    isLoading = true

    let calendar = Calendar.current
    let startOfDay = calendar.startOfDay(for: date)
    let endOfDay = calendar.date(byAdding: .day, value: 1, to: startOfDay)!
    visibleTimelineRange = startOfDay.timeIntervalSince1970...endOfDay.timeIntervalSince1970

    do {
      var results = try await timelineScreenshotLoader(
        startOfDay,
        endOfDay,
        Self.timelineSampleTarget,
        selectedApp
      )
      guard ownerSnapshot.isCurrent() else { return }

      // Frames from the active (unfinalized) video chunk are only displayable via their live JPEG
      let activeChunk = await VideoChunkEncoder.shared.currentChunkPath
      guard ownerSnapshot.isCurrent() else { return }
      if let activeChunk = activeChunk {
        results = results.filter { $0.videoChunkPath != activeChunk || !($0.imagePath ?? "").isEmpty }
      }

      // Apply app filter if set
      if let app = selectedApp {
        results = results.filter { $0.appName == app }
      }

      guard ownerSnapshot.isCurrent() else { return }
      screenshots = results

    } catch {
      logError("RewindViewModel: Failed to load screenshots for date: \(error)")
    }

    if ownerSnapshot.isCurrent() { isLoading = false }
  }

  /// Append newly finalized captures without repeating the all-time sample query every three seconds.
  private func silentlyRefreshNewestFrames() async {
    guard let ownerSnapshot = RewindCaptureOwnerSnapshot.capture() else { return }
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
      guard ownerSnapshot.isCurrent() else { return }
      let existingIDs = Set(screenshots.compactMap(\.id))
      let additions = candidates.filter { screenshot in
        if let id = screenshot.id { return !existingIDs.contains(id) }
        return screenshot.timestamp > newest.timestamp
      }
      guard !additions.isEmpty else { return }
      guard ownerSnapshot.isCurrent() else { return }
      // Follow the live edge: only when the user is parked on the newest frame does the
      // selection advance with new captures; a scrubbed-back position stays put.
      let wasParkedOnNewestFrame = selectedScreenshot?.id != nil && selectedScreenshot?.id == newest.id
      screenshots.append(contentsOf: additions)
      historyRange = RewindTrackWindow.extending(historyRange, toInclude: additions[additions.count - 1].timestamp)
      if wasParkedOnNewestFrame {
        // Not selectScreenshot(_:) — that emits a per-frame analytics view event; this is
        // passive following, not a user navigation.
        selectedScreenshot = additions[additions.count - 1]
      }
      // A viewport parked at the live edge follows the frames it accepts; otherwise the newest
      // loaded frame moves past the viewport's end and the next refresh tick gates itself off.
      if let visible = visibleTimelineRange, visible.upperBound >= newest.timestamp.timeIntervalSince1970 {
        visibleTimelineRange = RewindTrackWindow.extending(
          visible, toInclude: additions[additions.count - 1].timestamp)
      }

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
      results.removeAll { $0.videoChunkPath == activeChunk && ($0.imagePath ?? "").isEmpty }
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
    SearchAnalytics.resultOpened(
      surface: .rewind,
      resultIndex: screenshots.firstIndex(where: { $0.id == screenshot.id }),
      searchIsActive: activeSearchQuery != nil
    )
  }

  /// Admit an exact citation target into the active timeline even when the day loader returned an
  /// evenly sampled subset. Returning `false` is intentional: the page must not claim focus while a
  /// stale, deleted, or owner-invalid row is still selected.
  @discardableResult
  func focusCitationScreenshot(
    _ screenshot: Screenshot,
    ownerLease: RewindCaptureOwnerSnapshot? = nil
  ) async -> Bool {
    await focusCitationScreenshotResult(screenshot, ownerLease: ownerLease) == .focused
  }

  /// Resolve the destination row under the exact owner lease captured by the citation handoff.
  /// The second local lookup in `focusCitationScreenshotResult` closes the deletion race between
  /// click-time validation and timeline insertion.
  func resolveCitationRequest(
    _ request: RewindCitationFocusState.Request
  ) async -> RewindCitationFocusResolution {
    guard RewindCitationFocusState.isCurrent(owner: request.owner) else { return .staleOwner }

    do {
      guard let screenshot = try await citationScreenshotLoader(request.screenshotID) else {
        return RewindCitationFocusState.isCurrent(owner: request.owner) ? .unavailable : .staleOwner
      }
      guard RewindCitationFocusState.isCurrent(owner: request.owner) else { return .staleOwner }
      return .found(screenshot)
    } catch {
      return RewindCitationFocusState.isCurrent(owner: request.owner) ? .unavailable : .staleOwner
    }
  }

  func focusCitationScreenshotResult(
    _ screenshot: Screenshot,
    ownerLease suppliedOwnerLease: RewindCaptureOwnerSnapshot? = nil
  ) async -> RewindCitationFocusAdmission {
    guard let screenshotID = screenshot.id,
      let ownerSnapshot = suppliedOwnerLease ?? RewindCaptureOwnerSnapshot.capture(),
      RewindCitationFocusState.isCurrent(owner: ownerSnapshot)
    else { return .staleOwner }

    isCitationFocusInProgress = true
    pinnedCitationScreenshot = screenshot
    suppressNextEmptySearch = true
    searchTask?.cancel()
    timelineLoadID = UUID()
    searchQuery = ""
    activeSearchQuery = nil
    isSearching = false
    selectedApp = nil
    selectedDate = Calendar.current.startOfDay(for: screenshot.timestamp)

    defer {
      isCitationFocusInProgress = false
      if !RewindCitationFocusState.isCurrent(owner: ownerSnapshot) { pinnedCitationScreenshot = nil }
    }

    await loadScreenshotsForDate(selectedDate, ownerSnapshot: ownerSnapshot)
    guard RewindCitationFocusState.isCurrent(owner: ownerSnapshot) else { return .staleOwner }

    // Active chunks are deliberately not displayable until finalized. Do not append one merely to
    // make the row appear focused; that would produce a timeline marker for an unreadable frame.
    let activeChunk = await VideoChunkEncoder.shared.currentChunkPath
    guard RewindCitationFocusState.isCurrent(owner: ownerSnapshot) else { return .staleOwner }
    if let activeChunk, activeChunk == screenshot.videoChunkPath {
      return .unavailable
    }

    // The click-time row may have been pruned while the sampled day query was in flight. Re-read
    // the canonical local row under the same owner lease immediately before any insertion, and
    // use that read as the authoritative metadata for the focus.
    let validatedScreenshot: Screenshot?
    do {
      validatedScreenshot = try await citationScreenshotLoader(screenshotID)
    } catch {
      return RewindCitationFocusState.isCurrent(owner: ownerSnapshot) ? .unavailable : .staleOwner
    }
    guard let validatedScreenshot else {
      return RewindCitationFocusState.isCurrent(owner: ownerSnapshot) ? .unavailable : .staleOwner
    }
    guard RewindCitationFocusState.isCurrent(owner: ownerSnapshot) else { return .staleOwner }
    guard validatedScreenshot.id == screenshotID else { return .unavailable }

    if !screenshots.contains(where: { $0.id == screenshotID }) {
      // This is the last owner check before old-owner pixels/paths can enter the new timeline.
      guard RewindCitationFocusState.isCurrent(owner: ownerSnapshot) else { return .staleOwner }
      pinnedCitationScreenshot = validatedScreenshot
      screenshots = Self.insertingCitationTarget(validatedScreenshot, into: screenshots)
    }
    guard RewindCitationFocusState.isCurrent(owner: ownerSnapshot) else { return .staleOwner }
    guard let focused = screenshots.first(where: { $0.id == screenshotID }) else {
      return .unavailable
    }
    selectScreenshot(focused)
    // Keep the exact row pinned through the viewport reveal that RewindPage performs next. That
    // debounced sample owns clearing the pin after it has reinserted the target if necessary.
    return .focused
  }

  /// Preserve one exact row alongside an otherwise sampled list. The helper is deterministic and
  /// keeps timeline order stable, including when a target shares a timestamp with another frame.
  static func insertingCitationTarget(_ target: Screenshot, into screenshots: [Screenshot]) -> [Screenshot] {
    guard let targetID = target.id, !screenshots.contains(where: { $0.id == targetID }) else {
      return screenshots
    }
    return (screenshots + [target]).sorted { lhs, rhs in
      if lhs.timestamp != rhs.timestamp { return lhs.timestamp < rhs.timestamp }
      return (lhs.id ?? Int64.min) < (rhs.id ?? Int64.min)
    }
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
