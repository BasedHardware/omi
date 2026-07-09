import Foundation

@MainActor
extension AppState {
  func loadConversations() async {
    await conversationRepository.load(
      query: ConversationQuery(
        showStarredOnly: showStarredOnly,
        selectedDate: selectedDateFilter,
        folderId: selectedFolderId
      )
    )
    NotificationCenter.default.post(name: .conversationsPageDidLoad, object: nil)
  }

  func refreshConversations() async {
    await conversationRepository.refresh()
  }

  func toggleStarredFilter() async {
    showStarredOnly.toggle()
    await loadConversations()
  }

  func setDateFilter(_ date: Date?) async {
    selectedDateFilter = date
    await loadConversations()
  }

  func clearFilters() async {
    showStarredOnly = false
    selectedDateFilter = nil
    selectedFolderId = nil
    await loadConversations()
  }

  func setFolderFilter(_ folderId: String?) async {
    selectedFolderId = folderId
    await loadConversations()
  }

  // MARK: - Folder Management

  func loadFolders() async {
    guard !isLoadingFolders else { return }
    isLoadingFolders = true
    defer { isLoadingFolders = false }

    do {
      folders = try await APIClient.shared.getFolders()
      log("Folders: Loaded \(folders.count) folders")
    } catch {
      logError("Folders: Failed to load", error: error)
    }
  }

  func createFolder(name: String, description: String? = nil, color: String? = nil) async -> Folder? {
    do {
      let folder = try await APIClient.shared.createFolder(
        name: name,
        description: description,
        color: color
      )
      folders.append(folder)
      return folder
    } catch {
      logError("Folders: Failed to create folder", error: error)
      return nil
    }
  }

  func deleteFolder(_ folderId: String, moveToFolderId: String? = nil) async {
    do {
      try await APIClient.shared.deleteFolder(id: folderId, moveToFolderId: moveToFolderId)
      folders.removeAll { $0.id == folderId }
      if selectedFolderId == folderId {
        selectedFolderId = nil
        await loadConversations()
      }
    } catch {
      logError("Folders: Failed to delete folder", error: error)
    }
  }

  func updateFolder(_ folderId: String, name: String?, description: String?, color: String?) async {
    do {
      let updated = try await APIClient.shared.updateFolder(
        id: folderId,
        name: name,
        description: description,
        color: color
      )
      if let index = folders.firstIndex(where: { $0.id == folderId }) {
        folders[index] = updated
      }
    } catch {
      logError("Folders: Failed to update folder", error: error)
    }
  }

  func moveConversationToFolder(_ conversationId: String, folderId: String?) async {
    do {
      try await conversationRepository.moveToFolder(id: conversationId, folderId: folderId)
    } catch {
      logError("Folders: Failed to move conversation to folder", error: error)
    }
  }

  // MARK: - People (Speaker Profiles)

  func fetchPeople() async {
    do {
      people = try await APIClient.shared.getPeople()
    } catch {
      logError("People: Failed to load", error: error)
    }
  }

  func createPerson(name: String) async -> Person? {
    do {
      let person = try await APIClient.shared.createPerson(name: name)
      people.append(person)
      return person
    } catch {
      logError("People: Failed to create person", error: error)
      return nil
    }
  }

  func assignSpeakerToSegments(
    conversationId: String,
    segmentIds: [String],
    personId: String?,
    isUser: Bool
  ) async -> Bool {
    do {
      try await APIClient.shared.assignSegmentsBulk(
        conversationId: conversationId,
        segmentIds: segmentIds,
        isUser: isUser,
        personId: personId
      )
      try? await TranscriptionStorage.shared.updateSegmentSpeakerAssignment(
        backendConversationId: conversationId,
        segmentIds: segmentIds,
        personId: personId,
        isUser: isUser
      )
      await conversationRepository.loadDetail(id: conversationId)
      return true
    } catch {
      logError("People: Failed to assign segments", error: error)
      return false
    }
  }
}
