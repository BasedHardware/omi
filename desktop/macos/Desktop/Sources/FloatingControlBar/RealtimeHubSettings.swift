import Foundation

// MARK: - Realtime Hub (Phase 1)
//
// "Realtime-as-hub": instead of the cascade (STT → router → Claude → TTS), one
// realtime model is the single hub. It does in-session STT, reasoning, routing
// (as tool choice), and speaks the answer. Its tools call the EXISTING backend
// endpoints / app code — no new backend routes.
//
// Phase 1 is CLIENT-DIRECT + dev/test only: the realtime WS connects straight to
// the provider with the user's own BYOK key (see APIKeyService). It is gated so
// it never runs for managed (non-BYOK) users. Phase 2 will replace the BYOK key
// with a server-minted ephemeral token to make it shippable.

enum RealtimeHubProvider: String, CaseIterable, Sendable {
  case openai
  case gemini

  var displayName: String {
    switch self {
    case .openai: return "OpenAI Realtime"
    case .gemini: return "Gemini Live"
    }
  }

  var subtitle: String {
    switch self {
    case .openai: return "gpt-realtime-2 · native spoken audio"
    case .gemini: return "gemini native-audio Live · spoken audio + tools"
    }
  }

  /// Concrete model identifier sent to the provider.
  var modelID: String {
    switch self {
    case .openai: return "gpt-realtime-2"
    // Native-audio Live model. NOTE (deviation): the original plan called for a
    // TEXT-modality half-cascade model spoken via AVSpeechSynthesizer, but Google
    // deprecated the half-cascade Live models — every model that currently exposes
    // bidiGenerateContent is native-audio and rejects TEXT modality (close 1007).
    // Verified function calling works on this one; it speaks via native audio (24k
    // PCM) played by StreamingPCMPlayer, same as OpenAI.
    case .gemini: return "gemini-2.5-flash-native-audio-preview-12-2025"
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

  private let enabledKey = "realtimeHubEnabled"
  private let providerKey = "realtimeHubProvider"

  private init() {
    UserDefaults.standard.register(defaults: [
      enabledKey: false,
      providerKey: RealtimeHubProvider.openai.rawValue,
    ])
  }

  /// Master switch. When off, the floating bar uses the legacy STT → router →
  /// Claude → TTS cascade. Ships behind this flag.
  var isEnabled: Bool {
    get { UserDefaults.standard.bool(forKey: enabledKey) }
    set {
      UserDefaults.standard.set(newValue, forKey: enabledKey)
      NotificationCenter.default.post(name: .realtimeHubSettingsDidChange, object: nil)
    }
  }

  var provider: RealtimeHubProvider {
    get {
      let raw = UserDefaults.standard.string(forKey: providerKey)
      return raw.flatMap(RealtimeHubProvider.init(rawValue:)) ?? .openai
    }
    set {
      UserDefaults.standard.set(newValue.rawValue, forKey: providerKey)
      NotificationCenter.default.post(name: .realtimeHubSettingsDidChange, object: nil)
    }
  }

  /// The hub may only run client-direct when the user has supplied the selected
  /// provider's own key (BYOK / dev key). This is the managed-user gate: managed
  /// users have no BYOK key, so the hub stays off and the cascade is used.
  var canConnect: Bool {
    APIKeyService.byokKey(provider.byokProvider) != nil
  }

  /// True when the hub should drive this PTT turn (enabled + a usable key).
  var isActive: Bool { isEnabled && canConnect }
}

extension Notification.Name {
  static let realtimeHubSettingsDidChange = Notification.Name("realtimeHubSettingsDidChange")
}
