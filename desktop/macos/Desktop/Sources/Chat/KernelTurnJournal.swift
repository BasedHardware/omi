import Foundation

enum KernelJournalTurnStatus: String, Sendable {
  case pending
  case streaming
  case completed
  case failed
}

/// Sendable wire projection of one kernel-owned journal row. Structured UI
/// payloads stay encoded while crossing the runtime actor boundary and are
/// decoded only on MainActor.
struct KernelJournalTurn: Sendable, Equatable {
  let conversationId: String
  let turnId: String
  let turnSeq: Int
  let conversationGeneration: Int
  let generationBaseTurnSeq: Int
  let producerId: String
  let payloadHash: String
  let role: String
  let surfaceKind: String
  let externalRefKind: String
  let externalRefId: String
  let content: String
  let origin: String
  let status: KernelJournalTurnStatus
  let contentBlocksJSON: String
  let resourcesJSON: String
  let producingRunId: String?
  let producingAttemptId: String?
  let remoteId: String?
  let metadataJSON: String
  let createdAtMs: Int
  let updatedAtMs: Int
  let completedAtMs: Int?

  init?(
    dictionary: [String: Any],
    surfaceFallback: AgentSurfaceReference? = nil,
    conversationGenerationFallback: Int = 1,
    generationBaseTurnSeqFallback: Int = 0
  ) {
    guard
      let turnId = dictionary["turnId"] as? String,
      !turnId.isEmpty,
      let role = dictionary["role"] as? String,
      let content = dictionary["content"] as? String,
      let rawStatus = dictionary["status"] as? String,
      let status = KernelJournalTurnStatus(rawValue: rawStatus)
    else { return nil }

    self.conversationId = dictionary["conversationId"] as? String ?? ""
    self.turnId = turnId
    self.turnSeq = Self.int(dictionary["turnSeq"]) ?? 0
    self.conversationGeneration =
      Self.int(dictionary["conversationGeneration"])
      ?? conversationGenerationFallback
    self.generationBaseTurnSeq =
      Self.int(dictionary["generationBaseTurnSeq"])
      ?? generationBaseTurnSeqFallback
    self.producerId = dictionary["producerId"] as? String ?? ""
    self.payloadHash = dictionary["payloadHash"] as? String ?? ""
    self.role = role
    self.surfaceKind = dictionary["surfaceKind"] as? String ?? surfaceFallback?.surfaceKind ?? ""
    self.externalRefKind =
      dictionary["externalRefKind"] as? String
      ?? surfaceFallback?.externalRefKind ?? ""
    self.externalRefId =
      dictionary["externalRefId"] as? String
      ?? surfaceFallback?.externalRefId ?? ""
    self.content = content
    self.origin = dictionary["origin"] as? String ?? "legacy"
    self.status = status
    self.contentBlocksJSON = Self.jsonArrayString(dictionary["contentBlocks"])
    self.resourcesJSON = Self.jsonArrayString(dictionary["resources"])
    self.producingRunId = dictionary["producingRunId"] as? String
    self.producingAttemptId = dictionary["producingAttemptId"] as? String
    self.remoteId = dictionary["remoteId"] as? String
    self.metadataJSON = dictionary["metadataJson"] as? String ?? "{}"
    self.createdAtMs = Self.int(dictionary["createdAtMs"]) ?? 0
    self.updatedAtMs = Self.int(dictionary["updatedAtMs"]) ?? self.createdAtMs
    self.completedAtMs = Self.int(dictionary["completedAtMs"])
  }

  private static func int(_ value: Any?) -> Int? {
    if let value = value as? Int { return value }
    if let value = value as? NSNumber { return value.intValue }
    return nil
  }

  private static func jsonArrayString(_ value: Any?) -> String {
    guard let array = value as? [Any],
      JSONSerialization.isValidJSONObject(array),
      let data = try? JSONSerialization.data(withJSONObject: array),
      let encoded = String(data: data, encoding: .utf8)
    else { return "[]" }
    return encoded
  }
}

