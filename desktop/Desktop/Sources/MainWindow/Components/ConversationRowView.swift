import SwiftUI
import AppKit

/// Row view for a conversation in the list
struct ConversationRowView: View {
    let conversation: ServerConversation
    let onTap: () -> Void
    let folders: [Folder]
    let onMoveToFolder: (String, String?) async -> Void

    // View mode
    var isCompactView: Bool = true

    // Multi-select support
    var isMultiSelectMode: Bool = false
    var isSelected: Bool = false
    var onToggleSelection: (() -> Void)? = nil

    var appState: AppState
    @State private var isStarring = false
    @State private var isHovering = false

    // Context menu action states
    @State private var showEditDialog = false
    @State private var showDeleteConfirmation = false
    @State private var editedTitle: String = ""
    @State private var isDeleting = false
    @State private var isUpdatingTitle = false
    @State private var isCopyingLink = false

    /// The timestamp to display (prefer startedAt, fall back to createdAt)
    private var displayDate: Date {
        conversation.startedAt ?? conversation.createdAt
    }

    /// Check if conversation was created less than 1 minute ago (newly added)
    private var isNewlyCreated: Bool {
        Date().timeIntervalSince(conversation.createdAt) < 60
    }

    private static let timeFormatter: DateFormatter = {
        let f = DateFormatter()
        f.dateFormat = "h:mm a"
        return f
    }()
    private static let yesterdayFormatter: DateFormatter = {
        let f = DateFormatter()
        f.dateFormat = "'Yesterday,' h:mm a"
        return f
    }()
    private static let sameYearFormatter: DateFormatter = {
        let f = DateFormatter()
        f.dateFormat = "MMM d, h:mm a"
        return f
    }()
    private static let otherYearFormatter: DateFormatter = {
        let f = DateFormatter()
        f.dateFormat = "MMM d, yyyy, h:mm a"
        return f
    }()

    /// Format timestamp (e.g., "10:43 AM" for today, "Jan 29, 10:43 AM" for other days)
    private var formattedTimestamp: String {
        let calendar = Calendar.current
        let formatter: DateFormatter

        if calendar.isDateInToday(displayDate) {
            formatter = Self.timeFormatter
        } else if calendar.isDateInYesterday(displayDate) {
            formatter = Self.yesterdayFormatter
        } else if calendar.isDate(displayDate, equalTo: Date(), toGranularity: .year) {
            formatter = Self.sameYearFormatter
        } else {
            formatter = Self.otherYearFormatter
        }

        return formatter.string(from: displayDate)
    }

    /// Folder name for inline display
    private var folderName: String? {
        guard let folderId = conversation.folderId else { return nil }
        return folders.first(where: { $0.id == folderId })?.name
    }

    /// Label for the conversation source
    private var sourceLabel: String {
        switch conversation.source {
        case .desktop: return "Desktop"
        case .omi: return "Omi"
        case .phone: return "Phone"
        case .appleWatch: return "Watch"
        case .workflow: return "Workflow"
        case .screenpipe: return "Screenpipe"
        case .friend, .friendCom: return "Friend"
        case .openglass: return "OpenGlass"
        case .frame: return "Frame"
        case .bee: return "Bee"
        case .limitless: return "Limitless"
        case .plaud: return "Plaud"
        default: return "Unknown"
        }
    }

    private func toggleStar() async {
        guard !isStarring else { return }
        isStarring = true
        let newStarred = !conversation.starred

        do {
            try await APIClient.shared.setConversationStarred(id: conversation.id, starred: newStarred)

            // Sync to local SQLite cache so reload doesn't revert the change
            try await TranscriptionStorage.shared.updateStarredByBackendId(conversation.id, starred: newStarred)

            await MainActor.run {
                appState.setConversationStarred(conversation.id, starred: newStarred)
            }
        } catch {
            log("Failed to update starred status: \(error)")
        }

        isStarring = false
    }

    // MARK: - Context Menu Actions

    private func copyTranscript() {
        let pasteboard = NSPasteboard.general
        pasteboard.clearContents()
        pasteboard.setString(conversation.transcript, forType: .string)
        log("Copied transcript to clipboard")
    }

