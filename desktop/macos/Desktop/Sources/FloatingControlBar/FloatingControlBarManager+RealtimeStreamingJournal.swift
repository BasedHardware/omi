import Foundation
import VoiceTurnDomain

extension FloatingControlBarManager {
  /// Admits the user turn and its assistant target atomically so all chat
  /// surfaces show one shared realtime exchange.
  func recordStreamingRealtimeExchange(
    projection: RealtimeStreamingJournalProjection,
    userText: String
  ) async -> Bool {
    guard RuntimeOwnerIdentity.currentOwnerId() == projection.ownerID,
      let provider = sharedFloatingProvider
    else { return false }
    return await provider.recordStreamingJournalExchange(
      surface: projection.admissionSurface, ownerID: projection.ownerID,
      continuityKey: projection.continuityKey, userMessage: projection.userMessage(text: userText),
      assistantMessage: projection.assistantMessage(text: "", isStreaming: true),
      origin: "realtime_voice", appId: nil, sessionId: nil, messageSource: "realtime_voice")
  }

  /// Persists a coalesced realtime delta through the admitted assistant row.
  func updateStreamingRealtimeAssistant(
    projection: RealtimeStreamingJournalProjection,
    assistantText: String
  ) async -> Bool {
    guard RuntimeOwnerIdentity.currentOwnerId() == projection.ownerID,
      let provider = sharedFloatingProvider
    else { return false }
    return await provider.kernelTurnProjection.updateTurn(
      surface: projection.admissionSurface,
      message: projection.assistantMessage(text: assistantText, isStreaming: true),
      status: .streaming, ownerID: projection.ownerID) != nil
  }

  /// Finalizes the existing pair after any late input-transcript correction.
  ///
  /// The user row always completes — the utterance happened regardless of how the
  /// turn ended. Only the assistant row carries the outcome, because only the reply
  /// can be cut off.
  func completeStreamingRealtimeExchange(
    projection: RealtimeStreamingJournalProjection,
    userText: String,
    assistantText: String,
    assistantStatus: KernelJournalTurnStatus = .completed,
    terminalReason: String? = nil
  ) async -> Bool {
    guard RuntimeOwnerIdentity.currentOwnerId() == projection.ownerID,
      let provider = sharedFloatingProvider
    else { return false }
    let surface = projection.admissionSurface
    guard
      await provider.kernelTurnProjection.updateTurn(
        surface: surface, message: projection.userMessage(text: userText), status: .completed,
        ownerID: projection.ownerID) != nil
    else { return false }
    // Retry the assistant mutation so a transient nil does not leave the row
    // stuck in .streaming after the user row is already committed.
    for _ in 0..<3 {
      if await provider.kernelTurnProjection.updateTurn(
        surface: surface,
        message: projection.assistantMessage(text: assistantText, isStreaming: false),
        status: assistantStatus, terminalReason: terminalReason, ownerID: projection.ownerID) != nil
      {
        await consumeInterjectHubTranscript(assistantText)
        return true
      }
    }
    return false
  }

  /// Revises an assistant row that was finalized `.completed` at
  /// provider-response-finish after its turn terminalized without delivering
  /// the answer (#12743). The revision is payload-free — it changes only the
  /// row's status and truncation cause — so the sealed row's content blocks,
  /// resources, and canonical metadata (model attribution, continuity) stay
  /// exactly as the funnel wrote them; the kernel merges the terminal reason
  /// into the existing metadata instead of replacing it. The journal stays
  /// the one transcript authority (INV-CHAT-1). Bounded retry mirrors
  /// `completeStreamingRealtimeExchange` so a transient rejection does not
  /// strand the optimistic status.
  func reviseSealedRealtimeAssistantStatus(
    surface: AgentSurfaceReference,
    ownerID: String,
    continuityKey: String,
    terminalReason: String
  ) async -> Bool {
    guard RuntimeOwnerIdentity.currentOwnerId() == ownerID,
      let provider = sharedFloatingProvider
    else { return false }
    let turnID = KernelTurnProjection.stableTurnID(
      continuityKey: continuityKey, role: "assistant")
    for _ in 0..<3 {
      if await provider.kernelTurnProjection.reviseSealedTerminalTurn(
        surface: surface,
        turnId: turnID,
        terminalReason: terminalReason,
        ownerID: ownerID) != nil
      {
        return true
      }
    }
    return false
  }
}
