import Foundation
import Security

/// Keychain-backed storage for sensitive auth tokens (Firebase ID + refresh tokens).
///
/// Items are scoped to the current app bundle, marked
/// `kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly`, and are NOT included in a
/// keychain access group — so another app running as the same macOS user cannot
/// read them the way it can read the app's UserDefaults plist.
enum AuthKeychain {
    private static var service: String {
        (Bundle.main.bundleIdentifier ?? "com.omi.desktop") + ".auth"
    }

    static func set(_ value: String?, forKey key: String) {
        let baseQuery: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: key,
        ]
        SecItemDelete(baseQuery as CFDictionary)
        guard let value, let data = value.data(using: .utf8) else { return }
        var addQuery = baseQuery
        addQuery[kSecValueData as String] = data
        addQuery[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
        let status = SecItemAdd(addQuery as CFDictionary, nil)
        if status != errSecSuccess {
            NSLog("OMI AUTH: Keychain add failed for %@ (status=%d)", key, Int(status))
        }
    }

    static func get(_ key: String) -> String? {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: key,
            kSecReturnData as String: true,
            kSecMatchLimit as String: kSecMatchLimitOne,
        ]
        var out: AnyObject?
        let status = SecItemCopyMatching(query as CFDictionary, &out)
        guard status == errSecSuccess,
              let data = out as? Data,
              let value = String(data: data, encoding: .utf8)
        else {
            return nil
        }
        return value
    }

    static func clearAll() {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
        ]
        SecItemDelete(query as CFDictionary)
    }
}
