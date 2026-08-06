//
//  QueryShellHome.swift — Home, as a search surface.
//
//  **Two glass objects with twelve points of air between them**: a bar you type into, and a panel that
//  answers. That gap is the design. Welded into one slab the surface reads as a form; apart, it reads
//  as a query pointed at a corpus, which is what it is.
//
//  Home was a hub of widgets with a chat under it. Search absorbs the hub — you do not browse a
//  destination called Memory when the field in front of you already returns memories — so what is left
//  is the field, the things it found, and one key (`⌘⏎`) that turns the same words into a question.
//
//  It paints **no background**. The window's ground is AppKit's (`ShellGlassGround`); the two panels
//  here wear the app's glass through `inkGlassPanel` and nothing else does.
//
//  The legacy hub is still here, behind the `useLegacyHomeDesign` setting that already gated it, so
//  the change is reversible by the person it happened to rather than by a rebuild.
//
//  Brand: `Ink` semantics only (INV-UI-1).
//

import OmiTheme
import SwiftUI

struct QueryShellHome: View {
  @ObservedObject var viewModel: DashboardViewModel
  @ObservedObject var homeStatusStore: HomeStatusStore = HomeStatusStore()
  @ObservedObject var appState: AppState
  @ObservedObject var appProvider: AppProvider
  @ObservedObject var chatProvider: ChatProvider
  @ObservedObject var memoriesViewModel: MemoriesViewModel
  var taskChatCoordinator: TaskChatCoordinator? = nil
  @Binding var selectedIndex: Int

  @AppStorage("useLegacyHomeDesign") private var useLegacyHomeDesign = false
  @AppStorage(MemoryHubDestination.storageKey) private var memoryDestinationRawValue =
    MemoryHubDestination.memories.rawValue

  @State private var request = QueryShellRequest()
  @State private var mode: QueryShellMode = .results
  @State private var screenCount: Int?
  @FocusState private var isQueryFocused: Bool

  var body: some View {
    if useLegacyHomeDesign {
      DashboardPage(
        viewModel: viewModel,
        homeStatusStore: homeStatusStore,
        appState: appState,
        appProvider: appProvider,
        chatProvider: chatProvider,
        memoriesViewModel: memoriesViewModel,
        taskChatCoordinator: taskChatCoordinator,
        selectedIndex: $selectedIndex)
    } else {
      querySurface
    }
  }

  private var querySurface: some View {
    GeometryReader { proxy in
      let lane = QueryShellLayout.laneWidth(for: proxy.size.width)
      VStack(spacing: QueryShellLayout.panelGap) {
        QueryHeroBar(
          text: $request.text,
          focus: $isQueryFocused,
          isWorking: chatProvider.isSending,
          mode: mode,
          onSearch: search,
          onAsk: ask
        )
        QueryResultsPanel(
          request: $request,
          mode: mode,
          total: total,
          onExitAnswer: { showResults() }
        ) {
          panelBody
        }
        Spacer(minLength: 0)
      }
      .frame(width: lane)
      .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
      .padding(.top, OmiSpacing.sm)
    }
    // A typed character belongs in the field even when the field is not focused: this is a search
    // surface, and a search surface that swallows the first letter you type is broken.
    .onAppear { isQueryFocused = true }
    // Escape leaves answer mode before the shell's own Escape handler navigates anywhere, because the
    // answer *is* this page — there is nowhere else to go back to first.
    .onEscapeKey(priority: .content) {
      guard mode == .answer else { return false }
      showResults()
      return true
    }
    .task { await loadScreenCount() }
    .onChange(of: request.text) { _, newValue in
      // Clearing the field leaves the answer behind, which would otherwise strand you in a mode with
      // nothing on screen explaining why the list is gone.
      if newValue.isEmpty, mode == .answer { mode = .results }
    }
  }

  @ViewBuilder
  private var panelBody: some View {
    switch mode {
    case .results:
      // The seam's occupant: one merged chronological spine — a conversation, the memories it
      // produced and the screen you were on, in the order they happened. See `SpineStream`.
      SpineStream(
        request: request,
        appState: appState,
        memoriesViewModel: memoriesViewModel,
        onOpenConversation: openConversation,
        onOpenBrainMap: openBrainMap,
        onOpenRewind: openRewind
      )
    case .answer:
      QueryAnswerThread(
        chatProvider: chatProvider,
        onOpenConversation: openConversation,
        onOpenMemories: openMemories
      )
    }
  }

  // MARK: - The two keys

  /// `⏎` — the panel is already filtering as you type, so this only has to put you back on the list
  /// and keep the caret where you are still typing.
  private func search() {
    showResults()
    isQueryFocused = true
  }

  /// `⌘⏎` — the same words, asked instead of matched.
  ///
  /// It sends through the one `ChatProvider` the composer and the floating bar send through, so the
  /// answer lands in the single transcript rather than in a second one this surface would own.
  private func ask() {
    let question = request.text.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !question.isEmpty else { return }
    OmiUISound.play(.commit)
    AnalyticsManager.shared.chatMessageSent(
      messageLength: question.count, hasSelectedAppContext: false, source: "query_shell")
    OmiMotion.withGated(.easeOut(duration: 0.16)) { mode = .answer }
    Task { await chatProvider.sendMessage(question) }
  }

  private func showResults() {
    OmiMotion.withGated(.easeOut(duration: 0.16)) { mode = .results }
  }

  // MARK: - Where a row goes

  /// Opens the real Conversations page on the real conversation — never a copy of it here (INV-NAV-1).
  private func openConversation(_ id: String) {
    ConversationDetailAutomationState.shared.requestOpen(conversationId: id, showTranscript: false)
    memoryDestinationRawValue = MemoryHubDestination.conversations.rawValue
    navigate(to: .conversations)
  }

  private func openMemories() {
    memoryDestinationRawValue = MemoryHubDestination.memories.rawValue
    navigate(to: .conversations)
  }

  /// The spine's end-of-day card is the only way into the graph from here, and it goes to the
  /// surface that owns it. The map is never a destination of this shell (INV-NAV-1).
  private func openBrainMap() {
    memoryDestinationRawValue = MemoryHubDestination.brainMap.rawValue
    navigate(to: .conversations)
  }

  private func openRewind() {
    navigate(to: .rewind)
  }

  private func navigate(to item: SidebarNavItem) {
    OmiUISound.play(.navigate)
    OmiMotion.withGated(.easeOut(duration: 0.08)) { selectedIndex = item.rawValue }
  }

  // MARK: - The corpus

  /// What the count line in the panel's corner is a fraction of: everything Omi is holding.
  ///
  /// `nil` until the screen count comes back, so the line says it is still counting rather than
  /// confidently under-reporting by the size of the whole Rewind archive.
  private var total: Int? {
    guard let screenCount else { return nil }
    let conversations = appState.conversations.filter { $0.deleted != true }.count
    return conversations + memoriesViewModel.memories.count + screenCount
  }

  private func loadScreenCount() async {
    screenCount = (try? await RewindDatabase.shared.getScreenshotCount()) ?? 0
  }
}
