import OmiSupport
import OmiTheme
import SwiftUI

enum ConversationDetailPane: Equatable {
  case summary
  case transcript
}

enum ConversationDetailRequestGate {
  static func canApply(
    requestGeneration: Int,
    currentGeneration: Int,
    isCancelled: Bool
  ) -> Bool {
    !isCancelled && requestGeneration == currentGeneration
  }
}

struct ConversationDetailProcessingLayout<Banner: View, Content: View>: View {
  let isProcessing: Bool
  let banner: Banner
  let content: Content

  init(
    isProcessing: Bool,
    @ViewBuilder banner: () -> Banner,
    @ViewBuilder content: () -> Content
  ) {
    self.isProcessing = isProcessing
    self.banner = banner()
    self.content = content()
  }

  var body: some View {
    VStack(alignment: .leading, spacing: OmiSpacing.xxl) {
      if isProcessing {
        banner
      }
      content
    }
    .frame(maxWidth: .infinity, alignment: .leading)
  }
}

/// Full detail view for a single conversation
struct ConversationDetailView: View {
  let conversation: ServerConversation
  let onBack: () -> Void
  /// Where Back returns to, named on the chip ("‹ Conversations", "‹ Memories", "‹ Activity").
  var backTitle: String = "Conversations"
  var folders: [Folder] = []
  var onMoveToFolder: ((String, String?) async -> Void)?
  var onDelete: (() -> Void)?
  var onTitleUpdated: ((String) -> Void)?

  /// Optional capture-archive context. The archive owns the list/filter; this
  /// canonical detail owns the source-specific playback affordances so an Omi
  /// capture never gets a second full detail presentation.
  var initialCaptureMomentTimestamp: TimeInterval? = nil
  var onCaptureFocusResolved: ((Bool) -> Void)? = nil
  var onDiscussInChat: (() -> Void)? = nil
  var onOpenLinkedTask: ((String) -> Void)? = nil
  /// Opens another conversation in this detail — another device's recording of the same event.
  var onOpenConversation: ((ServerConversation) -> Void)? = nil
  /// Called after a recording is separated, for surfaces (search) the list refresh does not reach.
  var onCaptureGroupChanged: (() -> Void)? = nil

  // People (speaker naming). Owned here, not injected: every surface that can
  // present a conversation detail — Conversations, Memories, Dashboard citations —
  // must offer the same speaker assignment. Requiring callers to thread closures
  // left two of the three entry points with dead, un-tappable speaker labels
  // ("impossible to assign speakers" reports).
  private var people: [Person] { AppState.current?.people ?? [] }
  @ObservedObject private var automation = ConversationDetailAutomationState.shared

  @StateObject private var appProvider = AppProvider()
  /// Playback belongs to the canonical detail, not to the capture browser.
  /// This keeps the signed URL and AVPlayer lifecycle scoped to whichever
  /// conversation detail is currently visible.
  @StateObject private var capturePlayback = CapturePlaybackController()
  /// On-device transcript-to-audio alignment behind the transcript refresh
  /// button. Its result replaces `loadedConversation` for this selection only.
  @StateObject private var transcriptResync = CaptureTranscriptResyncer()
  /// True once the displayed transcript's times are seconds into the media
  /// (a stored or fresh sync), so playback must not apply server spans again.
  @State private var transcriptOnMediaClock = false
  /// The transcript as the server sent it, kept while a sync is on screen so
  /// the page can fall back to the server's clock when the audio that sync was
  /// made against is no longer what plays.
  @State private var serverClockConversation: ServerConversation?
  /// This note's screenshots, owned here rather than inside the summary because both halves of the
  /// note read them: the strip is in the summary, and the banner is the *header's* background.
  /// Constructing it is free — the initialiser only captures closures — and it starts no work
  /// until `MeetingNoteScreenshotStrip`'s task calls `load()`, which the gate below still governs.
  @StateObject private var screenshotsStore = MeetingScreenshotsStore()
  /// This event's recordings panel, and separating one of them (`CaptureRecordingsPanelHost`).
  @StateObject private var separation = CaptureGroupSeparationController { id in
    await AppState.current?.separateConversationFromCaptureGroup(id) ?? false
  }
  @State private var showRecordings = false
  @State private var pendingSeparation: CaptureGroupRecording?
  @State private var showAppSelector = false
  @State private var isReprocessing = false
  @State private var selectedAppForReprocess: OmiApp?
  /// Locally mirrored preferred summarization app (mobile keeps the same key
  /// in SharedPreferences; the backend exposes no GET for it).
  @State private var preferredSummaryAppId: String?

  // Transcript presentation state. Summary and transcript are exclusive panes so neither one is
  // compressed into an unreadable split view at the minimum window width.
  @State private var showTranscriptDrawer = false
  @State private var transcriptSearch = TranscriptSearchModel()
  @State private var isTranscriptSearchOpen = false
  @FocusState private var isTranscriptSearchFocused: Bool

  // Entry animation
  @State private var hasAppeared = false

  // Full conversation loaded from API (with transcript segments)
  @State private var loadedConversation: ServerConversation?
  @State private var isLoadingConversation = false
  // True while a lazily-deferred conversation is being enriched (polled) on first open.
  @State private var isEnrichingDeferred = false

  // Action states
  @State private var showDeleteConfirmation = false
  @State private var showEditDialog = false
  @State private var editedTitle = ""
  @State private var isUpdatingTitle = false
  @State private var isDeleting = false

  // Capture deep-link focus state. A successful acknowledgement is terminal;
  // unresolved attempts intentionally remain retryable when audio is refreshed.
  @State private var didResolveInitialCaptureFocus = false
  @State private var detailLoadGeneration = 0
  @State private var detailReadyConversationID: String?
  @State private var isRefreshingTranscript = false
  @State private var captureFocusGeneration = 0

  // Speaker naming state
  @State private var selectedSegmentForNaming: TranscriptSegment? = nil

