import OmiSupport
import OmiTheme
import SwiftUI

/// Full detail view for a single conversation
struct ConversationDetailView: View {
  let conversation: ServerConversation
  let onBack: () -> Void
  var folders: [Folder] = []
  var onMoveToFolder: ((String, String?) async -> Void)?
  var onDelete: (() -> Void)?
  var onTitleUpdated: ((String) -> Void)?

  // People (speaker naming)
  var people: [Person] = []
  var onFetchPeople: (() async -> Void)?
  var onCreatePerson: ((String) async -> Person?)?
  var onAssignSpeaker: ((String, [String], String?, Bool) async -> Bool)?

  @StateObject private var appProvider = AppProvider()
  @State private var showAppSelector = false
  @State private var isReprocessing = false
  @State private var selectedAppForReprocess: OmiApp?

  // Transcript drawer state (replaces tab system)
  @State private var showTranscriptDrawer = false
  // When expanded, the transcript drawer fills the window (the summary pane
  // collapses) for full-width reading; collapsed it's the fixed side drawer.
  @State private var isTranscriptExpanded = false

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
  @State private var isCopyingLink = false
  @State private var isDeleting = false

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

  var body: some View {
    HStack(spacing: 0) {
      // Main content (always visible)
      VStack(alignment: .leading, spacing: 0) {
        headerView

        ScrollView {
          // Card container wrapping summary content
          VStack(alignment: .leading, spacing: 0) {
            // Card header bar
            HStack(spacing: OmiSpacing.sm) {
              Image(systemName: "doc.text")
                .scaledFont(size: OmiType.caption)
                .foregroundColor(OmiColors.textTertiary)
              Text("Conversation Details")
                .scaledFont(size: OmiType.body, weight: .medium)
                .foregroundColor(OmiColors.textSecondary)
              Spacer()
            }
            .padding(.horizontal, OmiSpacing.lg)
            .padding(.vertical, OmiSpacing.sm)
            .background(OmiColors.backgroundTertiary.opacity(0.4))

            VStack(alignment: .leading, spacing: OmiSpacing.xxl) {
              summaryContent
            }
            .padding(OmiSpacing.xxl)
          }
          .background(
            RoundedRectangle(cornerRadius: OmiChrome.controlRadius)
              .fill(OmiColors.backgroundSecondary.opacity(0.6))
          )
          .clipShape(RoundedRectangle(cornerRadius: OmiChrome.controlRadius))
          .overlay(
            RoundedRectangle(cornerRadius: OmiChrome.controlRadius)
              .stroke(OmiColors.backgroundTertiary.opacity(0.3), lineWidth: 1)
          )
          .shadow(color: Color.black.opacity(0.1), radius: 20, x: 0, y: 8)
          .padding(OmiSpacing.xxl)
        }
      }
      // Collapses to zero width when the transcript is expanded so the drawer
      // can fill the window; otherwise it's the greedy main pane.
      .frame(maxWidth: isTranscriptExpanded ? 0 : .infinity)
      .opacity(isTranscriptExpanded ? 0 : 1)
      .clipped()

      // Transcript drawer (slides in from right; expands to fill on demand)
      if showTranscriptDrawer {
        if !isTranscriptExpanded {
          Rectangle()
            .fill(OmiColors.border)
            .frame(width: 1)
        }

        transcriptDrawerView
          .frame(maxWidth: isTranscriptExpanded ? .infinity : 450)
          .transition(.move(edge: .trailing))
      }
    }
    .opacity(hasAppeared ? 1 : 0)
    .offset(y: hasAppeared ? 0 : 20)
    .onAppear {
      ConversationDetailAutomationState.shared.setOpen(
        conversationId: conversation.id,
        transcriptDrawerOpen: showTranscriptDrawer
      )
      OmiMotion.withGated(.easeOut(duration: 0.5)) {
        hasAppeared = true
      }
    }
    .onDisappear {
      ConversationDetailAutomationState.shared.clear(conversationId: conversation.id)
    }
    .onChange(of: showTranscriptDrawer) { _, newValue in
      ConversationDetailAutomationState.shared.setTranscriptDrawerOpen(
        newValue, conversationId: conversation.id)
    }
    .task {
      await appProvider.fetchApps()
      await onFetchPeople?()
      AnalyticsManager.shared.conversationDetailOpened(conversationId: conversation.id)

      // All detail reads go through the repository. It can paint a complete
      // cached detail immediately, but always revalidates server-owned fields.
      if conversation.deferred || conversation.status == .processing {
        isEnrichingDeferred = true
        var attempts = 0
        while attempts < 15 {
          guard let appState = AppState.current else { break }
          let fetched = await appState.loadConversationDetail(conversation) { cached in
            loadedConversation = cached
          }
          loadedConversation = fetched
          if fetched.status != .processing { break }
          attempts += 1
          try? await Task.sleep(nanoseconds: 2_000_000_000)
        }
        isEnrichingDeferred = false
        return
      }

      isLoadingConversation = true
      if let appState = AppState.current {
        loadedConversation = await appState.loadConversationDetail(conversation) { cached in
          loadedConversation = cached
        }
      }
      isLoadingConversation = false
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
        onSelect: { app in
          selectedAppForReprocess = app
          Task {
            await reprocessWithApp(app)
          }
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
          Task {
            let assignment = Self.assignmentMetadata(
              for: segmentIndices,
              in: displayConversation.transcriptSegments
            )
            let success =
              await onAssignSpeaker?(
                conversation.id,
                assignment.targets,
                personId,
                isUser
              ) ?? false
            if success {
              await persistSpeakerAssignment(
                conversationId: conversation.id,
                backendSegmentIds: assignment.backendIds,
                fallbackSegmentOrders: assignment.fallbackOrders,
                isUser: isUser,
                personId: personId
              )
              updateDisplayedConversation(segmentIndices: segmentIndices, isUser: isUser, personId: personId)
            }
            selectedSegmentForNaming = nil
          }
        },
        onCreatePerson: { name in
          await onCreatePerson?(name)
        },
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
      Button(action: onBack) {
        HStack(spacing: OmiSpacing.xs) {
          Image(systemName: "chevron.left")
            .scaledFont(size: OmiType.body, weight: .medium)
          Text("Back")
            .scaledFont(size: OmiType.body, weight: .medium)
        }
        .foregroundColor(OmiColors.accent)
      }
      .buttonStyle(.plain)

      // Emoji
      Text(displayConversation.structured.emoji.isEmpty ? "\u{1F4AC}" : displayConversation.structured.emoji)
        .scaledFont(size: OmiType.title)

      // Title + timestamp subtitle
      VStack(alignment: .leading, spacing: OmiSpacing.hairline) {
        HStack(spacing: OmiSpacing.sm) {
          Text(displayConversation.title)
            .scaledFont(size: OmiType.heading, weight: .semibold)
            .foregroundColor(OmiColors.textPrimary)
            .lineLimit(1)

          // Edit title button (inline with title)
          Button(action: {
            editedTitle = displayConversation.title
            showEditDialog = true
          }) {
            Image(systemName: "pencil")
              .scaledFont(size: OmiType.body)
              .foregroundColor(OmiColors.textTertiary)
          }
          .buttonStyle(.plain)
          .help("Edit title")
        }

        Text(formattedTimeRange)
          .scaledFont(size: OmiType.caption)
          .foregroundColor(OmiColors.textTertiary)
      }

      Spacer()

      // Status badge
      if displayConversation.status != .completed {
        statusBadge
      }

      // View Transcript pill button
      viewTranscriptButton

      // Inline action buttons
      inlineActionButtons
    }
    .padding(.horizontal, OmiSpacing.xxl)
    .padding(.vertical, OmiSpacing.lg)
    .background(OmiColors.backgroundTertiary.opacity(0.5))
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

  // MARK: - View Transcript Button

  private var viewTranscriptButton: some View {
    Button(action: {
      OmiMotion.withGated(.easeInOut(duration: 0.25)) {
        showTranscriptDrawer.toggle()
      }
    }) {
      HStack(spacing: OmiSpacing.xs) {
        Image(systemName: "text.quote")
          .scaledFont(size: OmiType.caption)
        Text(showTranscriptDrawer ? "Hide Transcript" : "View Transcript")
          .scaledFont(size: OmiType.caption, weight: .medium)
      }
      .foregroundColor(showTranscriptDrawer ? OmiColors.backgroundPrimary : OmiColors.textSecondary)
      .padding(.horizontal, OmiSpacing.md)
      .padding(.vertical, OmiSpacing.xs)
      .background(
        Capsule()
          .fill(showTranscriptDrawer ? OmiColors.accent : OmiColors.backgroundTertiary)
      )
    }
    .buttonStyle(.plain)
  }

  // MARK: - Inline Action Buttons

  private var inlineActionButtons: some View {
    HStack(spacing: OmiSpacing.sm) {
      // Copy link button
      Button(action: { Task { await copyLink() } }) {
        Image(systemName: isCopyingLink ? "arrow.triangle.2.circlepath" : "link")
          .scaledFont(size: OmiType.body)
          .foregroundColor(OmiColors.textSecondary)
          .frame(width: 28, height: 28)
          .background(
            Circle()
              .fill(OmiColors.backgroundTertiary)
          )
      }
      .buttonStyle(.plain)
      .disabled(isCopyingLink)
      .help("Copy link")

      // Copy transcript button
      Button(action: copyTranscript) {
        Image(systemName: "doc.on.doc")
          .scaledFont(size: OmiType.body)
          .foregroundColor(OmiColors.textSecondary)
          .frame(width: 28, height: 28)
          .background(
            Circle()
              .fill(OmiColors.backgroundTertiary)
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
            .foregroundColor(displayConversation.folderId != nil ? OmiColors.accent : OmiColors.textSecondary)
            .frame(width: 28, height: 28)
            .background(
              Circle()
                .fill(OmiColors.backgroundTertiary)
            )
        }
        .menuStyle(.borderlessButton)
        .frame(width: 28)
        .help("Move to folder")
      }

      // Delete button
      Button(action: { showDeleteConfirmation = true }) {
        Image(systemName: "trash")
          .scaledFont(size: OmiType.body)
          .foregroundColor(OmiColors.error)
          .frame(width: 28, height: 28)
          .background(
            Circle()
              .fill(OmiColors.backgroundTertiary)
          )
      }
      .buttonStyle(.plain)
      .help("Delete conversation")
    }
  }

  private var canCopyTranscript: Bool {
    displayConversation.transcriptPresenceState != .lockedOrRedacted
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

  private func copyLink() async {
    isCopyingLink = true
    defer { isCopyingLink = false }

    do {
      let shareableUrl = try await APIClient.shared.getConversationShareLink(id: conversation.id)
      await MainActor.run {
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(shareableUrl, forType: .string)
      }
      AnalyticsManager.shared.shareAction(category: "conversation", properties: ["conversation_id": conversation.id])
    } catch {
      logError("Failed to get share link", error: error)
    }
  }

  private func updateTitle() async {
    guard !editedTitle.isEmpty else { return }
    isUpdatingTitle = true
    defer { isUpdatingTitle = false }

    await AppState.current?.updateConversationTitle(conversation.id, title: editedTitle)
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

  private var statusBadge: some View {
    Text(displayConversation.status.rawValue.replacingOccurrences(of: "_", with: " ").capitalized)
      .scaledFont(size: OmiType.caption, weight: .medium)
      .foregroundColor(statusColor)
      .padding(.horizontal, OmiSpacing.sm)
      .padding(.vertical, OmiSpacing.xxs)
      .background(
        Capsule()
          .fill(statusColor.opacity(0.2))
      )
  }

  private var statusColor: Color {
    switch displayConversation.status {
    case .completed:
      return OmiColors.success
    case .processing, .merging:
      return OmiColors.info
    case .inProgress:
      return OmiColors.warning
    case .failed:
      return OmiColors.error
    }
  }

  // MARK: - Summary Content (always visible, no tabs)

  @ViewBuilder
  private var summaryContent: some View {
    // Lazy processing: while the deferred conversation is being enriched (polled) on first
    // open, show a loader where the summary will appear. Cleared when enrichment completes or
    // the poll times out, so it never spins forever.
    if isEnrichingDeferred {
      deferredProcessingSection
    }

    // Overview section
    if !displayConversation.overview.isEmpty {
      overviewSection
    }

    // Metadata chips
    metadataSection

    // App Results section
    if !displayConversation.appsResults.isEmpty {
      appResultsSection
    }

    // Suggested apps section
    suggestedAppsSection

    // Action items section
    if !displayConversation.structured.actionItems.isEmpty {
      actionItemsSection
    }
  }

  // MARK: - Transcript Drawer

  @ViewBuilder
  private var transcriptDrawerView: some View {
    VStack(alignment: .leading, spacing: 0) {
      // Drawer header
      HStack(spacing: OmiSpacing.sm) {
        Image(systemName: "text.quote")
          .scaledFont(size: OmiType.body)
          .foregroundColor(OmiColors.textSecondary)

        Text("Transcript")
          .scaledFont(size: OmiType.subheading, weight: .semibold)
          .foregroundColor(OmiColors.textPrimary)

        // Segment count badge
        Text("\(displayConversation.transcriptSegments.count)")
          .scaledFont(size: OmiType.caption, weight: .medium)
          .foregroundColor(OmiColors.accent)
          .padding(.horizontal, OmiSpacing.sm)
          .padding(.vertical, OmiSpacing.hairline)
          .background(
            Capsule()
              .fill(OmiColors.accent.opacity(0.15))
          )

        Spacer()

        // Expand / collapse the drawer to fill the window for full-width reading
        Button(action: {
          OmiMotion.withGated(.easeInOut(duration: 0.25)) {
            isTranscriptExpanded.toggle()
          }
        }) {
          Image(
            systemName: isTranscriptExpanded
              ? "arrow.down.right.and.arrow.up.left" : "arrow.up.left.and.arrow.down.right"
          )
          .scaledFont(size: OmiType.body)
          .foregroundColor(OmiColors.textSecondary)
          .frame(width: 28, height: 28)
          .background(Circle().fill(OmiColors.backgroundTertiary))
        }
        .buttonStyle(.plain)
        .help(isTranscriptExpanded ? "Collapse transcript" : "Expand transcript")

        // Copy button
        Button(action: copyTranscript) {
          Image(systemName: "doc.on.doc")
            .scaledFont(size: OmiType.body)
            .foregroundColor(OmiColors.textSecondary)
            .frame(width: 28, height: 28)
            .background(
              Circle()
                .fill(OmiColors.backgroundTertiary)
            )
        }
        .buttonStyle(.plain)
        .help("Copy transcript")

        // Close button
        Button(action: {
          OmiMotion.withGated(.easeInOut(duration: 0.25)) {
            showTranscriptDrawer = false
            isTranscriptExpanded = false
          }
        }) {
          Image(systemName: "xmark")
            .scaledFont(size: OmiType.body)
            .foregroundColor(OmiColors.textSecondary)
            .frame(width: 28, height: 28)
            .background(
              Circle()
                .fill(OmiColors.backgroundTertiary)
            )
        }
        .buttonStyle(.plain)
        .help("Close transcript")
      }
      .padding(.horizontal, OmiSpacing.xl)
      .padding(.vertical, OmiSpacing.md)
      .background(OmiColors.backgroundTertiary.opacity(0.5))

      // Drawer content
      if displayConversation.transcriptPresenceState == .lockedOrRedacted && !isLoadingConversation {
        VStack(spacing: OmiSpacing.md) {
          Image(systemName: "lock")
            .scaledFont(size: OmiType.hero)
            .foregroundColor(OmiColors.textTertiary.opacity(0.5))

          Text("Transcript locked")
            .scaledFont(size: OmiType.body)
            .foregroundColor(OmiColors.textTertiary)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
      } else if displayConversation.transcriptSegments.isEmpty && !isLoadingConversation {
        // Empty state
        VStack(spacing: OmiSpacing.md) {
          Image(systemName: "text.quote")
            .scaledFont(size: OmiType.hero)
            .foregroundColor(OmiColors.textTertiary.opacity(0.5))

          Text("No transcript available")
            .scaledFont(size: OmiType.body)
            .foregroundColor(OmiColors.textTertiary)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
      } else if isLoadingConversation {
        // Loading state
        VStack(spacing: OmiSpacing.md) {
          ProgressView()
            .scaleEffect(0.8)

          Text("Loading transcript...")
            .scaledFont(size: OmiType.body)
            .foregroundColor(OmiColors.textTertiary)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
      } else {
        // LazyVStack is a DIRECT child of ScrollView so it gets bounded proposed height
        // and only materializes visible children.
        ScrollView {
          LazyVStack(alignment: .leading, spacing: OmiSpacing.md) {
            transcriptBubblesContent
          }
          .padding(OmiSpacing.lg)
        }
      }
    }
    .background(OmiColors.backgroundPrimary)
  }

  // MARK: - Transcript Bubbles (shared)

  /// Flat content intended to be placed inside a parent LazyVStack.
  /// Do NOT wrap this in another LazyVStack or VStack — it emits ForEach items directly.
  @ViewBuilder
  private var transcriptBubblesContent: some View {
    let peopleDict = Dictionary(lastWriteWins: people.map { ($0.id, $0) })
    ForEach(displayConversation.transcriptSegments) { segment in
      SpeakerBubbleView(
        segment: segment,
        isUser: segment.isUser,
        personName: segment.personId.flatMap { peopleDict[$0]?.name },
        onSpeakerTapped: segment.isUser
          ? nil
          : {
            selectedSegmentForNaming = segment
          }
      )
      .padding(.horizontal, OmiSpacing.lg)
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

  private func persistSpeakerAssignment(
    conversationId: String,
    backendSegmentIds: [String],
    fallbackSegmentOrders: [Int],
    isUser: Bool,
    personId: String?
  ) async {
    do {
      try await TranscriptionStorage.shared.updateSpeakerAssignmentByBackendId(
        conversationId,
        segmentIds: backendSegmentIds,
        fallbackSegmentOrders: fallbackSegmentOrders,
        isUser: isUser,
        personId: isUser ? nil : personId
      )
    } catch {
      logError("ConversationDetail: Failed to persist speaker assignment locally", error: error)
    }
  }

  // MARK: - Deferred Processing Loader

  /// Shown while a lazily-deferred conversation is being enriched on first open.
  private var deferredProcessingSection: some View {
    HStack(spacing: OmiSpacing.md) {
      ProgressView()
        .controlSize(.small)
      VStack(alignment: .leading, spacing: OmiSpacing.hairline) {
        Text("Processing conversation…")
          .scaledFont(size: OmiType.body, weight: .semibold)
          .foregroundColor(OmiColors.textPrimary)
        Text("Generating summary and action items")
          .scaledFont(size: OmiType.caption)
          .foregroundColor(OmiColors.textSecondary)
      }
      Spacer()
    }
    .padding(OmiSpacing.lg)
    .frame(maxWidth: .infinity, alignment: .leading)
    .background(OmiColors.backgroundTertiary.opacity(0.5))
    .cornerRadius(OmiChrome.smallControlRadius)
  }

  // MARK: - Overview Section

  private var overviewSection: some View {
    VStack(alignment: .leading, spacing: OmiSpacing.sm) {
      HStack(spacing: OmiSpacing.xs) {
        Image(systemName: "star.fill")
          .scaledFont(size: OmiType.body)
          .foregroundColor(Color(red: 0.95, green: 0.75, blue: 0.15))

        Text("Summary")
          .scaledFont(size: OmiType.body, weight: .semibold)
          .foregroundColor(OmiColors.textSecondary)
      }

      SelectableMarkdown(text: displayConversation.overview, sender: .ai)
        .textSelection(.enabled)
        .environment(\.colorScheme, .dark)
        .frame(maxWidth: .infinity, alignment: .leading)
    }
  }

  // MARK: - Metadata Section

  private var metadataSection: some View {
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
        .foregroundColor(OmiColors.textTertiary)

      Text(text)
        .scaledFont(size: OmiType.caption)
        .foregroundColor(OmiColors.textSecondary)
    }
    .padding(.horizontal, OmiSpacing.sm)
    .padding(.vertical, OmiSpacing.xs)
    .background(
      Capsule()
        .fill(OmiColors.backgroundTertiary)
    )
  }

  // MARK: - App Results Section

  private var appResultsSection: some View {
    VStack(alignment: .leading, spacing: OmiSpacing.md) {
      HStack {
        Text("App Insights")
          .scaledFont(size: OmiType.body, weight: .semibold)
          .foregroundColor(OmiColors.textSecondary)

        Spacer()

        Button(action: { showAppSelector = true }) {
          HStack(spacing: OmiSpacing.xxs) {
            Image(systemName: "arrow.triangle.2.circlepath")
              .scaledFont(size: OmiType.caption)
            Text("Reprocess")
              .scaledFont(size: OmiType.caption)
          }
          .foregroundColor(OmiColors.accent)
        }
        .buttonStyle(.plain)
        .disabled(isReprocessing)
      }

      ForEach(displayConversation.appsResults) { result in
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
          .foregroundColor(OmiColors.textSecondary)

        Spacer()
      }

      let memoryApps = appProvider.apps.filter { app in
        // Name the outer element: inside the inner closure a bare `$0`
        // shadows it, so `$0.appId == $0.id` compared an appsResults entry
        // to itself (always true for any entry with a non-nil app_id, since
        // AppResponse.id == appId ?? uuid), which excluded every app and
        // left this section perpetually empty.
        app.capabilities.contains("memories")
          && !displayConversation.appsResults.contains(where: { $0.appId == app.id })
      }.prefix(4)

      if memoryApps.isEmpty && !appProvider.isLoading {
        Text("Enable apps with memory capability to get additional insights")
          .scaledFont(size: OmiType.body)
          .foregroundColor(OmiColors.textTertiary)
          .padding()
          .frame(maxWidth: .infinity)
          .background(
            RoundedRectangle(cornerRadius: OmiChrome.elementRadius)
              .fill(OmiColors.backgroundSecondary)
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
    isReprocessing = true
    defer {
      isReprocessing = false
      selectedAppForReprocess = nil
      showAppSelector = false
    }

    // Track reprocess
    AnalyticsManager.shared.conversationReprocessed(conversationId: conversation.id, appId: app.id)

    do {
      try await APIClient.shared.reprocessConversation(
        conversationId: conversation.id,
        appId: app.id
      )
    } catch {
      logError("Failed to reprocess conversation", error: error)
    }
  }

  // MARK: - Action Items Section

  private var actionItemsSection: some View {
    let activeItems = displayConversation.structured.actionItems.filter { !$0.deleted }
    return VStack(alignment: .leading, spacing: OmiSpacing.md) {
      HStack(spacing: OmiSpacing.sm) {
        Image(systemName: "checklist")
          .scaledFont(size: OmiType.body)
          .foregroundColor(OmiColors.textSecondary)

        Text("Action Items")
          .scaledFont(size: OmiType.subheading, weight: .semibold)
          .foregroundColor(OmiColors.textSecondary)

        // Count badge
        Text("\(activeItems.count)")
          .scaledFont(size: OmiType.caption, weight: .medium)
          .foregroundColor(OmiColors.accent)
          .padding(.horizontal, OmiSpacing.sm)
          .padding(.vertical, OmiSpacing.hairline)
          .background(
            Capsule()
              .fill(OmiColors.accent.opacity(0.15))
          )

        Spacer()
      }

      VStack(alignment: .leading, spacing: OmiSpacing.sm) {
        ForEach(activeItems) { item in
          HStack(alignment: .top, spacing: OmiSpacing.sm) {
            Image(systemName: item.completed ? "checkmark.circle.fill" : "circle")
              .scaledFont(size: OmiType.subheading)
              .foregroundColor(item.completed ? OmiColors.success : OmiColors.textTertiary)

            Text(item.description)
              .scaledFont(size: OmiType.body)
              .foregroundColor(item.completed ? OmiColors.textTertiary : OmiColors.textPrimary)
              .textSelection(.enabled)
              .strikethrough(item.completed, color: OmiColors.textTertiary)
          }
          .padding(OmiSpacing.md)
          .frame(maxWidth: .infinity, alignment: .leading)
          .background(
            RoundedRectangle(cornerRadius: OmiChrome.smallControlRadius)
              .fill(OmiColors.backgroundTertiary)
          )
          .overlay(
            RoundedRectangle(cornerRadius: OmiChrome.smallControlRadius)
              .stroke(OmiColors.backgroundTertiary.opacity(0.3), lineWidth: 1)
          )
        }
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
    .background(OmiColors.backgroundPrimary)
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
                .fill(OmiColors.backgroundTertiary)
            }
          }
          .frame(width: 32, height: 32)
          .clipShape(RoundedRectangle(cornerRadius: OmiChrome.elementRadius))

          VStack(alignment: .leading, spacing: OmiSpacing.hairline) {
            Text(app.name)
              .scaledFont(size: OmiType.body, weight: .medium)
              .foregroundColor(OmiColors.textPrimary)

            Text(app.author)
              .scaledFont(size: OmiType.caption)
              .foregroundColor(OmiColors.textTertiary)
          }
        } else {
          Image(systemName: "app.fill")
            .scaledFont(size: OmiType.subheading)
            .foregroundColor(OmiColors.textTertiary)
            .frame(width: 32, height: 32)
            .background(OmiColors.backgroundTertiary)
            .clipShape(RoundedRectangle(cornerRadius: OmiChrome.elementRadius))

          Text("App")
            .scaledFont(size: OmiType.body, weight: .medium)
            .foregroundColor(OmiColors.textPrimary)
        }

        Spacer()

        Button(action: { OmiMotion.withGated { isExpanded.toggle() } }) {
          Image(systemName: isExpanded ? "chevron.up" : "chevron.down")
            .scaledFont(size: OmiType.caption)
            .foregroundColor(OmiColors.textTertiary)
        }
        .buttonStyle(.plain)
      }

      // Content
      if isExpanded || result.content.count < 200 {
        Text(result.content)
          .scaledFont(size: OmiType.body)
          .foregroundColor(OmiColors.textSecondary)
          .textSelection(.enabled)
          .lineSpacing(4)
      } else {
        Text(result.content.prefix(200) + "...")
          .scaledFont(size: OmiType.body)
          .foregroundColor(OmiColors.textSecondary)
          .textSelection(.enabled)
          .lineSpacing(4)
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
                .fill(OmiColors.backgroundTertiary)
            }
          }
          .frame(width: 16, height: 16)
          .clipShape(RoundedRectangle(cornerRadius: OmiChrome.stripRadius))

          Text("Generated by \(app.name)")
            .scaledFont(size: OmiType.caption)
            .foregroundColor(OmiColors.textTertiary)
        }
        .padding(.horizontal, OmiSpacing.sm)
        .padding(.vertical, OmiSpacing.xxs)
        .background(
          Capsule()
            .fill(OmiColors.backgroundTertiary.opacity(0.6))
        )
      }
    }
    .padding(OmiSpacing.md)
    .background(
      RoundedRectangle(cornerRadius: OmiChrome.smallControlRadius)
        .fill(OmiColors.backgroundSecondary)
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
                .fill(OmiColors.backgroundTertiary)
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
              .tint(.white)
          }
        }

        Text(app.name)
          .scaledFont(size: OmiType.caption, weight: .medium)
          .foregroundColor(OmiColors.textPrimary)
          .lineLimit(1)
      }
      .frame(width: 80)
      .padding(.vertical, OmiSpacing.sm)
      .padding(.horizontal, OmiSpacing.sm)
      .background(
        RoundedRectangle(cornerRadius: OmiChrome.smallControlRadius)
          .fill(isHovering ? OmiColors.backgroundTertiary : OmiColors.backgroundSecondary)
      )
    }
    .buttonStyle(.plain)
    .disabled(isLoading)
    .onHover { isHovering = $0 }
  }
}

// MARK: - App Selector Sheet

struct AppSelectorSheet: View {
  let apps: [OmiApp]
  let isLoading: Bool
  let onSelect: (OmiApp) -> Void
  let onDismiss: () -> Void

