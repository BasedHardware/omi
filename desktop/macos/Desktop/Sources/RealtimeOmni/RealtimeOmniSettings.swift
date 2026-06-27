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
            // Default to Auto: AutoModelSelector picks the best provider (currently Gemini),
            // and the hub fails over to the other realtime model (GPT Realtime), then the
            // Claude cascade, if it can't connect. The user can pin a provider in
            // Advanced → Voice Model. This default also drives the realtime hub provider.
            providerKey: RealtimeOmniProvider.auto.rawValue,
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

    /// The concrete provider to actually use right now. Resolves `.auto`:
    ///   1. v3: Try AutoRouter.shared.currentPick(for: .pttResponse) — the
    ///      v1+v2 framework's per-task pick. Map to a realtime-capable
    ///      provider (gemini or gpt-realtime). If the router picks a non-
    ///      realtime model (e.g., claude-sonnet-4-6), fall through.
    ///   2. Fall back to AutoModelSelector.shared.currentPick — the upstream
    ///      AA integration (RealtimeOmniProvider already validated).
    ///   3. Last resort: .geminiFlashLive.
    var effectiveProvider: RealtimeOmniProvider {
        guard selectedProvider == .auto else { return selectedProvider }
        if let routerPick = AutoRouter.shared.currentPick(for: .pttResponse),
           let provider = Self.realtimeProvider(for: routerPick) {
            return provider
        }
        return AutoModelSelector.shared.currentPick ?? .geminiFlashLive
    }

    /// Map a router model ID to a realtime-capable RealtimeOmniProvider.
    /// Returns nil if the model ID doesn't map to a realtime-capable provider
    /// (e.g., claude-sonnet-4-6 — not a realtime voice model).
    static func realtimeProvider(for modelId: String) -> RealtimeOmniProvider? {
        let id = modelId.lowercased()
        // Cubic review: broadened to handle common OpenAI realtime variants
        // (gpt-4o-realtime-preview, gpt-4o-mini-realtime, gpt-realtime-2,
        // gpt_realtime_2 with underscores, etc.). We match the gpt- prefix
        // OR the gpt_ prefix, and require "realtime" or "audio" in the name.
        // OpenAI's realtime models all match this pattern; other gpt-* models
        // (gpt-4o, gpt-4-turbo, etc.) don't have "realtime"/"audio" and are
        // correctly NOT matched here.
        let is_gpt = id.contains("gpt-") || id.contains("gpt_")
        if is_gpt && (id.contains("realtime") || id.contains("audio")) {
            return .gptRealtime2
        }
        if id.contains("gemini") {
            return .geminiFlashLive
        }
        return nil
    }
}

extension Notification.Name {
    static let realtimeOmniSettingsDidChange = Notification.Name("realtimeOmniSettingsDidChange")
}