  static func assignmentMetadata(
    for segmentIndices: [Int],
    in segments: [TranscriptSegment]
  ) -> (targets: [String], backendIds: [String], fallbackOrders: [Int]) {
    let validIndices = segmentIndices.filter { segments.indices.contains($0) }
    let targets = validIndices.map { index in
      segments[index].backendId ?? "#index:\(index)"
    }
    let backendIds = validIndices.compactMap { index in
      segments[index].backendId
    }
    let fallbackOrders = validIndices.filter { index in
      segments[index].backendId == nil
    }
    return (targets, backendIds, fallbackOrders)
  }

  /// The conversation to display - use loaded version if available, otherwise use prop
  private var displayConversation: ServerConversation {
    loadedConversation ?? conversation
  }

  /// The date to display (prefer startedAt, fall back to createdAt)
  private var displayDate: Date {
    displayConversation.startedAt ?? displayConversation.createdAt
  }

  /// "1 segment", "388 segments" — a badge says what it counts.
  nonisolated static func segmentCountLabel(_ count: Int) -> String {
    count == 1 ? "1 segment" : "\(count) segments"
  }

  static func visiblePane(transcriptOpen: Bool) -> ConversationDetailPane {
    transcriptOpen ? .transcript : .summary
  }

  /// The canonical detail only renders capture playback for first-party Omi
  /// captures. Other conversation sources retain the same summary/transcript
  /// editor without advertising unavailable audio controls.
  static func showsCapturePlayback(
    for source: ConversationSource?,
    in pane: ConversationDetailPane
  ) -> Bool {
    source == .omi && pane == .transcript
  }

  private var capturePlaybackTaskID: String {
    let moment = initialCaptureMomentTimestamp.map { String($0) } ?? "none"
    return "\(conversation.id):\(detailReadyConversationID ?? "loading"):\(moment)"
  }

  private var detailRequestToken: ConversationDetailRequestToken {
    ConversationDetailRequestToken(conversation: conversation)
  }

