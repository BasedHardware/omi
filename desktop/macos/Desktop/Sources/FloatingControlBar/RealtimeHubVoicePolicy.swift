/// One authority for which spoken voice each realtime provider is pinned to.
///
/// Gemini's Charon and the gpt-realtime family's cedar are deliberately deep, calm
/// male voices — so a provider failover changes the engine, not who Omi sounds
/// like. GPT-Live-1 pins its native full-duplex voice `marin`, as its session
/// protocol requires. Session builders read from here; a per-call-site string is
/// how the lanes drifted apart (marin).
enum RealtimeHubVoicePolicy {
  static func voiceName(for provider: RealtimeHubProvider) -> String {
    switch provider {
    case .openai: return "cedar"
    case .gemini: return "Charon"
    case .gptLive: return "marin"
    }
  }
}
