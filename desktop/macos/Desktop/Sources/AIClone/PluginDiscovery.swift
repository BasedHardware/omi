import Foundation

/// Reads the plugin discovery file written by the Telegram/WhatsApp plugin
/// at startup.
///
/// The plugin writes `~/.config/omi/ai-clone-plugin.json` containing its
/// URL, bearer token, and dev-mode flag. This struct parses that file so
/// `AICloneConfig` can auto-fill the AI Clone settings without the user
/// copy/pasting anything.
///
/// Zero-config flow:
/// 1. User starts the plugin (`uvicorn ...` or `./start.sh`)
/// 2. Plugin's FastAPI lifespan writes the discovery file
/// 3. User opens Omi Desktop → Settings → AI Clone
/// 4. `AICloneConfig.init()` calls `PluginDiscovery.read()`
/// 5. If found + valid → URL + bearer auto-filled into Keychain/UserDefaults
/// 6. User just clicks "Connect" on Telegram → done
///
/// The discovery file is a bootstrap convenience, not the source of truth.
/// Once read, the values are persisted to Keychain (bearer) and UserDefaults
/// (URL). If the plugin restarts with a new token, the discovery file
/// changes, and the desktop picks up the new value on next launch.
struct PluginDiscovery {

    struct Info {
        let pluginURL: String
        let publicURL: String?
        /// publicURL if set + valid, otherwise pluginURL. Convenience
        /// for callers that just need "the URL the outside world would
        /// use to reach the plugin" (e.g. the desktop-side settings
        /// banner). Callers that specifically want the LOCAL URL
        /// (desktop → plugin /health, /setup, /toggle) should use
        /// pluginURL, not this field.
        let effectivePublicURL: String
        let bearerToken: String
        let devMode: Bool
        let pluginType: String
        let instanceID: String
        let startedAt: TimeInterval
        let omiBaseURL: String?
    }

    /// Path: `~/.config/omi/ai-clone-plugin.json`
    /// Uses ProcessInfo.environment["HOME"] which matches what the Python
    /// plugin sees (it uses `Path.home()` which reads $HOME). NSHomeDirectory()
    /// can return a different path under some macOS app-launch contexts.
    static var filePath: String {
        let home = ProcessInfo.processInfo.environment["HOME"] ?? NSHomeDirectory()
        return home + "/.config/omi/ai-clone-plugin.json"
    }

    /// User-account plugin (plan §7) discovery file. Distinct from
    /// the bot plugin's `ai-clone-plugin.json` — the user-account
    /// plugin authenticates as the user's PERSONAL Telegram account
    /// (Telethon), so the discovery payload carries account
    /// metadata (phone, name, device_label) and the URL/bearer used
    /// to reach the local FastAPI service. The Telethon session
    /// string is NOT in the file (it's in Keychain only).
    static var userAccountFilePath: String {
        let home = ProcessInfo.processInfo.environment["HOME"] ?? NSHomeDirectory()
        return home + "/.config/omi/ai-clone-telegram-user.json"
    }

    /// Read + parse the discovery file. Returns nil if the file doesn't
    /// exist, is malformed, or has an unsupported version.
    static func read() -> Info? {
        let path = filePath
        guard FileManager.default.fileExists(atPath: path) else {
            return nil
        }

        guard let data = FileManager.default.contents(atPath: path),
              let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
        else {
            NSLog("PluginDiscovery: file exists but could not parse JSON at \(path)")
            return nil
        }

        // Version check — refuse to read a higher version (forward-compat).
        // Version 1 is the only format we know.
        guard let version = json["version"] as? Int, version == 1 else {
            NSLog("PluginDiscovery: unsupported version \(json["version"] ?? "?"), expected 1")
            return nil
        }

        guard let pluginURL = json["plugin_url"] as? String, !pluginURL.isEmpty,
              let bearerToken = json["bearer_token"] as? String, !bearerToken.isEmpty
        else {
            NSLog("PluginDiscovery: missing required fields (plugin_url or bearer_token)")
            return nil
        }

        // Reject the file if plugin_url is not a valid http(s) URL.
        // The discovery file is auto-applied to settings; auto-filling
        // an arbitrary non-empty string (e.g. a shell command, an
        // html blob, a path with a scheme the URLSession client can't
        // speak) would either crash URLSession, silently fail health
        // checks, or surface to the user as a non-actionable error.
        // P2 (cubic).
        guard Self.isLikelyValidPluginURL(pluginURL) else {
            NSLog("PluginDiscovery: plugin_url '\(pluginURL)' is not a valid http(s) URL — ignoring")
            return nil
        }

        // public_url is optional. Same validation when present, but
        // empty-string is treated as "not provided" rather than invalid.
        // public_url is optional. When present but invalid, we
        // ignore it (set to nil) rather than failing the entire
        // discovery — the plugin_url is the authoritative local
        // URL and is always required. A malformed optional tunnel
        // URL should not block local discovery.
        // cubic review 4630319623: previously returned nil on
        // invalid public_url, which disabled otherwise-valid
        // local discovery.
        let rawPublic = json["public_url"] as? String
        let publicURL: String?
        if let raw = rawPublic, !raw.isEmpty {
            if Self.isLikelyValidPluginURL(raw) {
                publicURL = raw
            } else {
                NSLog("PluginDiscovery: public_url '\(raw)' is not a valid http(s) URL — ignoring (falling back to plugin_url)")
                publicURL = nil
            }
        } else {
            publicURL = nil
        }

        // The desktop client should prefer the LOCAL plugin_url
        // (http://127.0.0.1:PORT) for /health, /setup, /toggle — those
        // are desktop-to-plugin calls on the same machine. The public_url
        // is the TUNNEL URL that Telegram/Meta need to reach the plugin
        // from outside the user's network. They're different consumers
        // with different needs; surface both in Info and let the caller
        // pick. P1 (cubic): publicURL was previously discarded here.
        let effectivePublicURL = publicURL ?? pluginURL

        return Info(
            pluginURL: pluginURL,
            publicURL: publicURL,
            effectivePublicURL: effectivePublicURL,
            bearerToken: bearerToken,
            devMode: json["dev_mode"] as? Bool ?? false,
            pluginType: json["plugin_type"] as? String ?? "unknown",
            instanceID: json["instance_id"] as? String ?? "",
            startedAt: json["started_at"] as? TimeInterval ?? 0,
            omiBaseURL: json["omi_base_url"] as? String
        )
    }