  var body: some View {
    VStack(alignment: .leading, spacing: 0) {
      pageHeader

      switch Self.visiblePane(transcriptOpen: showTranscriptDrawer) {
      case .summary:
        summaryPane
          .transition(.opacity)
      case .transcript:
        transcriptDrawerView
          .frame(maxWidth: .infinity, maxHeight: .infinity)
          .transition(.opacity)
      }
    }
    .modifier(
      CaptureRecordingsPanelHost(
        isOpen: $showRecordings, recordings: captureRecordings, phase: separation.phase,
        onOpen: openRecording, onSeparate: separateRecording, pendingSeparation: $pendingSeparation)
    )
    .opacity(hasAppeared ? 1 : 0)
    .offset(y: hasAppeared ? 0 : 20)
    // Esc peels one layer: the transcript back to the summary, then the summary back to the list.
    // (The recordings list and find each claim Esc first, at a higher priority.)
    .onEscapeKey(priority: .content) {
      if showTranscriptDrawer {
        closeTranscript()
      } else {
        onBack()
      }
      return true
    }
    .shellConfirmation(
      isPresented: $showDeleteConfirmation,
      title: "Delete Conversation?",
      message: "This permanently deletes the conversation, its transcript and its summary.",
      confirmTitle: "Delete"
    ) {
      Task { await deleteConversation() }
    }
    .dismissableSheet(isPresented: $showEditDialog) {
      TextPromptSheet(
        title: "Rename Conversation",
        placeholder: "Title",
        text: $editedTitle,
        isBusy: isUpdatingTitle,
        onConfirm: {
          showEditDialog = false
          Task { await updateTitle() }
        },
        onCancel: { showEditDialog = false }
      )
    }
    .onAppear {
      showTranscriptDrawer = ConversationDetailAutomationState.shared.syncPresentedDetail(
        conversationId: conversation.id,
        transcriptDrawerOpen: showTranscriptDrawer
      )
      OmiMotion.withGated(.easeOut(duration: 0.5)) {
        hasAppeared = true
      }
    }
    .onChange(of: detailRequestToken) { previous, current in
      detailLoadGeneration &+= 1
      detailReadyConversationID = nil
      isLoadingConversation = false
      isEnrichingDeferred = false
      loadedConversation = nil
      if previous.conversationID != current.conversationID {
        captureFocusGeneration &+= 1
        showTranscriptDrawer = ConversationDetailAutomationState.shared.syncPresentedDetail(
          conversationId: current.conversationID,
          transcriptDrawerOpen: showTranscriptDrawer
        )
        didResolveInitialCaptureFocus = false
        capturePlayback.clear()
        transcriptResync.reset()
        transcriptOnMediaClock = false
        serverClockConversation = nil
        separation.reset()
        showRecordings = false
        pendingSeparation = nil
      }
    }
    .onDisappear {
      detailLoadGeneration &+= 1
      captureFocusGeneration &+= 1
      detailReadyConversationID = nil
      ConversationDetailAutomationState.shared.clear(conversationId: conversation.id)
      capturePlayback.clear()
      transcriptResync.reset()
      transcriptOnMediaClock = false
      serverClockConversation = nil
    }
    .onChange(of: showTranscriptDrawer) { _, newValue in
      ConversationDetailAutomationState.shared.setTranscriptDrawerOpen(
        newValue, conversationId: conversation.id)
    }
    .onChange(of: automation.transcriptDrawerOpen) { _, isOpen in
      guard automation.openConversationId == conversation.id, isOpen else { return }
      showTranscriptDrawer = true
    }
    .task(id: detailRequestToken) {
      detailLoadGeneration &+= 1
      let requestGeneration = detailLoadGeneration
      let requestedConversation = conversation
      detailReadyConversationID = nil

      preferredSummaryAppId =
        UserDefaults.standard.string(forKey: .preferredSummarizationAppId).flatMap { $0.isEmpty ? nil : $0 }
      await appProvider.fetchApps()
      guard isCurrentDetailRequest(requestGeneration) else { return }
      await AppState.current?.fetchPeople()
      guard isCurrentDetailRequest(requestGeneration) else { return }
      AnalyticsManager.shared.conversationDetailOpened(conversationId: requestedConversation.id)

      // All detail reads go through the repository. It can paint a complete
      // cached detail immediately, but always revalidates server-owned fields.
      if requestedConversation.deferred || requestedConversation.status == .processing {
        isEnrichingDeferred = true
        // Keep following the row for as long as it is open. A bounded loop
        // that silently stops leaves the banner promising a summary that no
        // fetch will ever deliver; the backoff caps the cost instead.
        var attempts = 0
        while true {
          guard isCurrentDetailRequest(requestGeneration), let appState = AppState.current else { break }
          let fetched = await appState.loadConversationDetail(requestedConversation) { cached in
            guard isCurrentDetailRequest(requestGeneration) else { return }
            applyLoadedConversation(cached)
          }
          guard isCurrentDetailRequest(requestGeneration) else { return }
          applyLoadedConversation(fetched)
          if fetched.status != .processing { break }
          let delay = ProcessingConversationWatcher.pollDelay(attempt: attempts)
          attempts += 1
          try? await Task.sleep(nanoseconds: UInt64(delay * 1_000_000_000))
        }
        guard isCurrentDetailRequest(requestGeneration) else { return }
        isEnrichingDeferred = false
      } else {
        isLoadingConversation = true
        if let appState = AppState.current {
          let fetched = await appState.loadConversationDetail(requestedConversation) { cached in
            guard isCurrentDetailRequest(requestGeneration) else { return }
            applyLoadedConversation(cached)
          }
          guard isCurrentDetailRequest(requestGeneration) else { return }
          applyLoadedConversation(fetched)
        }
        guard isCurrentDetailRequest(requestGeneration) else { return }
        isLoadingConversation = false
      }

      guard isCurrentDetailRequest(requestGeneration) else { return }
      detailReadyConversationID = requestedConversation.id
    }
    .task(id: capturePlaybackTaskID) {
      guard detailReadyConversationID == conversation.id else { return }
      captureFocusGeneration &+= 1
      let requestGeneration = captureFocusGeneration
      didResolveInitialCaptureFocus = false
      await prepareCapturePlaybackIfNeeded(requestGeneration: requestGeneration)
    }
    .onReceive(
      NotificationCenter.default.publisher(for: .desktopAutomationShowConversationTranscriptRequested)
    ) { notification in
      guard let conversationId = notification.userInfo?["conversationId"] as? String,
        conversationId == displayConversation.id
      else { return }
      OmiMotion.withGated(.easeInOut(duration: 0.2)) {
        showTranscriptDrawer = true
      }
    }
    .onReceive(
      NotificationCenter.default.publisher(for: .desktopAutomationConversationRecordingRequested)
    ) { notification in
      guard notification.userInfo?["conversationId"] as? String == displayConversation.id,
        let action = notification.userInfo?["action"] as? String
      else { return }
      if action == "show" || action == "hide" {
        showRecordings = action == "show" && !captureRecordings.isEmpty
        return
      }
      guard
        let recording = captureRecordings.first(where: { $0.id == notification.userInfo?["recordingId"] as? String })
      else { return }
      switch action {
      case "separate": separateRecording(recording)
      // Raises the confirmation a row's Separate… raises, so the dialog itself can be checked.
      case "request_separate": pendingSeparation = recording
      default: openRecording(recording)
      }
    }
    .onReceive(
      NotificationCenter.default.publisher(for: .desktopAutomationConversationPromptRequested)
    ) { notification in
      guard notification.userInfo?["conversationId"] as? String == displayConversation.id else { return }
      switch notification.userInfo?["prompt"] as? String {
      case "rename":
        editedTitle = displayConversation.title
        showEditDialog = true
      case "delete": showDeleteConfirmation = true
      default: break
      }
    }
    .dismissableSheet(isPresented: $showAppSelector) {
      AppSelectorSheet(
        apps: appProvider.apps.filter { $0.capabilities.contains("memories") },
        isLoading: isReprocessing,
        selectedAppId: ConversationSummarySelection.primarySummary(for: displayConversation).appId,
        preferredAppId: preferredSummaryAppId,
        onSelect: { app in
          selectedAppForReprocess = app
          Task {
            await reprocessWithApp(app)
          }
        },
        onSetPreferred: { app in
          setPreferredSummaryApp(app)
        },
        onDismiss: { showAppSelector = false }
      )
      .frame(width: 400, height: 500)
    }
    .dismissableSheet(item: $selectedSegmentForNaming) { segment in
      NameSpeakerSheet(
        segment: segment,
        allSegments: displayConversation.transcriptSegments,
        people: people,
        onSave: { personId, isUser, segmentIndices in
          guard let appState = AppState.current else { return false }

          let assignment = Self.assignmentMetadata(
            for: segmentIndices,
            in: displayConversation.transcriptSegments
          )
          let success = await appState.assignSpeakerToSegments(
            conversationId: conversation.id,
            segmentIds: assignment.targets,
            personId: personId,
            isUser: isUser
          )
          guard success else { return false }

          // assignSpeakerToSegments already persisted the assignment (backend
          // and/or awaited local SQLite) — only the displayed copy needs updating.
          updateDisplayedConversation(segmentIndices: segmentIndices, isUser: isUser, personId: personId)
          return true
        },
        onCreatePerson: { name in await AppState.current?.createPerson(name: name) },
        onDismiss: {
          selectedSegmentForNaming = nil
        }
      )
    }
  }

  // MARK: - Header

