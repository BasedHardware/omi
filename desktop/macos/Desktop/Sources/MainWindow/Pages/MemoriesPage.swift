import AppKit
import Combine
import OmiTheme
import SwiftUI

/// Memory categories for filtering. Mirrors the mobile app: filtering is driven
/// purely by the backend `category` field (no tag-derived pseudo-categories), so
/// desktop and mobile stay in lockstep. Labels match mobile exactly.
enum MemoryTag: String, CaseIterable, Identifiable {
  case manual
  case system
  case interesting
  case workflow

  var id: String { rawValue }

  var displayName: String {
    switch self {
    case .manual: return "Manual"
    case .system: return "About You"
    case .interesting: return "Insights"
    case .workflow: return "Workflow"
    }
  }

  var icon: String {
    switch self {
    case .manual: return "square.and.pencil"
    case .system: return "person"
    case .interesting: return "lightbulb"
    case .workflow: return "arrow.triangle.branch"
    }
  }

  var color: Color { OmiColors.textSecondary }

  /// Backend category this filter maps to.
  var category: MemoryCategory {
    switch self {
    case .manual: return .manual
    case .system: return .system
    case .interesting: return .interesting
    case .workflow: return .workflow
    }
  }

  /// Check if a memory matches this category (by backend category, like mobile).
  func matches(_ memory: ServerMemory) -> Bool {
    memory.category == category
  }
}

enum MemoryLayerFilter: String, CaseIterable, Identifiable {
  case defaultAccess
  case shortTerm
  case longTerm
  case archive

  var id: String { rawValue }

  var displayName: String {
    switch self {
    case .defaultAccess: return "Default"
    case .shortTerm: return "Short-term"
    case .longTerm: return "Long-term"
    case .archive: return "Archive"
    }
  }

  var description: String {
    switch self {
    case .defaultAccess: return "Short-term + Long-term"
    case .shortTerm: return "Fresh source-backed memories"
    case .longTerm: return "Stable memories"
    case .archive: return "Explicit archive search"
    }
  }

  var layerScope: MemoryLayerScope {
    switch self {
    case .defaultAccess: return .defaultAccess
    case .shortTerm:
      return MemoryLayerScope(tiers: [.shortTerm], requiresArchiveAcknowledgement: false)
    case .longTerm:
      return MemoryLayerScope(tiers: [.longTerm], requiresArchiveAcknowledgement: false)
    case .archive: return .archiveOnly
    }
  }

  var allowedLayers: [MemoryLayer] { layerScope.tiers }
}

