import AVFoundation
import Combine
import SwiftUI
import UserNotifications

@MainActor
extension AppState {
  private var currentConversationQuery: ConversationListQuery {
    ConversationListQuery(
      starredOnly: showStarredOnly,
      date: selectedDateFilter,
      folderId: selectedFolderId
    )
  }

  /// Cache-first load owned by ConversationRepository. The repository emits
  /// the cached projection immediately and quietly replaces it with server truth.
  func loadConversations() async {
    await conversationRepository.load(query: currentConversationQuery)
    NotificationCenter.default.post(name: .conversationsPageDidLoad, object: nil)
  }

  /// Server-only revalidation for activation and Cmd+R.
  func refreshConversations() async {
    guard AuthState.shared.isSignedIn else { return }
    await conversationRepository.refresh(query: currentConversationQuery)
    NotificationCenter.default.post(name: .conversationsPageDidLoad, object: nil)
  }

  /// Optimistically update star state, then settle from the canonical mutation response.
  func setConversationStarred(_ conversationId: String, starred: Bool) async {
    do {
      try await conversationRepository.setStarred(id: conversationId, starred: starred)
    } catch {
      logError("Conversations: Failed to update starred state", error: error)
    }
  }

  /// Toggle starred filter and reload conversations
  func toggleStarredFilter() async {
    showStarredOnly.toggle()
    await loadConversations()
  }

  /// Set date filter and reload conversations
  func setDateFilter(_ date: Date?) async {
    selectedDateFilter = date
    await loadConversations()
  }

  /// Clear all filters and reload conversations
  func clearFilters() async {
    showStarredOnly = false
    selectedDateFilter = nil
    selectedFolderId = nil
    await loadConversations()
  }

  /// Set folder filter and reload conversations
  func setFolderFilter(_ folderId: String?) async {
    selectedFolderId = folderId
    await loadConversations()
  }

  // MARK: - Folder Management

  /// Load folders from API. `fetch` is a test seam (production uses APIClient).
  func loadFolders(fetch: (() async throws -> [Folder])? = nil) async {
    guard !isLoadingFolders else { return }

    isLoadingFolders = true
    let generation = ownerScopeGeneration

    do {
      let fetchedFolders: [Folder]
      if let fetch {
        fetchedFolders = try await fetch()
      } else {
        fetchedFolders = try await APIClient.shared.getFolders()
      }
      // Owner fence: a previous account's in-flight response must not
      // repopulate folders after an account switch reset them.
      guard generation == ownerScopeGeneration else { return }
      folders = fetchedFolders
      log("Folders: Loaded \(fetchedFolders.count) folders")
    } catch {
      guard generation == ownerScopeGeneration else { return }
      logError("Folders: Failed to load", error: error)
    }

    isLoadingFolders = false
  }

  /// Create a new folder
  func createFolder(name: String, description: String? = nil, color: String? = nil) async -> Folder? {
    do {
      let folder = try await APIClient.shared.createFolder(
        name: name, description: description, color: color)
      folders.append(folder)
      log("Folders: Created folder '\(name)'")
      return folder
    } catch {
      logError("Folders: Failed to create folder", error: error)
      return nil
    }
  }

  /// Delete a folder
  func deleteFolder(_ folderId: String, moveToFolderId: String? = nil) async {
    do {
      try await APIClient.shared.deleteFolder(id: folderId, moveToFolderId: moveToFolderId)
      folders.removeAll { $0.id == folderId }
      if selectedFolderId == folderId {
        selectedFolderId = nil
      }
      log("Folders: Deleted folder \(folderId)")
    } catch {
      logError("Folders: Failed to delete folder", error: error)
    }
  }

  /// Update a folder
  func updateFolder(_ folderId: String, name: String?, description: String?, color: String?) async {
    do {
      let updated = try await APIClient.shared.updateFolder(
        id: folderId, name: name, description: description, color: color)
      if let index = folders.firstIndex(where: { $0.id == folderId }) {
        folders[index] = updated
      }
      log("Folders: Updated folder \(folderId)")
    } catch {
      logError("Folders: Failed to update folder", error: error)
    }
  }