  @State private var selectedAppId: String?

  var body: some View {
    VStack(spacing: 0) {
      // Header
      HStack {
        Text("Select App")
          .scaledFont(size: OmiType.subheading, weight: .semibold)
          .foregroundColor(OmiColors.textPrimary)

        Spacer()

        Button(action: onDismiss) {
          Image(systemName: "xmark.circle.fill")
            .scaledFont(size: OmiType.heading)
            .foregroundColor(OmiColors.textTertiary)
        }
        .buttonStyle(.plain)
      }
      .padding()

      Divider()
        .background(OmiColors.backgroundTertiary)

      // Apps list
      if apps.isEmpty {
        VStack(spacing: OmiSpacing.md) {
          Image(systemName: "square.grid.2x2")
            .scaledFont(size: OmiType.hero)
            .foregroundColor(OmiColors.textTertiary)

          Text("No Apps Available")
            .scaledFont(size: OmiType.body, weight: .medium)
            .foregroundColor(OmiColors.textSecondary)

          Text("Enable apps with memory capability to reprocess conversations")
            .scaledFont(size: OmiType.caption)
            .foregroundColor(OmiColors.textTertiary)
            .multilineTextAlignment(.center)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .padding()
      } else {
        ScrollView {
          LazyVStack(spacing: OmiSpacing.hairline) {
            ForEach(apps) { app in
              AppSelectorRow(
                app: app,
                isSelected: selectedAppId == app.id,
                isLoading: isLoading && selectedAppId == app.id
              ) {
                selectedAppId = app.id
                onSelect(app)
              }
            }
          }
          .padding(.horizontal, OmiSpacing.sm)
          .padding(.vertical, OmiSpacing.sm)
        }
      }
    }
    .frame(width: 320, height: 400)
    .background(OmiColors.backgroundPrimary)
  }
}

struct AppSelectorRow: View {
  let app: OmiApp
  let isSelected: Bool
  let isLoading: Bool
  let onSelect: () -> Void

