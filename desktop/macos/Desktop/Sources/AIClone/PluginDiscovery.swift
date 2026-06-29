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
        let bearerToken: String
        let devMode: Bool
        let pluginType: String
        let instanceID: String
        let startedAt: TimeInterval
    }

    /// Path: `~/.config/omi/ai-clone-plugin.json`
    /// Uses ProcessInfo.environment["HOME"] which matches what the Python
    /// plugin sees (it uses `Path.home()` which reads $HOME). NSHomeDirectory()
    /// can return a different path under some macOS app-launch contexts.
    static var filePath: String {
        let home = ProcessInfo.processInfo.environment["HOME"] ?? NSHomeDirectory()
        return home + "/.config/omi/ai-clone-plugin.json"
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

        // Prefer public_url (the tunnel URL) if present — that's what
        // Telegram/Meta need to reach the plugin from outside. Fall back
        // to plugin_url (localhost) for same-machine-only testing.
        let url = (json["public_url"] as? String).flatMap { $0.isEmpty ? nil : $0 } ?? pluginURL

        return Info(
            pluginURL: pluginURL,
            publicURL: json["public_url"] as? String,
            bearerToken: bearerToken,
            devMode: json["dev_mode"] as? Bool ?? false,
            pluginType: json["plugin_type"] as? String ?? "unknown",
            instanceID: json["instance_id"] as? String ?? "",
            startedAt: json["started_at"] as? TimeInterval ?? 0
        )
    }

    /// Check whether the discovery file was written "recently" (within
    /// the last `maxAgeSeconds`). A stale file likely means the plugin
    /// crashed or was stopped — the desktop shouldn't auto-configure
    /// from a dead plugin.
    static func isFresh(maxAgeSeconds: TimeInterval = 3600) -> Bool {
        guard let info = read() else { return false }
        guard info.startedAt > 0 else { return true }  // no timestamp = assume fresh
        let age = Date().timeIntervalSince1970 - info.startedAt
        return age < maxAgeSeconds
    }
}