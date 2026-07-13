import SwiftUI
import OmiTheme

struct RecentConversationsWidget: View {
    let conversations: [ServerConversation]
    let folders: [Folder]
    let onViewAll: () -> Void
    let onMoveToFolder: (String, String?) async -> Void
    var appState: AppState

    var body: some View {
        VStack(alignment: .leading, spacing: OmiSpacing.md) {
            // Header
            HStack {
                Text("Recent Conversations")
                    .scaledFont(size: OmiType.subheading, weight: .semibold)
                    .foregroundColor(OmiColors.textPrimary)

                Spacer()

                Button(action: onViewAll) {
                    Text("View All")
                        .scaledFont(size: OmiType.caption, weight: .medium)
                        .foregroundColor(OmiColors.accent)
                }
                .buttonStyle(.plain)
            }

            if conversations.isEmpty {
                VStack(spacing: OmiSpacing.sm) {
                    Text("No conversations yet")
                        .scaledFont(size: OmiType.body)
                        .foregroundColor(OmiColors.textTertiary)
                }
                .frame(maxWidth: .infinity)
                .padding(.vertical, OmiSpacing.lg)
            } else {
                VStack(spacing: OmiSpacing.xxs) {
                    ForEach(conversations) { conversation in
                        ConversationRowView(
                            conversation: conversation,
                            onTap: onViewAll,
                            folders: folders,
                            onMoveToFolder: onMoveToFolder,
                            isCompactView: true,
                            appState: appState
                        )
                    }
                }
            }
        }
        .padding(OmiSpacing.xl)
        .background(
            RoundedRectangle(cornerRadius: OmiChrome.controlRadius)
                .fill(OmiColors.backgroundTertiary.opacity(0.5))
                .overlay(
                    RoundedRectangle(cornerRadius: OmiChrome.controlRadius)
                        .stroke(OmiColors.backgroundQuaternary.opacity(0.5), lineWidth: 1)
                )
        )
    }
}
