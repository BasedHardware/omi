import Foundation

enum KernelJournalTurnStatus: String, Sendable {
  case pending
  case streaming
  case completed
  case failed
}

enum KernelJournalDelivery: String, Sendable {
  case backend
  case local
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
    self.conversationGeneration = Self.int(dictionary["conversationGeneration"])
      ?? conversationGenerationFallback
    self.generationBaseTurnSeq = Self.int(dictionary["generationBaseTurnSeq"])
      ?? generationBaseTurnSeqFallback
    self.producerId = dictionary["producerId"] as? String ?? ""
    self.payloadHash = dictionary["payloadHash"] as? String ?? ""
    self.role = role
    self.surfaceKind = dictionary["surfaceKind"] as? String ?? surfaceFallback?.surfaceKind ?? ""
    self.externalRefKind = dictionary["externalRefKind"] as? String
      ?? surfaceFallback?.externalRefKind ?? ""
    self.externalRefId = dictionary["externalRefId"] as? String
      ?? surfaceFallback?.externalRefId ?? ""
    self.content = content
    self.origin = dictionary["origin"] as? String ?? "legacy"
    self.status = status
    self.contentBlocksJSON = Self.jsonArrayString(dictionary["contentBlocks"])
    self.resourcesJSON = Self.jsonArrayString(dictionary["resources"])
    self.producingRunId = dictionary["producingRunId"] as? String
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
  let producingRunId: String?
  let metadataJSON: String
  let delivery: KernelJournalDelivery
  let createdAtMs: Int

  var dictionary: [String: Any] {
    var value: [String: Any] = [
      "turnId": turnId,
      "role": role,
      "origin": origin,
      "status": status.rawValue,
      "content": content,
      "contentBlocks": Self.jsonArray(contentBlocksJSON),
      "resources": Self.jsonArray(resourcesJSON),
      "metadataJson": metadataJSON,
      "delivery": delivery.rawValue,
      "createdAtMs": createdAtMs,
    ]
    if let producingRunId { value["producingRunId"] = producingRunId }
    return value
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
  let producingRunId: String?
  let metadataJSON: String?

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
    if let producingRunId { value["producingRunId"] = producingRunId }
    if let metadataJSON { value["metadataJson"] = metadataJSON }
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
    let continuityKey = (metadata["continuityKey"] as? String)
      ?? (metadata["idempotencyKey"] as? String)
    let owner: ChatTurnOwner?
    switch origin {
    case "realtime_voice": owner = .floatingVoice
    case "floating_chat": owner = .floatingDefault
    case "task_chat", "workstream": owner = .taskChat(externalRefId)
    default: owner = .mainChat
    }
    return ChatMessage(
      id: turnId,
      clientTurnId: continuityKey,
      text: content,
      createdAt: Date(timeIntervalSince1970: TimeInterval(createdAtMs) / 1_000),
      sender: role == "user" ? .user : .ai,
      isStreaming: status == .pending || status == .streaming,
      isSynced: remoteId != nil,
      contentBlocks: ChatContentBlockCodec.decode(contentBlocksJSON) ?? [],
      notificationContext: metadata["notificationContext"] as? String,
      resources: ChatResource.hydrateFileStates(
        ChatResource.decodeResourcesFromPersistence(resourcesJSON)
      ),
      turnOwner: owner
    )
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
    delivery: KernelJournalDelivery,
    continuityKey: String? = nil,
    producingRunId: String? = nil,
    appId: String? = nil,
    sessionId: String? = nil,
    messageSource: String? = nil
  ) -> KernelJournalTurnWrite {
    var metadata: [String: Any] = [:]
    if let continuityKey, !continuityKey.isEmpty { metadata["continuityKey"] = continuityKey }
    if let notificationContext { metadata["notificationContext"] = notificationContext }
    // These rollback-compatible fields are consumed only by the kernel outbox
    // renderer for the existing /v2/desktop/messages POST shape.
    if let appId { metadata["appId"] = appId }
    if let sessionId { metadata["sessionId"] = sessionId }
    if let messageSource { metadata["messageSource"] = messageSource }
    let metadataJSON: String
    if let data = try? JSONSerialization.data(withJSONObject: metadata),
       let encoded = String(data: data, encoding: .utf8)
    {
      metadataJSON = encoded
    } else {
      metadataJSON = "{}"
    }
    return KernelJournalTurnWrite(
      turnId: id,
      role: sender == .user ? "user" : "assistant",
      origin: origin,
      status: status,
      content: text,
      contentBlocksJSON: ChatContentBlockCodec.encode(contentBlocks) ?? "[]",
      resourcesJSON: ChatResource.encodeResourcesForPersistence(displayResources) ?? "[]",
      producingRunId: producingRunId,
      metadataJSON: metadataJSON,
      delivery: delivery,
      createdAtMs: Int(createdAt.timeIntervalSince1970 * 1_000)
    )
  }

  func journalUpdate(
    status: KernelJournalTurnStatus? = nil,
    producingRunId: String? = nil
  ) -> KernelJournalTurnUpdate {
    KernelJournalTurnUpdate(
      turnId: id,
      status: status,
      content: text,
      contentBlocksJSON: ChatContentBlockCodec.encode(contentBlocks) ?? "[]",
      appendContentBlocksJSON: nil,
      resourcesJSON: ChatResource.encodeResourcesForPersistence(displayResources) ?? "[]",
      appendResourcesJSON: nil,
      producingRunId: producingRunId,
      metadataJSON: nil
    )
  }
}
