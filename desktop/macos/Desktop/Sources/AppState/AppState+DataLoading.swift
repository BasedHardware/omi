import AVFoundation
import Combine
import SwiftUI
import UserNotifications

private struct LocalConversationCacheTimeout: Error {}

@MainActor
extension AppState {

  func updateConversationCount(_ count: Int, filtered: Bool) {
    if filtered {
      if filteredConversationsCount != count {
        filteredConversationsCount = count
      }
    } else {
      if totalConversationsCount != count {
        totalConversationsCount = count
      }
      if filteredConversationsCount != nil {
        filteredConversationsCount = nil
      }
    }
  }

  /// Load conversations - first from local cache (instant), then from API (background refresh)
  func loadConversations() async {
    guard !isLoadingConversations else { return }

    isLoadingConversations = true
    conversationsError = nil

    let requestShowStarredOnly = showStarredOnly
    let requestSelectedDateFilter = selectedDateFilter
    let requestSelectedFolderId = selectedFolderId
    let requestHasActiveFilters = hasActiveConversationFilters

    func requestFiltersAreCurrent() -> Bool {
      showStarredOnly == requestShowStarredOnly
        && selectedDateFilter == requestSelectedDateFilter
        && selectedFolderId == requestSelectedFolderId
    }

    // Step 1: Load from local cache first (instant display)
    // Use timeout to avoid blocking UI if database is initializing (e.g. recovery).
    // The local cache currently supports starred/folder filters but not server date ranges;
    // skip it for date-filtered views so the visible list and total count share semantics.
    if requestSelectedDateFilter == nil {
      do {
        let cachedConversations = try await withThrowingTaskGroup(of: [ServerConversation].self) { group in
          group.addTask {
            try await TranscriptionStorage.shared.getLocalConversations(
              limit: 50,
              starredOnly: requestShowStarredOnly,
              folderId: requestSelectedFolderId
            )
          }
          group.addTask {
            try await Task.sleep(nanoseconds: 3_000_000_000)  // 3 second timeout
            throw LocalConversationCacheTimeout()
          }
          let result = try await group.next()!
          group.cancelAll()
          return result
        }

        if !cachedConversations.isEmpty && requestFiltersAreCurrent() {
          conversations = cachedConversations
          log("Conversations: Loaded \(cachedConversations.count) from local cache (instant)")

          // Get local count
          let localCount = try await TranscriptionStorage.shared.getLocalConversationsCount(
            starredOnly: requestShowStarredOnly,
            folderId: requestSelectedFolderId)
          updateConversationCount(localCount, filtered: requestHasActiveFilters)

          // Stop loading state so UI shows cached data immediately
          isLoadingConversations = false
          // Notify sidebar immediately so loading indicator clears with cached data
          NotificationCenter.default.post(name: .conversationsPageDidLoad, object: nil)
        }
      } catch is LocalConversationCacheTimeout {
        log("Conversations: Local cache load timed out, falling back to API")
      } catch is CancellationError {
        log("Conversations: Local cache load cancelled")
        return
      } catch {
        log("Conversations: Local cache unavailable, falling back to API")
        // Continue to API fetch even if local fails
      }
    } else {
      conversations = []
      filteredConversationsCount = 0
    }

    // Step 2: Fetch from API in background to get fresh data
    // Calculate date range if date filter is set
    let startDate: Date?
    let endDate: Date?
    if let filterDate = requestSelectedDateFilter {
      let calendar = Calendar.current
      startDate = calendar.startOfDay(for: filterDate)
      endDate = calendar.date(byAdding: .day, value: 1, to: startDate!)
    } else {
      startDate = nil
      endDate = nil
    }

    // Fetch conversations and count in parallel
    async let conversationsTask = APIClient.shared.getConversations(
      limit: 50,
      offset: 0,
      statuses: [.completed, .processing],
      includeDiscarded: false,
      startDate: startDate,
      endDate: endDate,
      folderId: requestSelectedFolderId,
      starred: requestShowStarredOnly ? true : nil
    )
    async let countTask = APIClient.shared.getConversationsCount(
      includeDiscarded: false,
      statuses: [.completed, .processing],
      startDate: startDate,
      endDate: endDate,
      folderId: requestSelectedFolderId,
      starred: requestShowStarredOnly ? true : nil
    )

    do {
      let fetchedConversations = try await conversationsTask
      if requestFiltersAreCurrent() {
        let reconciliation = ConversationReconciliationPolicy.mergeList(
          server: fetchedConversations,
          current: conversations,
          pendingMutations: pendingConversationMutations
        )
        pendingConversationMutations = reconciliation.pendingMutations
        conversations = reconciliation.conversations
      } else {
        log("Conversations: Ignoring stale response for superseded filters")
      }
      log(
        "Conversations: Refreshed \(fetchedConversations.count) from API (starred=\(requestShowStarredOnly), date=\(requestSelectedDateFilter?.description ?? "nil"))"
      )

      // DEBUG: Log any conversations with empty titles
      for conv in fetchedConversations where conv.structured.title.isEmpty {
        log(
          "DEBUG: Conversation \(conv.id) has EMPTY title"
        )
      }

      // Sync conversations to local database in background
      Task.detached(priority: .background) {
        var syncedCount = 0
        for conversation in fetchedConversations {
          do {
            try await TranscriptionStorage.shared.syncServerConversation(conversation)
            syncedCount += 1
          } catch {
            log(
              "Conversations: Failed to sync \(conversation.id) to local DB: \(error.localizedDescription)"
            )
          }
        }
        log("Conversations: Synced \(syncedCount)/\(fetchedConversations.count) to local database")
      }
    } catch {
      logError("Conversations: API fetch failed", error: error)
      // Only set error if we don't have cached data
      if conversations.isEmpty {
        conversationsError = error.localizedDescription
      } else {
        log("Conversations: Using cached data after API failure")
      }
    }

    // Update total count from API (more accurate than local)
    do {
      let count = try await countTask
      if requestFiltersAreCurrent() {
        updateConversationCount(count, filtered: requestHasActiveFilters)
        log("Conversations: Count from API = \(count) (filtered=\(requestHasActiveFilters))")
      } else {
        log("Conversations: Ignoring stale count for superseded filters")
      }
    } catch {
      logError("Conversations: Failed to get count from API", error: error)
      // Keep local count if API fails
    }

    isLoadingConversations = false
    NotificationCenter.default.post(name: .conversationsPageDidLoad, object: nil)
    if !requestFiltersAreCurrent() {
      await loadConversations()
    }
  }

