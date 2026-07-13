import SwiftUI
import OmiTheme

/// Sidebar showing chat sessions grouped by date
struct ChatSessionsSidebar: View {
    @ObservedObject var chatProvider: ChatProvider

    @State private var isTogglingStarredFilter = false

    private let sidebarWidth: CGFloat = 220

    var body: some View {
        VStack(spacing: 0) {
            // New Chat button, starred filter, and search
            VStack(spacing: OmiSpacing.sm) {
                newChatButton
                HStack(spacing: OmiSpacing.sm) {
                    starredFilterButton
                    Spacer()
                }
                searchField
            }
            .padding(.horizontal, OmiSpacing.md)
            .padding(.vertical, OmiSpacing.md)

            Divider()
                .background(OmiColors.backgroundTertiary)

            // Sessions list
            if chatProvider.isLoadingSessions {
                loadingView
            } else if let error = chatProvider.sessionsLoadError {
                VStack(spacing: OmiSpacing.md) {
                    Image(systemName: "exclamationmark.triangle")
                        .scaledFont(size: 24)
                        .foregroundColor(OmiColors.warning)

                    Text("Failed to load chats")
                        .scaledFont(size: OmiType.body, weight: .medium)
                        .foregroundColor(OmiColors.textPrimary)

                    Text(error)
                        .scaledFont(size: OmiType.caption)
                        .foregroundColor(OmiColors.textTertiary)
                        .multilineTextAlignment(.center)
                        .lineLimit(3)

                    Button(action: {
                        Task { await chatProvider.retryLoad() }
                    }) {
                        Text("Try Again")
                            .scaledFont(size: OmiType.caption, weight: .medium)
                            .foregroundColor(OmiColors.backgroundPrimary)
                            .padding(.horizontal, OmiSpacing.lg)
                            .padding(.vertical, OmiSpacing.sm)
                            .background(
                                RoundedRectangle(cornerRadius: OmiChrome.badgeRadius)
                                    .fill(OmiColors.accent)
                            )
                    }
                    .buttonStyle(.plain)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                .padding(OmiSpacing.lg)
            } else if chatProvider.filteredSessions.isEmpty {
                emptyStateView
            } else {
                sessionsList
            }
        }
        .frame(width: sidebarWidth)
        .background(OmiColors.backgroundSecondary)
    }

    // MARK: - New Chat Button

    private var newChatButton: some View {
        Button(action: {
            Task {
                _ = await chatProvider.createNewSession()
            }
        }) {
            HStack(spacing: OmiSpacing.sm) {
                Image(systemName: "plus.circle.fill")
                    .scaledFont(size: OmiType.subheading)

                Text("New Chat")
                    .scaledFont(size: OmiType.body, weight: .medium)

                Spacer()
            }
            .foregroundColor(OmiColors.accent)
            .padding(.horizontal, OmiSpacing.md)
            .padding(.vertical, OmiSpacing.sm)
            .background(OmiColors.backgroundTertiary)
            .cornerRadius(OmiChrome.smallControlRadius)
        }
        .buttonStyle(.plain)
    }

    // MARK: - Starred Filter Button

    private var starredFilterButton: some View {
        Button(action: {
            Task {
                isTogglingStarredFilter = true
                await chatProvider.toggleStarredFilter()
                isTogglingStarredFilter = false
            }
        }) {
            HStack(spacing: OmiSpacing.xs) {
                if isTogglingStarredFilter {
                    ProgressView()
                        .scaleEffect(0.5)
                        .frame(width: 12, height: 12)
                } else {
                    Image(systemName: chatProvider.showStarredOnly ? "star.fill" : "star")
                        .scaledFont(size: OmiType.caption)
                }
                Text("Starred")
                    .scaledFont(size: OmiType.caption, weight: .medium)
                Spacer()
            }
            .foregroundColor(chatProvider.showStarredOnly ? OmiColors.amber : OmiColors.textSecondary)
            .padding(.horizontal, OmiSpacing.md)
            .padding(.vertical, OmiSpacing.sm)
            .background(
                RoundedRectangle(cornerRadius: OmiChrome.elementRadius)
                    .fill(chatProvider.showStarredOnly ? OmiColors.amber.opacity(0.15) : OmiColors.backgroundTertiary.opacity(0.6))
            )
            .overlay(
                RoundedRectangle(cornerRadius: OmiChrome.elementRadius)
                    .stroke(chatProvider.showStarredOnly ? OmiColors.amber.opacity(0.4) : Color.clear, lineWidth: 1)
            )
        }
        .buttonStyle(.plain)
        .disabled(isTogglingStarredFilter)
    }

    // MARK: - Search Field

    private var searchField: some View {
        HStack(spacing: OmiSpacing.sm) {
            Image(systemName: "magnifyingglass")
                .scaledFont(size: OmiType.caption)
                .foregroundColor(OmiColors.textTertiary)

            TextField("Search chats...", text: $chatProvider.searchQuery)
                .textFieldStyle(.plain)
                .scaledFont(size: OmiType.body)
                .foregroundColor(OmiColors.textPrimary)

            if !chatProvider.searchQuery.isEmpty {
                Button(action: {
                    chatProvider.searchQuery = ""
                }) {
                    Image(systemName: "xmark.circle.fill")
                        .scaledFont(size: OmiType.caption)
                        .foregroundColor(OmiColors.textTertiary)
                }
                .buttonStyle(.plain)
            }
        }
        .padding(.horizontal, OmiSpacing.sm)
        .padding(.vertical, OmiSpacing.sm)
        .background(OmiColors.backgroundTertiary.opacity(0.6))
        .cornerRadius(OmiChrome.elementRadius)
    }

    // MARK: - Sessions List

    private var sessionsList: some View {
        ScrollView {
            LazyVStack(alignment: .leading, spacing: 0) {
                ForEach(chatProvider.groupedSessions, id: \.0) { group, sessions in
                    // Group header
                    Text(group)
                        .scaledFont(size: OmiType.caption, weight: .semibold)
                        .foregroundColor(OmiColors.textTertiary)
                        .padding(.horizontal, OmiSpacing.lg)
                        .padding(.top, OmiSpacing.lg)
                        .padding(.bottom, OmiSpacing.sm)

                    // Sessions in group
                    ForEach(sessions) { session in
                        SessionRow(
                            session: session,
                            isSelected: chatProvider.currentSession?.id == session.id,
                            isDeleting: chatProvider.deletingSessionIds.contains(session.id),
                            onSelect: {
                                Task {
                                    await chatProvider.selectSession(session)
                                }
                            },
                            onDelete: {
                                Task {
                                    await chatProvider.deleteSession(session)
                                }
                            },
                            onToggleStar: {
                                Task {
                                    await chatProvider.toggleStarred(session)
                                }
                            },
                            onRename: { newTitle in
                                Task {
                                    await chatProvider.updateSessionTitle(session, title: newTitle)
                                }
                            }
                        )
                    }
                }
            }
            .padding(.bottom, OmiSpacing.lg)
        }
    }

    // MARK: - Loading & Empty States

    private var loadingView: some View {
        VStack {
            Spacer()
            ProgressView()
                .scaleEffect(0.8)
            Text("Loading chats...")
                .scaledFont(size: OmiType.caption)
                .foregroundColor(OmiColors.textTertiary)
                .padding(.top, OmiSpacing.sm)
            Spacer()
        }
    }

    private var emptyStateView: some View {
        VStack(spacing: OmiSpacing.md) {
            Spacer()
            Image(systemName: emptyStateIcon)
                .scaledFont(size: 32)
                .foregroundColor(OmiColors.textTertiary)

            Text(emptyStateTitle)
                .scaledFont(size: OmiType.body, weight: .medium)
                .foregroundColor(OmiColors.textSecondary)

            Text(emptyStateSubtitle)
                .scaledFont(size: OmiType.caption)
                .foregroundColor(OmiColors.textTertiary)
            Spacer()
        }
        .padding()
    }

    private var emptyStateIcon: String {
        if !chatProvider.searchQuery.isEmpty {
            return "magnifyingglass"
        } else if chatProvider.showStarredOnly {
            return "star"
        } else {
            return "bubble.left.and.bubble.right"
        }
    }

    private var emptyStateTitle: String {
        if !chatProvider.searchQuery.isEmpty {
            return "No results"
        } else if chatProvider.showStarredOnly {
            return "No starred chats"
        } else {
            return "No chats yet"
        }
    }

    private var emptyStateSubtitle: String {
        if !chatProvider.searchQuery.isEmpty {
            return "Try a different search term"
        } else if chatProvider.showStarredOnly {
            return "Star a chat to see it here"
        } else {
            return "Start a conversation"
        }
    }
}

// MARK: - Session Row

struct SessionRow: View {
    let session: ChatSession
    let isSelected: Bool
    var isDeleting: Bool = false
    let onSelect: () -> Void
    let onDelete: () -> Void
    let onToggleStar: () -> Void
    let onRename: (String) -> Void

