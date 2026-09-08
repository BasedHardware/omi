import AppKit
import OmiTheme
import SwiftUI

/// Row view for a conversation in the list
struct ConversationRowView: View {
  let conversation: ServerConversation
  let onTap: () -> Void
  let folders: [Folder]
  let onMoveToFolder: (String, String?) async -> Void

  // View mode
  var isCompactView: Bool = true

  // Multi-select support
  var isMultiSelectMode: Bool = false
  var isSelected: Bool = false
  var onToggleSelection: (() -> Void)? = nil

  var appState: AppState
  @State private var isStarring = false
  @State private var isHovering = false

  // Context menu action states
  @State private var showEditDialog = false
  @State private var showDeleteConfirmation = false
  @State private var editedTitle: String = ""
  @State private var isDeleting = false
  @State private var isUpdatingTitle = false
  @State private var isCopyingLink = false
  @State private var isReprocessing = false

  /// The timestamp to display (prefer startedAt, fall back to createdAt)
  private var displayDate: Date {
    conversation.startedAt ?? conversation.createdAt
  }

  /// Check if conversation was created less than 1 minute ago (newly added)
  private var isNewlyCreated: Bool {
    Date().timeIntervalSince(conversation.createdAt) < 60
  }

  private static let timeFormatter: DateFormatter = {
    let f = DateFormatter()
    f.dateFormat = "h:mm a"
    return f
  }()
  private static let yesterdayFormatter: DateFormatter = {
    let f = DateFormatter()
    f.dateFormat = "'Yesterday,' h:mm a"
    return f
  }()
  private static let sameYearFormatter: DateFormatter = {
    let f = DateFormatter()
    f.dateFormat = "MMM d, h:mm a"
    return f
  }()
  private static let otherYearFormatter: DateFormatter = {
    let f = DateFormatter()
    f.dateFormat = "MMM d, yyyy, h:mm a"
    return f
  }()

  /// Format timestamp (e.g., "10:43 AM" for today, "Jan 29, 10:43 AM" for other days)
  private var formattedTimestamp: String {
    let calendar = Calendar.current
    let formatter: DateFormatter

    if calendar.isDateInToday(displayDate) {
      formatter = Self.timeFormatter
    } else if calendar.isDateInYesterday(displayDate) {
      formatter = Self.yesterdayFormatter
    } else if calendar.isDate(displayDate, equalTo: Date(), toGranularity: .year) {
      formatter = Self.sameYearFormatter
    } else {
      formatter = Self.otherYearFormatter
    }

    return formatter.string(from: displayDate)
  }

  /// Folder name for inline display
  private var folderName: String? {
    guard let folderId = conversation.folderId else { return nil }
    return folders.first(where: { $0.id == folderId })?.name
  }

  /// Title color — dim placeholders (Locked / Untitled / clock-only
  /// provisional titles) so they read as secondary text. A provisional title
  /// quoted from the transcript is real content and reads as primary.
  private var titleColor: Color {
    switch conversation.displayState {
    case .titled: return Ink.primary
    case .processing, .awaitingFirstOpen:
      return conversation.hasTranscriptProvisionalTitle ? Ink.primary : Ink.secondary
    default: return Ink.secondary
    }
  }

  /// A live pipeline row re-evaluates its phase on a slow clock; every other
  /// row is static and must not pay for a timeline.
  private var isLivePipelineRow: Bool {
    conversation.displayState == .processing
  }

  private var isSettlingDerived: Bool {
    conversation.status == .completed && appState.processingWatcher.isSettlingDerived(conversation.id)
  }

  private func processingPhase(now: Date) -> ConversationProcessingPhase {
    ConversationProcessingProgress.phase(for: conversation, now: now)
  }

  /// Emoji tile, or a waveform while the conversation has no emoji of its
  /// own. A fallback 💬 would claim an identity the pipeline has not produced.
  @ViewBuilder
  private func leadingTile(size: CGFloat, fontSize: CGFloat, cornerRadius: CGFloat) -> some View {
    let tile = RoundedRectangle(cornerRadius: cornerRadius, style: .continuous).fill(Ink.rowFill)
    if conversation.structured.emoji.isEmpty {
      Image(systemName: "waveform")
        .scaledFont(size: fontSize * 0.8, weight: .medium)
        .foregroundColor(Ink.secondary)
        .frame(width: size, height: size)
        .background(tile)
    } else {
      Text(conversation.structured.emoji)
        .scaledFont(size: fontSize)
        .frame(width: size, height: size)
        .background(tile)
    }
  }

