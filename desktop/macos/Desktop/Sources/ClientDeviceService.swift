import CryptoKit
import Foundation
import Security

/// Stable per-installation device identity for capture provenance (mirrors Flutter `deviceIdHash`).
final class ClientDeviceService {
  static let shared = ClientDeviceService()

  private let keychainService = "com.omi.client-device-id"
  private let keychainAccount = "install-uuid"
  private let devInstallIdDefaultsKey = "dev-client-device-install-uuid"
  private let bundleIdentifier: String?
  private let userDefaults: UserDefaults

  init(
    bundleIdentifier: String? = Bundle.main.bundleIdentifier,
    userDefaults: UserDefaults = .standard
  ) {
    self.bundleIdentifier = bundleIdentifier
    self.userDefaults = userDefaults
  }

  var deviceIdHash: String {
    let installId = loadOrCreateInstallId()
    let digest = SHA256.hash(data: Data(installId.utf8))
    return digest.map { String(format: "%02x", $0) }.joined().prefix(8).description
  }

  /// Contract: `{platform}_{hash}` — same shape as backend FCM `device_key`.
  var clientDeviceId: String {
    "macos_\(deviceIdHash)"
  }

  func deviceProvenanceLabel(for memory: ServerMemory) -> String? {
    let localId = clientDeviceId
    if memory.primaryCaptureDevice == localId {
      return "This Mac"
    }
    if let device = memory.primaryCaptureDevice, !device.isEmpty {
      let platform = device.split(separator: "_").first.map(String.init) ?? device
      switch platform {
      case "macos": return "Mac"
      case "ios": return "iPhone"
      case "android": return "Android"
      default: return platform.capitalized
      }
    }
    return nil
  }

  func memoryMatchesThisDevice(_ memory: ServerMemory) -> Bool {
    let localId = clientDeviceId
    if memory.primaryCaptureDevice == localId {
      return true
    }
    return memory.captureDeviceIds.contains(localId)
  }

  private func loadOrCreateInstallId() -> String {
    if usesBundleScopedDevInstallId {
      return loadOrCreateDevInstallId()
    }
    if let existing = readKeychainInstallId() {
      return existing
    }
    let fresh = UUID().uuidString
    saveKeychainInstallId(fresh)
    return fresh
  }

  private var usesBundleScopedDevInstallId: Bool {
    guard let bundleIdentifier else { return false }
    // Throwaway named dev bundles should not prompt for the shared login-keychain item.
    return bundleIdentifier.hasPrefix("com.omi.omi-")
  }

  private func loadOrCreateDevInstallId() -> String {
    if let existing = userDefaults.string(forKey: devInstallIdDefaultsKey), !existing.isEmpty {
      return existing
    }
    let fresh = UUID().uuidString
    userDefaults.set(fresh, forKey: devInstallIdDefaultsKey)
    return fresh
  }

  private func readKeychainInstallId() -> String? {
    let query: [String: Any] = [
      kSecClass as String: kSecClassGenericPassword,
      kSecAttrService as String: keychainService,
      kSecAttrAccount as String: keychainAccount,
      kSecReturnData as String: true,
      kSecMatchLimit as String: kSecMatchLimitOne,
    ]
    var item: CFTypeRef?
    let status = SecItemCopyMatching(query as CFDictionary, &item)
    guard status == errSecSuccess, let data = item as? Data, let value = String(data: data, encoding: .utf8) else {
      return nil
    }
    return value
  }

  private func saveKeychainInstallId(_ value: String) {
    let data = Data(value.utf8)
    let query: [String: Any] = [
      kSecClass as String: kSecClassGenericPassword,
      kSecAttrService as String: keychainService,
      kSecAttrAccount as String: keychainAccount,
      kSecValueData as String: data,
      kSecAttrAccessible as String: kSecAttrAccessibleAfterFirstUnlock,
    ]
    SecItemDelete(query as CFDictionary)
    SecItemAdd(query as CFDictionary, nil)
  }
}
