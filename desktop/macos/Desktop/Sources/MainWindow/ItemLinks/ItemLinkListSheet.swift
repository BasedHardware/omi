import OmiTheme
import SwiftUI

/// The "N items" sheet an item-list link opens. Rows keep the link's order;
/// each opens the same detail surface its kind opens everywhere else.
struct ItemLinkListSheet: View {
  let state: ItemLinkSheetState
  let onOpen: (ItemLinkRow) -> Void
  let onDismiss: () -> Void

  private var title: String {
    let count = state.references.count
    return count == 1 ? "1 item" : "\(count) items"
  }

  var body: some View {
    VStack(alignment: .leading, spacing: OmiSpacing.md) {
      HStack(alignment: .center) {
        Text(title)
          .scaledFont(size: OmiType.subheading, weight: .semibold)
          .foregroundStyle(Ink.primary)
          .accessibilityAddTraits(.isHeader)
        Spacer(minLength: OmiSpacing.md)
        DismissButton(action: onDismiss)
      }

      content
    }
    .padding(OmiSpacing.xl)
    .frame(width: 480)
    .frame(minHeight: 220, maxHeight: 560, alignment: .top)
    .background(Ink.surface)
    .accessibilityIdentifier("item-link-list-sheet")
  }

  @ViewBuilder
  private var content: some View {
    if let rows = state.rows {
      if rows.isEmpty {
        ItemLinkEmptyState()
      } else {
        ScrollView {
          LazyVStack(alignment: .leading, spacing: OmiSpacing.xs) {
            ForEach(rows) { row in
              ItemLinkRowView(row: row, onOpen: { onOpen(row) })
            }
          }
        }
      }
    } else {
      VStack(spacing: OmiSpacing.md) {
        ProgressView()
          .controlSize(.small)
          .tint(Ink.secondary)
        Text("Loading items…")
          .inkStyle(.prose, color: Ink.secondary)
      }
      .frame(maxWidth: .infinity, minHeight: 140)
      .accessibilityElement(children: .combine)
      .accessibilityIdentifier("item-link-list-loading")
    }
  }
}

private struct ItemLinkEmptyState: View {
  var body: some View {
    VStack(spacing: OmiSpacing.xs) {
      Image(systemName: "tray")
        .scaledFont(size: OmiType.heading, weight: .regular)
        .foregroundStyle(Ink.secondary)
      Text("Nothing to show")
        .inkStyle(.rowCopy, color: Ink.primary)
      Text("This link doesn't name any conversations, tasks, or memories.")
        .inkStyle(.statusLabel, color: Ink.secondary)
        .multilineTextAlignment(.center)
    }
    .frame(maxWidth: .infinity, minHeight: 140)
    .accessibilityElement(children: .combine)
    .accessibilityIdentifier("item-link-list-empty")
  }
}

/// One row. Available rows share the Spine conversation row's grammar — a
/// round tile, a one-line title, a secondary line — on the row-fill wash the
/// design system uses for hover and selection. Unavailable rows are muted and
/// inert.
struct ItemLinkRowView: View {
  let row: ItemLinkRow
  let onOpen: () -> Void

  @State private var isHovering = false

  var body: some View {
    if row.isAvailable {
      Button(action: onOpen) { rowBody }
        .buttonStyle(.plain)
        .pointingHandOnHover { isHovering = $0 }
        .accessibilityLabel(Text("\(presentation.title). \(presentation.subtitle)"))
        .accessibilityIdentifier("item-link-row-\(row.reference.kind.rawValue)-\(row.reference.id)")
    } else {
      rowBody
        .opacity(0.6)
        .accessibilityElement(children: .combine)
        .accessibilityLabel(Text("\(presentation.subtitle), no longer available"))
        .accessibilityIdentifier("item-link-row-unavailable-\(row.reference.id)")
    }
  }

  private var rowBody: some View {
    HStack(spacing: OmiSpacing.md) {
      tile
      VStack(alignment: .leading, spacing: 2) {
        Text(presentation.title)
          .inkStyle(.rowCopy, color: row.isAvailable ? Ink.primary : Ink.secondary)
          .strikethrough(presentation.isCompletedTask, color: Ink.secondary)
          .lineLimit(2)
          .truncationMode(.tail)
        Text(presentation.subtitle)
          .inkStyle(.statusLabel, color: Ink.secondary)
          .lineLimit(1)
      }
      .frame(maxWidth: .infinity, alignment: .leading)
      if row.isAvailable {
        Image(systemName: "chevron.right")
          .scaledFont(size: OmiType.caption, weight: .semibold)
          .foregroundStyle(Ink.secondary)
      }
    }
    .padding(.horizontal, OmiSpacing.md)
    .padding(.vertical, OmiSpacing.sm + 2)
    .background(
      RoundedRectangle(cornerRadius: 10, style: .continuous)
        .fill(isHovering && row.isAvailable ? Ink.rowFillHover : Ink.rowFill)
    )
    .contentShape(Rectangle())
  }

  private var tile: some View {
    Group {
      if let emoji = presentation.emoji {
        Text(emoji).scaledFont(size: OmiType.subheading)
      } else {
        Image(systemName: presentation.symbol)
          .scaledFont(size: OmiType.body, weight: .medium)
          .foregroundStyle(Ink.secondary)
      }
    }
    .frame(width: 32, height: 32)
    .background(Circle().fill(Ink.rowFillHover))
    .overlay(Circle().strokeBorder(Ink.separator, lineWidth: 1))
  }

  private var presentation: ItemLinkRowPresentation {
    ItemLinkRowPresentation(row: row)
  }
}

/// Row text, kept out of the view so its wording is testable.
struct ItemLinkRowPresentation: Equatable {
  let title: String
  let subtitle: String
  let symbol: String
  let emoji: String?
  let isCompletedTask: Bool

  static let unavailableTitle = "No longer available"

  init(row: ItemLinkRow) {
    let kindLabel = Self.kindLabel(row.reference.kind)
    guard let item = row.item else {
      title = Self.unavailableTitle
      subtitle = kindLabel
      symbol = Self.symbol(row.reference.kind)
      emoji = nil
      isCompletedTask = false
      return
    }
    switch item {
    case .conversation(let conversation):
      title = conversation.displayTitle
      subtitle = "\(kindLabel) · \(OmiDateFormat.timestamp(conversation.startedAt ?? conversation.createdAt))"
      symbol = Self.symbol(.conversation)
      let trimmed = conversation.structured.emoji.trimmingCharacters(in: .whitespacesAndNewlines)
      emoji = trimmed.isEmpty ? nil : trimmed
      isCompletedTask = false
    case .task(let task):
      title = task.description
      if task.completed {
        subtitle = "\(kindLabel) · Completed"
      } else if let due = task.dueAt {
        subtitle = "\(kindLabel) · Due \(OmiDateFormat.timestamp(due))"
      } else {
        subtitle = kindLabel
      }
      symbol = task.completed ? "checkmark.circle.fill" : "circle"
      emoji = nil
      isCompletedTask = task.completed
    case .memory(let memory):
      title = memory.content
      subtitle = "\(kindLabel) · \(memory.category.displayName)"
      symbol = Self.symbol(.memory)
      emoji = nil
      isCompletedTask = false
    }
  }

  static func kindLabel(_ kind: ItemLinkKind) -> String {
    switch kind {
    case .conversation: return "Conversation"
    case .task: return "Task"
    case .memory: return "Memory"
    }
  }

  static func symbol(_ kind: ItemLinkKind) -> String {
    switch kind {
    case .conversation: return "waveform"
    case .task: return "circle"
    case .memory: return "brain.head.profile"
    }
  }
}
