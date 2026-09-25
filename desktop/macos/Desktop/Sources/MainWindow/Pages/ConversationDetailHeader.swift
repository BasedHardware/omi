import OmiTheme
import SwiftUI

// MARK: - Facts the header states

/// The header's secondary line, computed once so the view stays a layout.
enum ConversationDetailMeta {
  /// "Tue, Sep 23 · 12:58 – 2:00 PM", or the start alone for an open-ended conversation.
  static func when(
    start: Date, end: Date?, now: Date = Date(), locale: Locale = .current, timeZone: TimeZone = .current
  ) -> String {
    var calendar = Calendar(identifier: .gregorian)
    calendar.timeZone = timeZone
    let day = DateFormatter()
    day.locale = locale
    day.timeZone = timeZone
    // The year only when it is not this one: "Tue, Sep 23" reads faster than a full date.
    day.setLocalizedDateFormatFromTemplate(
      calendar.isDate(start, equalTo: now, toGranularity: .year) ? "EEEMMMd" : "EEEMMMdyyyy")
    let dayText = day.string(from: start)

    guard let end, end > start else {
      let time = DateFormatter()
      time.locale = locale
      time.timeZone = timeZone
      time.dateStyle = .none
      time.timeStyle = .short
      return "\(dayText) · \(time.string(from: start))"
    }
    let interval = DateIntervalFormatter()
    interval.locale = locale
    interval.timeZone = timeZone
    interval.dateStyle = .none
    interval.timeStyle = .short
    return "\(dayText) · \(interval.string(from: start, to: end))"
  }

  /// "You, Speaker 1 +2": the first names that fit a metadata line, then how many more.
  static func peopleSummary(_ names: [String], limit: Int = 2) -> String {
    guard names.count > limit else { return names.joined(separator: ", ") }
    return names.prefix(limit).joined(separator: ", ") + " +\(names.count - limit)"
  }

  /// Who spoke, by the names the transcript shows (`SpeakerLabelFormatter`: "You", a named person,
  /// or the 1-based "Speaker N"). First appearance order, with the reader first.
  static func participants(in segments: [TranscriptSegment], people: [Person]) -> [String] {
    let names = SpeakerLabelFormatter(people: people).participants(in: segments)
    guard let you = names.firstIndex(of: "You") else { return names }
    return ["You"] + names[..<you] + names[(you + 1)...]
  }
}

// MARK: - Header

/// Title bar and page actions for one conversation, shared by the summary and transcript panes
/// so switching panes never loses the title, the way back, or the actions.
///
/// Two rows and nothing else. Row one is identity and control: back, emoji, title, the pane
/// switch, and the three actions a reader reaches for (star, share, more). Row two is one
/// secondary line of facts — when, how long, who, what, where it is filed — ending in the
/// device stack when more than one device recorded the event. Anything rarer lives in the
/// overflow menu, which keeps the one red action off the page until it is asked for.
struct ConversationDetailHeader<BannerInset: View, Recordings: View, Trailing: View>: View {
  let conversation: ServerConversation
  let folders: [Folder]
  let people: [Person]
  let pane: ConversationDetailPane
  let canCopyTranscript: Bool
  let isGroupedEvent: Bool
  /// Where Back returns to, named on the chip ("‹ Conversations", "‹ Memories").
  let backTitle: String
  let onBack: () -> Void
  let onSelectPane: (ConversationDetailPane) -> Void
  let onToggleStar: () -> Void
  let onRename: () -> Void
  let onMoveToFolder: ((String?) -> Void)?
  let onCopyTranscript: () -> Void
  let onDiscussInChat: (() -> Void)?
  let onDelete: () -> Void
  @ViewBuilder let bannerInset: () -> BannerInset
  @ViewBuilder let recordings: () -> Recordings
  /// The pane's own tool at the end of the metadata line (transcript re-sync).
  @ViewBuilder let trailing: () -> Trailing

  private var folderName: String? {
    guard let id = conversation.folderId else { return nil }
    return folders.first { $0.id == id }?.name
  }

  private var titleColor: Color {
    if case .titled = conversation.displayState { return Ink.primary }
    return Ink.secondary
  }

  var body: some View {
    HStack(alignment: .top, spacing: OmiSpacing.md) {
      // A drill-in leaves the way it came: the chip on the leading edge names the destination.
      BackChip(backTitle, accessibilityIdentifier: "conversation-detail-back", action: onBack)
        .frame(height: 28)
      VStack(alignment: .leading, spacing: OmiSpacing.xs) {
        titleRow
        HStack(spacing: OmiSpacing.sm) {
          metaLine
          Spacer(minLength: OmiSpacing.sm)
          trailing()
        }
      }
      bannerInset()
    }
  }

  // MARK: Row one

