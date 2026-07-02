import Foundation
import Security

/// Thin wrapper around the macOS Keychain for AI Clone plugin secrets.
///
/// Two long-lived credentials are stored here:
/// - the plugin bearer token (`AI_CLONE_PLUGIN_TOKEN` on the plugin service)
/// - the user's `omi_dev_...` developer API key
///
/// Both were previously in `UserDefaults` (along with the non-secret
/// plugin URL). UserDefaults is a plaintext plist on disk readable by
/// any process running as the user (e.g. `defaults read
/// com.omi.desktop-dev`), so the long-lived secrets should not have
/// been there in the first place. Identified by maintainer security
/// review on PR #8528.
///
/// ## What this migration actually provides
///
/// The Keychain improves on the UserDefaults baseline in two ways:
///
/// 1. **Opportunistic exposure is blocked.** Other apps running as
///    the same user can't `cat` the file or `defaults read` the plist
///    to learn the secret. They would need to know the exact
///    `kSecAttrService` (bundle id) + `kSecAttrAccount` (secret name)
///    AND call the Security framework correctly. This raises the bar
///    from "trivial file read" to "targeted API call".
///
/// 2. **Locked-screen gating via `kSecAttrAccessibleWhenUnlocked`.**
///    The item is unavailable while the screen is locked, reducing
///    the window of physical-access exposure (someone at an unlocked
///    Mac can still read it; someone at a locked Mac cannot).
///
/// ## What this migration does NOT provide
///
/// Stronger isolation would require `com.apple.security.app-sandbox`
/// (currently `<false/>` in Omi.entitlements) AND a keychain access
/// group with the `keychain-access-groups` entitlement. Without
/// sandboxing, SecItem calls go to the legacy file-based keychain
/// (`~/Library/Keychains/login.keychain-db`), which is readable by any
/// process running as the same user — so `kSecAttrAccessibleWhenUnlocked`
/// controls WHEN the item is available (unlocked screen) but NOT WHICH
/// PROCESS can read it. Other user processes that know the bundle id
/// and secret name CAN read these items. (Identified by cubic review
/// on PR #8528.) Sandboxing the app is a project-wide architectural
/// decision tracked separately; this commit is the realistic
/// improvement within current entitlements.
///
/// ## Why not a third-party Keychain wrapper?
///
/// The native Security framework is ~30 lines for the operations we
/// need, doesn't require an extra SwiftPM dependency, and Apple's
/// reference impl handles the ACL / `kSecAttrAccessible` policy
/// correctly.
///
/// ## Threading
///
/// All Keychain APIs are thread-safe per Apple. We do not maintain
/// any in-memory cache, so concurrent reads are simple independent
/// SecItemCopyMatching calls — cheap and correct.
enum AICloneKeychain {

    /// kSecAttrService for our keychain items. Combined with the
    /// per-secret `kSecAttrAccount` (the secret's name) this gives
    /// each secret a unique address in the user keychain.
    ///
    /// The bundle id is used so dev (`com.omi.desktop-dev`) and prod
    /// (`com.omi.computer-macos`) installs have separate keychain
    /// entries — otherwise running dev would clobber a prod user's
    /// stored tokens, and vice versa.
    static let service: String = {
        Bundle.main.bundleIdentifier ?? "com.omi.desktop-dev.aiclone"
    }()

    enum Key: String {
        case pluginBearerToken = "ai_clone.plugin_bearer_token"
        case devApiKey = "ai_clone.omi_dev_api_key"
        /// Telethon session string for the user-account plugin. This
        /// is a FULLY-COMPROMISING identity secret — anyone with the
        /// string can read all of the user's Telegram chats, send
        /// as the user, and the only revocation path is Settings →
        /// Devices on the user's phone. Held in Keychain (encrypted at
        /// rest, only readable when the screen is unlocked) rather
        /// than UserDefaults (plaintext plist readable by any process
        /// as the same user). See plan §7 for the threat model.
        case telegramUserSession = "ai_clone.telegram_user_session"
    }

    enum KeychainError: Error, LocalizedError {
        case unexpectedStatus(OSStatus)
        case dataConversion

