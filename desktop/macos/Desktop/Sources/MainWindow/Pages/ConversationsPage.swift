import OmiTheme
import SwiftUI

/// Applies the list query's refinements to remote text-search results.
///
/// The search endpoint only accepts text, so search results must pass through
/// this same local predicate as the list's cached/server rows. Keeping the
/// predicate pure also means a filter change immediately updates an already
/// visible search without starting a second request.
enum ConversationSearchResultFilter {
  static func apply(
    _ conversations: [ServerConversation],
    starredOnly: Bool,
    date: Date?,
    folderId: String?,
    calendar: Calendar = .current
  ) -> [ServerConversation] {
    let dateRange: (start: Date, end: Date)? = date.flatMap { selectedDate in
      let start = calendar.startOfDay(for: selectedDate)
      guard let end = calendar.date(byAdding: .day, value: 1, to: start) else { return nil }
      return (start: start, end: end)
    }

    return conversations.filter { conversation in
      if starredOnly && !conversation.starred { return false }
      if let folderId, conversation.folderId != folderId { return false }
      if let dateRange {
        let conversationDate = conversation.startedAt ?? conversation.createdAt
        guard conversationDate >= dateRange.start && conversationDate < dateRange.end else {
          return false
        }
      }
      return true
    }
  }
}

// MARK: - Conversations Page

struct ConversationsPage: View {
  @ObservedObject var appState: AppState
  @Binding var selectedConversation: ServerConversation?
  var brainDestination: MemoryHubDestination? = nil
  var onSelectBrainDestination: ((MemoryHubDestination) -> Void)? = nil
  var initialCaptureMomentTimestamp: TimeInterval? = nil
  var onCaptureFocusResolved: ((Bool) -> Void)? = nil
  var onDiscussInChat: ((ServerConversation) -> Void)? = nil
  var onOpenLinkedTask: ((String) -> Void)? = nil
  @ObservedObject private var automation = ConversationDetailAutomationState.shared

  /// When true, renders without internal ScrollViews (for embedding in an outer ScrollView)
  var embedded: Bool = false

  // Compact view mode - persisted preference
  @AppStorage("conversationsCompactView") private var isCompactView = true

  // Listening mode — used only to decide whether the manual "Start Recording"
  // action is meaningful in the page's overflow menu.
  @AppStorage(AssistantSettings.audioRecordingModeDefaultsKey) private var audioRecordingModeRaw =
    AssistantSettings.AudioRecordingMode.onlyMeetings.rawValue
  private var audioRecordingMode: AssistantSettings.AudioRecordingMode {
    CaptureListeningLogic.audioRecordingMode(raw: audioRecordingModeRaw)
  }

  // Search state
  @State private var searchQuery: String = ""
  @State private var searchResults: [ServerConversation] = []
  @State private var isSearching: Bool = false
  @State private var searchError: String? = nil
  @StateObject private var searchCoordinator = DebouncedSearchCoordinator()

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

  // Full-screen live transcript overlay
  @State private var isLiveTranscriptExpanded: Bool = false