  /// Refresh conversations silently (for app-activation and Cmd+R event-driven refreshes).
  /// Fetches from API only, merges in-place, and only triggers @Published if data actually changed.
  func refreshConversations() async {
    // Skip if user is signed out (tokens are cleared)
    guard AuthState.shared.isSignedIn else { return }
    // Skip if in auth backoff period (recent 401 errors)
    guard !AuthBackoffTracker.shared.shouldSkipRequest() else { return }
    // Skip if currently doing a full load
    guard !isLoadingConversations else { return }

    let requestShowStarredOnly = showStarredOnly
    let requestSelectedDateFilter = selectedDateFilter
    let requestSelectedFolderId = selectedFolderId
    let requestHasActiveFilters = hasActiveConversationFilters

    func requestFiltersAreCurrent() -> Bool {
      showStarredOnly == requestShowStarredOnly
        && selectedDateFilter == requestSelectedDateFilter
        && selectedFolderId == requestSelectedFolderId
    }

    // Calculate date range if date filter is set
    let startDate: Date?
    let endDate: Date?
    if let filterDate = requestSelectedDateFilter {
      let calendar = Calendar.current
      startDate = calendar.startOfDay(for: filterDate)
      endDate = calendar.date(byAdding: .day, value: 1, to: startDate!)
    } else {
      startDate = nil
      endDate = nil
    }

    do {
      let fetchedConversations = try await APIClient.shared.getConversations(
        limit: 50,
        offset: 0,
        statuses: [.completed, .processing],
        includeDiscarded: false,
        startDate: startDate,
        endDate: endDate,
        folderId: requestSelectedFolderId,
        starred: requestShowStarredOnly ? true : nil
      )

      if requestFiltersAreCurrent() {
        let reconciliation = ConversationReconciliationPolicy.mergeList(
          server: fetchedConversations,
          current: conversations,
          pendingMutations: pendingConversationMutations
        )
        pendingConversationMutations = reconciliation.pendingMutations
        if reconciliation.conversations != conversations {
          conversations = reconciliation.conversations
          log("Conversations: Auto-refresh updated (\(reconciliation.conversations.count) items)")
        }
      } else {
        log("Conversations: Ignoring stale auto-refresh response for superseded filters")
      }

      // Sync to local database in background
      Task.detached(priority: .background) {
        for conversation in fetchedConversations {
          _ = try? await TranscriptionStorage.shared.syncServerConversation(conversation)
        }
      }
      AuthBackoffTracker.shared.reportSuccess()
    } catch {
      if case APIError.unauthorized = error {
        AuthBackoffTracker.shared.reportAuthFailure()
      }
      // Silently ignore errors during auto-refresh — cached data stays visible.
      // Auth errors (notSignedIn) are transient: token refresh may fail momentarily
      // while the user is still signed in. Don't send these to Sentry.
      if case AuthError.notSignedIn = error {
        log("Conversations: Auto-refresh skipped (auth token temporarily unavailable)")
      } else {
        logError("Conversations: Auto-refresh failed", error: error)
      }
    }

    do {
      let count = try await APIClient.shared.getConversationsCount(
        includeDiscarded: false,
        statuses: [.completed, .processing],
        startDate: startDate,
        endDate: endDate,
        folderId: requestSelectedFolderId,
        starred: requestShowStarredOnly ? true : nil
      )
      if requestFiltersAreCurrent() {
        updateConversationCount(count, filtered: requestHasActiveFilters)
      }
    } catch {
      // Keep existing count
    }
  }

