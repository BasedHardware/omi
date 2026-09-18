import OmiTheme
import SwiftUI

/// List view showing conversations grouped by date
struct ConversationListView: View {
  let conversations: [ServerConversation]
  let isLoading: Bool
  let error: String?
  let folders: [Folder]
  var isCompactView: Bool = true
  let onSelect: (ServerConversation) -> Void
  let onRefresh: () -> Void
  let onMoveToFolder: (String, String?) async -> Void

  // Multi-select support
  var isMultiSelectMode: Bool = false
  var selectedIds: Set<String> = []
  var onToggleSelection: ((String) -> Void)? = nil

  /// When true, renders without its own ScrollView (for embedding in an outer ScrollView)
  var embedded: Bool = false

  var appState: AppState

  private static let groupDateFormatter: DateFormatter = {
    let f = DateFormatter()
    f.dateFormat = "MMM d, yyyy"
    return f
  }()

  /// Flat list item — either a section header or a conversation row.
  /// Using a single flat ForEach avoids nested ForEach attribute graph depth which can cause
  /// SwiftUI layout comparison hangs (AG::LayoutDescriptor::compare) on refresh.
  private enum ListItem: Identifiable {
    case header(key: String, isFirst: Bool)
    case conversation(ServerConversation)

    var id: String {
      switch self {
      case .header(let key, _): return "header_\(key)"
      case .conversation(let c): return c.id
      }
    }
  }

  /// Flat ordered list of headers + conversations, grouped by date.
  private var flatListItems: [ListItem] {
    let calendar = Calendar.current
    let today = calendar.startOfDay(for: Date())
    let yesterday = calendar.date(byAdding: .day, value: -1, to: today)!
    let formatter = Self.groupDateFormatter

    var groups: [String: [ServerConversation]] = [:]
    var groupDates: [String: Date] = ["Today": today, "Yesterday": yesterday]

    for conversation in conversations {
      let conversationDate = calendar.startOfDay(for: conversation.createdAt)
      let groupKey: String

      if conversationDate == today {
        groupKey = "Today"
      } else if conversationDate == yesterday {
        groupKey = "Yesterday"
      } else {
        groupKey = formatter.string(from: conversation.createdAt)
        groupDates[groupKey] = conversationDate
      }

      groups[groupKey, default: []].append(conversation)
    }

    // Sort groups: Today first, then Yesterday, then by date descending
    let sortedKeys = groups.keys.sorted { key1, key2 in
      if key1 == "Today" { return true }
      if key2 == "Today" { return false }
      if key1 == "Yesterday" { return true }
      if key2 == "Yesterday" { return false }
      let date1 = groupDates[key1] ?? .distantPast
      let date2 = groupDates[key2] ?? .distantPast
      return date1 > date2
    }

    var items: [ListItem] = []
    for (index, key) in sortedKeys.enumerated() {
      guard let convos = groups[key] else { continue }
      items.append(.header(key: key, isFirst: index == 0))
      for conv in convos {
        items.append(.conversation(conv))
      }
    }
    return items
  }

  var body: some View {
    Group {
      if isLoading && conversations.isEmpty {
        loadingView
      } else if let error = error, conversations.isEmpty {
        errorView(error)
      } else if conversations.isEmpty {
        emptyView
      } else {
        conversationList
      }
    }
  }

  private var loadingView: some View {
    VStack(spacing: OmiSpacing.lg) {
      ProgressView()
        .scaleEffect(1.2)
        .tint(Ink.secondary)

      Text("Loading conversations...")
        .scaledFont(size: OmiType.body)
        .foregroundColor(Ink.secondary)
    }
    .frame(maxWidth: .infinity, maxHeight: .infinity)
  }

  private func errorView(_: String) -> some View {
    VStack(spacing: OmiSpacing.lg) {
      Image(systemName: "exclamationmark.triangle")
        .scaledFont(size: OmiType.hero)
        .foregroundColor(PageGlass.warning)

      Text("Failed to load conversations")
        .scaledFont(size: OmiType.subheading, weight: .medium)
        .foregroundColor(Ink.primary)

      Text("Check your connection and try again.")
        .scaledFont(size: OmiType.body)
        .foregroundColor(Ink.secondary)
        .multilineTextAlignment(.center)

      Button(action: onRefresh) {
        Text("Try Again")
          .scaledFont(size: OmiType.body, weight: .medium)
          .foregroundColor(Ink.primary)
          .padding(.horizontal, OmiSpacing.xl)
          .padding(.vertical, OmiSpacing.sm)
          .glassChip(isActive: true)
      }
      .buttonStyle(.plain)
    }
    .frame(maxWidth: .infinity, maxHeight: .infinity)
    .padding(OmiSpacing.section)
  }

  private var emptyView: some View {
    VStack(spacing: OmiSpacing.lg) {
      Image(systemName: "bubble.left.and.bubble.right")
        .scaledFont(size: 48)
        .foregroundColor(Ink.secondary)

      Text("No Conversations")
        .scaledFont(size: OmiType.heading, weight: .semibold)
        .foregroundColor(Ink.primary)

      Text("Start recording to capture your first conversation")
        .scaledFont(size: OmiType.body)
        .foregroundColor(Ink.secondary)
        .multilineTextAlignment(.center)
    }
    .frame(maxWidth: .infinity, maxHeight: .infinity)
    .padding(OmiSpacing.section)
  }

  private var conversationListContent: some View {
    let items = flatListItems
    return LazyVStack(alignment: .leading, spacing: OmiSpacing.md) {
      ForEach(items) { item in
        switch item {
        case .header(let key, let isFirst):
          Text(key)
            .scaledFont(size: OmiType.body, weight: .semibold)
            .foregroundColor(Ink.secondary)
            .padding(.top, isFirst ? 0 : OmiSpacing.lg)
            .padding(.bottom, OmiSpacing.xs)
        case .conversation(let conversation):
          ConversationRowView(
            conversation: conversation,
            onTap: { onSelect(conversation) },
            folders: folders,
            onMoveToFolder: onMoveToFolder,
            isCompactView: isCompactView,
            isMultiSelectMode: isMultiSelectMode,
            isSelected: selectedIds.contains(conversation.id),
            onToggleSelection: { onToggleSelection?(conversation.id) },
            appState: appState
          )
        }
      }
    }
    .padding(.horizontal, PagePanelVerticalRhythm.horizontalPadding)
    .padding(.top, PagePanelVerticalRhythm.contentGap)
    .padding(.bottom, PagePanelVerticalRhythm.contentBottomPadding)
    // Keyed on identity only: a finished capture slides into the list as one
    // row change rather than a repaint, and field updates stay animation-free.
    .omiAnimation(.easeInOut(duration: 0.25), value: conversations.map(\.id))
  }

  private var conversationList: some View {
    Group {
      if embedded {
        conversationListContent
      } else {
        ScrollView {
          conversationListContent
        }
        .refreshable {
          onRefresh()
        }
        .glassScrollFade()
      }
    }
  }
}

#if canImport(PreviewsMacros)
  #Preview {
    ConversationListView(
      conversations: [],
      isLoading: false,
      error: nil,
      folders: [],
      onSelect: { _ in },
      onRefresh: {},
      onMoveToFolder: { _, _ in },
      appState: AppState()
    )
    .frame(width: 400, height: 600)
    .background(Ink.surface)
  }
#endif
