//
//  QueryShellHome.swift — Home, as a search surface.
//
//  **While you are searching: two glass objects with twelve points of air between them** — a bar you
//  type into, and a panel that answers. That gap is the design. Welded into one slab the surface reads
//  as a form; apart, it reads as a query pointed at a corpus, which is what it is.
//
//  **Once a conversation is open: one panel.** The bar comes down inside it and pins itself under the
//  transcript, and the search affordance goes with it — a chat you have already opened is not
//  searching, and an input above the thing it is replying to is not a chat. The top bar is untouched
//  either way. It is the same composer in both, not two (`QueryComposerPlacement`).
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
  @ObservedObject private var tasksStore = TasksStore.shared
  var taskChatCoordinator: TaskChatCoordinator? = nil
  /// The cohort shell keeps the existing modern Home presentation even when the reversible legacy
  /// preference is enabled. This is presentation-only; capability sampling and rich-block access
  /// remain owned by `ChatFirstShell`.
  var forceModernPresentation: Bool = false
  /// Non-nil only for the sampled Chat-first main-chat surface. It enables the existing inline entity
  /// controls without creating another provider or transcript.
  var chatFirstRichBlockContext: ChatFirstRichBlockContext? = nil
  @Binding var selectedIndex: Int

  @AppStorage("useLegacyHomeDesign") private var useLegacyHomeDesign = false
  @AppStorage(MemoryHubDestination.storageKey) private var memoryDestinationRawValue =
    MemoryHubDestination.memories.rawValue

  /// **The shell owns the filters. It does not own the query text.**
  ///
  /// The text is `chatProvider.draftText` — the one composer draft, which is also what persistence
  /// restores, what a send clears and what the automation bridge writes. This surface used to keep a
  /// private `@State` copy of it, so the bar drew one variable while the rest of the app read
  /// another: `set_chat_drafts` reported a draft stored and the bar went on showing its placeholder,
  /// and any test asserting composer behaviour through the bridge was asserting on a variable nothing
  /// rendered. A `QueryShellRequest` is assembled per render from the draft plus these.
  @State private var filters = QueryShellFilters()
  @State private var mode: QueryShellMode = .results
  @State private var screenCount: Int?
  /// Two seconds of "copied", which is the whole confirmation a pasteboard write gets.
  @State private var didCopyTranscript = false
  /// The last question that actually went. `Try again` re-sends *that* — the composer is emptied by
  /// the send now, so re-reading the bar would retry an empty string.
  @State private var lastAskedQuestion = ""
  /// The composer's measured height, so the panel's body can end inside the window.
  ///
  /// Measured rather than assumed: the composer is at its resting height most of the time but grows
  /// with a staged-file row, with a second line of draft and with the reader's font scale, and a
  /// reserve that ignores that is a reserve that puts the panel back off the bottom edge the first
  /// time somebody drops a file on it. The reporter is a `background` `GeometryReader`, which cannot
  /// affect layout, and the value it feeds only ever flows *downwards* — the composer's height never
  /// depends on the panel's — so there is no measurement loop. One state for both placements, because
  /// there is only ever one composer on screen (`QueryComposerPlacement`).
  @State private var composerHeight: CGFloat = QueryShellLayout.barMinHeight
  /// **The caret, as a claim rather than a flag.** Monotonic, and every increment lands the caret in
  /// the bar. `@FocusState` cannot do that job any more: the field is an `NSTextView` that SwiftUI's
  /// `.focused()` does not reach, and a flag already `true` could never re-claim a caret AppKit had
  /// since given away — which is precisely the case the `didBecomeActive` claim below exists for.
  @State private var caretClaims = 0

  private var usesLegacyPresentation: Bool {
    useLegacyHomeDesign && !forceModernPresentation
  }

  var body: some View {
    if usesLegacyPresentation {
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
      let bodyHeight = QueryShellLayout.panelBodyHeight(
        availableHeight: proxy.size.height,
        composerHeight: composerHeight,
        mode: mode)
      // **Only this column is woken by a keystroke.** The composer draft is not published on
      // `ChatProvider` (see `ChatComposerDraft`), so subscribing to it here keeps typing out of the
      // shell and the transcript while still giving the bar — and the list it filters — the live text.
      ChatDraftScope(draft: chatProvider.composerDraft) { draft in
        VStack(spacing: QueryShellLayout.panelGap) {
          // **The search bar exists while you are searching.** In answer mode it is not hidden,
          // moved or restyled in place — the same view is mounted inside the panel below instead, so
          // the surface reads as one chat window with its input under the transcript rather than as
          // a conversation with a search field parked on top of it.
          if QueryComposerPlacement.of(mode) == .hero {
            composerBar(draft: draft)
          }
          QueryResultsPanel(
            request: requestBinding(text: draft),
            mode: mode,
            total: total,
            onExitAnswer: { showResults() },
            bodyHeight: bodyHeight,
            headerAccessory: { headerAccessory },
            footer: {
              if QueryComposerPlacement.of(mode) == .panelFooter {
                composerBar(draft: draft)
              }
            }
          ) {
            panelBody(request: QueryShellRequest(text: draft.wrappedValue, filters: filters))
          }
          Spacer(minLength: 0)
        }
        .onPreferenceChange(QueryComposerHeightKey.self) { measured in
          guard measured > 0, measured != composerHeight else { return }
          composerHeight = measured
        }
        .frame(width: lane)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
        .padding(.top, OmiSpacing.sm)
      }
    }
    // A typed character belongs in the field even when the field is not focused: this is a search
    // surface, and a search surface that swallows the first letter you type is broken.
    .onAppear {
      claimCaret()
      showOnboardingOpenerIfPresent()
    }
    // **Coming back to Omi puts the caret back in the field.** This surface's whole job is to be typed
    // into, and re-activating the app is the one moment it is certain the person is here to type.
    // `onAppear` claims the caret exactly once — the page `switch` in `DesktopHomeView` only rebuilds
    // this view on a tab change — so anything that took the keyboard away in between (another app
    // becoming key, a sheet, a menu) left the field cold and the next thing typed went nowhere.
    // Harmless when the field already has it — the claim is a no-op once the caret is already there.
    .onReceive(NotificationCenter.default.publisher(for: NSApplication.didBecomeActiveNotification)) { _ in
      claimCaret()
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
    //
    // **`home_connect_toggle` is deliberately not among them.** It is the fifth of that set, and it
    // is missing here because this surface has nothing for it to run: there is no Connect tray and no
    // control that opens one, since connectors and export destinations live on the Apps page (its own
    // pill, and `navigate apps` from the bridge). Handing it `navigate(.apps)` would put the "toggle"
    // name over a different destination and let a flow assert a tray while watching another page, so
    // the bridge refuses it here instead — keyed on the stage mode this surface never publishes.
    // See `DesktopAutomationActionRegistry.registerBuiltins`.
    .onReceive(NotificationCenter.default.publisher(for: .homeStageOpenChat)) { _ in
      guard !usesLegacyPresentation else { return }
      showAnswer()
    }
    .onReceive(NotificationCenter.default.publisher(for: .homeStageClose)) { _ in
      guard !usesLegacyPresentation else { return }
      showResults()
    }
    .onReceive(NotificationCenter.default.publisher(for: .homeStageAsk)) { note in
      guard !usesLegacyPresentation, let query = note.userInfo?["query"] as? String else { return }
      chatProvider.draftText = query
      ask()
    }
    .onReceive(NotificationCenter.default.publisher(for: .homeStageAttach)) { note in
      guard !usesLegacyPresentation, let path = note.userInfo?["path"] as? String else { return }
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

  /// **The one composer, built once and mounted wherever the mode puts it.**
  ///
  /// Two call sites, one function: a second `QueryHeroBar(...)` written out for the panel would be a
  /// second set of closures wired to the same provider, and the first thing to drift would be which
  /// of them still stages an attachment or still stops a turn. The caret claim, the draft binding and
  /// the send are the same values in both placements — only `mode` differs, and it is read rather
  /// than passed.
  @ViewBuilder
  private func composerBar(draft: Binding<String>) -> some View {
    QueryHeroBar(
      text: draft,
      caretClaim: caretClaims,
      isWorking: chatProvider.isSending,
      isStopping: chatProvider.isStopping,
      mode: mode,
      attachments: chatProvider.pendingAttachments,
      onAsk: ask,
      onStop: { chatProvider.stopAgent(owner: .mainChat) },
      onAttachmentsAdded: stageAttachments,
      onAttachmentRemoved: { chatProvider.removePendingAttachment(id: $0) }
    )
    .background {
      GeometryReader { composer in
        Color.clear.preference(key: QueryComposerHeightKey.self, value: composer.size.height)
      }
    }
  }

  /// The seam value the panel and its body are handed, **assembled rather than stored**: the text
  /// half has an owner already (`chatProvider.composerDraft`) and a second copy of it here is the
  /// two-variables defect this surface shipped with.
  private func requestBinding(text: Binding<String>) -> Binding<QueryShellRequest> {
    Binding(
      get: { QueryShellRequest(text: text.wrappedValue, filters: filters) },
      set: { next in
        if next.text != text.wrappedValue { text.wrappedValue = next.text }
        filters = next.filters
      })
  }

  @ViewBuilder
  private func panelBody(request: QueryShellRequest) -> some View {
    switch mode {
    case .results:
      // The seam's occupant: one merged chronological spine — a conversation, the memories and
      // tasks it produced, and the screen you were on, in the order they happened. See `SpineStream`.
      SpineStream(
        request: request,
        appState: appState,
        memoriesViewModel: memoriesViewModel,
        tasksStore: tasksStore,
        onOpenConversation: openConversation,
        onOpenBrainMap: openBrainMap,
        onOpenRewind: openRewind
      )
    case .answer:
      QueryAnswerThread(
        chatProvider: chatProvider,
        onOpenConversation: openConversation,
        onOpenMemories: openMemories,
        onRetry: retry,
        chatFirstRichBlockContext: chatFirstRichBlockContext
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

  // MARK: - The one key

  /// **`⏎` — the words, asked.**
  ///
  /// There is no second key any more. Searching was never a key: the spine under the bar is rebuilt
  /// from the live draft on every render, so it narrows as each character lands, and the `⏎ Search`
  /// button that used to sit here committed to a filter the panel had already applied. `⌘⏎` is the
  /// `keyboardShortcut` on the primary and lands in this same function.
  ///
  /// It sends through the one `ChatProvider` the composer and the floating bar send through, so the
  /// answer lands in the single transcript rather than in a second one this surface would own
  /// (INV-6).
  private func ask() { submit() }

  /// Resolved by `QueryShellSubmission` rather than restated here, so the trim, the empty guard and
  /// the mode change cannot drift away from the value that defines them.
  private func submit() {
    let submission = QueryShellSubmission.resolve(text: chatProvider.draftText)
    if chatProvider.draftText != submission.text { chatProvider.draftText = submission.text }
    guard let next = submission.mode else { return }
    setMode(next)
    guard let question = submission.question else { return }
    lastAskedQuestion = question
    send(question)
  }

  /// The one send. `Try again` on a failed turn enters here too, so a retry is the same turn through
  /// the same provider and never a second send path (INV-6).
  private func send(_ question: String) {
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
    claimCaret()
  }

  /// Asks for the caret. Monotonic, so a claim is never swallowed for already having been made — the
  /// bar can be cold while this view still believes it is focused, which is the state every one of
  /// these call sites is written for.
  private func claimCaret() {
    caretClaims &+= 1
  }

  // MARK: - Where a row goes

  /// Opens the real Conversations page on the real conversation — never a copy of it here (INV-NAV-1).
  private func openConversation(_ id: String) {
    ConversationDetailAutomationState.shared.requestOpen(conversationId: id, showTranscript: false)
    navigate(.conversation)
  }

  private func openConversationSource(_ id: String, transcriptSegmentIds: [String]) {
    ConversationDetailAutomationState.shared.requestOpen(
      conversationId: id,
      showTranscript: true,
      transcriptSegmentIds: transcriptSegmentIds
    )
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
    let tasks = tasksStore.tasks.filter { !$0.isRetired }.count
    return conversations + memoriesViewModel.memories.count + tasks + screenCount
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

/// The composer's height, reported up to the surface that has to fit a panel around it.
///
/// `max` rather than last-writer-wins: only one composer is mounted at a time, but a preference that
/// reduced to the newest value would let a transient zero from a view being torn down — which is
/// exactly what a mode change does to the placement it is leaving — shrink the reserve and let the
/// panel run off the window for a frame.
private struct QueryComposerHeightKey: PreferenceKey {
  static let defaultValue: CGFloat = 0
  static func reduce(value: inout CGFloat, nextValue: () -> CGFloat) {
    value = max(value, nextValue())
  }
}