  @State private var isHovering = false

  var body: some View {
    Button(action: onSelect) {
      HStack(spacing: OmiSpacing.md) {
        AsyncImage(url: URL(string: app.image)) { phase in
          switch phase {
          case .success(let image):
            image
              .resizable()
              .aspectRatio(contentMode: .fill)
          default:
            RoundedRectangle(cornerRadius: OmiChrome.smallControlRadius)
              .fill(OmiColors.backgroundTertiary)
          }
        }
        .frame(width: 44, height: 44)
        .clipShape(RoundedRectangle(cornerRadius: OmiChrome.smallControlRadius))

        VStack(alignment: .leading, spacing: OmiSpacing.hairline) {
          Text(app.name)
            .scaledFont(size: OmiType.body, weight: .medium)
            .foregroundColor(OmiColors.textPrimary)

          Text(app.author)
            .scaledFont(size: OmiType.caption)
            .foregroundColor(OmiColors.textTertiary)
        }

        Spacer()

        if isLoading {
          ProgressView()
            .scaleEffect(0.7)
        } else if isSelected {
          Image(systemName: "checkmark.circle.fill")
            .scaledFont(size: OmiType.heading)
            .foregroundColor(OmiColors.accent)
        }
      }
      .padding(.horizontal, OmiSpacing.md)
      .padding(.vertical, OmiSpacing.sm)
      .background(
        RoundedRectangle(cornerRadius: OmiChrome.smallControlRadius)
          .fill(isSelected || isHovering ? OmiColors.backgroundTertiary : Color.clear)
      )
    }
    .buttonStyle(.plain)
    .disabled(isLoading)
    .onHover { isHovering = $0 }
  }
}