  private var titleRow: some View {
    HStack(spacing: OmiSpacing.sm) {
      // Emoji, or the neutral waveform the list row uses — a fallback 💬 would claim an identity the
      // pipeline has not produced.
      if conversation.structured.emoji.isEmpty {
        Image(systemName: "waveform")
          .scaledFont(size: OmiType.body)
          .foregroundColor(Ink.secondary)
      } else {
        Text(conversation.structured.emoji)
          .scaledFont(size: OmiType.heading)
      }
      Text(conversation.displayTitle)
        .scaledFont(size: OmiType.heading, weight: .semibold)
        .foregroundColor(titleColor)
        .lineLimit(1)
        .truncationMode(.tail)
        .help(conversation.displayTitle)
        .layoutPriority(-1)
      // Fixed so a narrow window truncates the title, never wraps the badge.
      ConversationStatusBadge(state: conversation.displayState)
        .fixedSize()

      Spacer(minLength: OmiSpacing.md)

      ConversationDetailPaneSwitch(
        pane: pane, transcriptCount: conversation.transcriptSegments.count, onSelect: onSelectPane)
      actions
    }
  }

  // MARK: Row two

  /// One line of facts. When it is short of room the category goes first, then people and place;
  /// both stay in their tooltips and the transcript.
  private var metaLine: some View {
    ViewThatFits(in: .horizontal) {
      metaItems(includeCategory: true, includeSecondary: true)
      metaItems(includeCategory: false, includeSecondary: true)
      metaItems(includeCategory: false, includeSecondary: false)
    }
  }

  private func metaItems(includeCategory: Bool, includeSecondary: Bool) -> some View {
    let start = conversation.startedAt ?? conversation.createdAt
    let participants = ConversationDetailMeta.participants(in: conversation.transcriptSegments, people: people)
    let address = conversation.geolocation?.address.flatMap { $0.isEmpty ? nil : $0 }
    let category = conversation.structured.category
    return HStack(spacing: OmiSpacing.xs) {
      metaText(ConversationDetailMeta.when(start: start, end: conversation.finishedAt))
      dot
      metaText(conversation.formattedDuration)
      // A grouped event names its devices in the stack at the end; naming one here would single
      // out whichever recording happens to be open.
      if !isGroupedEvent, let source = conversation.source, source != .unknown {
        dot
        Label(source.captureLabel, systemImage: source.captureSymbol)
          .labelStyle(DetailMetaLabelStyle())
      }
      if includeSecondary, !participants.isEmpty {
        dot
        Label(ConversationDetailMeta.peopleSummary(participants), systemImage: "person.2")
          .labelStyle(DetailMetaLabelStyle())
          .help(participants.joined(separator: ", "))
      }
      if includeCategory, !category.isEmpty, category != "other" {
        dot
        metaText(category.capitalized)
      }
      if let folderName {
        dot
        Label(folderName, systemImage: "folder")
          .labelStyle(DetailMetaLabelStyle())
      }
      if includeSecondary, let address {
        dot
        Label(address, systemImage: "mappin.and.ellipse")
          .labelStyle(DetailMetaLabelStyle())
          .help(address)
      }
      recordings()
        .padding(.leading, OmiSpacing.xxs)
    }
    .lineLimit(1)
    .fixedSize(horizontal: true, vertical: false)
  }

  private var dot: some View {
    metaText("·")
  }

  private func metaText(_ text: String) -> some View {
    Text(text)
      .scaledFont(size: OmiType.caption)
      .foregroundColor(Ink.secondary)
  }

  private var actions: some View {
    HStack(spacing: OmiSpacing.xs) {
      if let onDiscussInChat {
        OmiIconButton("bubble.left.and.bubble.right", help: "Discuss in Chat", action: onDiscussInChat)
          .accessibilityLabel("Discuss this conversation in Chat")
          // Preserve the capture archive's automation contract.
          .accessibilityIdentifier("chat-first-capture-discuss-\(conversation.id)")
      }

      // The star keeps its starred colour, so it is drawn here on the shared icon-button chrome.
      Button(action: onToggleStar) {
        Image(systemName: conversation.starred ? "star.fill" : "star")
          .scaledFont(size: OmiType.body, weight: .medium)
          .foregroundColor(conversation.starred ? PageGlass.starred : Ink.secondary)
      }
      .buttonStyle(GlassIconButtonStyle(diameter: OmiIconButtonSize.regular.diameter, restsFilled: true))
      .help(conversation.starred ? "Remove from Starred" : "Add to Starred")
      .accessibilityLabel(conversation.starred ? "Remove from Starred" : "Add to Starred")
      .accessibilityIdentifier("conversation-detail-star")

      ConversationShareLinkButton(
        conversationId: conversation.id,
        canShare: canCopyTranscript,
        onCopied: {
          AnalyticsManager.shared.shareAction(
            category: "conversation", properties: ["conversation_id": conversation.id])
        }
      )

      moreMenu
    }
  }

