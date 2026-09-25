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
  ///
  /// Grouped by the same date the row displays (`startedAt ?? createdAt`). Grouping by `createdAt`
  /// while the row printed `startedAt` put a conversation that started at 11:50 PM and saved after
  /// midnight under "Today" with a time from yesterday.
  private var flatListItems: [ListItem] {
    let calendar = Calendar.current
    let now = Date()

    var order: [Date] = []
    var groups: [Date: [ServerConversation]] = [:]
    // One row per recorded event: other devices' recordings stay reachable from its detail.
    for conversation in CaptureGroupPresentation.collapse(conversations) {
      let day = calendar.startOfDay(for: conversation.startedAt ?? conversation.createdAt)
      if groups[day] == nil { order.append(day) }
      groups[day, default: []].append(conversation)
    }

    var items: [ListItem] = []
    for (index, day) in order.sorted(by: >).enumerated() {
      guard let convos = groups[day] else { continue }
      items.append(.header(key: OmiDateFormat.dayHeader(day, now: now, calendar: calendar), isFirst: index == 0))
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
    GlassLoadingState(label: "Loading conversations…")
  }

  private func errorView(_: String) -> some View {
    GlassErrorState(
      title: "Couldn't Load Conversations",
      message: "Check your connection and try again.",
      retry: onRefresh
    )
  }

  private var emptyView: some View {
    GlassEmptyState(
      systemImage: "bubble.left.and.bubble.right",
      title: "No Conversations",
      message: "Start recording to capture your first conversation"
    )
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
