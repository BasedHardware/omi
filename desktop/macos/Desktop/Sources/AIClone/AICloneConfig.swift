import Foundation
import Combine

/// Persisted configuration for the AI Clone plugin service.
///
/// Three values, two of them stored in the macOS Keychain:
/// 1. Plugin service URL (e.g. https://my-omi-clone.example.com) — stored in
///    UserDefaults (non-secret; the URL is the destination, not a credential).
/// 2. Plugin bearer token — stored in Keychain via AICloneKeychain. Matches
///    the AI_CLONE_PLUGIN_TOKEN env var set on the plugin service. Sent as
///    `Authorization: Bearer <token>` on every request from desktop → plugin.
/// 3. The user's `omi_dev_...` developer API key — stored in Keychain via
///    AICloneKeychain. Forwarded to the plugin's `/setup` so the plugin can
///    call the backend persona chat endpoint on the user's behalf.
///
/// Why two stores: UserDefaults is a plaintext plist on disk readable by
/// any process running as the user. Storing the bearer token or the
/// developer API key there exposed them to other apps and to backup
/// exfiltration. Identified by maintainer security review on PR #8528 —
/// moved to Keychain (encrypted at rest, only this app's bundle id can
/// read). The plugin URL is non-secret and stays in UserDefaults.
///
/// Migration: a previous build stored both secrets in UserDefaults. On
/// first launch under this code, `migrateFromUserDefaultsIfNeeded()`
/// detects the old entries, copies them to Keychain, and deletes the
/// UserDefaults copy. Migration is idempotent — re-running on an already-
/// migrated machine is a no-op.
///
/// Published via @Published so SwiftUI views update reactively when these
/// change (e.g. when the user saves new values from a settings sheet).
@MainActor
final class AICloneConfig: ObservableObject {
    static let shared = AICloneConfig()

    /// Legacy UserDefaults keys. Kept here so the one-time migration
    /// can find them. New code reads/writes via AICloneKeychain.
    private enum LegacyDefaultsKeys {
        static let bearerToken = "ai_clone_plugin_bearer_token"
        static let devApiKey = "ai_clone_omi_dev_api_key"
    }

    private enum DefaultsKeys {
        static let pluginURL = "ai_clone_plugin_url"
    }

    private let defaults: UserDefaults

    @Published var pluginURL: String {
        didSet { defaults.set(pluginURL, forKey: DefaultsKeys.pluginURL) }
    }

    @Published var bearerToken: String {
        didSet {
            // Persist to Keychain. An empty string clears it.
            do {
                try AICloneKeychain.set(.pluginBearerToken, bearerToken)
            } catch {
                // Keychain failures are rare (the user has denied access
                // once) and shouldn't crash the app. Log and keep the
                // in-memory value — the user can retry on next save.
                NSLog("AICloneConfig: Keychain set failed: \(error)")
            }
        }
    }

    @Published var omiDevApiKey: String {
        didSet {
            do {
                try AICloneKeychain.set(.devApiKey, omiDevApiKey)
            } catch {
                NSLog("AICloneConfig: Keychain set failed: \(error)")
            }
        }
    }

    init(defaults: UserDefaults = .standard) {
        self.defaults = defaults
        self.pluginURL = defaults.string(forKey: DefaultsKeys.pluginURL) ?? ""
        // Default-initialize secrets to empty before calling any method
        // that uses self. Swift requires all stored properties set before
        // self is used.
        self.bearerToken = ""
        self.omiDevApiKey = ""

        // Migrate any legacy UserDefaults values BEFORE reading from
        // Keychain so that if a migration happens we read the moved
        // value rather than nil. Migration is best-effort and
        // idempotent; failures don't block init.
        migrateFromUserDefaultsIfNeeded(defaults: defaults)

        // Load current values from Keychain (may be empty).
        self.bearerToken = (try? AICloneKeychain.get(.pluginBearerToken)) ?? ""
        self.omiDevApiKey = (try? AICloneKeychain.get(.devApiKey)) ?? ""
    }

    /// Move legacy UserDefaults-stored secrets into the Keychain.
    /// Called once at init; idempotent.
    private func migrateFromUserDefaultsIfNeeded(defaults: UserDefaults) {
        _ = try? AICloneKeychain.migrateFromUserDefaults(
            .pluginBearerToken,
            defaultsKey: LegacyDefaultsKeys.bearerToken,
            defaults: defaults
        )
        _ = try? AICloneKeychain.migrateFromUserDefaults(
            .devApiKey,
            defaultsKey: LegacyDefaultsKeys.devApiKey,
            defaults: defaults
        )
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