import OmiCore
import OmiDesign
import OmiService
import SwiftUI

/// "Move to folder…": the folders, "No folder", and a new one made on the spot.
public struct MoveToFolderSheet: View {
    @Environment(ConversationsStore.self) private var conversations
    @Environment(\.dismiss) private var dismiss
    @State private var naming = false
    @State private var newName = ""
    let ids: [String]
    let onMoved: () -> Void

    public init(ids: [String], onMoved: @escaping () -> Void = {}) {
        self.ids = ids
        self.onMoved = onMoved
    }

    public var body: some View {
        NavigationStack {
            List {
                Section {
                    ForEach(conversations.folders) { folder in
                        row(FolderLabel(folder: folder), selected: current == folder.id) { move(to: folder.id) }
                    }
                    row(Label(L("noFolder"), systemImage: "tray"), selected: current == nil && ids.count == 1) { move(to: nil) }
                }
                Section {
                    Button {
                        newName = ""
                        naming = true
                    } label: { Label(L("newFolder"), systemImage: "folder.badge.plus") }
                }
            }
            .navigationTitle(L("moveToFolder"))
            .navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .cancellationAction) { Button(L("cancel")) { dismiss() } } }
            .alert(L("newFolder"), isPresented: $naming) {
                TextField(L("folderName"), text: $newName)
                Button(L("cancel"), role: .cancel) {}
                Button(L("save")) {
                    Task {
                        if let folder = await conversations.createFolder(FolderDraft(name: newName)) { move(to: folder.id) }
                    }
                }
            }
            .task { await conversations.loadFolders() }
        }
    }

    /// The folder all the conversations share, if they do.
    private var current: String? {
        let folders = Set(ids.map { id in conversations.conversations.first { $0.id == id }?.folderID })
        return folders.count == 1 ? folders.first ?? nil : nil
    }

    private func row(_ label: some View, selected: Bool, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            HStack {
                label.foregroundStyle(DS.Palette.ink)
                Spacer()
                if selected { Image(systemName: "checkmark").foregroundStyle(DS.Palette.agent) }
            }
        }
    }

    private func move(to folderID: String?) {
        DSHaptics.tap()
        let ids = ids
        Task { await conversations.move(ids, to: folderID) }
        onMoved()
        dismiss()
    }
}

/// Folders: new, rename (tap), delete (swipe; Omi's own folders stay).
public struct FoldersSheet: View {
    @Environment(ConversationsStore.self) private var conversations
    @Environment(\.dismiss) private var dismiss
    @State private var renaming: Folder?
    @State private var naming = false
    @State private var name = ""

    public init() {}

    public var body: some View {
        NavigationStack {
            List {
                Section {
                    ForEach(conversations.folders) { folder in
                        Button {
                            name = folder.name
                            renaming = folder
                        } label: {
                            HStack {
                                FolderLabel(folder: folder).foregroundStyle(DS.Palette.ink)
                                Spacer()
                                Text(verbatim: "\(folder.conversationCount)").foregroundStyle(DS.Palette.inkTertiary)
                            }
                        }
                        .swipeActions {
                            if !folder.isSystem {
                                Button(role: .destructive) { Task { await conversations.deleteFolder(folder.id) } } label: {
                                    Label(L("deleteFolder"), systemImage: "trash")
                                }
                            }
                        }
                    }
                } footer: {
                    Text(L("nativeFolderDeleteFooter"))
                }
                Section {
                    Button {
                        name = ""
                        naming = true
                    } label: { Label(L("newFolder"), systemImage: "folder.badge.plus") }
                }
            }
            .navigationTitle(L("nativeFolders"))
            .navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .confirmationAction) { Button(L("done")) { dismiss() } } }
            .alert(L("newFolder"), isPresented: $naming) {
                TextField(L("folderName"), text: $name)
                Button(L("cancel"), role: .cancel) {}
                Button(L("save")) { Task { await conversations.createFolder(FolderDraft(name: name)) } }
            }
            .alert(L("editFolder"), isPresented: Binding(get: { renaming != nil }, set: { if !$0 { renaming = nil } })) {
                TextField(L("folderName"), text: $name)
                Button(L("cancel"), role: .cancel) {}
                Button(L("save")) {
                    guard let folder = renaming else { return }
                    var draft = folder.draft
                    draft.name = name
                    Task { await conversations.updateFolder(folder.id, to: draft) }
                }
            }
            .task { await conversations.loadFolders() }
        }
    }
}

/// A folder's emoji (or a folder glyph) and name.
public struct FolderLabel: View {
    let folder: Folder

    public init(folder: Folder) {
        self.folder = folder
    }

    public var body: some View {
        Label {
            Text(folder.name)
        } icon: {
            if folder.icon.unicodeScalars.first?.properties.isEmojiPresentation == true {
                Text(folder.icon)
            } else {
                Image(systemName: "folder")
            }
        }
    }
}
