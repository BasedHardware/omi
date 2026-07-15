import Foundation

/// Capability-scoped main-Chat journal operations. The kernel remains the sole
/// journal writer; this extension validates the Swift boundary and projects the
/// kernel receipts through the existing runtime actor.
extension AgentRuntimeProcess {
  struct JournalOperationResult: Sendable {
    let operation: String
    let conversationId: String
    let turn: KernelJournalTurn?
    let turns: [KernelJournalTurn]
    let clearedCount: Int
    let highWaterTurnSeq: Int
    let conversationGeneration: Int
    let generationBaseTurnSeq: Int
    let accepted: Bool?
    let duplicate: Bool?
    let continuityKey: String?
    let suppressedByTailQuestion: Bool
    let suppressedByStreamingTail: Bool
    let materializationStoppedByTail: Bool
    let materializationReceipts: [ChatFirstMaterializationReceipt]
    let coldStartSequenceTerminalReceipts: [ChatFirstColdStartSequenceTerminalReceipt]
    let acknowledgedReceiptCount: Int

    init(
      operation: String,
      conversationId: String,
      turn: KernelJournalTurn?,
      turns: [KernelJournalTurn],
      clearedCount: Int,
      highWaterTurnSeq: Int,
      conversationGeneration: Int,
      generationBaseTurnSeq: Int,
      accepted: Bool? = nil,
      duplicate: Bool? = nil,
      continuityKey: String? = nil,
      suppressedByTailQuestion: Bool = false,
      suppressedByStreamingTail: Bool = false,
      materializationStoppedByTail: Bool = false,
      materializationReceipts: [ChatFirstMaterializationReceipt] = [],
      coldStartSequenceTerminalReceipts: [ChatFirstColdStartSequenceTerminalReceipt] = [],
      acknowledgedReceiptCount: Int = 0
    ) {
      self.operation = operation
      self.conversationId = conversationId
      self.turn = turn
      self.turns = turns
      self.clearedCount = clearedCount
      self.highWaterTurnSeq = highWaterTurnSeq
      self.conversationGeneration = conversationGeneration
      self.generationBaseTurnSeq = generationBaseTurnSeq
      self.accepted = accepted
      self.duplicate = duplicate
      self.continuityKey = continuityKey
      self.suppressedByTailQuestion = suppressedByTailQuestion
      self.suppressedByStreamingTail = suppressedByStreamingTail
      self.materializationStoppedByTail = materializationStoppedByTail
      self.materializationReceipts = materializationReceipts
      self.coldStartSequenceTerminalReceipts = coldStartSequenceTerminalReceipts
      self.acknowledgedReceiptCount = acknowledgedReceiptCount
    }
  }

  struct QuestionInteractionReply: Sendable {
    let accepted: Bool
    let duplicate: Bool
    let continuityKey: String
    let parentTurn: KernelJournalTurn?
    let userTurn: KernelJournalTurn
    let assistantTurn: KernelJournalTurn
  }

  struct ChatFirstIntentsMaterialization: Sendable {
    let accepted: Bool
    let stoppedByTail: Bool
    let receipts: [ChatFirstMaterializationReceipt]
  }

  /// Append server-validated structured blocks to exactly the assistant turn
  /// produced by this capability's run/attempt. The Node kernel re-checks the
  /// live capability and performs the sole journal mutation.
  func appendChatFirstBlocks(
    clientId: String,
    surface: AgentSurfaceReference,
    ownerID: String,
    sessionID: String,
    runID: String,
    attemptID: String,
    capabilityRef: String,
    controlGeneration: Int,
    blocks: [[String: Any]],
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot
  ) async throws -> KernelJournalTurn {
    guard surface.surfaceKind == "main_chat",
      controlGeneration >= 0,
      !blocks.isEmpty,
      blocks.count <= 8
    else {
      throw BridgeError.agentError("Invalid chat-first journal append")
    }
    let result = try await journalOperation(
      type: "append_chat_first_blocks",
      operation: "append_chat_first_blocks",
      clientId: clientId,
      surface: surface,
      ownerID: ownerID,
      payload: [
        "sessionId": sessionID,
        "runId": runID,
        "attemptId": attemptID,
        "capabilityRef": capabilityRef,
        "controlGeneration": controlGeneration,
        "blocks": blocks,
      ],
      authorizationSnapshot: authorizationSnapshot
    )
    guard let turn = result.turn else {
      throw BridgeError.agentError("Chat-first journal append returned no turn")
    }
    recordLifecycleJournalMutation(turn)
    return turn
  }

