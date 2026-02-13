import SwiftUI

// MARK: - Folder Colors

struct FolderColors {
    static let palette: [(name: String, hex: String)] = [
        ("Gray", "#6B7280"),
        ("Red", "#EF4444"),
        ("Orange", "#F97316"),
        ("Amber", "#F59E0B"),
        ("Green", "#22C55E"),
        ("Teal", "#14B8A6"),
        ("Blue", "#3B82F6"),
        ("Indigo", "#6366F1"),
        ("Purple", "#A855F7"),
        ("Pink", "#EC4899"),
    ]
}

// MARK: - Folder Tabs Strip

struct FolderTabsStrip: View {
    @ObservedObject var appState: AppState
    var onCreateFolder: () -> Void
    var onEditFolder: (Folder) -> Void
    var onDeleteFolder: (Folder) -> Void

    @State private var isFilteringFolder: Bool = false

    var body: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 6) {
                // "All" tab
                folderTab(
                    label: "All",
                    icon: "tray.2",
                    isSelected: appState.selectedFolderId == nil && !appState.showStarredOnly
                ) {
                    Task {
                        isFilteringFolder = true
                        await appState.setFolderFilter(nil)
                        if appState.showStarredOnly {
                            await appState.toggleStarredFilter()
                        }
                        isFilteringFolder = false
                    }
                }

                // "Starred" tab
                folderTab(
                    label: "Starred",
                    icon: appState.showStarredOnly ? "star.fill" : "star",
                    isSelected: appState.showStarredOnly
                ) {
                    Task {
                        isFilteringFolder = true
                        await appState.toggleStarredFilter()
                        isFilteringFolder = false
                    }
                }

                // Folder tabs
                ForEach(appState.folders) { folder in
                    let isSelected = appState.selectedFolderId == folder.id
                    folderTab(
                        label: folder.name,
                        icon: nil,
                        isSelected: isSelected
                    ) {
                        Task {
                            isFilteringFolder = true
                            if isSelected {
                                await appState.setFolderFilter(nil)
                            } else {
                                await appState.setFolderFilter(folder.id)
                            }
                            isFilteringFolder = false
                        }
                    }
                    .contextMenu {
                        Button {
                            onEditFolder(folder)
                        } label: {
                            Label("Edit", systemImage: "pencil")
                        }
                        Button(role: .destructive) {
                            onDeleteFolder(folder)
                        } label: {
                            Label("Delete", systemImage: "trash")
                        }
                    }
                }

                // "+" create button
                Button(action: onCreateFolder) {
                    Image(systemName: "plus")
                        .font(.system(size: 11, weight: .semibold))
                        .foregroundColor(OmiColors.textSecondary)
                        .frame(width: 26, height: 26)
                        .background(
                            RoundedRectangle(cornerRadius: 6)
                                .fill(OmiColors.backgroundTertiary.opacity(0.6))
                        )
                }
                .buttonStyle(.plain)
            }
            .padding(.vertical, 2)
        }
        .disabled(isFilteringFolder)
    }

    @ViewBuilder
    private func folderTab(
        label: String,
        icon: String?,
        isSelected: Bool,
        action: @escaping () -> Void
    ) -> some View {
        Button(action: action) {
            HStack(spacing: 5) {
                if let icon = icon {
                    Image(systemName: icon)
                        .font(.system(size: 11))
                }
                Text(label)
                    .font(.system(size: 12, weight: .medium))
                    .lineLimit(1)
            }
            .foregroundColor(isSelected ? OmiColors.textPrimary : OmiColors.textSecondary)
            .padding(.horizontal, 10)
            .padding(.vertical, 6)
            .background(
                RoundedRectangle(cornerRadius: 8)
                    .fill(isSelected ? OmiColors.textPrimary.opacity(0.12) : OmiColors.backgroundTertiary.opacity(0.6))
            )
            .overlay(
                RoundedRectangle(cornerRadius: 8)
                    .stroke(isSelected ? OmiColors.textPrimary.opacity(0.3) : Color.clear, lineWidth: 1)
            )
        }
        .buttonStyle(.plain)
    }
}

// MARK: - Folder Form Sheet (Create / Edit)

struct FolderFormSheet: View {
    let folder: Folder?
    let onDismiss: () -> Void

    @EnvironmentObject var appState: AppState

    @State private var name: String = ""
    @State private var descriptionText: String = ""
    @State private var selectedColor: String = "#6B7280"
    @State private var isSaving: Bool = false

