import Foundation
import LocalAuthentication
import Security

/// The credential set Context for Claude keeps between launches.
///
/// `expiryTime` is stored already-shortened (see `OmiAuth.expiryBuffer`) so every reader gets the
/// same answer to "is this usable?" without having to remember the safety margin.
struct OmiSession: Codable, Equatable, Sendable {
    let idToken: String
    let refreshToken: String
    /// Epoch seconds.
    let expiryTime: Double
    let tokenUserId: String

    var isExpired: Bool { Date().timeIntervalSince1970 >= expiryTime }
}

/// Context for Claude's own login-Keychain item — the only secret this app stores.
///
/// Deliberately **not** the Omi desktop app's `com.omi.desktop.firebase-rest-session.*` item, even
/// though it holds the same shape of session. That item's ACL is bound to the desktop app's signing
/// Team ID and code signature; a differently-signed binary reading it does not get a clean failure,
/// it gets the login-keychain password sheet ("Context for Claude wants to use your confidential information"),
/// which is both alarming and unanswerable. A separate service name means Context for Claude only ever touches
/// an item it created and therefore owns.
///
/// Two more constraints inherited from the same fix (desktop #9167):
/// - Never opt into the data-protection keychain (`kSecUseDataProtectionKeychain`). That requires a
///   `keychain-access-groups` entitlement a non-sandboxed Developer ID app does not have, and every
///   write fails with `errSecMissingEntitlement` (-34018) on the signed build.
/// - Never let SecItem raise UI: an `LAContext` with `interactionNotAllowed` makes calls that would
///   need a prompt fail closed instead.
enum SessionStore {
    static let service = "com.omi.context-for-claude.session"
    static let account = "omi-session"

    // MARK: - Read

    static func load() -> OmiSession? {
        var query = baseQuery()
        query[kSecReturnData as String] = true
        query[kSecMatchLimit as String] = kSecMatchLimitOne
        applySilentAuth(&query)

        var item: CFTypeRef?
        let status = SecItemCopyMatching(query as CFDictionary, &item)
        switch status {
        case errSecSuccess:
            guard let data = item as? Data else { return nil }
            guard let session = try? JSONDecoder().decode(OmiSession.self, from: data) else {
                // A shape we cannot read is worse than nothing: it would keep the app "signed in"
                // with no usable credential. Drop it so the next launch offers a clean sign-in.
                ContextLog.error("Stored session is unreadable; discarding it", "auth")
                clear()
                return nil
            }
            return session
        case errSecItemNotFound:
            return nil
        default:
            ContextLog.error("Keychain read unavailable (OSStatus \(status))", "auth")
            return nil
        }
    }

    // MARK: - Write

    /// Update-then-add, never delete-then-add: a delete followed by a failing add turns a
    /// temporarily locked keychain into permanent session loss.
    @discardableResult
    static func save(_ session: OmiSession) -> Bool {
        guard let data = try? JSONEncoder().encode(session) else {
            ContextLog.error("Could not encode session for storage", "auth")
            return false
        }

        var query = baseQuery()
        applySilentAuth(&query)
        let attributes: [String: Any] = [
            kSecValueData as String: data,
            kSecAttrAccessible as String: kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly,
        ]

        let updateStatus = SecItemUpdate(query as CFDictionary, attributes as CFDictionary)
        if updateStatus == errSecSuccess { return true }
        if updateStatus != errSecItemNotFound {
            ContextLog.error("Keychain update failed (OSStatus \(updateStatus))", "auth")
            return false
        }

        var addQuery = baseQuery()
        applySilentAuth(&addQuery)
        addQuery[kSecValueData as String] = data
        addQuery[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
        addQuery[kSecAttrLabel as String] = "Omi Context for Claude"

        let addStatus = SecItemAdd(addQuery as CFDictionary, nil)
        if addStatus == errSecSuccess { return true }
        if addStatus == errSecDuplicateItem {
            // Another process wrote between our update and our add.
            let retry = SecItemUpdate(query as CFDictionary, attributes as CFDictionary)
            if retry == errSecSuccess { return true }
            ContextLog.error("Keychain add/update race failed (OSStatus \(retry))", "auth")
            return false
        }
        ContextLog.error("Keychain add failed (OSStatus \(addStatus))", "auth")
        return false
    }

    // MARK: - Delete

    static func clear() {
        var query = baseQuery()
        applySilentAuth(&query)
        let status = SecItemDelete(query as CFDictionary)
        if status != errSecSuccess, status != errSecItemNotFound {
            ContextLog.error("Keychain delete failed (OSStatus \(status))", "auth")
        }
    }

    // MARK: - Query construction

    private static func baseQuery() -> [String: Any] {
        [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account,
        ]
    }

    private static func applySilentAuth(_ query: inout [String: Any]) {
        let context = LAContext()
        context.interactionNotAllowed = true
        query[kSecUseAuthenticationContext as String] = context
    }
}