  var body: some View {
    pageSurface
      .frame(maxWidth: .infinity, maxHeight: .infinity)
      .glassContent()
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
        consumePendingAutomationOpenConversation()
      }
      .onReceive(automation.$pendingOpenRequest.compactMap { $0 }) { _ in
        consumePendingAutomationOpenConversation()
      }
      .onReceive(NotificationCenter.default.publisher(for: .desktopAutomationOpenConversationRequested)) {
        _ in
        consumePendingAutomationOpenConversation()
      }
      .onReceive(
        NotificationCenter.default.publisher(for: .desktopAutomationSetConversationsSearchRequested)
      ) { notification in
        searchQuery = (notification.userInfo?["query"] as? String) ?? ""
      }
      // Owner fencing: an in-place account switch posts only .runtimeOwnerDidChange;
      // this page's local state (active search results, multi-select/merge state,
      // folder sheets) otherwise keeps rendering the previous account's rows even
      // after AppState and the repository reset.
      .onReceive(NotificationCenter.default.publisher(for: .runtimeOwnerDidChange)) { _ in
        selectedConversation = nil
        searchQuery = ""
        searchResults = []
        isSearching = false
        searchError = nil
        showDatePicker = false
        showCreateFolderSheet = false
        editingFolder = nil
        deletingFolder = nil
        isFilteringStarred = false
        isFilteringDate = false
        isMultiSelectMode = false
        selectedConversationIds = []
        showMergeConfirmation = false
        isMerging = false
        mergeError = nil
        isLiveTranscriptExpanded = false
      }
      .onReceive(appState.$conversations) { conversations in
        guard let selectedConversation,
          let refreshed = conversations.first(where: { $0.id == selectedConversation.id })
        else { return }
        self.selectedConversation = refreshed
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

  @ViewBuilder
  private var pageSurface: some View {
    if let brainDestination, let onSelectBrainDestination {
      BrainSectionPageLayout(
        selected: brainDestination,
        onSelect: onSelectBrainDestination,
        search: {
          QuerySearchBar(
            text: $searchQuery,
            accessibilityID: "conversations-search-field",
            placeholder: "Search conversations…",
            searchSurface: .conversations
          )
          .onChange(of: searchQuery) { _, newValue in
            if !newValue.isEmpty { selectedConversation = nil }
            submitSearch(newValue)
          }
        },
        content: { pageContent }
      )
    } else {
      pageContent
    }
  }

  @ViewBuilder
  private var pageContent: some View {
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
          // Cascade is owned by ConversationDetailView; refresh list after dismiss.
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
        },
        initialCaptureMomentTimestamp: initialCaptureMomentTimestamp,
        onCaptureFocusResolved: onCaptureFocusResolved,
        onDiscussInChat: selected.source == .omi ? { onDiscussInChat?(selected) } : nil,
        onOpenLinkedTask: onOpenLinkedTask
      )
    } else {
      // Main view with recording header and conversation list
      mainConversationsView
    }
  }

  private func consumePendingAutomationOpenConversation() {
    guard let request = ConversationDetailAutomationState.shared.takePendingOpenRequest() else { return }
    handleAutomationOpenConversation(conversationId: request.conversationId)
  }

  private func handleAutomationOpenConversation(conversationId: String) {

    func present(_ conversation: ServerConversation) {
      selectedConversation = conversation
    }

    if let conversation = appState.conversations.first(where: { $0.id == conversationId }) {
      present(conversation)
      return
    }

    if let conversation = searchResults.first(where: { $0.id == conversationId }) {
      present(conversation)
      return
    }

    Task {
      await appState.refreshConversations()
      await MainActor.run {
        guard let conversation = appState.conversations.first(where: { $0.id == conversationId }) else {
          log("Desktop automation: conversation \(conversationId) not found")
          return
        }
        present(conversation)
      }
    }
  }
  // MARK: - Main View with Recording Header + List

  private var mainConversationsView: some View {
    Group {
      if isLiveTranscriptExpanded && appState.isLiveCapturing {
        ConversationsLiveTranscriptFullScreen(
          onCollapse: {
            OmiMotion.withGated(.easeInOut(duration: 0.2)) {
              isLiveTranscriptExpanded = false
            }
          }
        )
        .transition(.opacity)
      } else {
        conversationsListLayout
      }
    }
    // Collapse if capture pauses (meeting ends) or the session stops while expanded.
    .onChange(of: appState.isLiveCapturing) { _, isLive in
      if !isLive {
        isLiveTranscriptExpanded = false
      }
    }
  }

  /// Compact workspace chrome followed by the scrolling live card + list.
  ///
  /// Brain navigation already names this destination, so repeating a large
  /// Conversations title and subtitle only pushes the first useful row down.
  /// Keep the page's refinements and actions pinned in one Activity-density
  /// command row instead.
  private var conversationsListLayout: some View {
    VStack(spacing: 0) {
      conversationQueryToolbar
        .pagePanelToolbarInsets(isBelowNavigation: brainDestination != nil)

      // The whole page below the command row scrolls together. Floating action bars
      // (load-more, merge) stay pinned to the bottom via the ZStack overlay.
      ZStack(alignment: .bottom) {
        scrollingBody
        floatingActionBars
      }
    }
  }

  /// Everything below the fixed header, rendered inside a single scroll so the
  /// live transcript, search bar, filters and conversation list all scroll
  /// together. When `embedded`, the parent owns the scroll and this renders bare.
  @ViewBuilder private var scrollingBody: some View {
    let content = VStack(spacing: 0) {
      // Live transcript while actually capturing. Only Meetings keeps a session
      // armed with the mic paused (`isAwaitingMeeting`); that is not Live.
      if appState.isLiveCapturing {
        ConversationsLiveTranscript(
          onExpand: {
            OmiMotion.withGated(.easeInOut(duration: 0.2)) {
              isLiveTranscriptExpanded = true
            }
          }
        )
        .padding(.horizontal, OmiSpacing.xxl)
        .padding(.top, OmiSpacing.md)
        .padding(.bottom, OmiSpacing.md)
        .transition(.opacity)
      } else if appState.isFinalizingCapture {
        // The Live card's slot stays occupied while the capture becomes a
        // row, so the meeting lands in place instead of vanishing and
        // reappearing further down.
        ConversationsSavingCaptureCard()
          .padding(.horizontal, OmiSpacing.xxl)
          .padding(.top, OmiSpacing.md)
          .padding(.bottom, OmiSpacing.md)
          .transition(.opacity)
      }

      conversationListSection
    }
    .omiAnimation(.easeInOut(duration: 0.25), value: appState.isLiveCapturing)
    .omiAnimation(.easeInOut(duration: 0.25), value: appState.isFinalizingCapture)

    if embedded {
      content
    } else {
      // minHeight = viewport keeps short/empty/loading states filling the
      // window (so their `maxHeight: .infinity` centering still works) while
      // taller content scrolls normally.
      GeometryReader { geo in
        ScrollView {
          content
            .frame(maxWidth: .infinity, minHeight: geo.size.height, alignment: .top)
        }
        .refreshable {
          await appState.refreshConversations()
        }
        .glassScrollFade()
      }
    }
  }

  /// Bottom-pinned floating controls that overlay the scroll (they must not
  /// scroll with the content). Load-more only applies to the main list; the
  /// merge bar applies to both list and search results.
  @ViewBuilder private var floatingActionBars: some View {
    if !embedded {
      if searchQuery.isEmpty && appState.canLoadMoreConversations
        && !(isMultiSelectMode && !selectedConversationIds.isEmpty)
      {
        Button {
          Task {
            await appState.loadMoreConversations()
          }
        } label: {
          Text("Load older conversations")
            .scaledFont(size: OmiType.caption, weight: .medium)
            .foregroundColor(Ink.primary)
            .padding(.horizontal, OmiSpacing.lg)
            .frame(height: 34)
            .glassFloatingBar(cornerRadius: 17)
        }
        .buttonStyle(.plain)
        .padding(.bottom, OmiSpacing.lg)
        .accessibilityIdentifier("conversations-load-more")
      }

      if isMultiSelectMode && !selectedConversationIds.isEmpty {
        mergeActionBar
          .transition(.move(edge: .bottom).combined(with: .opacity))
      }
    }
  }

  /// IDs of the conversations currently shown to the user — search results while
  /// a search is active, otherwise the full list. Used to scope "Select All".
  private var displayedConversationIds: [String] {
    searchQuery.isEmpty ? appState.conversations.map { $0.id } : visibleSearchResults.map { $0.id }
  }

  /// Search is text-only at the API boundary. Apply the same local refinements
  /// to the returned rows so search and list queries have identical AND
  /// semantics without inventing a second backend endpoint.
  private var visibleSearchResults: [ServerConversation] {
    ConversationSearchResultFilter.apply(
      searchResults,
      starredOnly: appState.showStarredOnly,
      date: appState.selectedDateFilter,
      folderId: appState.selectedFolderId
    )
  }

  /// Entry point for the multi-select / merge feature. Without this the whole
  /// merge UI (checkboxes, action bar, Merge button) was permanently unreachable
  /// because `isMultiSelectMode` was never set true anywhere.
  private var selectModeButton: some View {
    Button {
      OmiMotion.withGated(.easeInOut(duration: 0.2)) {
        isMultiSelectMode.toggle()
        if !isMultiSelectMode {
          selectedConversationIds.removeAll()
          showMergeConfirmation = false
        }
      }
    } label: {
      HStack(spacing: OmiSpacing.xs) {
        Image(systemName: isMultiSelectMode ? "checkmark.circle" : "checkmark.circle.badge.questionmark")
          .scaledFont(size: OmiType.caption)
        Text(isMultiSelectMode ? "Done" : "Select")
          .scaledFont(size: OmiType.body, weight: .medium)
      }
      .foregroundColor(isMultiSelectMode ? Ink.primary : Ink.secondary)
      .padding(.horizontal, OmiSpacing.md)
      .padding(.vertical, OmiSpacing.sm)
      .glassChip(isActive: isMultiSelectMode)
    }
    .buttonStyle(.plain)
    .help(isMultiSelectMode ? "Exit selection" : "Select conversations to merge")
    .accessibilityIdentifier("conversations-select-toggle")
  }

  // MARK: - Conversation List Section

  private var conversationListSection: some View {
    VStack(spacing: 0) {
      // Search stays in the shared top search surface on Brain pages. The
      // local search is retained for the standalone conversations surface.
      if brainDestination == nil {
        OmiSearchField(
          placeholder: "Search conversations",
          text: $searchQuery,
          isLoading: isSearching,
          searchSurface: .conversations
        )
        .onChange(of: searchQuery) { _, newValue in submitSearch(newValue) }
        .padding(.horizontal, QueryShellLayout.panelPaddingHorizontal)
        .padding(.bottom, OmiSpacing.sm)
      }

      // List - show search results or regular conversations. Both render
      // embedded (no inner ScrollView); the page's outer ScrollView (see
      // `scrollingBody`) owns scrolling so the whole page scrolls together.
      // Floating load-more / merge bars live in `floatingActionBars`.
      if DebouncedSearchCoordinator.isActive(searchQuery) {
        // Search results view
        searchResultsView
      } else {
        // A successful filtered request with no rows is different from an
        // account with no conversations. Keep the recovery action beside the
        // state that caused the empty result instead of suggesting recording.
        if appState.hasActiveConversationFilters && !appState.isLoadingConversations
          && appState.conversationsError == nil && appState.conversations.isEmpty
        {
          filteredConversationsEmptyView
        } else {
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
            embedded: true,
            appState: appState
          )
        }
      }
    }
  }

  // MARK: - Search Results View

  private var searchResultsView: some View {
    Group {
      if isSearching {
        VStack(spacing: OmiSpacing.md) {
          ProgressView()
          Text("Searching...")
            .scaledFont(size: OmiType.body)
            .foregroundColor(Ink.secondary)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
      } else if searchError != nil {
        VStack(spacing: OmiSpacing.md) {
          Image(systemName: "exclamationmark.triangle")
            .scaledFont(size: 32)
            .foregroundColor(Ink.secondary)
          Text("Couldn't search conversations. Check your connection and try again.")
            .scaledFont(size: OmiType.body)
            .foregroundColor(Ink.secondary)
            .multilineTextAlignment(.center)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .padding()
      } else if visibleSearchResults.isEmpty {
        VStack(spacing: OmiSpacing.md) {
          Image(systemName: "magnifyingglass")
            .scaledFont(size: 32)
            .foregroundColor(Ink.secondary)
          Text("No search results")
            .scaledFont(size: OmiType.heading, weight: .semibold)
            .foregroundColor(Ink.secondary)
          Text(
            appState.hasActiveConversationFilters
              ? "Nothing matches \(quotedSearchQuery) with your active filters."
              : "Nothing matches \(quotedSearchQuery). Try a different term."
          )
          .scaledFont(size: OmiType.body)
          .foregroundColor(Ink.secondary)
          .multilineTextAlignment(.center)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
      } else {
        // Renders bare — the page's outer ScrollView owns scrolling and the
        // merge bar floats via `floatingActionBars`.
        searchResultsContent
      }
    }
  }

  @ViewBuilder
  private var searchResultsContent: some View {
    LazyVStack(spacing: OmiSpacing.sm) {
      ForEach(visibleSearchResults) { conversation in
        ConversationRowView(
          conversation: conversation,
          onTap: {
            AnalyticsManager.shared.memoryListItemClicked(conversationId: conversation.id)
            SearchAnalytics.resultOpened(
              surface: .conversations,
              resultIndex: visibleSearchResults.firstIndex(where: { $0.id == conversation.id }),
              searchIsActive: true
            )
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
    .padding(.horizontal, PagePanelVerticalRhythm.horizontalPadding)
    .padding(.top, PagePanelVerticalRhythm.contentGap)
    .padding(.bottom, isMultiSelectMode && !selectedConversationIds.isEmpty ? 80 : OmiSpacing.lg)
  }

  // MARK: - Search

  private func submitSearch(_ query: String) {
    searchCoordinator.submit(query) { submittedQuery in
      performSearch(query: submittedQuery)
    }
  }

  private func performSearch(query: String) {
    guard !query.isEmpty else {
      appState.cancelConversationSearch()
      searchResults = []
      searchError = nil
      isSearching = false
      return
    }

    isSearching = true
    searchError = nil
    log("Search: Starting search for '\(query)'")

    Task {
      do {
        let result = try await appState.searchConversations(query)
        log("Search: Found \(result.count) results")
        searchResults = result
        isSearching = false
        SearchAnalytics.queryEntered(surface: .conversations, query: query, resultsCount: result.count)
      } catch is CancellationError {
        // A newer query owns the search UI now.
      } catch {
        logError("Search: Failed", error: error)
        searchError = UserFacingErrorPresentation.message(for: error, while: .conversationSearch)
        searchResults = []
        isSearching = false
        SearchAnalytics.queryEntered(surface: .conversations, query: query, resultsCount: 0)
      }
    }
  }

  // MARK: - Query Toolbar

  /// The toolbar makes collection scope and refinements explicit. A folder is
  /// a single Collection dimension; Starred is only a refinement, so it cannot
  /// appear as a second, competing tab.
  private var conversationQueryToolbar: some View {
    PageQueryToolbar(
      refinement: {
        conversationFiltersMenu
      },
      activeFilters: {
        ActivePageFilterStrip(
          filters: activeConversationFilters,
          onClearAll: { Task { await appState.clearFilters() } }
        )
      },
      actions: {
        if isMultiSelectMode {
          selectModeButton
        } else if !appState.conversations.isEmpty
          || (!appState.isTranscribing && audioRecordingMode == .always)
        {
          conversationMoreMenu
        }
      }
    )
  }

  private var conversationFiltersMenu: some View {
    Menu {
      Section("Collection") {
        Button {
          Task { await appState.setFolderFilter(nil) }
        } label: {
          HStack {
            Label("All collections", systemImage: "tray.2")
            Spacer()
            if appState.selectedFolderId == nil {
              Image(systemName: "checkmark")
            }
          }
        }

        ForEach(appState.folders) { folder in
          Button {
            Task {
              await appState.setFolderFilter(
                appState.selectedFolderId == folder.id ? nil : folder.id
              )
            }
          } label: {
            HStack {
              Text(folder.name)
              Spacer()
              if appState.selectedFolderId == folder.id {
                Image(systemName: "checkmark")
              }
            }
          }
        }
      }

      Section("Refine") {
        Button {
          Task {
            isFilteringStarred = true
            await appState.toggleStarredFilter()
            isFilteringStarred = false
          }
        } label: {
          Label(
            appState.showStarredOnly ? "Remove Starred filter" : "Starred",
            systemImage: appState.showStarredOnly ? "star.fill" : "star")
        }
        .disabled(isFilteringStarred)

        Button {
          showDatePicker = true
        } label: {
          Label(appState.selectedDateFilter == nil ? "Date…" : "Change date…", systemImage: "calendar")
        }
      }

      Section("Collections") {
        Button {
          showCreateFolderSheet = true
        } label: {
          Label("New collection…", systemImage: "plus")
        }

        if !appState.folders.isEmpty {
          Menu("Manage collections") {
            ForEach(appState.folders) { folder in
              Menu(folder.name) {
                Button("Edit…") { editingFolder = folder }
                Button("Delete…", role: .destructive) { deletingFolder = folder }
              }
            }
          }
        }
      }
    } label: {
      PageQueryControlLabel(
        icon: "line.3.horizontal.decrease",
        dimension: activeConversationFilterCount == 0 ? nil : "Filter",
        value: activeConversationFilterCount == 0
          ? "Filter" : "\(activeConversationFilterCount)",
        isActive: activeConversationFilterCount > 0,
        dimensionSeparator: " ·"
      )
    }
    .menuStyle(.button)
    .buttonStyle(.plain)
    .popover(isPresented: $showDatePicker) {
      datePickerPopover
    }
    .help("Filter conversations by collection, starred status, or date")
    .accessibilityIdentifier("conversations-filter-menu")
  }

  private var conversationMoreMenu: some View {
    Menu {
      if !appState.conversations.isEmpty {
        Button {
          OmiMotion.withGated(.easeInOut(duration: 0.2)) {
            isMultiSelectMode = true
          }
        } label: {
          Label("Select conversations…", systemImage: "checkmark.circle")
        }
      }

      if !appState.isTranscribing && audioRecordingMode == .always {
        Button {
          appState.startTranscription()
        } label: {
          Label("Start recording", systemImage: "mic.fill")
        }
      }
    } label: {
      PageQueryActionLabel(icon: "ellipsis", title: "More")
    }
    .menuStyle(.borderlessButton)
    .menuIndicator(.hidden)
    .fixedSize()
    .help("More conversation actions")
    .accessibilityLabel("More conversation actions")
    .accessibilityIdentifier("conversations-more-actions")
  }

  private var activeConversationFilters: [PageActiveFilter] {
    var filters: [PageActiveFilter] = []

    if appState.showStarredOnly {
      filters.append(
        PageActiveFilter(id: "starred", title: "Starred") {
          Task { await appState.toggleStarredFilter() }
        })
    }

    if let date = appState.selectedDateFilter {
      filters.append(
        PageActiveFilter(id: "date", title: formatFilterDate(date)) {
          Task { await appState.setDateFilter(nil) }
        })
    }

    if appState.selectedFolderId != nil {
      filters.append(
        PageActiveFilter(id: "collection", title: selectedCollectionName) {
          Task { await appState.setFolderFilter(nil) }
        })
    }

    return filters
  }

  private var activeConversationFilterCount: Int {
    (appState.showStarredOnly ? 1 : 0)
      + (appState.selectedDateFilter == nil ? 0 : 1)
      + (appState.selectedFolderId == nil ? 0 : 1)
  }

  private var selectedCollectionName: String {
    guard let selectedFolderId = appState.selectedFolderId else { return "All" }
    return appState.folders.first(where: { $0.id == selectedFolderId })?.name ?? "Selected"
  }

  private var filteredConversationsEmptyView: some View {
    VStack(spacing: OmiSpacing.md) {
      Image(systemName: "line.3.horizontal.decrease.circle")
        .scaledFont(size: 42)
        .foregroundColor(Ink.secondary)

      Text("No matching conversations")
        .scaledFont(size: OmiType.heading, weight: .semibold)
        .foregroundColor(Ink.primary)

      Text("Nothing matches \(activeConversationFilterDescription).")
        .scaledFont(size: OmiType.body)
        .foregroundColor(Ink.secondary)
        .multilineTextAlignment(.center)

      Button {
        Task { await appState.clearFilters() }
      } label: {
        PageQueryActionLabel(icon: "xmark.circle", title: "Clear filters", isPrimary: true)
      }
      .buttonStyle(.plain)
    }
    .frame(maxWidth: .infinity, maxHeight: .infinity)
    .padding(.horizontal, OmiSpacing.section)
    .padding(.top, PagePanelVerticalRhythm.contentGap)
    .padding(.bottom, PagePanelVerticalRhythm.contentBottomPadding)
    .accessibilityIdentifier("conversations-filtered-empty")
  }

  private var activeConversationFilterDescription: String {
    var filters: [String] = []
    if appState.showStarredOnly { filters.append("Starred") }
    if let date = appState.selectedDateFilter { filters.append("Date: \(formatFilterDate(date))") }
    if appState.selectedFolderId != nil { filters.append("Collection: \(selectedCollectionName)") }
    return filters.joined(separator: " and ")
  }

  private var quotedSearchQuery: String {
    let query = DebouncedSearchCoordinator.normalized(searchQuery)
    return "\u{201c}\(query)\u{201d}"
  }

  private var datePickerPopover: some View {
    VStack(spacing: OmiSpacing.md) {
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
    .background(Ink.surface)
  }

  private func formatFilterDate(_ date: Date) -> String {
    let formatter = DateFormatter()
    formatter.dateFormat = "MMM d"
    return formatter.string(from: date)
  }

  // MARK: - Merge Action Bar

  private var mergeActionBar: some View {
    HStack(spacing: OmiSpacing.lg) {
      // Selection count
      Text("\(selectedConversationIds.count) selected")
        .scaledFont(size: OmiType.body, weight: .medium)
        .foregroundColor(Ink.secondary)

      Spacer()

      // Select All / Deselect All — scoped to the CURRENTLY DISPLAYED list
      // (search results when searching, otherwise all conversations), so
      // "Select All" in search mode selects the results the user can see rather
      // than the entire conversation list.
      Button(action: {
        selectedConversationIds = ConversationMergeSelection.toggledSelectAll(
          displayedIds: displayedConversationIds,
          current: selectedConversationIds
        )
      }) {
        Text(
          ConversationMergeSelection.allDisplayedSelected(
            displayedIds: displayedConversationIds,
            current: selectedConversationIds
          ) ? "Deselect All" : "Select All"
        )
        .scaledFont(size: OmiType.caption, weight: .medium)
        .foregroundColor(Ink.secondary)
      }
      .buttonStyle(.plain)

      // Merge button (only enabled when 2+ selected)
      Button(action: {
        showMergeConfirmation = true
      }) {
        HStack(spacing: OmiSpacing.xs) {
          if isMerging {
            ProgressView()
              .scaleEffect(0.5)
              .frame(width: 14, height: 14)
          } else {
            Image(systemName: "arrow.triangle.merge")
              .scaledFont(size: OmiType.caption)
          }
          Text("Merge")
            .scaledFont(size: OmiType.body, weight: .semibold)
        }
        .foregroundColor(
          selectedConversationIds.count >= 2 ? Ink.surface : Ink.secondary
        )
        .padding(.horizontal, OmiSpacing.lg)
        .padding(.vertical, OmiSpacing.sm)
        .background(
          Capsule()
            .fill(selectedConversationIds.count >= 2 ? Ink.primary : Ink.rowFillHover)
        )
        .overlay(
          Capsule()
            .strokeBorder(
              selectedConversationIds.count >= 2 ? Color.clear : Ink.separator, lineWidth: 1)
        )
      }
      .buttonStyle(.plain)
      .disabled(selectedConversationIds.count < 2 || isMerging)
    }
    .padding(.horizontal, OmiSpacing.lg)
    .padding(.vertical, OmiSpacing.md)
    .glassFloatingBar()
    .padding(.horizontal, OmiSpacing.lg)
    .padding(.bottom, OmiSpacing.lg)
    .alert("Merge Conversations", isPresented: $showMergeConfirmation) {
      Button("Cancel", role: .cancel) {}
      Button("Merge") {
        Task {
          await performMerge()
        }
      }
    } message: {
      Text(
        "Are you sure you want to merge \(selectedConversationIds.count) conversations? This will combine them into a single conversation and delete the originals. This action cannot be undone."
      )
    }
    .alert(
      "Merge Failed",
      isPresented: .init(
        get: { mergeError != nil },
        set: { if !$0 { mergeError = nil } }
      )
    ) {
      Button("OK", role: .cancel) {}
    } message: {
      Text(mergeError ?? "Failed to merge conversations. Please try again.")
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
      OmiMotion.withGated(.easeInOut(duration: 0.2)) {
        isMultiSelectMode = false
        selectedConversationIds.removeAll()
      }
    } catch {
      logError("Merge failed", error: error)
      mergeError = UserFacingErrorPresentation.message(for: error, while: .conversationMerge)
    }

    isMerging = false
  }

}

// MARK: - Conversation Merge Selection

/// Pure selection logic for the conversation multi-select / merge feature.
/// Kept free of view state so it is unit-testable and so "Select All" is always
/// scoped to the list the user is actually looking at.
enum ConversationMergeSelection {
  /// Toggle "select all" over the currently displayed list. If every displayed
  /// id is already selected, deselect just those (leaving any selections from
  /// another view intact); otherwise add all displayed ids to the selection.
  static func toggledSelectAll(displayedIds: [String], current: Set<String>) -> Set<String> {
    let displayed = Set(displayedIds)
    guard !displayed.isEmpty else { return current }
    if displayed.isSubset(of: current) {
      return current.subtracting(displayed)
    }
    return current.union(displayed)
  }

  /// True when every currently displayed id is selected (drives the
  /// "Select All" / "Deselect All" label). False for an empty displayed list.
  static func allDisplayedSelected(displayedIds: [String], current: Set<String>) -> Bool {
    let displayed = Set(displayedIds)
    return !displayed.isEmpty && displayed.isSubset(of: current)
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
      .fill(isDragging ? Ink.secondary : Ink.separator)
      .frame(width: 1)
      .contentShape(Rectangle().inset(by: -4))  // Larger hit area
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

#if canImport(PreviewsMacros)
  #Preview {
    ConversationsPage(appState: AppState(), selectedConversation: .constant(nil))
      .frame(width: 600, height: 800)
      .background(Ink.rowFill)
  }
#endif