  private var pageHeader: some View {
    ConversationDetailHeader(
      conversation: displayConversation,
      folders: folders,
      people: people,
      pane: Self.visiblePane(transcriptOpen: showTranscriptDrawer),
      canCopyTranscript: canCopyTranscript,
      isGroupedEvent: !captureRecordings.isEmpty,
      backTitle: backTitle,
      onBack: onBack,
      onSelectPane: { pane in
        OmiMotion.withGated(.easeInOut(duration: 0.2)) { showTranscriptDrawer = pane == .transcript }
      },
      onToggleStar: toggleStar,
      onRename: {
        editedTitle = displayConversation.title
        showEditDialog = true
      },
      onMoveToFolder: onMoveToFolder.map { move in { folderId in moveToFolder(folderId, using: move) } },
      onCopyTranscript: copyTranscript,
      onDiscussInChat: onDiscussInChat,
      onDelete: { showDeleteConfirmation = true },
      bannerInset: { headerBannerInset },
      recordings: {
        if !captureRecordings.isEmpty {
          CaptureRecordingsStackButton(recordings: captureRecordings, isOpen: showRecordings) {
            OmiMotion.withGated(.easeOut(duration: 0.15)) { showRecordings.toggle() }
          }
        }
      },
      trailing: {
        if showTranscriptDrawer {
          TranscriptFindField(
            isOpen: isTranscriptSearchOpen,
            query: Binding(get: { transcriptSearch.query }, set: { runTranscriptSearch($0) }),
            countLabel: transcriptSearch.countLabel, hasMatches: transcriptSearch.currentMatch != nil,
            isFocused: $isTranscriptSearchFocused, onOpen: openTranscriptSearch,
            onStep: { forward in forward ? transcriptSearch.next() : transcriptSearch.previous() },
            onClose: closeTranscriptSearch)
          refreshTranscriptButton
        }
      }
    )
    .padding(.horizontal, OmiSpacing.xxl)
    .padding(.top, OmiSpacing.md)
    .padding(.bottom, OmiSpacing.md)
    // The banner, as this header's ground rather than as a slot below it. It draws no text and is
    // absent when the note has no approved frame, which leaves the ordinary header as it was.
    .background(headerBanner)
  }

  @ViewBuilder
  private var headerBanner: some View {
    if MeetingScreenshotsStore.isEnabled, let banner = screenshotsStore.banner {
      MeetingNoteHeaderBanner(frame: banner)
    }
  }

  @ViewBuilder
  private var headerBannerInset: some View {
    if MeetingScreenshotsStore.isEnabled, let banner = screenshotsStore.banner {
      MeetingNoteHeaderInset(
        frame: banner,
        onOpen: {
          ScreenFrameQuickLook.shared.present(
            screenshotsStore.quickLookFrames,
            startingAt: banner.id,
            refreshing: {
              await screenshotsStore.refreshPersistedSet()
              return screenshotsStore.quickLookFrames
            })
        },
        onContentUnavailable: { Task { await screenshotsStore.refreshPersistedSet() } })
    }
  }

  // MARK: - Recordings of this event

  private var captureRecordings: [CaptureGroupRecording] {
    CaptureGroupPresentation.recordings(of: displayConversation)
  }

  /// A member the loaded list does not hold is fetched by id rather than assumed present.
  private func openRecording(_ recording: CaptureGroupRecording) {
    guard let onOpenConversation, let appState = AppState.current else { return }
    Task { @MainActor in
      let member = await CaptureGroupPresentation.resolveMember(
        id: recording.id, loaded: appState.conversations, fetch: { await appState.loadConversation(id: $0) })
      if let member { onOpenConversation(member) }
    }
  }

  /// Sticky on the server; afterwards the detail re-reads its own membership and the list
  /// (refreshed by AppState) splits the row.
  private func separateRecording(_ recording: CaptureGroupRecording) {
    let requestGeneration = detailLoadGeneration
    Task { @MainActor in
      await separation.separate(recordingID: recording.id) {
        guard isCurrentDetailRequest(requestGeneration), let appState = AppState.current else { return }
        let refreshed = await appState.loadConversationDetail(displayConversation)
        guard isCurrentDetailRequest(requestGeneration) else { return }
        applyLoadedConversation(refreshed)
        onCaptureGroupChanged?()
      }
    }
  }

  private var canCopyTranscript: Bool {
    displayConversation.transcriptPresenceState != .lockedOrRedacted
  }

  /// Sharing publishes the conversation (visibility flips to "shared"), so it
  /// honors the same lock/redaction gate as copying the transcript: content
  /// this surface refuses to put on the pasteboard must not be publishable to
  /// an unauthenticated share URL from the same toolbar.
  private var canShareConversation: Bool {
    canCopyTranscript
  }

  // MARK: - Actions

  /// Re-reads the detail through the repository and re-resolves capture
  /// playback. Selection identity is unchanged, so the same generation guards
  /// that protect the initial load also discard a refresh that outlives it.
  /// A freshly loaded detail, with any sync this machine already made for
  /// this audio part applied on top so reopening never regresses the timing.
  private func applyLoadedConversation(_ fetched: ServerConversation) {
    serverClockConversation = fetched
    if let synced = CaptureTranscriptSyncStore().applied(to: fetched) {
      loadedConversation = synced
      transcriptOnMediaClock = true
    } else {
      loadedConversation = fetched
      transcriptOnMediaClock = false
    }
  }

  /// A sync is made against the aggregate; while the transport is playing one
  /// part instead, the aggregate's clock is the wrong one for a multi-part
  /// transcript, so the page shows the server's timing until an exact
  /// aggregate is back.
  private func showServerClockTranscriptIfPlaybackIsAFallback(_ resolution: CapturePlaybackResolution) {
    guard transcriptOnMediaClock, case .fileFallback = resolution, let serverClockConversation else { return }
    loadedConversation = serverClockConversation
    transcriptOnMediaClock = false
  }

