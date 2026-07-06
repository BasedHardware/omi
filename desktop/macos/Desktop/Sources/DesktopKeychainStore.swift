import Foundation
import Security

enum DesktopKeychainStore {
  static func string(service: String, account: String) -> String? {
    let query: [String: Any] = [
      kSecClass as String: kSecClassGenericPassword,
      kSecAttrService as String: service,
      kSecAttrAccount as String: account,
      kSecReturnData as String: true,
      kSecMatchLimit as String: kSecMatchLimitOne,
    ]

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
    let query: [String: Any] = [
      kSecClass as String: kSecClassGenericPassword,
      kSecAttrService as String: service,
      kSecAttrAccount as String: account,
    ]
    let attributes: [String: Any] = [
      kSecValueData as String: data,
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
    let query: [String: Any] = [
      kSecClass as String: kSecClassGenericPassword,
      kSecAttrService as String: service,
      kSecAttrAccount as String: account,
    ]
    let status = SecItemDelete(query as CFDictionary)
    if status != errSecSuccess && status != errSecItemNotFound {
      log("DesktopKeychainStore: delete failed for \(service)/\(account) (status \(status))")
    }
  }
}
