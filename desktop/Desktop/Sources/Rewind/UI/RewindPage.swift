import SwiftUI
import AppKit
import AVKit

/// Main Rewind page - Timeline-first view with integrated search
/// The timeline is the primary interface, with search results highlighted inline
struct RewindPage: View {
    var appState: AppState? = nil

    @StateObject private var viewModel = RewindViewModel()
    @ObservedObject private var audioLevels = AudioLevelMonitor.shared
    @ObservedObject private var recordingTimer = RecordingTimer.shared
    @ObservedObject private var liveTranscript = LiveTranscriptMonitor.shared

    @State private var currentIndex: Int = 0
    @State private var currentImage: NSImage?
    @State private var isLoadingFrame = false
    @State private var showDatePicker = false

    @State private var searchViewMode: SearchViewMode? = nil
    @State private var selectedGroupIndex: Int = 0
    @FocusState private var isSearchFocused: Bool

    // Monitoring toggle state
    @State private var isMonitoring = false
    @State private var isTogglingMonitoring = false
    @AppStorage("screenAnalysisEnabled") private var screenAnalysisEnabled = true

    // Recording animation state
    @State private var isRecordingPulsing = false
    @State private var isSavingPulsing = false

    // Expanded transcript state
    @State private var isTranscriptExpanded = false
    @State private var savedTranscriptSegments: [SpeakerSegment] = []

    // Finish conversation button state
    @State private var isFinishing = false
    @State private var showSavedSuccess = false
    @State private var showDiscarded = false
    @State private var showError = false

    // Speaker naming state
    @State private var showNameSpeakerSheet = false
    @State private var selectedSpeakerSegment: SpeakerSegment? = nil

    // Rewind intro video (first-time experience)
    @AppStorage("hasSeenRewindIntro") private var hasSeenRewindIntro = false

    enum SearchViewMode {
        case results  // Full-screen search results
        case timeline // Timeline with search highlights
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
                    // Recording bar (always visible when appState exists)
                    if let appState = appState {
                        rewindRecordingBar(appState: appState)
                    }

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
            }