  /// Refresh = re-fetch the transcript, then, for a capture with audio, listen
  /// to that audio on-device and move every timestamp onto the audio's clock.
  /// The raw transcript is always what gets aligned, never an already-synced
  /// one, so repeated presses converge instead of compounding. Whatever timing
  /// is on screen stays there until the new sync succeeds: a refresh that
  /// cannot download, hear, or match the audio must not throw away a sync
  /// that already lined the bubbles up.
  private func refreshTranscript() {
    guard !isRefreshingTranscript, !transcriptResync.phase.isBusy else { return }
    isRefreshingTranscript = true
    let requestGeneration = detailLoadGeneration
    Task {
      defer { isRefreshingTranscript = false }
      var raw = displayConversation
      if let appState = AppState.current {
        raw = await appState.loadConversationDetail(raw) { _ in }
        guard isCurrentDetailRequest(requestGeneration) else { return }
      }
      applyLoadedConversation(raw)
      guard Self.showsCapturePlayback(for: raw.source, in: .transcript) else { return }
      transcriptResync.reset()
      let resolution = await capturePlayback.prepare(
        for: raw, forceRefresh: true, transcriptOnMediaClock: transcriptOnMediaClock)
      guard isCurrentDetailRequest(requestGeneration) else { return }
      guard case .readyAggregate = resolution, let artifact = capturePlayback.serverClockArtifact else {
        // Nothing exact to align against yet; the transport says why.
        showServerClockTranscriptIfPlaybackIsAFallback(resolution ?? .unavailable)
        return
      }
      guard let synced = await transcriptResync.resync(conversation: raw, artifact: artifact),
        isCurrentDetailRequest(requestGeneration)
      else { return }
      loadedConversation = synced
      transcriptOnMediaClock = true
      capturePlayback.setTranscriptOnMediaClock(true)
    }
  }

  private func toggleStar() {
    let starred = !displayConversation.starred
    var optimistic = displayConversation
    optimistic.starred = starred
    loadedConversation = optimistic
    Task { @MainActor in
      await AppState.current?.setConversationStarred(conversation.id, starred: starred)
      // Settle on what the repository kept (it rolls back a rejected mutation).
      if let row = AppState.current?.conversations.first(where: { $0.id == conversation.id }),
        loadedConversation?.id == row.id
      {
        loadedConversation?.starred = row.starred
      }
    }
  }

  private func moveToFolder(_ folderId: String?, using move: @escaping (String, String?) async -> Void) {
    let requestGeneration = detailLoadGeneration
    Task { @MainActor in
      await move(conversation.id, folderId)
      guard isCurrentDetailRequest(requestGeneration), let appState = AppState.current else { return }
      let refreshed = await appState.loadConversationDetail(displayConversation)
      guard isCurrentDetailRequest(requestGeneration) else { return }
      applyLoadedConversation(refreshed)
    }
  }

  /// The transcript every copy action here produces, or nil when it is locked.
  private var transcriptText: String? {
    guard canCopyTranscript else { return nil }
    return SpeakerLabelFormatter(people: people).transcript(displayConversation.transcriptSegments)
  }

  private func copyTranscript() {
    guard let transcriptText else { return }
    OmiToastCenter.shared.copy(transcriptText, confirming: "Transcript copied")
  }

  private func updateTitle() async {
    guard !editedTitle.isEmpty else { return }
    let requestGeneration = detailLoadGeneration
    isUpdatingTitle = true
    defer { isUpdatingTitle = false }

    await AppState.current?.updateConversationTitle(conversation.id, title: editedTitle)
    guard isCurrentDetailRequest(requestGeneration) else { return }
    loadedConversation?.structured.title = editedTitle
    onTitleUpdated?(editedTitle)
  }

  private func deleteConversation() async {
    isDeleting = true
    defer { isDeleting = false }

    let conversationId = conversation.id
    if await AppState.current?.deleteConversation(conversationId) == true {
      await MainActor.run {
        onDelete?()
        onBack()
      }
    }
  }

  // MARK: - Summary Pane

  private var summaryPane: some View {
    ScrollView {
      ConversationDetailProcessingLayout(isProcessing: isEnrichingDeferred) {
        deferredProcessingSection
      } content: {
        // Spacing 0: each section carries its own top inset, so one that renders nothing (or only
        // the screenshot loader's zero-height anchor) leaves no gap behind.
        VStack(alignment: .leading, spacing: 0) {
          summaryContent
        }
      }
      .padding(.horizontal, OmiSpacing.xxl)
      .padding(.top, OmiSpacing.sm)
      .padding(.bottom, OmiSpacing.section)
    }
    .glassScrollFade()
  }

  @ViewBuilder
  private var summaryContent: some View {
    if MeetingScreenshotsStore.isEnabled {
      MeetingNoteScreenshotsLayout(
        store: screenshotsStore, conversation: displayConversation, date: displayDate
      ) {
        summaryBeforeScreenshots
      } afterScreenshots: {
        summaryAfterScreenshots
      }
    } else {
      summaryBeforeScreenshots
      summaryAfterScreenshots
    }
  }

  @ViewBuilder
  private var summaryBeforeScreenshots: some View {
    let selection = ConversationSummarySelection.primarySummary(for: displayConversation)

    // Overview section (selected app result, or the structured fallback)
    if !selection.content.isEmpty {
      overviewSection
    }

    ConversationPhotoGallery(
      conversationID: displayConversation.id,
      photos: displayConversation.photos
    )
    .padding(.top, OmiSpacing.xxl)

    // Action items sit directly under the summary: they are the part of a
    // meeting a reader acts on. Nothing here is a task until the reader says
    // so (I1) — each row carries its own "Add to Tasks".
    ConversationActionItemsSection(conversation: displayConversation, onOpenLinkedTask: onOpenLinkedTask)
      .padding(.top, OmiSpacing.xxl)
  }