  /// Update the starred status of a conversation locally after a successful mutation.
  func setConversationStarred(_ conversationId: String, starred: Bool) {
    var mutation = pendingConversationMutations[conversationId] ?? ConversationPendingMutation()
    mutation.setStarred(starred)
    pendingConversationMutations[conversationId] = mutation

    if let index = conversations.firstIndex(where: { $0.id == conversationId }) {
      conversations[index].starred = starred
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

  /// Load folders from API
  func loadFolders() async {
    guard !isLoadingFolders else { return }

    isLoadingFolders = true

    do {
      let fetchedFolders = try await APIClient.shared.getFolders()
      folders = fetchedFolders
      log("Folders: Loaded \(fetchedFolders.count) folders")
    } catch {
      logError("Folders: Failed to load", error: error)
    }

    isLoadingFolders = false
  }

  /// Create a new folder
  func createFolder(name: String, description: String? = nil, color: String? = nil) async -> Folder?
  {
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

  /// Move a conversation to a folder
  func moveConversationToFolder(_ conversationId: String, folderId: String?) async {
    do {
      try await APIClient.shared.moveConversationToFolder(
        conversationId: conversationId, folderId: folderId)

      var mutation = pendingConversationMutations[conversationId] ?? ConversationPendingMutation()
      mutation.setFolderId(folderId)
      pendingConversationMutations[conversationId] = mutation

      // Sync to local SQLite cache so reload doesn't revert the change. A cache write failure
      // should not roll back the already-successful backend move or block UI reconciliation.
      do {
        try await TranscriptionStorage.shared.updateFolderByBackendId(
          conversationId, folderId: folderId)
      } catch {
        logError("Folders: Failed to update local folder cache", error: error)
      }

      // Update local state
      if conversations.contains(where: { $0.id == conversationId }) {
        // Reload to get updated conversation
        await loadConversations()
      }
      log("Folders: Moved conversation \(conversationId) to folder \(folderId ?? "none")")
    } catch {
      logError("Folders: Failed to move conversation to folder", error: error)
    }
  }

  /// Delete a conversation locally (after successful API call)
  func deleteConversationLocally(_ conversationId: String) {
    withAnimation {
      conversations.removeAll { $0.id == conversationId }
    }
  }

  /// Update a conversation title locally after a successful mutation.
  func updateConversationTitle(_ conversationId: String, title: String) {
    var mutation = pendingConversationMutations[conversationId] ?? ConversationPendingMutation()
    mutation.setTitle(title)
    pendingConversationMutations[conversationId] = mutation

    if let index = conversations.firstIndex(where: { $0.id == conversationId }) {
      conversations[index].structured.title = title
    }
  }

  // MARK: - People (Speaker Profiles)

  /// Fetches all people from the OMI API
  func fetchPeople() async {
    do {
      let fetchedPeople = try await APIClient.shared.getPeople()
      people = fetchedPeople
      log("People: Loaded \(fetchedPeople.count) people")
    } catch {
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
