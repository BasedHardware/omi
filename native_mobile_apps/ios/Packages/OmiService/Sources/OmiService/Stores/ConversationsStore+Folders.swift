import Foundation
import OmiCore
import OmiNetwork

/// The list filter (all, starred, one folder) and the folders themselves.
public extension ConversationsStore {
    /// Shows only starred conversations or one folder's; `.all` goes back to the full list.
    func setFilter(_ filter: ConversationFilter) async {
        guard filter != self.filter else { return }
        self.filter = filter
        filtered = []
        filteredHasMore = false
        guard filter != .all else { return }
        await reloadFiltered()
    }

    func loadFolders() async {
        if let loaded = try? await api.folders() { folders = loaded }
    }

    func folder(_ id: String?) -> Folder? {
        id.flatMap { id in folders.first { $0.id == id } }
    }

    /// Creates a folder from the editor's draft; `nil` when the name is empty or the backend
    /// refuses (e.g. the 50-folder limit).
    @discardableResult
    func createFolder(_ draft: FolderDraft) async -> Folder? {
        guard let draft = draft.trimmed, let folder = try? await api.createFolder(draft) else { return nil }
        folders.append(folder)
        return folder
    }

    /// Optimistic edit of a folder's name and look; the old folder comes back if the backend
    /// refuses. False when the draft is empty or the folder is gone.
    @discardableResult
    func updateFolder(_ id: String, to draft: FolderDraft) async -> Bool {
        guard let draft = draft.trimmed, let index = folders.firstIndex(where: { $0.id == id }) else { return false }
        let previous = folders[index]
        apply(draft, at: index)
        do {
            let updated = try await api.updateFolder(id: id, draft)
            if let index = folders.firstIndex(where: { $0.id == id }) { folders[index] = updated }
            return true
        } catch {
            if let index = folders.firstIndex(where: { $0.id == id }) { folders[index] = previous }
            return false
        }
    }

    private func apply(_ draft: FolderDraft, at index: Int) {
        folders[index].name = draft.name
        folders[index].icon = draft.icon
        folders[index].color = draft.color
        folders[index].description = draft.description
    }

    /// Deletes a custom folder; the backend keeps its conversations (they move to `moveTo`, or
    /// leave every folder when that is `nil`).
    func deleteFolder(_ id: String, moveTo folderID: String? = nil) async {
        guard let index = folders.firstIndex(where: { $0.id == id }), !folders[index].isSystem else { return }
        let removed = folders.remove(at: index)
        // A folder cannot be its own destination.
        let destination = folderID == id ? nil : folderID
        do {
            try await api.deleteFolder(id: id, moveTo: destination)
            if filter == .folder(id) { await setFilter(.all) }
            // The backend re-files the folder's conversations; the next page load shows where.
            await load()
        } catch {
            folders.insert(removed, at: min(index, folders.count))
        }
    }

    /// The filter's first page again.
    func reloadFiltered() async {
        let filter = filter
        guard filter != .all else { return }
        isLoadingFiltered = true
        defer { isLoadingFiltered = false }
        guard let page = try? await api.conversations(limit: pageSize, offset: 0, filter: filter), filter == self.filter else { return }
        let hidden = Set(pendingDeletion?.ids ?? [])
        filtered = page.filter { !hidden.contains($0.id) }
        filteredHasMore = page.count == pageSize
    }

    internal func loadMoreFiltered() async {
        let filter = filter
        guard filteredHasMore, !isLoadingFiltered else { return }
        isLoadingFiltered = true
        defer { isLoadingFiltered = false }
        guard let page = try? await api.conversations(limit: pageSize, offset: filtered.count, filter: filter),
              filter == self.filter else { return }
        let known = Set(filtered.map(\.id))
        filtered += page.filter { !known.contains($0.id) }
        filteredHasMore = page.count == pageSize
    }
}