  @ViewBuilder
  private var summaryAfterScreenshots: some View {
    // Insights beyond the promoted primary summary.
    ConversationAppInsightsSection(
      rows: ConversationSummarySelection.secondaryResults(for: displayConversation),
      apps: appProvider.apps,
      isReprocessing: isReprocessing,
      onReprocess: { showAppSelector = true }
    )
    .padding(.top, OmiSpacing.xxl)

    // The $0-shadow exclusion that kept this section empty lives (and is tested) in
    // ConversationSummarySelection.suggestedApps.
    ConversationSuggestedAppsSection(
      apps: Array(
        ConversationSummarySelection.suggestedApps(appProvider.apps, results: displayConversation.appsResults)
          .prefix(4)),
      isLoadingApps: appProvider.isLoading,
      reprocessingAppID: isReprocessing ? selectedAppForReprocess?.id : nil,
      onSelect: { app in
        selectedAppForReprocess = app
        Task { await reprocessWithApp(app) }
      }
    )
    .padding(.top, OmiSpacing.xxl)
  }

  // MARK: - Capture Playback

  @ViewBuilder
  private var capturePlaybackSection: some View {
    ConversationCapturePlaybackSection(
      capture: displayConversation,
      playback: capturePlayback,
      resync: transcriptResync,
      onPrepare: { startCapturePlaybackPreparation() },
      onRefresh: { startCapturePlaybackPreparation(forceRefresh: true) }
    )
  }

  /// Resolve the capture's signed URL after the canonical detail has loaded.
  /// A nil moment is acknowledged once preparation returns any honest state;
  /// an explicit moment is acknowledged only after exact aggregate seeking.
  @MainActor
  private func prepareCapturePlaybackIfNeeded(
    forceRefresh: Bool = false,
    requestGeneration: Int
  ) async {
    guard isCurrentCaptureFocusRequest(requestGeneration) else { return }
    guard Self.showsCapturePlayback(for: displayConversation.source, in: .transcript) else {
      if initialCaptureMomentTimestamp == nil {
        reportInitialCaptureFocus(resolved: true)
      } else {
        reportInitialCaptureFocus(resolved: false)
      }
      return
    }

    guard
      let resolution = await capturePlayback.prepare(
        for: displayConversation,
        forceRefresh: forceRefresh,
        transcriptOnMediaClock: transcriptOnMediaClock
      )
    else { return }
    guard isCurrentCaptureFocusRequest(requestGeneration) else { return }
    showServerClockTranscriptIfPlaybackIsAFallback(resolution)

    guard let requestedMoment = initialCaptureMomentTimestamp else {
      reportInitialCaptureFocus(resolved: true)
      return
    }

    let didCompleteSeek = await capturePlayback.seekToMoment(wallOffset: requestedMoment)
    guard isCurrentCaptureFocusRequest(requestGeneration) else { return }
    let resolved = CaptureFocusAcknowledgementPolicy.canAcknowledge(
      requestedMoment: requestedMoment,
      resolution: resolution,
      didCompleteSeek: didCompleteSeek
    )
    reportInitialCaptureFocus(resolved: resolved)
  }

  @MainActor
  private func startCapturePlaybackPreparation(forceRefresh: Bool = false) {
    captureFocusGeneration &+= 1
    let requestGeneration = captureFocusGeneration
    didResolveInitialCaptureFocus = false
    Task {
      await prepareCapturePlaybackIfNeeded(
        forceRefresh: forceRefresh,
        requestGeneration: requestGeneration
      )
    }
  }

  private func isCurrentDetailRequest(_ requestGeneration: Int) -> Bool {
    ConversationDetailRequestGate.canApply(
      requestGeneration: requestGeneration,
      currentGeneration: detailLoadGeneration,
      isCancelled: Task.isCancelled
    )
  }

  private func isCurrentCaptureFocusRequest(_ requestGeneration: Int) -> Bool {
    ConversationDetailRequestGate.canApply(
      requestGeneration: requestGeneration,
      currentGeneration: captureFocusGeneration,
      isCancelled: Task.isCancelled
    )
  }

  private func reportInitialCaptureFocus(resolved: Bool) {
    // Keep failed attempts retryable (for example, when aggregate audio is
    // still pending), but never send a second success callback for one detail.
    if resolved {
      guard !didResolveInitialCaptureFocus else { return }
      didResolveInitialCaptureFocus = true
    }
    onCaptureFocusResolved?(resolved)
  }

  // MARK: - Transcript Pane

  /// Refresh: re-fetch the transcript and rebuild the audio player from fresh signed URLs, so a
  /// stale detail or an expired link recovers without leaving and reopening the conversation.
  private var refreshTranscriptButton: some View {
    let isBusy = isRefreshingTranscript || transcriptResync.phase.isBusy
    return Button(action: refreshTranscript) {
      Image(systemName: "arrow.clockwise")
        .scaledFont(size: OmiType.body, weight: .medium)
        .rotationEffect(.degrees(isBusy ? 360 : 0))
        .animation(
          isBusy ? .linear(duration: 0.8).repeatForever(autoreverses: false) : .default,
          value: isBusy
        )
    }
    .buttonStyle(GlassIconButtonStyle(diameter: OmiIconButtonSize.regular.diameter, restsFilled: true))
    .disabled(isBusy)
    .help("Refresh transcript and re-sync it to the audio")
    .accessibilityLabel("Refresh transcript and re-sync it to the audio")
    .accessibilityIdentifier("conversation-detail-transcript-refresh")
  }

