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
  func completeStreamingRealtimeExchange(
    projection: RealtimeStreamingJournalProjection,
    userText: String,
    assistantText: String
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
        status: .completed, ownerID: projection.ownerID) != nil
      {
        return true
      }
    }
    return false
  }
}
