import Foundation
import Security

/// Small secrets the user typed (custom STT API keys). Kept out of `UserDefaults` and never logged.
public protocol SecretStore: Sendable {
    func secret(_ name: String) -> String?
    /// `nil` or empty removes it.
    func setSecret(_ value: String?, for name: String)
}

/// The Keychain: generic passwords under the app's service, readable after the first unlock
/// (background capture runs with the phone locked), never synced to iCloud.
public struct KeychainSecretStore: SecretStore {
    private let service: String

    public init(service: String = (Bundle.main.bundleIdentifier ?? "omi") + ".secrets") {
        self.service = service
    }

    public func secret(_ name: String) -> String? {
        var query = baseQuery(name)
        query[kSecReturnData as String] = true
        query[kSecMatchLimit as String] = kSecMatchLimitOne
        var item: CFTypeRef?
        guard SecItemCopyMatching(query as CFDictionary, &item) == errSecSuccess, let data = item as? Data else { return nil }
        return String(data: data, encoding: .utf8)
    }

    public func setSecret(_ value: String?, for name: String) {
        SecItemDelete(baseQuery(name) as CFDictionary)
        guard let value, !value.isEmpty else { return }
        var query = baseQuery(name)
        query[kSecValueData as String] = Data(value.utf8)
        query[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
        SecItemAdd(query as CFDictionary, nil)
    }

    private func baseQuery(_ name: String) -> [String: Any] {
        [kSecClass as String: kSecClassGenericPassword, kSecAttrService as String: service, kSecAttrAccount as String: name]
    }
}