  @ViewBuilder
  private var transcriptDrawerView: some View {
    VStack(alignment: .leading, spacing: 0) {
      if Self.showsCapturePlayback(for: displayConversation.source, in: .transcript) {
        capturePlaybackSection
          .padding(.horizontal, OmiSpacing.xxl)
          .padding(.bottom, OmiSpacing.md)
      }

      if displayConversation.transcriptPresenceState == .lockedOrRedacted && !isLoadingConversation {
        GlassEmptyState(
          systemImage: "lock", title: "Transcript locked",
          message: "This transcript is available again once your subscription is active.")
      } else if displayConversation.transcriptSegments.isEmpty && !isLoadingConversation {
        GlassEmptyState(
          systemImage: "text.quote", title: "No transcript",
          message: "Nothing was transcribed for this conversation.")
      } else if isLoadingConversation {
        VStack(spacing: OmiSpacing.md) {
          ProgressView()
            .controlSize(.small)
          Text("Loading transcript…")
            .scaledFont(size: OmiType.body)
            .foregroundColor(Ink.secondary)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
      } else {
        ScrollViewReader { proxy in
          // LazyVStack is a DIRECT child of ScrollView so it gets bounded proposed height
          // and only materializes visible children.
          ScrollView {
            LazyVStack(alignment: .leading, spacing: OmiSpacing.sm) {
              transcriptBubblesContent
            }
            // Bubbles carry their own 16 pt inset, so 8 here lines their text up with the header.
            .padding(.horizontal, OmiSpacing.sm)
            .padding(.bottom, OmiSpacing.section)
          }
          // A soft top edge, so a speaker label scrolling under the header fades instead of being
          // sliced mid-glyph.
          .glassScrollFade(top: OmiSpacing.lg)
          .onAppear { focusTranscript(using: proxy) }
          .onChange(of: automation.focusedTranscriptSegmentIds) { _, _ in
            focusTranscript(using: proxy)
          }
          .onChange(of: displayConversation.transcriptSegments.count) { _, _ in
            focusTranscript(using: proxy)
          }
          .onChange(of: activeCaptureTranscriptSegmentID) { _, segmentID in
            followCapturePlayback(using: proxy, segmentID: segmentID)
          }
          .onChange(of: transcriptSearch.revealRequest) { _, _ in
            guard let segmentID = transcriptSearch.currentMatch?.segmentID else { return }
            proxy.scrollTo(segmentID, anchor: .center)
          }
        }
      }
    }
    // Esc clears and closes find before the pane's own Esc leaves the transcript.
    .onEscapeKey(priority: .editing) {
      guard isTranscriptSearchOpen else { return false }
      closeTranscriptSearch()
      return true
    }
    .onChange(of: displayConversation.transcriptSegments.count) { _, _ in
      if transcriptSearch.isActive { runTranscriptSearch(transcriptSearch.query) }
    }
    .onDisappear { closeTranscriptSearch() }
  }

  private func closeTranscript() {
    OmiMotion.withGated(.easeInOut(duration: 0.25)) {
      showTranscriptDrawer = false
    }
  }

  private func openTranscriptSearch() {
    isTranscriptSearchOpen = true
    DispatchQueue.main.async { isTranscriptSearchFocused = true }
  }

  private func closeTranscriptSearch() {
    runTranscriptSearch("")
    isTranscriptSearchOpen = false
    isTranscriptSearchFocused = false
  }

  private func runTranscriptSearch(_ query: String) {
    transcriptSearch.update(
      query: query,
      segments: displayConversation.transcriptSegments.map { (id: $0.backendId ?? $0.id, text: $0.text) })
  }

  // MARK: - Transcript Bubbles (shared)

  /// Flat content intended to be placed inside a parent LazyVStack.
  /// Do NOT wrap this in another LazyVStack or VStack — it emits ForEach items directly.
  @ViewBuilder
  private var transcriptBubblesContent: some View {
    let peopleDict = Dictionary(lastWriteWins: people.map { ($0.id, $0) })
    ForEach(displayConversation.transcriptSegments) { segment in
      let segmentID = segment.backendId ?? segment.id
      let isPlaybackActive = activeCaptureTranscriptSegmentID == segmentID
      SpeakerBubbleView(
        segment: segment,
        isUser: segment.isUser,
        personName: segment.personId.flatMap { peopleDict[$0]?.name },
        onSpeakerTapped: segment.isUser
          ? nil
          : {
            selectedSegmentForNaming = segment
          },
        onMomentTapped: Self.showsCapturePlayback(for: displayConversation.source, in: .transcript)
          ? {
            Task { await capturePlayback.playFromMoment(wallOffset: segment.start) }
          }
          : nil,
        isMomentPlayable: canSeekCaptureMoment(segment),
        searchHighlights: transcriptSearch.ranges(inSegment: segmentID),
        currentSearchHighlight: transcriptSearch.currentRange(inSegment: segmentID)
      )
      .padding(.horizontal, OmiSpacing.lg)
      .padding(.vertical, OmiSpacing.xs)
      .background(
        RoundedRectangle(cornerRadius: OmiChrome.smallControlRadius)
          .fill(
            automation.focusedTranscriptSegmentIds.contains(segment.backendId ?? segment.id)
              ? Ink.rowFillHover
              : isPlaybackActive ? Ink.accent.opacity(0.12) : Color.clear
          )
      )
      .overlay(
        RoundedRectangle(cornerRadius: OmiChrome.smallControlRadius)
          .stroke(isPlaybackActive ? Ink.accent.opacity(0.45) : Color.clear, lineWidth: 1)
      )
      .accessibilityValue(isPlaybackActive ? "Currently playing" : "")
      .id(segmentID)
    }
  }

  private func canSeekCaptureMoment(_ segment: TranscriptSegment) -> Bool {
    guard Self.showsCapturePlayback(for: displayConversation.source, in: .transcript),
      let resolution = capturePlayback.resolution
    else { return false }
    return resolution.playbackOffset(forWallOffset: segment.start) != nil
  }

  /// The highlighted bubble is the transport's current position, so it also
  /// marks where a paused or scrubbed player will resume, not only live playback.
  private var activeCaptureTranscriptSegmentID: String? {
    guard capturePlayback.isPlaybackRequested || capturePlayback.currentTime > 0,
      let resolution = capturePlayback.resolution
    else { return nil }
    return CaptureTranscriptFollowPolicy.activeSegmentID(
      atPlaybackOffset: capturePlayback.currentTime,
      resolution: resolution,
      segments: displayConversation.transcriptSegments
    )
  }

  private func followCapturePlayback(using proxy: ScrollViewProxy, segmentID: String?) {
    guard showTranscriptDrawer, capturePlayback.isPlaybackRequested, let segmentID else { return }
    OmiMotion.withGated(.easeInOut(duration: 0.2)) {
      proxy.scrollTo(segmentID, anchor: .center)
    }
  }

  private func focusTranscript(using proxy: ScrollViewProxy) {
    guard showTranscriptDrawer,
      let segmentID = automation.focusedTranscriptSegmentIds.first,
      displayConversation.transcriptSegments.contains(where: { ($0.backendId ?? $0.id) == segmentID })
    else { return }
    DispatchQueue.main.async {
      OmiMotion.withGated(.easeInOut(duration: 0.25)) {
        proxy.scrollTo(segmentID, anchor: .center)
      }
    }
  }

  @MainActor
  private func updateDisplayedConversation(segmentIndices: [Int], isUser: Bool, personId: String?) {
    var updatedConversation = displayConversation
    for index in segmentIndices where updatedConversation.transcriptSegments.indices.contains(index) {
      let oldSegment = updatedConversation.transcriptSegments[index]
      updatedConversation.transcriptSegments[index] = TranscriptSegment(
        id: oldSegment.id,
        backendId: oldSegment.backendId,
        text: oldSegment.text,
        speaker: oldSegment.speaker,
        isUser: isUser,
        personId: isUser ? nil : personId,
        start: oldSegment.start,
        end: oldSegment.end,
        translations: oldSegment.translations
      )
    }
    loadedConversation = updatedConversation
  }

  // MARK: - Deferred Processing Loader

  /// Overlaid while a lazily-deferred conversation is enriched, preserving the
  /// position of details that may already be available from the local cache.
  private var deferredProcessingSection: some View {
    ConversationProcessingBanner(conversation: displayConversation) { updated in
      loadedConversation = updated
      isEnrichingDeferred = false
    }
  }

  // MARK: - Overview Section

  private var overviewSection: some View {
    let selection = ConversationSummarySelection.primarySummary(for: displayConversation)
    let primaryApp = selection.appId.flatMap { id in appProvider.apps.first { $0.id == id } }

    return VStack(alignment: .leading, spacing: OmiSpacing.sm) {
      DetailSectionHeader(title: "Overview", systemImage: "text.alignleft") {
        // The selected summarization app owns this section; say which one.
        if let appName = selection.appDisplayName(resolvedName: primaryApp?.name) {
          Text(appName)
            .scaledFont(size: OmiType.caption, weight: .medium)
            .foregroundColor(Ink.secondary)
            .padding(.horizontal, OmiSpacing.sm)
            .padding(.vertical, OmiSpacing.hairline)
            .glassChip()
        }
        Button(action: { showAppSelector = true }) {
          DetailQuietButtonLabel(
            title: selection.kind == .app ? "Change app" : "Summarize with an app",
            systemImage: "arrow.triangle.2.circlepath")
        }
        .buttonStyle(.plain)
        .disabled(isReprocessing)
        .help("Choose the app that summarizes this conversation")
      }

      // No `colorScheme` override here. This section used to force `.dark` so the markdown would
      // resolve light-on-dark for the old near-black page; on the glass panel that renders the
      // whole summary — the longest prose in the app — in near-white on a near-white ground. The
      // page is `glassContent()`, which already pins the panel's light appearance, and the markdown
      // inherits it.
      //
      // Selection is AppKit prose, not a SwiftUI native-selection modifier on an ancestor:
      // that wraps this tall block in SelectionOverlay and re-lays-out the visible portion
      // while the reader scrolls (FC-selection-overlay-layout-loop; same contract as chat).
      ConversationSummaryBody(
        conversation: displayConversation,
        onOpenSources: { sourceIDs in
          ConversationDetailAutomationState.shared.requestOpen(
            conversationId: displayConversation.id,
            showTranscript: true,
            transcriptSegmentIds: sourceIDs
          )
        }
      )
    }
  }

  // MARK: - Reprocess

  private func reprocessWithApp(_ app: OmiApp) async {
    let requestGeneration = detailLoadGeneration
    isReprocessing = true
    defer {
      isReprocessing = false
      selectedAppForReprocess = nil
      showAppSelector = false
    }

    // Track reprocess
    AnalyticsManager.shared.conversationReprocessed(conversationId: conversation.id, appId: app.id)

    // Mobile parity: the backend resolves reprocess targets from the enabled
    // slice (plus defaults), so a not-yet-enabled pick is enabled first —
    // otherwise it silently clears apps_results and produces no summary.
    if !app.enabled {
      await appProvider.enableApp(app)
      guard isCurrentDetailRequest(requestGeneration) else { return }
    }

    do {
      // The route returns the updated conversation; adopting it repaints the
      // summary pane with the selected app as primary.
      let updated = try await APIClient.shared.reprocessConversation(
        conversationId: conversation.id,
        appId: app.id
      )
      guard isCurrentDetailRequest(requestGeneration) else { return }
      loadedConversation = updated
      AppState.current?.replaceConversation(updated)
    } catch {
      logError("Failed to reprocess conversation", error: error)
    }
  }

  /// Persists the preferred summarization app locally (the backend has no GET
  /// for it) and server-side, where future conversation processing keys on it.
  private func setPreferredSummaryApp(_ app: OmiApp) {
    preferredSummaryAppId = app.id
    UserDefaults.standard.set(app.id, forKey: .preferredSummarizationAppId)
    Task {
      do {
        try await APIClient.shared.setPreferredSummarizationApp(appId: app.id)
      } catch {
        logError("Failed to set preferred summarization app", error: error)
      }
    }
  }
}

#if canImport(PreviewsMacros)
  #Preview {
    ConversationDetailView(
      conversation: ServerConversation.preview,
      onBack: {}
    )
    .frame(width: 600, height: 800)
    .background(Ink.surface)
  }
#endif

// Preview helper
extension ServerConversation {
  static var preview: ServerConversation {
    // This would need to be implemented with a proper initializer
    // For now, previews won't work without mock data
    fatalError("Preview not implemented")
  }
}
