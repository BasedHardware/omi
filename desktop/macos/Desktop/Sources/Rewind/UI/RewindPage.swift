@preconcurrency import AppKit
import OmiTheme
import SwiftUI

/// Main Rewind page - Timeline-first view with integrated search
/// The timeline is the primary interface, with search results highlighted inline
struct RewindPage: View {
  var appState: AppState? = nil

  @StateObject private var viewModel = RewindViewModel()

  @State private var currentIndex: Int = 0
  @State private var currentImage: NSImage?
  @State private var isLoadingFrame = false
  @State private var frameLoadTask: Task<Void, Never>?
  @State private var frameLoadRequestID = UUID()
  @State private var showDatePicker = false
  @StateObject private var trackWindow = RewindTrackWindowModel()

  @State private var searchViewMode: SearchViewMode? = nil
  @State private var selectedGroupIndex: Int = 0
  @FocusState private var isSearchFocused: Bool
  @FocusState private var isPageFocused: Bool

  // Monitoring toggle state
  @State var isMonitoring = false
  @State var screenCaptureHealth: ScreenCaptureHealth = .stopped
  @State var isTogglingMonitoring = false
  @AppStorage("screenAnalysisEnabled") var screenAnalysisEnabled = true

  // Recording animation state
  @State private var isRecordingPulsing = false
  @State private var isSavingPulsing = false

  // Expanded transcript state
  @State private var isTranscriptExpanded = false

  // Finish conversation button state
  @State private var isFinishing = false
  @State private var showSavedSuccess = false
  @State private var showDiscarded = false
  @State private var showError = false

  // Speaker naming state
  @State private var selectedSpeakerSegment: SpeakerSegment? = nil

  enum SearchViewMode {
    case results  // Full-screen search results
    case timeline  // Timeline with search highlights
  }

  /// Whether we're in search mode (has query or active search)
  private var isInSearchMode: Bool {
    viewModel.activeSearchQuery != nil || !viewModel.searchQuery.isEmpty
  }

  private var finishButtonText: String {
    if isFinishing { return "Saving..." }
    if showSavedSuccess { return "Saved!" }
    if showDiscarded { return "Too Short" }
    if showError { return "Failed" }
    return "Finish Conversation"
  }

  private var finishButtonForeground: Color {
    if showSavedSuccess { return Ink.surface }
    if showDiscarded { return Ink.surface }
    if showError { return Ink.surface }
    return Ink.surface
  }

  private var finishButtonBackground: Color {
    if showSavedSuccess { return Ink.listeningGreen }
    if showDiscarded { return PageGlass.warning }
    if showError { return Ink.errorRed }
    return Ink.primary
  }

  /// Compute speaker names from the live speaker-person map
  private var speakerNames: [Int: String] {
    guard let appState = appState else { return [:] }
    var names: [Int: String] = [:]
    for (speakerId, personId) in appState.liveSpeakerPersonMap {
      if let person = appState.peopleById[personId] {
        names[speakerId] = person.name
      }
    }
    return names
  }