  /// Status pill plus, once stalled, the way out — inline, not hidden behind
  /// a hover menu.
  @ViewBuilder
  private func statusCluster(phase: ConversationProcessingPhase) -> some View {
    ConversationStatusBadge(state: conversation.displayState, phase: phase)
    if isLivePipelineRow && phase == .stalled {
      Button {
        Task { await reprocessConversation() }
      } label: {
        HStack(spacing: 4) {
          Image(systemName: isReprocessing ? "arrow.triangle.2.circlepath" : "wand.and.stars")
            .scaledFont(size: 9, weight: .semibold)
          Text(isReprocessing ? "Reprocessing…" : "Reprocess")
            .scaledFont(size: 10, weight: .semibold)
        }
        .foregroundColor(Ink.primary)
        .padding(.horizontal, 7)
        .padding(.vertical, 3)
        .background(Capsule(style: .continuous).fill(Ink.rowFillHover))
      }
      .buttonStyle(.plain)
      .disabled(isReprocessing)
      .help("Run the title and summary again")
      .accessibilityIdentifier("conversation-row-reprocess-\(conversation.id)")
    }
  }

  /// Second line: time · duration, plus the second wave of processing when
  /// the title has landed but memories and tasks are still being added.
  private var metadataLine: some View {
    HStack(spacing: OmiSpacing.xs) {
      Text(formattedTimestamp)
        .scaledFont(size: OmiType.caption)
        .foregroundColor(Ink.secondary)

      Text("·")
        .scaledFont(size: OmiType.caption)
        .foregroundColor(Ink.secondary)

      Text(conversation.formattedDuration)
        .scaledFont(size: OmiType.caption)
        .foregroundColor(Ink.secondary)

      if isSettlingDerived {
        Text("·")
          .scaledFont(size: OmiType.caption)
          .foregroundColor(Ink.secondary)
        Text("Adding memories & tasks…")
          .scaledFont(size: OmiType.caption)
          .foregroundColor(Ink.secondary)
          .transition(.opacity)
      }
    }
  }

  /// Whether the actions menu should offer Reprocess. `canReprocess` covers
  /// failed/untitled rows; a stalled pipeline is the third case.
  private func offersReprocess(now: Date) -> Bool {
    conversation.canReprocess || (isLivePipelineRow && processingPhase(now: now) == .stalled)
  }

