@preconcurrency import AppKit
import Combine
import OmiTheme
import SwiftUI

/// Main Rewind page - Timeline-first view with integrated search
/// The timeline is the primary interface, with search results highlighted inline
struct RewindPage: View {
  var appState: AppState? = nil
  var brainDestination: MemoryHubDestination? = nil
  var onSelectBrainDestination: ((MemoryHubDestination) -> Void)? = nil

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
  @State private var unavailableCitationScreenshotID: Int64?
  @FocusState private var isSearchFocused: Bool
  @FocusState private var isPageFocused: Bool

  // Monitoring toggle state
  @State var isMonitoring = false
  @State var screenCaptureHealth: ScreenCaptureHealth = .stopped
  @State var isTogglingMonitoring = false
  @AppStorage("screenAnalysisEnabled") var screenAnalysisEnabled = true
  /// Read here only to say *why* the history stops where it does — the setting itself lives in
  /// Settings → Rewind.
  @AppStorage("rewindRetentionDays") private var retentionDays = 7

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

  @ViewBuilder
  private var pageContent: some View {
    ZStack {
      // Background
      Color.clear.ignoresSafeArea()

      if viewModel.isLoading && viewModel.screenshots.isEmpty && viewModel.activeSearchQuery == nil {
        loadingView
      } else if let error = viewModel.errorMessage {
        errorView(error)
      } else {
        // Rewind is two glass objects with one shared lane. Keeping the lower player aligned with the
        // header prevents the route from reading like a differently-sized window.
        GeometryReader { proxy in
          let header = RewindSurfaceLayout.headerWidth(for: proxy.size.width)
          let player = RewindSurfaceLayout.playerWidth(for: proxy.size.width)
          VStack(spacing: 0) {
            if isTranscriptExpanded {
              // Expanded transcript + notes view replaces timeline
              rewindContentPanel(expandedTranscriptView, width: player)
            } else {
              // Recovery banner (if database was recovered from corruption)
              if viewModel.showRecoveryBanner {
                recoveryBanner.rewindHeaderPanel(width: header)
              }

              // Brain uses the same standalone search panel as every primary page. Standalone
              // Rewind keeps its historical compact header panel.
              if brainDestination != nil {
                unifiedTopBar.frame(width: header)
              } else {
                unifiedTopBar.rewindHeaderPanel(width: header)
              }

              // Content area changes based on mode
              if isInSearchMode {
                if viewModel.screenshots.isEmpty {
                  rewindContentPanel(noSearchResultsView, width: player)
                } else if searchViewMode == .timeline {
                  rewindContentPanel(timelineWithSearch, width: player)
                } else {
                  // Already two panels of its own, with its own gap under the bar.
                  fullScreenResultsView(width: header)
                }
              } else if !RewindTimelinePresentation.showsTimeline(
                screenshotCount: viewModel.screenshots.count,
                historyRange: viewModel.historyRange
              ) {
                rewindContentPanel(emptyState, width: player)
              } else {
                // Normal timeline view (without top bar, since we have unified one)
                rewindContentPanel(timelineContentBody, width: player)
              }
            }
          }
          .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
        }
        .padding(.top, RewindSurfaceLayout.topGap)
        .padding(.bottom, RewindSurfaceLayout.bottomGap)
      }

      if let screenshotID = unavailableCitationScreenshotID {
        VStack {
          citationUnavailableBanner(for: screenshotID)
          Spacer()
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
        .padding(.top, RewindSurfaceLayout.topGap)
        .padding(.horizontal, OmiSpacing.lg)
      }
    }
  }

  var body: some View {
    // Split so the release compiler can type-check. One 160-line modifier
    // chain here fails `swift build -c release` (Codemagic 170 / #11519).
    rewindPageKeyHandlers(rewindPageLifecycle(pageChrome))
  }

  private var pageChrome: some View {
    pageContent
      .glassContent()
      // The page answers arrow keys wherever the pointer is, so it holds keyboard focus itself. The
      // timeline track owns scroll gestures directly. This container is not a control, though: the
      // system focus effect around it was a 1 pt accent rectangle on the window's edges, which on a
      // window with no visible extent is a blue rectangle on the wallpaper. See
      // `shellPageKeyboardTarget`.
      .shellPageKeyboardTarget($isPageFocused)
  }

  private func rewindPageLifecycle<Content: View>(_ content: Content) -> some View {
    content
      .task {
        await viewModel.loadInitialData()
        await resolveCitationFocusIfNeeded()
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
      .onReceive(NotificationCenter.default.publisher(for: .rewindCitationFocusRequested)) { _ in
        Task { await resolveCitationFocusIfNeeded() }
      }
      .onReceive(NotificationCenter.default.publisher(for: .runtimeOwnerDidChange)) { _ in
        // RewindPage itself owns the decoded NSImage and frame-load task. Clearing
        // only the view model would leave the previous owner's last frame visible
        // while this persistent page reloads for the incoming account.
        invalidatePendingFrameLoad()
        currentImage = nil
        currentIndex = 0
        selectedGroupIndex = 0
        unavailableCitationScreenshotID = nil
        searchViewMode = nil
        selectedSpeakerSegment = nil
        isTranscriptExpanded = false
        LiveTranscriptMonitor.shared.clearSaved()
        // Cancel the model's in-flight citation admission immediately. The model also carries the
        // exact owner lease, so a suspended database read cannot insert an old-owner row later.
        viewModel.invalidateCitationFocus()
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
          currentIndex = RewindTimelineNavigation.sameFrameIndex(
            old: oldScreenshots.count, new: newScreenshots.count, current: currentIndex, found: newIndex)
          if currentIndex != newIndex { scheduleLoadCurrentFrame() }
        } else if !newScreenshots.isEmpty {
          // A viewport query may replace every sampled row. Stay near the same visible moment instead
          // of snapping to the newest capture in all of history.
          if !oldScreenshots.isEmpty, viewModel.activeSearchQuery == nil, trackWindow.span > 0 {
            let centre = trackWindow.start + trackWindow.span / 2
            currentIndex = RewindTimelineNavigation.nearestIndex(to: centre, screenshots: newScreenshots) ?? 0
          } else {
            currentIndex = newScreenshots.count - 1
          }
          selectedGroupIndex = 0
          scheduleLoadCurrentFrame()
        }
      }
      .onReceive(
        trackWindow.$start.combineLatest(trackWindow.$span)
          .debounce(for: .milliseconds(120), scheduler: DispatchQueue.main)
      ) { start, span in
        guard span > 0, viewModel.activeSearchQuery == nil else { return }
        Task { await viewModel.loadTimelineWindow(from: start, to: start + span) }
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
  }

  private func rewindPageKeyHandlers<Content: View>(_ content: Content) -> some View {
    content
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
  }

  @MainActor
  private func resolveCitationFocusIfNeeded() async {
    // Keep the one-shot request queued until the owner's initial database load has completed. A
    // notification can arrive while the destination is still mounting; consuming then would lose
    // the citation before Rewind can resolve it.
    guard viewModel.isReadyForCitationFocus,
      let request = RewindCitationFocusState.shared.consumeRequest()
    else { return }

    switch await viewModel.resolveCitationRequest(request) {
    case .staleOwner:
      return
    case .unavailable:
      guard RewindCitationFocusState.isCurrent(owner: request.owner) else { return }
      unavailableCitationScreenshotID = request.screenshotID
      return
    case .found(let screenshot):
      guard RewindCitationFocusState.isCurrent(owner: request.owner) else { return }

      // A citation jump owns the frame transition. Cancel the previous decode and clear its image
      // so an old day's picture cannot remain visible while the exact target day is sampled.
      invalidatePendingFrameLoad()
      currentImage = nil
      currentIndex = 0

      switch await viewModel.focusCitationScreenshotResult(
        screenshot,
        ownerLease: request.owner
      ) {
      case .staleOwner:
        return
      case .unavailable:
        guard RewindCitationFocusState.isCurrent(owner: request.owner) else { return }
        unavailableCitationScreenshotID = request.screenshotID
        return
      case .focused:
        guard let targetIndex = viewModel.screenshots.firstIndex(where: { $0.id == request.screenshotID })
        else {
          guard RewindCitationFocusState.isCurrent(owner: request.owner) else { return }
          unavailableCitationScreenshotID = request.screenshotID
          return
        }

        guard RewindCitationFocusState.isCurrent(owner: request.owner) else { return }
        unavailableCitationScreenshotID = nil
        currentIndex = targetIndex
        trackWindow.reveal(screenshot.timestamp.timeIntervalSince1970)
        scheduleLoadCurrentFrame()
      }
    }
  }

  private func citationUnavailableBanner(for screenshotID: Int64) -> some View {
    HStack(spacing: OmiSpacing.sm) {
      Image(systemName: "exclamationmark.triangle.fill")
        .foregroundColor(PageGlass.warning)
        .scaledFont(size: OmiType.body)

      VStack(alignment: .leading, spacing: OmiSpacing.hairline) {
        Text(RewindCitationUnavailablePresentationPolicy.title)
          .scaledFont(size: OmiType.caption, weight: .semibold)
          .foregroundColor(Ink.primary)
        Text(RewindCitationUnavailablePresentationPolicy.message(for: screenshotID))
          .scaledFont(size: OmiType.micro)
          .foregroundColor(Ink.secondary)
      }

      Spacer(minLength: OmiSpacing.xs)

      Button("Dismiss") {
        unavailableCitationScreenshotID = nil
      }
      .buttonStyle(.plain)
      .scaledFont(size: OmiType.micro, weight: .medium)
      .foregroundColor(PageGlass.primaryActionLabel)
      .accessibilityIdentifier("rewind-citation-unavailable-dismiss")
    }
    .padding(.horizontal, OmiSpacing.md)
    .padding(.vertical, OmiSpacing.sm)
    .glassCard(cornerRadius: PageGlass.chipRadius, emphasized: false)
    .accessibilityIdentifier("rewind-citation-unavailable")
    .accessibilityElement(children: .combine)
    .accessibilityLabel(RewindCitationUnavailablePresentationPolicy.title)
    .accessibilityValue(RewindCitationUnavailablePresentationPolicy.message(for: screenshotID))
    .accessibilityHint(RewindCitationUnavailablePresentationPolicy.hint)
  }

  /// The AppKit track owns wheel/swipe input and forwards only gestures that begin on the timeline.
  private func handleTimelineScroll(deltaX: CGFloat, deltaY: CGFloat) {
    guard viewModel.activeSearchQuery == nil, searchViewMode != .results else { return }
    trackWindow.pan(deltaX: deltaX, deltaY: deltaY)
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
    Group {
      if brainDestination != nil {
        QuerySearchBar(
          text: $viewModel.searchQuery,
          accessibilityID: "rewind-search-field",
          placeholder: "Search screen history…",
          focus: $isSearchFocused, searchSurface: .rewind
        )
        .onChange(of: viewModel.searchQuery) { _, query in
          if query.isEmpty { searchViewMode = nil }
        }
      } else {
        unifiedTopBarControls
          .padding(.horizontal, OmiSpacing.xxl)
          .padding(.vertical, OmiSpacing.md)
      }
    }
  }

  @ViewBuilder
  private func rewindContentPanel<Content: View>(_ content: Content, width: CGFloat) -> some View {
    if brainDestination != nil {
      VStack(alignment: .leading, spacing: 0) {
        brainNavigationRow
        content.frame(maxWidth: .infinity, maxHeight: .infinity)
      }
      .rewindPlayerPanel(width: width)
    } else {
      content.rewindPlayerPanel(width: width)
    }
  }

  @ViewBuilder
  private var brainNavigationRow: some View {
    if let brainDestination, let onSelectBrainDestination {
      HStack(spacing: OmiSpacing.md) {
        BrainSectionNavigation(
          selected: brainDestination,
          onSelect: onSelectBrainDestination
        )
        Spacer(minLength: OmiSpacing.sm)
        rewindBrainActions
      }
      .padding(.horizontal, QueryShellLayout.panelPaddingHorizontal)
      .padding(.top, BrainSectionPageMetrics.navigationTopPadding)
      .padding(.bottom, BrainSectionPageMetrics.navigationBottomPadding)
    }
  }

  private var rewindBrainActions: some View {
    HStack(spacing: OmiSpacing.sm) {
      if isInSearchMode {
        searchViewModeButton(
          title: "Results", icon: "list.bullet", mode: .results)
        searchViewModeButton(
          title: "Timeline", icon: "timeline.selection", mode: .timeline)
      }

      if isInSearchMode {
        Rectangle()
          .fill(Ink.separator)
          .frame(width: 1, height: 18)
          .accessibilityHidden(true)
      }

      rewindMoreMenu

      captureStateControl
    }
  }

  private func searchViewModeButton(title: String, icon: String, mode: SearchViewMode) -> some View {
    let isActive = searchViewMode == mode
    return Button {
      if mode == .timeline {
        if searchViewMode != .timeline && !viewModel.screenshots.isEmpty { currentIndex = 0 }
        searchViewMode = .timeline
        scheduleLoadCurrentFrame()
      } else {
        searchViewMode = .results
      }
    } label: {
      PageQueryActionLabel(icon: icon, title: title, isPrimary: isActive)
    }
    .buttonStyle(.plain)
    .help("Show search \(title.lowercased())")
    .accessibilityLabel("Search \(title.lowercased())")
    .accessibilityAddTraits(isActive ? .isSelected : [])
  }

  private var rewindMoreMenu: some View {
    Menu {
      Button {
        NotificationCenter.default.post(name: .navigateToRewindSettings, object: nil)
      } label: {
        Label("Rewind settings…", systemImage: "gearshape")
      }
    } label: {
      PageQueryActionLabel(icon: "ellipsis", title: "More")
    }
    .menuStyle(.borderlessButton)
    .menuIndicator(.hidden)
    .fixedSize()
    .help("More Rewind actions")
    .accessibilityLabel("More Rewind actions")
    .accessibilityIdentifier("rewind-more-actions")
  }

  /// The switch still owns the capture action, but the surrounding control names its state so it
  /// cannot be mistaken for an unlabeled status light. The health-specific help preserves the
  /// reason when capture is paused or recovering.
  private var captureStateControl: some View {
    HStack(spacing: OmiSpacing.xs) {
      Text(captureStateLabel)
        .scaledFont(size: OmiType.caption, weight: .semibold)
        .foregroundStyle(Ink.primary)
        .lineLimit(1)
        .accessibilityHidden(true)
      rewindToggle
    }
    .padding(.horizontal, OmiSpacing.sm)
    .frame(height: QueryShellLayout.chipHeight)
    .background {
      Capsule(style: .continuous)
        .fill(Ink.rowFill)
        .overlay { Capsule(style: .continuous).stroke(Ink.separator, lineWidth: 1) }
    }
    .contentShape(Capsule(style: .continuous))
    .help(captureStateHelp)
  }

  /// The knob shows the setting (right = capture enabled); the label shows reality.
  /// "Off" therefore only ever appears next to a left knob — when capture is enabled
  /// but health reports it not flowing, the label names the failure instead, or the
  /// control reads as contradicting itself (red pill, knob right, "Capture Off").
  private var captureStateLabel: String {
    switch screenCaptureHealth {
    case .active: return "Capture On"
    case .temporarilyUnavailable: return "Capture Paused"
    case .recovering: return "Capture Recovering"
    case .stopped: return isMonitoring ? "Capture Stopped" : "Capture Off"
    }
  }

  private var captureStateHelp: String {
    "\(screenCaptureHealth.statusText). Click to turn screen capture \(isMonitoring ? "off" : "on")."
  }

  private var unifiedTopBarControls: some View {
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

      rewindMoreMenu

      captureStateControl
    }
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
  @ViewBuilder
  private func fullScreenResultsView(width: CGFloat) -> some View {
    if brainDestination != nil {
      GeometryReader { proxy in
        VStack(alignment: .leading, spacing: 0) {
          brainNavigationRow
          rewindSearchResultsPanel(
            width: width,
            availableBodyHeight: max(
              0,
              proxy.size.height - BrainSectionPageMetrics.navigationHeight
                - RewindSearchLayout.panelHeaderHeight - RewindSearchLayout.panelGap
                - RewindSearchLayout.shadowMargin
            )
          )
        }
        .frame(width: width, alignment: .top)
        .inkGlassPanel(cornerRadius: RewindSearchLayout.panelCornerRadius, shadow: .ambient)
        .padding(.top, RewindSearchLayout.panelGap)
        .frame(maxWidth: .infinity, alignment: .top)
      }
    } else {
      RewindSearchResultsSurface(
        groups: viewModel.groupedSearchResults,
        query: viewModel.activeSearchQuery ?? "",
        totalScreenshots: viewModel.totalScreenshotCount,
        selectedIndex: $selectedGroupIndex,
        panelWidth: width,
        onOpen: openSearchResult
      )
      .onChange(of: selectedGroupIndex) { _, _ in
        invalidatePendingFrameLoad()
      }
    }
  }

  private func rewindSearchResultsPanel(
    width: CGFloat,
    availableBodyHeight: CGFloat
  ) -> some View {
    RewindSearchResultsPanel(
      groups: viewModel.groupedSearchResults,
      query: viewModel.activeSearchQuery ?? "",
      totalScreenshots: viewModel.totalScreenshotCount,
      selectedIndex: $selectedGroupIndex,
      panelWidth: width,
      availableBodyHeight: availableBodyHeight,
      onOpen: openSearchResult
    )
    .onChange(of: selectedGroupIndex) { _, _ in
      invalidatePendingFrameLoad()
    }
  }

  private func openSearchResult(_ groupIndex: Int) {
    selectedGroupIndex = groupIndex
    currentIndex = 0
    searchViewMode = .timeline
    let groups = viewModel.groupedSearchResults
    if groups.indices.contains(groupIndex) {
      viewModel.alignSelectedDay(to: groups[groupIndex].startTime)
      trackWindow.center(on: groups[groupIndex].startTime.timeIntervalSince1970)
      viewModel.rememberTimelineWindow(
        from: trackWindow.start,
        to: trackWindow.start + trackWindow.span
      )
    }
    scheduleLoadCurrentFrame()
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
      placeholder: brainDestination == nil
        ? RewindSearchMetrics.placeholder : "Search screen history…",
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
    VStack(alignment: .leading, spacing: OmiSpacing.sm) {
      DatePicker(
        "",
        selection: Binding(
          get: { viewModel.selectedDate },
          set: { newDate in
            // Keep one all-time source; the picker moves its playhead instead of replacing it with
            // a day-bounded query.
            guard !Calendar.current.isDate(newDate, inSameDayAs: viewModel.selectedDate) else { return }
            seekToCapturedDay(newDate)
          }
        ),
        displayedComponents: [.date]
      )
      .datePickerStyle(.graphical)
      .labelsHidden()

      historyReach
    }
    .padding(14)
  }

  /// How far back Rewind actually goes, and one click to get there.
  ///
  /// **A calendar alone cannot answer "what do I still have".** Most days in it hold no capture —
  /// the Mac was asleep, permission was off, or the retention window has already deleted them — and
  /// stepping day by day through a month of empty ones to find the oldest is not navigation. These
  /// controls move to the next day that *holds* capture, and the line above them states the real
  /// span so the user never has to discover the boundary by hitting it.
  @ViewBuilder
  private var historyReach: some View {
    let oldest = viewModel.oldestCapturedDay
    let older = viewModel.capturedDay(before: viewModel.selectedDate)
    let newer = viewModel.capturedDay(after: viewModel.selectedDate)
    // "There is nowhere older to go": either the survey found no oldest day, or the day we are on is
    // it. Bound once because the button below asks the same question twice — for `disabled` and for
    // the dimming that shows it — and the two spellings drifting apart is a control that looks live
    // and does nothing. It replaces `oldest == nil || …isDate(oldest!, …)`, which could not actually
    // trap (`||` short-circuits before the unwrap) but made every reader re-derive that.
    let atOldestCapture = oldest.map { Calendar.current.isDate($0, inSameDayAs: viewModel.selectedDate) } ?? true

    VStack(alignment: .leading, spacing: OmiSpacing.xs) {
      // `nil` here is "not surveyed yet", not "nothing captured" — the two claims are different and
      // the second one is a lie until the walk has finished.
      //
      // Two lines, two levels, and **on glass that separation is weight rather than a third colour
      // rung.** The note under the span was set on the third rung, which measures under WCAG AA on
      // this panel — the same illegibility class as the onboarding copy at 2.17:1. Promoting it to
      // `Ink.secondary` alone would have flattened the pair into one voice, so the span it explains
      // takes the rung above it and the medium weight instead: the answer reads first, its footnote
      // second, and both are legible.
      Text(RewindHistoryReach.spanLabel(days: viewModel.capturedDays, surveyed: viewModel.didSurveyHistory))
        .scaledFont(size: OmiType.caption, weight: .medium)
        .foregroundColor(Ink.primary)

      Text(RewindHistoryReach.retentionNote(retentionDays: retentionDays))
        .scaledFont(size: OmiType.caption)
        .foregroundColor(Ink.secondary)

      HStack(spacing: OmiSpacing.sm) {
        Button {
          if let older { seekToCapturedDay(older) }
        } label: {
          Label("Older", systemImage: "chevron.left")
            .scaledFont(size: OmiType.caption)
        }
        .buttonStyle(.plain)
        .disabled(older == nil)
        .opacity(older == nil ? 0.35 : 1)

        Button {
          if let newer { seekToCapturedDay(newer) }
        } label: {
          Label("Newer", systemImage: "chevron.right")
            .scaledFont(size: OmiType.caption)
        }
        .buttonStyle(.plain)
        .disabled(newer == nil)
        .opacity(newer == nil ? 0.35 : 1)

        Spacer(minLength: 0)

        Button {
          if let oldest { seekToCapturedDay(oldest) }
        } label: {
          Text("Oldest capture")
            .scaledFont(size: OmiType.caption)
        }
        .buttonStyle(.plain)
        .disabled(atOldestCapture)
        .opacity(atOldestCapture ? 0.35 : 1)
      }
      .foregroundColor(Ink.primary)
    }
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
        // Where the picture lands, asked of `RewindStageFit` rather than recomputed here. The chrome
        // overlay below asks the same type the same question about the same frame, and two copies of
        // this arithmetic drifting apart is a control that no longer sits on the picture it belongs
        // to — which is the defect that put the type there.
        let displaySize = RewindStageFit.pictureRect(image: image.size, in: geometry.size).size

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
            // **The stage is a preview, not the frame.** It is fit to whatever the pane happens to
            // be, which on a half-width window is a fraction of a 5120pt capture — enough to
            // recognise the moment and not enough to read a line of it, which is the whole reason
            // someone scrubbed to it. Clicking opens the real thing in Quick Look, at full
            // resolution, with the rest of the day's frames behind the arrow keys.
            .contentShape(frameShape)
            .onTapGesture { openCurrentFrameFullSize() }
            .help("Open this frame in Quick Look")
            .contextMenu { Button("Quick Look", action: openCurrentFrameFullSize) }
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
    .padding(.horizontal, RewindStageFit.horizontalInset)
    .padding(.vertical, RewindStageFit.verticalInset)
    .overlay {
      RewindStageChrome(
        screenshots: activeScreenshots,
        currentIndex: currentIndex,
        // The overlay lands on the *padded* stage, so the chrome re-derives the picture's rect in
        // that space. It needs the frame's shape to do it.
        imageSize: currentImage?.size,
        window: trackWindow,
        onSelect: { seekToIndex($0) },
        showsDatePicker: $showDatePicker,
        datePicker: AnyView(dayPicker))
    }
  }

  private var frameShape: RoundedRectangle {
    RoundedRectangle(cornerRadius: 10, style: .continuous)
  }

  /// Hand the whole visible run to Quick Look, positioned on the frame that is on the stage.
  ///
  /// The run and not the single frame, because Quick Look steps left and right through whatever it
  /// is given — so this makes the arrow keys walk the same sequence the track does, which is the
  /// behaviour someone who opened a frame from a timeline already expects.
  private func openCurrentFrameFullSize() {
    let screenshots = activeScreenshots
    guard screenshots.indices.contains(currentIndex) else { return }
    let frames = screenshots.map { QuickLookFrame(screenshot: $0) }
    ScreenFrameQuickLook.shared.present(
      frames, startingAt: frames[currentIndex].id)
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
        historyRange: viewModel.historyRange,
        currentIndex: currentIndex,
        searchResultIndices: viewModel.activeSearchQuery != nil && searchViewMode != .timeline
          ? Set(searchResultIndices) : nil,
        window: trackWindow,
        onSelect: { seekToIndex($0) },
        onScroll: { handleTimelineScroll(deltaX: $0, deltaY: $1) })
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
    guard requestedIndex >= 0, requestedIndex < screenshots.count else { return }

    isLoadingFrame = true

    // Try to load the requested frame. Scrubbing can launch several loads;
    // only the newest request is allowed to update visible state.
    if let image = await tryLoadFrame(at: requestedIndex) {
      guard isCurrentFrameLoad(index: requestedIndex, requestID: requestID, sourceToken: sourceToken) else { return }
      currentImage = image
      viewModel.selectScreenshot(screenshots[requestedIndex])
      if viewModel.activeSearchQuery == nil {
        viewModel.alignSelectedDay(to: screenshots[requestedIndex].timestamp)
      }
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
    guard let newIndex = RewindTimelineNavigation.clampedIndex(index, screenshots: screenshots) else { return }
    guard newIndex != currentIndex else { return }

    currentIndex = newIndex
    trackWindow.reveal(screenshots[newIndex].timestamp.timeIntervalSince1970)
    scheduleLoadCurrentFrame()
  }

  private func seekToCapturedDay(_ date: Date) {
    viewModel.chooseDate(date)
    let calendar = Calendar.current
    let start = calendar.startOfDay(for: date)
    let end = calendar.date(byAdding: .day, value: 1, to: start) ?? start.addingTimeInterval(24 * 3600)
    let span = max(trackWindow.span, end.timeIntervalSince(start))
    let middle = start.timeIntervalSince1970 + end.timeIntervalSince(start) / 2
    trackWindow.set(start: middle - span / 2, span: span)
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

        // "Every second" was never the interval: `RewindSettings.captureInterval` defaults to 3s and
        // `effectiveCaptureInterval` triples it on battery. Both this line and the onboarding
        // disclosure now say the same true thing.
        Text(
          "Screenshots will appear here as you use your Mac.\nRewind captures your screen every few seconds."
        )
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
            .foregroundColor(PageGlass.primaryActionLabel)
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
    TransparentWindowStatusPanel {
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
  }

  private func errorView(_: String) -> some View {
    TransparentWindowStatusPanel {
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
          .foregroundColor(PageGlass.primaryActionLabel)
          .padding(.horizontal, OmiSpacing.xl)
          .padding(.vertical, OmiSpacing.sm)
          .background(Ink.primary)
          .cornerRadius(OmiChrome.elementRadius)
        }
        .buttonStyle(.plain)
      }
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
      appState.toggleTranscription()
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

#if canImport(PreviewsMacros)
  #Preview {
    RewindPage()
      .frame(width: 1000, height: 700)
  }
#endif