  var body: some View {
    ZStack {
      // Background
      Color.clear.ignoresSafeArea()

      if viewModel.isLoading && viewModel.screenshots.isEmpty && viewModel.activeSearchQuery == nil {
        loadingView
      } else if let error = viewModel.errorMessage {
        errorView(error)
      } else {
        // Main content with persistent search field
        VStack(spacing: 0) {
          if isTranscriptExpanded {
            // Expanded transcript + notes view replaces timeline
            expandedTranscriptView
          } else {
            // Recovery banner (if database was recovered from corruption)
            if viewModel.showRecoveryBanner {
              recoveryBanner
            }

            // Unified top bar - search field is always here
            unifiedTopBar

            // Content area changes based on mode
            if isInSearchMode {
              if viewModel.screenshots.isEmpty {
                noSearchResultsView
              } else if searchViewMode == .timeline {
                timelineWithSearch
              } else {
                fullScreenResultsView
              }
            } else if viewModel.screenshots.isEmpty {
              emptyState
            } else {
              // Normal timeline view (without top bar, since we have unified one)
              timelineContentBody
            }
          }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
      }
    }
    .glassContent()
    .focusable()
    .focused($isPageFocused)
    .task {
      await viewModel.loadInitialData()
    }
    .onAppear {
      isMonitoring = ProactiveAssistantsPlugin.shared.isMonitoring
      screenCaptureHealth = ProactiveAssistantsPlugin.shared.screenCaptureHealth
      isPageFocused = true
    }
    .onReceive(NotificationCenter.default.publisher(for: .assistantMonitoringStateDidChange)) { _ in
      let pluginState = ProactiveAssistantsPlugin.shared.isMonitoring
      let state = RewindCaptureState.afterMonitoringChange(
        captureEnabled: screenAnalysisEnabled,
        monitoring: pluginState
      )
      isMonitoring = state.isMonitoring
      screenAnalysisEnabled = state.captureEnabled
      screenCaptureHealth = ProactiveAssistantsPlugin.shared.screenCaptureHealth
    }
    .onReceive(NotificationCenter.default.publisher(for: .expandRewindTranscript)) { _ in
      OmiMotion.withGated(.easeInOut(duration: 0.2)) {
        isTranscriptExpanded = true
      }
    }
    .onChange(of: isSearchFocused) { _, focused in
      if !focused {
        isPageFocused = true
      }
    }
    .onChange(of: isTranscriptExpanded) { _, expanded in
      viewModel.isTranscriptExpanded = expanded
    }
    .onChange(of: viewModel.screenshots) { oldScreenshots, newScreenshots in
      // Try to preserve position on the same screenshot the user was viewing
      if !oldScreenshots.isEmpty,
        currentIndex < oldScreenshots.count,
        let currentId = oldScreenshots[currentIndex].id,
        let newIndex = newScreenshots.firstIndex(where: { $0.id == currentId })
      {
        // Same screenshot found in new array - adjust index
        currentIndex = newIndex
        // No need to reload frame - it's the same screenshot
      } else if !newScreenshots.isEmpty {
        // First load or current screenshot deleted — start at newest (last index, ASC order)
        currentIndex = newScreenshots.count - 1
        selectedGroupIndex = 0
        scheduleLoadCurrentFrame()
      }
    }
    .onChange(of: viewModel.activeSearchQuery) { oldQuery, newQuery in
      // When search becomes active, default to results view
      if oldQuery == nil && newQuery != nil {
        searchViewMode = .results
        selectedGroupIndex = 0
      }
      // When search is cleared, reset view mode
      if newQuery == nil {
        searchViewMode = nil
        selectedGroupIndex = 0
      }
      invalidatePendingFrameLoad()
      if searchViewMode != .results && !activeScreenshots.isEmpty {
        currentIndex = min(currentIndex, activeScreenshots.count - 1)
        scheduleLoadCurrentFrame()
      }
    }
    // Global keyboard handlers
    .onEscapeKey {
      // Expanded transcript → collapse
      if isTranscriptExpanded {
        isTranscriptExpanded = false
        LiveTranscriptMonitor.shared.clearSaved()
        return true
      }
      // Timeline mode → go back to results list
      if searchViewMode == .timeline {
        searchViewMode = .results
        return true
      }
      // In search mode → clear search
      if viewModel.activeSearchQuery != nil {
        viewModel.searchQuery = ""
        searchViewMode = nil
        return true
      }
      if isSearchFocused {
        isSearchFocused = false
        return true
      }
      return false
    }
    .onKeyPress(.leftArrow) {
      // Arrow keys only work in timeline mode
      // Left = older = lower index (ASC order: oldest first)
      if searchViewMode != .results {
        previousFrame()
        return .handled
      }
      return .ignored
    }
    .onKeyPress(.rightArrow) {
      // Right = newer = higher index
      if searchViewMode != .results {
        nextFrame()
        return .handled
      }
      return .ignored
    }
    .onKeyPress(.upArrow) {
      // Up/down navigate search result groups
      if searchViewMode == .results {
        if selectedGroupIndex > 0 {
          selectedGroupIndex -= 1
          return .handled
        }
      }
      return .ignored
    }
    .onKeyPress(.downArrow) {
      if searchViewMode == .results {
        let groups = viewModel.groupedSearchResults
        if selectedGroupIndex < groups.count - 1 {
          selectedGroupIndex += 1
          return .handled
        }
      }
      return .ignored
    }
    // Global scroll wheel handler - works anywhere on the page
    .onScrollWheel { delta in
      handleScrollWheel(delta: delta)
    }
  }

  // Handle scroll wheel to move playhead
  private func handleScrollWheel(delta: CGFloat) {
    log("RewindPage: Scroll wheel delta=\(delta), currentIndex=\(currentIndex), screenshots=\(activeScreenshots.count)")

    guard !activeScreenshots.isEmpty else {
      log("RewindPage: Scroll ignored - no screenshots")
      return
    }
    guard searchViewMode != .results else {
      log("RewindPage: Scroll ignored - in results view")
      return
    }

    let sensitivity: CGFloat = 0.5  // Reduced from 3.0 - was too fast
    let framesToMove = Int(delta * sensitivity)  // Positive delta (scroll right/down) = newer = higher index

    if framesToMove != 0 {
      let newIndex = max(0, min(activeScreenshots.count - 1, currentIndex + framesToMove))
      if newIndex != currentIndex {
        log("RewindPage: Scroll moving from \(currentIndex) to \(newIndex)")
        seekToIndex(newIndex)
      }
    }
  }

  // MARK: - No Search Results

  private var noSearchResultsView: some View {
    VStack(spacing: OmiSpacing.lg) {
      Spacer()

      Image(systemName: "magnifyingglass")
        .scaledFont(size: 48)
        .foregroundColor(Ink.secondary)

      if viewModel.isSearching {
        Text("Searching...")
          .scaledFont(size: OmiType.subheading, weight: .medium)
          .foregroundColor(Ink.secondary)
      } else {
        Text("No results found")
          .scaledFont(size: OmiType.subheading, weight: .medium)
          .foregroundColor(Ink.secondary)

        Text("Try a different search term")
          .scaledFont(size: OmiType.body)
          .foregroundColor(Ink.secondary)
      }

      Spacer()
    }
  }

  // MARK: - Unified Top Bar (persistent search field)

  private var unifiedTopBar: some View {
    HStack(spacing: OmiSpacing.md) {
      // Left side: Back button (search timeline mode) or Rewind logo (other modes)
      if isInSearchMode && searchViewMode == .timeline {
        Button {
          searchViewMode = .results
        } label: {
          Image(systemName: "chevron.left")
            .scaledFont(size: OmiType.caption, weight: .semibold)
            .foregroundColor(Ink.secondary)
            .frame(width: 28, height: 28)
            .background(Ink.rowFill)
            .clipShape(Circle())
        }
        .buttonStyle(.plain)
        .help("Back to results")
      } else {
        // Rewind title
        HStack(spacing: OmiSpacing.sm) {
          Text("Rewind")
            .scaledFont(size: OmiType.subheading, weight: .semibold)
            .foregroundColor(Ink.primary)

          // Global hotkey hint
          HStack(spacing: OmiSpacing.hairline) {
            Text("⌘")
            Text("⌥")
            Text("R")
          }
          .scaledFont(size: OmiType.micro, weight: .medium, design: .rounded)
          .foregroundColor(Ink.secondary)
          .padding(.horizontal, OmiSpacing.xs)
          .padding(.vertical, OmiSpacing.hairline)
          .background(Ink.rowFill)
          .cornerRadius(OmiChrome.stripRadius)
          .help("Press ⌘⌥R from anywhere to open Rewind")
        }
      }

      // Search field — always present. "When" is the timestamp pill on the frame, not a second
      // control up here.
      searchField(showResultsCount: isInSearchMode)

      // Right side controls depend on mode
      if isInSearchMode {
        // View mode toggle for search
        HStack(spacing: OmiSpacing.hairline) {
          Button {
            searchViewMode = .results
            if !viewModel.screenshots.isEmpty {
              currentIndex = 0
              scheduleLoadCurrentFrame()
            }
          } label: {
            Image(systemName: "list.bullet")
              .scaledFont(size: OmiType.caption)
              .foregroundColor(searchViewMode == .results ? Ink.surface : Ink.secondary)
              .frame(width: 28, height: 24)
              .background(searchViewMode == .results ? Ink.primary : Color.clear)
              .cornerRadius(OmiChrome.stripRadius)
          }
          .buttonStyle(.plain)
          .help("List view")

          Button {
            if searchViewMode != .timeline && !viewModel.screenshots.isEmpty {
              currentIndex = 0
            }
            searchViewMode = .timeline
            scheduleLoadCurrentFrame()
          } label: {
            Image(systemName: "timeline.selection")
              .scaledFont(size: OmiType.caption)
              .foregroundColor(searchViewMode == .timeline ? Ink.surface : Ink.secondary)
              .frame(width: 28, height: 24)
              .background(searchViewMode == .timeline ? Ink.primary : Color.clear)
              .cornerRadius(OmiChrome.stripRadius)
          }
          .buttonStyle(.plain)
          .help("Timeline view")
        }
        .padding(OmiSpacing.hairline)
        .background(Ink.rowFill)
        .cornerRadius(OmiChrome.badgeRadius)
      }

      Spacer()

      // Settings
      Button {
        NotificationCenter.default.post(
          name: .navigateToRewindSettings,
          object: nil
        )
      } label: {
        Image(systemName: "gearshape")
          .scaledFont(size: OmiType.caption)
          .foregroundColor(Ink.secondary)
      }
      .buttonStyle(.plain)
      .help("Rewind Settings")

      // Rewind on/off toggle (screen capture only)
      if let badgeText = screenCaptureHealth.rewindBadgeText {
        Text(badgeText)
          .scaledFont(size: OmiType.micro, weight: .medium)
          .foregroundColor(PageGlass.warning)
          .padding(.horizontal, OmiSpacing.xs)
          .padding(.vertical, OmiSpacing.hairline)
          .background(PageGlass.warning.opacity(0.15))
          .cornerRadius(OmiChrome.stripRadius)
          .help(screenCaptureHealth.statusText)
      }
      rewindToggle
    }
    .padding(.horizontal, OmiSpacing.xxl)
    .padding(.vertical, OmiSpacing.md)
    .overlay(alignment: .bottom) { GlassSeparator() }
  }

  // MARK: - Timeline Content Body (without top bar)

  private var timelineContentBody: some View {
    VStack(spacing: 0) {
      // Main frame display - fills available space without Spacers to avoid SwiftUI layout loops
      // (GeometryReader + Spacer inside VStack causes recursive StackLayout sizing)
      frameDisplay
        .frame(maxHeight: .infinity)

      // Timeline and controls at bottom
      bottomControls
    }
  }

  // MARK: - Full Screen Results View (the search surface's second panel)

  /// What the search found, as its own sheet of glass under the query bar.
  ///
  /// The panel owns its own grid, filter block, height clamp and scrolling
  /// (`RewindSearchResultsPanel`); the page keeps only what is genuinely the page's — which group is
  /// selected, and what opening one does.
  private var fullScreenResultsView: some View {
    RewindSearchResultsPanel(
      groups: viewModel.groupedSearchResults,
      query: viewModel.activeSearchQuery ?? "",
      totalScreenshots: viewModel.totalScreenshotCount,
      selectedIndex: $selectedGroupIndex
    ) { groupIndex in
      // Set the screenshots to this group's screenshots for timeline navigation
      selectedGroupIndex = groupIndex
      currentIndex = 0
      searchViewMode = .timeline
      scheduleLoadCurrentFrame()
    }
    .panel
    // The gap that makes the bar above and this panel read as two objects rather than one slab.
    .padding(.top, RewindSearchLayout.panelGap)
    .padding(.bottom, RewindSearchLayout.shadowMargin)
    .frame(maxWidth: .infinity, alignment: .top)
    .onChange(of: selectedGroupIndex) { _, _ in
      invalidatePendingFrameLoad()
    }
  }

  /// Screenshots for the currently selected group (used in timeline view)
  private var currentGroupScreenshots: [Screenshot] {
    let groups = viewModel.groupedSearchResults
    guard selectedGroupIndex < groups.count else { return viewModel.screenshots }
    return groups[selectedGroupIndex].screenshots
  }

  /// The active screenshot list - either group screenshots (when viewing a group) or all screenshots
  private var activeScreenshots: [Screenshot] {
    if searchViewMode == .timeline && viewModel.activeSearchQuery != nil {
      return currentGroupScreenshots
    }
    return viewModel.screenshots
  }

  private var activeFrameSourceToken: String {
    let screenshots = activeScreenshots
    let currentScreenshotID: String
    if currentIndex < screenshots.count {
      let screenshot = screenshots[currentIndex]
      currentScreenshotID =
        screenshot.id.map(String.init)
        ?? "\(screenshot.timestamp.timeIntervalSince1970):\(screenshot.videoChunkPath ?? screenshot.imagePath ?? "")"
    } else {
      currentScreenshotID = "none"
    }
    return [
      searchViewMode.map(String.init(describing:)) ?? "timeline",
      viewModel.activeSearchQuery ?? "",
      String(selectedGroupIndex),
      String(screenshots.count),
      currentScreenshotID,
    ].joined(separator: "|")
  }

  // MARK: - Timeline with Search

  private var timelineWithSearch: some View {
    VStack(spacing: 0) {
      // Frame display - fills available space (no Spacers to avoid layout loop)
      frameDisplay
        .frame(maxHeight: .infinity)

      // Timeline and controls
      bottomControls
    }
  }

  // MARK: - Unified Search Field

  /// The place you type. The bar's own furniture — the query chip, the count, the keyboard hint —
  /// belongs to `RewindSearchBar`; the page supplies only the state and what clearing does.
  private func searchField(showResultsCount: Bool = false) -> some View {
    RewindSearchBar(
      query: $viewModel.searchQuery,
      isSearching: viewModel.isSearching,
      countLabel: showResultsCount && viewModel.activeSearchQuery != nil
        ? RewindSearchResultsPanel.countLabel(
          groups: viewModel.groupedSearchResults.count,
          screenshots: viewModel.totalScreenshotCount)
        : nil,
      focus: $isSearchFocused,
      onClear: {
        viewModel.searchQuery = ""
        searchViewMode = nil
      }
    )
    .frame(maxWidth: RewindSearchLayout.panelWidth * 0.6)
  }

  // MARK: - Day Picker

  /// The popover behind the timestamp pill. The pill itself lives on the frame stage, per the
  /// playback chrome — a page with a date control in the header *and* a timestamp on the picture is
  /// two answers to "when is this".
  private var dayPicker: some View {
    DatePicker(
      "",
      selection: Binding(
        get: { viewModel.selectedDate },
        set: { newDate in
          // Only reload if the selected day actually changed
          guard !Calendar.current.isDate(newDate, inSameDayAs: viewModel.selectedDate) else { return }
          Task { await viewModel.filterByDate(newDate) }
        }
      ),
      displayedComponents: [.date]
    )
    .datePickerStyle(.graphical)
    .labelsHidden()
    .padding(14)
  }

  // MARK: - Frame Display

  private var frameDisplay: some View {
    GeometryReader { geometry in
      if isLoadingFrame && currentImage == nil {
        ProgressView()
          .progressViewStyle(.circular)
          .scaleEffect(1.2)
          .tint(Ink.surface)
          .frame(width: geometry.size.width, height: geometry.size.height)
      } else if let image = currentImage, image.size.height > 0, image.size.width > 0, geometry.size.height > 0,
        geometry.size.width > 0
      {
        // Calculate size to fill container while maintaining aspect ratio
        let imageAspect = image.size.width / image.size.height
        let containerAspect = geometry.size.width / geometry.size.height

        let displaySize: CGSize = {
          if imageAspect > containerAspect {
            // Wide image - fill width
            let width = geometry.size.width
            let height = width / imageAspect
            return CGSize(width: max(1, width), height: max(1, height))
          } else {
            // Tall image - fill height
            let height = geometry.size.height
            let width = height * imageAspect
            return CGSize(width: max(1, width), height: max(1, height))
          }
        }()

        ZStack {
          Image(nsImage: image)
            .resizable()
            .frame(width: displaySize.width, height: displaySize.height)
            // Search highlight overlays with explicit frame
            .overlay {
              if let query = viewModel.activeSearchQuery, currentIndex < activeScreenshots.count {
                SearchHighlightOverlay(
                  screenshot: activeScreenshots[currentIndex],
                  query: query,
                  imageSize: image.size,
                  containerSize: displaySize)
              }
            }
            .clipShape(frameShape)
            // A border keyed to the app the frame belongs to, so the picture and its segment on the
            // track are visibly the same stretch of the day.
            .overlay(frameShape.strokeBorder(frameBorderColor, lineWidth: 2))
            .shadow(color: .black.opacity(0.08), radius: 8)
        }
        .frame(width: geometry.size.width, height: geometry.size.height)
      } else {
        // Log why we're showing "No frame" for debugging
        let _ = {
          if currentImage == nil {
            // Normal case - no image loaded yet
          } else if let img = currentImage {
            logError("RewindPage: Invalid frame dimensions - image=\(img.size) geometry=\(geometry.size)")
          }
        }()
        VStack(spacing: OmiSpacing.xs) {
          Image(systemName: "photo")
            .scaledFont(size: 24)
            .foregroundColor(Ink.secondary)
          Text("No frame")
            .scaledFont(size: OmiType.caption)
            .foregroundColor(Ink.secondary)
        }
        .frame(width: geometry.size.width, height: geometry.size.height)
      }
    }
    .padding(.horizontal, 18)
    .padding(.vertical, 12)
    .overlay {
      RewindStageChrome(
        screenshots: activeScreenshots,
        currentIndex: currentIndex,
        window: trackWindow,
        onSelect: { seekToIndex($0) },
        showsDatePicker: $showDatePicker,
        datePicker: AnyView(dayPicker))
    }
  }

  private var frameShape: RoundedRectangle {
    RoundedRectangle(cornerRadius: 10, style: .continuous)
  }

  /// Nil is an honest outcome: with no frame resolved the border is a neutral hairline rather than an
  /// invented colour.
  private var frameBorderColor: Color {
    guard activeScreenshots.indices.contains(currentIndex) else { return Ink.hairline }
    return RewindPalette.color(forApp: activeScreenshots[currentIndex].appName)
  }

  // MARK: - Bottom Controls

  private var bottomControls: some View {
    VStack(spacing: 0) {
      RewindTrackBar(
        screenshots: activeScreenshots,
        currentIndex: currentIndex,
        searchResultIndices: viewModel.activeSearchQuery != nil && searchViewMode != .timeline
          ? Set(searchResultIndices) : nil,
        window: trackWindow,
        onSelect: { seekToIndex($0) })
      RewindTrackFooter(
        screenshots: activeScreenshots,
        currentIndex: currentIndex,
        showsMatchLegend: viewModel.activeSearchQuery != nil && !searchResultIndices.isEmpty)
    }
  }

  // MARK: - Search Result Indices

  private var searchResultIndices: [Int] {
    guard viewModel.activeSearchQuery != nil else { return [] }
    // All current screenshots are search results when searching
    return Array(0..<min(activeScreenshots.count, 100))
  }

  // MARK: - Playback

  private func scheduleLoadCurrentFrame() {
    frameLoadTask?.cancel()
    frameLoadRequestID = UUID()
    let requestID = frameLoadRequestID
    let requestedIndex = currentIndex
    let sourceToken = activeFrameSourceToken
    frameLoadTask = Task {
      await loadCurrentFrame(at: requestedIndex, requestID: requestID, sourceToken: sourceToken)
    }
  }

  private func invalidatePendingFrameLoad() {
    frameLoadTask?.cancel()
    frameLoadTask = nil
    frameLoadRequestID = UUID()
    isLoadingFrame = false
  }

  private func isCurrentFrameLoad(index: Int, requestID: UUID, sourceToken: String) -> Bool {
    !Task.isCancelled
      && frameLoadRequestID == requestID
      && currentIndex == index
      && activeFrameSourceToken == sourceToken
  }

  private func loadCurrentFrame(at requestedIndex: Int, requestID: UUID, sourceToken: String) async {
    let screenshots = activeScreenshots
    guard requestedIndex < screenshots.count else { return }

    isLoadingFrame = true

    // Try to load the requested frame. Scrubbing can launch several loads;
    // only the newest request is allowed to update visible state.
    if let image = await tryLoadFrame(at: requestedIndex) {
      guard isCurrentFrameLoad(index: requestedIndex, requestID: requestID, sourceToken: sourceToken) else { return }
      currentImage = image
      viewModel.selectScreenshot(screenshots[requestedIndex])
      isLoadingFrame = false
      return
    }

    // Frame failed to load (likely in an unfinalized video chunk).
    // Do NOT move currentIndex — keep the user's position and show the last valid image.
    guard isCurrentFrameLoad(index: requestedIndex, requestID: requestID, sourceToken: sourceToken) else { return }
    isLoadingFrame = false
  }

  /// Try to load a frame at a specific index, returns nil if failed
  private func tryLoadFrame(at index: Int) async -> NSImage? {
    let screenshots = activeScreenshots
    guard index >= 0 && index < screenshots.count else { return nil }
    let screenshot = screenshots[index]

    do {
      let image = try await RewindStorage.shared.loadScreenshotImage(for: screenshot)
      // Validate image dimensions
      if image.size.width <= 0 || image.size.height <= 0 {
        logError(
          "RewindPage: Loaded invalid image at index \(index) - size=\(image.size), videoChunk=\(screenshot.videoChunkPath ?? "nil"), frameOffset=\(screenshot.frameOffset ?? -1)"
        )
        return nil
      }
      return image
    } catch let error as RewindError {
      // Handle corrupted video chunk - but don't delete the active chunk being written
      if case .corruptedVideoChunk(let chunkPath) = error {
        let activeChunk = await VideoChunkEncoder.shared.currentChunkPath
        if chunkPath == activeChunk {
          // This chunk is still being recorded — not corrupted, just not finalized yet
          log("RewindPage: Frame at index \(index) is in active chunk \(chunkPath), not yet available")
        } else {
          // Truly corrupted (old chunk) - clean it up
          log("RewindPage: Detected corrupted chunk at index \(index): \(chunkPath), cleaning up...")
          Task {
            do {
              let deleted = try await RewindStorage.shared.cleanupCorruptedChunk(chunkPath)
              log("RewindPage: Cleaned up corrupted chunk, removed \(deleted) entries")
              await viewModel.refresh()
            } catch {
              logError("RewindPage: Failed to cleanup corrupted chunk: \(error.localizedDescription)")
            }
          }
        }
        return nil
      }
      logError(
        "RewindPage: Failed to load frame at index \(index): \(error.localizedDescription), videoChunk=\(screenshot.videoChunkPath ?? "nil"), frameOffset=\(screenshot.frameOffset ?? -1)"
      )
      return nil
    } catch {
      logError(
        "RewindPage: Failed to load frame at index \(index): \(error.localizedDescription), videoChunk=\(screenshot.videoChunkPath ?? "nil"), frameOffset=\(screenshot.frameOffset ?? -1)"
      )
      return nil
    }
  }

  private func seekToIndex(_ index: Int) {
    let screenshots = activeScreenshots
    let newIndex = max(0, min(index, screenshots.count - 1))
    guard newIndex != currentIndex else { return }

    currentIndex = newIndex
    scheduleLoadCurrentFrame()
  }

  private func nextFrame() {
    seekToIndex(currentIndex + 1)  // Screenshots are oldest first — right/next = newer = higher index
  }

  private func previousFrame() {
    seekToIndex(currentIndex - 1)
  }

  // MARK: - Empty States

  private var emptyState: some View {
    let isScreenCaptureKitBroken = appState?.isScreenCaptureKitBroken == true
    let hasNoPermission = appState?.hasScreenRecordingPermission == false

    return VStack(spacing: OmiSpacing.lg) {
      Spacer()

      if isScreenCaptureKitBroken {
        ZStack {
          Circle()
            .fill(Ink.errorRed.opacity(0.1))
            .frame(width: 80, height: 80)

          Image(systemName: "rectangle.on.rectangle.slash")
            .scaledFont(size: 36)
            .foregroundColor(Ink.errorRed)
        }

        Text("Screen Recording Needs Reset")
          .scaledFont(size: OmiType.heading, weight: .semibold)
          .foregroundColor(Ink.primary)

        Text(
          "macOS granted permission but ScreenCaptureKit is stuck.\nResetting fixes this — the app will restart automatically."
        )
        .scaledFont(size: OmiType.body)
        .foregroundColor(Ink.secondary)
        .multilineTextAlignment(.center)

        Button {
          AnalyticsManager.shared.screenCaptureResetClicked(source: "rewind_empty_state")
          // Re-enable screen analysis so it auto-starts after the restart
          screenAnalysisEnabled = true
          AssistantSettings.shared.screenAnalysisEnabled = true
          ScreenCaptureService.resetScreenCapturePermissionAndRestart()
        } label: {
          Text("Reset & Restart")
            .scaledFont(size: OmiType.body, weight: .semibold)
            .foregroundColor(Ink.surface)
            .padding(.horizontal, OmiSpacing.xl)
            .padding(.vertical, OmiSpacing.sm)
            .background(Ink.errorRed.opacity(0.8))
            .cornerRadius(OmiChrome.elementRadius)
        }
        .buttonStyle(.plain)
        .padding(.top, OmiSpacing.xxs)
      } else if hasNoPermission {
        ZStack {
          Circle()
            .fill(PageGlass.warning.opacity(0.1))
            .frame(width: 80, height: 80)

          Image(systemName: "lock.rectangle")
            .scaledFont(size: 36)
            .foregroundColor(PageGlass.warning)
        }

        Text("Screen Recording Permission Required")
          .scaledFont(size: OmiType.heading, weight: .semibold)
          .foregroundColor(Ink.primary)

        Text("Rewind needs Screen Recording permission to capture your screen.")
          .scaledFont(size: OmiType.body)
          .foregroundColor(Ink.secondary)
          .multilineTextAlignment(.center)

        Button {
          // Re-enable screen analysis so it auto-starts after permission is granted and app restarts
          screenAnalysisEnabled = true
          AssistantSettings.shared.screenAnalysisEnabled = true
          ScreenCaptureService.requestScreenRecordingAccessAndOpenSettings()
        } label: {
          Text("Grant Permission")
            .scaledFont(size: OmiType.body, weight: .semibold)
            .foregroundColor(Ink.surface)
            .padding(.horizontal, OmiSpacing.xl)
            .padding(.vertical, OmiSpacing.sm)
            .background(PageGlass.warning.opacity(0.8))
            .cornerRadius(OmiChrome.elementRadius)
        }
        .buttonStyle(.plain)
        .padding(.top, OmiSpacing.xxs)
      } else {
        ZStack {
          Circle()
            .fill(Ink.rowFill)
            .frame(width: 80, height: 80)

          Image(systemName: "clock.arrow.circlepath")
            .scaledFont(size: 36)
            .foregroundColor(Ink.secondary)
        }

        Text("No Screenshots Yet")
          .scaledFont(size: OmiType.heading, weight: .semibold)
          .foregroundColor(Ink.primary)

        Text("Screenshots will appear here as you use your Mac.\nRewind captures your screen every second.")
          .scaledFont(size: OmiType.body)
          .foregroundColor(Ink.secondary)
          .multilineTextAlignment(.center)

        HStack(spacing: OmiSpacing.sm) {
          Image(systemName: "lightbulb.fill")
            .foregroundColor(PageGlass.warning)
          Text("Tip: Use search to find anything you've seen on screen")
            .scaledFont(size: OmiType.caption)
            .foregroundColor(Ink.secondary)
        }
        .padding(.horizontal, OmiSpacing.lg)
        .padding(.vertical, OmiSpacing.sm)
        .background(Ink.rowFill)
        .cornerRadius(OmiChrome.elementRadius)
        .padding(.top, OmiSpacing.sm)
      }

      Spacer()
    }
  }

  private var recoveryBanner: some View {
    HStack(spacing: OmiSpacing.md) {
      Image(systemName: "exclamationmark.triangle.fill")
        .foregroundColor(PageGlass.warning)
        .scaledFont(size: OmiType.subheading)

      VStack(alignment: .leading, spacing: OmiSpacing.hairline) {
        Text("Database Recovered")
          .scaledFont(size: OmiType.body, weight: .semibold)
          .foregroundColor(Ink.primary)

        if viewModel.recoveredRecordCount > 0 {
          Text("\(viewModel.recoveredRecordCount) screenshots recovered from corrupted database")
            .scaledFont(size: OmiType.caption)
            .foregroundColor(Ink.secondary)
        } else {
          Text("Database was corrupted and has been reset. Your video files are intact.")
            .scaledFont(size: OmiType.caption)
            .foregroundColor(Ink.secondary)
        }
      }

      Spacer()

      if viewModel.recoveredRecordCount == 0 {
        Button {
          Task { await rebuildDatabase() }
        } label: {
          Text("Rebuild Index")
            .scaledFont(size: OmiType.caption, weight: .medium)
            .foregroundColor(Ink.primary)
            .padding(.horizontal, OmiSpacing.sm)
            .padding(.vertical, OmiSpacing.xxs)
            .background(Ink.primary)
            .cornerRadius(OmiChrome.stripRadius)
        }
        .buttonStyle(.plain)
        .disabled(viewModel.isRebuilding)
      }

      Button {
        OmiMotion.withGated(.easeOut(duration: 0.2)) {
          viewModel.dismissRecoveryBanner()
        }
      } label: {
        Image(systemName: "xmark")
          .scaledFont(size: OmiType.caption, weight: .medium)
          .foregroundColor(Ink.secondary)
      }
      .buttonStyle(.plain)
    }
    .padding(.horizontal, OmiSpacing.lg)
    .padding(.vertical, OmiSpacing.sm)
    .background(PageGlass.warning.opacity(0.15))
    .overlay(
      Rectangle()
        .fill(PageGlass.warning)
        .frame(height: 2),
      alignment: .top
    )
  }

  private func rebuildDatabase() async {
    viewModel.isRebuilding = true
    viewModel.rebuildProgress = 0

    do {
      let vm = viewModel
      try await RewindIndexer.shared.rebuildFromVideoFiles { @Sendable progress in
        Task { @MainActor in
          vm.rebuildProgress = progress
        }
      }
      await viewModel.loadInitialData()
      viewModel.dismissRecoveryBanner()
    } catch {
      logError("RewindPage: Database rebuild failed: \(error)")
    }

    viewModel.isRebuilding = false
  }

  private var loadingView: some View {
    VStack(spacing: OmiSpacing.md) {
      ProgressView()
        .progressViewStyle(.circular)
        .scaleEffect(1.2)
        .tint(Ink.surface)

      Text("Loading screenshots...")
        .scaledFont(size: OmiType.body)
        .foregroundColor(Ink.secondary)
    }
  }

  private func errorView(_: String) -> some View {
    VStack(spacing: OmiSpacing.lg) {
      ZStack {
        Circle()
          .fill(Ink.errorRed.opacity(0.1))
          .frame(width: 80, height: 80)

        Image(systemName: "exclamationmark.triangle")
          .scaledFont(size: 36)
          .foregroundColor(Ink.errorRed)
      }

      Text("Failed to Load Screenshots")
        .scaledFont(size: OmiType.heading, weight: .semibold)
        .foregroundColor(Ink.primary)

      Text("Try again. If this continues, restart Omi.")
        .scaledFont(size: OmiType.body)
        .foregroundColor(Ink.secondary)

      Button {
        Task { await viewModel.loadInitialData() }
      } label: {
        HStack(spacing: OmiSpacing.xs) {
          Image(systemName: "arrow.clockwise")
          Text("Retry")
        }
        .scaledFont(size: OmiType.body, weight: .medium)
        .foregroundColor(Ink.primary)
        .padding(.horizontal, OmiSpacing.xl)
        .padding(.vertical, OmiSpacing.sm)
        .background(Ink.primary)
        .cornerRadius(OmiChrome.elementRadius)
      }
      .buttonStyle(.plain)
    }
  }

  // MARK: - Expanded Transcript View

  @AppStorage("recordingNotesPanelRatio") private var panelRatio: Double = 0.65
  private let minPanelWidth: CGFloat = 200

  private var expandedTranscriptView: some View {
    VStack(spacing: 0) {
      // Show a back bar only when the recording bar is not visible
      if appState?.isTranscribing != true && appState?.isSavingConversation != true {
        HStack(spacing: OmiSpacing.sm) {
          Button {
            OmiMotion.withGated(.easeInOut(duration: 0.2)) {
              isTranscriptExpanded = false
              LiveTranscriptMonitor.shared.clearSaved()
            }
          } label: {
            HStack(spacing: OmiSpacing.xxs) {
              Image(systemName: "chevron.up")
                .scaledFont(size: OmiType.caption, weight: .semibold)
              Text("Back to Rewind")
                .scaledFont(size: OmiType.body, weight: .medium)
            }
            .foregroundColor(Ink.secondary)
            .padding(.horizontal, OmiSpacing.sm)
            .padding(.vertical, OmiSpacing.xs)
            .background(Ink.rowFill)
            .cornerRadius(OmiChrome.badgeRadius)
          }
          .buttonStyle(.plain)

          Spacer()
        }
        .padding(.horizontal, OmiSpacing.lg)
        .padding(.vertical, OmiSpacing.sm)
        .background(Ink.rowFillHover.opacity(0.8))
      }

      // Split panel: transcript (left) + notes (right)
      GeometryReader { geometry in
        let totalWidth = geometry.size.width
        let transcriptWidth = max(minPanelWidth, totalWidth * panelRatio)
        let notesWidth = max(minPanelWidth, totalWidth - transcriptWidth - 1)

        HStack(spacing: 0) {
          // Left: Live transcript
          VStack(spacing: 0) {
            LiveTranscriptPanel(
              speakerNames: speakerNames,
              onSpeakerTapped: { segment in
                selectedSpeakerSegment = segment
              }
            )
          }
          .frame(width: transcriptWidth)
          .background(Color.clear)

          // Divider
          Rectangle()
            .fill(Ink.separator)
            .frame(width: 1)

          // Right: Notes
          LiveNotesView()
            .frame(width: notesWidth)
        }
      }
    }
    .background(Color.clear)
    .task {
      await appState?.fetchPeople()
    }
    .dismissableSheet(item: $selectedSpeakerSegment) { segment in
      if let appState = appState {
        LiveNameSpeakerSheet(
          speakerId: segment.speaker,
          sampleText: segment.text,
          people: appState.people,
          currentPersonId: appState.liveSpeakerPersonMap[segment.speaker],
          onSave: { personId in
            appState.liveSpeakerPersonMap[segment.speaker] = personId
            selectedSpeakerSegment = nil
          },
          onCreatePerson: { name in
            return await appState.createPerson(name: name)
          },
          onDismiss: {
            selectedSpeakerSegment = nil
          }
        )
      }
    }
  }

  // MARK: - Recording Bar

  private func rewindRecordingBar(appState: AppState) -> some View {
    HStack(spacing: OmiSpacing.md) {
      // Content depends on state
      if appState.isTranscribing {
        // Transcript text + chevron (clickable to expand/collapse)
        Button {
          OmiMotion.withGated(.easeInOut(duration: 0.2)) {
            isTranscriptExpanded.toggle()
            if !isTranscriptExpanded {
              LiveTranscriptMonitor.shared.clearSaved()
            }
          }
        } label: {
          HStack(spacing: OmiSpacing.xs) {
            RecordingBarTranscriptText()
            Image(systemName: isTranscriptExpanded ? "chevron.up" : "chevron.down")
              .scaledFont(size: OmiType.micro, weight: .semibold)
              .foregroundColor(Ink.secondary)
          }
          .padding(.horizontal, OmiSpacing.sm)
          .padding(.vertical, OmiSpacing.xxs)
          .background(
            RoundedRectangle(cornerRadius: OmiChrome.badgeRadius)
              .fill(Ink.rowFillHover.opacity(0.5))
          )
        }
        .buttonStyle(.plain)

        // Audio level waveforms (self-observing, won't re-render parent)
        RecordingBarAudioLevels()

        // Duration (self-observing, won't re-render parent)
        RecordingBarDuration()
      } else if appState.isSavingConversation {
        // Saving indicator
        ZStack {
          Circle()
            .fill(Ink.primary.opacity(0.3))
            .frame(width: 24, height: 24)
            .scaleEffect(isSavingPulsing ? 1.5 : 1.0)
            .opacity(isSavingPulsing ? 0.0 : 0.6)

          Image(systemName: "arrow.up.circle.fill")
            .scaledFont(size: OmiType.subheading)
            .foregroundColor(Ink.primary)
            .scaleEffect(isSavingPulsing ? 1.1 : 1.0)
        }
        .omiAnimation(
          .easeInOut(duration: 0.8)
            .repeatForever(autoreverses: true),
          value: isSavingPulsing
        )
        .onAppear { isSavingPulsing = true }
        .onDisappear { isSavingPulsing = false }

        Text("Saving conversation...")
          .scaledFont(size: OmiType.body, weight: .medium)
          .foregroundColor(Ink.primary)

        ProgressView()
          .scaleEffect(0.7)
      }

      Spacer()

      // Right: Finish Conversation button (when recording)
      if appState.isTranscribing {
        Button(action: {
          handleFinish(appState: appState)
        }) {
          HStack(spacing: OmiSpacing.xs) {
            if isFinishing {
              ProgressView()
                .scaleEffect(0.5)
                .frame(width: 12, height: 12)
            } else if showSavedSuccess {
              Image(systemName: "checkmark")
                .scaledFont(size: OmiType.caption, weight: .bold)
            } else if showDiscarded {
              Image(systemName: "xmark")
                .scaledFont(size: OmiType.caption, weight: .bold)
            } else if showError {
              Image(systemName: "exclamationmark.triangle.fill")
                .scaledFont(size: OmiType.caption)
            }
            Text(finishButtonText)
              .scaledFont(size: OmiType.body, weight: .medium)
          }
          .foregroundColor(finishButtonForeground)
          .padding(.horizontal, OmiSpacing.md)
          .padding(.vertical, OmiSpacing.xs)
          .background(Capsule().fill(finishButtonBackground))
          .overlay(Capsule().stroke(Ink.separator, lineWidth: 1))
        }
        .buttonStyle(.plain)
        .disabled(isFinishing || showSavedSuccess || showDiscarded || showError)
        .help("Saves current conversation and starts a new one")
      }

    }
    .padding(.horizontal, OmiSpacing.lg)
    .padding(.vertical, OmiSpacing.sm)
    .background(Ink.rowFillHover.opacity(0.8))
  }

  // MARK: - Audio Toggle

  private func audioToggle(appState: AppState) -> some View {
    ZStack {
      Capsule()
        .fill(appState.isTranscribing ? Ink.listeningGreen : Ink.errorRed)
        .frame(width: 36, height: 20)

      Circle()
        .fill(Ink.surface)
        .frame(width: 16, height: 16)
        .shadow(color: .black.opacity(0.08), radius: 1, x: 0, y: 1)
        .offset(x: appState.isTranscribing ? 8 : -8)
        .omiAnimation(.easeInOut(duration: 0.15), value: appState.isTranscribing)
    }
    .onTapGesture {
      if appState.isTranscribing {
        appState.stopTranscription()
      } else {
        appState.startTranscription()
      }
    }
    .help(appState.isTranscribing ? "Audio is on - click to stop" : "Audio is off - click to start")
  }

  // MARK: - Finish Conversation

  private func handleFinish(appState: AppState) {
    guard !isFinishing else { return }
    isFinishing = true
    Task {
      let result = await appState.finishConversation()
      isFinishing = false
      switch result {
      case .saved:
        OmiMotion.withGated(.easeInOut(duration: 0.3)) {
          showSavedSuccess = true
        }
        try? await Task.sleep(for: .seconds(2.5))
        OmiMotion.withGated(.easeInOut(duration: 0.3)) {
          showSavedSuccess = false
        }
      case .discarded:
        OmiMotion.withGated(.easeInOut(duration: 0.3)) {
          showDiscarded = true
        }
        try? await Task.sleep(for: .seconds(2.5))
        OmiMotion.withGated(.easeInOut(duration: 0.3)) {
          showDiscarded = false
        }
      case .error:
        OmiMotion.withGated(.easeInOut(duration: 0.3)) {
          showError = true
        }
        try? await Task.sleep(for: .seconds(2.5))
        OmiMotion.withGated(.easeInOut(duration: 0.3)) {
          showError = false
        }
      }
    }
  }
}

// MARK: - Search Result List Item (Google-style)

struct SearchResultListItem: View {
  let screenshot: Screenshot
  let index: Int
  let totalCount: Int
  let searchQuery: String
  let isSelected: Bool
  let onTap: () -> Void

