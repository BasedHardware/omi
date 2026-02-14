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
    @Binding var selectedConversation: ServerConversation?

    /// When true, renders without internal ScrollViews (for embedding in an outer ScrollView)
    var embedded: Bool = false

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
        VStack(spacing: 0) {
            // Conversations header
            HStack {
                Text("Conversations")
                    .scaledFont(size: 18, weight: .semibold)
                    .foregroundColor(OmiColors.textPrimary)

                Spacer()

                if !appState.isTranscribing {
                    startRecordingButton
                }
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 10)

            // Conversation list
            conversationListSection
        }
    }

    // MARK: - Conversation List Section

    private var conversationListSection: some View {
        VStack(spacing: 0) {
            // Section header with search bar and filters
            HStack(spacing: 8) {
                // Search bar
                HStack(spacing: 8) {
                    Image(systemName: "magnifyingglass")
                        .scaledFont(size: 13)
                        .foregroundColor(OmiColors.textTertiary)

                    TextField("Search conversations...", text: $searchQuery)
                        .textFieldStyle(.plain)
                        .scaledFont(size: 13)
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
                                .scaledFont(size: 13)
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
                        embedded: embedded,
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
                        .scaledFont(size: 13)
                        .foregroundColor(OmiColors.textTertiary)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else if let error = searchError {
                VStack(spacing: 12) {
                    Image(systemName: "exclamationmark.triangle")
                        .scaledFont(size: 32)
                        .foregroundColor(OmiColors.textTertiary)
                    Text(error)
                        .scaledFont(size: 13)
                        .foregroundColor(OmiColors.textTertiary)
                        .multilineTextAlignment(.center)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                .padding()
            } else if searchResults.isEmpty {
                VStack(spacing: 12) {
                    Image(systemName: "magnifyingglass")
                        .scaledFont(size: 32)
                        .foregroundColor(OmiColors.textTertiary.opacity(0.5))
                    Text("No conversations found")
                        .scaledFont(size: 14)
                        .foregroundColor(OmiColors.textTertiary)
                    Text("Try a different search term")
                        .scaledFont(size: 12)
                        .foregroundColor(OmiColors.textQuaternary)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                ZStack(alignment: .bottom) {
                    searchResultsContent

                    // Floating merge action bar (also show in search results)
                    if isMultiSelectMode && !selectedConversationIds.isEmpty {
                        mergeActionBar
                            .transition(.move(edge: .bottom).combined(with: .opacity))
                    }
                }
            }
        }
    }

    @ViewBuilder
    private var searchResultsContent: some View {
        let content = LazyVStack(spacing: 8) {
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

        if embedded {
            content
        } else {
            ScrollView {
                content
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
                            .scaledFont(size: 12)
                    }
                    Text("Starred")
                        .scaledFont(size: 12, weight: .medium)
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
                            .scaledFont(size: 12)
                    }
                    if let date = appState.selectedDateFilter {
                        Text(formatFilterDate(date))
                            .scaledFont(size: 12, weight: .medium)
                        // Clear button
                        Button(action: {
                            Task {
                                isFilteringDate = true
                                await appState.setDateFilter(nil)
                                isFilteringDate = false
                            }
                        }) {
                            Image(systemName: "xmark.circle.fill")
                                .scaledFont(size: 10)
                        }
                        .buttonStyle(.plain)
                    } else {
                        Text("Date")
                            .scaledFont(size: 12, weight: .medium)
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
                        .scaledFont(size: 12)
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
                .scaledFont(size: 14, weight: .medium)
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
                    .scaledFont(size: 12, weight: .medium)
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
                            .scaledFont(size: 12)
                    }
                    Text("Merge")
                        .scaledFont(size: 13, weight: .semibold)
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

    // MARK: - Buttons

    private var startRecordingButton: some View {
        Button(action: {
            appState.startTranscription()
        }) {
            HStack(spacing: 6) {
                Image(systemName: "mic.fill")
                    .scaledFont(size: 12)
                Text("Start Recording")
                    .scaledFont(size: 13, weight: .medium)
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
    ConversationsPage(appState: AppState(), selectedConversation: .constant(nil))
        .frame(width: 600, height: 800)
        .background(OmiColors.backgroundSecondary)
}