/// Deterministic replay gate shared by every Swift journal projection. Runtime
/// notifications can be duplicated or reordered; only a contiguous range may
/// advance a projection checkpoint.
enum KernelJournalReplay {
  static func contiguousTurns(
    from candidates: [KernelJournalTurn],
    after checkpoint: Int
  ) -> [KernelJournalTurn] {
    var expected = checkpoint + 1
    var accepted: [KernelJournalTurn] = []
    for turn in candidates.sorted(by: {
      $0.turnSeq == $1.turnSeq ? $0.turnId < $1.turnId : $0.turnSeq < $1.turnSeq
    }) where turn.turnSeq > checkpoint {
      guard turn.turnSeq == expected else { break }
      accepted.append(turn)
      expected += 1
    }
    return accepted
  }
}

struct KernelJournalTurnWrite: Sendable {
  let turnId: String
  let role: String
  let origin: String
  let status: KernelJournalTurnStatus
  let content: String
  let contentBlocksJSON: String
  let resourcesJSON: String
  let metadataJSON: String
  let createdAtMs: Int

  var dictionary: [String: Any] {
    [
      "turnId": turnId,
      "role": role,
      "origin": origin,
      "status": status.rawValue,
      "content": content,
      "contentBlocks": Self.jsonArray(contentBlocksJSON),
      "resources": Self.jsonArray(resourcesJSON),
      "metadataJson": metadataJSON,
      "createdAtMs": createdAtMs,
    ]
  }

  static func jsonArray(_ raw: String) -> [Any] {
    guard let data = raw.data(using: .utf8),
      let value = try? JSONSerialization.jsonObject(with: data) as? [Any]
    else { return [] }
    return value
  }
}

struct KernelJournalTurnUpdate: Sendable {
  let turnId: String
  let status: KernelJournalTurnStatus?
  let content: String?
  let contentBlocksJSON: String?
  let appendContentBlocksJSON: String?
  let resourcesJSON: String?
  let appendResourcesJSON: String?
  let metadataJSON: String?
  /// Narrow authority flag for revising an optimistically sealed terminal row:
  /// the same desktop client that sealed a row `.completed` before delivery
  /// resolved may downgrade it to `.failed` when the answer never reached the
  /// user (#12743). The kernel accepts this only as a payload-free downgrade
  /// and merges — never replaces — the row's existing metadata.
  let terminalRevision: Bool

  /// A terminal lifecycle update that deliberately carries no response
  /// payload. This is used after stop/supersession when the visible projection
  /// may already have removed its empty placeholder: the existing journal row
  /// still becomes terminal, but a late adapter result cannot be copied into it.
  static func statusOnly(
    turnId: String,
    status: KernelJournalTurnStatus
  ) -> KernelJournalTurnUpdate {
    KernelJournalTurnUpdate(
      turnId: turnId,
      status: status,
      content: nil,
      contentBlocksJSON: nil,
      appendContentBlocksJSON: nil,
      resourcesJSON: nil,
      appendResourcesJSON: nil,
      metadataJSON: nil,
      terminalRevision: false
    )
  }

  /// Downgrades an optimistically sealed `.completed` row to `.failed` with
  /// its truncation cause, carrying no payload: content, content blocks,
  /// resources, and existing metadata (model attribution, continuity) stay
  /// untouched while `terminalReason` merges into the row's metadata.
  static func sealedTerminalRevision(
    turnId: String,
    terminalReason: String
  ) -> KernelJournalTurnUpdate {
    let encodedReason: String
    if let data = try? JSONSerialization.data(withJSONObject: ["terminalReason": terminalReason]),
      let encoded = String(data: data, encoding: .utf8)
    {
      encodedReason = encoded
    } else {
      encodedReason = "{}"
    }
    return KernelJournalTurnUpdate(
      turnId: turnId,
      status: .failed,
      content: nil,
      contentBlocksJSON: nil,
      appendContentBlocksJSON: nil,
      resourcesJSON: nil,
      appendResourcesJSON: nil,
      metadataJSON: encodedReason,
      terminalRevision: true
    )
  }