  @State private var isHovered = false
  @State private var thumbnail: NSImage?

  var body: some View {
    Button(action: onTap) {
      HStack(alignment: .top, spacing: OmiSpacing.lg) {
        // Left side: Text content
        VStack(alignment: .leading, spacing: OmiSpacing.xs) {
          // App name and window title (like URL in Google)
          HStack(spacing: OmiSpacing.xs) {
            AppIconView(appName: screenshot.appName, size: 16)
            Text(screenshot.appName)
              .scaledFont(size: OmiType.caption, weight: .medium)
              .foregroundColor(Ink.primary)
            if let windowTitle = screenshot.windowTitle, !windowTitle.isEmpty {
              Text("›")
                .foregroundColor(Ink.secondary)
              Text(windowTitle)
                .scaledFont(size: OmiType.caption)
                .foregroundColor(Ink.secondary)
                .lineLimit(1)
            }
          }

          // Timestamp (like page title in Google)
          Text(screenshot.formattedDate)
            .scaledFont(size: OmiType.body, weight: .medium)
            .foregroundColor(Ink.primary)

          // Context snippet with highlighted search term
          if let snippet = screenshot.contextSnippet(for: searchQuery) {
            highlightedSnippet(snippet)
          }

          // Result number
          Text("Result \(index + 1) of \(totalCount)")
            .scaledFont(size: OmiType.micro)
            .foregroundColor(Ink.secondary)
            .padding(.top, OmiSpacing.hairline)
        }

        Spacer()

        // Right side: Small thumbnail
        Group {
          if let thumb = thumbnail {
            Image(nsImage: thumb)
              .resizable()
              .aspectRatio(contentMode: .fill)
              .frame(width: 120, height: 80)
              .cornerRadius(OmiChrome.badgeRadius)
              .clipped()
          } else {
            Rectangle()
              .fill(Ink.rowFill)
              .frame(width: 120, height: 80)
              .cornerRadius(OmiChrome.badgeRadius)
              .overlay(
                ProgressView()
                  .progressViewStyle(.circular)
                  .scaleEffect(0.6)
                  .tint(Ink.secondary)
              )
          }
        }
      }
      .padding(.horizontal, OmiSpacing.lg)
      .padding(.vertical, OmiSpacing.md)
      .background(
        RoundedRectangle(cornerRadius: OmiChrome.elementRadius)
          .fill(isSelected ? PageGlass.chipFill(isActive: true) : (isHovered ? Ink.rowFill : Color.clear))
      )
      .overlay(
        RoundedRectangle(cornerRadius: OmiChrome.elementRadius)
          .stroke(isSelected ? Ink.hairline : Color.clear, lineWidth: 1)
      )
    }
    .buttonStyle(.plain)
    .onHover { hovering in
      isHovered = hovering
    }
    .task {
      await loadThumbnail()
    }
  }

