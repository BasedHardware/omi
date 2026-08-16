import Foundation

/// Seam for `AgentCompletionVoiceDelivery`: lets completed background-agent
/// results reach the live voice conversation as silent context, without
/// touching the voice turn coordinator's output authority.
extension RealtimeHubController {
  /// True when a physical provider session exists (including warm-idle).
  var hasLiveVoiceSession: Bool { session != nil }

  /// Adds completed background-agent context to the live conversation without
  /// requesting a response. Returns false when no session is live so the
  /// caller leaves the completion checkpoint unadvanced and retries later.
  func injectBackgroundAgentCompletionContext(_ text: String) async -> Bool {
    guard let session else { return false }
    return await session.sendBackgroundAgentContext(text)
  }
}
