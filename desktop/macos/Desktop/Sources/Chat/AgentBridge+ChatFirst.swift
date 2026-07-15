import Foundation

/// The cohort-only projection and journal façade. Keeping it separate makes
/// the capability boundary visible without creating a second bridge or
/// transcript owner.
extension AgentBridge {
  func resolveSurfaceSession(
    _ surface: AgentSurfaceReference,
    title: String? = nil,
    creationProfile: AgentSessionCreationProfile? = nil,
    chatFirstCapability: ChatFirstCapabilityProjection? = nil,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot? = nil
  ) async throws -> AgentSurfaceSession {
    let authorization = try resolveAuthorization(authorizationSnapshot)
    try await start(authorizationSnapshot: authorization)
    guard RuntimeOwnerIdentity.isAuthorizationCurrent(authorization) else {
      throw BridgeError.authMissing
    }
    return try await runtime.resolveSurfaceSession(
      clientId: clientId,
      surface: surface,
      title: title,
      creationProfile: creationProfile,
      chatFirstCapability: chatFirstCapability,
      authorizationSnapshot: authorization
    )
  }

  func recordQuestionInteractionReply(
    surface: AgentSurfaceReference,
    ownerID: String,
    sessionID: String,
    questionID: String,
    optionID: String,
    controlGeneration: Int,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot? = nil
  ) async throws -> AgentRuntimeProcess.QuestionInteractionReply {
    let authorization = try resolveAuthorization(
      authorizationSnapshot,
      expectedOwnerID: ownerID)
    try await start(authorizationSnapshot: authorization)
    return try await runtime.recordQuestionInteractionReply(
      clientId: clientId,
      surface: surface,
      ownerID: ownerID,
      sessionID: sessionID,
      questionID: questionID,
      optionID: optionID,
      controlGeneration: controlGeneration,
      authorizationSnapshot: authorization
    )
  }

  func materializeChatFirstIntents(
    surface: AgentSurfaceReference,
    ownerID: String,
    sessionID: String,
    controlGeneration: Int,
    intents: [ChatFirstPromptIntent],
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot? = nil
  ) async throws -> AgentRuntimeProcess.ChatFirstIntentsMaterialization {
    let authorization = try resolveAuthorization(
      authorizationSnapshot,
      expectedOwnerID: ownerID)
    try await start(authorizationSnapshot: authorization)
    return try await runtime.materializeChatFirstIntents(
      clientId: clientId,
      surface: surface,
      ownerID: ownerID,
      sessionID: sessionID,
      controlGeneration: controlGeneration,
      intents: intents,
      authorizationSnapshot: authorization
    )
  }

  func listChatFirstMaterializationReceipts(
    surface: AgentSurfaceReference,
    ownerID: String,
    sessionID: String,
    controlGeneration: Int,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot? = nil
  ) async throws -> ChatFirstPromptReceiptBatch {
    let authorization = try resolveAuthorization(
      authorizationSnapshot,
      expectedOwnerID: ownerID)
    try await start(authorizationSnapshot: authorization)
    return try await runtime.listChatFirstMaterializationReceipts(
      clientId: clientId,
      surface: surface,
      ownerID: ownerID,
      sessionID: sessionID,
      controlGeneration: controlGeneration,
      authorizationSnapshot: authorization
    )
  }

  @discardableResult
  func acknowledgeChatFirstMaterializationReceipts(
    surface: AgentSurfaceReference,
    ownerID: String,
    sessionID: String,
    controlGeneration: Int,
    receipts: ChatFirstPromptReceiptBatch,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot? = nil
  ) async throws -> Int {
    let authorization = try resolveAuthorization(
      authorizationSnapshot,
      expectedOwnerID: ownerID)
    try await start(authorizationSnapshot: authorization)
    return try await runtime.acknowledgeChatFirstMaterializationReceipts(
      clientId: clientId,
      surface: surface,
      ownerID: ownerID,
      sessionID: sessionID,
      controlGeneration: controlGeneration,
      receipts: receipts,
      authorizationSnapshot: authorization
    )
  }

  func invokeChatFirstFixtureTaskCard(
    ownerID: String,
    sessionID: String,
    producingTurnID: String,
    controlGeneration: Int,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot? = nil
  ) async throws -> AgentRuntimeProcess.ChatFirstHarnessExecutorReceipt {
    let authorization = try resolveAuthorization(
      authorizationSnapshot,
      expectedOwnerID: ownerID)
    try await start(authorizationSnapshot: authorization)
    return try await runtime.invokeChatFirstFixtureTaskCard(
      clientId: clientId,
      ownerID: ownerID,
      sessionID: sessionID,
      producingTurnID: producingTurnID,
      controlGeneration: controlGeneration,
      authorizationSnapshot: authorization
    )
  }
}
