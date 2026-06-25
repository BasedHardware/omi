import Foundation

/// Local user edits that have succeeded locally/API-side but may not be reflected
/// in the next eventually-consistent server list response yet.
///
/// The reconciliation layer treats these as short-lived overlays. Everything
/// else in the server list remains authoritative over cache data.
struct ConversationPendingMutation: Equatable {
  var title: String?
  var starred: Bool?
  var recordedAt: Date = Date()
  private(set) var folderId: String?
  private(set) var hasFolderIdMutation: Bool = false

  var isEmpty: Bool {
    title == nil && starred == nil && !hasFolderIdMutation
  }

  mutating func setFolderId(_ folderId: String?) {
    self.folderId = folderId
    hasFolderIdMutation = true
  }

  mutating func clearResolvedFields(matching server: ServerConversation) {
    if title == server.structured.title {
      title = nil
    }
    if starred == server.starred {
      starred = nil
    }
    if hasFolderIdMutation && folderId == server.folderId {
      folderId = nil
      hasFolderIdMutation = false
    }
  }
}

struct ConversationReconciliationResult: Equatable {
  let conversations: [ServerConversation]
  let pendingMutations: [String: ConversationPendingMutation]
}

enum ConversationReconciliationPolicy {
  /// Merge a server-authoritative list response over whatever the UI currently
  /// renders. The server controls list ordering and all non-pending fields;
  /// local state only survives as explicit pending user-edit overlays.
  static func mergeList(
    server: [ServerConversation],
    current: [ServerConversation],
    pendingMutations: [String: ConversationPendingMutation] = [:],
    now: Date = Date(),
    pendingMutationTTL: TimeInterval = 120
  ) -> ConversationReconciliationResult {
    let serverIds = Set(server.map(\.id))
    var nextPending = pendingMutations

    var merged = server.map { serverConversation in
      var mutation = nextPending[serverConversation.id]
      if let pendingMutation = mutation,
        now.timeIntervalSince(pendingMutation.recordedAt) > pendingMutationTTL
      {
        mutation = nil
        nextPending.removeValue(forKey: serverConversation.id)
      }
      let mergedConversation = apply(mutation: mutation, to: serverConversation)
      mutation?.clearResolvedFields(matching: serverConversation)
      if let mutation, !mutation.isEmpty {
        nextPending[serverConversation.id] = mutation
      } else {
        nextPending.removeValue(forKey: serverConversation.id)
      }
      return mergedConversation
    }

    // Preserve genuinely local in-progress rows that have not reached the
    // backend yet. Synced cache rows missing from the server response are not
    // retained, because doing so masks filtered/deleted/backend-updated state.
    let localOnly = current.filter { conversation in
      !serverIds.contains(conversation.id) && shouldPreserveLocalOnly(conversation)
    }
    merged.append(contentsOf: localOnly)

    return ConversationReconciliationResult(
      conversations: merged,
      pendingMutations: nextPending
    )
  }

  static func apply(
    mutation: ConversationPendingMutation?,
    to serverConversation: ServerConversation
  ) -> ServerConversation {
    guard let mutation, !mutation.isEmpty else {
      return serverConversation
    }

    var structured = serverConversation.structured
    if let title = mutation.title {
      structured.title = title
    }

    return ServerConversation(
      id: serverConversation.id,
      createdAt: serverConversation.createdAt,
      startedAt: serverConversation.startedAt,
      finishedAt: serverConversation.finishedAt,
      structured: structured,
      transcriptSegments: serverConversation.transcriptSegments,
      geolocation: serverConversation.geolocation,
      photos: serverConversation.photos,
      appsResults: serverConversation.appsResults,
      source: serverConversation.source,
      language: serverConversation.language,
      status: serverConversation.status,
      discarded: serverConversation.discarded,
      deleted: serverConversation.deleted,
      isLocked: serverConversation.isLocked,
      starred: mutation.starred ?? serverConversation.starred,
      folderId: mutation.hasFolderIdMutation ? mutation.folderId : serverConversation.folderId,
      inputDeviceName: serverConversation.inputDeviceName,
      deferred: serverConversation.deferred
    )
  }

  private static func shouldPreserveLocalOnly(_ conversation: ServerConversation) -> Bool {
    conversation.status == .inProgress && !conversation.deleted && !conversation.discarded
  }
}