    private var isEditing: Bool { folder != nil }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            // Header
            HStack {
                Text(isEditing ? "Edit Folder" : "New Folder")
                    .font(.system(size: 16, weight: .semibold))
                    .foregroundColor(OmiColors.textPrimary)
                Spacer()
                DismissButton(action: onDismiss)
            }
            .padding(20)

            Divider().background(OmiColors.backgroundTertiary)

            VStack(alignment: .leading, spacing: 16) {
                // Name field
                VStack(alignment: .leading, spacing: 6) {
                    Text("Name")
                        .font(.system(size: 12, weight: .medium))
                        .foregroundColor(OmiColors.textSecondary)
                    TextField("Folder name", text: $name)
                        .textFieldStyle(.plain)
                        .font(.system(size: 14))
                        .foregroundColor(OmiColors.textPrimary)
                        .padding(.horizontal, 10)
                        .padding(.vertical, 8)
                        .background(
                            RoundedRectangle(cornerRadius: 8)
                                .fill(OmiColors.backgroundTertiary.opacity(0.5))
                        )
                        .overlay(
                            RoundedRectangle(cornerRadius: 8)
                                .stroke(OmiColors.border, lineWidth: 1)
                        )
                }

                // Description field
                VStack(alignment: .leading, spacing: 6) {
                    Text("Description")
                        .font(.system(size: 12, weight: .medium))
                        .foregroundColor(OmiColors.textSecondary)
                    TextField("Optional description", text: $descriptionText)
                        .textFieldStyle(.plain)
                        .font(.system(size: 14))
                        .foregroundColor(OmiColors.textPrimary)
                        .padding(.horizontal, 10)
                        .padding(.vertical, 8)
                        .background(
                            RoundedRectangle(cornerRadius: 8)
                                .fill(OmiColors.backgroundTertiary.opacity(0.5))
                        )
                        .overlay(
                            RoundedRectangle(cornerRadius: 8)
                                .stroke(OmiColors.border, lineWidth: 1)
                        )
                }

                // Color picker
                VStack(alignment: .leading, spacing: 6) {
                    Text("Color")
                        .font(.system(size: 12, weight: .medium))
                        .foregroundColor(OmiColors.textSecondary)

                    LazyVGrid(columns: Array(repeating: GridItem(.fixed(32), spacing: 8), count: 5), spacing: 8) {
                        ForEach(FolderColors.palette, id: \.hex) { item in
                            let isSelected = selectedColor == item.hex
                            Button(action: {
                                selectedColor = item.hex
                            }) {
                                Circle()
                                    .fill(Color(hex: item.hex) ?? Color.gray)
                                    .frame(width: 28, height: 28)
                                    .overlay(
                                        Circle()
                                            .stroke(Color.white, lineWidth: isSelected ? 2 : 0)
                                            .padding(2)
                                    )
                                    .overlay(
                                        Circle()
                                            .stroke(isSelected ? (Color(hex: item.hex) ?? Color.gray) : Color.clear, lineWidth: 2)
                                    )
                            }
                            .buttonStyle(.plain)
                        }
                    }
                }
            }
            .padding(20)

            Divider().background(OmiColors.backgroundTertiary)

            // Action buttons
            HStack {
                Spacer()
                Button("Cancel") {
                    onDismiss()
                }
                .buttonStyle(.plain)
                .foregroundColor(OmiColors.textSecondary)
                .padding(.horizontal, 16)
                .padding(.vertical, 8)

                Button(action: save) {
                    if isSaving {
                        ProgressView()
                            .scaleEffect(0.6)
                            .frame(width: 14, height: 14)
                    } else {
                        Text(isEditing ? "Save" : "Create")
                    }
                }
                .buttonStyle(.plain)
                .foregroundColor(name.trimmingCharacters(in: .whitespaces).isEmpty ? OmiColors.textTertiary : .white)
                .padding(.horizontal, 16)
                .padding(.vertical, 8)
                .background(
                    RoundedRectangle(cornerRadius: 8)
                        .fill(name.trimmingCharacters(in: .whitespaces).isEmpty ? OmiColors.backgroundTertiary : Color(hex: selectedColor) ?? OmiColors.textPrimary)
                )
                .disabled(name.trimmingCharacters(in: .whitespaces).isEmpty || isSaving)
            }
            .padding(20)
        }
        .onAppear {
            if let folder = folder {
                name = folder.name
                descriptionText = folder.description ?? ""
                selectedColor = folder.color
            }
        }
    }

    private func save() {
        let trimmedName = name.trimmingCharacters(in: .whitespaces)
        guard !trimmedName.isEmpty else { return }

        isSaving = true
        Task {
            if let folder = folder {
                await appState.updateFolder(
                    folder.id,
                    name: trimmedName,
                    description: descriptionText.isEmpty ? nil : descriptionText,
                    color: selectedColor
                )
            } else {
                _ = await appState.createFolder(
                    name: trimmedName,
                    description: descriptionText.isEmpty ? nil : descriptionText,
                    color: selectedColor
                )
            }
            isSaving = false
            onDismiss()
        }
    }
}