  @ViewBuilder
  private func highlightedSnippet(_ snippet: String) -> some View {
    let lowercasedQuery = searchQuery.lowercased()
    let lowercasedSnippet = snippet.lowercased()

    if let range = lowercasedSnippet.range(of: lowercasedQuery) {
      // Use lowercasedSnippet for distance calculation to avoid String.Index incompatibility
      let beforeIndex = lowercasedSnippet.distance(from: lowercasedSnippet.startIndex, to: range.lowerBound)
      let afterIndex = lowercasedSnippet.distance(from: lowercasedSnippet.startIndex, to: range.upperBound)

      // Bounds check before creating indices
      if beforeIndex <= snippet.count, afterIndex <= snippet.count, beforeIndex <= afterIndex {
        let before = String(snippet.prefix(beforeIndex))
        let match = String(
          snippet[
            snippet.index(
              snippet.startIndex, offsetBy: beforeIndex)..<snippet.index(snippet.startIndex, offsetBy: afterIndex)])
        let after = String(snippet.suffix(from: snippet.index(snippet.startIndex, offsetBy: afterIndex)))

        (Text(before).foregroundColor(Ink.secondary) + Text(match).foregroundColor(Ink.primary).bold()
          + Text(after).foregroundColor(Ink.secondary))
          .scaledFont(size: OmiType.caption)
          .lineLimit(3)
      } else {
        Text(snippet)
          .scaledFont(size: OmiType.caption)
          .foregroundColor(Ink.secondary)
          .lineLimit(3)
      }
    } else {
      Text(snippet)
        .scaledFont(size: OmiType.caption)
        .foregroundColor(Ink.secondary)
        .lineLimit(3)
    }
  }