    @State private var isHovering = false
    @State private var showDeleteConfirm = false
    @State private var isEditing = false
    @State private var editedTitle = ""
    @FocusState private var isTitleFocused: Bool

    var body: some View {
        Button(action: {
            if !isEditing {
                onSelect()
            }
        }) {
            HStack(spacing: OmiSpacing.sm) {
                // Star indicator
                if session.starred {
                    Image(systemName: "star.fill")
                        .scaledFont(size: OmiType.micro)
                        .foregroundColor(.yellow)
                }

                VStack(alignment: .leading, spacing: OmiSpacing.hairline) {
                    if isEditing {
                        TextField("Chat title", text: $editedTitle)
                            .textFieldStyle(.plain)
                            .scaledFont(size: OmiType.body, weight: isSelected ? .semibold : .regular)
                            .foregroundColor(isSelected ? OmiColors.accent : OmiColors.textPrimary)
                            .focused($isTitleFocused)
                            .onSubmit {
                                saveTitle()
                            }
                            .onExitCommand {
                                cancelEditing()
                            }
                    } else {
                        Text(session.title)
                            .scaledFont(size: OmiType.body, weight: isSelected ? .semibold : .regular)
                            .foregroundColor(isSelected ? OmiColors.accent : OmiColors.textPrimary)
                            .lineLimit(1)
                    }

                    if let preview = session.preview, !preview.isEmpty, !isEditing,
                       !preview.hasPrefix("[Protected"), !preview.hasPrefix("[Encrypted") {
                        Text(preview)
                            .scaledFont(size: OmiType.caption)
                            .foregroundColor(OmiColors.textTertiary)
                            .lineLimit(1)
                    }
                }

                Spacer()

                if isDeleting {
                    ProgressView()
                        .scaleEffect(0.5)
                        .frame(width: 14, height: 14)
                }

                // Hover actions
                if isHovering && !isEditing && !isDeleting {
                    HStack(spacing: OmiSpacing.xxs) {
                        // Rename button
                        Button(action: startEditing) {
                            Image(systemName: "pencil")
                                .scaledFont(size: OmiType.caption)
                                .foregroundColor(OmiColors.textTertiary)
                        }
                        .buttonStyle(.plain)

                        // Star/unstar button
                        Button(action: onToggleStar) {
                            Image(systemName: session.starred ? "star.fill" : "star")
                                .scaledFont(size: OmiType.caption)
                                .foregroundColor(session.starred ? .yellow : OmiColors.textTertiary)
                        }
                        .buttonStyle(.plain)

                        // Delete button
                        Button(action: { showDeleteConfirm = true }) {
                            Image(systemName: "trash")
                                .scaledFont(size: OmiType.caption)
                                .foregroundColor(OmiColors.textTertiary)
                        }
                        .buttonStyle(.plain)
                    }
                }
            }
            .padding(.horizontal, OmiSpacing.md)
            .padding(.vertical, OmiSpacing.sm)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(isSelected ? OmiColors.backgroundTertiary : (isHovering ? OmiColors.backgroundTertiary.opacity(0.5) : Color.clear))
            .contentShape(Rectangle())
            .cornerRadius(OmiChrome.elementRadius)
        }
        .buttonStyle(.plain)
        .padding(.horizontal, OmiSpacing.sm)
        .onHover { isHovering = $0 }
        .onTapGesture(count: 2) {
            startEditing()
        }
        .alert("Delete Chat?", isPresented: $showDeleteConfirm) {
            Button("Cancel", role: .cancel) {}
            Button("Delete", role: .destructive) {
                onDelete()
            }
        } message: {
            Text("This will permanently delete this chat and all its messages.")
        }
    }

    private func startEditing() {
        editedTitle = session.title
        isEditing = true
        isTitleFocused = true
    }

    private func saveTitle() {
        let trimmed = editedTitle.trimmingCharacters(in: .whitespacesAndNewlines)
        if !trimmed.isEmpty && trimmed != session.title {
            onRename(trimmed)
        }
        isEditing = false
    }

    private func cancelEditing() {
        isEditing = false
        editedTitle = session.title
    }
}

#if canImport(PreviewsMacros)
#Preview {
    ChatSessionsSidebar(chatProvider: ChatProvider())
        .frame(height: 500)
}
#endif
