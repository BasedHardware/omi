import Foundation
import Combine

/// Persisted configuration for the AI Clone plugin service.
///
/// Three values, all stored in UserDefaults:
/// 1. Plugin service URL (e.g. https://my-omi-clone.example.com)
/// 2. Plugin bearer token — matches the AI_CLONE_PLUGIN_TOKEN env var set on
///    the plugin service. Sent as `Authorization: Bearer <token>` on every
///    request from desktop -> plugin.
/// 3. The user's `omi_dev_...` developer API key — forwarded to the plugin's
///    `/setup` so the plugin can call the backend persona chat endpoint on
///    the user's behalf.
///
/// Published via @Published so SwiftUI views update reactively when these
/// change (e.g. when the user saves new values from a settings sheet).
@MainActor
final class AICloneConfig: ObservableObject {
    static let shared = AICloneConfig()

    private enum Keys {
        static let pluginURL = "ai_clone_plugin_url"
        static let bearerToken = "ai_clone_plugin_bearer_token"
        static let devApiKey = "ai_clone_omi_dev_api_key"
    }

    private let defaults: UserDefaults

    @Published var pluginURL: String {
        didSet { defaults.set(pluginURL, forKey: Keys.pluginURL) }
    }

    @Published var bearerToken: String {
        didSet { defaults.set(bearerToken, forKey: Keys.bearerToken) }
    }

    @Published var omiDevApiKey: String {
        didSet { defaults.set(omiDevApiKey, forKey: Keys.devApiKey) }
    }

    init(defaults: UserDefaults = .standard) {
        self.defaults = defaults
        self.pluginURL = defaults.string(forKey: Keys.pluginURL) ?? ""
        self.bearerToken = defaults.string(forKey: Keys.bearerToken) ?? ""
        self.omiDevApiKey = defaults.string(forKey: Keys.devApiKey) ?? ""
    }

    /// True if the plugin URL is set and at least looks like a URL.
    var isPluginURLConfigured: Bool {
        guard !pluginURL.isEmpty else { return false }
        guard let url = URL(string: pluginURL) else { return false }
        return url.scheme?.lowercased() == "http" || url.scheme?.lowercased() == "https"
    }

    /// True if the bearer token is set (non-empty).
    var isBearerTokenConfigured: Bool { !bearerToken.isEmpty }

    /// True if the dev API key is set (non-empty).
    var isDevApiKeyConfigured: Bool { !omiDevApiKey.isEmpty }

    /// True if all three values needed to call the plugin are present.
    var isFullyConfigured: Bool {
        isPluginURLConfigured && isBearerTokenConfigured && isDevApiKeyConfigured
    }
}