  private func loadThumbnail() async {
    do {
      // 120×80 pt row @2x retina — decode a downsampled thumbnail, not the
      // full-resolution screenshot, to keep a long results list light on memory.
      let image = try await RewindStorage.shared.loadScreenshotThumbnail(
        for: screenshot, maxPixelSize: 240)
      await MainActor.run {
        thumbnail = image
      }
    } catch {
      // Thumbnail load failed, keep placeholder
    }
  }
}

// MARK: - Search Result Group Item (Grouped results)

struct SearchResultGroupItem: View {
  let group: SearchResultGroup
  let index: Int
  let totalGroups: Int
  let totalScreenshots: Int
  let searchQuery: String
  let isSelected: Bool
  let onTap: () -> Void

  @State private var isHovered = false
  @State private var thumbnail: NSImage?

  var body: some View {
    Button(action: onTap) {
      HStack(alignment: .top, spacing: OmiSpacing.lg) {
        // Left side: Text content
        VStack(alignment: .leading, spacing: OmiSpacing.xs) {
          // App name and window title
          HStack(spacing: OmiSpacing.xs) {
            AppIconView(appName: group.appName, size: 16)
            Text(group.appName)
              .scaledFont(size: OmiType.caption, weight: .medium)
              .foregroundColor(Ink.primary)
            if let windowTitle = group.windowTitle, !windowTitle.isEmpty {
              Text("›")
                .foregroundColor(Ink.secondary)
              Text(windowTitle)
                .scaledFont(size: OmiType.caption)
                .foregroundColor(Ink.secondary)
                .lineLimit(1)
            }
          }

          // Time range
          Text(group.formattedTimeRange)
            .scaledFont(size: OmiType.body, weight: .medium)
            .foregroundColor(Ink.primary)

          // Context snippet from representative screenshot
          if let snippet = group.representativeScreenshot.contextSnippet(for: searchQuery) {
            highlightedSnippet(snippet)
          }

          // Group info: count and position
          HStack(spacing: OmiSpacing.sm) {
            if group.count > 1 {
              HStack(spacing: OmiSpacing.xxs) {
                Image(systemName: "square.stack")
                  .scaledFont(size: OmiType.micro)
                Text("\(group.count) screenshots")
              }
              .scaledFont(size: OmiType.micro)
              .foregroundColor(Ink.secondary)
              .padding(.horizontal, OmiSpacing.xs)
              .padding(.vertical, OmiSpacing.hairline)
              .background(Ink.rowFillHover)
              .cornerRadius(OmiChrome.stripRadius)
            }

            Text("Group \(index + 1) of \(totalGroups)")
              .scaledFont(size: OmiType.micro)
              .foregroundColor(Ink.secondary)
          }
          .padding(.top, OmiSpacing.hairline)
        }

        Spacer()

        // Right side: Small thumbnail
        Group {
          if let thumb = thumbnail {
            Image(nsImage: thumb)
              .resizable()
              .aspectRatio(contentMode: .fill)
              .frame(width: 120, height: 80)
              .cornerRadius(OmiChrome.badgeRadius)
              .clipped()
          } else {
            Rectangle()
              .fill(Ink.rowFill)
              .frame(width: 120, height: 80)
              .cornerRadius(OmiChrome.badgeRadius)
              .overlay(
                ProgressView()
                  .progressViewStyle(.circular)
                  .scaleEffect(0.6)
                  .tint(Ink.secondary)
              )
          }
        }
      }
      .padding(.horizontal, OmiSpacing.lg)
      .padding(.vertical, OmiSpacing.md)
      .background(
        RoundedRectangle(cornerRadius: OmiChrome.elementRadius)
          .fill(isSelected ? PageGlass.chipFill(isActive: true) : (isHovered ? Ink.rowFill : Color.clear))
      )
      .overlay(
        RoundedRectangle(cornerRadius: OmiChrome.elementRadius)
          .stroke(isSelected ? Ink.hairline : Color.clear, lineWidth: 1)
      )
    }
    .buttonStyle(.plain)
    .onHover { hovering in
      isHovered = hovering
    }
    .task {
      await loadThumbnail()
    }
  }

