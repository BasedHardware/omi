import SwiftUI
import Combine

// MARK: - Search Debouncer

/// Debounces search queries to avoid excessive API calls
class SearchDebouncer: ObservableObject {
    /// The input query (set immediately when user types)
    @Published var inputQuery: String = ""
    /// The debounced query (updated 500ms after user stops typing)
    @Published var debouncedQuery: String = ""
    private var cancellables = Set<AnyCancellable>()

    init() {
        // Observe input and debounce to output
        $inputQuery
            .debounce(for: .milliseconds(500), scheduler: DispatchQueue.main)
            .removeDuplicates()
            .sink { [weak self] value in
                self?.debouncedQuery = value
            }
            .store(in: &cancellables)
    }
}

// MARK: - Conversations Page

struct ConversationsPage: View {
    @ObservedObject var appState: AppState
    @ObservedObject private var audioLevels = AudioLevelMonitor.shared
    @ObservedObject private var recordingTimer = RecordingTimer.shared
    @ObservedObject private var liveTranscript = LiveTranscriptMonitor.shared
    @ObservedObject private var liveNotes = LiveNotesMonitor.shared
    @State private var selectedConversation: ServerConversation? = nil

    // Transcript visibility state - hidden by default
    @State private var isTranscriptCollapsed: Bool = true

    // Notes panel visibility
    @State private var isNotesPanelVisible: Bool = true

    // Notes panel width ratio (persisted)
    @AppStorage("transcriptNotesPanelRatio") private var notesPanelRatio: Double = 0.65

    // Compact view mode - persisted preference
    @AppStorage("conversationsCompactView") private var isCompactView = false

    // Search state
    @State private var searchQuery: String = ""
    @State private var searchResults: [ServerConversation] = []
    @State private var isSearching: Bool = false
    @State private var searchError: String? = nil
    @StateObject private var searchDebouncer = SearchDebouncer()

    // Date picker state
    @State private var showDatePicker: Bool = false

    // Folder management state
    @State private var showCreateFolderSheet: Bool = false
    @State private var editingFolder: Folder? = nil
    @State private var deletingFolder: Folder? = nil

    // Filter loading states (to show loading on the clicked button)
    @State private var isFilteringStarred: Bool = false
    @State private var isFilteringDate: Bool = false

    // Multi-select state for merging
    @State private var isMultiSelectMode: Bool = false
    @State private var selectedConversationIds: Set<String> = []
    @State private var showMergeConfirmation: Bool = false
    @State private var isMerging: Bool = false
    @State private var mergeError: String? = nil

