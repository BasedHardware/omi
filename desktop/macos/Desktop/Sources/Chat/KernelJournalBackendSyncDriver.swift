import Foundation

/// Per-conversation reader/writer barrier for physical backend transport.
///
/// Sync POSTs may overlap each other, but DELETE is exclusive and has priority
/// once requested. Keeping this below the durable kernel outbox closes the
/// final URLSession race: an old-generation POST cannot land after DELETE, and
/// a new-generation POST cannot start until every queued DELETE has settled.
actor KernelJournalConversationBarrier {
  struct Snapshot: Equatable, Sendable {
    let activeSyncCount: Int
    let isDeleting: Bool
    let queuedDeleteCount: Int
    let queuedSyncCount: Int
    let syncDrainWaiterCount: Int
  }

  private var activeSyncCountByConversation: [String: Int] = [:]
  private var activeSyncDrainWaiters: [String: [CheckedContinuation<Void, Never>]] = [:]
  private var deletingConversations: Set<String> = []
  private var queuedDeleteWaiters: [String: [CheckedContinuation<Void, Never>]] = [:]
  private var queuedSyncWaiters: [String: [CheckedContinuation<Void, Never>]] = [:]

  func beginSync(conversationId: String) async {
    while deletingConversations.contains(conversationId) {
      await withCheckedContinuation { continuation in
        queuedSyncWaiters[conversationId, default: []].append(continuation)
      }
    }
    activeSyncCountByConversation[conversationId, default: 0] += 1
  }

  func endSync(conversationId: String) {
    let remaining = max(0, (activeSyncCountByConversation[conversationId] ?? 1) - 1)
    if remaining > 0 {
      activeSyncCountByConversation[conversationId] = remaining
      return
    }
    activeSyncCountByConversation.removeValue(forKey: conversationId)
    let waiters = activeSyncDrainWaiters.removeValue(forKey: conversationId) ?? []
    for waiter in waiters { waiter.resume() }
  }

  func beginDelete(conversationId: String) async {
    if deletingConversations.contains(conversationId) {
      // Ownership is handed directly to this waiter by endDelete. The set
      // intentionally stays populated so no sync can slip between deletes.
      await withCheckedContinuation { continuation in
        queuedDeleteWaiters[conversationId, default: []].append(continuation)
      }
    } else {
      deletingConversations.insert(conversationId)
    }

    guard (activeSyncCountByConversation[conversationId] ?? 0) > 0 else { return }
    await withCheckedContinuation { continuation in
      activeSyncDrainWaiters[conversationId, default: []].append(continuation)
    }
  }

  func endDelete(conversationId: String) {
    if var deleteWaiters = queuedDeleteWaiters[conversationId], !deleteWaiters.isEmpty {
      let next = deleteWaiters.removeFirst()
      if deleteWaiters.isEmpty {
        queuedDeleteWaiters.removeValue(forKey: conversationId)
      } else {
        queuedDeleteWaiters[conversationId] = deleteWaiters
      }
      next.resume()
      return
    }

    deletingConversations.remove(conversationId)
    let syncWaiters = queuedSyncWaiters.removeValue(forKey: conversationId) ?? []
    for waiter in syncWaiters { waiter.resume() }
  }

  func snapshot(conversationId: String) -> Snapshot {
    Snapshot(
      activeSyncCount: activeSyncCountByConversation[conversationId] ?? 0,
      isDeleting: deletingConversations.contains(conversationId),
      queuedDeleteCount: queuedDeleteWaiters[conversationId]?.count ?? 0,
      queuedSyncCount: queuedSyncWaiters[conversationId]?.count ?? 0,
      syncDrainWaiterCount: activeSyncDrainWaiters[conversationId]?.count ?? 0
    )
  }
}

