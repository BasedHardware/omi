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
//  **This is the app's only chat destination**, which makes it the only place the controls of the
//  deleted standalone chat page can live (`6be26e85bc`; INV-NAV-1 forbids bringing that page back).
//  So this file also hosts: the chat overflow menu (copy / clear / AI settings), the way back into
//  the transcript after you navigate away, the provider's two chat-blocking product flows, and the
//  `home_*` automation entry points that used to land on the legacy hub. It adds no second
//  transcript, no second send path and no second turn handler — every one of them acts on the one
//  `ChatProvider` (INV-6).
//
//  Brand: `Ink` semantics only (INV-UI-1).
//

import AppKit
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
  /// Two seconds of "copied", which is the whole confirmation a pasteboard write gets.
  @State private var didCopyTranscript = false
  /// The last question that actually went. `Try again` re-sends *that* — the composer is emptied by
  /// the send now, so re-reading the bar would retry an empty string.
  @State private var lastAskedQuestion = ""
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
          isStopping: chatProvider.isStopping,
          mode: mode,
          attachments: chatProvider.pendingAttachments,
          onSearch: search,
          onAsk: ask,
          onStop: { chatProvider.stopAgent(owner: .mainChat) },
          onAttachmentsAdded: stageAttachments,
          onAttachmentRemoved: { chatProvider.removePendingAttachment(id: $0) }
        )
        QueryResultsPanel(
          request: $request,
          mode: mode,
          total: total,
          onExitAnswer: { showResults() },
          headerAccessory: { headerAccessory }
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
    .onAppear {
      isQueryFocused = true
      showOnboardingOpenerIfPresent()
    }
    // **The other half of `hidesOnDeactivate`.** The shell hides itself when you click away and the
    // next summon re-orders the *same* window forward rather than rebuilding this view, so `onAppear`
    // — the only thing that ever claimed the caret — never runs again. A summoned search surface that
    // swallows the first thing you type is the whole bug. Claiming it again is idempotent when the
    // field already has it.
    .onReceive(NotificationCenter.default.publisher(for: NSApplication.didBecomeActiveNotification)) { _ in
      isQueryFocused = true
    }
    .onChange(of: chatProvider.onboardingOpener == nil) { _, _ in showOnboardingOpenerIfPresent() }
    // The two product flows the provider drives and nothing renders. Both were hosted only by the
    // deleted chat page, so since that deletion a browser tool with no extension token has killed
    // the turn and offered no way to fix it, and the usage-cap nudge has fired into nothing. They
    // are hosted here because this is where chat is; the provider already foregrounds the window.
    .sheet(isPresented: $chatProvider.needsBrowserExtensionSetup) {
      BrowserExtensionSetup(
        onComplete: { chatProvider.needsBrowserExtensionSetup = false },
        onDismiss: { chatProvider.needsBrowserExtensionSetup = false },
        chatProvider: chatProvider
      )
      .fixedSize()
    }
    .alert("Upgrade Required", isPresented: $chatProvider.showOmiThresholdAlert) {
      Button("Upgrade to Omi Pro") {
        chatProvider.showOmiThresholdAlert = false
        if let url = URL(string: "https://omi.me/pricing") { NSWorkspace.shared.open(url) }
      }
      Button("Later", role: .cancel) { chatProvider.showOmiThresholdAlert = false }
    } message: {
      Text("Upgrade to Omi Pro for $199/month to continue chatting.")
    }
    // `home_open_chat` / `home_ask` / `home_attach` / `home_close_panel`. They were written against
    // the legacy hub and have been inert since Home became this surface — the bridge answered "ok"
    // and nothing happened, which is worse than an error. Each one runs the exact function its
    // on-screen control runs.
    .onReceive(NotificationCenter.default.publisher(for: .homeStageOpenChat)) { _ in
      guard !useLegacyHomeDesign else { return }
      showAnswer()
    }
    .onReceive(NotificationCenter.default.publisher(for: .homeStageClose)) { _ in
      guard !useLegacyHomeDesign else { return }
      showResults()
    }
    .onReceive(NotificationCenter.default.publisher(for: .homeStageAsk)) { note in
      guard !useLegacyHomeDesign, let query = note.userInfo?["query"] as? String else { return }
      request.text = query
      ask()
    }
    .onReceive(NotificationCenter.default.publisher(for: .homeStageAttach)) { note in
      guard !useLegacyHomeDesign, let path = note.userInfo?["path"] as? String else { return }
      stageAttachments([URL(fileURLWithPath: path)])
    }
    // Escape leaves answer mode before the shell's own Escape handler navigates anywhere, because the
    // answer *is* this page — there is nowhere else to go back to first.
    .onEscapeKey(priority: .content) {
      guard mode == .answer else { return false }
      showResults()
      return true
    }
    .task { await loadScreenCount() }
    // **No rule here reads an empty field as an instruction.** Emptying the bar used to eject you
    // from answer mode — so backspacing your last question to type a follow-up threw the conversation
    // off screen mid-edit, and the composer could never be cleared by the send either. `esc Results`
    // on the bar and `‹ Results` in the panel header are the two labelled ways out, and they are the
    // only two. See `QueryShellSubmission`.
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
        onOpenMemories: openMemories,
        onRetry: retry
      )
    }
  }

  // MARK: - The panel's chat controls

  /// The one slot the panel gives its host, filled differently per mode: on the list it is the way
  /// into the conversation, and in the conversation it is what you can do to it.
  @ViewBuilder
  private var headerAccessory: some View {
    switch mode {
    case .results:
      HStack(spacing: OmiSpacing.sm) {
        brainMapButton
        if HomeChatReentry.isOffered(
          messageCount: chatProvider.messages.count, isLoading: chatProvider.isLoading)
        {
          transcriptEntryButton
        }
      }
    case .answer:
      if menu.isPresentable {
        chatMenu
      }
    }
  }

  /// **The map, in the filter row — not a fifth chip.**
  ///
  /// The chips under this row all do one thing: narrow *these rows*, in place, leaving you on the
  /// same list. The Brain Map is not a subset of those rows — it is a second drawing of the same
  /// corpus, and it lives on a page that owns it. A control that sits among the chips, looks like
  /// them, and then navigates somewhere is the worse of the two available mistakes: it teaches the
  /// row a rule and then breaks it.
  ///
  /// So it goes in the header instead, where this panel already keeps the one other control that
  /// leaves the list for a surface that owns something (`Chat ›`), and wears that control's exact
  /// label. Leading rather than trailing so it never moves — `Chat ›` appears only once there is a
  /// transcript to go back to.
  ///
  /// It opens the *real* Brain Map on the Library page (INV-NAV-1). The hub's own switcher is still
  /// the mechanism that owns the destination; this is one more way in, never a smaller copy of it.
  private var brainMapButton: some View {
    Button(action: openBrainMap) {
      QueryPanelChipLabel(
        systemImage: "point.3.connected.trianglepath.dotted",
        title: "Brain Map",
        trailingSystemImage: "chevron.right")
    }
    .buttonStyle(.plain)
    .help("See how everything Omi has kept connects")
    .accessibilityIdentifier("query-shell-open-brain-map")
  }

  private var menu: HomeChatMenu {
    HomeChatMenu.resolve(
      messageCount: chatProvider.messages.count,
      isSending: chatProvider.isSending,
      isClearing: chatProvider.isClearing)
  }

  /// **The mirror of `‹ Results`.** Without it the transcript survives navigation and is invisible:
  /// the mode is view state, so leaving Home and coming back leaves you on the list with no control
  /// anywhere that admits a conversation exists. This is not a second destination — it is the same
  /// panel, the same provider and the same transcript, one chip away.
  private var transcriptEntryButton: some View {
    Button(action: showAnswer) {
      QueryPanelChipLabel(
        systemImage: "bubble.left.and.text.bubble.right",
        title: "Chat",
        trailingSystemImage: "chevron.right")
    }
    .buttonStyle(.plain)
    .help("Back to your conversation with omi")
    .accessibilityIdentifier("query-shell-open-chat")
  }

  /// Clear, copy and the jump to AI settings — the deleted chat page's last three controls, which
  /// have had nowhere to live since it went. An overflow rather than three icons in the header,
  /// because none of them is something you reach for during a conversation.
  private var chatMenu: some View {
    Menu {
      Button(didCopyTranscript ? "Copied" : "Copy conversation", action: copyTranscript)
        .disabled(!menu.canCopy)
      Button("Clear conversation", role: .destructive, action: clearTranscript)
        .disabled(!menu.canClear)
      Divider()
      // The deleted page's gear, with its own words ("Advanced AI settings"). It posts the shared
      // notification rather than routing itself, so it lands wherever `DesktopHomeView` already
      // sends that jump — today `.advanced`, which is the *visible* section holding AI Provider, the
      // Claude connection and the chat workspace directory. `SettingsSection.aiChat` is deliberately
      // absent from the sidebar and bounces to `.advanced` on production bundles; pointing a chat
      // control straight at it would be a menu item that silently lands somewhere else.
      Button("Advanced AI settings…") {
        NotificationCenter.default.post(name: .navigateToAIChatSettings, object: nil)
      }
    } label: {
      QueryPanelChipLabel(
        systemImage: didCopyTranscript ? "checkmark" : "ellipsis",
        isActive: chatProvider.isClearing)
    }
    .menuStyle(.borderlessButton)
    .menuIndicator(.hidden)
    .fixedSize()
    // Same override and same reason as `Filter ›`: a `Menu` label inherits the shell's `.tint`,
    // which on this surface is the accent that belongs to `⌘⏎ Ask` alone.
    .tint(Ink.primary)
    .help("Conversation actions")
    .accessibilityLabel("Conversation actions")
    .accessibilityIdentifier("query-shell-chat-menu")
  }

  private func copyTranscript() {
    let text = HomeChatTranscript.plainText(chatProvider.messages)
    guard !text.isEmpty else { return }
    NSPasteboard.general.clearContents()
    NSPasteboard.general.setString(text, forType: .string)
    AnalyticsManager.shared.shareAction(category: "main_chat_conversation_copy")
    didCopyTranscript = true
    DispatchQueue.main.asyncAfter(deadline: .now() + 2) { didCopyTranscript = false }
  }

  /// Clearing empties the one transcript, so the panel goes back to the list rather than sitting in
  /// answer mode staring at nothing it can explain.
  private func clearTranscript() {
    Task {
      await chatProvider.clearChat()
      await MainActor.run { showResults() }
    }
  }

  /// Staging goes through the provider, which owns the cap and the upload — the paperclip, a drop on
  /// the bar and the automation bridge all end here rather than each keeping their own list.
  private func stageAttachments(_ urls: [URL]) {
    let staged = urls.compactMap(ChatAttachment.from(url:))
    guard !staged.isEmpty else { return }
    chatProvider.addAttachments(staged)
  }

  /// The post-onboarding opener is a greeting with starters in it, and the only surface that can
  /// show it is the answer thread — so its arrival puts the panel there.
  private func showOnboardingOpenerIfPresent() {
    guard chatProvider.onboardingOpener != nil, mode != .answer else { return }
    showAnswer()
  }

  // MARK: - The two keys

  /// `⏎` — the panel is already filtering as you type, so this only has to put you back on the list.
  private func search() { submit(commandHeld: false) }

  /// `⌘⏎` — the same words, asked instead of matched.
  ///
  /// It sends through the one `ChatProvider` the composer and the floating bar send through, so the
  /// answer lands in the single transcript rather than in a second one this surface would own.
  private func ask() { submit(commandHeld: true) }

  /// Both keys, resolved by `QueryShellSubmission` rather than by two functions that each restate the
  /// trim, the empty guard and the mode change — which is how they drift.
  private func submit(commandHeld: Bool) {
    let submission = QueryShellSubmission.resolve(text: request.text, commandHeld: commandHeld)
    if request.text != submission.text { request.text = submission.text }
    guard let next = submission.mode else { return }
    setMode(next)
    guard let question = submission.question else { return }
    lastAskedQuestion = question
    send(question)
  }

  /// The one send. `Try again` on a failed turn enters here too, so a retry is the same turn through
  /// the same provider and never a second send path (INV-6).
  private func send(_ question: String) {
    OmiUISound.play(.commit)
    AnalyticsManager.shared.chatMessageSent(
      messageLength: question.count, hasSelectedAppContext: false, source: "query_shell")
    chatProvider.dismissOnboardingOpener()
    Task { await chatProvider.sendMessage(question) }
  }

  /// Re-sends the question that failed, not whatever the bar holds now — the send emptied it.
  private func retry() {
    guard !lastAskedQuestion.isEmpty else { return }
    showAnswer()
    send(lastAskedQuestion)
  }

  private func showResults() { setMode(.results) }

  private func showAnswer() { setMode(.answer) }

  /// **The caret belongs to the bar.** Both modes leave you about to type — a filter or a follow-up —
  /// so every transition hands it back. Only `⏎ Search` used to, which meant the two exits the
  /// surface advertises (`esc Results`, `‹ Results`) and a sent question all dropped it: you pressed
  /// the key the bar told you to press, and the next thing you typed went nowhere.
  private func setMode(_ next: QueryShellMode) {
    OmiMotion.withGated(.easeOut(duration: 0.16)) { mode = next }
    isQueryFocused = true
  }

  // MARK: - Where a row goes

  /// Opens the real Conversations page on the real conversation — never a copy of it here (INV-NAV-1).
  private func openConversation(_ id: String) {
    ConversationDetailAutomationState.shared.requestOpen(conversationId: id, showTranscript: false)
    navigate(.conversation)
  }

  private func openMemories() {
    navigate(.memories)
  }

  /// Where both of Home's ways into the graph land — the spine's end-of-day card and the header's
  /// `Brain Map ›`. One route, so the two controls cannot drift apart, and it goes to the surface
  /// that owns the map. The map is never a destination of this shell (INV-NAV-1).
  private func openBrainMap() {
    navigate(.brainMap)
  }

  private func openRewind() {
    navigate(.rewind)
  }

  /// The one place Home leaves Home. Every outbound control resolves its destination from
  /// `QueryShellRoute` rather than restating a rail index and a hub raw value at its own call site —
  /// which is how one of them ends up pointing somewhere the others do not.
  private func navigate(_ route: QueryShellRoute) {
    if let hubView = route.memoryDestination {
      memoryDestinationRawValue = hubView.rawValue
    }
    OmiUISound.play(.navigate)
    OmiMotion.withGated(.easeOut(duration: 0.08)) { selectedIndex = route.navItem.rawValue }
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
    // Rewind's pool opens asynchronously after launch, and this is a `.task` that runs once — so an
    // ask that lands before it is open under-reports the archive by its entire size for the rest of
    // the session. That is what made the corner read "390 results · of 147 captured": 147 was the
    // conversations and memories alone, with the whole screen archive counted as nothing.
    guard await SpineScreenIndex.poolWhenReady() != nil else {
      screenCount = 0
      return
    }
    screenCount = (try? await RewindDatabase.shared.getScreenshotCount()) ?? 0
  }
}