/// Reversible alias during WS-G client rename (Wave 36).
typealias MemoryTierFilter = MemoryLayerFilter

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
        bumpScopeGeneration()
        displayLimit = pageSize
        Task { await performSearch() }
      }
    }
  }
  @Published private(set) var isSearching = false
  @Published private(set) var searchResults: [ServerMemory] = []
  @Published var selectedLayerFilter: MemoryLayerFilter = .defaultAccess {
    didSet {
      guard oldValue != selectedLayerFilter else { return }
      bumpScopeGeneration()
      displayLimit = pageSize
      Task { await reloadForCurrentLayerFilter() }
    }
  }

  @Published private(set) var canonicalLifecycleExposed = false {
    didSet {
      guard oldValue != canonicalLifecycleExposed else { return }
      if !canonicalLifecycleExposed, selectedLayerFilter != .defaultAccess {
        selectedLayerFilter = .defaultAccess
      }
      memories = displayMemories(memories, lifecycleExposed: canonicalLifecycleExposed)
      searchResults = displayMemories(searchResults, lifecycleExposed: canonicalLifecycleExposed)
      filteredFromDatabase = displayMemories(filteredFromDatabase, lifecycleExposed: canonicalLifecycleExposed)
      recomputeFilteredMemories()
    }
  }

  @Published var filterThisDeviceOnly = false {
    didSet {
      guard oldValue != filterThisDeviceOnly else { return }
      bumpScopeGeneration()
      displayLimit = pageSize
      Task { await loadMemories() }
    }
  }

  /// Whether the backend supports device_scope filtering for this user.
  /// Canonical memory users support it; legacy users get a 400. Legacy rows
  /// have no capture provenance, so after that fallback we preserve the
  /// unscoped list rather than falsely filtering every row out locally.
  private var deviceScopeSupported = true

  @Published var selectedTags: Set<MemoryTag> = [] {
    didSet {
      // Reset display limit when filters change
      bumpScopeGeneration()
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

  /// Counter bumped at the top of `refreshMemoriesIfNeeded()`, before any of
  /// the early-exit guards. Lets `MemoriesViewModelObserverTests` prove that
  /// posting `didBecomeActive` / `.refreshAllData` actually reaches the refresh
  /// method — if the observer rewire regresses, the counter stays flat and the
  /// test fails.
  /// Deliberately **not** `@Published` — publishing on every activation/Cmd+R
  /// refresh would emit `objectWillChange` and invalidate any SwiftUI view
  /// observing `MemoriesViewModel`, which is a pure production cost for a
  /// value nothing drives UI from.
  private(set) var refreshInvocations: Int = 0
  /// Bumped at the top of `handleConversationDeleted()` for observer wiring tests.
  private(set) var conversationDeleteInvocations: Int = 0
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
  // Tracks the raw backend fetch cursor independently from the visible/SQLite
  // cursor (currentOffset). The API returns unscoped/default-scope pages that
  // may contain items excluded by the current layer filter. Advancing the
  // backend offset by only the visible count would re-request part of the same
  // raw page on the next loadMore(), causing overlapping pages and duplicates.
  private var rawBackendOffset = 0
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

  private struct MemoryScopeToken: Equatable {
    let generation: Int
    let layerFilter: MemoryLayerFilter
    let searchText: String
    let selectedTags: Set<MemoryTag>
  }

  private var scopeGeneration = 0

  private var activeLayerFilter: [MemoryLayer]? { canonicalLifecycleExposed ? selectedLayerFilter.allowedLayers : nil }
  private var activeLayerScope: MemoryLayerScope { selectedLayerFilter.layerScope }

  private var currentScopeToken: MemoryScopeToken {
    MemoryScopeToken(
      generation: scopeGeneration,
      layerFilter: selectedLayerFilter,
      searchText: searchText.trimmingCharacters(in: .whitespacesAndNewlines),
      selectedTags: selectedTags
    )
  }

  private func bumpScopeGeneration() {
    scopeGeneration += 1
  }

  private func isCurrentScope(_ token: MemoryScopeToken) -> Bool {
    token == currentScopeToken
  }

  private func layers(for token: MemoryScopeToken) -> [MemoryLayer]? {
    canonicalLifecycleExposed ? token.layerFilter.allowedLayers : nil
  }

  private func recordReadScope(for token: MemoryScopeToken) -> MemoryRecordReadScope {
    canonicalLifecycleExposed ? .canonicalProduct : .legacyCompatibility
  }

  private func displayMemories(_ values: [ServerMemory], for token: MemoryScopeToken) -> [ServerMemory] {
    displayMemories(values, lifecycleExposed: canonicalLifecycleExposed)
  }

  private func displayCacheMemories(_ values: [ServerMemory], for token: MemoryScopeToken) -> [ServerMemory] {
    displayMemories(values, for: token)
  }

  private func displayMemories(_ values: [ServerMemory], lifecycleExposed: Bool) -> [ServerMemory] {
    values.filter { $0.tierIsExplicit == lifecycleExposed }
  }

  private struct MemoryPageFetchResult {
    let page: APIClient.MemoryListPage
    let deviceScopeSupportedOverride: Bool?
  }

  private var lifecycleExposureCapabilityKey: String {
    let userId = UserDefaults.standard.string(forKey: "auth_userId") ?? "unknown"
    return "memoriesCanonicalLifecycleExposure_v1_\(userId)"
  }

  /// Restores the last authoritative lifecycle capability for this account.
  ///
  /// The cache itself cannot prove whether an untiered row is a legacy
  /// compatibility record or a local-pending write. Until the first response
  /// establishes that capability, defer cache rendering instead of briefly
  /// presenting those rows as product memories.
  @discardableResult
  private func restoreCanonicalLifecycleExposure() -> Bool {
    guard let exposed = UserDefaults.standard.object(forKey: lifecycleExposureCapabilityKey) as? Bool else {
      return false
    }
    canonicalLifecycleExposed = exposed
    return true
  }

  private func persistCanonicalLifecycleExposure(_ exposed: Bool) {
    UserDefaults.standard.set(exposed, forKey: lifecycleExposureCapabilityKey)
  }

  @discardableResult
  private func commitMemoryPageCapabilities(
    _ page: APIClient.MemoryListPage,
    for token: MemoryScopeToken,
    expectedOffset: Int? = nil,
    deviceScopeSupportedOverride: Bool? = nil
  ) -> Bool {
    guard isCurrentScope(token) else { return false }
    if let expectedOffset, currentOffset != expectedOffset { return false }
    canonicalLifecycleExposed = page.canonicalLifecycleExposed
    persistCanonicalLifecycleExposure(page.canonicalLifecycleExposed)
    if let deviceScopeCapability = deviceScopeSupportedOverride ?? page.deviceScopeSupported {
      deviceScopeSupported = deviceScopeCapability
    }
    return isCurrentScope(token)
  }

  private func layerAllowed(_ memory: ServerMemory, for token: MemoryScopeToken) -> Bool {
    guard memory.tierIsExplicit == canonicalLifecycleExposed else { return false }
    guard let allowedLayers = layers(for: token) else { return true }
    return Set(allowedLayers).contains(memory.tier)
  }

  private func reloadForCurrentLayerFilter() async {
    let token = currentScopeToken
    if !token.searchText.isEmpty {
      await performSearch()
      guard isCurrentScope(token) else { return }
    }
    if !token.selectedTags.isEmpty {
      await loadFilteredMemoriesFromDatabase()
      guard isCurrentScope(token) else { return }
    } else {
      do {
        let loaded = try await MemoryStorage.shared.getLocalMemories(
          limit: pageSize,
          offset: 0,
          tiers: layers(for: token),
          scope: recordReadScope(for: token)
        )
        guard isCurrentScope(token) else { return }
        memories = displayCacheMemories(loaded, for: token)
        currentOffset = loaded.count
        hasMoreMemories = loaded.count >= pageSize
        recomputeFilteredMemories()
      } catch {
        guard isCurrentScope(token) else { return }
        logError("MemoriesViewModel: Failed to reload tier-filtered memories", error: error)
        recomputeFilteredMemories()
      }
    }
    guard isCurrentScope(token) else { return }
    await loadTagCountsFromDatabase()
  }

  private var bulkServerMutationsAvailable: Bool { false }
  var areBulkServerMutationsAvailable: Bool { bulkServerMutationsAvailable }

  // MARK: - Initialization

  init() {
    // Owner fencing: an in-place account switch posts only
    // .runtimeOwnerDidChange (never .userDidSignOut), so without this reset the
    // previous owner's memories keep rendering until the container's deferred
    // startup reset runs. Mirrors TasksStore.resetSessionState's subscription.
    NotificationCenter.default.publisher(for: .runtimeOwnerDidChange)
      .sink { [weak self] _ in
        MainActor.assumeIsolated {
          self?.resetSessionState()
        }
      }
      .store(in: &cancellables)

    // Refresh memories when app becomes active
    NotificationCenter.default.publisher(for: NSApplication.didBecomeActiveNotification)
      .sink { [weak self] _ in
        Task { await self?.refreshMemoriesIfNeeded() }
      }
      .store(in: &cancellables)

    // Cmd+R: refresh memories on demand
    NotificationCenter.default.publisher(for: .refreshAllData)
      .sink { [weak self] _ in
        Task { await self?.refreshMemoriesIfNeeded() }
      }
      .store(in: &cancellables)

    // Conversation delete: purge conversation-sourced memories from local cache + re-fetch.
    NotificationCenter.default.publisher(for: .conversationDeleted)
      .sink { [weak self] notification in
        guard let conversationId = notification.userInfo?["conversationId"] as? String else { return }
        Task { await self?.handleConversationDeleted(conversationId) }
      }
      .store(in: &cancellables)
  }

  /// After conversation delete (server cascade retract + local cache purge).
  func handleConversationDeleted(_ conversationId: String) async {
    conversationDeleteInvocations += 1
    guard AuthState.shared.isSignedIn else { return }

    do {
      let removed = try await MemoryStorage.shared.softDeleteMemoriesByConversationId(conversationId)
      if removed > 0 {
        log("MemoriesViewModel: Soft-deleted \(removed) local memories for conversation \(conversationId)")
      }
    } catch {
      logError("MemoriesViewModel: Failed to soft-delete memories for conversation \(conversationId)", error: error)
    }

    memories.removeAll { $0.conversationId == conversationId }
    recomputeFilteredMemories()

    // Re-fetch from backend (source of truth after cascade retract).
    if hasLoadedInitially {
      await refreshMemoriesAfterConversationCascade()
    }
  }

  /// Paginated server pull + orphan prune after conversation cascade delete.
  /// Catches promoted memories whose projection dropped `conversation_id`.
  private func refreshMemoriesAfterConversationCascade() async {
    let token = currentScopeToken
    var offset = 0
    let batchSize = 500
    var allFetched: [ServerMemory] = []
    var fetchedLifecycleExposure: Bool?

    do {
      while true {
        let page = try await APIClient.shared.getMemoriesPage(limit: batchSize, offset: offset)
        fetchedLifecycleExposure = page.canonicalLifecycleExposed
        let batch = page.memories
        if batch.isEmpty { break }
        allFetched.append(contentsOf: batch)
        offset += batch.count
        if batch.count < batchSize { break }
      }

      // A successful fetch (even if empty) is an authoritative keep-set for
      // pruning. Without this, stale SQLite rows remain visible after a
      // conversation cascade delete retracts all backend memories.
      let pruned = try await MemoryStorage.shared.syncServerMemoriesAndPruneAbsent(
        allFetched,
        within: .defaultAccess
      )
      if pruned > 0 {
        log("MemoriesViewModel: Pruned \(pruned) server-backed orphans after conversation delete")
      }

      let reloadLimit = max(pageSize, memories.count)
      let mergedMemories = try await MemoryStorage.shared.getLocalMemories(
        limit: reloadLimit,
        offset: 0,
        tiers: layers(for: token),
        scope: recordReadScope(for: token)
      )
      guard isCurrentScope(token) else { return }
      if let fetchedLifecycleExposure {
        canonicalLifecycleExposed = fetchedLifecycleExposure
        guard isCurrentScope(token) else { return }
      }
      memories = displayCacheMemories(mergedMemories, for: token)
      currentOffset = mergedMemories.count
      hasMoreMemories = mergedMemories.count >= reloadLimit
      recomputeFilteredMemories()
      await loadTagCountsFromDatabase()
    } catch {
      logError("MemoriesViewModel: Failed to refresh after conversation delete", error: error)
      await loadMemories()
    }
  }

  func resetSessionState() {
    deleteTask?.cancel()
    deleteTask = nil
    memories = []
    isLoading = false
    isLoadingMore = false
    hasMoreMemories = true
    errorMessage = nil
    searchText = ""
    isSearching = false
    searchResults = []
    canonicalLifecycleExposed = false
    selectedLayerFilter = .defaultAccess
    selectedTags = []
    filteredFromDatabase = []
    isLoadingFiltered = false
    refreshInvocations = 0
    showingAddMemory = false
    newMemoryText = ""
    editingMemory = nil
    editText = ""
    selectedMemory = nil
    pendingDeleteMemory = nil
    undoTimeRemaining = 0
    hasLoadedInitially = false
    isActive = false
    currentOffset = 0
    rawBackendOffset = 0
    showingDeleteAllConfirmation = false
    isBulkOperationInProgress = false
    linkedConversation = nil
    isLoadingConversation = false
    isTogglingVisibility = false
    totalMemoriesCount = 0
    hasMoreFilteredResults = false
    allFilteredResults = []
    displayLimit = pageSize
  }

  /// Refresh memories if already loaded (for auto-refresh)
  private func refreshMemoriesIfNeeded() async {
    refreshInvocations += 1
    // Skip if user is signed out (tokens are cleared)
    guard AuthState.shared.isSignedIn else { return }
    // Skip if page is not visible
    guard isActive else { return }

    // Skip if currently loading or haven't loaded initially
    guard !isLoading, !isLoadingMore, hasLoadedInitially else { return }

    // Skip if there's a pending delete (avoid interfering with undo)
    guard pendingDeleteMemory == nil else { return }

    // Silently sync from API and reload from local cache (local-first pattern)
    let token = currentScopeToken
    do {
      let reloadLimit = max(pageSize, memories.count)
      let page = try await APIClient.shared.getMemoriesPage(limit: reloadLimit, offset: 0)
      let apiMemories = page.memories
      guard commitMemoryPageCapabilities(page, for: token) else { return }

      // Sync API results to local cache
      try await MemoryStorage.shared.syncServerMemories(apiMemories)

      // Reload from local cache to get merged data (local + synced)
      let mergedMemories = try await MemoryStorage.shared.getLocalMemories(
        limit: reloadLimit,
        offset: 0,
        tiers: layers(for: token),
        scope: recordReadScope(for: token)
      )
      guard isCurrentScope(token) else { return }
      log(
        "MemoriesViewModel: Auto-refresh showing \(mergedMemories.count) memories (API had \(apiMemories.count))"
      )
      memories = displayCacheMemories(mergedMemories, for: token)
      currentOffset = mergedMemories.count
      rawBackendOffset = apiMemories.count
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
      let totalCount = try await MemoryStorage.shared.getLocalMemoriesCount(
        tiers: activeLayerFilter,
        scope: canonicalLifecycleExposed ? .canonicalProduct : .legacyCompatibility
      )
      totalMemoriesCount = totalCount

      // One count per backend category (mirrors mobile).
      for tag in MemoryTag.allCases {
        counts[tag] = try await MemoryStorage.shared.getLocalMemoriesCount(
          category: tag.rawValue,
          tiers: activeLayerFilter,
          scope: canonicalLifecycleExposed ? .canonicalProduct : .legacyCompatibility
        )
      }

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
    let token = currentScopeToken
    guard !token.selectedTags.isEmpty else {
      guard isCurrentScope(token) else { return }
      filteredFromDatabase = []
      recomputeFilteredMemories()
      return
    }

    isLoadingFiltered = true

    // Filter purely by backend category (OR logic across selected categories).
    let matchAnyCategory: [String] = token.selectedTags.map { $0.rawValue }

    do {
      let results = try await MemoryStorage.shared.getFilteredMemories(
        limit: 10000,
        matchAnyTag: nil,
        matchAnyCategory: matchAnyCategory.isEmpty ? nil : matchAnyCategory,
        tiers: layers(for: token),
        scope: recordReadScope(for: token)
      )

      guard isCurrentScope(token) else { return }
      let filteredResults = results.filter { memory in
        token.selectedTags.contains { tag in tag.matches(memory) }
      }

      filteredFromDatabase = displayCacheMemories(filteredResults, for: token)
      log(
        "MemoriesViewModel: Loaded \(filteredResults.count) filtered memories from SQLite (raw: \(results.count))"
      )
    } catch {
      guard isCurrentScope(token) else { return }
      logError("MemoriesViewModel: Failed to load filtered memories", error: error)
      filteredFromDatabase = []
    }

    guard isCurrentScope(token) else { return }
    isLoadingFiltered = false
    recomputeFilteredMemories()
  }

  /// Recompute filtered memories when search/tags/layer change
  private func recomputeFilteredMemories() {
    // Must match the isInFilteredMode property so pagination routing is
    // consistent. Layer-only views and device-scoped views are excluded from
    // "filtered mode" because they paginate via loadMore()
    // (SQLite/API batches), not loadMoreFiltered() (in-memory expansion of a
    // single-page allFilteredResults array).
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

    // Guardrail: Archive is never part of the default list unless the user explicitly selects Archive.
    if let allowedLayers = activeLayerFilter {
      let allowedTiers = Set(allowedLayers)
      result = result.filter { allowedTiers.contains($0.tier) }
    }

    // A canonical response has already been filtered server-side and its
    // provenance is authoritative. Legacy rows cannot identify their capture
    // device, so keeping them visible is the only honest fallback; filtering
    // them client-side would turn the list into a misleading empty state.
    if filterThisDeviceOnly && deviceScopeSupported {
      result = result.filter { ClientDeviceService.shared.memoryMatchesThisDevice($0) }
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
    let token = currentScopeToken
    let query = token.searchText

    // If search is empty, clear results and show all memories
    if query.isEmpty {
      guard isCurrentScope(token) else { return }
      searchResults = []
      isSearching = false
      recomputeFilteredMemories()
      return
    }

    isSearching = true

    do {
      let results = try await MemoryStorage.shared.searchLocalMemories(
        query: query,
        limit: 10000,
        tiers: layers(for: token),
        scope: recordReadScope(for: token)
      )
      guard isCurrentScope(token) else { return }
      searchResults = displayCacheMemories(results, for: token)
      log("MemoriesViewModel: Search for '\(query)' found \(results.count) results")
    } catch {
      guard isCurrentScope(token) else { return }
      logError("MemoriesViewModel: Search failed", error: error)
      // Fall back to in-memory filtering within the captured tier scope.
      searchResults = memories.filter {
        layerAllowed($0, for: token) && $0.content.localizedCaseInsensitiveContains(query)
      }
    }

    guard isCurrentScope(token) else { return }
    isSearching = false
    recomputeFilteredMemories()
  }

  // MARK: - API Actions

  /// Fetch memories from the API, honoring the device-scope filter only when
  /// the backend supports it for this user. Legacy (non-canonical) memory users
  /// get a 400 from device_scope=current; on that we retry without the scope
  /// and return the capability update to the guarded page commit. Legacy rows
  /// lack capture provenance, so recomputeFilteredMemories keeps that fallback
  /// list visible.
  private func fetchMemoriesPageDeviceScopeAware(limit: Int, offset: Int) async throws -> MemoryPageFetchResult {
    let scope = (filterThisDeviceOnly && deviceScopeSupported) ? "current" : nil
    do {
      let page = try await APIClient.shared.getMemoriesPage(limit: limit, offset: offset, deviceScope: scope)
      return MemoryPageFetchResult(page: page, deviceScopeSupportedOverride: nil)
    } catch APIError.httpError(let statusCode, _) where statusCode == 400 && scope != nil {
      // Backend rejected device_scope for a non-canonical user — retry unscoped.
      log("MemoriesViewModel: device_scope unsupported by backend, retrying unscoped")
      DesktopDiagnosticsManager.shared.recordFallback(
        area: "other",
        from: "device_scoped",
        to: "unscoped",
        reason: "capability_mismatch",
        outcome: .degraded,
        extra: ["user_visible": false]
      )
      let page = try await APIClient.shared.getMemoriesPage(limit: limit, offset: offset, deviceScope: nil)
      return MemoryPageFetchResult(page: page, deviceScopeSupportedOverride: false)
    }
  }

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
    rawBackendOffset = 0
    let token = currentScopeToken
    let tokenTiers = layers(for: token)
    let hasRememberedLifecycleExposure = restoreCanonicalLifecycleExposure()

    // Step 1: Load from local cache first for instant display
    // A cache alone cannot establish an account's lifecycle capability. On a
    // first launch, wait for the authoritative response rather than flash
    // untiered legacy/local-pending records in a canonical user experience.
    // Use timeout to avoid blocking UI if database is initializing (e.g. recovery).
    if hasRememberedLifecycleExposure {
      do {
        let cachedMemories = try await withThrowingTaskGroup(of: [ServerMemory].self) { group in
          group.addTask {
            try await MemoryStorage.shared.getLocalMemories(
              limit: self.pageSize,
              offset: 0,
              tiers: tokenTiers,
              scope: self.recordReadScope(for: token)
            )
          }
          group.addTask {
            try await Task.sleep(nanoseconds: 3_000_000_000)  // 3 second timeout
            throw CancellationError()
          }
          let result = try await group.next()!
          group.cancelAll()
          return result
        }

        if !cachedMemories.isEmpty, isCurrentScope(token) {
          memories = displayCacheMemories(cachedMemories, for: token)
          currentOffset = cachedMemories.count
          hasMoreMemories = cachedMemories.count >= pageSize
          isLoading = false  // Show cached data immediately
          log("MemoriesViewModel: Loaded \(cachedMemories.count) memories from local cache")
        }
      } catch {
        log("MemoriesViewModel: Local cache unavailable, falling back to API")
        // Continue to API fetch even if cache fails
      }
    } else {
      log("MemoriesViewModel: Deferring unclassified cache until lifecycle capability is confirmed")
    }

    // Step 2: Fetch from API in background and sync to local cache
    do {
      let fetchResult = try await fetchMemoriesPageDeviceScopeAware(
        limit: pageSize,
        offset: 0
      )
      let page = fetchResult.page
      let fetchedMemories = page.memories
      guard isCurrentScope(token) else {
        // Scope changed mid-load; reset loading state so the replacement load
        // (gated by `guard !isLoading`) is not permanently blocked.
        isLoading = false
        return
      }
      guard
        commitMemoryPageCapabilities(
          page,
          for: token,
          deviceScopeSupportedOverride: fetchResult.deviceScopeSupportedOverride
        )
      else {
        isLoading = false
        return
      }
      hasLoadedInitially = true
      log("MemoriesViewModel: Fetched \(fetchedMemories.count) memories from API")

      // Step 3: Sync API results to local cache, then reload from cache
      // This ensures we show ALL local data (including locally-created memories)
      // merged with any updates from the server
      do {
        try await MemoryStorage.shared.syncServerMemories(fetchedMemories)
        log("MemoriesViewModel: Synced \(fetchedMemories.count) memories to local cache")

        // For device-scoped loads the server already filtered to this device.
        // Reloading from the unscoped SQLite cache can surface other devices'
        // newer memories that recomputeFilteredMemories() then strips, leaving
        // an empty/short initial page that cannot paginate. Display the fetched
        // page directly instead. (If device_scope 400'd, the committed
        // capability override is false so we take the merged-cache path with
        // client-side filtering.)
        let wasDeviceScoped = filterThisDeviceOnly && deviceScopeSupported
        let displayMemories: [ServerMemory]
        if wasDeviceScoped {
          displayMemories = fetchedMemories.filter { layerAllowed($0, for: token) }
        } else {
          // Reload from local cache to get merged data
          displayMemories = try await MemoryStorage.shared.getLocalMemories(
            limit: pageSize,
            offset: 0,
            tiers: layers(for: token),
            scope: recordReadScope(for: token)
          )
        }
        guard isCurrentScope(token) else {
          // Scope changed mid-merge; reset loading state so the replacement
          // load is not permanently blocked.
          isLoading = false
          return
        }
        let visibleMemories = self.displayCacheMemories(displayMemories, for: token)
        memories = visibleMemories
        currentOffset = visibleMemories.count
        // Track the raw backend cursor for subsequent loadMore() fetches.
        rawBackendOffset = fetchedMemories.count
        // Use the raw backend page count for pagination, not the tier-filtered
        // count. The API fetch is an unscoped/default-scope page, so a full raw
        // page may contain fewer tier-matching items than pageSize while later
        // backend pages still hold matches for the selected layer. Deriving
        // hasMoreMemories from the filtered count would disable scrolling and
        // permanently hide those memories. This matches the error-fallback path
        // below and the loadMore() API path.
        hasMoreMemories = fetchedMemories.count >= pageSize
        log(
          "MemoriesViewModel: Showing \(visibleMemories.count) memories from \(wasDeviceScoped ? "device-scoped API" : "merged local cache")"
        )
      } catch {
        logError("MemoriesViewModel: Failed to sync/reload from local cache", error: error)
        // Fall back to API data if sync fails, preserving the desktop default-access guardrail.
        memories = displayMemories(fetchedMemories.filter { layerAllowed($0, for: token) }, for: token)
        currentOffset = memories.count
        rawBackendOffset = fetchedMemories.count
        hasMoreMemories = fetchedMemories.count >= pageSize
      }
    } catch {
      // Only show error if we don't have cached data
      if memories.isEmpty {
        errorMessage = UserFacingErrorPresentation.message(for: error, while: .memories)
      }
      logError("Failed to load memories from API", error: error)
    }

    isLoading = false

    // Kick off one-time full sync, then a one-time cache reconcile, in background.
    Task {
      await performFullSyncIfNeeded()
      await reconcileCacheIfNeeded()
    }
  }

  func loadMemoriesIfNeeded() async {
    guard !hasLoadedInitially && memories.isEmpty else { return }
    await loadMemories()
  }

  /// One-time cache reconcile. The local SQLite cache can diverge from the
  /// backend (the source of truth): stale categories after the server-side
  /// category cleanup, plus "orphan" rows whose backendId no longer exists on
  /// the backend. This re-pulls every backend memory (fixing categories via the
  /// normal upsert) and soft-deletes synced local rows the backend no longer
  /// has. Local-only unsynced memories are preserved. Runs once per user.
  private func reconcileCacheIfNeeded() async {
    let userId = UserDefaults.standard.string(forKey: "auth_userId") ?? "unknown"
    let reconcileKey = "memoriesCacheReconcile_v2_defaultScopeNoPrune_\(userId)"

    guard !UserDefaults.standard.bool(forKey: reconcileKey) else { return }

    log("MemoriesViewModel: Starting one-time cache reconcile for user \(userId)")

    var offset = 0
    let batchSize = 500
    var backendIds = Set<String>()

    do {
      while true {
        let page = try await APIClient.shared.getMemoriesPage(limit: batchSize, offset: offset)
        let batch = page.memories
        if batch.isEmpty { break }

        try await MemoryStorage.shared.syncServerMemories(batch)
        for memory in batch { backendIds.insert(memory.id) }
        offset += batch.count

        if batch.count < batchSize { break }
      }

      // Guard against pruning on a partial/failed pull: only reconcile when the
      // backend actually returned memories. An empty result here would otherwise
      // wrongly delete the entire local cache.
      guard !backendIds.isEmpty else {
        log("MemoriesViewModel: Cache reconcile skipped pruning (no backend memories returned)")
        return
      }

      // The current API does not return authoritative tier-scope/completeness metadata.
      // Fail closed: sync returned default-scope rows, but do not prune orphans until the
      // backend can prove this page set is complete for an explicit scope. This preserves
      // Archive rows when the default endpoint omits them by design.
      UserDefaults.standard.set(true, forKey: reconcileKey)
      log("MemoriesViewModel: Cache reconcile skipped orphan pruning because backend completeness is unknown")

      await loadTagCountsFromDatabase()
      await loadMemories()
    } catch {
      logError("MemoriesViewModel: Cache reconcile failed (will retry next launch)", error: error)
    }
  }

  /// One-time background sync for the backend default memory scope.
  /// Archive requires an explicit backend contract before desktop syncs or reconciles it.
  private func performFullSyncIfNeeded() async {
    let userId = UserDefaults.standard.string(forKey: "auth_userId") ?? "unknown"
    let syncKey = "memoriesDefaultScopeSyncCompleted_v3_\(userId)"

    guard !UserDefaults.standard.bool(forKey: syncKey) else {
      log("MemoriesViewModel: Full sync already completed for user \(userId)")
      return
    }

    log("MemoriesViewModel: Starting one-time default-scope sync for user \(userId)")

    var offset = 0
    var totalSynced = 0
    let batchSize = 500

    do {
      while true {
        let page = try await APIClient.shared.getMemoriesPage(limit: batchSize, offset: offset)
        let batch = page.memories
        if batch.isEmpty { break }

        try await MemoryStorage.shared.syncServerMemories(batch)
        totalSynced += batch.count
        offset += batch.count
        log("MemoriesViewModel: Full sync progress - \(totalSynced) additional memories synced")

        if batch.count < batchSize { break }
      }

      UserDefaults.standard.set(true, forKey: syncKey)
      log("MemoriesViewModel: Default-scope sync completed - \(totalSynced) additional memories synced")

      // Refresh tag counts now that SQLite has everything
      await loadTagCountsFromDatabase()
    } catch {
      logError("MemoriesViewModel: Full sync failed (will retry next launch)", error: error)
    }
  }

  /// Whether we're currently in a filtered/search mode.
  ///
  /// Layer-only views (Short-term/Long-term/Archive) and device-scoped views
  /// are intentionally NOT included here: they load paginated batches from
  /// SQLite via the same loadMore() path as the default view, just with a
  /// tier/device filter applied. Treating them as "filtered" would route
  /// pagination through loadMoreFiltered(), which only expands the in-memory
  /// allFilteredResults array (capped at one page), preventing further
  /// SQLite/API pagination.
  var isInFilteredMode: Bool {
    !searchText.isEmpty || !selectedTags.isEmpty
  }

  /// Load more memories (pagination) - triggered by scrolling near end
  func loadMoreIfNeeded(currentMemory: ServerMemory) async {
    let hasMore = isInFilteredMode ? hasMoreFilteredResults : hasMoreMemories
    guard hasMore, !isLoading, !isLoadingMore else { return }

    // Only load more when near the end of the list
    let thresholdIndex =
      filteredMemories.index(
        filteredMemories.endIndex, offsetBy: -10, limitedBy: filteredMemories.startIndex)
      ?? filteredMemories.startIndex
    guard let memoryIndex = filteredMemories.firstIndex(where: { $0.id == currentMemory.id }),
      memoryIndex >= thresholdIndex
    else {
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
    // Clear the flag on every exit path, including stale-scope guard returns,
    // so pagination is not permanently blocked by `guard !isLoadingMore`.
    defer { isLoadingMore = false }
    let token = currentScopeToken
    let requestedOffset = currentOffset
    let requestedRawOffset = rawBackendOffset

    // Step 1: Try to load more from local cache first
    do {
      let moreFromCache = try await MemoryStorage.shared.getLocalMemories(
        limit: pageSize,
        offset: requestedOffset,
        tiers: layers(for: token),
        scope: recordReadScope(for: token)
      )

      guard isCurrentScope(token), currentOffset == requestedOffset else { return }
      if !moreFromCache.isEmpty {
        let visibleMemories = displayCacheMemories(moreFromCache, for: token)
        memories.append(contentsOf: visibleMemories)
        // Advance the SQLite paging cursor by the RAW row count returned by the
        // query, not the tier-filtered visible count. getLocalMemories(offset:)
        // pages over raw rows, so advancing by the smaller filtered count makes the
        // next page re-fetch the filtered-out rows — duplicate/stuck paging once
        // hasMoreMemories (below) correctly stays true on a filtered page.
        currentOffset += moreFromCache.count
        // Derive hasMoreMemories from the RAW cache count, not the tier-filtered
        // visible count. A full raw page whose visible subset is < pageSize still
        // has more cached rows to page; using the filtered count here disabled
        // scrolling and permanently hid those memories (the initial-load path
        // already documents this exact raw-vs-filtered pagination rule).
        hasMoreMemories = moreFromCache.count >= pageSize
        log(
          "MemoriesViewModel: Loaded \(visibleMemories.count) more from local cache (total: \(memories.count))"
        )
        return
      }
    } catch {
      log("MemoriesViewModel: Local cache pagination failed, trying API")
    }

    // Step 2: If local cache is exhausted, fetch from API
    // Pass deviceScope so the server filters for device-scoped views, keeping
    // pagination server-side rather than limited to the first in-memory page.
    // Use the raw backend offset (not the visible/SQLite offset) so that layer
    // filtering does not cause overlapping pages or duplicate appends.
    do {
      let fetchResult = try await fetchMemoriesPageDeviceScopeAware(
        limit: pageSize,
        offset: requestedRawOffset
      )
      let page = fetchResult.page
      let newMemories = page.memories
      guard
        commitMemoryPageCapabilities(
          page,
          for: token,
          expectedOffset: requestedOffset,
          deviceScopeSupportedOverride: fetchResult.deviceScopeSupportedOverride
        )
      else { return }

      // Sync to local cache first
      try await MemoryStorage.shared.syncServerMemories(newMemories)

      let visibleNewMemories = displayMemories(newMemories.filter { layerAllowed($0, for: token) }, for: token)

      // Then append to display
      memories.append(contentsOf: visibleNewMemories)
      currentOffset += visibleNewMemories.count
      // Advance the raw backend cursor by the raw page size so the next fetch
      // starts after all items in this page, not just the visible subset.
      rawBackendOffset += newMemories.count
      hasMoreMemories = newMemories.count >= pageSize
      log(
        "MemoriesViewModel: Loaded \(visibleNewMemories.count) more visible memories from API (raw: \(newMemories.count), total: \(memories.count))"
      )
    } catch {
      logError("Failed to load more memories", error: error)
    }
  }

  func createMemory() async {
    guard !newMemoryText.isEmpty else { return }

    do {
      _ = try await APIClient.shared.createMemory(content: newMemoryText, category: .manual)
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

    do {
      try await MemoryStorage.shared.deleteMemoryByBackendId(memory.id)
    } catch {
      logError("Failed to soft-delete memory locally", error: error)
    }

    // Remove from UI immediately (optimistic) — must also remove from filter source arrays
    // so recomputeFilteredMemories() doesn't resurrect the deleted memory.
    OmiMotion.withGated(.easeInOut(duration: 0.2)) {
      memories.removeAll { $0.id == memory.id }
      filteredFromDatabase.removeAll { $0.id == memory.id }
      allFilteredResults.removeAll { $0.id == memory.id }
      searchResults.removeAll { $0.id == memory.id }
      pendingDeleteMemory = memory
      undoTimeRemaining = 4
    }

    // The soft-delete above immediately drops this row from getLocalMemories(), so
    // the SQLite paging cursor is now one position too high — the next loadMore()
    // would skip the item that shifted into the old cursor slot. Back the
    // visible/cache cursor off by one. (rawBackendOffset is adjusted separately in
    // performActualDelete, only after the backend row is actually removed, because
    // the backend still holds the row during the undo window.) Undo and
    // delete-failure both call reloadForCurrentLayerFilter(), which recomputes
    // currentOffset from offset 0, so this decrement safely unwinds.
    currentOffset = max(0, currentOffset - 1)

    // Start countdown timer
    deleteTask = Task {
      // Update countdown every 100ms
      for _ in 0..<40 {
        try? await Task.sleep(nanoseconds: 100_000_000)  // 100ms
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

    OmiMotion.withGated(.easeInOut(duration: 0.2)) {
      pendingDeleteMemory = nil
      undoTimeRemaining = 0
    }

    Task {
      do {
        try await MemoryStorage.shared.restoreMemoryByBackendId(memory.id)
      } catch {
        logError("Failed to restore memory locally", error: error)
      }
      await reloadForCurrentLayerFilter()
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

    OmiMotion.withGated(.easeInOut(duration: 0.2)) {
      pendingDeleteMemory = nil
      undoTimeRemaining = 0
    }
  }

  private func performActualDelete(_ memory: ServerMemory) async {
    do {
      try await APIClient.shared.deleteMemory(id: memory.id)
      AnalyticsManager.shared.memoryDeleted(conversationId: memory.id)
      // The backend row is now gone, so the raw backend paging cursor is one
      // position too high — decrement it so the next API-backed loadMore() doesn't
      // skip the item that shifted into the old cursor slot. Done here rather than
      // in the optimistic block because the backend still holds the row during the
      // undo window; decrementing earlier would re-fetch and duplicate it.
      rawBackendOffset = max(0, rawBackendOffset - 1)
    } catch {
      logError("Failed to delete memory", error: error)
      do {
        try await MemoryStorage.shared.restoreMemoryByBackendId(memory.id)
      } catch {
        logError("Failed to restore memory after delete failure", error: error)
      }
      await reloadForCurrentLayerFilter()
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
      try await MemoryStorage.shared.updateVisibilityByBackendId(
        memory.id, visibility: newVisibility)

      // Update memory in place
      if let index = memories.firstIndex(where: { $0.id == memory.id }) {
        memories[index].visibility = newVisibility
      }
      if let index = searchResults.firstIndex(where: { $0.id == memory.id }) {
        searchResults[index].visibility = newVisibility
      }
      if let index = filteredFromDatabase.firstIndex(where: { $0.id == memory.id }) {
        filteredFromDatabase[index].visibility = newVisibility
      }
      recomputeFilteredMemories()
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

  private var currentBulkScope: MemoryLayerScope { activeLayerScope }

  func makeMemoriesPrivate(scope: MemoryLayerScope? = nil) async {
    let scope = scope ?? currentBulkScope
    isBulkOperationInProgress = true
    defer { isBulkOperationInProgress = false }
    do {
      try await APIClient.shared.updateAllMemoriesVisibility(scope: scope, visibility: "private")
      try await MemoryStorage.shared.updateVisibility(scope: scope, visibility: "private")
      await reloadForCurrentLayerFilter()
    } catch {
      errorMessage = UserFacingErrorPresentation.message(for: error, while: .memoryVisibility)
      logError("Bulk make private disabled or failed", error: error)
    }
  }

  func makeMemoriesPublic(scope: MemoryLayerScope? = nil) async {
    let scope = scope ?? currentBulkScope
    isBulkOperationInProgress = true
    defer { isBulkOperationInProgress = false }
    do {
      try await APIClient.shared.updateAllMemoriesVisibility(scope: scope, visibility: "public")
      try await MemoryStorage.shared.updateVisibility(scope: scope, visibility: "public")
      await reloadForCurrentLayerFilter()
    } catch {
      errorMessage = UserFacingErrorPresentation.message(for: error, while: .memoryVisibility)
      logError("Bulk make public disabled or failed", error: error)
    }
  }

  func deleteMemories(scope: MemoryLayerScope? = nil, archiveAcknowledged: Bool = false) async {
    let scope = scope ?? currentBulkScope
    if scope.includesArchive && !archiveAcknowledged {
      errorMessage = "Archive deletion requires explicit Archive confirmation."
      return
    }

    isBulkOperationInProgress = true
    defer { isBulkOperationInProgress = false }

    // Cancel any pending single delete
    deleteTask?.cancel()
    pendingDeleteMemory = nil

    do {
      try await APIClient.shared.deleteAllMemories(scope: scope)
      try await MemoryStorage.shared.deleteAllMemories(scope: scope)
      await reloadForCurrentLayerFilter()
    } catch {
      errorMessage = UserFacingErrorPresentation.message(for: error, while: .memoryDeletion)
      logError("Bulk delete disabled or failed", error: error)
    }
  }

  // MARK: - Automation (headless memory search/filter/visibility for desktop bridge)

  private var didRegisterAutomationActions = false

  func registerAutomationActions() {
    guard !didRegisterAutomationActions else { return }
    didRegisterAutomationActions = true
    let registry = DesktopAutomationActionRegistry.shared

    registry.register(
      name: "memories_search",
      summary: "Set memories search query and return filtered result count",
      params: ["query"]
    ) { [weak self] params in
      guard let self else { return ["error": "memories view model deallocated"] }
      let query = params["query"] ?? ""
      self.searchText = query
      let trimmed = query.trimmingCharacters(in: .whitespacesAndNewlines)
      if !trimmed.isEmpty {
        let startDeadline = Date().addingTimeInterval(2)
        while !self.isSearching, Date() < startDeadline {
          try? await Task.sleep(nanoseconds: 10_000_000)
        }
      }
      let deadline = Date().addingTimeInterval(10)
      while self.isSearching, Date() < deadline {
        try? await Task.sleep(nanoseconds: 50_000_000)
      }
      return [
        "query": query,
        "result_count": "\(self.filteredMemories.count)",
        "search_active": query.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ? "false" : "true",
        "is_searching": self.isSearching ? "true" : "false",
      ]
    }

    registry.register(
      name: "memories_set_tag_filter",
      summary: "Set memory tag/category filters and return filtered count",
      params: ["tags"]
    ) { [weak self] params in
      guard let self else { return ["error": "memories view model deallocated"] }
      let raw = params["tags"] ?? ""
      let tags: Set<MemoryTag>
      if raw.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
        tags = []
      } else {
        let parsed = raw.split(separator: ",")
          .map { $0.trimmingCharacters(in: .whitespacesAndNewlines).lowercased() }
          .compactMap { MemoryTag(rawValue: $0) }
        tags = Set(parsed)
      }
      self.selectedTags = tags
      if !tags.isEmpty {
        let startDeadline = Date().addingTimeInterval(2)
        while !self.isLoadingFiltered, Date() < startDeadline {
          try? await Task.sleep(nanoseconds: 10_000_000)
        }
      }
      let deadline = Date().addingTimeInterval(10)
      while self.isLoadingFiltered, Date() < deadline {
        try? await Task.sleep(nanoseconds: 50_000_000)
      }
      let tagList = tags.map(\.rawValue).sorted().joined(separator: ",")
      return [
        "tags": tagList.isEmpty ? "none" : tagList,
        "filtered_count": "\(self.filteredMemories.count)",
        "tag_filter_active": tags.isEmpty ? "false" : "true",
      ]
    }

    registry.register(
      name: "toggle_memory_visibility",
      summary: "Toggle a memory's public/private visibility via the real API path",
      params: ["id", "marker"]
    ) { [weak self] params in
      guard let self else { return ["error": "memories view model deallocated"] }
      if self.memories.isEmpty {
        await self.loadMemories()
      }
      let memory: ServerMemory?
      if let id = params["id"]?.trimmingCharacters(in: .whitespacesAndNewlines), !id.isEmpty {
        memory =
          self.memories.first(where: { $0.id == id })
          ?? self.searchResults.first(where: { $0.id == id })
          ?? self.filteredFromDatabase.first(where: { $0.id == id })
      } else if let marker = params["marker"]?.trimmingCharacters(in: .whitespacesAndNewlines),
        !marker.isEmpty
      {
        memory =
          self.memories.first(where: { $0.content.contains(marker) })
          ?? self.searchResults.first(where: { $0.content.contains(marker) })
          ?? self.filteredFromDatabase.first(where: { $0.content.contains(marker) })
      } else {
        memory = nil
      }
      guard let memory else {
        return ["error": "missing id or marker match"]
      }
      let priorVisibility = memory.visibility
      await self.toggleVisibility(memory)
      let updated =
        self.memories.first(where: { $0.id == memory.id })
        ?? self.searchResults.first(where: { $0.id == memory.id })
        ?? self.filteredFromDatabase.first(where: { $0.id == memory.id })
      let newVisibility = updated?.visibility ?? (priorVisibility == "public" ? "private" : "public")
      return [
        "memory_id": memory.id,
        "prior_visibility": priorVisibility,
        "visibility": newVisibility,
        "toggled": priorVisibility == newVisibility ? "false" : "true",
      ]
    }
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
  let graphViewModel: MemoryGraphViewModel
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
      EditMemorySheet(
        memory: memory, viewModel: viewModel, onDismiss: { viewModel.editingMemory = nil }
      )
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
    .task {
      await viewModel.loadMemoriesIfNeeded()
    }
  }

  // MARK: - Undo Delete Toast

  @ViewBuilder
  private var undoDeleteToast: some View {
    if viewModel.pendingDeleteMemory != nil {
      HStack(spacing: OmiSpacing.md) {
        Image(systemName: "trash")
          .scaledFont(size: OmiType.body)
          .foregroundColor(OmiColors.textSecondary)

        Text("Memory deleted")
          .scaledFont(size: OmiType.body)
          .foregroundColor(OmiColors.textPrimary)

        Spacer()

        // Progress indicator
        Text(String(format: "%.0fs", viewModel.undoTimeRemaining))
          .scaledFont(size: OmiType.caption, weight: .medium)
          .foregroundColor(OmiColors.textTertiary)
          .monospacedDigit()

        Button {
          viewModel.undoDelete()
        } label: {
          Text("Undo")
            .scaledFont(size: OmiType.body, weight: .semibold)
            .foregroundColor(OmiColors.textPrimary)
        }
        .buttonStyle(.plain)

        Button {
          // Dismiss immediately and delete now
          viewModel.confirmDelete()
        } label: {
          Image(systemName: "xmark")
            .scaledFont(size: OmiType.caption, weight: .medium)
            .foregroundColor(OmiColors.textTertiary)
        }
        .buttonStyle(.plain)
      }
      .padding(.horizontal, OmiSpacing.lg)
      .padding(.vertical, OmiSpacing.md)
      .omiPanel(
        fill: OmiColors.backgroundSecondary, radius: 20, stroke: OmiColors.border.opacity(0.18),
        shadowOpacity: 0.18, shadowRadius: 14, shadowY: 8
      )
      .padding(.horizontal, OmiSpacing.xxl)
      .padding(.bottom, OmiSpacing.xxl)
      .transition(.move(edge: .bottom).combined(with: .opacity))
      .omiAnimation(
        .spring(response: 0.3, dampingFraction: 0.8), value: viewModel.pendingDeleteMemory != nil)
    }
  }

  // MARK: - Header

  private var header: some View {
    HStack(spacing: OmiSpacing.md) {
      // Search field
      HStack(spacing: OmiSpacing.sm) {
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
      .padding(.horizontal, OmiSpacing.md)
      .padding(.vertical, OmiSpacing.md)
      .frame(minHeight: 46)
      .omiControlSurface(fill: OmiColors.backgroundTertiary, radius: 18)

      if viewModel.canonicalLifecycleExposed {
        // Layer filter dropdown. Default is product default access: Short-term + Long-term.
        Menu {
          ForEach(MemoryLayerFilter.allCases) { filter in
            Button {
              viewModel.selectedLayerFilter = filter
            } label: {
              HStack {
                Text(filter.displayName)
                if viewModel.selectedLayerFilter == filter {
                  Image(systemName: "checkmark")
                }
              }
            }
            .help(filter.description)
          }
        } label: {
          HStack(spacing: OmiSpacing.xs) {
            Image(systemName: viewModel.selectedLayerFilter == .archive ? "archivebox" : "clock.badge.checkmark")
              .scaledFont(size: OmiType.caption)
            Text(viewModel.selectedLayerFilter.displayName)
              .scaledFont(
                size: OmiType.body, weight: viewModel.selectedLayerFilter == .defaultAccess ? .regular : .medium)
            Image(systemName: "chevron.down")
              .scaledFont(size: OmiType.micro)
          }
          .foregroundColor(
            viewModel.selectedLayerFilter == .defaultAccess ? OmiColors.textSecondary : OmiColors.textPrimary
          )
          .padding(.horizontal, OmiSpacing.md)
          .padding(.vertical, OmiSpacing.md)
          .frame(minHeight: 46)
          .omiControlSurface(
            fill: viewModel.selectedLayerFilter == .defaultAccess
              ? OmiColors.backgroundTertiary : OmiColors.backgroundRaised,
            radius: 18,
            stroke: viewModel.selectedLayerFilter == .defaultAccess ? nil : OmiColors.border.opacity(0.6)
          )
        }
        .menuStyle(.button)
        .buttonStyle(.plain)
        .help("Default shows Short-term + Long-term. Archive is explicit.")
      }

      Button {
        viewModel.filterThisDeviceOnly.toggle()
      } label: {
        HStack(spacing: OmiSpacing.xs) {
          Image(systemName: "desktopcomputer")
            .scaledFont(size: OmiType.caption)
          Text("This device")
            .scaledFont(size: OmiType.body, weight: viewModel.filterThisDeviceOnly ? .medium : .regular)
        }
        .foregroundColor(
          viewModel.filterThisDeviceOnly ? OmiColors.textPrimary : OmiColors.textSecondary
        )
        .padding(.horizontal, OmiSpacing.md)
        .padding(.vertical, OmiSpacing.md)
        .frame(minHeight: 46)
        .omiControlSurface(
          fill: viewModel.filterThisDeviceOnly
            ? OmiColors.backgroundRaised : OmiColors.backgroundTertiary,
          radius: 18,
          stroke: viewModel.filterThisDeviceOnly ? OmiColors.border.opacity(0.6) : nil
        )
      }
      .buttonStyle(.plain)
      .help("Show memories captured on this Mac")

      // Category filter dropdown
      Button {
        pendingSelectedTags = viewModel.selectedTags
        categorySearchText = ""
        showCategoryFilter = true
      } label: {
        HStack(spacing: OmiSpacing.xs) {
          Image(systemName: "line.3.horizontal.decrease")
            .scaledFont(size: OmiType.caption)
          Text(categoryFilterLabel)
            .scaledFont(size: OmiType.body, weight: viewModel.selectedTags.isEmpty ? .regular : .medium)
          Image(systemName: "chevron.down")
            .scaledFont(size: OmiType.micro)
        }
        .foregroundColor(
          viewModel.selectedTags.isEmpty ? OmiColors.textSecondary : OmiColors.textPrimary
        )
        .padding(.horizontal, OmiSpacing.md)
        .padding(.vertical, OmiSpacing.md)
        .frame(minHeight: 46)
        .omiControlSurface(
          fill: viewModel.selectedTags.isEmpty
            ? OmiColors.backgroundTertiary : OmiColors.backgroundRaised,
          radius: 18,
          stroke: viewModel.selectedTags.isEmpty ? nil : OmiColors.border.opacity(0.6)
        )
      }
      .buttonStyle(.plain)
      .popover(isPresented: $showCategoryFilter, arrowEdge: .bottom) {
        categoryFilterPopover
      }

      // Add Memory button (icon only)
      Button {
        viewModel.showingAddMemory = true
      } label: {
        Image(systemName: "plus")
          .scaledFont(size: OmiType.body)
          .foregroundColor(.black)
          .frame(width: 42, height: 42)
          .background(OmiColors.textPrimary)
          .clipShape(RoundedRectangle(cornerRadius: OmiChrome.controlRadius, style: .continuous))
      }
      .buttonStyle(.plain)
      .help("Add Memory")

      // Management menu
      Button {
        showManagementMenu = true
      } label: {
        Image(systemName: "chevron.down")
          .scaledFont(size: OmiType.caption, weight: .medium)
          .foregroundColor(.black)
          .frame(width: 42, height: 42)
          .background(OmiColors.textPrimary)
          .clipShape(RoundedRectangle(cornerRadius: OmiChrome.controlRadius, style: .continuous))
      }
      .buttonStyle(.plain)
      .popover(isPresented: $showManagementMenu, arrowEdge: .bottom) {
        managementMenuPopover
      }
    }
    .padding(.horizontal, OmiSpacing.xxl)
    .padding(.top, OmiSpacing.xxl)
    .padding(.bottom, OmiSpacing.xl)
    .alert("Delete Default Memories?", isPresented: $viewModel.showingDeleteAllConfirmation) {
      Button("Cancel", role: .cancel) {}
      Button("Delete Default Memories", role: .destructive) {
        Task { await viewModel.deleteMemories(scope: .defaultAccess) }
      }
    } message: {
      Text(
        viewModel.canonicalLifecycleExposed
          ? "This would delete Short-term and Long-term memories only. Archive is not included. Bulk deletion remains disabled until the backend supports layer-scoped mutation semantics."
          : "This would delete default memories. Bulk deletion remains disabled until the backend supports scoped mutation semantics."
      )
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
      categories = MemoryTag.allCases.filter {
        $0.displayName.localizedCaseInsensitiveContains(categorySearchText)
      }
    }
    // Sort by count (highest first)
    return categories.sorted { viewModel.tagCount($0) > viewModel.tagCount($1) }
  }

  private var categoryFilterPopover: some View {
    VStack(spacing: 0) {
      // Search field
      HStack(spacing: OmiSpacing.sm) {
        Image(systemName: "magnifyingglass")
          .foregroundColor(OmiColors.textTertiary)
          .scaledFont(size: OmiType.caption)

        TextField("Search categories...", text: $categorySearchText)
          .textFieldStyle(.plain)
          .scaledFont(size: OmiType.body)
          .foregroundColor(OmiColors.textPrimary)

        if !categorySearchText.isEmpty {
          Button {
            categorySearchText = ""
          } label: {
            Image(systemName: "xmark.circle.fill")
              .foregroundColor(OmiColors.textTertiary)
              .scaledFont(size: OmiType.caption)
          }
          .buttonStyle(.plain)
        }
      }
      .padding(.horizontal, OmiSpacing.md)
      .padding(.vertical, OmiSpacing.sm)
      .background(OmiColors.backgroundTertiary)
      .cornerRadius(OmiChrome.badgeRadius)
      .padding(.horizontal, OmiSpacing.md)
      .padding(.top, OmiSpacing.md)
      .padding(.bottom, OmiSpacing.sm)

      Divider()
        .padding(.horizontal, OmiSpacing.md)

      // Category list
      ScrollView {
        VStack(spacing: OmiSpacing.hairline) {
          // "All" option
          Button {
            pendingSelectedTags.removeAll()
          } label: {
            HStack {
              Image(systemName: "tray.full")
                .scaledFont(size: OmiType.caption)
                .frame(width: 20)
              Text("All")
                .scaledFont(size: OmiType.body)
              Spacer()
              Text("\(viewModel.totalMemoriesCount)")
                .scaledFont(size: OmiType.caption)
                .foregroundColor(OmiColors.textTertiary)
                .padding(.horizontal, OmiSpacing.xs)
                .padding(.vertical, OmiSpacing.hairline)
                .background(OmiColors.backgroundTertiary)
                .cornerRadius(OmiChrome.stripRadius)
              if pendingSelectedTags.isEmpty {
                Image(systemName: "checkmark")
                  .scaledFont(size: OmiType.caption, weight: .medium)
                  .foregroundColor(.white)
              }
            }
            .foregroundColor(OmiColors.textPrimary)
            .padding(.horizontal, OmiSpacing.md)
            .padding(.vertical, OmiSpacing.sm)
            .background(
              pendingSelectedTags.isEmpty ? OmiColors.backgroundTertiary.opacity(0.5) : Color.clear
            )
            .cornerRadius(OmiChrome.badgeRadius)
            .contentShape(Rectangle())
          }
          .buttonStyle(.plain)

          Divider()
            .padding(.vertical, OmiSpacing.xxs)

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
                  .scaledFont(size: OmiType.caption)
                  .frame(width: 20)
                Text(tag.displayName)
                  .scaledFont(size: OmiType.body)
                Spacer()
                Text("\(count)")
                  .scaledFont(size: OmiType.caption)
                  .foregroundColor(OmiColors.textTertiary)
                  .padding(.horizontal, OmiSpacing.xs)
                  .padding(.vertical, OmiSpacing.hairline)
                  .background(OmiColors.backgroundTertiary)
                  .cornerRadius(OmiChrome.stripRadius)
                if isSelected {
                  Image(systemName: "checkmark")
                    .scaledFont(size: OmiType.caption, weight: .medium)
                    .foregroundColor(.white)
                }
              }
              .foregroundColor(OmiColors.textPrimary)
              .padding(.horizontal, OmiSpacing.md)
              .padding(.vertical, OmiSpacing.sm)
              .background(isSelected ? OmiColors.backgroundTertiary.opacity(0.5) : Color.clear)
              .cornerRadius(OmiChrome.badgeRadius)
              .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
          }
        }
        .padding(.horizontal, OmiSpacing.md)
        .padding(.vertical, OmiSpacing.sm)
      }
      .frame(maxHeight: 300)

      Divider()
        .padding(.horizontal, OmiSpacing.md)

      // Action buttons
      HStack(spacing: OmiSpacing.sm) {
        Button {
          pendingSelectedTags.removeAll()
        } label: {
          Text("Clear")
            .scaledFont(size: OmiType.body, weight: .medium)
            .foregroundColor(OmiColors.textSecondary)
            .padding(.horizontal, OmiSpacing.lg)
            .padding(.vertical, OmiSpacing.sm)
            .background(OmiColors.backgroundTertiary)
            .cornerRadius(OmiChrome.badgeRadius)
        }
        .buttonStyle(.plain)

        Button {
          viewModel.selectedTags = pendingSelectedTags
          showCategoryFilter = false
        } label: {
          Text("Apply")
            .scaledFont(size: OmiType.body, weight: .medium)
            .foregroundColor(.black)
            .padding(.horizontal, OmiSpacing.lg)
            .padding(.vertical, OmiSpacing.sm)
            .background(Color.white)
            .cornerRadius(OmiChrome.badgeRadius)
        }
        .buttonStyle(.plain)
      }
      .padding(OmiSpacing.md)
    }
    .frame(width: 280)
    .background(OmiColors.backgroundSecondary)
  }

  // MARK: - Management Menu Popover

  private var managementMenuPopover: some View {
    VStack(alignment: .leading, spacing: 0) {
      // Visibility section
      Text("Visibility")
        .scaledFont(size: OmiType.caption, weight: .medium)
        .foregroundColor(OmiColors.textTertiary)
        .padding(.horizontal, OmiSpacing.md)
        .padding(.top, OmiSpacing.md)
        .padding(.bottom, OmiSpacing.xs)

      Button {
        showManagementMenu = false
        Task { await viewModel.makeMemoriesPrivate(scope: .defaultAccess) }
      } label: {
        HStack(spacing: OmiSpacing.sm) {
          Image(systemName: "lock")
            .scaledFont(size: OmiType.body)
            .frame(width: 20)
          Text("Make Default Memories Private")
            .scaledFont(size: OmiType.body)
          Spacer()
        }
        .foregroundColor(OmiColors.textPrimary)
        .padding(.horizontal, OmiSpacing.md)
        .padding(.vertical, OmiSpacing.sm)
        .contentShape(Rectangle())
      }
      .buttonStyle(.plain)
      .disabled(
        !viewModel.areBulkServerMutationsAvailable || viewModel.memories.isEmpty || viewModel.isBulkOperationInProgress
      )
      .opacity(
        !viewModel.areBulkServerMutationsAvailable || viewModel.memories.isEmpty || viewModel.isBulkOperationInProgress
          ? 0.5 : 1
      )
      .help("Bulk memory mutations are disabled until the backend supports layer-scoped operations.")

      Button {
        showManagementMenu = false
        Task { await viewModel.makeMemoriesPublic(scope: .defaultAccess) }
      } label: {
        HStack(spacing: OmiSpacing.sm) {
          Image(systemName: "globe")
            .scaledFont(size: OmiType.body)
            .frame(width: 20)
          Text("Make Default Memories Public")
            .scaledFont(size: OmiType.body)
          Spacer()
        }
        .foregroundColor(OmiColors.textPrimary)
        .padding(.horizontal, OmiSpacing.md)
        .padding(.vertical, OmiSpacing.sm)
        .contentShape(Rectangle())
      }
      .buttonStyle(.plain)
      .disabled(
        !viewModel.areBulkServerMutationsAvailable || viewModel.memories.isEmpty || viewModel.isBulkOperationInProgress
      )
      .opacity(
        !viewModel.areBulkServerMutationsAvailable || viewModel.memories.isEmpty || viewModel.isBulkOperationInProgress
          ? 0.5 : 1
      )
      .help("Bulk memory mutations are disabled until the backend supports layer-scoped operations.")

      Divider()
        .padding(.vertical, OmiSpacing.sm)
        .padding(.horizontal, OmiSpacing.md)

      // Danger section
      Button {
        showManagementMenu = false
        viewModel.showingDeleteAllConfirmation = true
      } label: {
        HStack(spacing: OmiSpacing.sm) {
          Image(systemName: "trash")
            .scaledFont(size: OmiType.body)
            .frame(width: 20)
          Text("Delete Default Memories")
            .scaledFont(size: OmiType.body)
          Spacer()
        }
        .foregroundColor(OmiColors.error)
        .padding(.horizontal, OmiSpacing.md)
        .padding(.vertical, OmiSpacing.sm)
        .contentShape(Rectangle())
      }
      .buttonStyle(.plain)
      .disabled(
        !viewModel.areBulkServerMutationsAvailable || viewModel.memories.isEmpty || viewModel.isBulkOperationInProgress
      )
      .opacity(
        !viewModel.areBulkServerMutationsAvailable || viewModel.memories.isEmpty || viewModel.isBulkOperationInProgress
          ? 0.5 : 1
      )
      .help("Bulk memory deletion is disabled until the backend supports layer-scoped operations.")
    }
    .padding(.vertical, OmiSpacing.xxs)
    .frame(width: 200)
    .background(OmiColors.backgroundSecondary)
  }

  // MARK: - Memory List

  private var memoryList: some View {
    ScrollView {
      LazyVStack(alignment: .leading, spacing: OmiSpacing.md) {
        MemoryGraphInlineCard(viewModel: graphViewModel)

        LazyVStack(spacing: OmiSpacing.sm) {
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
        }

        // Loading more indicator
        if viewModel.isLoadingMore {
          HStack(spacing: OmiSpacing.sm) {
            ProgressView()
              .scaleEffect(0.8)
            Text("Loading more...")
              .scaledFont(size: OmiType.body)
              .foregroundColor(OmiColors.textTertiary)
          }
          .frame(maxWidth: .infinity)
          .padding(.vertical, OmiSpacing.lg)
        }

        // "Load more" button if there are more memories
        if !viewModel.filteredMemories.isEmpty && !viewModel.isLoadingMore {
          if viewModel.isInFilteredMode && viewModel.hasMoreFilteredResults {
            Button {
              viewModel.loadMoreFiltered()
            } label: {
              HStack(spacing: OmiSpacing.xs) {
                Image(systemName: "arrow.down.circle")
                Text("Load more memories")
              }
              .scaledFont(size: OmiType.body, weight: .medium)
              .foregroundColor(OmiColors.textSecondary)
              .padding(.horizontal, OmiSpacing.lg)
              .padding(.vertical, OmiSpacing.sm)
              .omiControlSurface(fill: OmiColors.backgroundTertiary, radius: 16)
            }
            .buttonStyle(.plain)
            .frame(maxWidth: .infinity)
            .padding(.vertical, OmiSpacing.sm)
          } else if !viewModel.isInFilteredMode && viewModel.hasMoreMemories {
            Button {
              Task { await viewModel.loadMore() }
            } label: {
              HStack(spacing: OmiSpacing.xs) {
                Image(systemName: "arrow.down.circle")
                Text("Load more memories")
              }
              .scaledFont(size: OmiType.body, weight: .medium)
              .foregroundColor(OmiColors.textSecondary)
              .padding(.horizontal, OmiSpacing.lg)
              .padding(.vertical, OmiSpacing.sm)
              .omiControlSurface(fill: OmiColors.backgroundTertiary, radius: 16)
            }
            .buttonStyle(.plain)
            .frame(maxWidth: .infinity)
            .padding(.vertical, OmiSpacing.sm)
          }
        }
      }
      .padding(.horizontal, OmiSpacing.xxl)
      .padding(.bottom, OmiSpacing.xxl)
    }
  }

  private func tagBadge(_ title: String, _ icon: String, _ color: Color) -> some View {
    HStack(spacing: OmiSpacing.xxs) {
      Image(systemName: icon)
        .scaledFont(size: OmiType.micro)
      Text(title)
        .scaledFont(size: OmiType.caption, weight: .medium)
    }
    .foregroundColor(OmiColors.textSecondary)
  }

  private func categoryIcon(_ category: MemoryCategory) -> String {
    category.icon
  }

  private func categoryColor(_ category: MemoryCategory) -> Color {
    OmiColors.textSecondary
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
    VStack(spacing: OmiSpacing.lg) {
      Image(systemName: "brain.head.profile")
        .scaledFont(size: 48)
        .foregroundColor(OmiColors.textTertiary)

      Text("No Memories Yet")
        .scaledFont(size: OmiType.heading, weight: .semibold)
        .foregroundColor(OmiColors.textPrimary)

      Text(
        "Your memories and tips will appear here.\nMemories are extracted from your conversations."
      )
      .scaledFont(size: OmiType.body)
      .foregroundColor(OmiColors.textTertiary)
      .multilineTextAlignment(.center)

      Button {
        viewModel.showingAddMemory = true
      } label: {
        HStack(spacing: OmiSpacing.xs) {
          Image(systemName: "plus")
          Text("Add Your First Memory")
        }
        .scaledFont(size: OmiType.body, weight: .medium)
        .foregroundColor(OmiColors.backgroundPrimary)
        .padding(.horizontal, OmiSpacing.xl)
        .padding(.vertical, OmiSpacing.sm)
        .background(OmiColors.accent)
        .cornerRadius(OmiChrome.elementRadius)
      }
      .buttonStyle(.plain)
      .padding(.top, OmiSpacing.sm)
    }
    .frame(maxWidth: .infinity, maxHeight: .infinity)
  }

  private var noResultsView: some View {
    VStack(spacing: OmiSpacing.md) {
      Image(systemName: "magnifyingglass")
        .scaledFont(size: 36)
        .foregroundColor(OmiColors.textTertiary)

      Text("No Results")
        .scaledFont(size: OmiType.heading, weight: .semibold)
        .foregroundColor(OmiColors.textPrimary)

      Text("Try a different search or filter")
        .scaledFont(size: OmiType.body)
        .foregroundColor(OmiColors.textTertiary)

      if !viewModel.selectedTags.isEmpty {
        Button {
          viewModel.selectedTags.removeAll()
        } label: {
          Text("Clear Filters")
            .scaledFont(size: OmiType.body, weight: .medium)
            .foregroundColor(OmiColors.textSecondary)
        }
        .buttonStyle(.plain)
      }
    }
    .frame(maxWidth: .infinity, maxHeight: .infinity)
  }

  private var loadingView: some View {
    VStack(spacing: OmiSpacing.md) {
      ProgressView()
        .progressViewStyle(.circular)
        .scaleEffect(1.2)

      Text("Loading memories...")
        .scaledFont(size: OmiType.body)
        .foregroundColor(OmiColors.textTertiary)
    }
    .frame(maxWidth: .infinity, maxHeight: .infinity)
  }

  private func errorView(_: String) -> some View {
    VStack(spacing: OmiSpacing.lg) {
      Image(systemName: "exclamationmark.triangle")
        .scaledFont(size: 36)
        .foregroundColor(OmiColors.error)

      Text("Failed to Load Memories")
        .scaledFont(size: OmiType.heading, weight: .semibold)
        .foregroundColor(OmiColors.textPrimary)

      Text("Check your connection and try again.")
        .scaledFont(size: OmiType.body)
        .foregroundColor(OmiColors.textTertiary)

      Button {
        Task { await viewModel.loadMemories() }
      } label: {
        HStack(spacing: OmiSpacing.xs) {
          Image(systemName: "arrow.clockwise")
          Text("Retry")
        }
        .scaledFont(size: OmiType.body, weight: .medium)
        .foregroundColor(OmiColors.backgroundPrimary)
        .padding(.horizontal, OmiSpacing.xl)
        .padding(.vertical, OmiSpacing.sm)
        .background(OmiColors.accent)
        .cornerRadius(OmiChrome.elementRadius)
      }
      .buttonStyle(.plain)
    }
    .frame(maxWidth: .infinity, maxHeight: .infinity)
  }

  // MARK: - Sheets

}

// MARK: - Memory Card View

private struct MemoryLayerBadge: View {
  let layer: MemoryLayer
  @State private var showLayerInfo = false

  var body: some View {
    Button {
      showLayerInfo.toggle()
    } label: {
      HStack(spacing: OmiSpacing.xxs) {
        Image(systemName: layer.icon)
          .scaledFont(size: OmiType.micro, weight: .medium)
        Text(layer.displayName)
          .scaledFont(size: OmiType.micro, weight: .medium)
      }
      .foregroundColor(layer == .archive ? OmiColors.textPrimary : OmiColors.textSecondary)
      .padding(.horizontal, OmiSpacing.xs)
      .padding(.vertical, OmiSpacing.hairline)
      .background(layer == .archive ? OmiColors.backgroundRaised : OmiColors.backgroundTertiary)
      .clipShape(Capsule())
    }
    .buttonStyle(.plain)
    .help(layer.layerInfoText)
    .popover(isPresented: $showLayerInfo, arrowEdge: .top) {
      VStack(alignment: .leading, spacing: OmiSpacing.xs) {
        Text(layer.displayName)
          .scaledFont(size: OmiType.caption, weight: .semibold)
          .foregroundColor(OmiColors.textPrimary)
        Text(layer.layerInfoText)
          .scaledFont(size: OmiType.caption)
          .foregroundColor(OmiColors.textSecondary)
          .fixedSize(horizontal: false, vertical: true)
      }
      .padding(OmiSpacing.md)
      .frame(maxWidth: 240)
    }
  }
}

/// Reversible alias during WS-G client rename (Wave 36).
private typealias MemoryTierBadge = MemoryLayerBadge

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
    Button(action: onTap) {
      VStack(alignment: .leading, spacing: OmiSpacing.sm) {
        HStack(alignment: .top, spacing: OmiSpacing.sm) {
          Group {
            if memory.content.hasPrefix("[Protected") || memory.content.hasPrefix("[Encrypted") {
              Text("Protected memory")
                .italic()
                .foregroundColor(OmiColors.textTertiary)
            } else {
              Text(memory.content)
                .foregroundColor(OmiColors.textPrimary)
            }
          }
          .scaledFont(size: 13.5)
          .lineLimit(2)
          .truncationMode(.tail)
          .frame(maxWidth: .infinity, alignment: .leading)

          if isNewlyCreated {
            NewBadge()
          }
        }

        HStack(spacing: OmiSpacing.sm) {
          Text(formatDate(memory.createdAt))
            .scaledFont(size: OmiType.caption)
            .foregroundColor(OmiColors.textSecondary)

          if let deviceLabel = ClientDeviceService.shared.deviceProvenanceLabel(for: memory) {
            Text(deviceLabel)
              .scaledFont(size: OmiType.caption)
              .foregroundColor(OmiColors.textTertiary)
          }

          // Badge when the server sent an authoritative layer (canonical cohort always does).
          // Only badge memories the backend actually tiered; legacy/untiered
          // records carry no real tier, so we show no badge for them.
          if memory.tierIsExplicit {
            MemoryLayerBadge(layer: memory.tier)
          }

          if let sourceName = memory.sourceName {
            Text("From \(sourceName)")
              .scaledFont(size: OmiType.micro)
              .foregroundColor(OmiColors.textTertiary)
              .lineLimit(1)
          }

          Spacer(minLength: 4)

          MemoryDetailButton(
            memory: memory,
            categoryIcon: categoryIcon,
            categoryColor: categoryColor,
            tagColorFor: tagColorFor
          )

          if isHovered {
            Image(systemName: "arrow.up.right")
              .scaledFont(size: OmiType.micro, weight: .medium)
              .foregroundColor(OmiColors.textTertiary)
          }
        }
      }
      .padding(.horizontal, OmiSpacing.lg)
      .padding(.vertical, OmiSpacing.md)
      .background(
        isHovered
          ? OmiColors.backgroundRaised
          : (isNewlyCreated ? OmiColors.userBubble.opacity(0.24) : OmiColors.backgroundSecondary)
      )
      .clipShape(RoundedRectangle(cornerRadius: OmiChrome.controlRadius, style: .continuous))
      .shadow(
        color: .black.opacity(isHovered ? 0.14 : 0.08), radius: isHovered ? 12 : 8, x: 0,
        y: isHovered ? 8 : 5)
    }
    .buttonStyle(.plain)
    .contentShape(Rectangle())
    .onHover { hovering in
      // No animation wrapper - simple state update for instant response
      isHovered = hovering
      if hovering {
        NSCursor.pointingHand.push()
      } else {
        NSCursor.pop()
      }
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
      .scaledFont(size: OmiType.micro)
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
    VStack(alignment: .leading, spacing: OmiSpacing.xs) {
      if memory.tierIsExplicit, memory.tier == .shortTerm, let expiresAt = memory.expiresAt {
        tooltipRow("Layer", memory.tier.displayName)
        tooltipRow("Expires", expiresAt.formatted(date: .abbreviated, time: .shortened))
      } else if memory.tierIsExplicit {
        tooltipRow("Layer", memory.tier.displayName)
      }

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
      tooltipRow(
        "Created",
        {
          let f = DateFormatter()
          f.dateStyle = .medium
          f.timeStyle = .short
          return f.string(from: memory.createdAt)
        }())
    }
    .padding(OmiSpacing.sm)
    .frame(maxWidth: 350, maxHeight: 400)
  }

  private func tooltipRow(_ label: String, _ value: String) -> some View {
    HStack(alignment: .top, spacing: OmiSpacing.xs) {
      Text(label)
        .scaledFont(size: OmiType.caption, weight: .medium)
        .foregroundColor(OmiColors.textTertiary)
        .frame(width: 70, alignment: .trailing)

      Text(value)
        .scaledFont(size: OmiType.caption)
        .foregroundColor(OmiColors.textPrimary)
    }
  }

  private func tooltipBlock(_ label: String, _ value: String) -> some View {
    VStack(alignment: .leading, spacing: OmiSpacing.hairline) {
      Text(label)
        .scaledFont(size: OmiType.caption, weight: .medium)
        .foregroundColor(OmiColors.textTertiary)
        .padding(.leading, 76)

      Text(value)
        .scaledFont(size: OmiType.caption)
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
      VStack(alignment: .leading, spacing: OmiSpacing.xl) {
        // Header with tags, visibility toggle, delete, and dismiss
        HStack(spacing: OmiSpacing.sm) {
          if memory.isTip {
            tagBadge("Tips", "lightbulb.fill", OmiColors.textSecondary)
            if let tipCat = memory.tipCategory {
              tagBadge(tipCat.capitalized, memory.tipCategoryIcon, tagColorFor(tipCat))
            }
          } else {
            tagBadge(
              memory.category.displayName, categoryIcon(memory.category),
              categoryColor(memory.category))
          }

          Spacer()

          // Public toggle
          HStack(spacing: OmiSpacing.xs) {
            Text("Public")
              .scaledFont(size: OmiType.body)
              .foregroundColor(OmiColors.textSecondary)
            if viewModel.isTogglingVisibility {
              ProgressView()
                .scaleEffect(0.7)
            } else {
              Toggle(
                "",
                isOn: Binding(
                  get: { memory.isPublic },
                  set: { _ in
                    Task { await viewModel.toggleVisibility(memory) }
                  }
                )
              )
              .toggleStyle(OmiToggleStyle())
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
              .scaledFont(size: OmiType.body)
              .foregroundColor(OmiColors.error)
          }
          .buttonStyle(.plain)

          DismissButton(action: dismissSheet)
        }

        // Content (click to edit)
        if isEditingContent {
          VStack(alignment: .trailing, spacing: OmiSpacing.sm) {
            TextEditor(text: $editContentText)
              .scaledFont(size: OmiType.subheading)
              .foregroundColor(OmiColors.textPrimary)
              .scrollContentBackground(.hidden)
              .padding(OmiSpacing.sm)
              .background(OmiColors.backgroundTertiary)
              .cornerRadius(OmiChrome.elementRadius)
              .frame(minHeight: 80)

            HStack(spacing: OmiSpacing.sm) {
              Button {
                isEditingContent = false
              } label: {
                Text("Cancel")
                  .scaledFont(size: OmiType.body)
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
                  .scaledFont(size: OmiType.body, weight: .medium)
                  .foregroundColor(.black)
                  .padding(.horizontal, OmiSpacing.md)
                  .padding(.vertical, OmiSpacing.xxs)
                  .background(Color.white)
                  .cornerRadius(OmiChrome.badgeRadius)
              }
              .buttonStyle(.plain)
              .disabled(editContentText.isEmpty)
            }
          }
        } else if memory.content.hasPrefix("[Protected") || memory.content.hasPrefix("[Encrypted") {
          Text("Protected memory")
            .italic()
            .scaledFont(size: OmiType.subheading)
            .foregroundColor(OmiColors.textTertiary)
            .fixedSize(horizontal: false, vertical: true)
        } else {
          Text(memory.content)
            .scaledFont(size: OmiType.subheading)
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
          VStack(alignment: .leading, spacing: OmiSpacing.sm) {
            Text("Why this tip?")
              .scaledFont(size: OmiType.body, weight: .semibold)
              .foregroundColor(OmiColors.textSecondary)

            Text(reasoning)
              .scaledFont(size: OmiType.body)
              .foregroundColor(OmiColors.textPrimary)
              .textSelection(.enabled)
          }
          .padding(OmiSpacing.md)
          .background(OmiColors.backgroundTertiary)
          .cornerRadius(OmiChrome.elementRadius)
        }

        // Context
        if memory.currentActivity != nil || memory.contextSummary != nil {
          VStack(alignment: .leading, spacing: OmiSpacing.sm) {
            Text("Context")
              .scaledFont(size: OmiType.body, weight: .semibold)
              .foregroundColor(OmiColors.textSecondary)

            if let activity = memory.currentActivity {
              HStack(spacing: OmiSpacing.xs) {
                Image(systemName: "figure.walk")
                  .scaledFont(size: OmiType.caption)
                Text(activity)
                  .scaledFont(size: OmiType.body)
                  .textSelection(.enabled)
              }
              .foregroundColor(OmiColors.textTertiary)
            }

            if let context = memory.contextSummary {
              Text(context)
                .scaledFont(size: OmiType.body)
                .foregroundColor(OmiColors.textTertiary)
                .textSelection(.enabled)
            }
          }
          .padding(OmiSpacing.md)
          .background(OmiColors.backgroundTertiary)
          .cornerRadius(OmiChrome.elementRadius)
        }

        // Metadata
        VStack(alignment: .leading, spacing: OmiSpacing.sm) {
          if let confidence = memory.confidenceString {
            HStack {
              Text("Confidence")
                .foregroundColor(OmiColors.textSecondary)
              Spacer()
              Text(confidence)
                .foregroundColor(OmiColors.textPrimary)
            }
            .scaledFont(size: OmiType.body)
          }

          if let sourceApp = memory.sourceApp {
            HStack {
              Text("Source App")
                .foregroundColor(OmiColors.textSecondary)
              Spacer()
              Text(sourceApp)
                .foregroundColor(OmiColors.textPrimary)
            }
            .scaledFont(size: OmiType.body)
          }

          if let sourceName = memory.sourceName {
            HStack {
              Text("Device")
                .foregroundColor(OmiColors.textSecondary)
              Spacer()
              HStack(spacing: OmiSpacing.xxs) {
                Image(systemName: memory.sourceIcon)
                Text(sourceName)
              }
              .foregroundColor(OmiColors.textPrimary)
            }
            .scaledFont(size: OmiType.body)
          }

          if let micName = memory.inputDeviceName, memory.source == "desktop" {
            HStack {
              Text("Microphone")
                .foregroundColor(OmiColors.textSecondary)
              Spacer()
              HStack(spacing: OmiSpacing.xxs) {
                Image(systemName: "mic")
                Text(micName)
              }
              .foregroundColor(OmiColors.textPrimary)
            }
            .scaledFont(size: OmiType.body)
          }

          HStack {
            Text("Created")
              .foregroundColor(OmiColors.textSecondary)
            Spacer()
            Text(formatDate(memory.createdAt))
              .foregroundColor(OmiColors.textPrimary)
          }
          .scaledFont(size: OmiType.body)

          if !memory.tags.isEmpty {
            HStack(alignment: .top) {
              Text("Tags")
                .foregroundColor(OmiColors.textSecondary)
                .scaledFont(size: OmiType.body)
              Spacer()
              FlowLayout(spacing: OmiSpacing.xxs) {
                ForEach(memory.tags, id: \.self) { tag in
                  Text(tag)
                    .scaledFont(size: OmiType.caption, weight: .medium)
                    .foregroundColor(tagColorFor(tag))
                }
              }
            }
          }
        }
        .padding(OmiSpacing.md)
        .background(OmiColors.backgroundTertiary)
        .cornerRadius(OmiChrome.elementRadius)

        // Action Buttons
        VStack(spacing: OmiSpacing.sm) {
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
        .padding(.top, OmiSpacing.sm)
      }
      .padding(OmiSpacing.xxl)
    }
    .frame(width: 450)
    .frame(maxHeight: 600)
    .background(OmiColors.backgroundSecondary)
  }

  private func tagBadge(_ title: String, _ icon: String, _ color: Color) -> some View {
    HStack(spacing: OmiSpacing.xxs) {
      Image(systemName: icon)
        .scaledFont(size: OmiType.micro)
      Text(title)
        .scaledFont(size: OmiType.caption, weight: .medium)
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
          .scaledFont(size: OmiType.caption)
          .foregroundColor(OmiColors.textTertiary)
      }
    }
    .scaledFont(size: OmiType.body)
    .foregroundColor(textColor)
    .padding(OmiSpacing.md)
    .background(backgroundColor)
    .cornerRadius(OmiChrome.elementRadius)
    .opacity(isPressed ? 0.7 : 1.0)
    .contentShape(Rectangle())
    .onTapGesture {
      guard !isPressed else { return }  // Prevent double-tap
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
    VStack(spacing: OmiSpacing.xl) {
      // Header with close button
      HStack {
        Text("Add Memory")
          .scaledFont(size: OmiType.heading, weight: .semibold)
          .foregroundColor(OmiColors.textPrimary)
        Spacer()
        DismissButton(action: dismissSheet)
      }

      TextEditor(text: $viewModel.newMemoryText)
        .scaledFont(size: OmiType.body)
        .foregroundColor(OmiColors.textPrimary)
        .scrollContentBackground(.hidden)
        .padding(OmiSpacing.md)
        .background(OmiColors.backgroundTertiary)
        .cornerRadius(OmiChrome.elementRadius)
        .frame(height: 150)

      HStack(spacing: OmiSpacing.md) {
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
            .scaledFont(size: OmiType.body, weight: .medium)
            .foregroundColor(viewModel.newMemoryText.isEmpty ? OmiColors.textTertiary : .black)
            .padding(.horizontal, OmiSpacing.xl)
            .padding(.vertical, OmiSpacing.sm)
            .background(
              viewModel.newMemoryText.isEmpty ? OmiColors.backgroundTertiary : Color.white
            )
            .cornerRadius(OmiChrome.elementRadius)
            .overlay(
              RoundedRectangle(cornerRadius: OmiChrome.elementRadius)
                .stroke(
                  viewModel.newMemoryText.isEmpty ? Color.clear : OmiColors.border, lineWidth: 1)
            )
        }
        .buttonStyle(.plain)
        .disabled(viewModel.newMemoryText.isEmpty)
      }
    }
    .padding(OmiSpacing.xxl)
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
    VStack(spacing: OmiSpacing.xl) {
      // Header with close button
      HStack {
        Text("Edit Memory")
          .scaledFont(size: OmiType.heading, weight: .semibold)
          .foregroundColor(OmiColors.textPrimary)
        Spacer()
        DismissButton(action: dismissSheet)
      }

      TextEditor(text: $viewModel.editText)
        .scaledFont(size: OmiType.body)
        .foregroundColor(OmiColors.textPrimary)
        .scrollContentBackground(.hidden)
        .padding(OmiSpacing.md)
        .background(OmiColors.backgroundTertiary)
        .cornerRadius(OmiChrome.elementRadius)
        .frame(height: 150)

      HStack(spacing: OmiSpacing.md) {
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
            .scaledFont(size: OmiType.body, weight: .medium)
            .foregroundColor(viewModel.editText.isEmpty ? OmiColors.textTertiary : .black)
            .padding(.horizontal, OmiSpacing.xl)
            .padding(.vertical, OmiSpacing.sm)
            .background(viewModel.editText.isEmpty ? OmiColors.backgroundTertiary : Color.white)
            .cornerRadius(OmiChrome.elementRadius)
            .overlay(
              RoundedRectangle(cornerRadius: OmiChrome.elementRadius)
                .stroke(viewModel.editText.isEmpty ? Color.clear : OmiColors.border, lineWidth: 1)
            )
        }
        .buttonStyle(.plain)
        .disabled(viewModel.editText.isEmpty)
      }
    }
    .padding(OmiSpacing.xxl)
    .frame(width: 400)
    .background(OmiColors.backgroundSecondary)
  }
}
