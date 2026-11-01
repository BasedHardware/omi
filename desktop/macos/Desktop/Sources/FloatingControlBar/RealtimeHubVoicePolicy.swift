/// One authority for which spoken voice each realtime provider session opens with.
///
/// The Gemini lane follows the shared assistant-voice selection (defaulting to
/// Charon); OpenAI stays pinned to the gpt-realtime family's cedar. Session
/// builders read from here; a per-call-site string is how the lanes drifted
/// apart (marin).
enum RealtimeHubVoicePolicy {
  static func voiceName(for provider: RealtimeHubProvider, assistantVoiceID: String = "Charon") -> String {
    switch provider {
    case .openai: return "cedar"
    case .gemini: return assistantVoiceID
    }
  }
}