    var body: some View {
        Group {
            if let selected = selectedConversation {
                // Detail view for selected conversation
                ConversationDetailView(
                    conversation: selected,
                    onBack: { selectedConversation = nil },
                    folders: appState.folders,
                    onMoveToFolder: { conversationId, folderId in
                        await appState.moveConversationToFolder(conversationId, folderId: folderId)
                    },
                    onDelete: {
                        appState.deleteConversationLocally(selected.id)
                        selectedConversation = nil
                        Task {
                            await appState.refreshConversations()
                        }
                    },
                    onTitleUpdated: { _ in
                        // Refresh to get updated data if conversation still exists
                        if appState.conversations.contains(where: { $0.id == selected.id }) {
                            Task {
                                await appState.refreshConversations()
                            }
                        }
                    }
                )
            } else {
                // Main view with recording header and conversation list
                mainConversationsView
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(Color.clear)
        .onAppear {
            // Load conversations when view appears
            if appState.conversations.isEmpty {
                Task {
                    await appState.loadConversations()
                }
            } else {
                // Already loaded, notify sidebar to clear loading indicator
                NotificationCenter.default.post(name: .conversationsPageDidLoad, object: nil)
            }
            // Load folders
            if appState.folders.isEmpty {
                Task {
                    await appState.loadFolders()
                }
            }
        }
        .dismissableSheet(isPresented: $showCreateFolderSheet) {
            FolderFormSheet(folder: nil, onDismiss: { showCreateFolderSheet = false })
                .environmentObject(appState)
                .frame(width: 380)
        }
        .dismissableSheet(item: $editingFolder) { folder in
            FolderFormSheet(folder: folder, onDismiss: { editingFolder = nil })
                .environmentObject(appState)
                .frame(width: 380)
        }
        .dismissableSheet(item: $deletingFolder) { folder in
            DeleteFolderSheet(folder: folder, onDismiss: { deletingFolder = nil })
                .environmentObject(appState)
                .frame(width: 380)
        }
    }

    // MARK: - Main View with Recording Header + List

    private var mainConversationsView: some View {
        ZStack(alignment: .top) {
            VStack(spacing: 0) {
                // Recording header (always visible)
                recordingHeader
                    .padding(.horizontal, 16)
                    .padding(.vertical, 10)

                // When transcribing and expanded: full-page transcript
                // When transcribing and collapsed: show splitter then conversation list
                // When not transcribing: just conversation list
                if appState.isTranscribing && !isTranscriptCollapsed {
                    // Expanded: full-page transcript with back button
                    fullPageTranscriptView
                } else {
                    // Collapsed or not recording: show conversation list
                    conversationListSection
                }
            }

        }
    }

    // MARK: - Transcript Views

    /// Expanded state: full-page transcript with notes panel
    private var fullPageTranscriptView: some View {
        VStack(spacing: 0) {
            // Header with back button and notes toggle
            HStack {
                Button(action: {
                    withAnimation(.easeInOut(duration: 0.2)) {
                        isTranscriptCollapsed = true
                    }
                }) {
                    HStack(spacing: 6) {
                        Image(systemName: "chevron.left")
                            .font(.system(size: 12, weight: .medium))
                        Text("Back to Conversations")
                            .font(.system(size: 13, weight: .medium))
                    }
                    .foregroundColor(OmiColors.textSecondary)
                }
                .buttonStyle(.plain)

                Spacer()

                // Notes panel toggle
                Button(action: {
                    withAnimation(.easeInOut(duration: 0.2)) {
                        isNotesPanelVisible.toggle()
                    }
                }) {
                    HStack(spacing: 4) {
                        Image(systemName: "note.text")
                            .font(.system(size: 12))
                        Text("Notes")
                            .font(.system(size: 12, weight: .medium))
                    }
                    .foregroundColor(isNotesPanelVisible ? OmiColors.textPrimary : OmiColors.textTertiary)
                }
                .buttonStyle(.plain)
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 10)
            .background(OmiColors.backgroundTertiary.opacity(0.5))

            // Split view: transcript (left) + notes (right)
            GeometryReader { geometry in
                let totalWidth = geometry.size.width
                let minPanelWidth: CGFloat = 200
                let transcriptWidth = isNotesPanelVisible
                    ? max(minPanelWidth, totalWidth * notesPanelRatio)
                    : totalWidth
                let notesWidth = isNotesPanelVisible
                    ? max(minPanelWidth, totalWidth - transcriptWidth - 1)
                    : 0

                HStack(spacing: 0) {
                    // Left panel: Transcript
                    transcriptContentView
                        .frame(width: transcriptWidth)

                    if isNotesPanelVisible {
                        // Draggable divider
                        TranscriptNotesDivider(
                            panelRatio: $notesPanelRatio,
                            totalWidth: totalWidth,
                            minRatio: minPanelWidth / totalWidth,
                            maxRatio: 1.0 - (minPanelWidth / totalWidth)
                        )

                        // Right panel: Notes
                        LiveNotesView()
                            .frame(width: notesWidth)
                    }
                }
            }
        }
    }

    /// Transcript content (empty state or live transcript)
    private var transcriptContentView: some View {
        Group {
            if liveTranscript.isEmpty {
                VStack(spacing: 12) {
                    Image(systemName: "waveform")
                        .font(.system(size: 32))
                        .foregroundColor(OmiColors.textTertiary.opacity(0.5))

                    Text("Listening...")
                        .font(.system(size: 14))
                        .foregroundColor(OmiColors.textTertiary)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                LiveTranscriptView(segments: liveTranscript.segments)
            }
        }
        .background(OmiColors.backgroundPrimary)
    }

    // MARK: - Conversation List Section

    private var conversationListSection: some View {
        VStack(spacing: 0) {
            // Section header with search bar and filters
            HStack(spacing: 8) {
                // Search bar
                HStack(spacing: 8) {
                    Image(systemName: "magnifyingglass")
                        .font(.system(size: 13))
                        .foregroundColor(OmiColors.textTertiary)

                    TextField("Search conversations...", text: $searchQuery)
                        .textFieldStyle(.plain)
                        .font(.system(size: 13))
                        .foregroundColor(OmiColors.textPrimary)
                        .onChange(of: searchQuery) { _, newValue in
                            // Feed input to debouncer
                            searchDebouncer.inputQuery = newValue
                        }
                        .onChange(of: searchDebouncer.debouncedQuery) { _, newValue in
                            // Debounced value changed - perform search
                            performSearch(query: newValue)
                        }

                    if !searchQuery.isEmpty {
                        Button(action: {
                            searchQuery = ""
                            searchDebouncer.inputQuery = ""
                            searchResults = []
                            searchError = nil
                        }) {
                            Image(systemName: "xmark.circle.fill")
                                .font(.system(size: 13))
                                .foregroundColor(OmiColors.textTertiary)
                        }
                        .buttonStyle(.plain)
                    }
                }
                .padding(.horizontal, 10)
                .padding(.vertical, 8)
                .background(
                    RoundedRectangle(cornerRadius: 8)
                        .fill(OmiColors.backgroundTertiary.opacity(0.5))
                )

                // Filter buttons
                filterButtonsRow
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 10)

            // Folder tabs strip
            FolderTabsStrip(
                appState: appState,
                onCreateFolder: { showCreateFolderSheet = true },
                onEditFolder: { folder in editingFolder = folder },
                onDeleteFolder: { folder in deletingFolder = folder }
            )
            .padding(.horizontal, 16)
            .padding(.bottom, 8)

            // List - show search results or regular conversations
            if !searchQuery.isEmpty {
                // Search results view
                searchResultsView
            } else {
                // Regular conversation list
                ZStack(alignment: .bottom) {
                    ConversationListView(
                        conversations: appState.conversations,
                        isLoading: appState.isLoadingConversations,
                        error: appState.conversationsError,
                        folders: appState.folders,
                        isCompactView: isCompactView,
                        onSelect: { conversation in
                            AnalyticsManager.shared.memoryListItemClicked(conversationId: conversation.id)
                            selectedConversation = conversation
                        },
                        onRefresh: {
                            Task {
                                await appState.refreshConversations()
                            }
                        },
                        onMoveToFolder: { conversationId, folderId in
                            await appState.moveConversationToFolder(conversationId, folderId: folderId)
                        },
                        isMultiSelectMode: isMultiSelectMode,
                        selectedIds: selectedConversationIds,
                        onToggleSelection: { conversationId in
                            if selectedConversationIds.contains(conversationId) {
                                selectedConversationIds.remove(conversationId)
                            } else {
                                selectedConversationIds.insert(conversationId)
                            }
                        },
                        appState: appState
                    )

                    // Floating merge action bar
                    if isMultiSelectMode && !selectedConversationIds.isEmpty {
                        mergeActionBar
                            .transition(.move(edge: .bottom).combined(with: .opacity))
                    }
                }
            }
        }
    }

    // MARK: - Search Results View

    private var searchResultsView: some View {
        Group {
            if isSearching {
                VStack(spacing: 12) {
                    ProgressView()
                    Text("Searching...")
                        .font(.system(size: 13))
                        .foregroundColor(OmiColors.textTertiary)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else if let error = searchError {
                VStack(spacing: 12) {
                    Image(systemName: "exclamationmark.triangle")
                        .font(.system(size: 32))
                        .foregroundColor(OmiColors.textTertiary)
                    Text(error)
                        .font(.system(size: 13))
                        .foregroundColor(OmiColors.textTertiary)
                        .multilineTextAlignment(.center)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                .padding()
            } else if searchResults.isEmpty {
                VStack(spacing: 12) {
                    Image(systemName: "magnifyingglass")
                        .font(.system(size: 32))
                        .foregroundColor(OmiColors.textTertiary.opacity(0.5))
                    Text("No conversations found")
                        .font(.system(size: 14))
                        .foregroundColor(OmiColors.textTertiary)
                    Text("Try a different search term")
                        .font(.system(size: 12))
                        .foregroundColor(OmiColors.textQuaternary)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                ZStack(alignment: .bottom) {
                    ScrollView {
                        LazyVStack(spacing: 8) {
                            ForEach(searchResults) { conversation in
                                ConversationRowView(
                                    conversation: conversation,
                                    onTap: {
                                        AnalyticsManager.shared.memoryListItemClicked(conversationId: conversation.id)
                                        selectedConversation = conversation
                                    },
                                    folders: appState.folders,
                                    onMoveToFolder: { conversationId, folderId in
                                        await appState.moveConversationToFolder(conversationId, folderId: folderId)
                                    },
                                    isCompactView: isCompactView,
                                    isMultiSelectMode: isMultiSelectMode,
                                    isSelected: selectedConversationIds.contains(conversation.id),
                                    onToggleSelection: {
                                        if selectedConversationIds.contains(conversation.id) {
                                            selectedConversationIds.remove(conversation.id)
                                        } else {
                                            selectedConversationIds.insert(conversation.id)
                                        }
                                    },
                                    appState: appState
                                )
                            }
                        }
                        .padding(.horizontal, 16)
                        .padding(.bottom, isMultiSelectMode && !selectedConversationIds.isEmpty ? 80 : 16)
                    }

                    // Floating merge action bar (also show in search results)
                    if isMultiSelectMode && !selectedConversationIds.isEmpty {
                        mergeActionBar
                            .transition(.move(edge: .bottom).combined(with: .opacity))
                    }
                }
            }
        }
    }

    // MARK: - Search

    private func performSearch(query: String) {
        guard !query.isEmpty else {
            searchResults = []
            searchError = nil
            return
        }

        isSearching = true
        searchError = nil
        log("Search: Starting search for '\(query)'")
        AnalyticsManager.shared.searchQueryEntered(query: query)

        Task {
            do {
                let result = try await APIClient.shared.searchConversations(
                    query: query,
                    page: 1,
                    perPage: 50,
                    includeDiscarded: false
                )
                log("Search: Found \(result.items.count) results")
                searchResults = result.items
                isSearching = false
            } catch {
                logError("Search: Failed", error: error)
                searchError = error.localizedDescription
                searchResults = []
                isSearching = false
            }
        }
    }

    // MARK: - Filter Buttons

    private var filterButtonsRow: some View {
        HStack(spacing: 8) {
            // Starred filter button
            Button(action: {
                Task {
                    isFilteringStarred = true
                    await appState.toggleStarredFilter()
                    isFilteringStarred = false
                }
            }) {
                HStack(spacing: 6) {
                    if isFilteringStarred {
                        ProgressView()
                            .scaleEffect(0.5)
                            .frame(width: 12, height: 12)
                    } else {
                        Image(systemName: appState.showStarredOnly ? "star.fill" : "star")
                            .font(.system(size: 12))
                    }
                    Text("Starred")
                        .font(.system(size: 12, weight: .medium))
                }
                .foregroundColor(appState.showStarredOnly ? OmiColors.amber : OmiColors.textSecondary)
                .padding(.horizontal, 12)
                .padding(.vertical, 6)
                .background(
                    RoundedRectangle(cornerRadius: 8)
                        .fill(appState.showStarredOnly ? OmiColors.amber.opacity(0.15) : OmiColors.backgroundTertiary.opacity(0.6))
                )
                .overlay(
                    RoundedRectangle(cornerRadius: 8)
                        .stroke(appState.showStarredOnly ? OmiColors.amber.opacity(0.4) : Color.clear, lineWidth: 1)
                )
            }
            .buttonStyle(.plain)
            .disabled(isFilteringStarred)

            // Date filter button
            Button(action: {
                showDatePicker.toggle()
            }) {
                HStack(spacing: 6) {
                    if isFilteringDate {
                        ProgressView()
                            .scaleEffect(0.5)
                            .frame(width: 12, height: 12)
                    } else {
                        Image(systemName: "calendar")
                            .font(.system(size: 12))
                    }
                    if let date = appState.selectedDateFilter {
                        Text(formatFilterDate(date))
                            .font(.system(size: 12, weight: .medium))
                        // Clear button
                        Button(action: {
                            Task {
                                isFilteringDate = true
                                await appState.setDateFilter(nil)
                                isFilteringDate = false
                            }
                        }) {
                            Image(systemName: "xmark.circle.fill")
                                .font(.system(size: 10))
                        }
                        .buttonStyle(.plain)
                    } else {
                        Text("Date")
                            .font(.system(size: 12, weight: .medium))
                    }
                }
                .foregroundColor(appState.selectedDateFilter != nil ? .black : OmiColors.textSecondary)
                .padding(.horizontal, 12)
                .padding(.vertical, 6)
                .background(
                    RoundedRectangle(cornerRadius: 8)
                        .fill(appState.selectedDateFilter != nil ? Color.white : OmiColors.backgroundTertiary.opacity(0.6))
                )
                .overlay(
                    RoundedRectangle(cornerRadius: 8)
                        .stroke(appState.selectedDateFilter != nil ? OmiColors.border : Color.clear, lineWidth: 1)
                )
            }
            .buttonStyle(.plain)
            .disabled(isFilteringDate)
            .popover(isPresented: $showDatePicker) {
                datePickerPopover
            }

            // Clear all filters button (only show if any filter is active)
            if appState.showStarredOnly || appState.selectedDateFilter != nil || appState.selectedFolderId != nil {
                Button(action: {
                    Task {
                        await appState.clearFilters()
                    }
                }) {
                    Image(systemName: "xmark.circle.fill")
                        .font(.system(size: 12))
                        .foregroundColor(OmiColors.textTertiary)
                }
                .buttonStyle(.plain)
            }
        }
    }

    private var datePickerPopover: some View {
        VStack(spacing: 12) {
            DatePicker(
                "Select Date",
                selection: Binding(
                    get: { appState.selectedDateFilter ?? Date() },
                    set: { newDate in
                        showDatePicker = false
                        Task {
                            isFilteringDate = true
                            await appState.setDateFilter(newDate)
                            isFilteringDate = false
                        }
                    }
                ),
                in: ...Date(),
                displayedComponents: .date
            )
            .datePickerStyle(.graphical)
            .labelsHidden()
        }
        .padding()
        .frame(width: 300)
        .background(OmiColors.backgroundSecondary)
    }

    private func formatFilterDate(_ date: Date) -> String {
        let formatter = DateFormatter()
        formatter.dateFormat = "MMM d"
        return formatter.string(from: date)
    }

    // MARK: - Merge Action Bar

    private var mergeActionBar: some View {
        HStack(spacing: 16) {
            // Selection count
            Text("\(selectedConversationIds.count) selected")
                .font(.system(size: 14, weight: .medium))
                .foregroundColor(OmiColors.textSecondary)

            Spacer()

            // Select All / Deselect All
            Button(action: {
                if selectedConversationIds.count == appState.conversations.count {
                    selectedConversationIds.removeAll()
                } else {
                    selectedConversationIds = Set(appState.conversations.map { $0.id })
                }
            }) {
                Text(selectedConversationIds.count == appState.conversations.count ? "Deselect All" : "Select All")
                    .font(.system(size: 12, weight: .medium))
                    .foregroundColor(OmiColors.textSecondary)
            }
            .buttonStyle(.plain)

            // Merge button (only enabled when 2+ selected)
            Button(action: {
                showMergeConfirmation = true
            }) {
                HStack(spacing: 6) {
                    if isMerging {
                        ProgressView()
                            .scaleEffect(0.5)
                            .frame(width: 14, height: 14)
                    } else {
                        Image(systemName: "arrow.triangle.merge")
                            .font(.system(size: 12))
                    }
                    Text("Merge")
                        .font(.system(size: 13, weight: .semibold))
                }
                .foregroundColor(selectedConversationIds.count >= 2 ? OmiColors.textPrimary : OmiColors.textTertiary)
                .padding(.horizontal, 16)
                .padding(.vertical, 8)
                .background(
                    Capsule()
                        .fill(selectedConversationIds.count >= 2 ? Color.white : OmiColors.backgroundTertiary)
                )
                .overlay(
                    Capsule()
                        .stroke(selectedConversationIds.count >= 2 ? OmiColors.border : Color.clear, lineWidth: 1)
                )
            }
            .buttonStyle(.plain)
            .disabled(selectedConversationIds.count < 2 || isMerging)
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 12)
        .background(
            RoundedRectangle(cornerRadius: 12)
                .fill(OmiColors.backgroundTertiary)
                .shadow(color: .black.opacity(0.3), radius: 10, y: -2)
        )
        .padding(.horizontal, 16)
        .padding(.bottom, 16)
        .alert("Merge Conversations", isPresented: $showMergeConfirmation) {
            Button("Cancel", role: .cancel) { }
            Button("Merge") {
                Task {
                    await performMerge()
                }
            }
        } message: {
            Text("Are you sure you want to merge \(selectedConversationIds.count) conversations? This will combine them into a single conversation and delete the originals. This action cannot be undone.")
        }
        .alert("Merge Failed", isPresented: .init(
            get: { mergeError != nil },
            set: { if !$0 { mergeError = nil } }
        )) {
            Button("OK", role: .cancel) { }
        } message: {
            Text(mergeError ?? "Unknown error")
        }
    }

    private func performMerge() async {
        guard selectedConversationIds.count >= 2 else { return }

        isMerging = true
        mergeError = nil

        do {
            let ids = Array(selectedConversationIds)
            let response = try await APIClient.shared.mergeConversations(ids: ids)

            log("Merge completed: \(response.message)")

            // Show warning if there was one
            if let warning = response.warning {
                log("Merge warning: \(warning)")
            }

            // Refresh conversations to show the merged one
            await appState.refreshConversations()

            // Exit multi-select mode
            withAnimation(.easeInOut(duration: 0.2)) {
                isMultiSelectMode = false
                selectedConversationIds.removeAll()
            }
        } catch {
            logError("Merge failed", error: error)
            mergeError = error.localizedDescription
        }

        isMerging = false
    }

    // MARK: - Recording Header

    private var recordingHeader: some View {
        HStack(spacing: 16) {
            if appState.isTranscribing {
                // Recording indicator
                recordingIndicator

                Spacer()

                // Duration
                Text(recordingDurationFormatted)
                    .font(.system(size: 14, weight: .medium, design: .monospaced))
                    .foregroundColor(OmiColors.textSecondary)

                // Stop recording button
                stopRecordingButton
            } else if appState.isSavingConversation {
                // Saving state with animation
                savingIndicator

                Spacer()
            } else {
                // Not recording - show start button
                Text("Conversations")
                    .font(.system(size: 18, weight: .semibold))
                    .foregroundColor(OmiColors.textPrimary)

                Spacer()

                startRecordingButton
            }
        }
    }

    // MARK: - Recording Indicator

    @State private var isPulsing = false

    private var recordingIndicator: some View {
        HStack(spacing: 12) {
            // Pulsing dot
            ZStack {
                Circle()
                    .fill(OmiColors.purplePrimary.opacity(0.3))
                    .frame(width: 20, height: 20)
                    .scaleEffect(isPulsing ? 1.6 : 1.0)
                    .opacity(isPulsing ? 0.0 : 0.6)

                Circle()
                    .fill(OmiColors.purplePrimary)
                    .frame(width: 10, height: 10)
            }
            .animation(
                .easeInOut(duration: 1.0)
                .repeatForever(autoreverses: true),
                value: isPulsing
            )
            .onAppear { isPulsing = true }

            // Show inline transcript when collapsed, "Listening" when expanded or no text
            if isTranscriptCollapsed, let latestText = latestTranscriptText {
                // Inline transcript preview - clickable to expand
                Button(action: {
                    withAnimation(.easeInOut(duration: 0.2)) {
                        isTranscriptCollapsed = false
                    }
                }) {
                    HStack(spacing: 6) {
                        Text(latestText)
                            .font(.system(size: 14))
                            .foregroundColor(OmiColors.textSecondary)
                            .lineLimit(1)
                            .truncationMode(.head)
                            .frame(maxWidth: 280, alignment: .leading)

                        Image(systemName: "chevron.down")
                            .font(.system(size: 10, weight: .medium))
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
                .contentShape(Rectangle())
            } else {
                Text("Listening")
                    .font(.system(size: 14, weight: .medium))
                    .foregroundColor(OmiColors.textPrimary)
            }

            // Audio level waveforms (restored original animation)
            HStack(spacing: 16) {
                HStack(spacing: 6) {
                    Image(systemName: "mic.fill")
                        .font(.system(size: 12))
                        .foregroundColor(OmiColors.textTertiary)
                    AudioLevelWaveformView(
                        level: audioLevels.microphoneLevel,
                        barCount: 8,
                        isActive: appState.isTranscribing
                    )
                }

                HStack(spacing: 6) {
                    Image(systemName: "speaker.wave.2.fill")
                        .font(.system(size: 12))
                        .foregroundColor(OmiColors.textTertiary)
                    AudioLevelWaveformView(
                        level: audioLevels.systemLevel,
                        barCount: 8,
                        isActive: appState.isTranscribing
                    )
                }
            }
        }
    }

    /// Get the latest transcript text for inline display
    private var latestTranscriptText: String? {
        guard !liveTranscript.isEmpty else { return nil }
        // Get the last segment's text
        return liveTranscript.latestText
    }

    // MARK: - Saving Indicator

    @State private var isSavingPulsing = false

    private var savingIndicator: some View {
        HStack(spacing: 12) {
            // Pulsing save icon
            ZStack {
                Circle()
                    .fill(OmiColors.purplePrimary.opacity(0.3))
                    .frame(width: 24, height: 24)
                    .scaleEffect(isSavingPulsing ? 1.5 : 1.0)
                    .opacity(isSavingPulsing ? 0.0 : 0.6)

                Image(systemName: "arrow.up.circle.fill")
                    .font(.system(size: 16))
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
                .font(.system(size: 14, weight: .medium))
                .foregroundColor(OmiColors.textPrimary)

            ProgressView()
                .scaleEffect(0.7)
        }
    }

    // MARK: - Buttons

    private var stopRecordingButton: some View {
        Button(action: {
            appState.stopTranscription()
        }) {
            HStack(spacing: 6) {
                Image(systemName: "stop.circle.fill")
                    .font(.system(size: 12))
                Text("Stop Recording")
                    .font(.system(size: 13, weight: .medium))
            }
            .foregroundColor(.black)
            .padding(.horizontal, 14)
            .padding(.vertical, 8)
            .background(
                Capsule()
                    .fill(Color.white)
            )
            .overlay(
                Capsule()
                    .stroke(OmiColors.border, lineWidth: 1)
            )
        }
        .buttonStyle(.plain)
    }

    private var startRecordingButton: some View {
        Button(action: {
            appState.startTranscription()
        }) {
            HStack(spacing: 6) {
                Image(systemName: "mic.fill")
                    .font(.system(size: 12))
                Text("Start Recording")
                    .font(.system(size: 13, weight: .medium))
            }
            .foregroundColor(.black)
            .padding(.horizontal, 14)
            .padding(.vertical, 8)
            .background(
                Capsule()
                    .fill(Color.white)
            )
            .overlay(
                Capsule()
                    .stroke(OmiColors.border, lineWidth: 1)
            )
        }
        .buttonStyle(.plain)
    }

    // MARK: - Helpers

    /// Recording duration formatted - separate from conversation duration
    private var recordingDurationFormatted: String {
        recordingTimer.formattedDuration
    }
}

// MARK: - Transcript Notes Divider

/// Draggable divider between transcript and notes panels
private struct TranscriptNotesDivider: View {
    @Binding var panelRatio: Double
    let totalWidth: CGFloat
    let minRatio: Double
    let maxRatio: Double

    @State private var isDragging = false

    var body: some View {
        Rectangle()
            .fill(isDragging ? OmiColors.textSecondary : OmiColors.border)
            .frame(width: 1)
            .contentShape(Rectangle().inset(by: -4)) // Larger hit area
            .onHover { hovering in
                if hovering {
                    NSCursor.resizeLeftRight.push()
                } else {
                    NSCursor.pop()
                }
            }
            .gesture(
                DragGesture()
                    .onChanged { value in
                        isDragging = true
                        let newRatio = Double(value.location.x / totalWidth)
                        panelRatio = min(maxRatio, max(minRatio, newRatio))
                    }
                    .onEnded { _ in
                        isDragging = false
                    }
            )
    }
}

#Preview {
    ConversationsPage(appState: AppState())
        .frame(width: 600, height: 800)
        .background(OmiColors.backgroundSecondary)
}
