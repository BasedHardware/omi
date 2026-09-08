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

/// A parent can replace a conversation row without changing its identity
/// (rename, folder move, processing completion). Keying detail work only by ID
/// leaves the open panel pinned to the old value, so these visible revisions
/// participate in the request identity as well.
struct ConversationDetailRequestToken: Hashable {
  let conversationID: String
  let updatedAt: Date?
  let title: String
  let folderID: String?
  let status: String

  init(conversation: ServerConversation) {
    self.init(
      conversationID: conversation.id,
      updatedAt: conversation.updatedAt,
      title: conversation.title,
      folderID: conversation.folderId,
      status: String(describing: conversation.status)
    )
  }

  init(
    conversationID: String,
    updatedAt: Date?,
    title: String,
    folderID: String?,
    status: String
  ) {
    self.conversationID = conversationID
    self.updatedAt = updatedAt
    self.title = title
    self.folderID = folderID
    self.status = status
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
  /// This note's screenshots, owned here rather than inside the summary because both halves of the
  /// note read them: the strip is in the summary, and the banner is the *header's* background.
  /// Constructing it is free — the initialiser only captures closures — and it starts no work
  /// until `MeetingNoteScreenshotStrip`'s task calls `load()`, which the gate below still governs.
  @StateObject private var screenshotsStore = MeetingScreenshotsStore()
  /// Descriptions the reader has explicitly added to their task list from this
  /// summary, and those currently in flight. Action items on a summary are not
  /// tasks (I1); this is the record of the reader's own "Add to Tasks" gesture.
  @State private var addedActionItemIDs: Set<String> = []
  @State private var addingActionItemIDs: Set<String> = []
  @State private var showAppSelector = false
  @State private var isReprocessing = false
  @State private var selectedAppForReprocess: OmiApp?
  /// Locally mirrored preferred summarization app (mobile keeps the same key
  /// in SharedPreferences; the backend exposes no GET for it).
  @State private var preferredSummaryAppId: String?

  // Transcript presentation state. Summary and transcript are exclusive panes so neither one is
  // compressed into an unreadable split view at the minimum window width.
  @State private var showTranscriptDrawer = false

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

  // Static date formatters — creating DateFormatter is expensive, avoid per-render allocation
  private static let dayDateFormatter: DateFormatter = {
    let f = DateFormatter()
    f.dateFormat = "EEEE, MMM d, yyyy"
    return f
  }()
  private static let timeOnlyFormatter: DateFormatter = {
    let f = DateFormatter()
    f.dateFormat = "h:mm a"
    return f
  }()
  private static let shortDateFormatter: DateFormatter = {
    let f = DateFormatter()
    f.dateFormat = "MMM d, yyyy"
    return f
  }()

  /// Format date for display
  private var formattedDate: String {
    Self.dayDateFormatter.string(from: displayDate)
  }

  /// Format time for display
  private var formattedTime: String {
    Self.timeOnlyFormatter.string(from: displayDate)
  }

  /// Format time range for header subtitle (e.g., "Jan 15, 2025 from 2:30 PM to 3:15 PM")
  private var formattedTimeRange: String {
    let dateStr = Self.shortDateFormatter.string(from: displayDate)
    let startStr = Self.timeOnlyFormatter.string(from: displayDate)

    if let finishedAt = displayConversation.finishedAt {
      let endStr = Self.timeOnlyFormatter.string(from: finishedAt)
      return "\(dateStr) from \(startStr) to \(endStr)"
    }
    return "\(dateStr) at \(startStr)"
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
    Group {
      switch Self.visiblePane(transcriptOpen: showTranscriptDrawer) {
      case .summary:
        VStack(alignment: .leading, spacing: 0) {
          headerView

          ScrollView {
            // Card container wrapping summary content
            VStack(alignment: .leading, spacing: 0) {
              // Card header bar
              HStack(spacing: OmiSpacing.sm) {
                Image(systemName: "doc.text")
                  .scaledFont(size: OmiType.caption)
                  .foregroundColor(Ink.secondary)
                Text("Conversation Details")
                  .scaledFont(size: OmiType.body, weight: .medium)
                  .foregroundColor(Ink.secondary)
                Spacer()
              }
              .padding(.horizontal, OmiSpacing.lg)
              .padding(.vertical, OmiSpacing.sm)
              .background(Ink.rowFillHover.opacity(0.4))

              ConversationDetailProcessingLayout(isProcessing: isEnrichingDeferred) {
                deferredProcessingSection
              } content: {
                summaryContent
              }
              .padding(OmiSpacing.xxl)
            }
            .glassCard(cornerRadius: OmiChrome.controlRadius)
            .clipShape(RoundedRectangle(cornerRadius: OmiChrome.controlRadius))
            .padding(OmiSpacing.xxl)
          }
          .glassScrollFade()
        }
        .transition(.move(edge: .leading))
      case .transcript:
        transcriptDrawerView
          .frame(maxWidth: .infinity, maxHeight: .infinity)
          .transition(.move(edge: .trailing))
      }
    }
    .opacity(hasAppeared ? 1 : 0)
    .offset(y: hasAppeared ? 0 : 20)
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
      }
    }
    .onDisappear {
      detailLoadGeneration &+= 1
      captureFocusGeneration &+= 1
      detailReadyConversationID = nil
      ConversationDetailAutomationState.shared.clear(conversationId: conversation.id)
      capturePlayback.clear()
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
            loadedConversation = cached
          }
          guard isCurrentDetailRequest(requestGeneration) else { return }
          loadedConversation = fetched
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
            loadedConversation = cached
          }
          guard isCurrentDetailRequest(requestGeneration) else { return }
          loadedConversation = fetched
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

  private var headerView: some View {
    HStack(spacing: OmiSpacing.md) {
      // Back button
      // A stadium chip, not blue text. `Ink.accent` is spent on the one link in this system that
      // is actionable and is not already a button; Back is already a button, and a blue word
      // floating beside a black headline is the loudest thing on the panel.
      Button(action: onBack) {
        HStack(spacing: OmiSpacing.xs) {
          Image(systemName: "chevron.left")
            .scaledFont(size: OmiType.caption, weight: .semibold)
          Text("Back")
            .scaledFont(size: OmiType.caption, weight: .semibold)
        }
        .foregroundColor(Ink.primary)
        .padding(.horizontal, OmiSpacing.md)
        .frame(height: 30)
        .glassChip()
      }
      .buttonStyle(.plain)

      // Emoji
      Text(displayConversation.structured.emoji.isEmpty ? "\u{1F4AC}" : displayConversation.structured.emoji)
        .scaledFont(size: OmiType.title)

      // Title + timestamp subtitle
      VStack(alignment: .leading, spacing: OmiSpacing.hairline) {
        HStack(spacing: OmiSpacing.sm) {
          Text(displayConversation.displayTitle)
            .scaledFont(size: OmiType.heading, weight: .semibold)
            .foregroundColor(detailTitleColor)
            .lineLimit(1)

          ConversationStatusBadge(state: displayConversation.displayState)

          // Edit title button (inline with title)
          Button(action: {
            editedTitle = displayConversation.title
            showEditDialog = true
          }) {
            Image(systemName: "pencil")
              .scaledFont(size: OmiType.body)
              .foregroundColor(Ink.secondary)
          }
          .buttonStyle(.plain)
          .help("Edit title")
        }

        Text(formattedTimeRange)
          .scaledFont(size: OmiType.caption)
          .foregroundColor(Ink.secondary)
      }

      Spacer()

      // The meeting's chosen frame, sharp and with nothing written over it. It sets this row's
      // height, so a note with a banner gets a slightly taller header and a note without one is
      // exactly as it was.
      headerBannerInset

      // View Transcript pill button
      viewTranscriptButton

      // Inline action buttons
      inlineActionButtons
    }
    .padding(.horizontal, OmiSpacing.xxl)
    .padding(.vertical, OmiSpacing.lg)
    // The banner, as this header's ground rather than as a slot below it. `MeetingNoteHeaderBanner`
    // draws no text — every word in this header is still the header's own real chrome, in front of
    // it — and it is absent entirely when the note has no approved frame, which leaves the ordinary
    // header exactly as it was.
    .background(headerBanner)
    .alert("Edit Conversation Title", isPresented: $showEditDialog) {
      TextField("Title", text: $editedTitle)
      Button("Cancel", role: .cancel) {}
      Button("Save") {
        Task { await updateTitle() }
      }
      .disabled(editedTitle.isEmpty || isUpdatingTitle)
    } message: {
      Text("Enter a new title for this conversation")
    }
    .alert("Delete Conversation", isPresented: $showDeleteConfirmation) {
      Button("Cancel", role: .cancel) {}
      Button("Delete", role: .destructive) {
        Task { await deleteConversation() }
      }
    } message: {
      Text("Are you sure you want to delete this conversation? This action cannot be undone.")
    }
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

  // MARK: - View Transcript Button

  private var viewTranscriptButton: some View {
    Button(action: {
      OmiMotion.withGated(.easeInOut(duration: 0.25)) {
        showTranscriptDrawer = true
      }
    }) {
      HStack(spacing: OmiSpacing.xs) {
        Image(systemName: "text.quote")
          .scaledFont(size: OmiType.caption)
        Text("View Transcript")
          .scaledFont(size: OmiType.caption, weight: .medium)
      }
      .foregroundColor(Ink.secondary)
      .padding(.horizontal, OmiSpacing.md)
      .padding(.vertical, OmiSpacing.xs)
      .background(
        Capsule()
          .fill(Ink.rowFillHover)
      )
    }
    .buttonStyle(.plain)
  }

  // MARK: - Inline Action Buttons

  private var inlineActionButtons: some View {
    HStack(spacing: OmiSpacing.sm) {
      if let onDiscussInChat {
        Button(action: onDiscussInChat) {
          HStack(spacing: OmiSpacing.xs) {
            Image(systemName: "bubble.left.and.bubble.right")
              .scaledFont(size: OmiType.caption)
            Text("Discuss in Chat")
              .scaledFont(size: OmiType.caption, weight: .medium)
              .lineLimit(1)
              .fixedSize(horizontal: true, vertical: false)
          }
          .foregroundColor(Ink.secondary)
          .padding(.horizontal, OmiSpacing.md)
          .padding(.vertical, OmiSpacing.xs)
          .frame(minWidth: 126)
          .background(Capsule().fill(Ink.rowFillHover))
        }
        .buttonStyle(.plain)
        .accessibilityLabel("Discuss this conversation in Chat")
        // Preserve the capture archive's automation contract while the
        // presentation itself moves into the canonical detail.
        .accessibilityIdentifier("chat-first-capture-discuss-\(conversation.id)")
      }

      // Copy share link (minting flips visibility to shared; the control
      // discloses and confirms that itself).
      ConversationShareLinkButton(
        conversationId: conversation.id,
        canShare: canShareConversation,
        onCopied: {
          AnalyticsManager.shared.shareAction(
            category: "conversation", properties: ["conversation_id": conversation.id])
        }
      )

      // Copy transcript button
      Button(action: copyTranscript) {
        Image(systemName: "doc.on.doc")
          .scaledFont(size: OmiType.body)
          .foregroundColor(Ink.secondary)
          .frame(width: 28, height: 28)
          .background(
            Circle()
              .fill(Ink.rowFillHover)
          )
      }
      .buttonStyle(.plain)
      .disabled(!canCopyTranscript)
      .help("Copy transcript")

      // Move to folder button (menu)
      if !folders.isEmpty {
        Menu {
          if displayConversation.folderId != nil {
            Button(action: {
              Task { await onMoveToFolder?(conversation.id, nil) }
            }) {
              Label("Remove from Folder", systemImage: "folder.badge.minus")
            }
            Divider()
          }

          ForEach(folders) { folder in
            Button(action: {
              Task { await onMoveToFolder?(conversation.id, folder.id) }
            }) {
              HStack {
                Text(folder.name)
                if displayConversation.folderId == folder.id {
                  Image(systemName: "checkmark")
                }
              }
            }
            .disabled(displayConversation.folderId == folder.id)
          }
        } label: {
          Image(systemName: displayConversation.folderId != nil ? "folder.fill" : "folder")
            .scaledFont(size: OmiType.body)
            .foregroundColor(displayConversation.folderId != nil ? Ink.primary : Ink.secondary)
            .frame(width: 28, height: 28)
            .background(
              Circle()
                .fill(Ink.rowFillHover)
            )
        }
        // `.borderlessButton` tints its template label with the *system* accent, which the
        // `foregroundColor` inside the label does not override — this glyph rendered blue in a
        // toolbar of neutral glass circles. The tint is the only lever that reaches it.
        .tint(Ink.primary)
        .menuStyle(.borderlessButton)
        .frame(width: 28)
        .help("Move to folder")
      }

      // Delete button
      Button(action: { showDeleteConfirmation = true }) {
        Image(systemName: "trash")
          .scaledFont(size: OmiType.body)
          .foregroundColor(Ink.errorRed)
          .frame(width: 28, height: 28)
          .background(
            Circle()
              .fill(Ink.rowFillHover)
          )
      }
      .buttonStyle(.plain)
      .help("Delete conversation")
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

  private func copyTranscript() {
    guard canCopyTranscript else { return }

    let peopleDict = Dictionary(lastWriteWins: people.map { ($0.id, $0) })
    let transcript: String = displayConversation.transcriptSegments.map { segment -> String in
      let speakerName: String
      if segment.isUser {
        speakerName = "You"
      } else if let personId = segment.personId, let person = peopleDict[personId] {
        speakerName = person.name
      } else {
        speakerName = "Speaker \(segment.speaker ?? "Unknown")"
      }
      return "[\(speakerName)]: \(segment.text)"
    }.joined(separator: "\n\n")

    NSPasteboard.general.clearContents()
    NSPasteboard.general.setString(transcript, forType: .string)
  }

  private func updateTitle() async {
    guard !editedTitle.isEmpty else { return }
    let requestGeneration = detailLoadGeneration
    isUpdatingTitle = true
    defer { isUpdatingTitle = false }

    await AppState.current?.updateConversationTitle(conversation.id, title: editedTitle)
    guard isCurrentDetailRequest(requestGeneration) else { return }
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

  /// Title color in the header — dim placeholder titles (Processing /
  /// Locked / Untitled) so they read as secondary text rather than as the
  /// real title of the conversation.
  private var detailTitleColor: Color {
    switch displayConversation.displayState {
    case .titled: return Ink.primary
    default: return Ink.secondary
    }
  }

  // MARK: - Summary Content (always visible, no tabs)

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

    // The backend's headed summary blocks. `overview` is only a compatibility paragraph now, so
    // without these the pane shows a fraction of what was actually written.
    //
    // Shown only when Omi's own summary is the one on screen. `sections` belongs to the first-party
    // structured summary, and a promoted app result already *replaces* that summary — rendering
    // both stacks a second, unattributed Omi summary under the app's, which is also the one thing
    // the Flutter client deliberately does not do.
    if selection.appId == nil {
      ConversationSummarySections(sections: displayConversation.structured.sections)
        .padding(.horizontal, OmiSpacing.lg)
    }

    ConversationPhotoGallery(
      conversationID: displayConversation.id,
      photos: displayConversation.photos)

    // Action items sit directly under the summary: they are the part of a
    // meeting a reader acts on. Nothing here is a task until the reader says
    // so (I1) — each row carries its own "Add to Tasks".
    if !displayConversation.structured.actionItems.isEmpty {
      actionItemsSection
    }
  }

  @ViewBuilder
  private var summaryAfterScreenshots: some View {
    // Metadata chips
    metadataSection

    // App Results section (insights beyond the promoted primary summary)
    if !ConversationSummarySelection.secondaryResults(for: displayConversation).isEmpty {
      appResultsSection
    }

    // Suggested apps section
    suggestedAppsSection
  }

  // MARK: - Capture Playback

  @ViewBuilder
  private var capturePlaybackSection: some View {
    ConversationCapturePlaybackSection(
      capture: displayConversation,
      playback: capturePlayback,
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
        forceRefresh: forceRefresh
      )
    else { return }
    guard isCurrentCaptureFocusRequest(requestGeneration) else { return }

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

  // MARK: - Transcript Drawer

  @ViewBuilder
  private var transcriptDrawerView: some View {
    VStack(alignment: .leading, spacing: 0) {
      // Drawer header
      HStack(spacing: OmiSpacing.sm) {
        Image(systemName: "text.quote")
          .scaledFont(size: OmiType.body)
          .foregroundColor(Ink.secondary)

        Text("Transcript")
          .scaledFont(size: OmiType.subheading, weight: .semibold)
          .foregroundColor(Ink.primary)

        // Segment count badge
        Text("\(displayConversation.transcriptSegments.count)")
          .scaledFont(size: OmiType.caption, weight: .medium)
          .foregroundColor(Ink.secondary)
          .padding(.horizontal, OmiSpacing.sm)
          .padding(.vertical, OmiSpacing.hairline)
          .background(
            Capsule()
              .fill(Ink.rowFillHover)
          )

        Spacer()

        // Copy button
        Button(action: copyTranscript) {
          Image(systemName: "doc.on.doc")
            .scaledFont(size: OmiType.body)
            .foregroundColor(Ink.secondary)
            .frame(width: 28, height: 28)
            .background(
              Circle()
                .fill(Ink.rowFillHover)
            )
        }
        .buttonStyle(.plain)
        .help("Copy transcript")

        // Close button
        Button(action: {
          OmiMotion.withGated(.easeInOut(duration: 0.25)) {
            showTranscriptDrawer = false
          }
        }) {
          Image(systemName: "xmark")
            .scaledFont(size: OmiType.body)
            .foregroundColor(Ink.secondary)
            .frame(width: 28, height: 28)
            .background(
              Circle()
                .fill(Ink.rowFillHover)
            )
        }
        .buttonStyle(.plain)
        .help("Close transcript")
      }
      .padding(.horizontal, OmiSpacing.xl)
      .padding(.vertical, OmiSpacing.md)
      .background(Ink.rowFillHover.opacity(0.5))

      if Self.showsCapturePlayback(for: displayConversation.source, in: .transcript) {
        capturePlaybackSection
          .padding(.horizontal, OmiSpacing.xl)
          .padding(.vertical, OmiSpacing.md)
      }

      // Drawer content
      if displayConversation.transcriptPresenceState == .lockedOrRedacted && !isLoadingConversation {
        VStack(spacing: OmiSpacing.md) {
          Image(systemName: "lock")
            .scaledFont(size: OmiType.hero)
            .foregroundColor(Ink.secondary)

          Text("Transcript locked")
            .scaledFont(size: OmiType.body)
            .foregroundColor(Ink.secondary)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
      } else if displayConversation.transcriptSegments.isEmpty && !isLoadingConversation {
        // Empty state
        VStack(spacing: OmiSpacing.md) {
          Image(systemName: "text.quote")
            .scaledFont(size: OmiType.hero)
            .foregroundColor(Ink.secondary)

          Text("No transcript available")
            .scaledFont(size: OmiType.body)
            .foregroundColor(Ink.secondary)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
      } else if isLoadingConversation {
        // Loading state
        VStack(spacing: OmiSpacing.md) {
          ProgressView()
            .scaleEffect(0.8)

          Text("Loading transcript...")
            .scaledFont(size: OmiType.body)
            .foregroundColor(Ink.secondary)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
      } else {
        ScrollViewReader { proxy in
          // LazyVStack is a DIRECT child of ScrollView so it gets bounded proposed height
          // and only materializes visible children.
          ScrollView {
            LazyVStack(alignment: .leading, spacing: OmiSpacing.md) {
              transcriptBubblesContent
            }
            .padding(OmiSpacing.lg)
          }
          .glassScrollFade()
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
        }
      }
    }
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
        onTimestampTapped: Self.showsCapturePlayback(for: displayConversation.source, in: .transcript)
          ? {
            Task { _ = await capturePlayback.seekToMoment(wallOffset: segment.start) }
          }
          : nil,
        isTimestampPlayable: canSeekCaptureMoment(segment)
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
      case .readyAggregate(let artifact) = capturePlayback.resolution
    else { return false }
    return artifact.artifactOffset(forWallOffset: segment.start) != nil
  }

  private var activeCaptureTranscriptSegmentID: String? {
    guard capturePlayback.isPlaybackRequested, let resolution = capturePlayback.resolution else { return nil }
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
      HStack(spacing: OmiSpacing.xs) {
        Image(systemName: "star.fill")
          .scaledFont(size: OmiType.body)
          .foregroundColor(PageGlass.starred)

        Text("Summary")
          .scaledFont(size: OmiType.body, weight: .semibold)
          .foregroundColor(Ink.secondary)

        // The selected summarization app owns this section; say which one.
        if let primaryApp {
          Text(primaryApp.name)
            .scaledFont(size: OmiType.caption, weight: .medium)
            .foregroundColor(Ink.secondary)
            .padding(.horizontal, OmiSpacing.sm)
            .padding(.vertical, OmiSpacing.xxs)
            .background(
              Capsule()
                .fill(Ink.rowFillHover)
            )
        }

        Spacer()

        Button(action: { showAppSelector = true }) {
          HStack(spacing: OmiSpacing.xxs) {
            Image(systemName: "arrow.triangle.2.circlepath")
              .scaledFont(size: OmiType.caption)
            Text(primaryApp == nil ? "Summary App" : "Change")
              .scaledFont(size: OmiType.caption, weight: .medium)
          }
          .foregroundColor(Ink.secondary)
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
      OmiMarkdown(text: selection.content, sender: .ai)
        .textSelection(.enabled)
        .frame(maxWidth: .infinity, alignment: .leading)
    }
  }

  // MARK: - Metadata Section

  private var metadataSection: some View {
    let participantLabels = Array(Set(displayConversation.transcriptSegments.compactMap(\.speaker))).sorted()
    return VStack(alignment: .leading, spacing: OmiSpacing.sm) {
      HStack(spacing: OmiSpacing.md) {
        // Source chip (device indicator)
        sourceChip

        // Duration chip
        metadataChip(icon: "hourglass", text: displayConversation.formattedDuration)

        // Category chip
        if !displayConversation.structured.category.isEmpty && displayConversation.structured.category != "other" {
          metadataChip(icon: "tag", text: displayConversation.structured.category.capitalized)
        }

        Spacer()
      }

      if let address = displayConversation.geolocation?.address, !address.isEmpty {
        Label(address, systemImage: "mappin.and.ellipse")
          .scaledFont(size: OmiType.caption)
          .foregroundStyle(Ink.secondary)
      }

      if !participantLabels.isEmpty {
        Label(participantLabels.joined(separator: ", "), systemImage: "person.2")
          .scaledFont(size: OmiType.caption)
          .foregroundStyle(Ink.secondary)
      }
    }
  }

  private var sourceChip: some View {
    metadataChip(icon: "dot.radiowaves.left.and.right", text: sourceLabel)
  }

  private var sourceLabel: String {
    switch displayConversation.source {
    case .desktop: return "Desktop"
    case .omi: return "omi"
    case .phone: return "Phone"
    case .appleWatch: return "Apple Watch"
    case .workflow: return "Workflow"
    case .screenpipe: return "Screenpipe"
    case .friend, .friendCom: return "Friend"
    case .openglass: return "OpenGlass"
    case .frame: return "Frame"
    case .bee: return "Bee"
    case .limitless: return "Limitless"
    case .plaud: return "Plaud"
    default: return "Unknown"
    }
  }

  private func metadataChip(icon: String, text: String) -> some View {
    HStack(spacing: OmiSpacing.xs) {
      Image(systemName: icon)
        .scaledFont(size: OmiType.caption)
        .foregroundColor(Ink.secondary)

      Text(text)
        .scaledFont(size: OmiType.caption)
        .foregroundColor(Ink.secondary)
    }
    .padding(.horizontal, OmiSpacing.sm)
    .padding(.vertical, OmiSpacing.xs)
    .background(
      Capsule()
        .fill(Ink.rowFillHover)
    )
  }

  // MARK: - App Results Section

  private var appResultsSection: some View {
    VStack(alignment: .leading, spacing: OmiSpacing.md) {
      HStack {
        Text("App Insights")
          .scaledFont(size: OmiType.body, weight: .semibold)
          .foregroundColor(Ink.secondary)

        Spacer()

        Button(action: { showAppSelector = true }) {
          HStack(spacing: OmiSpacing.xxs) {
            Image(systemName: "arrow.triangle.2.circlepath")
              .scaledFont(size: OmiType.caption)
            Text("Reprocess")
              .scaledFont(size: OmiType.caption)
          }
          .foregroundColor(Ink.secondary)
        }
        .buttonStyle(.plain)
        .disabled(isReprocessing)
      }

      ForEach(ConversationSummarySelection.secondaryResults(for: displayConversation)) { result in
        AppResultCard(
          result: result,
          app: appProvider.apps.first { $0.id == result.appId }
        )
      }
    }
  }

  // MARK: - Suggested Apps Section

  private var suggestedAppsSection: some View {
    VStack(alignment: .leading, spacing: OmiSpacing.md) {
      HStack {
        Text("Try with Apps")
          .scaledFont(size: OmiType.body, weight: .semibold)
          .foregroundColor(Ink.secondary)

        Spacer()
      }

      // The $0-shadow exclusion that kept this section empty now lives (and is
      // tested) in ConversationSummarySelection.suggestedApps.
      let memoryApps = ConversationSummarySelection.suggestedApps(
        appProvider.apps, results: displayConversation.appsResults
      ).prefix(4)

      if memoryApps.isEmpty && !appProvider.isLoading {
        Text("Enable apps with memory capability to get additional insights")
          .scaledFont(size: OmiType.body)
          .foregroundColor(Ink.secondary)
          .padding()
          .frame(maxWidth: .infinity)
          .background(
            RoundedRectangle(cornerRadius: OmiChrome.elementRadius)
              .fill(Ink.rowFill)
          )
      } else {
        ScrollView(.horizontal, showsIndicators: false) {
          HStack(spacing: OmiSpacing.md) {
            ForEach(Array(memoryApps)) { app in
              SuggestedAppCard(
                app: app,
                isLoading: selectedAppForReprocess?.id == app.id && isReprocessing,
                onTap: {
                  selectedAppForReprocess = app
                  Task {
                    await reprocessWithApp(app)
                  }
                }
              )
            }
          }
        }
      }
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

  // MARK: - Action Items Section

  private var actionItemsSection: some View {
    let activeItems = displayConversation.structured.actionItems.filter { !$0.deleted }
    return VStack(alignment: .leading, spacing: OmiSpacing.md) {
      HStack(spacing: OmiSpacing.sm) {
        Image(systemName: "checklist")
          .scaledFont(size: OmiType.body)
          .foregroundColor(Ink.secondary)

        Text("Action Items")
          .scaledFont(size: OmiType.subheading, weight: .semibold)
          .foregroundColor(Ink.secondary)

        // Count badge
        Text("\(activeItems.count)")
          .scaledFont(size: OmiType.caption, weight: .medium)
          .foregroundColor(Ink.secondary)
          .padding(.horizontal, OmiSpacing.sm)
          .padding(.vertical, OmiSpacing.hairline)
          .background(
            Capsule()
              .fill(Ink.rowFillHover)
          )

        Spacer()
      }

      VStack(alignment: .leading, spacing: OmiSpacing.sm) {
        ForEach(activeItems) { item in
          HStack(alignment: .top, spacing: OmiSpacing.sm) {
            Image(systemName: item.completed ? "checkmark.circle.fill" : "circle")
              .scaledFont(size: OmiType.subheading)
              .foregroundColor(item.completed ? Ink.listeningGreen : Ink.secondary)

            Text(item.description)
              .scaledFont(size: OmiType.body)
              .foregroundColor(item.completed ? Ink.secondary : Ink.primary)
              .textSelection(.enabled)
              .strikethrough(item.completed, color: Ink.secondary)

            Spacer(minLength: OmiSpacing.sm)

            if let taskID = item.targetTaskID, let onOpenLinkedTask {
              Button {
                onOpenLinkedTask(taskID)
              } label: {
                HStack(spacing: OmiSpacing.xxs) {
                  Image(systemName: "checklist")
                  Text("Open linked task")
                }
                .scaledFont(size: OmiType.caption)
                .foregroundColor(Ink.secondary)
              }
              .buttonStyle(.plain)
              .accessibilityIdentifier("chat-first-capture-task-\(taskID)")
              .help("Open the task linked to this action item")
            } else {
              addToTasksButton(for: item)
            }

            Button {
              ConversationDetailAutomationState.shared.requestOpen(
                conversationId: displayConversation.id,
                showTranscript: true,
                transcriptSegmentIds: item.sourceSegmentIDs
              )
            } label: {
              HStack(spacing: OmiSpacing.xxs) {
                Image(systemName: "text.quote")
                Text(item.sourceSegmentIDs.isEmpty ? "Transcript" : "Source")
              }
              .scaledFont(size: OmiType.caption)
              .foregroundColor(Ink.secondary)
            }
            .buttonStyle(.plain)
            .help("Open the full transcript")
          }
          .padding(OmiSpacing.md)
          .frame(maxWidth: .infinity, alignment: .leading)
          .background(
            RoundedRectangle(cornerRadius: OmiChrome.smallControlRadius)
              .fill(Ink.rowFillHover)
          )
          .overlay(
            RoundedRectangle(cornerRadius: OmiChrome.smallControlRadius)
              .stroke(Ink.rowFillHover.opacity(0.3), lineWidth: 1)
          )
        }
      }
    }
  }

  /// Explicit, per-item promotion of a summary action item into the task list.
  /// This gesture is the only way an extracted item becomes a task.
  @ViewBuilder
  private func addToTasksButton(for item: ActionItem) -> some View {
    let isAdded = addedActionItemIDs.contains(item.id)
    let isAdding = addingActionItemIDs.contains(item.id)

    Button {
      addActionItemToTasks(item)
    } label: {
      HStack(spacing: OmiSpacing.xxs) {
        Image(systemName: isAdded ? "checkmark" : "plus")
        Text(isAdded ? "Added" : "Add to Tasks")
      }
      .scaledFont(size: OmiType.caption)
      .foregroundColor(isAdded ? Ink.listeningGreen : Ink.secondary)
    }
    .buttonStyle(.plain)
    .disabled(isAdded || isAdding)
    .opacity(isAdding ? 0.5 : 1)
    .accessibilityIdentifier("action-item-add-to-tasks")
    .help(isAdded ? "Already in your tasks" : "Add this to your tasks")
  }

  private func addActionItemToTasks(_ item: ActionItem) {
    guard !addedActionItemIDs.contains(item.id), !addingActionItemIDs.contains(item.id) else { return }
    addingActionItemIDs.insert(item.id)
    Task { @MainActor in
      let created = await TasksStore.shared.createTask(
        description: item.description,
        dueAt: nil,
        priority: nil
      )
      addingActionItemIDs.remove(item.id)
      if created != nil {
        addedActionItemIDs.insert(item.id)
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

/// Source-specific transport embedded in the canonical transcript. Transcript
/// bubbles own precise moment seeking, so playback no longer creates a second
/// transcript-like list ahead of the conversation summary.
private struct ConversationCapturePlaybackSection: View {
  let capture: ServerConversation
  @ObservedObject var playback: CapturePlaybackController
  let onPrepare: () -> Void
  let onRefresh: () -> Void

  var body: some View {
    VStack(alignment: .leading, spacing: OmiSpacing.md) {
      HStack(spacing: OmiSpacing.sm) {
        Image(systemName: "waveform")
          .scaledFont(size: OmiType.body)
          .foregroundStyle(Ink.secondary)
        Text("Audio")
          .scaledFont(size: OmiType.subheading, weight: .semibold)
          .foregroundStyle(Ink.secondary)
        Spacer()
      }

      playbackControls
    }
    .padding(OmiSpacing.lg)
    .frame(maxWidth: .infinity, alignment: .leading)
    .background(
      RoundedRectangle(cornerRadius: OmiChrome.smallControlRadius, style: .continuous)
        .fill(Ink.rowFillHover.opacity(0.45))
    )
    .accessibilityIdentifier("conversation-detail-capture-playback")
  }

  @ViewBuilder
  private var playbackControls: some View {
    if playback.isResolving {
      HStack(spacing: OmiSpacing.sm) {
        ProgressView()
        Text("Preparing audio")
          .scaledFont(size: OmiType.body)
          .foregroundStyle(Ink.secondary)
      }
      .accessibilityLabel("Preparing capture audio")
    } else if let resolution = playback.resolution {
      VStack(alignment: .leading, spacing: OmiSpacing.sm) {
        HStack(spacing: OmiSpacing.md) {
          switch resolution {
          case .readyAggregate, .fileFallback:
            Button {
              playback.playOrPause()
            } label: {
              Label(
                playback.isPlaybackRequested ? "Pause" : "Play audio",
                systemImage: playback.isPlaybackRequested ? "pause.fill" : "play.fill"
              )
            }
            .buttonStyle(.bordered)
            .accessibilityLabel(playback.isPlaybackRequested ? "Pause capture audio" : "Play capture audio")
            .accessibilityIdentifier("chat-first-capture-play")
          case .pending, .locked, .unavailable, .noAudio:
            Button("Check audio", action: onRefresh)
              .buttonStyle(.bordered)
              .disabled(capture.isLocked)
              .accessibilityLabel("Check capture audio")
              .accessibilityIdentifier("chat-first-capture-check-audio-\(capture.id)")
          }

          Text(resolution.userFacingMessage)
            .scaledFont(size: OmiType.caption)
            .foregroundStyle(Ink.secondary)
        }

        if playback.duration > 0 {
          HStack(spacing: OmiSpacing.sm) {
            ProgressView(value: min(playback.currentTime, playback.duration), total: playback.duration)
              .accessibilityLabel("Capture playback progress")
            Text("\(Self.playbackTimestamp(playback.currentTime)) / \(Self.playbackTimestamp(playback.duration))")
              .scaledFont(size: OmiType.caption, weight: .medium)
              .foregroundStyle(Ink.secondary)
              .monospacedDigit()
          }
        }

        if playback.isBuffering {
          Label("Buffering audio…", systemImage: "circle.dotted")
            .scaledFont(size: OmiType.caption)
            .foregroundStyle(Ink.secondary)
        } else if playback.isPlaying {
          Label("Playing", systemImage: "speaker.wave.2.fill")
            .scaledFont(size: OmiType.caption)
            .foregroundStyle(Ink.secondary)
        }

        if let playbackError = playback.playbackError {
          HStack(spacing: OmiSpacing.sm) {
            Label(playbackError, systemImage: "exclamationmark.triangle")
              .scaledFont(size: OmiType.caption)
              .foregroundStyle(Ink.errorRed)
            Button("Refresh", action: onRefresh)
              .buttonStyle(.link)
          }
        }
      }
    } else {
      Button("Prepare audio", action: onPrepare)
        .buttonStyle(.bordered)
        .accessibilityLabel("Prepare capture audio")
        .accessibilityIdentifier("chat-first-capture-prepare-audio")
    }
  }

  private static func playbackTimestamp(_ offset: TimeInterval) -> String {
    let totalSeconds = max(0, Int(offset))
    return String(format: "%02d:%02d", totalSeconds / 60, totalSeconds % 60)
  }
}

// Preview helper
extension ServerConversation {
  static var preview: ServerConversation {
    // This would need to be implemented with a proper initializer
    // For now, previews won't work without mock data
    fatalError("Preview not implemented")
  }
}

// MARK: - App Result Card

struct AppResultCard: View {
  let result: AppResponse
  let app: OmiApp?

  @State private var isExpanded = false

  var body: some View {
    VStack(alignment: .leading, spacing: OmiSpacing.sm) {
      // Header
      HStack(spacing: OmiSpacing.sm) {
        if let app = app {
          AsyncImage(url: URL(string: app.image)) { phase in
            switch phase {
            case .success(let image):
              image
                .resizable()
                .aspectRatio(contentMode: .fill)
            default:
              RoundedRectangle(cornerRadius: OmiChrome.elementRadius)
                .fill(Ink.rowFillHover)
            }
          }
          .frame(width: 32, height: 32)
          .clipShape(RoundedRectangle(cornerRadius: OmiChrome.elementRadius))

          VStack(alignment: .leading, spacing: OmiSpacing.hairline) {
            Text(app.name)
              .scaledFont(size: OmiType.body, weight: .medium)
              .foregroundColor(Ink.primary)

            Text(app.author)
              .scaledFont(size: OmiType.caption)
              .foregroundColor(Ink.secondary)
          }
        } else {
          Image(systemName: "app.fill")
            .scaledFont(size: OmiType.subheading)
            .foregroundColor(Ink.secondary)
            .frame(width: 32, height: 32)
            .background(Ink.rowFillHover)
            .clipShape(RoundedRectangle(cornerRadius: OmiChrome.elementRadius))

          Text("App")
            .scaledFont(size: OmiType.body, weight: .medium)
            .foregroundColor(Ink.primary)
        }

        Spacer()

        Button(action: { OmiMotion.withGated { isExpanded.toggle() } }) {
          Image(systemName: isExpanded ? "chevron.up" : "chevron.down")
            .scaledFont(size: OmiType.caption)
            .foregroundColor(Ink.secondary)
        }
        .buttonStyle(.plain)
      }

      // Content
      if isExpanded || result.content.count < 200 {
        OmiMarkdown(text: result.content, sender: .ai)
          .textSelection(.enabled)
          .frame(maxWidth: .infinity, alignment: .leading)
      } else {
        OmiMarkdown(text: String(result.content.prefix(200)) + "\u{2026}", sender: .ai)
          .textSelection(.enabled)
          .frame(maxWidth: .infinity, alignment: .leading)
      }

      // "Generated by" footer
      if let app = app {
        HStack(spacing: OmiSpacing.xs) {
          AsyncImage(url: URL(string: app.image)) { phase in
            switch phase {
            case .success(let image):
              image
                .resizable()
                .aspectRatio(contentMode: .fill)
            default:
              RoundedRectangle(cornerRadius: OmiChrome.stripRadius)
                .fill(Ink.rowFillHover)
            }
          }
          .frame(width: 16, height: 16)
          .clipShape(RoundedRectangle(cornerRadius: OmiChrome.stripRadius))

          Text("Generated by \(app.name)")
            .scaledFont(size: OmiType.caption)
            .foregroundColor(Ink.secondary)
        }
        .padding(.horizontal, OmiSpacing.sm)
        .padding(.vertical, OmiSpacing.xxs)
        .background(
          Capsule()
            .fill(Ink.rowFillHover.opacity(0.6))
        )
      }
    }
    .padding(OmiSpacing.md)
    .background(
      RoundedRectangle(cornerRadius: OmiChrome.smallControlRadius)
        .fill(Ink.rowFill)
    )
  }
}

// MARK: - Suggested App Card

struct SuggestedAppCard: View {
  let app: OmiApp
  let isLoading: Bool
  let onTap: () -> Void

  @State private var isHovering = false

  var body: some View {
    Button(action: onTap) {
      VStack(spacing: OmiSpacing.sm) {
        ZStack {
          AsyncImage(url: URL(string: app.image)) { phase in
            switch phase {
            case .success(let image):
              image
                .resizable()
                .aspectRatio(contentMode: .fill)
            default:
              RoundedRectangle(cornerRadius: OmiChrome.smallControlRadius)
                .fill(Ink.rowFillHover)
            }
          }
          .frame(width: 56, height: 56)
          .clipShape(RoundedRectangle(cornerRadius: OmiChrome.smallControlRadius))

          if isLoading {
            RoundedRectangle(cornerRadius: OmiChrome.smallControlRadius)
              .fill(Color.black.opacity(0.5))
              .frame(width: 56, height: 56)

            ProgressView()
              .scaleEffect(0.7)
              .tint(Ink.surface)
          }
        }

        Text(app.name)
          .scaledFont(size: OmiType.caption, weight: .medium)
          .foregroundColor(Ink.primary)
          .lineLimit(1)
      }
      .frame(width: 80)
      .padding(.vertical, OmiSpacing.sm)
      .padding(.horizontal, OmiSpacing.sm)
      .background(
        RoundedRectangle(cornerRadius: OmiChrome.smallControlRadius)
          .fill(isHovering ? Ink.rowFillHover : Ink.rowFill)
      )
    }
    .buttonStyle(.plain)
    .disabled(isLoading)
    .onHover { isHovering = $0 }
  }

}
