import OmiTheme
import SwiftUI

/// The Activity destination inside the Memory hub: the chronological spine that used to be Home's
/// landing surface, wearing the same panel chrome (time filter, kind chips, corpus count) it wore
/// there. Home now lands in the conversation (`QueryShellMode.homeDefault`); this is where the
/// timeline went.
///
/// Deliberately **not** `QueryShellHome`: that surface is the app's one chat destination (INV-NAV-1)
/// and mounts the one composer. This host has no composer and no answer mode — it is the `.results`
/// body only, so the hub cannot grow a second chat.
struct ActivityHubTab: View {
  @ObservedObject var appState: AppState
  @ObservedObject var memoriesViewModel: MemoriesViewModel
  let onOpenConversation: (ServerConversation) -> Void
  let onOpenMemory: (SpineMemory) -> Void
  let onOpenBrainMap: () -> Void
  let onOpenRewind: () -> Void
  let selectedDestination: MemoryHubDestination
  let onSelectDestination: (MemoryHubDestination) -> Void

  @ObservedObject private var tasksStore = TasksStore.shared
  @ObservedObject private var failurePlacement = HomeFailurePlacementStore.shared
  @ObservedObject private var placementAuth = AuthState.shared
  @StateObject private var attention = AttentionLedgerStore()
  @State private var filters = QueryShellFilters()
  @State private var searchText = ""
  @State private var screenCount: Int?

  var body: some View {
    GeometryReader { proxy in
      let failedRows = failurePlacement.activity(appState.conversations).filter {
        !attention.conversationIds.contains($0.id)
      }
      let hasLedger = failurePlacement.enabled && (!attention.rows.isEmpty || attention.loadFailed)
      let lane = QueryShellLayout.laneWidth(for: proxy.size.width)
      // The panel arithmetic with the search bar in the hero slot but no composer inside the panel.
      let room =
        proxy.size.height - QueryShellLayout.surfaceTopInset
        - QueryShellLayout.barMinHeight
        - QueryShellLayout.panelGap
        - BrainSectionPageMetrics.navigationHeight
        - QueryShellLayout.panelChromeHeight(mode: .results, composerHeight: 0)
      let bodyHeight = min(
        QueryShellLayout.maximumBodyHeight, max(QueryShellLayout.minimumBodyHeight, room))
      VStack(spacing: QueryShellLayout.panelGap) {
        searchBar
        QueryResultsPanel(
          request: requestBinding,
          mode: .results,
          total: total,
          onExitAnswer: nil,
          bodyHeight: bodyHeight,
          chipBehavior: .none,
          topAccessory: {
            BrainSectionNavigation(
              selected: selectedDestination,
              onSelect: onSelectDestination
            )
          },
          headerAccessory: { EmptyView() },
          footer: { EmptyView() }
        ) {
          VStack(alignment: .leading, spacing: 12) {
            if hasLedger || !failedRows.isEmpty {
              ScrollView {
                VStack(alignment: .leading, spacing: 12) {
                  if hasLedger { AttentionLedgerSection(store: attention, onOpen: openAttentionConversation) }
                  FailedConversationsActivitySection(
                    conversations: failedRows,
                    showHeader: !hasLedger,
                    onOpen: onOpenConversation,
                    retry: { conversation in
                      let updated = try await APIClient.shared.reprocessConversation(conversationId: conversation.id)
                      appState.replaceConversation(updated)
                      failurePlacement.remember([updated], for: AuthState.shared.userId)
                    }
                  )
                }
              }.frame(maxHeight: 260)
            }
            SpineStream(
              request: QueryShellRequest(text: searchText, filters: filters),
              appState: appState,
              memoriesViewModel: memoriesViewModel,
              tasksStore: tasksStore,
              searchSurface: .activity,
              onOpenConversation: onOpenConversation,
              onOpenMemory: onOpenMemory,
              onOpenBrainMap: onOpenBrainMap,
              onOpenRewind: onOpenRewind
            )
          }
        }
        Spacer(minLength: 0)
      }
      .frame(width: lane)
      .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
      .padding(.top, QueryShellLayout.surfaceTopInset)
    }
    .task { await loadScreenCount() }
    .task(id: placementAuth.userId) {
      let owner = placementAuth.userId
      await refreshAttention()
      failurePlacement.remember(appState.conversations, for: owner)
    }
    .onReceive(appState.$conversations) { rows in
      failurePlacement.remember(rows, for: placementAuth.userId)
    }
    .onReceive(NotificationCenter.default.publisher(for: .runtimeOwnerDidChange)) { _ in
      failurePlacement.reset()
      attention.reset()
      Task { await refreshAttention() }
    }
    .onReceive(NotificationCenter.default.publisher(for: NSApplication.didBecomeActiveNotification)) { _ in
      Task { await refreshAttention() }
    }
  }

  private func refreshAttention() async {
    await failurePlacement.refresh()
    if failurePlacement.enabled { await attention.refresh() } else { attention.reset() }
  }

  private func openAttentionConversation(_ id: String) {
    if let loaded = appState.conversations.first(where: { $0.id == id }) {
      onOpenConversation(loaded)
      return
    }
    Task {
      if let conversation = try? await APIClient.shared.getConversation(id: id) { onOpenConversation(conversation) }
    }
  }

  private var searchBar: some View {
    QuerySearchBar(
      text: $searchText,
      accessibilityID: "activity-search-field",
      placeholder: "Search activity",
      focus: nil,
      searchSurface: .activity
    )
  }

  private var requestBinding: Binding<QueryShellRequest> {
    Binding(
      get: { QueryShellRequest(text: searchText, filters: filters) },
      set: { next in
        searchText = next.text
        filters = next.filters
      })
  }

  /// Same corpus arithmetic as Home's count line, minus nothing: the hub shows the same account.
  private var total: Int? {
    guard let screenCount else { return nil }
    let conversations = appState.conversations.filter { $0.deleted != true }.count
    let tasks = tasksStore.tasks.filter { !$0.isRetired }.count
    return conversations + memoriesViewModel.memories.count + tasks + screenCount
  }

  private func loadScreenCount() async {
    guard await SpineScreenIndex.poolWhenReady() != nil else {
      screenCount = 0
      return
    }
    screenCount = (try? await RewindDatabase.shared.getScreenshotCount()) ?? 0
  }
}