  /// Move a conversation through the single conversation repository.
  func moveConversationToFolder(_ conversationId: String, folderId: String?) async {
    do {
      try await conversationRepository.moveToFolder(id: conversationId, folderId: folderId)
      log("Folders: Moved conversation \(conversationId) to folder \(folderId ?? "none")")
    } catch {
      logError("Folders: Failed to move conversation to folder", error: error)
    }
  }

  /// Optimistically update title, then settle from the canonical mutation response.
  func updateConversationTitle(_ conversationId: String, title: String) async {
    do {
      try await conversationRepository.updateTitle(id: conversationId, title: title)
    } catch {
      logError("Conversations: Failed to update title", error: error)
    }
  }

  func loadConversationDetail(
    _ conversation: ServerConversation,
    onCached: ((ServerConversation) -> Void)? = nil
  ) async -> ServerConversation {
    (try? await conversationRepository.detail(
      id: conversation.id,
      seed: conversation,
      onCached: onCached
    )) ?? conversation
  }

  func searchConversations(_ query: String) async throws -> [ServerConversation] {
    try await conversationRepository.search(text: query)
  }

  func cancelConversationSearch() {
    conversationRepository.cancelSearch()
  }

  func deleteConversation(_ conversationId: String) async -> Bool {
    do {
      try await conversationRepository.delete(id: conversationId)
      return true
    } catch {
      logError("Conversations: Failed to delete conversation", error: error)
      return false
    }
  }

  // MARK: - People (Speaker Profiles)

  /// Fetches all people from the OMI API. `fetch` is a test seam.
  func fetchPeople(fetch: (() async throws -> [Person])? = nil) async {
    let generation = ownerScopeGeneration
    do {
      let fetchedPeople: [Person]
      if let fetch {
        fetchedPeople = try await fetch()
      } else {
        fetchedPeople = try await APIClient.shared.getPeople()
      }
      // Owner fence: see loadFolders.
      guard generation == ownerScopeGeneration else { return }
      people = fetchedPeople
      log("People: Loaded \(fetchedPeople.count) people")
    } catch {
      guard generation == ownerScopeGeneration else { return }
      logError("People: Failed to load", error: error)
    }
  }

  /// Creates a new person and adds to local cache
  func createPerson(name: String) async -> Person? {
    do {
      let person = try await APIClient.shared.createPerson(name: name)
      people.append(person)
      log("People: Created person '\(name)' with id \(person.id)")
      return person
    } catch {
      logError("People: Failed to create person", error: error)
      return nil
    }
  }

  /// Assigns segments to a person or user via bulk API
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
      log("People: Assigned \(segmentIds.count) segments in conversation \(conversationId)")
      // Update in-memory conversations list so the prop is fresh on next open
      let idSet = Set(segmentIds)
      if let idx = conversations.firstIndex(where: { $0.id == conversationId }) {
        for segIdx in conversations[idx].transcriptSegments.indices
        where idSet.contains(conversations[idx].transcriptSegments[segIdx].id) {
          let old = conversations[idx].transcriptSegments[segIdx]
          conversations[idx].transcriptSegments[segIdx] = TranscriptSegment(
            id: old.id,
            backendId: old.backendId,
            text: old.text,
            speaker: old.speaker,
            isUser: isUser,
            personId: isUser ? nil : personId,
            start: old.start,
            end: old.end,
            translations: old.translations
          )
        }
      }
      // Also update local SQLite cache so changes persist across app restarts
      try? await TranscriptionStorage.shared.updateSegmentSpeakerAssignment(
        backendConversationId: conversationId,
        segmentIds: segmentIds,
        personId: personId,
        isUser: isUser
      )
      return true
    } catch {
      logError("People: Failed to assign segments", error: error)
      return false
    }
  }

  // MARK: - Backend Segment Handling

  /// Handle incoming transcript segments from Python backend `/v4/listen`.
  /// Backend sends pre-merged segments with speaker attribution — no client-side word merging needed.
}
