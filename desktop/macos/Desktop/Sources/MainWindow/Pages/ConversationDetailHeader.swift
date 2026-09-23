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

  /// Who spoke, by the names the transcript shows: "You", a named person, or "Speaker N".
  /// First appearance order, with the reader first.
  static func participants(in segments: [TranscriptSegment], people: [Person]) -> [String] {
    let names = Dictionary(lastWriteWins: people.map { ($0.id, $0.name) })
    var seen: Set<String> = []
    var result: [String] = []
    if segments.contains(where: \.isUser) {
      seen.insert("You")
      result.append("You")
    }
    for segment in segments where !segment.isUser {
      let name = segment.personId.flatMap { names[$0] } ?? "Speaker \(segment.speakerId)"
      if seen.insert(name).inserted { result.append(name) }
    }
    return result
  }
}

// MARK: - Header

/// Title block and page actions for one conversation, shared by the summary and transcript panes
/// so switching panes never loses the title, the way back, or the actions.
///
/// Hierarchy, top to bottom: what it is (emoji, title, status), when and how (date, time,
/// duration, device, category, folder), who and where, and — only for an event more than one
/// device recorded — the other recordings. Destructive and rarely used actions live in the
/// overflow menu so the one red thing on the page is not permanently on screen.
struct ConversationDetailHeader<BannerInset: View, Recordings: View>: View {
  let conversation: ServerConversation
  let folders: [Folder]
  let people: [Person]
  let canCopyTranscript: Bool
  let isGroupedEvent: Bool
  let onBack: () -> Void
  let onToggleStar: () -> Void
  let onRename: () -> Void
  let onMoveToFolder: ((String?) -> Void)?
  let onCopyTranscript: () -> Void
  let onDelete: () -> Void
  @ViewBuilder let bannerInset: () -> BannerInset
  @ViewBuilder let recordings: () -> Recordings

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
      backButton

      VStack(alignment: .leading, spacing: OmiSpacing.xs) {
        HStack(alignment: .firstTextBaseline, spacing: OmiSpacing.sm) {
          Text(conversation.structured.emoji.isEmpty ? "\u{1F4AC}" : conversation.structured.emoji)
            .scaledFont(size: OmiType.heading)
          Text(conversation.displayTitle)
            .scaledFont(size: OmiType.heading, weight: .semibold)
            .foregroundColor(titleColor)
            .lineLimit(2)
            .fixedSize(horizontal: false, vertical: true)
            .help(conversation.displayTitle)
          ConversationStatusBadge(state: conversation.displayState)
        }

        metaLine
        peopleLine
        recordings()
      }
      .frame(maxWidth: .infinity, alignment: .leading)

      bannerInset()

