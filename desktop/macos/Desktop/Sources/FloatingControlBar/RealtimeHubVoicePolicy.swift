/// One authority for which spoken voice each realtime provider is pinned to.
///
/// Both lanes deliberately use deep, calm male voices — Gemini's Charon and
/// the gpt-realtime family's cedar (its counterpart) — so a provider failover
/// changes the engine, not who Omi sounds like. Session builders read from
/// here; a per-call-site string is how the lanes drifted apart (marin).
enum RealtimeHubVoicePolicy {
  static func voiceName(for provider: RealtimeHubProvider) -> String {
    switch provider {
    case .openai: return "cedar"
    case .gemini: return "Charon"
    }
  }
}