  @ViewBuilder
  private func highlightedSnippet(_ snippet: String) -> some View {
    let lowercasedQuery = searchQuery.lowercased()
    let lowercasedSnippet = snippet.lowercased()

    if let range = lowercasedSnippet.range(of: lowercasedQuery) {
      // Use lowercasedSnippet for distance calculation to avoid String.Index incompatibility
      let beforeIndex = lowercasedSnippet.distance(from: lowercasedSnippet.startIndex, to: range.lowerBound)
      let afterIndex = lowercasedSnippet.distance(from: lowercasedSnippet.startIndex, to: range.upperBound)

      // Bounds check before creating indices
      if beforeIndex <= snippet.count, afterIndex <= snippet.count, beforeIndex <= afterIndex {
        let before = String(snippet.prefix(beforeIndex))
        let match = String(
          snippet[
            snippet.index(
              snippet.startIndex, offsetBy: beforeIndex)..<snippet.index(snippet.startIndex, offsetBy: afterIndex)])
        let after = String(snippet.suffix(from: snippet.index(snippet.startIndex, offsetBy: afterIndex)))

        (Text(before).foregroundColor(Ink.secondary) + Text(match).foregroundColor(Ink.primary).bold()
          + Text(after).foregroundColor(Ink.secondary))
          .scaledFont(size: OmiType.caption)
          .lineLimit(3)
      } else {
        Text(snippet)
          .scaledFont(size: OmiType.caption)
          .foregroundColor(Ink.secondary)
          .lineLimit(3)
      }
    } else {
      Text(snippet)
        .scaledFont(size: OmiType.caption)
        .foregroundColor(Ink.secondary)
        .lineLimit(3)
    }
  }