  var dictionary: [String: Any] {
    var value: [String: Any] = ["turnId": turnId]
    if let status { value["status"] = status.rawValue }
    if let content { value["content"] = content }
    if let contentBlocksJSON {
      value["replaceContentBlocks"] = KernelJournalTurnWrite.jsonArray(contentBlocksJSON)
    }
    if let appendContentBlocksJSON {
      value["appendContentBlocks"] = KernelJournalTurnWrite.jsonArray(appendContentBlocksJSON)
    }
    if let resourcesJSON {
      value["replaceResources"] = KernelJournalTurnWrite.jsonArray(resourcesJSON)
    }
    if let appendResourcesJSON {
      value["appendResources"] = KernelJournalTurnWrite.jsonArray(appendResourcesJSON)
    }
    if let metadataJSON { value["metadataJson"] = metadataJSON }
    if terminalRevision { value["terminalRevision"] = true }
    return value
  }
}

enum KernelJournalTerminalDisposition: String, Sendable {
  case accept
  case discard
}

struct KernelJournalTurnTerminalization: Sendable {
  let turnId: String
  let producingRunId: String
  let producingAttemptId: String
  let disposition: KernelJournalTerminalDisposition
  let content: String?
  let contentBlocksJSON: String?
  let resourcesJSON: String?

  var dictionary: [String: Any] {
    var value: [String: Any] = [
      "turnId": turnId,
      "producingRunId": producingRunId,
      "producingAttemptId": producingAttemptId,
      "disposition": disposition.rawValue,
    ]
    if let content { value["content"] = content }
    if let contentBlocksJSON {
      value["replaceContentBlocks"] = KernelJournalTurnWrite.jsonArray(contentBlocksJSON)
    }
    if let resourcesJSON {
      value["replaceResources"] = KernelJournalTurnWrite.jsonArray(resourcesJSON)
    }
    return value
  }
}

struct KernelJournalRemoteTurn: Sendable {
  let remoteId: String
  let canonicalTurnId: String?
  let role: String
  let content: String
  let contentBlocksJSON: String
  let resourcesJSON: String
  let metadataJSON: String
  let createdAtMs: Int

  var dictionary: [String: Any] {
    var value: [String: Any] = [
      "remoteId": remoteId,
      "role": role,
      "content": content,
      "contentBlocks": KernelJournalTurnWrite.jsonArray(contentBlocksJSON),
      "resources": KernelJournalTurnWrite.jsonArray(resourcesJSON),
      "metadataJson": Self.normalizedMetadataObject(metadataJSON),
      "createdAtMs": createdAtMs,
    ]
    if let canonicalTurnId { value["canonicalTurnId"] = canonicalTurnId }
    return value
  }

  private static func normalizedMetadataObject(_ raw: String) -> String {
    guard let data = raw.data(using: .utf8),
      let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
      JSONSerialization.isValidJSONObject(object),
      let normalized = try? JSONSerialization.data(withJSONObject: object),
      let encoded = String(data: normalized, encoding: .utf8)
    else { return "{}" }
    return encoded
  }
}

@MainActor
extension KernelJournalTurn {
  func chatMessage() -> ChatMessage {
    let metadata = Self.metadataObject(metadataJSON)
    let continuityKey =
      (metadata["continuityKey"] as? String)
      ?? (metadata["idempotencyKey"] as? String)
    let owner: ChatTurnOwner?
    switch origin {
    case "realtime_voice": owner = .floatingVoice
    case "floating_chat": owner = .floatingDefault
    case "task_chat", "workstream": owner = .taskChat(externalRefId)
    default: owner = .mainChat
    }
    var message = ChatMessage(
      id: turnId,
      clientTurnId: continuityKey,
      text: content,
      createdAt: Date(timeIntervalSince1970: TimeInterval(createdAtMs) / 1_000),
      sender: role == "user" ? .user : .ai,
      isStreaming: status == .pending || status == .streaming,
      isSynced: remoteId != nil,
      contentBlocks: ChatContentBlockCodec.mergingCitationBackup(
        ChatContentBlockCodec.decode(contentBlocksJSON) ?? [],
        backup: ChatContentBlockCodec.decodeFromMessageMetadata(metadataJSON)
      ),
      notificationContext: metadata["notificationContext"] as? String,
      resources: ChatResource.hydrateFileStates(
        ChatResource.decodeResourcesFromPersistence(resourcesJSON)
      ),
      turnOwner: owner,
      journalStatus: status,
      hidesEmptyStreamingPlaceholder: metadata["hiddenUntilOutput"] as? Bool ?? false
    )
    // Persisted served-model attribution: lets a journaled voice turn (or a
    // restored one) show the Response Context Model row that in-memory
    // metadata would otherwise lose.
    if message.sender == .ai, let models = metadata["modelsUsed"] as? [String], !models.isEmpty {
      message.metadata = MessageMetadata(
        adapterId: origin == "realtime_voice" ? "realtime" : "",
        modelsUsed: models
      )
    }
    return message
  }