        var errorDescription: String? {
            switch self {
            case .unexpectedStatus(let s): return "Keychain error \(s)"
            case .dataConversion: return "Keychain data conversion error"
            }
        }
    }

    // MARK: - Public API

    /// Read a secret. Returns nil if the key is unset. Throws on a
    /// real Keychain failure (the caller can decide whether to surface
    /// that to the user — typically we'd log + show a "keychain
    /// unavailable" message rather than crash).
    static func get(_ key: Key) throws -> String? {
        var query = baseQuery(for: key)
        query[kSecReturnData as String] = kCFBooleanTrue
        query[kSecMatchLimit as String] = kSecMatchLimitOne

        var item: CFTypeRef?
        let status = SecItemCopyMatching(query as CFDictionary, &item)

        switch status {
        case errSecSuccess:
            guard let data = item as? Data,
                  let str = String(data: data, encoding: .utf8) else {
                throw KeychainError.dataConversion
            }
            return str
        case errSecItemNotFound:
            return nil
        default:
            throw KeychainError.unexpectedStatus(status)
        }
    }

    /// Write or update a secret. Empty string is treated as "delete"
    /// (so setting a field to "" in the UI clears it from the
    /// keychain rather than persisting an empty value).
    static func set(_ key: Key, _ value: String) throws {
        if value.isEmpty {
            try delete(key)
            return
        }

        let data = Data(value.utf8)
        var query = baseQuery(for: key)
        // kSecAttrAccessible controls WHEN the item is available
        // (while the keychain is unlocked, i.e. while the user is
        // logged in / screen is unlocked). It does NOT control which
        // process can read the item — that requires the app sandbox
        // entitlement + `keychain-access-groups` (not currently set
        // on this project; see AICloneKeychain.swift's docstring for
        // the residual-risk discussion).
        //
        // We pick `kSecAttrAccessibleWhenUnlocked` (vs. `AfterFirstUnlock`)
        // because nothing in the AI Clone flow needs to read secrets
        // before the user has logged in this session.
        query[kSecValueData as String] = data
        query[kSecAttrAccessible as String] = kSecAttrAccessibleWhenUnlocked

        let status = SecItemAdd(query as CFDictionary, nil)
        switch status {
        case errSecSuccess:
            return
        case errSecDuplicateItem:
            // Item already exists — update it in place.
            let attrsToUpdate: [String: Any] = [
                kSecValueData as String: data,
                kSecAttrAccessible as String: kSecAttrAccessibleWhenUnlocked,
            ]
            let updateStatus = SecItemUpdate(baseQuery(for: key) as CFDictionary,
                                             attrsToUpdate as CFDictionary)
            guard updateStatus == errSecSuccess else {
                throw KeychainError.unexpectedStatus(updateStatus)
            }
        default:
            throw KeychainError.unexpectedStatus(status)
        }
    }

    /// Remove a secret. Idempotent — succeeds silently if not present.
    static func delete(_ key: Key) throws {
        let status = SecItemDelete(baseQuery(for: key) as CFDictionary)
        guard status == errSecSuccess || status == errSecItemNotFound else {
            throw KeychainError.unexpectedStatus(status)
        }
    }

    // MARK: - Migration

    /// Move a legacy UserDefaults value into the Keychain. Called
    /// once at app startup for each secret that may have been
    /// persisted by a previous build. After successful migration the
    /// UserDefaults entry is removed.
    ///
    /// - Returns: true if a migration happened (caller can use this for
    ///   telemetry / "your secrets were upgraded" toast).
    @discardableResult
    static func migrateFromUserDefaults(
        _ key: Key,
        defaultsKey: String,
        defaults: UserDefaults = .standard
    ) throws -> Bool {
        guard let oldValue = defaults.string(forKey: defaultsKey),
              !oldValue.isEmpty else {
            return false
        }
        // Don't clobber a real Keychain value if one already exists
        // (e.g. user had keychain entry from a fresh install on the
        // same machine, then restored from a backup that put an old
        // UserDefaults value back).
        if try get(key) == nil {
            try set(key, oldValue)
        }
        defaults.removeObject(forKey: defaultsKey)
        return true
    }

    // MARK: - Internal

    private static func baseQuery(for key: Key) -> [String: Any] {
        return [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: key.rawValue,
        ]
    }
}