  private func loadThumbnail() async {
    do {
      // 120×80 pt row @2x retina — decode a downsampled thumbnail, not the
      // full-resolution screenshot, to keep a long results list light on memory.
      let image = try await RewindStorage.shared.loadScreenshotThumbnail(
        for: group.representativeScreenshot, maxPixelSize: 240)
      await MainActor.run {
        thumbnail = image
      }
    } catch {
      // Thumbnail load failed, keep placeholder
    }
  }
}

// MARK: - Search Result Row (Legacy)

struct SearchResultRow: View {
  let screenshot: Screenshot
  let searchQuery: String?
  let isSelected: Bool
  let onTap: () -> Void

  @State private var isHovered = false

  var body: some View {
    Button(action: onTap) {
      HStack(spacing: OmiSpacing.md) {
        // App icon
        AppIconView(appName: screenshot.appName, size: 24)

        // Info
        VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
          HStack {
            Text(screenshot.appName)
              .scaledFont(size: OmiType.body, weight: .medium)
              .foregroundColor(Ink.primary)

            if let windowTitle = screenshot.windowTitle, !windowTitle.isEmpty {
              Text("— \(windowTitle)")
                .scaledFont(size: OmiType.caption)
                .foregroundColor(Ink.secondary)
                .lineLimit(1)
            }
          }

          // Context snippet if searching
          if let query = searchQuery,
            let snippet = screenshot.contextSnippet(for: query)
          {
            Text(snippet)
              .scaledFont(size: OmiType.caption)
              .foregroundColor(Ink.secondary)
              .lineLimit(2)
          }
        }

        Spacer()

        // Timestamp
        Text(screenshot.formattedDate)
          .scaledFont(size: OmiType.caption, design: .monospaced)
          .foregroundColor(Ink.secondary)

        // Selection indicator
        if isSelected {
          Image(systemName: "checkmark.circle.fill")
            .scaledFont(size: OmiType.body)
            .foregroundColor(Ink.primary)
        }
      }
      .padding(.horizontal, OmiSpacing.md)
      .padding(.vertical, OmiSpacing.sm)
      .background(
        RoundedRectangle(cornerRadius: OmiChrome.elementRadius)
          .fill(
            isSelected
              ? PageGlass.chipFill(isActive: true) : (isHovered ? Ink.rowFill : Color.clear))
      )
      .overlay(
        RoundedRectangle(cornerRadius: OmiChrome.elementRadius)
          .stroke(isSelected ? Ink.hairline : Color.clear, lineWidth: 1)
      )
    }
    .buttonStyle(.plain)
    .onHover { hovering in
      isHovered = hovering
    }
  }
}

// MARK: - Scroll Wheel Event Monitor

/// View modifier that monitors scroll wheel events globally when the view is visible
struct ScrollWheelMonitor: ViewModifier {
  let onScroll: (CGFloat) -> Void
  @State private var monitor: Any?

  func body(content: Content) -> some View {
    content
      .onAppear {
        // Add local monitor for scroll wheel events
        monitor = NSEvent.addLocalMonitorForEvents(matching: .scrollWheel) { event in
          let delta = event.scrollingDeltaY + event.scrollingDeltaX
          if delta != 0 {
            onScroll(delta)
          }
          return event  // Pass event through
        }
      }
      .onDisappear {
        if let monitor = monitor {
          NSEvent.removeMonitor(monitor)
        }
        monitor = nil
      }
  }
}

extension View {
  func onScrollWheel(_ handler: @escaping (CGFloat) -> Void) -> some View {
    modifier(ScrollWheelMonitor(onScroll: handler))
  }
}

#if canImport(PreviewsMacros)
  #Preview {
    RewindPage()
      .frame(width: 1000, height: 700)
  }
#endif