  private static func metadataObject(_ raw: String) -> [String: Any] {
    guard let data = raw.data(using: .utf8),
      let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
    else { return [:] }
    return object
  }
}

@MainActor
extension ChatMessage {
  func journalWrite(
    origin: String,
    status: KernelJournalTurnStatus,
    continuityKey: String? = nil,
    appId: String? = nil,
    sessionId: String? = nil,
    messageSource: String? = nil,
    terminalReason: String? = nil
  ) -> KernelJournalTurnWrite {
    var metadata: [String: Any] = [:]
    if let continuityKey, !continuityKey.isEmpty { metadata["continuityKey"] = continuityKey }
    if let models = self.metadata?.modelsUsed, !models.isEmpty { metadata["modelsUsed"] = models }
    if let notificationContext { metadata["notificationContext"] = notificationContext }
    if let screenContext = self.metadata?.screenContext, !screenContext.isEmpty {
      metadata["screen_context"] = String(screenContext.prefix(1_200))
    }
    // These rollback-compatible fields are consumed only by the kernel outbox
    // renderer for the existing /v2/desktop/messages POST shape.
    if let appId { metadata["appId"] = appId }
    if let sessionId { metadata["sessionId"] = sessionId }
    if let messageSource { metadata["messageSource"] = messageSource }
    if let terminalReason { metadata["terminalReason"] = terminalReason }
    let metadataJSON: String
    let encodedMetadata: String
    if let data = try? JSONSerialization.data(withJSONObject: metadata),
      let encoded = String(data: data, encoding: .utf8)
    {
      encodedMetadata = encoded
    } else {
      encodedMetadata = "{}"
    }
    metadataJSON =
      ChatContentBlockCodec.mergeIntoMessageMetadata(
        encodedMetadata,
        contentBlocks: ChatContentBlockCodec.citationBlocks(in: contentBlocks)
      ) ?? encodedMetadata
    return KernelJournalTurnWrite(
      turnId: id,
      role: sender == .user ? "user" : "assistant",
      origin: origin,
      status: status,
      content: text,
      contentBlocksJSON: ChatContentBlockCodec.encode(contentBlocks) ?? "[]",
      resourcesJSON: ChatResource.encodeResourcesForPersistence(displayResources) ?? "[]",
      metadataJSON: metadataJSON,
      createdAtMs: Int(createdAt.timeIntervalSince1970 * 1_000)
    )
  }

  func journalUpdate(
    status: KernelJournalTurnStatus? = nil,
    terminalReason: String? = nil
  ) -> KernelJournalTurnUpdate {
    var metadataJSON: String?
    if let terminalReason,
      let data = try? JSONSerialization.data(withJSONObject: ["terminalReason": terminalReason]),
      let encoded = String(data: data, encoding: .utf8)
    {
      metadataJSON = encoded
    }
    return KernelJournalTurnUpdate(
      turnId: id,
      status: status,
      content: text,
      contentBlocksJSON: ChatContentBlockCodec.encode(contentBlocks) ?? "[]",
      appendContentBlocksJSON: nil,
      resourcesJSON: ChatResource.encodeResourcesForPersistence(displayResources) ?? "[]",
      appendResourcesJSON: nil,
      metadataJSON: metadataJSON,
      terminalRevision: false
    )
  }
}