  /// Label for the conversation source
  private var sourceLabel: String {
    switch conversation.source {
    case .desktop: return "Desktop"
    case .omi: return "omi"
    case .phone: return "Phone"
    case .appleWatch: return "Watch"
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

  private func toggleStar() async {
    guard !isStarring else { return }
    isStarring = true
    let newStarred = !conversation.starred

    await appState.setConversationStarred(conversation.id, starred: newStarred)

    isStarring = false
  }

  // MARK: - Context Menu Actions

  private func copyTranscript() {
    let pasteboard = NSPasteboard.general
    pasteboard.clearContents()
    pasteboard.setString(conversation.transcript, forType: .string)
    log("Copied transcript to clipboard")
  }

  private func copyLink() async {
    guard !isCopyingLink else { return }
    isCopyingLink = true
    defer { isCopyingLink = false }

    // Same contract as the detail view and the meeting-notes card: the
    // visibility mutation is what makes the URL resolve, so a failed mint
    // copies nothing instead of handing out a link that may 404.
    let feedback = await ConversationShareLinkAction.run(
      mintLink: { try await APIClient.shared.getConversationShareLink(id: conversation.id) },
      copyToPasteboard: { link in
        let pasteboard = NSPasteboard.general
        pasteboard.clearContents()
        return pasteboard.setString(link, forType: .string)
      },
      onFailure: { log("Failed to get share link: \($0)") }
    )
    if feedback == .copied {
      log("Copied conversation share link to clipboard (visibility set to shared)")
    }
  }

  private func deleteConversation() async {
    guard !isDeleting else { return }
    isDeleting = true

    if await appState.deleteConversation(conversation.id) {
      log("Deleted conversation \(conversation.id)")
    }

    isDeleting = false
  }

  /// Re-runs LLM processing for this conversation. Used when a conversation
  /// finished processing but ended up with no title — usually a transient
  /// LLM failure that resolves on retry. Replaces the row with the refreshed
  /// payload so the badge/CTA also update (a `.failed` conversation that
  /// reprocesses successfully should flip to `.completed`, not just gain a
  /// title — otherwise `displayState` keeps returning `.failed`).
  private func reprocessConversation() async {
    guard !isReprocessing else { return }
    isReprocessing = true

    AnalyticsManager.shared.conversationReprocessedDefault(conversationId: conversation.id)

    do {
      let refreshed = try await APIClient.shared.reprocessConversation(
        conversationId: conversation.id)

      // Sync to local SQLite cache so a reload doesn't revert the new title.
      try? await TranscriptionStorage.shared.updateTitleByBackendId(
        conversation.id, title: refreshed.structured.title)

      await MainActor.run {
        // Replace the whole conversation, not just the title — `status`,
        // `structured.overview`, action items etc. all change on reprocess
        // and the row's display state derives from `status` AND title.
        appState.replaceConversation(refreshed)
      }
      log("Reprocessed conversation \(conversation.id) → \(refreshed.structured.title)")
    } catch {
      log("Failed to reprocess conversation \(conversation.id): \(error)")
    }

    isReprocessing = false
  }

  private func updateTitle() async {
    guard !isUpdatingTitle, !editedTitle.isEmpty else { return }
    isUpdatingTitle = true

    await appState.updateConversationTitle(conversation.id, title: editedTitle)
    log("Updated conversation title to: \(editedTitle)")

    isUpdatingTitle = false
  }

  // MARK: - Row Actions

  private var inlineActionMenu: some View {
    Menu {
      if offersReprocess(now: Date()) {
        Button {
          Task { await reprocessConversation() }
        } label: {
          Label(
            isReprocessing ? "Reprocessing…" : "Reprocess title & summary",
            systemImage: isReprocessing ? "arrow.triangle.2.circlepath" : "wand.and.stars")
        }
        .disabled(isReprocessing)
      }

      Button {
        editedTitle = conversation.title
        showEditDialog = true
      } label: {
        Label("Edit title…", systemImage: "pencil")
      }

      Button(action: copyTranscript) {
        Label("Copy transcript", systemImage: "doc.on.doc")
      }

      Button {
        Task { await copyLink() }
      } label: {
        Label(
          isCopyingLink ? "Generating link…" : "Copy share link",
          systemImage: isCopyingLink ? "arrow.triangle.2.circlepath" : "link")
      }
      .disabled(isCopyingLink)

      if !folders.isEmpty {
        Menu {
          if conversation.folderId != nil {
            Button {
              Task { await onMoveToFolder(conversation.id, nil) }
            } label: {
              Label("Remove from Folder", systemImage: "folder.badge.minus")
            }
            Divider()
          }
          ForEach(folders) { folder in
            Button {
              Task { await onMoveToFolder(conversation.id, folder.id) }
            } label: {
              HStack {
                Text(folder.name)
                if conversation.folderId == folder.id {
                  Image(systemName: "checkmark")
                }
              }
            }
            .disabled(conversation.folderId == folder.id)
          }
        } label: {
          Label("Move to folder", systemImage: "folder")
        }
      }

      Divider()

      Button(role: .destructive) {
        showDeleteConfirmation = true
      } label: {
        Label("Delete conversation…", systemImage: "trash")
      }
    } label: {
      Image(systemName: "ellipsis")
        .scaledFont(size: OmiType.caption, weight: .semibold)
        .foregroundColor(Ink.secondary)
        .frame(width: 26, height: 26)
        .background(Circle().fill(Ink.rowFill))
    }
    .menuStyle(.borderlessButton)
    .menuIndicator(.hidden)
    .fixedSize()
    .help("Conversation actions")
    .accessibilityLabel("Actions for \(conversation.displayTitle)")
    .accessibilityIdentifier("conversation-row-actions-\(conversation.id)")
  }

  private var starButton: some View {
    Button {
      Task { await toggleStar() }
    } label: {
      Image(systemName: conversation.starred ? "star.fill" : "star")
        .scaledFont(size: isCompactView ? OmiType.caption : OmiType.body)
        .foregroundColor(conversation.starred ? PageGlass.starred : Ink.secondary)
        .opacity(isStarring ? 0.5 : 1.0)
        .frame(width: 26, height: 26)
    }
    .buttonStyle(.plain)
    .disabled(isStarring)
    .help(conversation.starred ? "Remove from Starred" : "Add to Starred")
    .accessibilityLabel(conversation.starred ? "Remove from Starred" : "Add to Starred")
  }

  // MARK: - Compact Row (single line)

  private func compactRowContent(phase: ConversationProcessingPhase) -> some View {
    HStack(spacing: OmiSpacing.sm) {
      // Checkbox for multi-select mode
      if isMultiSelectMode {
        Image(systemName: isSelected ? "checkmark.circle.fill" : "circle")
          .scaledFont(size: OmiType.heading)
          .foregroundColor(isSelected ? Ink.primary : Ink.secondary)
      }

      leadingTile(size: 36, fontSize: OmiType.subheading, cornerRadius: OmiChrome.smallControlRadius)

      // Title + metadata below
      VStack(alignment: .leading, spacing: OmiSpacing.hairline) {
        HStack(spacing: OmiSpacing.sm) {
          Text(conversation.displayTitle)
            .scaledFont(size: OmiType.body, weight: .medium)
            .foregroundColor(titleColor)
            .lineLimit(1)

          statusCluster(phase: phase)

          if isNewlyCreated {
            NewBadge()
          }

        }

        metadataLine
      }

      Spacer()
      Color.clear.frame(width: 58, height: 26)
    }
    .padding(.horizontal, OmiSpacing.md)
    .padding(.vertical, OmiSpacing.md)
    // The shared row states: nothing at rest, a wash under the pointer, the heavier
    // wash plus the one outline when selected. A `primary`-tinted fill would be a
    // third opinion about selection and, at 22%, an opaque slab on a glass panel.
    .glassRow(
      isSelected ? .selected : (isHovering || isNewlyCreated ? .hover : .rest),
      cornerRadius: OmiChrome.controlRadius)
  }

  // MARK: - Expanded Row (title + time/duration)

  private func expandedRowContent(phase: ConversationProcessingPhase) -> some View {
    HStack(spacing: OmiSpacing.md) {
      // Checkbox for multi-select mode
      if isMultiSelectMode {
        Image(systemName: isSelected ? "checkmark.circle.fill" : "circle")
          .scaledFont(size: OmiType.heading)
          .foregroundColor(isSelected ? Ink.primary : Ink.secondary)
      }

      leadingTile(size: 40, fontSize: OmiType.heading, cornerRadius: OmiChrome.chipRadius)

      // Title + time/duration below
      VStack(alignment: .leading, spacing: OmiSpacing.hairline) {
        HStack(spacing: OmiSpacing.sm) {
          Text(conversation.displayTitle)
            .scaledFont(size: OmiType.subheading, weight: .medium)
            .foregroundColor(titleColor)
            .lineLimit(1)

          statusCluster(phase: phase)

          if isNewlyCreated {
            NewBadge()
          }

        }

        metadataLine
      }

      Spacer()
      Color.clear.frame(width: 58, height: 26)
    }
    .padding(OmiSpacing.lg)
    // The shared row states: nothing at rest, a wash under the pointer, the heavier
    // wash plus the one outline when selected. A `primary`-tinted fill would be a
    // third opinion about selection and, at 22%, an opaque slab on a glass panel.
    .glassRow(
      isSelected ? .selected : (isHovering || isNewlyCreated ? .hover : .rest),
      cornerRadius: PageGlass.cardRadius)
  }

  @ViewBuilder
  private func rowContent(phase: ConversationProcessingPhase) -> some View {
    if isCompactView {
      // Compact mode: single line with all info
      compactRowContent(phase: phase)
    } else {
      // Expanded mode: title + overview with metadata below
      expandedRowContent(phase: phase)
    }
  }

  var body: some View {
    ZStack(alignment: .trailing) {
      Button(action: {
        if isMultiSelectMode {
          onToggleSelection?()
        } else {
          onTap()
        }
      }) {
        Group {
          if isLivePipelineRow {
            // Bound the wait: the phase moves on a 15s clock so "Summarizing"
            // becomes "Taking longer than usual" and then "Stuck" without any
            // network event, and the Reprocess exit appears when it should.
            TimelineView(.periodic(from: .now, by: 15)) { timeline in
              rowContent(phase: processingPhase(now: timeline.date))
            }
          } else {
            rowContent(phase: .summarizing)
          }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .contentShape(Rectangle())
      }
      .buttonStyle(.plain)

      if !isMultiSelectMode {
        HStack(spacing: OmiSpacing.xxs) {
          if isHovering {
            inlineActionMenu
              .transition(.opacity)
          }
          starButton
        }
        .padding(.trailing, isCompactView ? OmiSpacing.md : OmiSpacing.lg)
      }
    }
    .onHover { hovering in
      isHovering = hovering
      if hovering {
        NSCursor.pointingHand.push()
      } else {
        NSCursor.pop()
      }
    }
    .contextMenu {
      Button(action: copyTranscript) {
        Label("Copy Transcript", systemImage: "doc.on.doc")
      }

      Button(action: { Task { await copyLink() } }) {
        Label(
          isCopyingLink ? "Generating Link..." : "Copy Share Link",
          systemImage: isCopyingLink ? "arrow.triangle.2.circlepath" : "link")
      }
      .disabled(isCopyingLink)
      .help("Anyone with the link can view")

      Divider()

      Button(action: {
        editedTitle = conversation.title
        showEditDialog = true
      }) {
        Label("Edit Title", systemImage: "pencil")
      }

      // Reprocess — surfaced in the menu (in addition to the inline hover
      // button) so it's discoverable even without hovering. Only enabled when
      // there's something to recover (canReprocess) or the pipeline stalled.
      if offersReprocess(now: Date()) {
        Button(action: { Task { await reprocessConversation() } }) {
          Label(
            isReprocessing ? "Reprocessing…" : "Reprocess Title & Summary",
            systemImage: isReprocessing ? "arrow.triangle.2.circlepath" : "wand.and.stars")
        }
        .disabled(isReprocessing)
      }

      // Move to Folder submenu
      if !folders.isEmpty {
        Menu {
          // Option to remove from folder
          if conversation.folderId != nil {
            Button(action: {
              Task {
                await onMoveToFolder(conversation.id, nil)
              }
            }) {
              Label("Remove from Folder", systemImage: "folder.badge.minus")
            }
            Divider()
          }

          // List available folders
          ForEach(folders) { folder in
            Button(action: {
              Task {
                await onMoveToFolder(conversation.id, folder.id)
              }
            }) {
              HStack {
                Text(folder.name)
                if conversation.folderId == folder.id {
                  Image(systemName: "checkmark")
                }
              }
            }
            .disabled(conversation.folderId == folder.id)
          }
        } label: {
          Label("Move to Folder", systemImage: "folder")
        }
      }

      Divider()

      Button(
        role: .destructive,
        action: {
          showDeleteConfirmation = true
        }
      ) {
        Label("Delete", systemImage: "trash")
      }
    }
    .alert("Edit Conversation Title", isPresented: $showEditDialog) {
      TextField("Title", text: $editedTitle)
      Button("Cancel", role: .cancel) {}
      Button("Save") {
        Task {
          await updateTitle()
        }
      }
      .disabled(editedTitle.isEmpty || isUpdatingTitle)
    } message: {
      Text("Enter a new title for this conversation")
    }
    .alert("Delete Conversation", isPresented: $showDeleteConfirmation) {
      Button("Cancel", role: .cancel) {}
      Button("Delete", role: .destructive) {
        Task {
          await deleteConversation()
        }
      }
    } message: {
      Text("Are you sure you want to delete this conversation? This action cannot be undone.")
    }
  }
}

#if canImport(PreviewsMacros)
  #Preview {
    VStack(spacing: OmiSpacing.md) {
      // Preview would require mock ServerConversation
      Text("ConversationRowView Preview")
        .foregroundColor(Ink.primary)
    }
    .padding()
  }
#endif
