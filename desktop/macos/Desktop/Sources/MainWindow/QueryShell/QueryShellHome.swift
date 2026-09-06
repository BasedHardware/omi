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
  /// Typed navigation and the interactable content-block controls. Every Chat
  /// surface has one; it creates no second provider or transcript.
  let chatFirstRichBlockContext: ChatFirstRichBlockContext

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
  /// The always-visible search bar's text. Not the chat draft: the one chat composer lives inside
  /// the panel (INV-6) and keeps `chatProvider.composerDraft`; this field only narrows the spine.
  @State private var searchText = ""
  // Home IS the conversation. The panel rests on the chat and shows search results only while the
  // search bar above it holds text — clearing the field (or esc) always lands back on the chat.
  // There is no stored mode, so no bridge action or stale state can strand the page on the list.
  private var mode: QueryShellMode {
    searchText.isEmpty ? QueryShellMode.homeDefault : .results
  }
  @State private var screenCount: Int?
  /// Two seconds of "copied", which is the whole confirmation a pasteboard write gets.
  @State private var didCopyTranscript = false
  /// The last question that actually went. `Try again` re-sends *that* — the composer is emptied by
  /// the send now, so re-reading the bar would retry an empty string.
  @State private var sendLedger = QueryShellSendLedger()
  /// The composer's measured height, so the panel's body can end inside the window.
  ///
  /// Measured rather than assumed: the composer is at its resting height most of the time but grows
  /// with a staged-file row, with a second line of draft and with the reader's font scale, and a
  /// reserve that ignores that is a reserve that puts the panel back off the bottom edge the first
  /// time somebody drops a file on it. The reporter is `onGeometryChange`, which cannot affect
  /// layout, and the value it feeds only ever flows *downwards* — the composer's height never
  /// depends on the panel's — so there is no measurement loop. One state for both placements,
  /// because there is only ever one composer on screen (`QueryComposerPlacement`).
  ///
  /// The height travels through a callback rather than a `PreferenceKey`: a preference written at
  /// the composer and read at this surface's root makes SwiftUI run a reduce over one combiner pair
  /// per node of everything mounted between them — the whole transcript on the chat surface — and
  /// that collection dominated the measured cost of every switch into Chat. The callback feeds the
  /// identical value into the identical state.
  @State private var composerHeight: CGFloat = QueryShellLayout.barMinHeight
  /// **The caret, as a claim rather than a flag.** Monotonic, and every increment lands the caret in
  /// the bar. `@FocusState` cannot do that job any more: the field is an `NSTextView` that SwiftUI's
  /// `.focused()` does not reach, and a flag already `true` could never re-claim a caret AppKit had
  /// since given away — which is precisely the case the `didBecomeActive` claim below exists for.
  @State private var caretClaims = 0

  var body: some View {
    // `markOnce`: body re-evaluates on every local state change (search text,
    // composer height); only the first evaluation after the route change is
    // the switch's mount work. The detail classifies cold vs warm switches.
    // `let _ =` keeps the Void result out of the ViewBuilder's expression list.
    let _ = ChatSwitchPerfLog.markOnce(
      "QueryShellHome.body",
      detail: "messages=\(chatProvider.messages.count) isLoading=\(chatProvider.isLoading)")
    querySurface
  }

  private var querySurface: some View {
    GeometryReader { proxy in
      let lane = QueryShellLayout.laneWidth(for: proxy.size.width)
      // The search bar is always mounted above the panel, so the body's room subtracts it in both
      // modes — `panelBodyHeight` only knows the hero reserve for `.results`.
      let chrome = QueryShellLayout.panelChromeHeight(
        mode: mode,
        composerHeight: mode == .answer
          ? max(QueryShellLayout.panelComposerMinHeight, composerHeight) : 0)
      let room =
        proxy.size.height - QueryShellLayout.surfaceTopInset - QueryShellLayout.barMinHeight
        - QueryShellLayout.panelGap - chrome
      let bodyHeight = min(
        QueryShellLayout.maximumBodyHeight, max(QueryShellLayout.minimumBodyHeight, room))
      // **Only this column is woken by a keystroke.** The composer draft is not published on
      // `ChatProvider` (see `ChatComposerDraft`), so subscribing to it here keeps typing out of the
      // shell and the transcript while still giving the bar — and the list it filters — the live text.
      ChatDraftScope(draft: chatProvider.composerDraft) { draft in
        VStack(spacing: QueryShellLayout.panelGap) {
          // **The search bar is always on screen.** It is pure search — typing narrows the spine
          // below; clearing it returns the panel to the conversation. The chat composer is a
          // different control and stays pinned inside the panel (INV-6: one chat composer).
          QuerySearchBar(text: $searchText, searchSurface: .home)
          QueryResultsPanel(
            request: requestBinding(),
            mode: mode,
            total: total,
            onExitAnswer: nil,
            bodyHeight: bodyHeight,
            topAccessory: { EmptyView() },
            headerAccessory: { headerAccessory },
            footer: {
              if mode == .answer {
                // Measured as one unit: `composerHeight` is what the panel
                // reserves for its footer, so a banner outside that
                // measurement would push the composer down by its own height.
                VStack(spacing: OmiSpacing.sm) {
                  ChatQuotaBannerView.Slot()
                  composerBar(draft: draft)
                }
                .onGeometryChange(for: CGFloat.self) {
                  $0.size.height
                } action: { measured in
                  reportComposerHeight(measured)
                }
              }
            }
          ) {
            panelBody(request: QueryShellRequest(text: searchText, filters: filters))
          }
          Spacer(minLength: 0)
        }
        .frame(width: lane)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
        .padding(.top, OmiSpacing.sm)
      }
    }
    // A typed character belongs in the field even when the field is not focused: this is a search
    // surface, and a search surface that swallows the first letter you type is broken.
    .onAppear {
      ChatSwitchPerfLog.mark("QueryShellHome.appear")
      takePendingDraftIfAny()
      claimCaret()
    }
    // A prefilled draft (first-real-app card, daily-summary follow-up) lands in the composer,
    // focused and unsent. This is the app's only chat destination, so it is the only consumer.
    .onReceive(NotificationCenter.default.publisher(for: .openMainChatRequested)) { _ in
      takePendingDraftIfAny()
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
    // Each handler applies `HomeBridgeIntent.searchTextAfter` first: mode is derived from the
    // search text, so an action that promises the conversation must clear it or its effect lands
    // hidden behind the results panel while the bridge reports success.
    .onReceive(NotificationCenter.default.publisher(for: .homeStageOpenChat)) { _ in
      searchText = HomeBridgeIntent.openChat.searchTextAfter(searchText)
      claimCaret()
    }
    // `home_close_panel` collapses Home to its resting chat state — the same thing Escape does.
    // The bridge action posts this and reports success, so an unobserved notification here would
    // be the "bridge answered ok and nothing happened" defect this file's actions exist to avoid.
    .onReceive(NotificationCenter.default.publisher(for: .homeStageClose)) { _ in
      searchText = HomeBridgeIntent.closePanel.searchTextAfter(searchText)
      claimCaret()
    }
    .onReceive(NotificationCenter.default.publisher(for: .homeStageAsk)) { note in
      guard let query = note.userInfo?["query"] as? String else { return }
      searchText = HomeBridgeIntent.ask.searchTextAfter(searchText)
      chatProvider.draftText = query
      ask()
    }
    .onReceive(NotificationCenter.default.publisher(for: .homeStageAttach)) { note in
      guard let path = note.userInfo?["path"] as? String else { return }
      searchText = HomeBridgeIntent.attach.searchTextAfter(searchText)
      stageAttachments([URL(fileURLWithPath: path)])
    }
    // Escape while searching clears the search and lands back on the conversation; with an empty
    // field it falls through to the shell's own Escape (dismiss the window).
    .onEscapeKey(priority: .content) {
      guard !searchText.isEmpty else { return false }
      searchText = ""
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
      onAttachmentRemoved: { chatProvider.removePendingAttachment(id: $0) },
      references: chatProvider.pendingComposerReferences,
      onReferenceRemoved: { chatProvider.removeComposerReference(id: $0) }
    )
    // The footer unit (quota banner + composer) is measured where it is
    // composed, so the bar itself carries no height reporting of its own.
  }

  /// Receives the composer's measured height — the same guarded write the
  /// preference reader used to perform, minus the preference traversal.
  private func reportComposerHeight(_ measured: CGFloat) {
    // The composer's real height has been measured and fed back — the bar is
    // laid out and usable at its resting geometry.
    ChatSwitchPerfLog.markOnce("composerMeasured")
    guard measured > 0, measured != composerHeight else { return }
    composerHeight = measured
  }

  /// The seam value the panel and its body are handed, **assembled rather than stored**: the text
  /// half has an owner already (`chatProvider.composerDraft`) and a second copy of it here is the
  /// two-variables defect this surface shipped with.
  private func requestBinding() -> Binding<QueryShellRequest> {
    Binding(
      get: { QueryShellRequest(text: searchText, filters: filters) },
      set: { next in
        if next.text != searchText { searchText = next.text }
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
        searchSurface: .home,
        onOpenConversation: openConversationRecord,
        onOpenMemory: openMemory,
        onOpenBrainMap: openBrainMap,
        onOpenRewind: openRewind
      )
    case .answer:
      QueryAnswerThread(
        chatProvider: chatProvider,
        onOpenCitation: openCitation,
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
    if mode == .answer, menu.isPresentable {
      chatMenu
    }
  }

  private var menu: HomeChatMenu {
    HomeChatMenu.resolve(
      messageCount: chatProvider.messages.count,
      isSending: chatProvider.isSending,
      isClearing: chatProvider.isClearing)
  }

  /// Conversation-local actions only. Global AI configuration belongs to the
  /// Settings gear that is already present on every page.
  private var chatMenu: some View {
    Menu {
      Button(didCopyTranscript ? "Copied" : "Copy conversation", action: copyTranscript)
        .disabled(!menu.canCopy)
      Button("Clear conversation", role: .destructive, action: clearTranscript)
        .disabled(!menu.canClear)
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

  /// Clearing empties the one transcript; the page stays a chat, ready for the next question.
  private func clearTranscript() {
    Task {
      await chatProvider.clearChat()
    }
  }

  /// Staging goes through the provider, which owns the cap and the upload — the paperclip, a drop on
  /// the bar and the automation bridge all end here rather than each keeping their own list.
  private func stageAttachments(_ urls: [URL]) {
    let staged = urls.compactMap(ChatAttachment.from(url:))
    guard !staged.isEmpty else { return }
    chatProvider.addAttachments(staged)
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
    // Plan before mutating anything: a busy provider rejects the send, so
    // Return during an active turn must leave the typed draft intact and
    // neither dispatch nor advance the rating-prompt count.
    guard submission.mode != nil,
      let plan = sendLedger.planSubmit(submission.question, providerBusy: chatProvider.isSending)
    else { return }
    if chatProvider.draftText != submission.text { chatProvider.draftText = submission.text }
    claimCaret()
    send(plan)
  }

  /// The one send. `Try again` on a failed turn enters here too, so a retry is the same turn through
  /// the same provider and never a second send path (INV-6). The ledger owns whether the emission
  /// counts toward the rating-prompt trigger (submits do, retries never re-count).
  private func send(_ plan: QueryShellSendLedger.Plan) {
    chatProvider.dismissOnboardingOpener()
    Task {
      // Analytics, question counting, and retry state all commit at the
      // provider's own acceptance boundary — a send it rejects (busy race,
      // signed-out) emits nothing and changes nothing.
      var accepted = false
      _ = await chatProvider.sendMessage(
        plan.question,
        onAccepted: {
          accepted = true
          sendLedger.recordAccepted(plan)
        },
        onAcceptedWithAttemptID: { attemptID in
          AnalyticsManager.shared.chatMessageSent(
            messageLength: plan.question.count, hasSelectedAppContext: false,
            source: "query_shell", countsAsQuestion: plan.countsAsQuestion,
            attemptID: attemptID)
        })
      if !accepted, chatProvider.draftText.isEmpty {
        // The provider refused the send — give the typed question back
        // instead of losing it to a cleared field.
        chatProvider.draftText = plan.question
      }
    }
  }

  /// Re-sends the question that failed, not whatever the bar holds now — the send emptied it.
  private func retry() {
    guard let plan = sendLedger.planRetry() else { return }
    send(plan)
  }

  /// Asks for the caret. Monotonic, so a claim is never swallowed for already having been made — the
  /// bar can be cold while this view still believes it is focused, which is the state every one of
  /// these call sites is written for.
  private func claimCaret() {
    caretClaims &+= 1
  }

  private func takePendingDraftIfAny() {
    guard let draft = MainChatNavigationRequestStore.shared.consumeDraft() else { return }
    // Leave search-results mode first, or the prefilled composer stays hidden behind the results.
    searchText = HomeBridgeIntent.openChat.searchTextAfter(searchText)
    chatProvider.draftText = draft
    claimCaret()
  }

  // MARK: - Where a row goes

  /// Opens the exact conversation a spine row is about.
  ///
  /// The row carries the whole record, so the typed deep link hands it straight to the
  /// Conversations host rather than re-resolving it by id.
  private func openConversationRecord(_ conversation: ServerConversation) {
    chatFirstRichBlockContext.navigation.open(conversation: conversation)
  }

  /// Opens the exact memory a spine row is about, on the same terms the Brain Map's citations use.
  private func openMemory(_ memory: SpineMemory) {
    chatFirstRichBlockContext.navigation.open(focus: .memory(id: memory.id))
  }

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

  /// Typed citation routing stays at the shell boundary. The inline renderer knows presentation;
  /// this root owns navigation and preserves exact entity identity where the destination supports it.
  private func openCitation(_ reference: ChatCitationReference) {
    guard reference.canOpen else { return }
    let navigation = chatFirstRichBlockContext.navigation
    switch reference.kind {
    case .conversation:
      openConversationCitation(reference)
    case .memory:
      navigation.open(focus: .memory(id: reference.sourceID))
    case .task:
      navigation.open(focus: .task(id: reference.sourceID))
    case .goal:
      navigation.open(focus: .goal(id: reference.sourceID))
    case .screenshot:
      guard let id = RewindCitationFocusState.parseScreenshotID(reference.sourceID) else { return }
      RewindCitationFocusState.shared.request(id)
      navigation.selectMore(.rewind)
    case .web:
      if let url = reference.url { NSWorkspace.shared.open(url) }
    case .unavailable:
      break
    }
  }

  /// A conversation citation must open the conversation it names. The agent
  /// cites desktop and phone recordings as readily as Omi-device captures, but
  /// the capture focus resolves through the archive's source-scoped fetch —
  /// navigating first used to strand a non-capture citation on the
  /// Conversations list with nothing opened. Fetch the unscoped record, then
  /// let its own provenance pick the route.
  private func openConversationCitation(_ reference: ChatCitationReference) {
    let navigation = chatFirstRichBlockContext.navigation
    let resolutionGeneration = navigation.beginConversationLinkResolution()
    Task { @MainActor in
      let fetched = try? await APIClient.shared.getConversation(id: reference.sourceID)
      guard
        let route = ChatFirstConversationLinkPolicy.citationRoute(
          forFetched: fetched,
          requestedID: reference.sourceID,
          momentTimestampMs: reference.momentTimestampMs)
      else { return }
      switch route {
      case .captureFocus(let momentTs):
        navigation.open(focus: .capture(id: reference.sourceID, momentTs: momentTs))
      case .exactRecord:
        guard let conversation = fetched else { return }
        navigation.completeConversationLinkResolution(
          conversation: conversation,
          generation: resolutionGeneration)
      }
    }
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
    let navigation = chatFirstRichBlockContext.navigation
    OmiMotion.withGated(.easeOut(duration: 0.08)) {
      guard let hubView = route.memoryDestination else {
        navigation.selectLegacyDestination(route.navItem)
        return
      }
      // Both halves of the hub state move together — the persisted view and the
      // typed route that decides which host is mounted (see `ChatFirstShell`).
      memoryDestinationRawValue = hubView.rawValue
      navigation.selectPrimary(MemoryHubSelectionPolicy.chatFirstRoute(for: hubView))
    }
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
    let startedAt = DispatchTime.now()
    // Rewind's pool opens asynchronously after launch, and this is a `.task` that runs once — so an
    // ask that lands before it is open under-reports the archive by its entire size for the rest of
    // the session. That is what made the corner read "390 results · of 147 captured": 147 was the
    // conversations and memories alone, with the whole screen archive counted as nothing.
    guard await SpineScreenIndex.poolWhenReady() != nil else {
      screenCount = 0
      ChatSwitchPerfLog.span("screenCountTask", startedAt: startedAt)
      return
    }
    screenCount = (try? await RewindDatabase.shared.getScreenshotCount()) ?? 0
    ChatSwitchPerfLog.span("screenCountTask", startedAt: startedAt)
  }
}