            // Rewind intro video overlay (first-time experience)
            if !hasSeenRewindIntro {
                rewindIntroOverlay
            }
        }
        .task {
            await viewModel.loadInitialData()
        }
        .onAppear {
            isMonitoring = ProactiveAssistantsPlugin.shared.isMonitoring
        }
        .onReceive(NotificationCenter.default.publisher(for: .assistantMonitoringStateDidChange)) { _ in
            isMonitoring = ProactiveAssistantsPlugin.shared.isMonitoring
        }
        .onChange(of: viewModel.screenshots) { oldScreenshots, newScreenshots in
            // Try to preserve position on the same screenshot the user was viewing
            if !oldScreenshots.isEmpty,
               currentIndex < oldScreenshots.count,
               let currentId = oldScreenshots[currentIndex].id,
               let newIndex = newScreenshots.firstIndex(where: { $0.id == currentId }) {
                // Same screenshot found in new array - adjust index
                currentIndex = newIndex
                // No need to reload frame - it's the same screenshot
            } else if !newScreenshots.isEmpty {
                // Can't find the current screenshot (first load, or it was deleted)
                if currentIndex >= newScreenshots.count {
                    currentIndex = 0
                }
                selectedGroupIndex = 0
                Task { await loadCurrentFrame() }
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
        }
        .onChange(of: appState?.isTranscribing) { _, newValue in
            // When recording stops, snapshot the transcript so it survives the clear
            if newValue != true && isTranscriptExpanded && !liveTranscript.segments.isEmpty {
                savedTranscriptSegments = liveTranscript.segments
            }
        }
        // Global keyboard handlers
        .onKeyPress(.escape) {
            // Expanded transcript → collapse
            if isTranscriptExpanded {
                isTranscriptExpanded = false
                savedTranscriptSegments = []
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
            if searchViewMode != .results {
                previousFrame()
                return .handled
            }
            return .ignored
        }
        .onKeyPress(.rightArrow) {
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
        let framesToMove = Int(-delta * sensitivity)

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
        VStack(spacing: 16) {
            Spacer()

            Image(systemName: "magnifyingglass")
                .scaledFont(size: 48)
                .foregroundColor(.white.opacity(0.3))

            if viewModel.isSearching {
                Text("Searching...")
                    .scaledFont(size: 16, weight: .medium)
                    .foregroundColor(.white.opacity(0.6))
            } else {
                Text("No results found")
                    .scaledFont(size: 16, weight: .medium)
                    .foregroundColor(.white.opacity(0.6))

                Text("Try a different search term")
                    .scaledFont(size: 13)
                    .foregroundColor(.white.opacity(0.4))
            }

            Spacer()
        }
    }

    // MARK: - Rewind Toggle

    private var rewindToggle: some View {
        ZStack {
            Capsule()
                .fill(isMonitoring ? OmiColors.purplePrimary : Color.red)
                .frame(width: 36, height: 20)

            Circle()
                .fill(Color.white)
                .frame(width: 16, height: 16)
                .shadow(color: .black.opacity(0.15), radius: 1, x: 0, y: 1)
                .offset(x: isMonitoring ? 8 : -8)
                .animation(.easeInOut(duration: 0.15), value: isMonitoring)
        }
        .opacity(isTogglingMonitoring ? 0.5 : 1.0)
        .overlay {
            if isTogglingMonitoring {
                ProgressView()
                    .scaleEffect(0.5)
            }
        }
        .onTapGesture {
            if !isTogglingMonitoring {
                toggleMonitoring(enabled: !isMonitoring)
            }
        }
        .help(isMonitoring ? "Rewind is capturing - click to stop" : "Rewind is off - click to start capturing")
    }

    private func toggleMonitoring(enabled: Bool) {
        if enabled && !ProactiveAssistantsPlugin.shared.hasScreenRecordingPermission {
            isMonitoring = false
            ScreenCaptureService.requestAllScreenCapturePermissions()
            ProactiveAssistantsPlugin.shared.openScreenRecordingPreferences()
            return
        }

        isTogglingMonitoring = true
        isMonitoring = enabled

        AnalyticsManager.shared.settingToggled(setting: "monitoring", enabled: enabled)

        screenAnalysisEnabled = enabled
        AssistantSettings.shared.screenAnalysisEnabled = enabled

        // Also toggle audio transcription
        if let appState = appState {
            if enabled && !appState.isTranscribing {
                appState.startTranscription()
            } else if !enabled && appState.isTranscribing {
                appState.stopTranscription()
            }
        }

        if enabled {
            ProactiveAssistantsPlugin.shared.startMonitoring { success, _ in
                DispatchQueue.main.async {
                    isTogglingMonitoring = false
                    if !success {
                        isMonitoring = false
                    }
                }
            }
        } else {
            ProactiveAssistantsPlugin.shared.stopMonitoring()
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.3) {
                isTogglingMonitoring = false
            }
        }
    }

    // MARK: - Unified Top Bar (persistent search field)

    private var unifiedTopBar: some View {
        HStack(spacing: 12) {
            // Left side: Back button (search timeline mode) or Rewind logo (other modes)
            if isInSearchMode && searchViewMode == .timeline {
                Button {
                    searchViewMode = .results
                } label: {
                    Image(systemName: "chevron.left")
                        .scaledFont(size: 12, weight: .semibold)
                        .foregroundColor(.white.opacity(0.7))
                        .frame(width: 28, height: 28)
                        .background(Color.white.opacity(0.1))
                        .clipShape(Circle())
                }
                .buttonStyle(.plain)
                .help("Back to results")
            } else {
                // Rewind title
                HStack(spacing: 8) {
                    Text("Rewind")
                        .scaledFont(size: 16, weight: .semibold)
                        .foregroundColor(.white)

                    // Global hotkey hint
                    HStack(spacing: 2) {
                        Text("⌘")
                        Text("⌥")
                        Text("R")
                    }
                    .scaledFont(size: 10, weight: .medium, design: .rounded)
                    .foregroundColor(.white.opacity(0.4))
                    .padding(.horizontal, 6)
                    .padding(.vertical, 3)
                    .background(Color.white.opacity(0.1))
                    .cornerRadius(4)
                    .help("Press ⌘⌥R from anywhere to open Rewind")
                }
            }

            // Search field + date picker - always present
            searchField(showResultsCount: isInSearchMode)
            datePickerControls

            // Right side controls depend on mode
            if isInSearchMode {
                // View mode toggle for search
                HStack(spacing: 2) {
                    Button {
                        searchViewMode = .results
                        if !viewModel.screenshots.isEmpty {
                            currentIndex = 0
                            Task { await loadCurrentFrame() }
                        }
                    } label: {
                        Image(systemName: "list.bullet")
                            .scaledFont(size: 11)
                            .foregroundColor(searchViewMode == .results ? .black : .white.opacity(0.5))
                            .frame(width: 28, height: 24)
                            .background(searchViewMode == .results ? Color.white : Color.clear)
                            .cornerRadius(4)
                    }
                    .buttonStyle(.plain)
                    .help("List view")

                    Button {
                        if searchViewMode != .timeline && !viewModel.screenshots.isEmpty {
                            currentIndex = 0
                            Task { await loadCurrentFrame() }
                        }
                        searchViewMode = .timeline
                    } label: {
                        Image(systemName: "timeline.selection")
                            .scaledFont(size: 11)
                            .foregroundColor(searchViewMode == .timeline ? .black : .white.opacity(0.5))
                            .frame(width: 28, height: 24)
                            .background(searchViewMode == .timeline ? Color.white : Color.clear)
                            .cornerRadius(4)
                    }
                    .buttonStyle(.plain)
                    .help("Timeline view")
                }
                .padding(2)
                .background(Color.white.opacity(0.1))
                .cornerRadius(6)
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
                    .scaledFont(size: 12)
                    .foregroundColor(.white.opacity(0.6))
            }
            .buttonStyle(.plain)
            .help("Rewind Settings")

            // Rewind on/off toggle (controls both screen + audio)
            rewindToggle
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 10)
        .background(OmiColors.backgroundTertiary.opacity(0.8))
    }

    // MARK: - Timeline Content Body (without top bar)

    private var timelineContentBody: some View {
        VStack(spacing: 0) {
            // Main frame display
            Spacer()
            frameDisplay
            Spacer()

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
                                Task { await loadCurrentFrame() }
                            }
                        )
                        .id(groupIndex)
                    }
                }
                .padding(.vertical, 8)
            }
            .onChange(of: selectedGroupIndex) { _, newIndex in
                withAnimation {
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

    // MARK: - Timeline with Search

    private var timelineWithSearch: some View {
        VStack(spacing: 0) {
            // Frame display
            Spacer()
            frameDisplay
            Spacer()

            // Timeline and controls
            bottomControls
        }
    }

    // MARK: - Unified Search Field

    private func searchField(showResultsCount: Bool = false) -> some View {
        HStack(spacing: 8) {
            Image(systemName: "magnifyingglass")
                .scaledFont(size: 12)
                .foregroundColor(isSearchFocused ? OmiColors.purplePrimary : .white.opacity(0.5))

            TextField("Search your screen history...", text: $viewModel.searchQuery)
                .textFieldStyle(.plain)
                .scaledFont(size: 13)
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
                        .scaledFont(size: 11)
                        .foregroundColor(.white.opacity(0.5))
                } else {
                    Text("\(groups.count) groups (\(total) total)")
                        .scaledFont(size: 11)
                        .foregroundColor(.white.opacity(0.5))
                }
            }

            if !viewModel.searchQuery.isEmpty {
                Button {
                    viewModel.searchQuery = ""
                    searchViewMode = nil
                } label: {
                    Image(systemName: "xmark.circle.fill")
                        .scaledFont(size: 12)
                        .foregroundColor(.white.opacity(0.5))
                }
                .buttonStyle(.plain)
            }
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 8)
        .frame(maxWidth: 400)
        .background(
            RoundedRectangle(cornerRadius: 8)
                .fill(Color.white.opacity(0.1))
                .overlay(
                    RoundedRectangle(cornerRadius: 8)
                        .stroke(isSearchFocused ? OmiColors.purplePrimary.opacity(0.5) : Color.clear, lineWidth: 1)
                )
        )
    }

    // MARK: - Date Picker Controls

    private var datePickerControls: some View {
        Button {
            showDatePicker.toggle()
        } label: {
            HStack(spacing: 6) {
                Text(viewModel.selectedDate.formatted(.dateTime.month().day().year()))
                    .scaledFont(size: 12)
                    .foregroundColor(.white)
                Image(systemName: "chevron.up.chevron.down")
                    .scaledFont(size: 8, weight: .semibold)
                    .foregroundColor(.white.opacity(0.5))
            }
            .padding(.horizontal, 10)
            .padding(.vertical, 6)
            .background(Color.white.opacity(0.15))
            .cornerRadius(6)
        }
        .buttonStyle(.plain)
        .popover(isPresented: $showDatePicker) {
            DatePicker(
                "",
                selection: Binding(
                    get: { viewModel.selectedDate },
                    set: { newDate in
                        Task { await viewModel.filterByDate(newDate) }
                    }
                ),
                displayedComponents: [.date]
            )
            .datePickerStyle(.graphical)
            .labelsHidden()
            .padding(8)
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
            } else if let image = currentImage, image.size.height > 0, image.size.width > 0, geometry.size.height > 0, geometry.size.width > 0 {
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
                        .cornerRadius(4)
                        .shadow(color: .black.opacity(0.3), radius: 8)

                    // Search highlight overlays with explicit frame
                    if let query = viewModel.activeSearchQuery,
                       currentIndex < activeScreenshots.count {
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
                VStack(spacing: 6) {
                    Image(systemName: "photo")
                        .scaledFont(size: 24)
                        .foregroundColor(.white.opacity(0.3))
                    Text("No frame")
                        .scaledFont(size: 11)
                        .foregroundColor(.white.opacity(0.4))
                }
                .frame(width: geometry.size.width, height: geometry.size.height)
            }
        }
        .padding(.horizontal, 12)
    }

    // MARK: - Bottom Controls (Compact - all on one line)

    private var bottomControls: some View {
        let screenshots = activeScreenshots

        return VStack(spacing: 8) {
            // Timeline bar
            InteractiveTimelineBar(
                screenshots: screenshots,
                currentIndex: currentIndex,
                searchResultIndices: viewModel.activeSearchQuery != nil && searchViewMode != .timeline ? Set(searchResultIndices) : nil,
                onSelect: { index in
                    seekToIndex(index)
                }
            )

            // Compact control bar: legend | position/timestamp | scroll hint
            HStack(spacing: 12) {
                // Left: Legend indicators
                HStack(spacing: 12) {
                    // Current indicator
                    HStack(spacing: 4) {
                        RoundedRectangle(cornerRadius: 1)
                            .fill(Color.white)
                            .frame(width: 8, height: 8)
                        Text("current")
                            .scaledFont(size: 9)
                            .foregroundColor(.white.opacity(0.4))
                    }

                    // Match indicator (only when searching)
                    if viewModel.activeSearchQuery != nil && !searchResultIndices.isEmpty {
                        HStack(spacing: 4) {
                            RoundedRectangle(cornerRadius: 1)
                                .fill(Color.yellow.opacity(0.8))
                                .frame(width: 8, height: 8)
                            Text("match")
                                .scaledFont(size: 9)
                                .foregroundColor(.white.opacity(0.4))
                        }
                    }
                }

                Spacer()

                // Right: Position and timestamp
                if currentIndex < screenshots.count {
                    let screenshot = screenshots[currentIndex]
                    HStack(spacing: 8) {
                        Text("\(currentIndex + 1)/\(screenshots.count)")
                            .scaledFont(size: 10, design: .monospaced)
                            .foregroundColor(.white.opacity(0.5))
                        Text(screenshot.formattedDateCompact)
                            .scaledFont(size: 10, design: .monospaced)
                            .foregroundColor(.white.opacity(0.7))
                    }
                }

                // Scroll hint
                Text("scroll to navigate")
                    .scaledFont(size: 9)
                    .foregroundColor(.white.opacity(0.3))
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 8)
        }
        .padding(.bottom, 12)
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

    private func loadCurrentFrame() async {
        let screenshots = activeScreenshots
        guard currentIndex < screenshots.count else { return }

        isLoadingFrame = true

        // Try to load the current frame
        if let image = await tryLoadFrame(at: currentIndex) {
            currentImage = image
            viewModel.selectScreenshot(screenshots[currentIndex])
            isLoadingFrame = false
            return
        }

        // Frame failed to load (likely in an unfinalized video chunk).
        // Do NOT move currentIndex — keep the user's position and show the last valid image.
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
                logError("RewindPage: Loaded invalid image at index \(index) - size=\(image.size), videoChunk=\(screenshot.videoChunkPath ?? "nil"), frameOffset=\(screenshot.frameOffset ?? -1)")
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
            logError("RewindPage: Failed to load frame at index \(index): \(error.localizedDescription), videoChunk=\(screenshot.videoChunkPath ?? "nil"), frameOffset=\(screenshot.frameOffset ?? -1)")
            return nil
        } catch {
            logError("RewindPage: Failed to load frame at index \(index): \(error.localizedDescription), videoChunk=\(screenshot.videoChunkPath ?? "nil"), frameOffset=\(screenshot.frameOffset ?? -1)")
            return nil
        }
    }

    private func seekToIndex(_ index: Int) {
        let screenshots = activeScreenshots
        let newIndex = max(0, min(index, screenshots.count - 1))
        guard newIndex != currentIndex else { return }

        currentIndex = newIndex
        Task { await loadCurrentFrame() }
    }

    private func nextFrame() {
        seekToIndex(currentIndex - 1) // Screenshots are newest first
    }

    private func previousFrame() {
        seekToIndex(currentIndex + 1)
    }


    // MARK: - Rewind Intro Video

    private var rewindIntroOverlay: some View {
        ZStack {
            Color.black.opacity(0.85)
                .ignoresSafeArea()

            VStack(spacing: 20) {
                RewindIntroVideoView()
                    .frame(maxWidth: 700, maxHeight: 394) // 16:9 aspect
                    .clipShape(RoundedRectangle(cornerRadius: 12))
                    .shadow(color: OmiColors.purplePrimary.opacity(0.3), radius: 20)

                Button(action: {
                    withAnimation(.easeOut(duration: 0.25)) {
                        hasSeenRewindIntro = true
                    }
                }) {
                    Text("Get Started")
                        .scaledFont(size: 15, weight: .semibold)
                        .foregroundColor(.white)
                        .padding(.horizontal, 32)
                        .padding(.vertical, 10)
                        .background(OmiColors.purplePrimary)
                        .clipShape(RoundedRectangle(cornerRadius: 10))
                }
                .buttonStyle(.plain)

                Button(action: {
                    withAnimation(.easeOut(duration: 0.25)) {
                        hasSeenRewindIntro = true
                    }
                }) {
                    Text("Skip")
                        .scaledFont(size: 13)
                        .foregroundColor(.white.opacity(0.5))
                }
                .buttonStyle(.plain)
            }
        }
        .transition(.opacity)
    }

    // MARK: - Empty States

    private var emptyState: some View {
        VStack(spacing: 16) {
            ZStack {
                Circle()
                    .fill(OmiColors.purplePrimary.opacity(0.1))
                    .frame(width: 80, height: 80)

                Image(systemName: "clock.arrow.circlepath")
                    .scaledFont(size: 36)
                    .foregroundColor(OmiColors.purplePrimary.opacity(0.6))
            }

            Text("No Screenshots Yet")
                .scaledFont(size: 20, weight: .semibold)
                .foregroundColor(.white)

            Text("Screenshots will appear here as you use your Mac.\nRewind captures your screen every second.")
                .scaledFont(size: 14)
                .foregroundColor(.white.opacity(0.6))
                .multilineTextAlignment(.center)

            HStack(spacing: 8) {
                Image(systemName: "lightbulb.fill")
                    .foregroundColor(.yellow)
                Text("Tip: Use search to find anything you've seen on screen")
                    .scaledFont(size: 12)
                    .foregroundColor(.white.opacity(0.7))
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 10)
            .background(Color.white.opacity(0.1))
            .cornerRadius(8)
            .padding(.top, 8)
        }
    }

    private var recoveryBanner: some View {
        HStack(spacing: 12) {
            Image(systemName: "exclamationmark.triangle.fill")
                .foregroundColor(.orange)
                .scaledFont(size: 16)

            VStack(alignment: .leading, spacing: 2) {
                Text("Database Recovered")
                    .scaledFont(size: 13, weight: .semibold)
                    .foregroundColor(.white)

                if viewModel.recoveredRecordCount > 0 {
                    Text("\(viewModel.recoveredRecordCount) screenshots recovered from corrupted database")
                        .scaledFont(size: 11)
                        .foregroundColor(.white.opacity(0.7))
                } else {
                    Text("Database was corrupted and has been reset. Your video files are intact.")
                        .scaledFont(size: 11)
                        .foregroundColor(.white.opacity(0.7))
                }
            }

            Spacer()

            if viewModel.recoveredRecordCount == 0 {
                Button {
                    Task { await rebuildDatabase() }
                } label: {
                    Text("Rebuild Index")
                        .scaledFont(size: 11, weight: .medium)
                        .foregroundColor(OmiColors.textPrimary)
                        .padding(.horizontal, 10)
                        .padding(.vertical, 5)
                        .background(Color.white)
                        .cornerRadius(4)
                }
                .buttonStyle(.plain)
                .disabled(viewModel.isRebuilding)
            }

            Button {
                withAnimation(.easeOut(duration: 0.2)) {
                    viewModel.dismissRecoveryBanner()
                }
            } label: {
                Image(systemName: "xmark")
                    .scaledFont(size: 12, weight: .medium)
                    .foregroundColor(.white.opacity(0.6))
            }
            .buttonStyle(.plain)
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 10)
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
            try await RewindIndexer.shared.rebuildFromVideoFiles { progress in
                Task { @MainActor in
                    viewModel.rebuildProgress = progress
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
        VStack(spacing: 12) {
            ProgressView()
                .progressViewStyle(.circular)
                .scaleEffect(1.2)
                .tint(.white)

            Text("Loading screenshots...")
                .scaledFont(size: 14)
                .foregroundColor(.white.opacity(0.6))
        }
    }

    private func errorView(_ message: String) -> some View {
        VStack(spacing: 16) {
            ZStack {
                Circle()
                    .fill(OmiColors.error.opacity(0.1))
                    .frame(width: 80, height: 80)

                Image(systemName: "exclamationmark.triangle")
                    .scaledFont(size: 36)
                    .foregroundColor(OmiColors.error)
            }

            Text("Failed to Load Screenshots")
                .scaledFont(size: 18, weight: .semibold)
                .foregroundColor(.white)

            Text(message)
                .scaledFont(size: 14)
                .foregroundColor(.white.opacity(0.6))

            Button {
                Task { await viewModel.loadInitialData() }
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
            }
            .buttonStyle(.plain)
        }
    }

    // MARK: - Expanded Transcript View

    @AppStorage("recordingNotesPanelRatio") private var panelRatio: Double = 0.65
    private let minPanelWidth: CGFloat = 200

    /// The segments to display — live if available, otherwise the saved snapshot
    private var displaySegments: [SpeakerSegment] {
        if !liveTranscript.segments.isEmpty {
            return liveTranscript.segments
        }
        return savedTranscriptSegments
    }

    private var expandedTranscriptView: some View {
        VStack(spacing: 0) {
            // Show a back bar only when the recording bar is not visible
            if appState?.isTranscribing != true && appState?.isSavingConversation != true {
                HStack(spacing: 8) {
                    Button {
                        withAnimation(.easeInOut(duration: 0.2)) {
                            isTranscriptExpanded = false
                            savedTranscriptSegments = []
                        }
                    } label: {
                        HStack(spacing: 4) {
                            Image(systemName: "chevron.up")
                                .scaledFont(size: 11, weight: .semibold)
                            Text("Back to Rewind")
                                .scaledFont(size: 13, weight: .medium)
                        }
                        .foregroundColor(.white.opacity(0.7))
                        .padding(.horizontal, 10)
                        .padding(.vertical, 6)
                        .background(Color.white.opacity(0.1))
                        .cornerRadius(6)
                    }
                    .buttonStyle(.plain)

                    Spacer()
                }
                .padding(.horizontal, 16)
                .padding(.vertical, 8)
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
                        if displaySegments.isEmpty {
                            VStack(spacing: 16) {
                                Image(systemName: "waveform")
                                    .scaledFont(size: 48)
                                    .foregroundColor(OmiColors.textTertiary)
                                    .opacity(0.5)
                                Text("Listening...")
                                    .scaledFont(size: 16, weight: .medium)
                                    .foregroundColor(OmiColors.textSecondary)
                                Text("Start speaking and your transcript will appear here")
                                    .scaledFont(size: 14)
                                    .foregroundColor(OmiColors.textTertiary)
                                    .multilineTextAlignment(.center)
                            }
                            .frame(maxWidth: .infinity, maxHeight: .infinity)
                            .padding(32)
                        } else {
                            LiveTranscriptView(
                                segments: displaySegments,
                                speakerNames: speakerNames,
                                onSpeakerTapped: { segment in
                                    selectedSpeakerSegment = segment
                                    showNameSpeakerSheet = true
                                }
                            )
                        }
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
        .dismissableSheet(isPresented: $showNameSpeakerSheet) {
            if let segment = selectedSpeakerSegment, let appState = appState {
                LiveNameSpeakerSheet(
                    speakerId: segment.speaker,
                    sampleText: segment.text,
                    people: appState.people,
                    currentPersonId: appState.liveSpeakerPersonMap[segment.speaker],
                    onSave: { personId in
                        appState.liveSpeakerPersonMap[segment.speaker] = personId
                        showNameSpeakerSheet = false
                    },
                    onCreatePerson: { name in
                        return await appState.createPerson(name: name)
                    },
                    onDismiss: {
                        showNameSpeakerSheet = false
                    }
                )
            }
        }
    }

    // MARK: - Recording Bar

    private func rewindRecordingBar(appState: AppState) -> some View {
        HStack(spacing: 12) {
            // Left: always show "Audio" label
            Text("Audio")
                .scaledFont(size: 16, weight: .semibold)
                .foregroundColor(.white)

            // Middle content depends on state
            if appState.isTranscribing {
                // Transcript text + chevron (clickable to expand/collapse)
                Button {
                    withAnimation(.easeInOut(duration: 0.2)) {
                        isTranscriptExpanded.toggle()
                        if !isTranscriptExpanded {
                            savedTranscriptSegments = []
                        }
                    }
                } label: {
                    HStack(spacing: 6) {
                        if let latestText = liveTranscript.latestText, !liveTranscript.isEmpty {
                            Text(latestText)
                                .scaledFont(size: 14)
                                .foregroundColor(OmiColors.textSecondary)
                                .lineLimit(1)
                                .truncationMode(.head)
                                .frame(maxWidth: 260, alignment: .leading)
                        } else {
                            Text("Listening")
                                .scaledFont(size: 14, weight: .medium)
                                .foregroundColor(OmiColors.textPrimary)
                        }
                        Image(systemName: isTranscriptExpanded ? "chevron.up" : "chevron.down")
                            .scaledFont(size: 10, weight: .semibold)
                            .foregroundColor(OmiColors.textTertiary)
                    }
                    .padding(.horizontal, 8)
                    .padding(.vertical, 4)
                    .background(
                        RoundedRectangle(cornerRadius: 6)
                            .fill(OmiColors.backgroundTertiary.opacity(0.5))
                    )
                }
                .buttonStyle(.plain)

                // Audio level waveforms
                HStack(spacing: 16) {
                    HStack(spacing: 6) {
                        Image(systemName: "mic.fill")
                            .scaledFont(size: 12)
                            .foregroundColor(OmiColors.textTertiary)
                        AudioLevelWaveformView(
                            level: audioLevels.microphoneLevel,
                            barCount: 8,
                            isActive: true
                        )
                    }

                    HStack(spacing: 6) {
                        Image(systemName: "speaker.wave.2.fill")
                            .scaledFont(size: 12)
                            .foregroundColor(OmiColors.textTertiary)
                        AudioLevelWaveformView(
                            level: audioLevels.systemLevel,
                            barCount: 8,
                            isActive: true
                        )
                    }
                }

                // Duration
                Text(recordingTimer.formattedDuration)
                    .scaledFont(size: 14, weight: .medium, design: .monospaced)
                    .foregroundColor(OmiColors.textSecondary)
            } else if appState.isSavingConversation {
                // Saving indicator
                ZStack {
                    Circle()
                        .fill(OmiColors.purplePrimary.opacity(0.3))
                        .frame(width: 24, height: 24)
                        .scaleEffect(isSavingPulsing ? 1.5 : 1.0)
                        .opacity(isSavingPulsing ? 0.0 : 0.6)

                    Image(systemName: "arrow.up.circle.fill")
                        .scaledFont(size: 16)
                        .foregroundColor(OmiColors.purplePrimary)
                        .scaleEffect(isSavingPulsing ? 1.1 : 1.0)
                }
                .animation(
                    .easeInOut(duration: 0.8)
                        .repeatForever(autoreverses: true),
                    value: isSavingPulsing
                )
                .onAppear { isSavingPulsing = true }
                .onDisappear { isSavingPulsing = false }

                Text("Saving conversation...")
                    .scaledFont(size: 14, weight: .medium)
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
                    HStack(spacing: 6) {
                        if isFinishing {
                            ProgressView()
                                .scaleEffect(0.5)
                                .frame(width: 12, height: 12)
                        } else if showSavedSuccess {
                            Image(systemName: "checkmark")
                                .scaledFont(size: 12, weight: .bold)
                        } else if showDiscarded {
                            Image(systemName: "xmark")
                                .scaledFont(size: 12, weight: .bold)
                        } else if showError {
                            Image(systemName: "exclamationmark.triangle.fill")
                                .scaledFont(size: 12)
                        }
                        Text(finishButtonText)
                            .scaledFont(size: 13, weight: .medium)
                    }
                    .foregroundColor(finishButtonForeground)
                    .padding(.horizontal, 14)
                    .padding(.vertical, 6)
                    .background(Capsule().fill(finishButtonBackground))
                    .overlay(Capsule().stroke(OmiColors.border, lineWidth: 1))
                }
                .buttonStyle(.plain)
                .disabled(isFinishing || showSavedSuccess || showDiscarded || showError)
                .help("Saves current conversation and starts a new one")
            }

        }
        .padding(.horizontal, 16)
        .padding(.vertical, 10)
        .background(OmiColors.backgroundTertiary.opacity(0.8))
    }

    // MARK: - Audio Toggle

    private func audioToggle(appState: AppState) -> some View {
        ZStack {
            Capsule()
                .fill(appState.isTranscribing ? OmiColors.purplePrimary : Color.red)
                .frame(width: 36, height: 20)

            Circle()
                .fill(Color.white)
                .frame(width: 16, height: 16)
                .shadow(color: .black.opacity(0.15), radius: 1, x: 0, y: 1)
                .offset(x: appState.isTranscribing ? 8 : -8)
                .animation(.easeInOut(duration: 0.15), value: appState.isTranscribing)
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
                withAnimation(.easeInOut(duration: 0.3)) {
                    showSavedSuccess = true
                }
                try? await Task.sleep(for: .seconds(2.5))
                withAnimation(.easeInOut(duration: 0.3)) {
                    showSavedSuccess = false
                }
            case .discarded:
                withAnimation(.easeInOut(duration: 0.3)) {
                    showDiscarded = true
                }
                try? await Task.sleep(for: .seconds(2.5))
                withAnimation(.easeInOut(duration: 0.3)) {
                    showDiscarded = false
                }
            case .error:
                withAnimation(.easeInOut(duration: 0.3)) {
                    showError = true
                }
                try? await Task.sleep(for: .seconds(2.5))
                withAnimation(.easeInOut(duration: 0.3)) {
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
            HStack(alignment: .top, spacing: 16) {
                // Left side: Text content
                VStack(alignment: .leading, spacing: 6) {
                    // App name and window title (like URL in Google)
                    HStack(spacing: 6) {
                        AppIconView(appName: screenshot.appName, size: 16)
                        Text(screenshot.appName)
                            .scaledFont(size: 12, weight: .medium)
                            .foregroundColor(OmiColors.purplePrimary)
                        if let windowTitle = screenshot.windowTitle, !windowTitle.isEmpty {
                            Text("›")
                                .foregroundColor(.white.opacity(0.3))
                            Text(windowTitle)
                                .scaledFont(size: 11)
                                .foregroundColor(.white.opacity(0.5))
                                .lineLimit(1)
                        }
                    }

                    // Timestamp (like page title in Google)
                    Text(screenshot.formattedDate)
                        .scaledFont(size: 14, weight: .medium)
                        .foregroundColor(.white)

                    // Context snippet with highlighted search term
                    if let snippet = screenshot.contextSnippet(for: searchQuery) {
                        highlightedSnippet(snippet)
                    }

                    // Result number
                    Text("Result \(index + 1) of \(totalCount)")
                        .scaledFont(size: 10)
                        .foregroundColor(.white.opacity(0.3))
                        .padding(.top, 2)
                }

                Spacer()

                // Right side: Small thumbnail
                Group {
                    if let thumb = thumbnail {
                        Image(nsImage: thumb)
                            .resizable()
                            .aspectRatio(contentMode: .fill)
                            .frame(width: 120, height: 80)
                            .cornerRadius(6)
                            .clipped()
                    } else {
                        Rectangle()
                            .fill(Color.white.opacity(0.1))
                            .frame(width: 120, height: 80)
                            .cornerRadius(6)
                            .overlay(
                                ProgressView()
                                    .progressViewStyle(.circular)
                                    .scaleEffect(0.6)
                                    .tint(.white.opacity(0.5))
                            )
                    }
                }
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 12)
            .background(
                RoundedRectangle(cornerRadius: 8)
                    .fill(isSelected ? OmiColors.purplePrimary.opacity(0.15) :
                          (isHovered ? Color.white.opacity(0.05) : Color.clear))
            )
            .overlay(
                RoundedRectangle(cornerRadius: 8)
                    .stroke(isSelected ? OmiColors.purplePrimary.opacity(0.4) : Color.clear, lineWidth: 1)
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
                let match = String(snippet[snippet.index(snippet.startIndex, offsetBy: beforeIndex)..<snippet.index(snippet.startIndex, offsetBy: afterIndex)])
                let after = String(snippet.suffix(from: snippet.index(snippet.startIndex, offsetBy: afterIndex)))

                (Text(before).foregroundColor(.white.opacity(0.6)) +
                 Text(match).foregroundColor(.white).bold() +
                 Text(after).foregroundColor(.white.opacity(0.6)))
                    .scaledFont(size: 12)
                    .lineLimit(3)
            } else {
                Text(snippet)
                    .scaledFont(size: 12)
                    .foregroundColor(.white.opacity(0.6))
                    .lineLimit(3)
            }
        } else {
            Text(snippet)
                .scaledFont(size: 12)
                .foregroundColor(.white.opacity(0.6))
                .lineLimit(3)
        }
    }

    private func loadThumbnail() async {
        do {
            let image = try await RewindStorage.shared.loadScreenshotImage(for: screenshot)
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
            HStack(alignment: .top, spacing: 16) {
                // Left side: Text content
                VStack(alignment: .leading, spacing: 6) {
                    // App name and window title
                    HStack(spacing: 6) {
                        AppIconView(appName: group.appName, size: 16)
                        Text(group.appName)
                            .scaledFont(size: 12, weight: .medium)
                            .foregroundColor(OmiColors.purplePrimary)
                        if let windowTitle = group.windowTitle, !windowTitle.isEmpty {
                            Text("›")
                                .foregroundColor(.white.opacity(0.3))
                            Text(windowTitle)
                                .scaledFont(size: 11)
                                .foregroundColor(.white.opacity(0.5))
                                .lineLimit(1)
                        }
                    }

                    // Time range
                    Text(group.formattedTimeRange)
                        .scaledFont(size: 14, weight: .medium)
                        .foregroundColor(.white)

                    // Context snippet from representative screenshot
                    if let snippet = group.representativeScreenshot.contextSnippet(for: searchQuery) {
                        highlightedSnippet(snippet)
                    }

                    // Group info: count and position
                    HStack(spacing: 8) {
                        if group.count > 1 {
                            HStack(spacing: 4) {
                                Image(systemName: "square.stack")
                                    .scaledFont(size: 9)
                                Text("\(group.count) screenshots")
                            }
                            .scaledFont(size: 10)
                            .foregroundColor(OmiColors.purplePrimary.opacity(0.8))
                            .padding(.horizontal, 6)
                            .padding(.vertical, 2)
                            .background(OmiColors.purplePrimary.opacity(0.15))
                            .cornerRadius(4)
                        }

                        Text("Group \(index + 1) of \(totalGroups)")
                            .scaledFont(size: 10)
                            .foregroundColor(.white.opacity(0.3))
                    }
                    .padding(.top, 2)
                }

                Spacer()

                // Right side: Small thumbnail
                Group {
                    if let thumb = thumbnail {
                        Image(nsImage: thumb)
                            .resizable()
                            .aspectRatio(contentMode: .fill)
                            .frame(width: 120, height: 80)
                            .cornerRadius(6)
                            .clipped()
                    } else {
                        Rectangle()
                            .fill(Color.white.opacity(0.1))
                            .frame(width: 120, height: 80)
                            .cornerRadius(6)
                            .overlay(
                                ProgressView()
                                    .progressViewStyle(.circular)
                                    .scaleEffect(0.6)
                                    .tint(.white.opacity(0.5))
                            )
                    }
                }
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 12)
            .background(
                RoundedRectangle(cornerRadius: 8)
                    .fill(isSelected ? OmiColors.purplePrimary.opacity(0.15) :
                          (isHovered ? Color.white.opacity(0.05) : Color.clear))
            )
            .overlay(
                RoundedRectangle(cornerRadius: 8)
                    .stroke(isSelected ? OmiColors.purplePrimary.opacity(0.4) : Color.clear, lineWidth: 1)
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
                let match = String(snippet[snippet.index(snippet.startIndex, offsetBy: beforeIndex)..<snippet.index(snippet.startIndex, offsetBy: afterIndex)])
                let after = String(snippet.suffix(from: snippet.index(snippet.startIndex, offsetBy: afterIndex)))

                (Text(before).foregroundColor(.white.opacity(0.6)) +
                 Text(match).foregroundColor(.white).bold() +
                 Text(after).foregroundColor(.white.opacity(0.6)))
                    .scaledFont(size: 12)
                    .lineLimit(3)
            } else {
                Text(snippet)
                    .scaledFont(size: 12)
                    .foregroundColor(.white.opacity(0.6))
                    .lineLimit(3)
            }
        } else {
            Text(snippet)
                .scaledFont(size: 12)
                .foregroundColor(.white.opacity(0.6))
                .lineLimit(3)
        }
    }

    private func loadThumbnail() async {
        do {
            let image = try await RewindStorage.shared.loadScreenshotImage(for: group.representativeScreenshot)
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
            HStack(spacing: 12) {
                // App icon
                AppIconView(appName: screenshot.appName, size: 24)

                // Info
                VStack(alignment: .leading, spacing: 4) {
                    HStack {
                        Text(screenshot.appName)
                            .scaledFont(size: 13, weight: .medium)
                            .foregroundColor(.white)

                        if let windowTitle = screenshot.windowTitle, !windowTitle.isEmpty {
                            Text("— \(windowTitle)")
                                .scaledFont(size: 12)
                                .foregroundColor(.white.opacity(0.6))
                                .lineLimit(1)
                        }
                    }

                    // Context snippet if searching
                    if let query = searchQuery,
                       let snippet = screenshot.contextSnippet(for: query) {
                        Text(snippet)
                            .scaledFont(size: 12)
                            .foregroundColor(.white.opacity(0.7))
                            .lineLimit(2)
                    }
                }

                Spacer()

                // Timestamp
                Text(screenshot.formattedDate)
                    .scaledFont(size: 11, design: .monospaced)
                    .foregroundColor(.white.opacity(0.5))

                // Selection indicator
                if isSelected {
                    Image(systemName: "checkmark.circle.fill")
                        .scaledFont(size: 14)
                        .foregroundColor(OmiColors.purplePrimary)
                }
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 10)
            .background(
                RoundedRectangle(cornerRadius: 8)
                    .fill(isSelected ? OmiColors.purplePrimary.opacity(0.2) :
                          (isHovered ? Color.white.opacity(0.1) : Color.white.opacity(0.05)))
            )
            .overlay(
                RoundedRectangle(cornerRadius: 8)
                    .stroke(isSelected ? OmiColors.purplePrimary.opacity(0.5) : Color.clear, lineWidth: 1)
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
                    return event // Pass event through
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

// MARK: - Rewind Intro Video Player

struct RewindIntroVideoView: NSViewRepresentable {
    func makeCoordinator() -> Coordinator {
        Coordinator()
    }

    func makeNSView(context: Context) -> AVPlayerView {
        let playerView = AVPlayerView()
        if let url = Bundle.resourceBundle.url(forResource: "rewind-demo", withExtension: "mp4") {
            let player = AVPlayer(url: url)
            playerView.player = player
            playerView.controlsStyle = .inline
            playerView.showsFullScreenToggleButton = false
            player.play()

            NotificationCenter.default.addObserver(
                context.coordinator,
                selector: #selector(Coordinator.playerDidFinishPlaying(_:)),
                name: .AVPlayerItemDidPlayToEndTime,
                object: player.currentItem
            )
            context.coordinator.player = player
        }
        return playerView
    }

    func updateNSView(_ nsView: AVPlayerView, context: Context) {}

    class Coordinator: NSObject {
        var player: AVPlayer?

        @objc func playerDidFinishPlaying(_ notification: Notification) {
            player?.seek(to: .zero)
            player?.play()
        }
    }
}

#Preview {
    RewindPage()
        .frame(width: 1000, height: 700)
}