/// Physical backend transport for the kernel-owned outbox. This is the only
/// Swift caller allowed to POST durable chat turns; retry, ordering, and
/// acknowledgement state remain in omi-agentd.
actor KernelJournalBackendSyncDriver {
  static let shared = KernelJournalBackendSyncDriver()

  private let conversationBarrier = KernelJournalConversationBarrier()

  struct Request: Sendable, Equatable {
    let ownerId: String
    let turnId: String
    let conversationId: String
    let clientMessageId: String
    let conversationGeneration: Int
    let attemptCount: Int
    let deliveryGeneration: Int
    let payloadHash: String
    let text: String
    let sender: String
    let appId: String?
    let sessionId: String?
    let metadata: String?
    let messageSource: String

    init?(payload: [String: Any]) {
      guard
        let ownerId = payload["ownerId"] as? String,
        !ownerId.isEmpty,
        let turnId = payload["turnId"] as? String,
        !turnId.isEmpty,
        let conversationId = payload["conversationId"] as? String,
        !conversationId.isEmpty,
        let clientMessageId = payload["clientMessageId"] as? String,
        clientMessageId == turnId,
        let conversationGeneration = payload["conversationGeneration"] as? Int,
        conversationGeneration > 0,
        let attemptCount = payload["attemptCount"] as? Int,
        attemptCount > 0,
        let deliveryGeneration = payload["deliveryGeneration"] as? Int,
        deliveryGeneration > 0,
        let payloadHash = payload["payloadHash"] as? String,
        !payloadHash.isEmpty,
        let text = payload["text"] as? String,
        let sender = payload["sender"] as? String,
        ["human", "ai"].contains(sender),
        let messageSource = payload["messageSource"] as? String,
        ["desktop_chat", "realtime_voice"].contains(messageSource)
      else { return nil }
      self.ownerId = ownerId
      self.turnId = turnId
      self.conversationId = conversationId
      self.clientMessageId = clientMessageId
      self.conversationGeneration = conversationGeneration
      self.attemptCount = attemptCount
      self.deliveryGeneration = deliveryGeneration
      self.payloadHash = payloadHash
      self.text = text
      self.sender = sender
      self.appId = payload["appId"] as? String
      self.sessionId = payload["sessionId"] as? String
      self.metadata = payload["metadata"] as? String
      self.messageSource = messageSource
    }
  }

  struct Receipt: Sendable, Equatable {
    let turnId: String
    let remoteId: String
  }

  enum DeleteTargetKind: String, Sendable {
    case messages
    case chatSession = "chat_session"
  }

  struct DeleteRequest: Sendable, Equatable {
    let ownerId: String
    let operationId: String
    let conversationId: String
    let conversationGeneration: Int
    let attemptCount: Int
    let deliveryGeneration: Int
    let payloadHash: String
    let targetKind: DeleteTargetKind
    let targetId: String?

    init?(payload: [String: Any]) {
      guard
        let ownerId = payload["ownerId"] as? String,
        !ownerId.isEmpty,
        let operationId = payload["operationId"] as? String,
        !operationId.isEmpty,
        let conversationId = payload["conversationId"] as? String,
        !conversationId.isEmpty,
        let conversationGeneration = payload["conversationGeneration"] as? Int,
        conversationGeneration > 0,
        let attemptCount = payload["attemptCount"] as? Int,
        attemptCount > 0,
        let deliveryGeneration = payload["deliveryGeneration"] as? Int,
        deliveryGeneration > 0,
        let payloadHash = payload["payloadHash"] as? String,
        !payloadHash.isEmpty,
        let rawTargetKind = payload["targetKind"] as? String,
        let targetKind = DeleteTargetKind(rawValue: rawTargetKind)
      else { return nil }

      let targetId = (payload["targetId"] as? String)?
        .trimmingCharacters(in: .whitespacesAndNewlines)
      switch targetKind {
      case .messages:
        break
      case .chatSession:
        guard let targetId, !targetId.isEmpty else { return nil }
      }

      self.ownerId = ownerId
      self.operationId = operationId
      self.conversationId = conversationId
      self.conversationGeneration = conversationGeneration
      self.attemptCount = attemptCount
      self.deliveryGeneration = deliveryGeneration
      self.payloadHash = payloadHash
      self.targetKind = targetKind
      self.targetId = targetId.flatMap { $0.isEmpty ? nil : $0 }
    }
  }

  struct ReconcileRequest: Sendable, Equatable {
    let ownerId: String
    let reconcileId: String
    let conversationId: String
    let targetKind: DeleteTargetKind
    let targetId: String?
    let pageCursor: String?
    let pageLimit: Int

    init?(payload: [String: Any]) {
      guard
        let ownerId = payload["ownerId"] as? String,
        !ownerId.isEmpty,
        let reconcileId = payload["reconcileId"] as? String,
        !reconcileId.isEmpty,
        let conversationId = payload["conversationId"] as? String,
        !conversationId.isEmpty,
        let rawTargetKind = payload["targetKind"] as? String,
        let targetKind = DeleteTargetKind(rawValue: rawTargetKind),
        let pageLimit = payload["pageLimit"] as? Int,
        (1...100).contains(pageLimit)
      else { return nil }
      let pageCursor: String?
      if payload["pageCursor"] is NSNull || payload["pageCursor"] == nil {
        pageCursor = nil
      } else if let rawCursor = payload["pageCursor"] as? String {
        let trimmed = rawCursor.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty, trimmed.count <= 200 else { return nil }
        pageCursor = trimmed
      } else {
        return nil
      }
      let targetId = (payload["targetId"] as? String)?
        .trimmingCharacters(in: .whitespacesAndNewlines)
      if targetKind == .chatSession, targetId?.isEmpty != false { return nil }

      self.ownerId = ownerId
      self.reconcileId = reconcileId
      self.conversationId = conversationId
      self.targetKind = targetKind
      self.targetId = targetId.flatMap { $0.isEmpty ? nil : $0 }
      self.pageCursor = pageCursor
      self.pageLimit = pageLimit
    }
  }

  struct ReconcilePage: Sendable {
    let request: ReconcileRequest
    let turns: [ReconcileTurn]
    let nextCursor: String?
    let hasMore: Bool
  }

  struct ReconcileTurn: Sendable, Equatable {
    let remoteId: String
    let canonicalTurnId: String?
    let role: String
    let content: String
    let contentBlocksJSON: String
    let resourcesJSON: String
    let metadataJSON: String
    let createdAtMs: Int

    var dictionary: [String: Any] {
      [
        "remoteId": remoteId,
        "canonicalTurnId": canonicalTurnId ?? NSNull(),
        "role": role,
        "content": content,
        "contentBlocks": Self.array(from: contentBlocksJSON),
        "resources": Self.array(from: resourcesJSON),
        "metadataJson": metadataJSON,
        "createdAtMs": createdAtMs,
      ]
    }

    private static func array(from json: String) -> [[String: Any]] {
      guard let data = json.data(using: .utf8),
            let array = try? JSONSerialization.jsonObject(with: data) as? [[String: Any]]
      else { return [] }
      return array
    }
  }

  private enum SyncError: Error, Equatable {
    case ownerChanged
  }

  nonisolated static func boundedErrorCode(for error: Error) -> String {
    if let error = error as? SyncError, error == .ownerChanged {
      return "backend_sync_owner_changed"
    }
    if let authError = error as? AuthError, case .userChangedDuringRequest = authError {
      return "backend_sync_owner_changed"
    }
    if case let APIError.httpError(statusCode, _) = error,
       (400...499).contains(statusCode)
    {
      if [408, 425, 429].contains(statusCode) {
        return "backend_sync_http_retryable"
      }
      return "backend_sync_http_4xx"
    }
    return "backend_sync_failed"
  }

  nonisolated static func boundedDeleteErrorCode(for error: Error) -> String {
    if let error = error as? SyncError, error == .ownerChanged {
      return "backend_sync_owner_changed"
    }
    if let authError = error as? AuthError, case .userChangedDuringRequest = authError {
      return "backend_sync_owner_changed"
    }
    if case let APIError.httpError(statusCode, _) = error,
       (400...499).contains(statusCode)
    {
      if [408, 425, 429].contains(statusCode) {
        return "backend_sync_http_retryable"
      }
      return "backend_delete_http_4xx"
    }
    return "backend_delete_failed"
  }

  nonisolated static func boundedReconcileErrorCode(for error: Error) -> String {
    if let error = error as? SyncError, error == .ownerChanged {
      return "backend_sync_owner_changed"
    }
    if let authError = error as? AuthError, case .userChangedDuringRequest = authError {
      return "backend_sync_owner_changed"
    }
    if case let APIError.httpError(statusCode, _) = error,
       (400...499).contains(statusCode),
       ![408, 425, 429].contains(statusCode)
    {
      return "backend_reconcile_http_4xx"
    }
    return "backend_reconcile_failed"
  }

  func sync(_ request: Request) async throws -> Receipt {
    guard RuntimeOwnerIdentity.currentOwnerId() == request.ownerId else {
      throw SyncError.ownerChanged
    }
    await conversationBarrier.beginSync(conversationId: request.conversationId)
    let response: SaveMessageResponse
    do {
      response = try await APIClient.shared.saveMessage(
        text: request.text,
        sender: request.sender,
        appId: request.appId,
        sessionId: request.sessionId,
        metadata: request.metadata,
        clientMessageId: request.turnId,
        messageSource: request.messageSource,
        expectedOwnerId: request.ownerId
      )
    } catch {
      await conversationBarrier.endSync(conversationId: request.conversationId)
      throw error
    }
    await conversationBarrier.endSync(conversationId: request.conversationId)
    guard RuntimeOwnerIdentity.currentOwnerId() == request.ownerId else {
      throw SyncError.ownerChanged
    }
    return Receipt(turnId: request.turnId, remoteId: response.id)
  }

  func delete(_ request: DeleteRequest) async throws {
    guard RuntimeOwnerIdentity.currentOwnerId() == request.ownerId else {
      throw SyncError.ownerChanged
    }
    await conversationBarrier.beginDelete(conversationId: request.conversationId)
    guard RuntimeOwnerIdentity.currentOwnerId() == request.ownerId else {
      await conversationBarrier.endDelete(conversationId: request.conversationId)
      throw SyncError.ownerChanged
    }

    do {
      do {
        switch request.targetKind {
        case .messages:
          _ = try await APIClient.shared.deleteMessages(
            appId: request.targetId,
            expectedOwnerId: request.ownerId
          )
        case .chatSession:
          guard let targetId = request.targetId else {
            await conversationBarrier.endDelete(conversationId: request.conversationId)
            return
          }
          try await APIClient.shared.deleteChatSession(
            sessionId: targetId,
            expectedOwnerId: request.ownerId
          )
        }
      } catch APIError.httpError(statusCode: 404, detail: _) {
        // Durable deletion is idempotent: an already-absent backend target is
        // the requested terminal state and may be acknowledged safely.
      }

      guard RuntimeOwnerIdentity.currentOwnerId() == request.ownerId else {
        throw SyncError.ownerChanged
      }
      await conversationBarrier.endDelete(conversationId: request.conversationId)
    } catch {
      await conversationBarrier.endDelete(conversationId: request.conversationId)
      throw error
    }
  }

  func reconcile(_ request: ReconcileRequest) async throws -> ReconcilePage {
    guard RuntimeOwnerIdentity.currentOwnerId() == request.ownerId else {
      throw SyncError.ownerChanged
    }
    let page: DesktopMessageReconcilePage
    switch request.targetKind {
    case .messages:
      page = try await APIClient.shared.getMessagesReconcilePage(
        appId: request.targetId,
        limit: request.pageLimit,
        cursor: request.pageCursor,
        expectedOwnerId: request.ownerId
      )
    case .chatSession:
      guard let targetId = request.targetId else {
        throw APIError.invalidResponse
      }
      page = try await APIClient.shared.getMessagesReconcilePage(
        sessionId: targetId,
        limit: request.pageLimit,
        cursor: request.pageCursor,
        expectedOwnerId: request.ownerId
      )
    }
    guard RuntimeOwnerIdentity.currentOwnerId() == request.ownerId else {
      throw SyncError.ownerChanged
    }
    return ReconcilePage(
      request: request,
      turns: page.messages.map(Self.reconcileProjection),
      nextCursor: page.nextCursor,
      hasMore: page.hasMore
    )
  }

  private nonisolated static func reconcileProjection(_ row: ChatMessageDB) -> ReconcileTurn {
    let metadata = metadataProjection(row.metadata)
    return ReconcileTurn(
      remoteId: row.id,
      canonicalTurnId: row.clientMessageId.flatMap { $0.isEmpty ? nil : $0 },
      role: row.sender == "ai" || row.sender == "assistant" ? "assistant" : "user",
      content: row.text,
      contentBlocksJSON: metadata.contentBlocksJSON,
      resourcesJSON: metadata.resourcesJSON,
      metadataJSON: row.metadata ?? "{}",
      createdAtMs: Int(row.createdAt.timeIntervalSince1970 * 1_000)
    )
  }

  private nonisolated static func metadataProjection(
    _ metadataJSON: String?
  ) -> (contentBlocksJSON: String, resourcesJSON: String) {
    guard let metadataJSON,
          let data = metadataJSON.data(using: .utf8),
          let root = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
    else { return ("[]", "[]") }
    return (
      jsonArrayString(root[ChatContentBlockCodec.messageMetadataKey]),
      jsonArrayString(root[ChatResource.messageMetadataResourcesKey])
    )
  }

  private nonisolated static func jsonArrayString(_ value: Any?) -> String {
    guard let array = value as? [[String: Any]],
          JSONSerialization.isValidJSONObject(array),
          let data = try? JSONSerialization.data(withJSONObject: array, options: [.sortedKeys]),
          let json = String(data: data, encoding: .utf8)
    else { return "[]" }
    return json
  }
}
