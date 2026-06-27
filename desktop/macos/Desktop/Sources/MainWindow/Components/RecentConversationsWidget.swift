import SwiftUI

struct RecentConversationsWidget: View {
    let conversations: [ServerConversation]
    let folders: [Folder]
    let onViewAll: () -> Void
    let onMoveToFolder: (String, String?) async -> Void
    var appState: AppState

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            // Header
            HStack {
                Text("Recent Conversations")
                    .scaledFont(size: 16, weight: .semibold)
                    .foregroundColor(OmiColors.textPrimary)

                Spacer()

                Button(action: onViewAll) {
                    Text("View All")
                        .scaledFont(size: 12, weight: .medium)
                        .foregroundColor(OmiColors.purplePrimary)
                }
                .buttonStyle(.plain)
            }

            if conversations.isEmpty {
                VStack(spacing: 8) {
                    Text("No conversations yet")
                        .scaledFont(size: 13)
                        .foregroundColor(OmiColors.textTertiary)
                }
                .frame(maxWidth: .infinity)
                .padding(.vertical, 16)
            } else {
                VStack(spacing: 4) {
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
        .padding(20)
        .background(
            RoundedRectangle(cornerRadius: 16)
                .fill(OmiColors.backgroundTertiary.opacity(0.5))
                .overlay(
                    RoundedRectangle(cornerRadius: 16)
                        .stroke(OmiColors.backgroundQuaternary.opacity(0.5), lineWidth: 1)
                )
        )
    }
}
