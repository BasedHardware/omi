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
  let onOpenConversation: (String) -> Void
  let onOpenBrainMap: () -> Void
  let onOpenRewind: () -> Void

  @ObservedObject private var tasksStore = TasksStore.shared
  @State private var filters = QueryShellFilters()
  @State private var screenCount: Int?

  var body: some View {
    GeometryReader { proxy in
      let lane = QueryShellLayout.laneWidth(for: proxy.size.width)
      // The panel arithmetic without the hero reserve: this host mounts no composer, so the body
      // gets the room `panelBodyHeight` would have set aside for one.
      let room =
        proxy.size.height - QueryShellLayout.surfaceTopInset
        - QueryShellLayout.panelChromeHeight(mode: .results, composerHeight: 0)
      let bodyHeight = min(
        QueryShellLayout.maximumBodyHeight, max(QueryShellLayout.minimumBodyHeight, room))
      QueryResultsPanel(
        request: requestBinding,
        mode: .results,
        total: total,
        onExitAnswer: nil,
        bodyHeight: bodyHeight,
        headerAccessory: { EmptyView() },
        footer: { EmptyView() }
      ) {
        SpineStream(
          request: QueryShellRequest(text: "", filters: filters),
          appState: appState,
          memoriesViewModel: memoriesViewModel,
          tasksStore: tasksStore,
          onOpenConversation: onOpenConversation,
          onOpenBrainMap: onOpenBrainMap,
          onOpenRewind: onOpenRewind
        )
      }
      .frame(width: lane)
      .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
      .padding(.top, QueryShellLayout.surfaceTopInset)
    }
    .task { await loadScreenCount() }
  }

  private var requestBinding: Binding<QueryShellRequest> {
    Binding(
      get: { QueryShellRequest(text: "", filters: filters) },
      set: { filters = $0.filters })
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
