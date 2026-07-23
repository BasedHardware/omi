@preconcurrency import AppKit
import OmiTheme
import SwiftUI

/// Main Rewind page - Timeline-first view with integrated search
/// The timeline is the primary interface, with search results highlighted inline
struct RewindPage: View {
  var appState: AppState? = nil
  /// Returns to the shell tab the user came from. Nil in the standalone window,
  /// where the gear menu handles navigation instead.
  var onBack: (() -> Void)? = nil

  @StateObject private var viewModel = RewindViewModel()

  @State private var currentIndex: Int = 0
  @State private var currentImage: NSImage?
  @State private var isLoadingFrame = false
  @State private var frameLoadTask: Task<Void, Never>?
  @State private var frameLoadRequestID = UUID()
  @State private var showDatePicker = false

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
    if showSavedSuccess { return .white }
    if showDiscarded { return .white }
    if showError { return .white }
    return .black
  }

  private var finishButtonBackground: Color {
    if showSavedSuccess { return OmiColors.success }
    if showDiscarded { return OmiColors.warning }
    if showError { return OmiColors.error }
    return .white
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
      Color.black.ignoresSafeArea()

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
    .onKeyPress(.escape) {
      // Expanded transcript → collapse
      if isTranscriptExpanded {
        isTranscriptExpanded = false
        LiveTranscriptMonitor.shared.clearSaved()
        return .handled
      }
      // Timeline mode → go back to results list
      if searchViewMode == .timeline {
        searchViewMode = .results
        return .handled
      }
      // In search mode → clear search
      if viewModel.activeSearchQuery != nil {
        viewModel.searchQuery = ""
        searchViewMode = nil
        return .handled
      }
      if isSearchFocused {
        isSearchFocused = false
        return .handled
      }
      return .ignored
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
        .foregroundColor(.white.opacity(0.3))

      if viewModel.isSearching {
        Text("Searching...")
          .scaledFont(size: OmiType.subheading, weight: .medium)
          .foregroundColor(.white.opacity(0.6))
      } else {
        Text("No results found")
          .scaledFont(size: OmiType.subheading, weight: .medium)
          .foregroundColor(.white.opacity(0.6))

        Text("Try a different search term")
          .scaledFont(size: OmiType.body)
          .foregroundColor(.white.opacity(0.4))
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
            .foregroundColor(.white.opacity(0.7))
            .frame(width: 28, height: 28)
            .background(Color.white.opacity(0.1))
            .clipShape(Circle())
        }
        .buttonStyle(.plain)
        .help("Back to results")
      } else {
        // Back to the tab the user came from (shell only).
        if let onBack {
          Button(action: onBack) {
            HStack(spacing: OmiSpacing.xs) {
              Image(systemName: "arrow.left")
                .scaledFont(size: OmiType.caption, weight: .semibold)
              Text("Back")
                .scaledFont(size: OmiType.caption, weight: .semibold)
            }
            .foregroundColor(.white.opacity(0.85))
            .padding(.horizontal, OmiSpacing.sm + 2)
            .padding(.vertical, 6)
            .background(Capsule(style: .continuous).fill(Color.white.opacity(0.1)))
            .contentShape(Capsule())
          }
          .buttonStyle(.plain)
          .help("Back to app")
        }

        // Rewind title
        HStack(spacing: OmiSpacing.sm) {
          Text("Rewind")
            .scaledFont(size: OmiType.subheading, weight: .semibold)
            .foregroundColor(.white)

          // Global hotkey hint
          HStack(spacing: OmiSpacing.hairline) {
            Text("⌘")
            Text("⌥")
            Text("R")
          }
          .scaledFont(size: OmiType.micro, weight: .medium, design: .rounded)
          .foregroundColor(.white.opacity(0.4))
          .padding(.horizontal, OmiSpacing.xs)
          .padding(.vertical, OmiSpacing.hairline)
          .background(Color.white.opacity(0.1))
          .cornerRadius(OmiChrome.stripRadius)
          .help("Press ⌘⌥R from anywhere to open Rewind")
        }
      }

      // Search field + date picker - always present
      searchField(showResultsCount: isInSearchMode)
      datePickerControls

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
              .foregroundColor(searchViewMode == .results ? .black : .white.opacity(0.5))
              .frame(width: 28, height: 24)
              .background(searchViewMode == .results ? Color.white : Color.clear)
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
              .foregroundColor(searchViewMode == .timeline ? .black : .white.opacity(0.5))
              .frame(width: 28, height: 24)
              .background(searchViewMode == .timeline ? Color.white : Color.clear)
              .cornerRadius(OmiChrome.stripRadius)
          }
          .buttonStyle(.plain)
          .help("Timeline view")
        }
        .padding(OmiSpacing.hairline)
        .background(Color.white.opacity(0.1))
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
          .foregroundColor(.white.opacity(0.6))
      }
      .buttonStyle(.plain)
      .help("Rewind Settings")

      // Rewind on/off toggle (screen capture only)
      if let badgeText = screenCaptureHealth.rewindBadgeText {
        Text(badgeText)
          .scaledFont(size: OmiType.micro, weight: .medium)
          .foregroundColor(OmiColors.warning)
          .padding(.horizontal, OmiSpacing.xs)
          .padding(.vertical, OmiSpacing.hairline)
          .background(OmiColors.warning.opacity(0.15))
          .cornerRadius(OmiChrome.stripRadius)
          .help(screenCaptureHealth.statusText)
      }
      rewindToggle
    }
    .padding(.horizontal, OmiSpacing.lg)
    .padding(.vertical, OmiSpacing.sm)
    .background(OmiColors.backgroundTertiary.opacity(0.8))
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

  // MARK: - Full Screen Results View (Google-style vertical list with grouping)

  private var fullScreenResultsView: some View {
    let groups = viewModel.groupedSearchResults

    return ScrollViewReader { proxy in
      ScrollView {
        LazyVStack(spacing: 1) {
          ForEach(Array(groups.enumerated()), id: \.element.id) { groupIndex, group in
            SearchResultGroupItem(
              group: group,
              index: groupIndex,
              totalGroups: groups.count,
              totalScreenshots: viewModel.totalScreenshotCount,
              searchQuery: viewModel.activeSearchQuery ?? "",
              isSelected: selectedGroupIndex == groupIndex,
              onTap: {
                // Set the screenshots to this group's screenshots for timeline navigation
                selectedGroupIndex = groupIndex
                currentIndex = 0
                searchViewMode = .timeline
                scheduleLoadCurrentFrame()
              }
            )
            .id(groupIndex)
          }
        }
        .padding(.vertical, OmiSpacing.sm)
      }
      .onChange(of: selectedGroupIndex) { _, newIndex in
        invalidatePendingFrameLoad()
        if searchViewMode == .timeline && !activeScreenshots.isEmpty {
          currentIndex = min(currentIndex, activeScreenshots.count - 1)
          scheduleLoadCurrentFrame()
        }
        OmiMotion.withGated {
          proxy.scrollTo(newIndex, anchor: .center)
        }
      }
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

  private func searchField(showResultsCount: Bool = false) -> some View {
    HStack(spacing: OmiSpacing.sm) {
      Image(systemName: "magnifyingglass")
        .scaledFont(size: OmiType.caption)
        .foregroundColor(isSearchFocused ? OmiColors.accent : .white.opacity(0.5))

      TextField("Search your screen history...", text: $viewModel.searchQuery)
        .textFieldStyle(.plain)
        .scaledFont(size: OmiType.body)
        .foregroundColor(.white)
        .focused($isSearchFocused)

      if viewModel.isSearching {
        ProgressView()
          .progressViewStyle(.circular)
          .scaleEffect(0.6)
          .tint(.white)
      } else if showResultsCount && !viewModel.searchQuery.isEmpty && viewModel.activeSearchQuery != nil {
        let groups = viewModel.groupedSearchResults
        let total = viewModel.totalScreenshotCount
        if groups.count == total {
          Text("\(total) results")
            .scaledFont(size: OmiType.caption)
            .foregroundColor(.white.opacity(0.5))
        } else {
          Text("\(groups.count) groups (\(total) total)")
            .scaledFont(size: OmiType.caption)
            .foregroundColor(.white.opacity(0.5))
        }
      }

      if !viewModel.searchQuery.isEmpty {
        Button {
          viewModel.searchQuery = ""
          searchViewMode = nil
        } label: {
          Image(systemName: "xmark.circle.fill")
            .scaledFont(size: OmiType.caption)
            .foregroundColor(.white.opacity(0.5))
        }
        .buttonStyle(.plain)
      }
    }
    .padding(.horizontal, OmiSpacing.md)
    .padding(.vertical, OmiSpacing.sm)
    .frame(maxWidth: 400)
    .background(
      RoundedRectangle(cornerRadius: OmiChrome.elementRadius)
        .fill(Color.white.opacity(0.1))
        .overlay(
          RoundedRectangle(cornerRadius: OmiChrome.elementRadius)
            .stroke(isSearchFocused ? OmiColors.accent.opacity(0.5) : Color.clear, lineWidth: 1)
        )
    )
  }

  // MARK: - Date Picker Controls

  private var datePickerControls: some View {
    Button {
      showDatePicker.toggle()
    } label: {
      HStack(spacing: OmiSpacing.xs) {
        Text(viewModel.selectedDate.formatted(.dateTime.month().day().year()))
          .scaledFont(size: OmiType.caption)
          .foregroundColor(.white)
        Image(systemName: "chevron.up.chevron.down")
          .scaledFont(size: 8, weight: .semibold)
          .foregroundColor(.white.opacity(0.5))
      }
      .padding(.horizontal, OmiSpacing.sm)
      .padding(.vertical, OmiSpacing.xs)
      .background(Color.white.opacity(0.15))
      .cornerRadius(OmiChrome.badgeRadius)
    }
    .buttonStyle(.plain)
    .popover(isPresented: $showDatePicker) {
      DatePicker(
        "",
        selection: Binding(
          get: { viewModel.selectedDate },
          set: { newDate in
            // Only reload if the selected day actually changed
            let calendar = Calendar.current
            guard !calendar.isDate(newDate, inSameDayAs: viewModel.selectedDate) else { return }
            Task { await viewModel.filterByDate(newDate) }
          }
        ),
        displayedComponents: [.date]
      )
      .datePickerStyle(.graphical)
      .labelsHidden()
      .padding(OmiSpacing.sm)
    }
  }

  // MARK: - Frame Display

  private var frameDisplay: some View {
    GeometryReader { geometry in
      if isLoadingFrame && currentImage == nil {
        ProgressView()
          .progressViewStyle(.circular)
          .scaleEffect(1.2)
          .tint(.white)
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
            .cornerRadius(OmiChrome.stripRadius)
            .shadow(color: .black.opacity(0.3), radius: 8)

          // Search highlight overlays with explicit frame
          if let query = viewModel.activeSearchQuery,
            currentIndex < activeScreenshots.count
          {
            SearchHighlightOverlay(
              screenshot: activeScreenshots[currentIndex],
              query: query,
              imageSize: image.size,
              containerSize: displaySize
            )
            .frame(width: displaySize.width, height: displaySize.height)
          }
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
            .foregroundColor(.white.opacity(0.3))
          Text("No frame")
            .scaledFont(size: OmiType.caption)
            .foregroundColor(.white.opacity(0.4))
        }
        .frame(width: geometry.size.width, height: geometry.size.height)
      }
    }
    .padding(.horizontal, OmiSpacing.md)
  }

  // MARK: - Bottom Controls (Compact - all on one line)

  private var bottomControls: some View {
    let screenshots = activeScreenshots

    return VStack(spacing: OmiSpacing.sm) {
      // Timeline bar
      InteractiveTimelineBar(
        screenshots: screenshots,
        currentIndex: currentIndex,
        searchResultIndices: viewModel.activeSearchQuery != nil && searchViewMode != .timeline
          ? Set(searchResultIndices) : nil,
        onSelect: { index in
          seekToIndex(index)
        }
      )

      // Compact control bar: position/timestamp | scroll hint
      HStack(spacing: OmiSpacing.md) {
        // Left: Legend indicators (only when searching)
        if viewModel.activeSearchQuery != nil && !searchResultIndices.isEmpty {
          HStack(spacing: OmiSpacing.xxs) {
            RoundedRectangle(cornerRadius: 1)
              .fill(Color.yellow.opacity(0.8))
              .frame(width: 8, height: 8)
            Text("match")
              .scaledFont(size: 9)
              .foregroundColor(.white.opacity(0.4))
          }
        }

        Spacer()

        // Right: Position and timestamp
        if currentIndex < screenshots.count {
          let screenshot = screenshots[currentIndex]
          HStack(spacing: OmiSpacing.sm) {
            Text("\(currentIndex + 1)/\(screenshots.count)")
              .scaledFont(size: OmiType.micro, design: .monospaced)
              .foregroundColor(.white.opacity(0.5))
            Text(screenshot.formattedDateCompact)
              .scaledFont(size: OmiType.micro, design: .monospaced)
              .foregroundColor(.white.opacity(0.7))
          }
        }

        // Navigation hint
        Text("scroll or drag to navigate")
          .scaledFont(size: OmiType.micro)
          .foregroundColor(.white.opacity(0.3))
      }
      .padding(.horizontal, OmiSpacing.lg)
      .padding(.vertical, OmiSpacing.sm)
    }
    .padding(.bottom, OmiSpacing.md)
    .background(
      LinearGradient(
        colors: [.clear, .black.opacity(0.7)],
        startPoint: .top,
        endPoint: .bottom
      )
    )
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
            .fill(Color.red.opacity(0.1))
            .frame(width: 80, height: 80)

          Image(systemName: "rectangle.on.rectangle.slash")
            .scaledFont(size: 36)
            .foregroundColor(.red.opacity(0.7))
        }

        Text("Screen Recording Needs Reset")
          .scaledFont(size: OmiType.heading, weight: .semibold)
          .foregroundColor(.white)

        Text(
          "macOS granted permission but ScreenCaptureKit is stuck.\nResetting fixes this — the app will restart automatically."
        )
        .scaledFont(size: OmiType.body)
        .foregroundColor(.white.opacity(0.6))
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
            .foregroundColor(.white)
            .padding(.horizontal, OmiSpacing.xl)
            .padding(.vertical, OmiSpacing.sm)
            .background(Color.red.opacity(0.8))
            .cornerRadius(OmiChrome.elementRadius)
        }
        .buttonStyle(.plain)
        .padding(.top, OmiSpacing.xxs)
      } else if hasNoPermission {
        ZStack {
          Circle()
            .fill(Color.orange.opacity(0.1))
            .frame(width: 80, height: 80)

          Image(systemName: "lock.rectangle")
            .scaledFont(size: 36)
            .foregroundColor(.orange.opacity(0.7))
        }

        Text("Screen Recording Permission Required")
          .scaledFont(size: OmiType.heading, weight: .semibold)
          .foregroundColor(.white)

        Text("Rewind needs Screen Recording permission to capture your screen.")
          .scaledFont(size: OmiType.body)
          .foregroundColor(.white.opacity(0.6))
          .multilineTextAlignment(.center)

        Button {
          // Re-enable screen analysis so it auto-starts after permission is granted and app restarts
          screenAnalysisEnabled = true
          AssistantSettings.shared.screenAnalysisEnabled = true
          ScreenCaptureService.requestScreenRecordingAccessAndOpenSettings()
        } label: {
          Text("Grant Permission")
            .scaledFont(size: OmiType.body, weight: .semibold)
            .foregroundColor(.white)
            .padding(.horizontal, OmiSpacing.xl)
            .padding(.vertical, OmiSpacing.sm)
            .background(Color.orange.opacity(0.8))
            .cornerRadius(OmiChrome.elementRadius)
        }
        .buttonStyle(.plain)
        .padding(.top, OmiSpacing.xxs)
      } else {
        ZStack {
          Circle()
            .fill(OmiColors.accent.opacity(0.1))
            .frame(width: 80, height: 80)

          Image(systemName: "clock.arrow.circlepath")
            .scaledFont(size: 36)
            .foregroundColor(OmiColors.accent.opacity(0.6))
        }

        Text("No Screenshots Yet")
          .scaledFont(size: OmiType.heading, weight: .semibold)
          .foregroundColor(.white)

        Text("Screenshots will appear here as you use your Mac.\nRewind captures your screen every second.")
          .scaledFont(size: OmiType.body)
          .foregroundColor(.white.opacity(0.6))
          .multilineTextAlignment(.center)

        HStack(spacing: OmiSpacing.sm) {
          Image(systemName: "lightbulb.fill")
            .foregroundColor(.yellow)
          Text("Tip: Use search to find anything you've seen on screen")
            .scaledFont(size: OmiType.caption)
            .foregroundColor(.white.opacity(0.7))
        }
        .padding(.horizontal, OmiSpacing.lg)
        .padding(.vertical, OmiSpacing.sm)
        .background(Color.white.opacity(0.1))
        .cornerRadius(OmiChrome.elementRadius)
        .padding(.top, OmiSpacing.sm)
      }

      Spacer()
    }
  }

  private var recoveryBanner: some View {
    HStack(spacing: OmiSpacing.md) {
      Image(systemName: "exclamationmark.triangle.fill")
        .foregroundColor(.orange)
        .scaledFont(size: OmiType.subheading)

      VStack(alignment: .leading, spacing: OmiSpacing.hairline) {
        Text("Database Recovered")
          .scaledFont(size: OmiType.body, weight: .semibold)
          .foregroundColor(.white)

        if viewModel.recoveredRecordCount > 0 {
          Text("\(viewModel.recoveredRecordCount) screenshots recovered from corrupted database")
            .scaledFont(size: OmiType.caption)
            .foregroundColor(.white.opacity(0.7))
        } else {
          Text("Database was corrupted and has been reset. Your video files are intact.")
            .scaledFont(size: OmiType.caption)
            .foregroundColor(.white.opacity(0.7))
        }
      }

      Spacer()

      if viewModel.recoveredRecordCount == 0 {
        Button {
          Task { await rebuildDatabase() }
        } label: {
          Text("Rebuild Index")
            .scaledFont(size: OmiType.caption, weight: .medium)
            .foregroundColor(OmiColors.textPrimary)
            .padding(.horizontal, OmiSpacing.sm)
            .padding(.vertical, OmiSpacing.xxs)
            .background(Color.white)
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
          .foregroundColor(.white.opacity(0.6))
      }
      .buttonStyle(.plain)
    }
    .padding(.horizontal, OmiSpacing.lg)
    .padding(.vertical, OmiSpacing.sm)
    .background(Color.orange.opacity(0.15))
    .overlay(
      Rectangle()
        .fill(Color.orange)
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
        .tint(.white)

      Text("Loading screenshots...")
        .scaledFont(size: OmiType.body)
        .foregroundColor(.white.opacity(0.6))
    }
  }

  private func errorView(_: String) -> some View {
    VStack(spacing: OmiSpacing.lg) {
      ZStack {
        Circle()
          .fill(OmiColors.error.opacity(0.1))
          .frame(width: 80, height: 80)

        Image(systemName: "exclamationmark.triangle")
          .scaledFont(size: 36)
          .foregroundColor(OmiColors.error)
      }

      Text("Failed to Load Screenshots")
        .scaledFont(size: OmiType.heading, weight: .semibold)
        .foregroundColor(.white)

      Text("Try again. If this continues, restart Omi.")
        .scaledFont(size: OmiType.body)
        .foregroundColor(.white.opacity(0.6))

      Button {
        Task { await viewModel.loadInitialData() }
      } label: {
        HStack(spacing: OmiSpacing.xs) {
          Image(systemName: "arrow.clockwise")
          Text("Retry")
        }
        .scaledFont(size: OmiType.body, weight: .medium)
        .foregroundColor(OmiColors.textPrimary)
        .padding(.horizontal, OmiSpacing.xl)
        .padding(.vertical, OmiSpacing.sm)
        .background(Color.white)
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
            .foregroundColor(.white.opacity(0.7))
            .padding(.horizontal, OmiSpacing.sm)
            .padding(.vertical, OmiSpacing.xs)
            .background(Color.white.opacity(0.1))
            .cornerRadius(OmiChrome.badgeRadius)
          }
          .buttonStyle(.plain)

          Spacer()
        }
        .padding(.horizontal, OmiSpacing.lg)
        .padding(.vertical, OmiSpacing.sm)
        .background(OmiColors.backgroundTertiary.opacity(0.8))
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
          .background(OmiColors.backgroundPrimary)

          // Divider
          Rectangle()
            .fill(OmiColors.border)
            .frame(width: 1)

          // Right: Notes
          LiveNotesView()
            .frame(width: notesWidth)
        }
      }
    }
    .background(OmiColors.backgroundPrimary)
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
              .foregroundColor(OmiColors.textTertiary)
          }
          .padding(.horizontal, OmiSpacing.sm)
          .padding(.vertical, OmiSpacing.xxs)
          .background(
            RoundedRectangle(cornerRadius: OmiChrome.badgeRadius)
              .fill(OmiColors.backgroundTertiary.opacity(0.5))
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
            .fill(OmiColors.accent.opacity(0.3))
            .frame(width: 24, height: 24)
            .scaleEffect(isSavingPulsing ? 1.5 : 1.0)
            .opacity(isSavingPulsing ? 0.0 : 0.6)

          Image(systemName: "arrow.up.circle.fill")
            .scaledFont(size: OmiType.subheading)
            .foregroundColor(OmiColors.accent)
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
          .foregroundColor(OmiColors.textPrimary)

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
          .overlay(Capsule().stroke(OmiColors.border, lineWidth: 1))
        }
        .buttonStyle(.plain)
        .disabled(isFinishing || showSavedSuccess || showDiscarded || showError)
        .help("Saves current conversation and starts a new one")
      }

    }
    .padding(.horizontal, OmiSpacing.lg)
    .padding(.vertical, OmiSpacing.sm)
    .background(OmiColors.backgroundTertiary.opacity(0.8))
  }

  // MARK: - Audio Toggle

  private func audioToggle(appState: AppState) -> some View {
    ZStack {
      Capsule()
        .fill(appState.isTranscribing ? OmiColors.accent : Color.red)
        .frame(width: 36, height: 20)

      Circle()
        .fill(appState.isTranscribing ? OmiColors.backgroundPrimary : Color.white)
        .frame(width: 16, height: 16)
        .shadow(color: .black.opacity(0.15), radius: 1, x: 0, y: 1)
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
              .foregroundColor(OmiColors.accent)
            if let windowTitle = screenshot.windowTitle, !windowTitle.isEmpty {
              Text("›")
                .foregroundColor(.white.opacity(0.3))
              Text(windowTitle)
                .scaledFont(size: OmiType.caption)
                .foregroundColor(.white.opacity(0.5))
                .lineLimit(1)
            }
          }

          // Timestamp (like page title in Google)
          Text(screenshot.formattedDate)
            .scaledFont(size: OmiType.body, weight: .medium)
            .foregroundColor(.white)

          // Context snippet with highlighted search term
          if let snippet = screenshot.contextSnippet(for: searchQuery) {
            highlightedSnippet(snippet)
          }

          // Result number
          Text("Result \(index + 1) of \(totalCount)")
            .scaledFont(size: OmiType.micro)
            .foregroundColor(.white.opacity(0.3))
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
              .fill(Color.white.opacity(0.1))
              .frame(width: 120, height: 80)
              .cornerRadius(OmiChrome.badgeRadius)
              .overlay(
                ProgressView()
                  .progressViewStyle(.circular)
                  .scaleEffect(0.6)
                  .tint(.white.opacity(0.5))
              )
          }
        }
      }
      .padding(.horizontal, OmiSpacing.lg)
      .padding(.vertical, OmiSpacing.md)
      .background(
        RoundedRectangle(cornerRadius: OmiChrome.elementRadius)
          .fill(isSelected ? OmiColors.accent.opacity(0.15) : (isHovered ? Color.white.opacity(0.05) : Color.clear))
      )
      .overlay(
        RoundedRectangle(cornerRadius: OmiChrome.elementRadius)
          .stroke(isSelected ? OmiColors.accent.opacity(0.4) : Color.clear, lineWidth: 1)
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

        (Text(before).foregroundColor(.white.opacity(0.6)) + Text(match).foregroundColor(.white).bold()
          + Text(after).foregroundColor(.white.opacity(0.6)))
          .scaledFont(size: OmiType.caption)
          .lineLimit(3)
      } else {
        Text(snippet)
          .scaledFont(size: OmiType.caption)
          .foregroundColor(.white.opacity(0.6))
          .lineLimit(3)
      }
    } else {
      Text(snippet)
        .scaledFont(size: OmiType.caption)
        .foregroundColor(.white.opacity(0.6))
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
              .foregroundColor(OmiColors.accent)
            if let windowTitle = group.windowTitle, !windowTitle.isEmpty {
              Text("›")
                .foregroundColor(.white.opacity(0.3))
              Text(windowTitle)
                .scaledFont(size: OmiType.caption)
                .foregroundColor(.white.opacity(0.5))
                .lineLimit(1)
            }
          }

          // Time range
          Text(group.formattedTimeRange)
            .scaledFont(size: OmiType.body, weight: .medium)
            .foregroundColor(.white)

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
              .foregroundColor(OmiColors.accent.opacity(0.8))
              .padding(.horizontal, OmiSpacing.xs)
              .padding(.vertical, OmiSpacing.hairline)
              .background(OmiColors.accent.opacity(0.15))
              .cornerRadius(OmiChrome.stripRadius)
            }

            Text("Group \(index + 1) of \(totalGroups)")
              .scaledFont(size: OmiType.micro)
              .foregroundColor(.white.opacity(0.3))
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
              .fill(Color.white.opacity(0.1))
              .frame(width: 120, height: 80)
              .cornerRadius(OmiChrome.badgeRadius)
              .overlay(
                ProgressView()
                  .progressViewStyle(.circular)
                  .scaleEffect(0.6)
                  .tint(.white.opacity(0.5))
              )
          }
        }
      }
      .padding(.horizontal, OmiSpacing.lg)
      .padding(.vertical, OmiSpacing.md)
      .background(
        RoundedRectangle(cornerRadius: OmiChrome.elementRadius)
          .fill(isSelected ? OmiColors.accent.opacity(0.15) : (isHovered ? Color.white.opacity(0.05) : Color.clear))
      )
      .overlay(
        RoundedRectangle(cornerRadius: OmiChrome.elementRadius)
          .stroke(isSelected ? OmiColors.accent.opacity(0.4) : Color.clear, lineWidth: 1)
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

        (Text(before).foregroundColor(.white.opacity(0.6)) + Text(match).foregroundColor(.white).bold()
          + Text(after).foregroundColor(.white.opacity(0.6)))
          .scaledFont(size: OmiType.caption)
          .lineLimit(3)
      } else {
        Text(snippet)
          .scaledFont(size: OmiType.caption)
          .foregroundColor(.white.opacity(0.6))
          .lineLimit(3)
      }
    } else {
      Text(snippet)
        .scaledFont(size: OmiType.caption)
        .foregroundColor(.white.opacity(0.6))
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
              .foregroundColor(.white)

            if let windowTitle = screenshot.windowTitle, !windowTitle.isEmpty {
              Text("— \(windowTitle)")
                .scaledFont(size: OmiType.caption)
                .foregroundColor(.white.opacity(0.6))
                .lineLimit(1)
            }
          }

          // Context snippet if searching
          if let query = searchQuery,
            let snippet = screenshot.contextSnippet(for: query)
          {
            Text(snippet)
              .scaledFont(size: OmiType.caption)
              .foregroundColor(.white.opacity(0.7))
              .lineLimit(2)
          }
        }

        Spacer()

        // Timestamp
        Text(screenshot.formattedDate)
          .scaledFont(size: OmiType.caption, design: .monospaced)
          .foregroundColor(.white.opacity(0.5))

        // Selection indicator
        if isSelected {
          Image(systemName: "checkmark.circle.fill")
            .scaledFont(size: OmiType.body)
            .foregroundColor(OmiColors.accent)
        }
      }
      .padding(.horizontal, OmiSpacing.md)
      .padding(.vertical, OmiSpacing.sm)
      .background(
        RoundedRectangle(cornerRadius: OmiChrome.elementRadius)
          .fill(
            isSelected
              ? OmiColors.accent.opacity(0.2) : (isHovered ? Color.white.opacity(0.1) : Color.white.opacity(0.05)))
      )
      .overlay(
        RoundedRectangle(cornerRadius: OmiChrome.elementRadius)
          .stroke(isSelected ? OmiColors.accent.opacity(0.5) : Color.clear, lineWidth: 1)
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
