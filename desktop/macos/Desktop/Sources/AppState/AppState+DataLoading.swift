@preconcurrency import AVFoundation
import Combine
import SwiftUI
@preconcurrency import UserNotifications

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
    // Every capture-stop path ends here; the Saving card has held the Live
    // card's slot until this load could show the conversation as a row.
    isFinalizingCapture = false
    NotificationCenter.default.post(name: .conversationsPageDidLoad, object: nil)
  }

  /// Server-only revalidation for activation and Cmd+R.
  func refreshConversations() async {
    guard AuthState.shared.isSignedIn else { return }
    await conversationRepository.refresh(query: currentConversationQuery)
    NotificationCenter.default.post(name: .conversationsPageDidLoad, object: nil)
  }

  var canLoadMoreConversations: Bool {
    conversationRepository.hasMore
  }

  func loadMoreConversations() async {
    await conversationRepository.loadMore()
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
    let generation = ownerScopeGeneration
    do {
      let folder = try await APIClient.shared.createFolder(
        name: name, description: description, color: color)
      // Fence like loadFolders: an in-flight mutation must not repopulate the
      // next account's folders after an in-place account switch reset them.
      guard generation == ownerScopeGeneration else { return nil }
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
    let generation = ownerScopeGeneration
    do {
      try await APIClient.shared.deleteFolder(id: folderId, moveToFolderId: moveToFolderId)
      guard generation == ownerScopeGeneration else { return }
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
    let generation = ownerScopeGeneration
    do {
      let updated = try await APIClient.shared.updateFolder(
        id: folderId, name: name, description: description, color: color)
      guard generation == ownerScopeGeneration else { return }
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

  /// Replace a conversation in local state with a freshly-fetched server
  /// version. Used after reprocess so the row sees the new `status` and full
  /// `structured` payload (not just title), which matters when reprocess
  /// transitions a `.failed` conversation back to `.completed`.
  func replaceConversation(_ refreshed: ServerConversation) {
    conversationRepository.replace(refreshed)
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
    let generation = ownerScopeGeneration
    do {
      let person = try await APIClient.shared.createPerson(name: name)
      guard generation == ownerScopeGeneration else { return nil }
      people.append(person)
      log("People: Created person '\(name)' with id \(person.id)")
      return person
    } catch {
      logError("People: Failed to create person", error: error)
      return nil
    }
  }

  /// Assigns segments to a person or user via bulk API
  /// When a backend bulk-assign fails, only "the conversation does not exist
  /// there yet" may fall back to a local-first assignment — any other failure
  /// (auth, validation, server error) must surface to the user, because the
  /// backend HAS the conversation and rejected the change.
  enum SpeakerAssignmentFallbackPolicy {
    static func keepsAssignmentLocally(statusCode: Int) -> Bool {
      statusCode == 404
    }
  }

  /// The wire targets a caller may send: backend segment ids, or `#index:N`
  /// positional fallbacks for segments stored without ids (the same contract
  /// the backend's `_resolve_bulk_segment_indices` accepts). The local half of
  /// an assignment must resolve BOTH — matching only ids silently drops every
  /// positional target on the floor.
  enum SpeakerAssignmentTargets {
    static let indexPrefix = "#index:"

    static func parse(_ targets: [String]) -> (ids: [String], orders: [Int]) {
      var ids: [String] = []
      var orders: [Int] = []
      for target in targets {
        if target.hasPrefix(indexPrefix), let order = Int(target.dropFirst(indexPrefix.count)) {
          orders.append(order)
        } else {
          ids.append(target)
        }
      }
      return (ids, orders)
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
      log("People: Assigned \(segmentIds.count) segments in conversation \(conversationId)")
    } catch let APIError.httpError(statusCode, _)
      where SpeakerAssignmentFallbackPolicy.keepsAssignmentLocally(statusCode: statusCode)
    {
      // The conversation has not reached the backend yet (a pending local session,
      // or one recovering from local fallback data). The assignment is still the
      // user's decision: keep it locally — the finalization sync uploads every
      // segment's person_id/is_user with the conversation itself, so the backend
      // converges once the session syncs. Failing here surfaced as the
      // "Couldn't assign this speaker" report on Beta.
      log("People: Conversation \(conversationId) not on backend yet; keeping speaker assignment local")
      // Here the local store is the ONLY holder of the user's decision — if the
      // write did not land (no matching session, no matching segment, or a
      // storage error) reporting success would silently drop the assignment.
      let persisted = await applySpeakerAssignmentLocally(
        conversationId: conversationId, segmentIds: segmentIds, personId: personId, isUser: isUser)
      DesktopDiagnosticsManager.shared.recordFallback(
        area: "speaker_assignment",
        from: "backend_bulk_assign",
        to: "local_store",
        reason: "conversation_not_synced",
        outcome: persisted ? .degraded : .exhausted
      )
      if !persisted {
        log(
          "People: Conversation \(conversationId) is neither on the backend (\(statusCode)) nor in local storage — assignment failed"
        )
      }
      return persisted
    } catch {
      logError("People: Failed to assign segments", error: error)
      return false
    }
    // Backend accepted the change — it owns the assignment now. The local
    // mirror is best-effort: a conversation recorded on another device has no
    // local session, and 0 updated rows is expected there.
    _ = await applySpeakerAssignmentLocally(
      conversationId: conversationId, segmentIds: segmentIds, personId: personId, isUser: isUser)
    return true
  }

  /// The client-side half of a speaker assignment: the in-memory conversation list
  /// (so the label is fresh on next open) and the local SQLite cache (so it
  /// survives restarts, and so a not-yet-synced session carries the assignment to
  /// the backend when it finalizes).
  /// - Returns: whether the SQLite write actually updated at least one segment.
  ///   False means nothing durable holds the assignment (no local session, no
  ///   matching segment, or a storage error).
  @discardableResult
  private func applySpeakerAssignmentLocally(
    conversationId: String,
    segmentIds: [String],
    personId: String?,
    isUser: Bool
  ) async -> Bool {
    let targets = SpeakerAssignmentTargets.parse(segmentIds)
    // Update the in-memory conversations list so the label is fresh on next open.
    // A target may be the segment's local id, its backend id, or a positional
    // #index:N — all three must land, or the caller's positional targets are
    // silently dropped on the floor.
    let idSet = Set(targets.ids)
    let orderSet = Set(targets.orders)
    if let idx = conversations.firstIndex(where: { $0.id == conversationId }) {
      for segIdx in conversations[idx].transcriptSegments.indices
      where idSet.contains(conversations[idx].transcriptSegments[segIdx].id)
        || conversations[idx].transcriptSegments[segIdx].backendId.map(idSet.contains) == true
        || orderSet.contains(segIdx)
      {
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
    // Also update the local SQLite cache so the assignment survives restarts —
    // and, for a conversation the backend does not have yet, so the finalization
    // sync can carry person_id/is_user up with the session. Awaited: returning
    // success before the write lands would let a quit drop the user's decision.
    do {
      let updatedRows = try await TranscriptionStorage.shared.updateSpeakerAssignmentByBackendId(
        conversationId,
        segmentIds: targets.ids,
        fallbackSegmentOrders: targets.orders,
        isUser: isUser,
        personId: isUser ? nil : personId
      )
      return updatedRows > 0
    } catch {
      logError("People: Failed to persist speaker assignment locally", error: error)
      return false
    }
  }

  // MARK: - Backend Segment Handling

  /// Handle incoming transcript segments from Python backend `/v4/listen`.
  /// Backend sends pre-merged segments with speaker attribution — no client-side word merging needed.
}