  /// The journal derives the stored question payload and only accepts the
  /// current main-Chat tail. Swift cannot send an answer string or select an
  /// arbitrary parent row through this operation.
  func recordQuestionInteractionReply(
    clientId: String,
    surface: AgentSurfaceReference,
    ownerID: String,
    sessionID: String,
    questionID: String,
    optionID: String,
    controlGeneration: Int,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot
  ) async throws -> QuestionInteractionReply {
    guard surface.surfaceKind == "main_chat",
      controlGeneration >= 0,
      !sessionID.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
      !questionID.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
      !optionID.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    else {
      throw BridgeError.agentError("Invalid question interaction")
    }
    let result = try await journalOperation(
      type: "record_question_interaction_reply",
      operation: "record_question_interaction_reply",
      clientId: clientId,
      surface: surface,
      ownerID: ownerID,
      payload: [
        "sessionId": sessionID,
        "questionId": questionID,
        "optionId": optionID,
        "controlGeneration": controlGeneration,
      ],
      authorizationSnapshot: authorizationSnapshot
    )
    guard result.accepted == true,
      let continuityKey = result.continuityKey,
      let userTurn = result.turns.first(where: { $0.role == "user" }),
      let assistantTurn = result.turns.first(where: { $0.role == "assistant" })
    else {
      throw BridgeError.agentError("Question is no longer actionable")
    }
    for turn in [result.turn, userTurn, assistantTurn] {
      if let turn { recordLifecycleJournalMutation(turn) }
    }
    return QuestionInteractionReply(
      accepted: true,
      duplicate: result.duplicate == true,
      continuityKey: continuityKey,
      parentTurn: result.turn,
      userTurn: userTurn,
      assistantTurn: assistantTurn
    )
  }

  /// Materialize one ordered server batch through the kernel, which owns the
  /// canonical assistant rows, tail suppression, and receipt identities.
  func materializeChatFirstIntents(
    clientId: String,
    surface: AgentSurfaceReference,
    ownerID: String,
    sessionID: String,
    controlGeneration: Int,
    intents: [ChatFirstPromptIntent],
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot
  ) async throws -> ChatFirstIntentsMaterialization {
    guard surface.surfaceKind == "main_chat",
      controlGeneration >= 0,
      !intents.isEmpty,
      intents.count <= 8,
      intents.allSatisfy({ $0.accountGeneration == controlGeneration && $0.kernelBlocks != nil }),
      !sessionID.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    else {
      throw BridgeError.agentError("Invalid chat-first materialization")
    }
    let result = try await journalOperation(
      type: "materialize_chat_first_intents",
      operation: "materialize_chat_first_intents",
      clientId: clientId,
      surface: surface,
      ownerID: ownerID,
      payload: [
        "sessionId": sessionID,
        "controlGeneration": controlGeneration,
        "intents": intents.compactMap { intent -> [String: Any]? in
          guard let blocks = intent.kernelBlocks else { return nil }
          return [
            "intentId": intent.intentID,
            "continuityKey": intent.continuityKey,
            "source": intent.source.rawValue,
            "blocks": blocks,
          ] as [String: Any]
        },
      ],
      authorizationSnapshot: authorizationSnapshot
    )
    for turn in result.turns {
      recordLifecycleJournalMutation(turn)
    }
    return ChatFirstIntentsMaterialization(
      accepted: result.accepted == true,
      stoppedByTail: result.materializationStoppedByTail,
      receipts: result.materializationReceipts
    )
  }

  func listChatFirstMaterializationReceipts(
    clientId: String,
    surface: AgentSurfaceReference,
    ownerID: String,
    sessionID: String,
    controlGeneration: Int,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot
  ) async throws -> ChatFirstPromptReceiptBatch {
    guard surface.surfaceKind == "main_chat", controlGeneration >= 0 else {
      throw BridgeError.agentError("Invalid chat-first receipt listing")
    }
    let result = try await journalOperation(
      type: "list_chat_first_materialization_receipts",
      operation: "list_chat_first_materialization_receipts",
      clientId: clientId,
      surface: surface,
      ownerID: ownerID,
      payload: ["sessionId": sessionID, "controlGeneration": controlGeneration, "limit": 16],
      authorizationSnapshot: authorizationSnapshot
    )
    return ChatFirstPromptReceiptBatch(
      materializationReceipts: result.materializationReceipts,
      coldStartSequenceTerminalReceipts: result.coldStartSequenceTerminalReceipts
    )
  }

