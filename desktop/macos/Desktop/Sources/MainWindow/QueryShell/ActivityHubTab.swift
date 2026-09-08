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
  let appState: AppState
  @ObservedObject var memoriesViewModel: MemoriesViewModel
  let onOpenConversation: (ServerConversation) -> Void
  let onOpenMemory: (SpineMemory) -> Void
  let onOpenBrainMap: () -> Void
  let onOpenRewind: () -> Void
  let selectedDestination: MemoryHubDestination
  let onSelectDestination: (MemoryHubDestination) -> Void

  @ObservedObject private var tasksStore = TasksStore.shared
  @State private var filters = QueryShellFilters()
  @State private var searchText = ""
  @State private var screenCount: Int?

  var body: some View {
    GeometryReader { proxy in
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
        Spacer(minLength: 0)
      }
      .frame(width: lane)
      .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
      .padding(.top, QueryShellLayout.surfaceTopInset)
    }
    .task { await loadScreenCount() }
  }

  private var searchBar: some View {
    QuerySearchBar(
      text: $searchText,
      accessibilityID: "activity-search-field",
      placeholder: "Search activity…",
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
