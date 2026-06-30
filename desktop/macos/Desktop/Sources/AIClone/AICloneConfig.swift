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

    /// True if the current config was auto-discovered from the plugin's
    /// discovery file (rather than manually entered by the user).
    /// Drives the UI banner: "Plugin discovered automatically".
    @Published var isAutoDiscovered: Bool = false

    /// True when the plugin is running in dev mode (the discovery file
    /// said so). In dev mode, the dev API key is optional because the
    /// local mock persona doesn't validate it.
    @Published var pluginDevMode: Bool = false
    /// The backend URL the plugin uses for persona calls. When the
    /// plugin is local (localhost), the desktop creates the persona + API
    /// key on that backend instead of prod. Prevents persona_id mismatch.
    @Published var discoveryBackendURL: String? = nil

    /// The PUBLIC URL of the plugin (the tunnel / external address
    /// Telegram or Meta use to reach the plugin from outside). Used by
    /// the desktop's ConnectSheet as the `publicBaseUrl` payload to the
    /// plugin's /setup endpoint — Telegram's webhook must be reachable
    /// from the internet, so we can't pass the local `pluginURL`
    /// (loopback). Falls back to pluginURL when no tunnel is configured
    /// (same-machine-only testing, where Telegram isn't involved).
    @Published var publicBaseURL: String? = nil

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

        // Discovery is now applied EXPLICITLY via applyDiscovery() —
        // called from app startup (OmiApp.swift), not from init. P2
        // (cubic): init() previously called applyDiscoveryIfAvailable()
        // unconditionally, which read ~/.config/omi/ai-clone-plugin.json
        // and mutated the injected UserDefaults + Keychain. That broke
        // the hermetic contract of `defaults` (any test using a stub
        // UserDefaults would have its state mutated by a real file on
        // the test machine) and made unit tests non-deterministic.
    }

    /// Read `~/.config/omi/ai-clone-plugin.json` and fill any empty
    /// fields (pluginURL, bearerToken). Called from app startup
    /// (OmiApp.swift), not from init, so unit tests can construct
    /// AICloneConfig without touching the real discovery file.
    ///
    /// For the dev API key: the discovery file doesn't contain it
    /// (it's user-specific). If `devMode == true` in the discovery
    /// file, the plugin is paired with a local mock persona that
    /// doesn't validate the key — so we leave the field empty and
    /// the UI will show a lighter "optional" indicator.
    func applyDiscovery() {
        let path = PluginDiscovery.filePath
        log("AICloneConfig: checking discovery file at \(path)")
        guard let discovery = PluginDiscovery.read() else {
            log("AICloneConfig: no discovery file found")
            return
        }

        // Use the LOCAL pluginURL (NOT the tunnel publicURL) for the
        // desktop client's API base URL. Desktop and plugin run on the
        // same machine, so /health, /setup, /status, /toggle should hit
        // the plugin directly over loopback / LAN. The publicURL (the
        // tunnel) is needed by Telegram/Meta to reach the plugin from
        // outside, but routing our own control traffic through the
        // tunnel adds latency and exposes control calls to a third
        // party. Falls back to pluginURL when publicURL is absent
        // (same-machine-only testing).
        //
        // P1 from cubic AI review (PR #8682): the previous code used
        // `discovery.publicURL ?? discovery.pluginURL`, which meant a
        // configured tunnel would silently route all desktop control
        // calls through the external tunnel. Switched to pluginURL.
        let discoveryURL = discovery.pluginURL

        var changed = false

        if self.pluginURL.isEmpty {
            // Write directly to UserDefaults (bypassing didSet which may
            // not fire reliably during init). Then set the property for
            // the in-memory state.
            defaults.set(discoveryURL, forKey: DefaultsKeys.pluginURL)
            self.pluginURL = discoveryURL
            changed = true
        }

        if self.bearerToken.isEmpty {
            // Write directly to Keychain.
            try? AICloneKeychain.set(.pluginBearerToken, discovery.bearerToken)
            self.bearerToken = discovery.bearerToken
            changed = true
        }

        if changed {
            // Use the app's log() function so it appears in /tmp/omi-dev.log
            // (NSLog goes to unified logging only, not the dev log file).
            log("AICloneConfig: auto-discovered plugin at \(discoveryURL) (type=\(discovery.pluginType), devMode=\(discovery.devMode))")
            self.isAutoDiscovered = true
            self.pluginDevMode = discovery.devMode
            self.discoveryBackendURL = discovery.omiBaseURL
            // Capture the public/tunnel URL so ConnectSheet can pass it
            // to the plugin's /setup endpoint as publicBaseUrl. Telegram
            // and Meta can't reach pluginURL (loopback) from outside;
            // they need the tunnel URL. Falls back to pluginURL when
            // publicURL is absent (same-machine testing only).
            self.publicBaseURL = discovery.publicURL ?? discovery.pluginURL
        }
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

    /// True if the plugin service is reachable (URL + bearer configured).
    /// The dev API key is NOT required for this check — it's only needed
    /// at /setup time (inside the Connect sheet). The Connect button is
    /// gated on this property, so requiring the dev API key here would
    /// prevent the user from even opening the Connect sheet.
    var isPluginReady: Bool {
        isPluginURLConfigured && isBearerTokenConfigured
    }

    /// True if all values needed to call the plugin are present,
    /// INCLUDING the dev API key. Used for the status indicator in
    /// PluginURLCard (shows whether the user still needs to provide
    /// the dev API key), NOT for gating the Connect button.
    ///
    /// In dev mode (plugin paired with local mock persona), the dev API
    /// key is optional — the mock doesn't validate it.
    var isFullyConfigured: Bool {
        if pluginDevMode {
            return isPluginReady
        }
        return isPluginReady && isDevApiKeyConfigured
    }
}