    private func copyLink() async {
        guard !isCopyingLink else { return }
        isCopyingLink = true

        do {
            // First, make the conversation public/shared so the link works
            try await APIClient.shared.setConversationVisibility(id: conversation.id, visibility: "shared")

            // Then copy the link
            let link = "https://h.omi.me/conversations/\(conversation.id)"
            let pasteboard = NSPasteboard.general
            pasteboard.clearContents()
            pasteboard.setString(link, forType: .string)
            log("Copied conversation link to clipboard (visibility set to shared)")
        } catch {
            log("Failed to set conversation visibility: \(error)")
            // Still copy the link even if visibility fails - user might have shared it before
            let link = "https://h.omi.me/conversations/\(conversation.id)"
            let pasteboard = NSPasteboard.general
            pasteboard.clearContents()
            pasteboard.setString(link, forType: .string)
            log("Copied conversation link to clipboard (visibility API failed)")
        }

        isCopyingLink = false
    }

    private func deleteConversation() async {
        guard !isDeleting else { return }
        isDeleting = true

        // Soft-delete in SQLite immediately so reload doesn't restore it
        do {
            try await TranscriptionStorage.shared.deleteByBackendId(conversation.id)
        } catch {
            log("Failed to soft-delete conversation locally: \(error)")
        }

        do {
            try await APIClient.shared.deleteConversation(id: conversation.id)
            await MainActor.run {
                appState.deleteConversationLocally(conversation.id)
            }
            log("Deleted conversation \(conversation.id)")
        } catch {
            log("Failed to delete conversation: \(error)")
        }

        isDeleting = false
    }

    private func updateTitle() async {
        guard !isUpdatingTitle, !editedTitle.isEmpty else { return }
        isUpdatingTitle = true

        do {
            try await APIClient.shared.updateConversationTitle(id: conversation.id, title: editedTitle)

            // Sync to local SQLite cache so reload doesn't revert the change
            try await TranscriptionStorage.shared.updateTitleByBackendId(conversation.id, title: editedTitle)

            await MainActor.run {
                appState.updateConversationTitle(conversation.id, title: editedTitle)
            }
            log("Updated conversation title to: \(editedTitle)")
        } catch {
            log("Failed to update title: \(error)")
        }

        isUpdatingTitle = false
    }

    // MARK: - Inline Action Buttons

    private var inlineActionButtons: some View {
        HStack(spacing: 4) {
            // Edit title
            Button(action: {
                editedTitle = conversation.title
                showEditDialog = true
            }) {
                Image(systemName: "pencil")
                    .scaledFont(size: 11)
                    .foregroundColor(OmiColors.textTertiary)
                    .frame(width: 22, height: 22)
                    .background(Circle().fill(OmiColors.backgroundSecondary))
            }
            .buttonStyle(.plain)
            .help("Edit title")

            // Copy link
            Button(action: { Task { await copyLink() } }) {
                Image(systemName: isCopyingLink ? "arrow.triangle.2.circlepath" : "link")
                    .scaledFont(size: 11)
                    .foregroundColor(OmiColors.textTertiary)
                    .frame(width: 22, height: 22)
                    .background(Circle().fill(OmiColors.backgroundSecondary))
            }
            .buttonStyle(.plain)
            .disabled(isCopyingLink)
            .help("Copy link")

            // Move to folder (if folders exist)
            if !folders.isEmpty {
                Menu {
                    if conversation.folderId != nil {
                        Button(action: { Task { await onMoveToFolder(conversation.id, nil) } }) {
                            Label("Remove from Folder", systemImage: "folder.badge.minus")
                        }
                        Divider()
                    }
                    ForEach(folders) { folder in
                        Button(action: { Task { await onMoveToFolder(conversation.id, folder.id) } }) {
                            HStack {
                                Text(folder.name)
                                if conversation.folderId == folder.id {
                                    Image(systemName: "checkmark")
                                }
                            }
                        }
                        .disabled(conversation.folderId == folder.id)
                    }
                } label: {
                    Image(systemName: conversation.folderId != nil ? "folder.fill" : "folder")
                        .scaledFont(size: 11)
                        .foregroundColor(conversation.folderId != nil ? .white : OmiColors.textTertiary)
                        .frame(width: 22, height: 22)
                        .background(Circle().fill(OmiColors.backgroundSecondary))
                }
                .menuStyle(.borderlessButton)
                .frame(width: 22)
                .help("Move to folder")
            }

            // Delete
            Button(action: { showDeleteConfirmation = true }) {
                Image(systemName: "trash")
                    .scaledFont(size: 11)
                    .foregroundColor(OmiColors.error.opacity(0.8))
                    .frame(width: 22, height: 22)
                    .background(Circle().fill(OmiColors.backgroundSecondary))
            }
            .buttonStyle(.plain)
            .help("Delete")
        }
    }

    // MARK: - Compact Row (single line)