    /// True iff the given string parses as an http(s) URL with a host.
    /// Used to reject arbitrary non-empty strings before auto-fill.
    private static func isLikelyValidPluginURL(_ raw: String) -> Bool {
        guard let url = URL(string: raw),
              let scheme = url.scheme?.lowercased(),
              scheme == "http" || scheme == "https",
              let host = url.host, !host.isEmpty
        else { return false }
        return true
    }

    /// Check whether the discovery file was written "recently" (within
    /// the last `maxAgeSeconds`). A stale file likely means the plugin
    /// crashed or was stopped — the desktop shouldn't auto-configure
    /// from a dead plugin.
    static func isFresh(maxAgeSeconds: TimeInterval = 3600) -> Bool {
        guard let info = read() else { return false }
        // cubic review 4630319623: a missing/zero timestamp is
        // treated as NOT fresh (fail conservative). The previous
        // code assumed fresh, which meant a stale discovery file
        // without a timestamp would be trusted indefinitely —
        // dangerous for an auto-applied credential/discovery path.
        guard info.startedAt > 0 else { return false }
        let age = Date().timeIntervalSince1970 - info.startedAt
        return age < maxAgeSeconds
    }

    // MARK: - User-account plugin (plan §7)

    /// Parsed payload of `ai-clone-telegram-user.json`. The user-account
    /// plugin writes this file at startup so the desktop can auto-fill
    /// the personal Telegram plugin's URL + bearer token + account
    /// metadata. The Telethon session string is NOT in the file (it's
    /// held in Keychain on the desktop side, plumbed to the plugin
    /// via a one-shot stdin pipe at startup).
    struct UserAccountInfo {
        let pluginURL: String
        let bearerToken: String
        let phone: String?
        let name: String?
        let deviceLabel: String?
    }

    /// Read + parse the user-account discovery file. Returns nil if
    /// the file doesn't exist, is malformed, has an unsupported
    /// version, or is missing the required fields (plugin_url,
    /// bearer_token). The session string is NOT a required field —
    /// it's held in Keychain, not on disk.
    static func readUserAccount() -> UserAccountInfo? {
        let path = userAccountFilePath
        guard FileManager.default.fileExists(atPath: path) else {
            return nil
        }
        guard let data = FileManager.default.contents(atPath: path),
              let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
        else {
            NSLog("PluginDiscovery: user-account file exists but could not parse JSON at \(path)")
            return nil
        }
        guard let version = json["version"] as? Int, version == 1 else {
            NSLog("PluginDiscovery: user-account unsupported version")
            return nil
        }
        guard let pluginURL = json["plugin_url"] as? String, !pluginURL.isEmpty,
              let bearerToken = json["bearer_token"] as? String, !bearerToken.isEmpty
        else {
            NSLog("PluginDiscovery: user-account missing plugin_url or bearer_token")
            return nil
        }
        guard Self.isLikelyValidPluginURL(pluginURL) else {
            NSLog("PluginDiscovery: user-account plugin_url is not a valid http(s) URL — ignoring")
            return nil
        }
        return UserAccountInfo(
            pluginURL: pluginURL,
            bearerToken: bearerToken,
            phone: json["phone"] as? String,
            name: json["name"] as? String,
            deviceLabel: json["device_label"] as? String,
        )
    }
}