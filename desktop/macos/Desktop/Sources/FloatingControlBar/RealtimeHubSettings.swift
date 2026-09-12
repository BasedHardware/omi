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

enum RealtimeHubProvider: String, Sendable, Equatable {
  case openai
  case gemini
  /// OpenAI "GPT-Live-1" full-duplex realtime (the default voice provider).
  case gptLive = "gpt_live"

  var displayName: String {
    switch self {
    case .openai: return "OpenAI Realtime"
    case .gemini: return "Gemini Live"
    case .gptLive: return "GPT-Live"
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
    case .gptLive: return "gpt-live-1"
    }
  }

  /// The provider string the backend's realtime mint endpoint expects.
  /// OpenAI's full-duplex model shares the OpenAI BYOK key but mints under its
  /// own `gpt_live` provider id so the backend can price/route it separately.
  var mintProviderParam: String {
    switch self {
    case .openai: return "openai"
    case .gemini: return "gemini"
    case .gptLive: return "gpt_live"
    }
  }

  /// The BYOK key this provider authenticates with (client-direct, Phase 1).
  var byokProvider: BYOKProvider {
    switch self {
    case .openai, .gptLive: return .openai
    case .gemini: return .gemini
    }
  }

  /// The other realtime provider — used by the hub's failover chain: when the
  /// Auto-selected provider can't connect, the hub tries this one before dropping to
  /// the legacy Claude cascade. GPT-Live (the default) falls back to Gemini; the
  /// legacy OpenAI realtime and Gemini lanes keep their existing pairing.
  var alternate: RealtimeHubProvider {
    switch self {
    case .openai: return .gemini
    case .gemini: return .openai
    case .gptLive: return .gemini
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
  /// GPT-Live is the default; an explicit "GPT Realtime 2" selection stays on the
  /// legacy OpenAI realtime lane (matching `RealtimeOmniService`), and Gemini stays
  /// selectable (and is GPT-Live's failover alternate).
  var provider: RealtimeHubProvider {
    switch RealtimeOmniSettings.shared.effectiveProvider {
    case .gptLive, .auto: return .gptLive
    case .gptRealtime2: return .openai
    case .geminiFlashLive: return .gemini
    }
  }

  /// Whether `candidate` is a provider the user actually picked for voice.
  ///
  /// `.auto` is the default and is not a pick. It resolves through `AutoModelSelector`
  /// (and falls back to Gemini Live), so treating it as a choice would spend a stored
  /// Gemini key on behalf of every user who never opened Advanced → Voice Model — a
  /// provider they never chose, selected by a benchmark rather than by them. Only an
  /// explicit selection unlocks a key that the Developer Keys provider does not already
  /// cover; `.auto` keeps the older, stricter rule.
  func isVoiceModelChoice(_ candidate: RealtimeHubProvider) -> Bool {
    RealtimeOmniSettings.shared.selectedProvider != .auto && candidate == provider
  }

  /// True when the hub can connect client-direct with the user's own provider key
  /// (BYOK / dev key). Managed users without a key connect via a minted ephemeral
  /// token instead (see RealtimeHubController.ensureWarm); both reach the hub.
  var canConnect: Bool {
    APIKeyService.selectedRealtimeBYOKKey(
      for: provider.byokProvider,
      chosenForVoice: isVoiceModelChoice(provider)) != nil
  }
}