    private var compactRowContent: some View {
        HStack(spacing: 8) {
            // Checkbox for multi-select mode
            if isMultiSelectMode {
                Image(systemName: isSelected ? "checkmark.circle.fill" : "circle")
                    .scaledFont(size: 18)
                    .foregroundColor(isSelected ? OmiColors.purplePrimary : OmiColors.textTertiary)
            }

            // Emoji
            Text(conversation.structured.emoji.isEmpty ? "💬" : conversation.structured.emoji)
                .scaledFont(size: 16)
                .frame(width: 28, height: 28)
                .background(
                    RoundedRectangle(cornerRadius: 8)
                        .fill(OmiColors.backgroundTertiary)
                )

            // Title
            Text(conversation.title)
                .scaledFont(size: 14, weight: .medium)
                .foregroundColor(OmiColors.textPrimary)
                .lineLimit(1)

            // New badge
            if isNewlyCreated {
                NewBadge()
            }

            // Inline action buttons (show on hover)
            if isHovering && !isMultiSelectMode {
                inlineActionButtons
                    .transition(.opacity)
            }

            Spacer()

            // Star button
            Button(action: {
                Task { await toggleStar() }
            }) {
                Image(systemName: conversation.starred ? "star.fill" : "star")
                    .scaledFont(size: 12)
                    .foregroundColor(conversation.starred ? OmiColors.amber : OmiColors.textTertiary)
                    .opacity(isStarring ? 0.5 : 1.0)
            }
            .buttonStyle(.plain)

            // Source label (hide on hover to make room)
            if !isHovering {
                Text(sourceLabel)
                    .scaledFont(size: 10, weight: .medium)
                    .foregroundColor(OmiColors.textQuaternary)
            }

            // Folder label
            if !isHovering, let folderName = folderName {
                Text(folderName)
                    .scaledFont(size: 10, weight: .medium)
                    .foregroundColor(OmiColors.textQuaternary)
                    .lineLimit(1)
            }

            // Time
            Text(formattedTimestamp)
                .scaledFont(size: 12)
                .foregroundColor(OmiColors.textTertiary)

            // Duration (hide on hover to make room)
            if !isHovering {
                Text(conversation.formattedDuration)
                    .scaledFont(size: 11)
                    .foregroundColor(OmiColors.textQuaternary)
            }
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 12)
        .background(
            RoundedRectangle(cornerRadius: 8)
                .fill(isSelected ? OmiColors.purplePrimary.opacity(0.2) : (isHovering ? OmiColors.backgroundTertiary : (isNewlyCreated ? OmiColors.purplePrimary.opacity(0.15) : OmiColors.backgroundSecondary)))
        )
        .overlay(
            RoundedRectangle(cornerRadius: 8)
                .stroke(isSelected ? OmiColors.purplePrimary.opacity(0.5) : Color.clear, lineWidth: 2)
        )
        .contentShape(Rectangle())
    }

    // MARK: - Expanded Row (title + overview)

    private var expandedRowContent: some View {
        HStack(spacing: 12) {
            // Checkbox for multi-select mode
            if isMultiSelectMode {
                Image(systemName: isSelected ? "checkmark.circle.fill" : "circle")
                    .scaledFont(size: 20)
                    .foregroundColor(isSelected ? OmiColors.purplePrimary : OmiColors.textTertiary)
            }

            // Emoji, Title, and overview
            VStack(alignment: .leading, spacing: 4) {
                HStack(spacing: 8) {
                    Text(conversation.title)
                        .scaledFont(size: 15, weight: .medium)
                        .foregroundColor(OmiColors.textPrimary)
                        .lineLimit(1)

                    // New badge
                    if isNewlyCreated {
                        NewBadge()
                    }

                    // Inline action buttons (show on hover)
                    if isHovering && !isMultiSelectMode {
                        inlineActionButtons
                            .transition(.opacity)
                    }

                    if conversation.structured.title.isEmpty && !isHovering {
                        Text("(\(conversation.id.prefix(8))...)")
                            .scaledFont(size: 11, design: .monospaced)
                            .foregroundColor(OmiColors.textQuaternary)
                    }
                }

                if !conversation.overview.isEmpty {
                    Text(conversation.overview)
                        .scaledFont(size: 13)
                        .foregroundColor(OmiColors.textTertiary)
                        .lineLimit(2)
                }
            }

            Spacer()

            // Star button
            Button(action: {
                Task { await toggleStar() }
            }) {
                Image(systemName: conversation.starred ? "star.fill" : "star")
                    .scaledFont(size: 14)
                    .foregroundColor(conversation.starred ? OmiColors.amber : OmiColors.textTertiary)
                    .opacity(isStarring ? 0.5 : 1.0)
            }
            .buttonStyle(.plain)

            // Time, duration, and source
            VStack(alignment: .trailing, spacing: 4) {
                HStack(spacing: 6) {
                    if !isHovering {
                        Text(sourceLabel)
                            .scaledFont(size: 10, weight: .medium)
                            .foregroundColor(OmiColors.textTertiary)
                    }

                    Text(formattedTimestamp)
                        .scaledFont(size: 13)
                        .foregroundColor(OmiColors.textTertiary)
                }

                if !isHovering {
                    HStack(spacing: 6) {
                        if let folderName = folderName {
                            Text(folderName)
                                .scaledFont(size: 11, weight: .medium)
                                .foregroundColor(OmiColors.textQuaternary)
                                .lineLimit(1)
                        }

                        Text(conversation.formattedDuration)
                            .scaledFont(size: 12)
                            .foregroundColor(OmiColors.textQuaternary)
                    }
                }
            }
        }
        .padding(12)
        .background(
            RoundedRectangle(cornerRadius: 10)
                .fill(isSelected ? OmiColors.purplePrimary.opacity(0.2) : (isHovering ? OmiColors.backgroundSecondary : (isNewlyCreated ? OmiColors.purplePrimary.opacity(0.15) : OmiColors.backgroundTertiary)))
        )
        .overlay(
            RoundedRectangle(cornerRadius: 10)
                .stroke(isSelected ? OmiColors.purplePrimary.opacity(0.5) : Color.clear, lineWidth: 2)
        )
        .contentShape(Rectangle())
    }

