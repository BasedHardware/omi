import Foundation

// MARK: - Realtime Omni Provider
//
// A single realtime "omni" model handles voice I/O for the floating bar:
//   - speech-to-text (replaces Deepgram)
//   - text-to-speech (replaces OpenAI TTS)
// Reasoning + every agent/tool still runs through ChatProvider (pi-mono/Claude),
// so the omni model is only the voice shell — nothing about tools changes.
//
// The user picks a provider in Advanced settings. "Auto" defers to
// AutoModelSelector, which refreshes a best-by-quality/speed pick daily from
// Artificial Analysis (https://artificialanalysis.ai).

enum RealtimeOmniProvider: String, CaseIterable, Sendable {
    case auto
    case geminiFlashLive
    case gptRealtime2

    var displayName: String {
        switch self {
        case .auto:           return "Auto"
        case .geminiFlashLive: return "Gemini 3.1 Flash Live"
        case .gptRealtime2:    return "GPT Realtime 2"
        }
    }

    var subtitle: String {
        switch self {
        case .auto:           return "Daily-picks the best model by quality & speed"
        case .geminiFlashLive: return "Google · native audio + vision, lowest cost"
        case .gptRealtime2:    return "OpenAI · GA speech-to-speech"
        }
    }

    /// Concrete model identifier sent to the provider. `.auto` resolves elsewhere.
    var modelID: String {
        switch self {
        case .auto:           return RealtimeOmniProvider.geminiFlashLive.modelID
        case .geminiFlashLive: return "gemini-3.1-flash-live-preview"
        case .gptRealtime2:    return "gpt-realtime-2"
        }
    }

    /// Concrete providers the resolver may choose from for `.auto`.
    static var selectable: [RealtimeOmniProvider] { [.geminiFlashLive, .gptRealtime2] }
}

// MARK: - Settings store (mirrors AssistantSettings persistence pattern)

@MainActor
final class RealtimeOmniSettings {
    static let shared = RealtimeOmniSettings()

    private let providerKey = "realtimeOmniProvider"
    /// Master switch: when off, the floating bar keeps using the legacy
    /// Deepgram STT + OpenAI/system TTS cascade. Lets us ship behind a flag.
    private let enabledKey = "realtimeOmniEnabled"

    private init() {
        UserDefaults.standard.register(defaults: [
            // Default to OpenAI (GPT Realtime 2); the user can switch to Gemini or Auto
            // in Advanced → Voice Model. This default also drives the realtime hub provider.
            providerKey: RealtimeOmniProvider.gptRealtime2.rawValue,
            enabledKey: false,
        ])
    }

    var isEnabled: Bool {
        get { UserDefaults.standard.bool(forKey: enabledKey) }
        set {
            UserDefaults.standard.set(newValue, forKey: enabledKey)
            NotificationCenter.default.post(name: .realtimeOmniSettingsDidChange, object: nil)
        }
    }

    /// The provider as configured by the user (may be `.auto`).
    var selectedProvider: RealtimeOmniProvider {
        get {
            let raw = UserDefaults.standard.string(forKey: providerKey)
            return raw.flatMap(RealtimeOmniProvider.init(rawValue:)) ?? .auto
        }
        set {
            UserDefaults.standard.set(newValue.rawValue, forKey: providerKey)
            NotificationCenter.default.post(name: .realtimeOmniSettingsDidChange, object: nil)
        }
    }

    /// The concrete provider to actually use right now. Resolves `.auto` via the
    /// cached daily benchmark pick (falling back to Gemini when no pick exists).
    var effectiveProvider: RealtimeOmniProvider {
        guard selectedProvider == .auto else { return selectedProvider }
        return AutoModelSelector.shared.currentPick ?? .geminiFlashLive
    }
}

extension Notification.Name {
    static let realtimeOmniSettingsDidChange = Notification.Name("realtimeOmniSettingsDidChange")
}
