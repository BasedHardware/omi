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

    /// Group conversations by date
    private var groupedConversations: [(String, [ServerConversation])] {
        let calendar = Calendar.current
        let today = calendar.startOfDay(for: Date())
        let yesterday = calendar.date(byAdding: .day, value: -1, to: today)!

        var groups: [String: [ServerConversation]] = [:]

        for conversation in conversations {
            let conversationDate = calendar.startOfDay(for: conversation.createdAt)
            let groupKey: String

            if conversationDate == today {
                groupKey = "Today"
            } else if conversationDate == yesterday {
                groupKey = "Yesterday"
            } else {
                let formatter = DateFormatter()
                formatter.dateFormat = "MMM d, yyyy"
                groupKey = formatter.string(from: conversation.createdAt)
            }

            if groups[groupKey] == nil {
                groups[groupKey] = []
            }
            groups[groupKey]?.append(conversation)
        }

        // Sort groups: Today first, then Yesterday, then by date descending
        let sortedKeys = groups.keys.sorted { key1, key2 in
            if key1 == "Today" { return true }
            if key2 == "Today" { return false }
            if key1 == "Yesterday" { return true }
            if key2 == "Yesterday" { return false }

            // Parse dates for comparison
            let formatter = DateFormatter()
            formatter.dateFormat = "MMM d, yyyy"
            let date1 = formatter.date(from: key1) ?? Date.distantPast
            let date2 = formatter.date(from: key2) ?? Date.distantPast
            return date1 > date2
        }

        return sortedKeys.compactMap { key in
            guard let convos = groups[key] else { return nil }
            return (key, convos)
        }
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
        VStack(spacing: 16) {
            ProgressView()
                .scaleEffect(1.2)
                .tint(OmiColors.purplePrimary)

            Text("Loading conversations...")
                .scaledFont(size: 14)
                .foregroundColor(OmiColors.textTertiary)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    private func errorView(_ error: String) -> some View {
        VStack(spacing: 16) {
            Image(systemName: "exclamationmark.triangle")
                .scaledFont(size: 40)
                .foregroundColor(OmiColors.warning)

            Text("Failed to load conversations")
                .scaledFont(size: 16, weight: .medium)
                .foregroundColor(OmiColors.textPrimary)

            Text(error)
                .scaledFont(size: 14)
                .foregroundColor(OmiColors.textTertiary)
                .multilineTextAlignment(.center)

            Button(action: onRefresh) {
                Text("Try Again")
                    .scaledFont(size: 14, weight: .medium)
                    .foregroundColor(OmiColors.textPrimary)
                    .padding(.horizontal, 20)
                    .padding(.vertical, 10)
                    .background(
                        RoundedRectangle(cornerRadius: 8)
                            .fill(OmiColors.purplePrimary)
                    )
            }
            .buttonStyle(.plain)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .padding(32)
    }

    private var emptyView: some View {
        VStack(spacing: 16) {
            Image(systemName: "bubble.left.and.bubble.right")
                .scaledFont(size: 48)
                .foregroundColor(OmiColors.textTertiary)

            Text("No Conversations")
                .scaledFont(size: 18, weight: .semibold)
                .foregroundColor(OmiColors.textPrimary)

            Text("Start recording to capture your first conversation")
                .scaledFont(size: 14)
                .foregroundColor(OmiColors.textTertiary)
                .multilineTextAlignment(.center)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .padding(32)
    }

    private var conversationListContent: some View {
        LazyVStack(alignment: .leading, spacing: 8) {
            ForEach(groupedConversations, id: \.0) { group, convos in
                // Date header
                Text(group)
                    .scaledFont(size: 12, weight: .semibold)
                    .foregroundColor(OmiColors.textTertiary)
                    .padding(.top, group == groupedConversations.first?.0 ? 0 : 16)
                    .padding(.bottom, 8)

                // Conversations in this group
                ForEach(convos) { conversation in
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
        .padding(16)
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
            }
        }
    }
}

#Preview {
    ConversationListView(
        conversations: [],
        isLoading: false,
        error: nil,
        folders: [],
        onSelect: { _ in },
        onRefresh: { },
        onMoveToFolder: { _, _ in },
        appState: AppState()
    )
    .frame(width: 400, height: 600)
    .background(OmiColors.backgroundSecondary)
}