// MARK: - Delete Folder Sheet

struct DeleteFolderSheet: View {
    let folder: Folder
    let onDismiss: () -> Void

    @EnvironmentObject var appState: AppState

    @State private var moveToFolderId: String? = nil
    @State private var isDeleting: Bool = false

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            // Header
            HStack {
                Text("Delete Folder")
                    .font(.system(size: 16, weight: .semibold))
                    .foregroundColor(OmiColors.textPrimary)
                Spacer()
                DismissButton(action: onDismiss)
            }
            .padding(20)

            Divider().background(OmiColors.backgroundTertiary)

            VStack(alignment: .leading, spacing: 16) {
                Text("Are you sure you want to delete \"\(folder.name)\"?")
                    .font(.system(size: 14))
                    .foregroundColor(OmiColors.textPrimary)

                if folder.conversationCount > 0 {
                    Text("This folder has \(folder.conversationCount) conversation\(folder.conversationCount == 1 ? "" : "s"). Choose where to move them:")
                        .font(.system(size: 13))
                        .foregroundColor(OmiColors.textSecondary)

                    // Move destination picker
                    VStack(alignment: .leading, spacing: 4) {
                        moveOption(label: "No folder (unfiled)", folderId: nil)

                        ForEach(appState.folders.filter { $0.id != folder.id }) { otherFolder in
                            moveOption(label: otherFolder.name, folderId: otherFolder.id, color: otherFolder.color)
                        }
                    }
                }
            }
            .padding(20)

            Divider().background(OmiColors.backgroundTertiary)

            // Action buttons
            HStack {
                Spacer()
                Button("Cancel") {
                    onDismiss()
                }
                .buttonStyle(.plain)
                .foregroundColor(OmiColors.textSecondary)
                .padding(.horizontal, 16)
                .padding(.vertical, 8)

                Button(action: performDelete) {
                    if isDeleting {
                        ProgressView()
                            .scaleEffect(0.6)
                            .frame(width: 14, height: 14)
                    } else {
                        Text("Delete")
                    }
                }
                .buttonStyle(.plain)
                .foregroundColor(.white)
                .padding(.horizontal, 16)
                .padding(.vertical, 8)
                .background(
                    RoundedRectangle(cornerRadius: 8)
                        .fill(Color.red)
                )
                .disabled(isDeleting)
            }
            .padding(20)
        }
    }

    @ViewBuilder
    private func moveOption(label: String, folderId: String?, color: String? = nil) -> some View {
        let isSelected = moveToFolderId == folderId
        Button(action: {
            moveToFolderId = folderId
        }) {
            HStack(spacing: 8) {
                if let color = color, let c = Color(hex: color) {
                    Circle()
                        .fill(c)
                        .frame(width: 8, height: 8)
                } else {
                    Image(systemName: "tray")
                        .font(.system(size: 11))
                        .foregroundColor(OmiColors.textTertiary)
                        .frame(width: 8)
                }
                Text(label)
                    .font(.system(size: 13))
                    .foregroundColor(OmiColors.textPrimary)
                Spacer()
                if isSelected {
                    Image(systemName: "checkmark")
                        .font(.system(size: 11, weight: .semibold))
                        .foregroundColor(OmiColors.textPrimary)
                }
            }
            .padding(.horizontal, 10)
            .padding(.vertical, 8)
            .background(
                RoundedRectangle(cornerRadius: 6)
                    .fill(isSelected ? OmiColors.backgroundTertiary : Color.clear)
            )
        }
        .buttonStyle(.plain)
    }

    private func performDelete() {
        isDeleting = true
        Task {
            await appState.deleteFolder(folder.id, moveToFolderId: moveToFolderId)
            isDeleting = false
            onDismiss()
        }
    }
}
