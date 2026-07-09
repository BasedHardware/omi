import Foundation

/// Local user edits that have succeeded locally/API-side but may not be reflected
/// in the next eventually-consistent server list response yet.
///
/// The reconciliation layer treats these as short-lived overlays. Everything
/// else in the server list remains authoritative over cache data.
///
/// Each field carries its own `recordedAt` so that a later star or folder change
/// does not accidentally refresh the TTL of an older title overlay (and vice-versa).
struct ConversationPendingMutation: Codable, Equatable, Sendable {
  var title: String?
  var starred: Bool?
  var titleRecordedAt: Date?
  var starredRecordedAt: Date?
  private(set) var folderId: String?
  private(set) var hasFolderIdMutation: Bool = false
  private(set) var folderIdRecordedAt: Date?

  var isEmpty: Bool {
    title == nil && starred == nil && !hasFolderIdMutation
  }

  mutating func setTitle(_ title: String?) {
    self.title = title
    titleRecordedAt = Date()
  }

  mutating func setStarred(_ starred: Bool) {
    self.starred = starred
    starredRecordedAt = Date()
  }

  mutating func setFolderId(_ folderId: String?) {
    self.folderId = folderId
    hasFolderIdMutation = true
    folderIdRecordedAt = Date()
  }

  /// Expire individual fields whose TTL has elapsed. The whole mutation is
  /// removed once every field has either resolved or expired.
  mutating func expireFields(now: Date, ttl: TimeInterval) {
    if title != nil, let recorded = titleRecordedAt,
       now.timeIntervalSince(recorded) > ttl {
      title = nil
      titleRecordedAt = nil
    }
    if starred != nil, let recorded = starredRecordedAt,
       now.timeIntervalSince(recorded) > ttl {
      starred = nil
      starredRecordedAt = nil
    }
    if hasFolderIdMutation, let recorded = folderIdRecordedAt,
       now.timeIntervalSince(recorded) > ttl {
      folderId = nil
      hasFolderIdMutation = false
      folderIdRecordedAt = nil
    }
  }

  mutating func clearResolvedFields(matching server: ServerConversation) {
    if title == server.structured.title {
      title = nil
      titleRecordedAt = nil
    }
    if starred == server.starred {
      starred = nil
      starredRecordedAt = nil
    }
    if hasFolderIdMutation && folderId == server.folderId {
      folderId = nil
      hasFolderIdMutation = false
      folderIdRecordedAt = nil
    }
  }

  mutating func clearAcknowledged(_ value: ConversationMutationValue) {
    switch value {
    case .title(let acknowledged) where title == acknowledged:
      title = nil
      titleRecordedAt = nil
    case .starred(let acknowledged) where starred == acknowledged:
      starred = nil
      starredRecordedAt = nil
    case .folder(let acknowledged) where hasFolderIdMutation && folderId == acknowledged:
      folderId = nil
      hasFolderIdMutation = false
      folderIdRecordedAt = nil
    default:
      break
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

    // Per-field TTL expiration: each overlay field is independently evaluated
    // so a recent star change doesn't keep an older title overlay alive.
    for id in nextPending.keys {
      nextPending[id]?.expireFields(now: now, ttl: pendingMutationTTL)
      if nextPending[id]?.isEmpty ?? true {
        nextPending.removeValue(forKey: id)
      }
    }

    var merged = server.map { serverConversation in
      var mutation = nextPending[serverConversation.id]
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
      transcriptSegmentsIncluded: serverConversation.transcriptSegmentsIncluded,
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
      deferred: serverConversation.deferred,
      updatedAt: serverConversation.updatedAt,
      revision: serverConversation.revision
    )
  }

  private static func shouldPreserveLocalOnly(_ conversation: ServerConversation) -> Bool {
    conversation.status == .inProgress && !conversation.deleted && !conversation.discarded
  }
}
