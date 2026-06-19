import Foundation

// MARK: - Realtime Hub
//
// "Realtime-as-hub": instead of the cascade (STT → router → Claude → TTS), one
// realtime model is the single hub. It does in-session STT, reasoning, routing
// (as tool choice), and speaks the answer. Its tools call the EXISTING backend
// endpoints / app code — no new backend routes.
//
// The hub is the default voice path — there is no opt-in toggle. Every PTT turn
// routes through it whenever it can connect: BYOK users connect client-direct with
// their own key (see APIKeyService); managed users connect with a server-minted
// ephemeral token. When neither is available (no key, mint fails / not entitled) the
// turn falls back to the legacy STT cascade. The provider follows the user's "Voice
// Model" choice in Advanced settings (RealtimeOmniSettings) — no separate picker.

enum RealtimeHubProvider: String, Sendable {
  case openai
  case gemini

  var displayName: String {
    switch self {
    case .openai: return "OpenAI Realtime"
    case .gemini: return "Gemini Live"
    }
  }

  /// Concrete model identifier sent to the provider.
  var modelID: String {
    switch self {
    case .openai: return "gpt-realtime-2"
    // Same Live model OMI already uses (RealtimeOmniProvider.geminiFlashLive).
    // NOTE (deviation): the original plan called for a TEXT-modality half-cascade
    // model spoken via AVSpeechSynthesizer, but Google deprecated the half-cascade
    // Live models — every model that currently exposes bidiGenerateContent is
    // native-audio and rejects TEXT modality (close 1007). Verified this model does
    // AUDIO + function calling; it speaks via native audio (24k PCM) played by
    // StreamingPCMPlayer, same as OpenAI.
    case .gemini: return "gemini-3.1-flash-live-preview"
    }
  }

  /// The BYOK key this provider authenticates with (client-direct, Phase 1).
  var byokProvider: BYOKProvider {
    switch self {
    case .openai: return .openai
    case .gemini: return .gemini
    }
  }
}

@MainActor
final class RealtimeHubSettings {
  static let shared = RealtimeHubSettings()

  private init() {}

  /// The hub provider follows the user's "Voice Model" choice in Advanced settings —
  /// there is no separate hub picker. The two map 1:1 (same underlying models), and
  /// `.auto` is already resolved to a concrete provider by `effectiveProvider`.
  var provider: RealtimeHubProvider {
    switch RealtimeOmniSettings.shared.effectiveProvider {
    case .gptRealtime2: return .openai
    case .geminiFlashLive, .auto: return .gemini
    }
  }

  /// True when the hub can connect client-direct with the user's own provider key
  /// (BYOK / dev key). Managed users without a key connect via a minted ephemeral
  /// token instead (see RealtimeHubController.ensureWarm); both reach the hub.
  var canConnect: Bool {
    APIKeyService.byokKey(provider.byokProvider) != nil
  }
}
