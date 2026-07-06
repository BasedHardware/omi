import Foundation
import Security

enum DesktopKeychainStore {
  private static func baseQuery(service: String, account: String) -> [String: Any] {
    // Use the file-based (login) keychain, NOT the iOS-style data-protection keychain.
    // Opting into the data-protection keychain requires a `keychain-access-groups` entitlement
    // this non-sandboxed Developer ID app does not have (see Omi-Release.entitlements:
    // app-sandbox=false, no keychain-access-groups). On the signed/notarized build that made
    // every SecItem write fail with errSecMissingEntitlement (-34018), so token storage failed
    // ("Could not securely store sign-in tokens") and sign-in was blocked. The default
    // file-based keychain works for a signed non-sandboxed app with no extra entitlement and
    // still keeps tokens out of UserDefaults. (Dev builds don't hit this — they use
    // UserDefaults, so it only ever failed on prod/beta.)
    [
      kSecClass as String: kSecClassGenericPassword,
      kSecAttrService as String: service,
      kSecAttrAccount as String: account,
    ]
  }

  static func string(service: String, account: String) -> String? {
    var query = baseQuery(service: service, account: account)
    query[kSecReturnData as String] = true
    query[kSecMatchLimit as String] = kSecMatchLimitOne

    var item: CFTypeRef?
    let status = SecItemCopyMatching(query as CFDictionary, &item)
    guard status == errSecSuccess else {
      if status != errSecItemNotFound {
        log("DesktopKeychainStore: read failed for \(service)/\(account) (status \(status))")
      }
      return nil
    }

    guard let data = item as? Data, let value = String(data: data, encoding: .utf8), !value.isEmpty else {
      return nil
    }
    return value
  }

  @discardableResult
  static func setString(_ value: String, service: String, account: String) -> Bool {
    let data = Data(value.utf8)
    let query = baseQuery(service: service, account: account)
    let attributes: [String: Any] = [
      kSecValueData as String: data,
      // Advisory on the file-based keychain (it's a data-protection-keychain attribute, so it's
      // accepted but not cryptographically enforced here); kept for intent + parity with iOS.
      kSecAttrAccessible as String: kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly,
    ]

    let updateStatus = SecItemUpdate(query as CFDictionary, attributes as CFDictionary)
    if updateStatus == errSecSuccess {
      return true
    }
    guard updateStatus == errSecItemNotFound else {
      log("DesktopKeychainStore: update failed for \(service)/\(account) (status \(updateStatus))")
      return false
    }

    var addQuery = query
    addQuery[kSecValueData as String] = data
    addQuery[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
    let addStatus = SecItemAdd(addQuery as CFDictionary, nil)
    if addStatus != errSecSuccess {
      log("DesktopKeychainStore: add failed for \(service)/\(account) (status \(addStatus))")
      return false
    }
    return true
  }

  static func delete(service: String, account: String) {
    let query = baseQuery(service: service, account: account)
    let status = SecItemDelete(query as CFDictionary)
    if status != errSecSuccess && status != errSecItemNotFound {
      log("DesktopKeychainStore: delete failed for \(service)/\(account) (status \(status))")
    }
  }
}
