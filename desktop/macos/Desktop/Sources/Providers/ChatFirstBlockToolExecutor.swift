import Foundation

/// Capability-scoped block validation and journal append. It is intentionally
/// separate from the legacy desktop tool switch so server admission is visible
/// as a distinct, all-or-nothing boundary.
@MainActor
enum ChatFirstBlockToolExecutor {
  static func execute(
    _ args: [String: Any],
    surface: AgentSurfaceReference?,
    sessionID: String?,
    runID: String?,
    attemptID: String?,
    capabilityRef: String?,
    controlGeneration: Int?,
    expectedOwnerID: String?,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot?,
    api: APIClient
  ) async -> String {
    guard let expectedOwnerID,
      let authorizationSnapshot,
      let surface,
      surface.surfaceKind == "main_chat",
      let sessionID,
      let runID,
      let attemptID,
      let capabilityRef,
      let controlGeneration,
      controlGeneration >= 0,
      let backendBlocks = ChatFirstBlockWire.backendBlocks(from: args)
    else {
      return #"{"ok":false,"error":{"code":"chat_first_invalid_authority"}}"#
    }
    guard ChatToolExecutor.isExpectedOwnerCurrent(expectedOwnerID, authorizationSnapshot: authorizationSnapshot) else {
      return ChatToolExecutor.authorizedOwnerChangedResult()
    }

    do {
      let request = ChatFirstBlockValidationRequest(
        controlGeneration: controlGeneration,
        ownerFence: expectedOwnerID,
        runID: runID,
        attemptID: attemptID,
        blocks: backendBlocks.map(OmiAnyCodable.init)
      )
      let receipt: ChatFirstBlockValidationReceipt = try await api.post(
        "v1/chat-first/blocks/validate",
        body: request,
        expectedOwnerId: expectedOwnerID,
        authorizationSnapshot: authorizationSnapshot
      )
      guard ChatToolExecutor.isExpectedOwnerCurrent(expectedOwnerID, authorizationSnapshot: authorizationSnapshot)
      else {
        return ChatToolExecutor.authorizedOwnerChangedResult()
      }
      guard let journalBlocks = ChatFirstBlockWire.journalBlocks(from: receipt) else {
        return #"{"ok":false,"error":{"code":"chat_first_blocks_rejected"}}"#
      }
      let journalBlocksData = try JSONSerialization.data(withJSONObject: journalBlocks)
      guard let journalBlocksJSON = String(data: journalBlocksData, encoding: .utf8) else {
        return #"{"ok":false,"error":{"code":"chat_first_blocks_unavailable"}}"#
      }
      _ = try await AgentRuntimeProcess.shared.appendChatFirstBlocks(
        clientId: "chat-first-render",
        surface: surface,
        ownerID: expectedOwnerID,
        sessionID: sessionID,
        runID: runID,
        attemptID: attemptID,
        capabilityRef: capabilityRef,
        controlGeneration: controlGeneration,
        blocksJSON: journalBlocksJSON,
        authorizationSnapshot: authorizationSnapshot
      )
      return #"{"ok":true,"rendered":#(journalBlocks.count)}"#
    } catch {
      guard ChatToolExecutor.isExpectedOwnerCurrent(expectedOwnerID, authorizationSnapshot: authorizationSnapshot)
      else {
        return ChatToolExecutor.authorizedOwnerChangedResult()
      }
      logError("Chat-first block rendering failed", error: error)
      return #"{"ok":false,"error":{"code":"chat_first_blocks_unavailable"}}"#
    }
  }
}