      actions
    }
  }

  // MARK: Pieces

  private var backButton: some View {
    // A stadium chip, not blue text: Back is already a button, and a blue word beside a black
    // headline is the loudest thing on the panel.
    Button(action: onBack) {
      HStack(spacing: OmiSpacing.xxs) {
        Image(systemName: "chevron.left")
        Text("Back")
      }
      .scaledFont(size: OmiType.caption, weight: .semibold)
      .foregroundColor(Ink.primary)
      .padding(.horizontal, OmiSpacing.md)
      .frame(height: 28)
      .glassChip()
    }
    .buttonStyle(.plain)
    .help("Back to conversations")
  }

  private var metaLine: some View {
    let start = conversation.startedAt ?? conversation.createdAt
    return HStack(spacing: OmiSpacing.xs) {
      metaText(ConversationDetailMeta.when(start: start, end: conversation.finishedAt))
      separatorDot
      metaText(conversation.formattedDuration)
      // A grouped event names its devices in the recordings row below; saying one of them here
      // would single out whichever recording happens to be open.
      if !isGroupedEvent, let source = conversation.source, source != .unknown {
        separatorDot
        Label(source.captureLabel, systemImage: source.captureSymbol)
          .labelStyle(DetailMetaLabelStyle())
      }
      let category = conversation.structured.category
      if !category.isEmpty && category != "other" {
        separatorDot
        metaText(category.capitalized)
      }
      if let folderName {
        separatorDot
        Label(folderName, systemImage: "folder")
          .labelStyle(DetailMetaLabelStyle())
      }
    }
    .lineLimit(1)
  }

  @ViewBuilder
  private var peopleLine: some View {
    let participants = ConversationDetailMeta.participants(in: conversation.transcriptSegments, people: people)
    let address = conversation.geolocation?.address.flatMap { $0.isEmpty ? nil : $0 }
    if !participants.isEmpty || address != nil {
      HStack(spacing: OmiSpacing.md) {
        if !participants.isEmpty {
          Label(participants.joined(separator: ", "), systemImage: "person.2")
            .labelStyle(DetailMetaLabelStyle())
        }
        if let address {
          Label(address, systemImage: "mappin.and.ellipse")
            .labelStyle(DetailMetaLabelStyle())
        }
      }
      .lineLimit(1)
      .truncationMode(.tail)
    }
  }

  private var separatorDot: some View {
    metaText("·")
  }

  private func metaText(_ text: String) -> some View {
    Text(text)
      .scaledFont(size: OmiType.caption)
      .foregroundColor(Ink.secondary)
  }

  private var actions: some View {
    HStack(spacing: OmiSpacing.xs) {
      Button(action: onToggleStar) {
        DetailIconLabel(
          systemImage: conversation.starred ? "star.fill" : "star",
          color: conversation.starred ? PageGlass.starred : Ink.secondary)
      }
      .buttonStyle(.plain)
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

      Button(action: onCopyTranscript) {
        DetailIconLabel(systemImage: "doc.on.doc")
      }
      .buttonStyle(.plain)
      .disabled(!canCopyTranscript)
      .help("Copy transcript")

      moreMenu
    }
  }

  private var moreMenu: some View {
    Menu {
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
    } label: {
      DetailIconLabel(systemImage: "ellipsis")
    }
    // `.button` + `.plain` draws the custom label; `.borderlessButton` redraws it as a system glyph.
    .menuStyle(.button)
    .buttonStyle(.plain)
    .menuIndicator(.hidden)
    .fixedSize()
    .help("More actions")
    .accessibilityLabel("More actions")
    .accessibilityIdentifier("conversation-detail-more")
  }
}

// MARK: - Pane bar

/// Summary / Transcript switch, with the pane's own tools on the trailing edge.
struct ConversationDetailPaneBar<Trailing: View>: View {
  let pane: ConversationDetailPane
  let transcriptCount: Int
  let onSelect: (ConversationDetailPane) -> Void
  @ViewBuilder let trailing: () -> Trailing

  var body: some View {
    HStack(spacing: OmiSpacing.xs) {
      tab(.summary, title: "Summary", systemImage: "text.alignleft", count: nil)
      tab(.transcript, title: "Transcript", systemImage: "text.quote", count: transcriptCount)
      Spacer(minLength: OmiSpacing.md)
      trailing()
    }
  }

  private func tab(_ target: ConversationDetailPane, title: String, systemImage: String, count: Int?)
    -> some View
  {
    let isActive = pane == target
    return Button {
      onSelect(target)
    } label: {
      HStack(spacing: OmiSpacing.xs) {
        Image(systemName: systemImage)
          .scaledFont(size: OmiType.caption)
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
      .frame(height: 28)
      .glassChip(isActive: isActive)
    }
    .buttonStyle(.plain)
    .accessibilityAddTraits(isActive ? .isSelected : [])
    .accessibilityIdentifier("conversation-detail-pane-\(target == .summary ? "summary" : "transcript")")
  }
}

/// A text-and-icon action in the pane bar ("Discuss in Chat").
struct DetailPillLabel: View {
  let title: String
  let systemImage: String

  var body: some View {
    HStack(spacing: OmiSpacing.xs) {
      Image(systemName: systemImage)
        .scaledFont(size: OmiType.caption)
      Text(title)
        .scaledFont(size: OmiType.caption, weight: .medium)
        .lineLimit(1)
        .fixedSize()
    }
    .foregroundColor(Ink.primary)
    .padding(.horizontal, OmiSpacing.md)
    .frame(height: 28)
    .glassChip()
  }
}

/// The one icon-button shape on this page: a 28 pt circle on the hover wash.
struct DetailIconLabel: View {
  let systemImage: String
  var color: Color = Ink.secondary

  var body: some View {
    Image(systemName: systemImage)
      .scaledFont(size: OmiType.body)
      .foregroundColor(color)
      .frame(width: 28, height: 28)
      // Same circle as `ConversationShareLinkButton`, which sits in the same row.
      .background(Circle().fill(Ink.rowFillHover))
      .contentShape(Circle())
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