    var body: some View {
        Button(action: {
            if isMultiSelectMode {
                onToggleSelection?()
            } else {
                onTap()
            }
        }) {
            if isCompactView {
                // Compact mode: single line with all info
                compactRowContent
            } else {
                // Expanded mode: title + overview with metadata below
                expandedRowContent
            }
        }
        .buttonStyle(.plain)
        .onHover { hovering in
            isHovering = hovering
            if hovering {
                NSCursor.pointingHand.push()
            } else {
                NSCursor.pop()
            }
        }
        .contextMenu {
            Button(action: copyTranscript) {
                Label("Copy Transcript", systemImage: "doc.on.doc")
            }

            Button(action: { Task { await copyLink() } }) {
                Label(isCopyingLink ? "Generating Link..." : "Copy Link", systemImage: isCopyingLink ? "arrow.triangle.2.circlepath" : "link")
            }
            .disabled(isCopyingLink)

            Divider()

            Button(action: {
                editedTitle = conversation.title
                showEditDialog = true
            }) {
                Label("Edit Title", systemImage: "pencil")
            }

            // Move to Folder submenu
            if !folders.isEmpty {
                Menu {
                    // Option to remove from folder
                    if conversation.folderId != nil {
                        Button(action: {
                            Task {
                                await onMoveToFolder(conversation.id, nil)
                            }
                        }) {
                            Label("Remove from Folder", systemImage: "folder.badge.minus")
                        }
                        Divider()
                    }

                    // List available folders
                    ForEach(folders) { folder in
                        Button(action: {
                            Task {
                                await onMoveToFolder(conversation.id, folder.id)
                            }
                        }) {
                            HStack {
                                Text(folder.name)
                                if conversation.folderId == folder.id {
                                    Image(systemName: "checkmark")
                                }
                            }
                        }
                        .disabled(conversation.folderId == folder.id)
                    }
                } label: {
                    Label("Move to Folder", systemImage: "folder")
                }
            }

            Divider()

            Button(role: .destructive, action: {
                showDeleteConfirmation = true
            }) {
                Label("Delete", systemImage: "trash")
            }
        }
        .alert("Edit Conversation Title", isPresented: $showEditDialog) {
            TextField("Title", text: $editedTitle)
            Button("Cancel", role: .cancel) { }
            Button("Save") {
                Task {
                    await updateTitle()
                }
            }
            .disabled(editedTitle.isEmpty || isUpdatingTitle)
        } message: {
            Text("Enter a new title for this conversation")
        }
        .alert("Delete Conversation", isPresented: $showDeleteConfirmation) {
            Button("Cancel", role: .cancel) { }
            Button("Delete", role: .destructive) {
                Task {
                    await deleteConversation()
                }
            }
        } message: {
            Text("Are you sure you want to delete this conversation? This action cannot be undone.")
        }
    }
}

#Preview {
    VStack(spacing: 12) {
        // Preview would require mock ServerConversation
        Text("ConversationRowView Preview")
            .foregroundColor(.white)
    }
    .padding()
    .background(OmiColors.backgroundPrimary)
}
