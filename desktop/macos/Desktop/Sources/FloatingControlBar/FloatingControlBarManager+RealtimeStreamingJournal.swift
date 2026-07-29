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
      let provider = historyChatProvider
    else { return false }
    return await provider.recordStreamingJournalExchange(
      surface: provider.mainChatSurfaceReference(), ownerID: projection.ownerID,
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
      let provider = historyChatProvider
    else { return false }
    return await provider.kernelTurnProjection.updateTurn(
      surface: provider.mainChatSurfaceReference(),
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
      let provider = historyChatProvider
    else { return false }
    let surface = provider.mainChatSurfaceReference()
    guard await provider.kernelTurnProjection.updateTurn(
      surface: surface, message: projection.userMessage(text: userText), status: .completed,
      ownerID: projection.ownerID) != nil else { return false }
    return await provider.kernelTurnProjection.updateTurn(
      surface: surface,
      message: projection.assistantMessage(text: assistantText, isStreaming: false),
      status: .completed, ownerID: projection.ownerID) != nil
  }
}