  private var moreMenu: some View {
    OmiIconMenu(systemName: "ellipsis", help: "More actions") {
      Button(action: onCopyTranscript) {
        Label("Copy Transcript", systemImage: "doc.on.doc")
      }
      .disabled(!canCopyTranscript)
      Button(action: onRename) {
        Label("Rename…", systemImage: "pencil")
      }
      if let onMoveToFolder, !folders.isEmpty {
        Menu {
          if conversation.folderId != nil {
            Button {
              onMoveToFolder(nil)
            } label: {
              Label("Remove from Folder", systemImage: "folder.badge.minus")
            }
            Divider()
          }
          ForEach(folders) { folder in
            Button {
              onMoveToFolder(folder.id)
            } label: {
              if conversation.folderId == folder.id {
                Label(folder.name, systemImage: "checkmark")
              } else {
                Text(folder.name)
              }
            }
            .disabled(conversation.folderId == folder.id)
          }
        } label: {
          Label("Move to Folder", systemImage: "folder")
        }
      }
      Divider()
      Button(role: .destructive, action: onDelete) {
        Label("Delete Conversation…", systemImage: "trash")
      }
    }
    .accessibilityIdentifier("conversation-detail-more")
  }
}

// MARK: - Pane switch

/// Summary / Transcript as one segmented capsule, sized to sit in the title row.
struct ConversationDetailPaneSwitch: View {
  let pane: ConversationDetailPane
  let transcriptCount: Int
  let onSelect: (ConversationDetailPane) -> Void

  var body: some View {
    HStack(spacing: OmiSpacing.hairline) {
      segment(.summary, title: "Summary", count: nil)
      segment(.transcript, title: "Transcript", count: transcriptCount)
    }
    .padding(OmiSpacing.hairline)
    .glassChip()
    .fixedSize()
  }

  private func segment(_ target: ConversationDetailPane, title: String, count: Int?) -> some View {
    let isActive = pane == target
    return Button {
      onSelect(target)
    } label: {
      HStack(spacing: OmiSpacing.xxs) {
        Text(title)
          .scaledFont(size: OmiType.caption, weight: isActive ? .semibold : .medium)
        if let count, count > 0 {
          Text("\(count)")
            .scaledFont(size: OmiType.micro, weight: .medium)
            .monospacedDigit()
            .foregroundColor(Ink.secondary)
        }
      }
      .foregroundColor(isActive ? Ink.primary : Ink.secondary)
      .padding(.horizontal, OmiSpacing.md)
      .frame(height: 24)
      .background(Capsule(style: .continuous).fill(isActive ? PageGlass.chipFill(isActive: true) : .clear))
      .contentShape(Capsule(style: .continuous))
    }
    .buttonStyle(.plain)
    .accessibilityAddTraits(isActive ? .isSelected : [])
    .accessibilityIdentifier("conversation-detail-pane-\(target == .summary ? "summary" : "transcript")")
  }
}

/// Section heading inside the summary pane: a glyph, a title, an optional count, and the
/// section's own control on the trailing edge.
struct DetailSectionHeader<Trailing: View>: View {
  let title: String
  let systemImage: String
  var count: Int?
  @ViewBuilder var trailing: () -> Trailing

  var body: some View {
    HStack(spacing: OmiSpacing.sm) {
      Image(systemName: systemImage)
        .scaledFont(size: OmiType.caption, weight: .medium)
        .foregroundColor(Ink.secondary)
        .frame(width: 16)
      Text(title)
        .scaledFont(size: OmiType.body, weight: .semibold)
        .foregroundColor(Ink.primary)
      if let count {
        Text("\(count)")
          .scaledFont(size: OmiType.caption, weight: .medium)
          .monospacedDigit()
          .foregroundColor(Ink.secondary)
      }
      Spacer(minLength: OmiSpacing.sm)
      trailing()
    }
  }
}

extension DetailSectionHeader where Trailing == EmptyView {
  init(title: String, systemImage: String, count: Int? = nil) {
    self.init(title: title, systemImage: systemImage, count: count, trailing: { EmptyView() })
  }
}

/// A quiet text button in a section header ("Change", "Reprocess").
struct DetailQuietButtonLabel: View {
  let title: String
  let systemImage: String

  var body: some View {
    HStack(spacing: OmiSpacing.xxs) {
      Image(systemName: systemImage)
      Text(title)
    }
    .scaledFont(size: OmiType.caption, weight: .medium)
    .foregroundColor(Ink.secondary)
    .contentShape(Rectangle())
  }
}

private struct DetailMetaLabelStyle: LabelStyle {
  func makeBody(configuration: Configuration) -> some View {
    HStack(spacing: OmiSpacing.xxs) {
      configuration.icon
        .scaledFont(size: OmiType.micro)
      configuration.title
        .scaledFont(size: OmiType.caption)
    }
    .foregroundColor(Ink.secondary)
  }
}
