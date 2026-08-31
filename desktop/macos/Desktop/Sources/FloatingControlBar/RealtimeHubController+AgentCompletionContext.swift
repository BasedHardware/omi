import Foundation
import VoiceTurnDomain

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

  /// Trusted turn instruction — not quoted card body. Callers must not wrap
  /// this in `NotchCardVoiceDelivery.contextBlock`. OpenAI applies it as
  /// per-turn `response.create` `instructions`; Gemini sends it inside the
  /// activity window. The controller keeps a copy so a replacement session
  /// can be armed before `beginInputTurn` (the inject often hits the old
  /// idle socket, which is then discarded).
  func injectTrustedTurnInstruction(_ text: String) async -> Bool {
    pendingTrustedTurnInstruction = text
    guard let session else { return false }
    return await session.sendTrustedTurnInstruction(text)
  }

  func clearTrustedTurnInstruction() {
    pendingTrustedTurnInstruction = nil
    session?.clearTrustedTurnInstruction()
  }

  func beginLiveInputTurn(
    _ live: RealtimeHubSession,
    turnID: VoiceTurnID? = nil,
    responseID: VoiceResponseID? = nil,
    interrupting: Bool = false
  ) {
    live.beginInputTurn(
      turnID: turnID,
      responseID: responseID,
      interrupting: interrupting,
      trustedTurnInstruction: pendingTrustedTurnInstruction
    )
  }
}
