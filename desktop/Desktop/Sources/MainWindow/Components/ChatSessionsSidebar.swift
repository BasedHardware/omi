import SwiftUI

/// Sidebar showing chat sessions grouped by date
struct ChatSessionsSidebar: View {
    @ObservedObject var chatProvider: ChatProvider

    @State private var isTogglingStarredFilter = false

    private let sidebarWidth: CGFloat = 220

    var body: some View {
        VStack(spacing: 0) {
            // New Chat button, starred filter, and search
            VStack(spacing: 8) {
                newChatButton
                HStack(spacing: 8) {
                    starredFilterButton
                    Spacer()
                }
                searchField
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 12)

            Divider()
                .background(OmiColors.backgroundTertiary)

            // Sessions list
            if chatProvider.isLoadingSessions {
                loadingView
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
            HStack(spacing: 8) {
                Image(systemName: "plus.circle.fill")
                    .scaledFont(size: 16)

                Text("New Chat")
                    .scaledFont(size: 14, weight: .medium)

                Spacer()
            }
            .foregroundColor(OmiColors.purplePrimary)
            .padding(.horizontal, 12)
            .padding(.vertical, 10)
            .background(OmiColors.backgroundTertiary)
            .cornerRadius(10)
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
            HStack(spacing: 6) {
                if isTogglingStarredFilter {
                    ProgressView()
                        .scaleEffect(0.5)
                        .frame(width: 12, height: 12)
                } else {
                    Image(systemName: chatProvider.showStarredOnly ? "star.fill" : "star")
                        .scaledFont(size: 12)
                }
                Text("Starred")
                    .scaledFont(size: 12, weight: .medium)
                Spacer()
            }
            .foregroundColor(chatProvider.showStarredOnly ? OmiColors.amber : OmiColors.textSecondary)
            .padding(.horizontal, 12)
            .padding(.vertical, 8)
            .background(
                RoundedRectangle(cornerRadius: 8)
                    .fill(chatProvider.showStarredOnly ? OmiColors.amber.opacity(0.15) : OmiColors.backgroundTertiary.opacity(0.6))
            )
            .overlay(
                RoundedRectangle(cornerRadius: 8)
                    .stroke(chatProvider.showStarredOnly ? OmiColors.amber.opacity(0.4) : Color.clear, lineWidth: 1)
            )
        }
        .buttonStyle(.plain)
        .disabled(isTogglingStarredFilter)
    }

    // MARK: - Search Field

    private var searchField: some View {
        HStack(spacing: 8) {
            Image(systemName: "magnifyingglass")
                .scaledFont(size: 12)
                .foregroundColor(OmiColors.textTertiary)

            TextField("Search chats...", text: $chatProvider.searchQuery)
                .textFieldStyle(.plain)
                .scaledFont(size: 13)
                .foregroundColor(OmiColors.textPrimary)

            if !chatProvider.searchQuery.isEmpty {
                Button(action: {
                    chatProvider.searchQuery = ""
                }) {
                    Image(systemName: "xmark.circle.fill")
                        .scaledFont(size: 12)
                        .foregroundColor(OmiColors.textTertiary)
                }
                .buttonStyle(.plain)
            }
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 8)
        .background(OmiColors.backgroundTertiary.opacity(0.6))
        .cornerRadius(8)
    }

    // MARK: - Sessions List

    private var sessionsList: some View {
        ScrollView {
            LazyVStack(alignment: .leading, spacing: 0) {
                ForEach(chatProvider.groupedSessions, id: \.0) { group, sessions in
                    // Group header
                    Text(group)
                        .scaledFont(size: 11, weight: .semibold)
                        .foregroundColor(OmiColors.textTertiary)
                        .padding(.horizontal, 16)
                        .padding(.top, 16)
                        .padding(.bottom, 8)

                    // Sessions in group
                    ForEach(sessions) { session in
                        SessionRow(
                            session: session,
                            isSelected: chatProvider.currentSession?.id == session.id,
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
            .padding(.bottom, 16)
        }
    }

    // MARK: - Loading & Empty States

    private var loadingView: some View {
        VStack {
            Spacer()
            ProgressView()
                .scaleEffect(0.8)
            Text("Loading chats...")
                .scaledFont(size: 12)
                .foregroundColor(OmiColors.textTertiary)
                .padding(.top, 8)
            Spacer()
        }
    }

    private var emptyStateView: some View {
        VStack(spacing: 12) {
            Spacer()
            Image(systemName: emptyStateIcon)
                .scaledFont(size: 32)
                .foregroundColor(OmiColors.textTertiary)

            Text(emptyStateTitle)
                .scaledFont(size: 14, weight: .medium)
                .foregroundColor(OmiColors.textSecondary)

            Text(emptyStateSubtitle)
                .scaledFont(size: 12)
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
            HStack(spacing: 8) {
                // Star indicator
                if session.starred {
                    Image(systemName: "star.fill")
                        .scaledFont(size: 10)
                        .foregroundColor(.yellow)
                }

                VStack(alignment: .leading, spacing: 2) {
                    if isEditing {
                        TextField("Chat title", text: $editedTitle)
                            .textFieldStyle(.plain)
                            .scaledFont(size: 13, weight: isSelected ? .semibold : .regular)
                            .foregroundColor(isSelected ? OmiColors.purplePrimary : OmiColors.textPrimary)
                            .focused($isTitleFocused)
                            .onSubmit {
                                saveTitle()
                            }
                            .onExitCommand {
                                cancelEditing()
                            }
                    } else {
                        Text(session.title)
                            .scaledFont(size: 13, weight: isSelected ? .semibold : .regular)
                            .foregroundColor(isSelected ? OmiColors.purplePrimary : OmiColors.textPrimary)
                            .lineLimit(1)
                    }

                    if let preview = session.preview, !preview.isEmpty, !isEditing {
                        Text(preview)
                            .scaledFont(size: 11)
                            .foregroundColor(OmiColors.textTertiary)
                            .lineLimit(1)
                    }
                }

                Spacer()

                // Hover actions
                if isHovering && !isEditing {
                    HStack(spacing: 4) {
                        // Rename button
                        Button(action: startEditing) {
                            Image(systemName: "pencil")
                                .scaledFont(size: 11)
                                .foregroundColor(OmiColors.textTertiary)
                        }
                        .buttonStyle(.plain)

                        // Star/unstar button
                        Button(action: onToggleStar) {
                            Image(systemName: session.starred ? "star.fill" : "star")
                                .scaledFont(size: 11)
                                .foregroundColor(session.starred ? .yellow : OmiColors.textTertiary)
                        }
                        .buttonStyle(.plain)

                        // Delete button
                        Button(action: { showDeleteConfirm = true }) {
                            Image(systemName: "trash")
                                .scaledFont(size: 11)
                                .foregroundColor(OmiColors.textTertiary)
                        }
                        .buttonStyle(.plain)
                    }
                }
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 8)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(isSelected ? OmiColors.backgroundTertiary : (isHovering ? OmiColors.backgroundTertiary.opacity(0.5) : Color.clear))
            .contentShape(Rectangle())
            .cornerRadius(8)
        }
        .buttonStyle(.plain)
        .padding(.horizontal, 8)
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

#Preview {
    ChatSessionsSidebar(chatProvider: ChatProvider())
        .frame(height: 500)
}
