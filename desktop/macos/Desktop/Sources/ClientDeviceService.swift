import CryptoKit
import Foundation
import Security

/// Stable per-installation device identity for capture provenance (mirrors Flutter `deviceIdHash`).
final class ClientDeviceService {
  static let shared = ClientDeviceService()

  private let keychainService = "com.omi.client-device-id"
  private let keychainAccount = "install-uuid"
  private let devInstallIdDefaultsKey = "dev-client-device-install-uuid"
  private let installIdMirrorDefaultsKey = "client-device-install-uuid-mirror"
  private let bundleIdentifier: String?
  private let userDefaults: UserDefaults
  private let cacheLock = NSLock()
  private var cachedInstallId: String?

  init(
    bundleIdentifier: String? = Bundle.main.bundleIdentifier,
    userDefaults: UserDefaults = .standard
  ) {
    self.bundleIdentifier = bundleIdentifier
    self.userDefaults = userDefaults
  }

  var deviceIdHash: String {
    let installId = resolveInstallId()
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

  private func resolveInstallId() -> String {
    cacheLock.lock()
    defer { cacheLock.unlock() }
    if let cached = cachedInstallId {
      return cached
    }
    let resolved = loadOrCreateInstallId()
    cachedInstallId = resolved
    return resolved
  }

  private func loadOrCreateInstallId() -> String {
    if usesBundleScopedDevInstallId {
      return loadOrCreateDevInstallId()
    }
    switch readKeychainInstallId() {
    case .found(let existing):
      userDefaults.set(existing, forKey: installIdMirrorDefaultsKey)
      return existing
    case .missing:
      let fresh = UUID().uuidString
      saveKeychainInstallId(fresh)
      userDefaults.set(fresh, forKey: installIdMirrorDefaultsKey)
      return fresh
    case .unavailable(let status):
      // Denied prompt or transient keychain failure. Never rotate the shared
      // item here — that would change this Mac's identity for all Omi builds.
      log("ClientDeviceService: keychain read unavailable (status \(status)); using mirror fallback")
      if let mirror = userDefaults.string(forKey: installIdMirrorDefaultsKey), !mirror.isEmpty {
        return mirror
      }
      let fallback = UUID().uuidString
      userDefaults.set(fallback, forKey: installIdMirrorDefaultsKey)
      return fallback
    }
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

  private enum KeychainReadResult {
    case found(String)
    case missing
    case unavailable(OSStatus)
  }

  private func readKeychainInstallId() -> KeychainReadResult {
    let query: [String: Any] = [
      kSecClass as String: kSecClassGenericPassword,
      kSecAttrService as String: keychainService,
      kSecAttrAccount as String: keychainAccount,
      kSecReturnData as String: true,
      kSecMatchLimit as String: kSecMatchLimitOne,
    ]
    var item: CFTypeRef?
    let status = SecItemCopyMatching(query as CFDictionary, &item)
    switch status {
    case errSecSuccess:
      guard let data = item as? Data, let value = String(data: data, encoding: .utf8), !value.isEmpty else {
        return .missing
      }
      return .found(value)
    case errSecItemNotFound:
      return .missing
    default:
      // errSecAuthFailed / errSecUserCanceled / errSecInteractionNotAllowed etc.
      return .unavailable(status)
    }
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