  @discardableResult
  func acknowledgeChatFirstMaterializationReceipts(
    clientId: String,
    surface: AgentSurfaceReference,
    ownerID: String,
    sessionID: String,
    controlGeneration: Int,
    receipts: ChatFirstPromptReceiptBatch,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot
  ) async throws -> Int {
    guard surface.surfaceKind == "main_chat",
      controlGeneration >= 0,
      receipts.materializationReceipts.count <= 16,
      receipts.coldStartSequenceTerminalReceipts.count <= 16
    else {
      throw BridgeError.agentError("Invalid chat-first receipt acknowledgement")
    }
    let result = try await journalOperation(
      type: "acknowledge_chat_first_materialization_receipts",
      operation: "acknowledge_chat_first_materialization_receipts",
      clientId: clientId,
      surface: surface,
      ownerID: ownerID,
      payload: [
        "sessionId": sessionID,
        "controlGeneration": controlGeneration,
        "receipts": receipts.materializationReceipts.map {
          ["intentId": $0.intentID, "receiptId": $0.receiptID]
        },
        "coldStartSequenceTerminalReceipts": receipts.coldStartSequenceTerminalReceipts.map {
          [
            "sequenceId": $0.sequenceID,
            "receiptId": $0.receiptID,
            "terminalState": $0.terminalState.rawValue,
          ]
        },
      ],
      authorizationSnapshot: authorizationSnapshot
    )
    return result.acknowledgedReceiptCount
  }

  nonisolated static func chatFirstMaterializationReceipts(
    from payload: Any?
  ) -> [ChatFirstMaterializationReceipt] {
    guard let values = payload as? [[String: Any]] else { return [] }
    return values.compactMap { value in
      guard let intentID = value["intentId"] as? String,
        !intentID.isEmpty,
        let receiptID = value["receiptId"] as? String,
        !receiptID.isEmpty
      else { return nil }
      return ChatFirstMaterializationReceipt(intentID: intentID, receiptID: receiptID)
    }
  }

  nonisolated static func chatFirstColdStartSequenceTerminalReceipts(
    from payload: Any?
  ) -> [ChatFirstColdStartSequenceTerminalReceipt] {
    guard let values = payload as? [[String: Any]] else { return [] }
    return values.compactMap { value in
      guard let sequenceID = value["sequenceId"] as? String,
        !sequenceID.isEmpty,
        let receiptID = value["receiptId"] as? String,
        !receiptID.isEmpty,
        let rawState = value["terminalState"] as? String,
        let terminalState = ChatFirstColdStartSequenceTerminalReceipt.TerminalState(rawValue: rawState)
      else { return nil }
      return ChatFirstColdStartSequenceTerminalReceipt(
        sequenceID: sequenceID,
        receiptID: receiptID,
        terminalState: terminalState
      )
    }
  }

  func handleChatFirstDeferralDelivery(_ message: RuntimeMessage) {
    guard let request = ChatFirstDeferralDeliveryRequest(payload: message.payload) else {
      sendChatFirstDeferralDeliveryResult(
        requestId: message.requestId,
        clientId: message.clientId,
        ownerID: message.payload["ownerId"] as? String,
        continuityKey: message.payload["continuityKey"] as? String ?? "",
        deliveryGeneration: message.payload["deliveryGeneration"] as? Int ?? 0,
        payloadHash: message.payload["payloadHash"] as? String ?? "",
        ok: false,
        errorCode: "chat_first_deferral_malformed"
      )
      return
    }
    Task { [weak self] in
      do {
        try await APIClient.shared.recordChatFirstDeferral(request)
        await self?.sendChatFirstDeferralDeliveryResult(
          requestId: message.requestId,
          clientId: message.clientId,
          ownerID: request.ownerID,
          continuityKey: request.continuityKey,
          deliveryGeneration: request.deliveryGeneration,
          payloadHash: request.payloadHash,
          ok: true,
          errorCode: nil
        )
      } catch {
        await self?.sendChatFirstDeferralDeliveryResult(
          requestId: message.requestId,
          clientId: message.clientId,
          ownerID: request.ownerID,
          continuityKey: request.continuityKey,
          deliveryGeneration: request.deliveryGeneration,
          payloadHash: request.payloadHash,
          ok: false,
          errorCode: Self.boundedChatFirstDeferralErrorCode(for: error)
        )
      }
    }
  }

  func sendChatFirstDeferralDeliveryResult(
    requestId: String?,
    clientId: String?,
    ownerID: String?,
    continuityKey: String,
    deliveryGeneration: Int,
    payloadHash: String,
    ok: Bool,
    errorCode: String?
  ) {
    var payload: [String: Any] = [
      "type": "chat_first_deferral_delivery_result",
      "protocolVersion": 2,
      "continuityKey": continuityKey,
      "deliveryGeneration": deliveryGeneration,
      "payloadHash": payloadHash,
      "ok": ok,
    ]
    if let requestId { payload["requestId"] = requestId }
    if let clientId { payload["clientId"] = clientId }
    if let ownerID { payload["ownerId"] = ownerID }
    if let errorCode { payload["errorCode"] = errorCode }
    sendJson(payload)
  }
}
