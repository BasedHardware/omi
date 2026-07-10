import CryptoKit
import Foundation
import LocalAuthentication
import Security

enum ClientDeviceKeychainReadResult {
  case found(String)
  case missing
  case unavailable(OSStatus)
}

/// Stable per-installation device identity for capture provenance (mirrors Flutter `deviceIdHash`).
final class ClientDeviceService {
  static let shared = ClientDeviceService()

  private let keychainAccount = "install-uuid"
  private let devInstallIdDefaultsKey = "dev-client-device-install-uuid"
  private let installIdMirrorDefaultsKey = "client-device-install-uuid-mirror"
  private let bundleIdentifier: String?
  private let userDefaults: UserDefaults
  private let keychainReader: (() -> ClientDeviceKeychainReadResult)?
  private let keychainWriter: ((String) -> Void)?
  private let cacheLock = NSLock()
  private var cachedInstallId: String?

  /// Team+bundle scoped service for this process. Never the shared legacy
  /// `com.omi.client-device-id` name — querying that from a binary not on its ACL
  /// is what caused keychain password prompt spam (#8799).
  private var keychainService: String {
    DesktopKeychainStore.scopedService(
      DesktopKeychainStore.legacyClientDeviceService,
      bundleID: bundleIdentifier ?? Bundle.main.bundleIdentifier ?? "unknown.bundle"
    )
  }

  init(
    bundleIdentifier: String? = Bundle.main.bundleIdentifier,
    userDefaults: UserDefaults = .standard,
    keychainReader: (() -> ClientDeviceKeychainReadResult)? = nil,
    keychainWriter: ((String) -> Void)? = nil
  ) {
    self.bundleIdentifier = bundleIdentifier
    self.userDefaults = userDefaults
    self.keychainReader = keychainReader
    self.keychainWriter = keychainWriter
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
    // All non-production bundles (Omi Dev + named omi-*) stay out of Keychain
    // entirely — UserDefaults is enough for throwaway local identity and never
    // prompts. Production Beta/Prod use the team+bundle scoped Keychain item.
    if usesUserDefaultsInstallId {
      return loadOrCreateDevInstallId()
    }
    switch keychainReader?() ?? readKeychainInstallId() {
    case .found(let existing):
      userDefaults.set(existing, forKey: installIdMirrorDefaultsKey)
      return existing
    case .missing:
      // v0.12.64 moved production builds to a team+bundle scoped Keychain
      // service. Existing installs have their prior stable value in this
      // mirror, so migrate it instead of changing the provenance identity.
      if let mirror = userDefaults.string(forKey: installIdMirrorDefaultsKey), !mirror.isEmpty {
        saveKeychainInstallId(mirror)
        return mirror
      }
      let fresh = UUID().uuidString
      saveKeychainInstallId(fresh)
      userDefaults.set(fresh, forKey: installIdMirrorDefaultsKey)
      return fresh
    case .unavailable(let status):
      // Denied prompt or transient keychain failure. Never rotate the item here —
      // and never fall through to the legacy unscoped service (that prompts).
      log("ClientDeviceService: keychain read unavailable (status \(status)); using mirror fallback")
      if let mirror = userDefaults.string(forKey: installIdMirrorDefaultsKey), !mirror.isEmpty {
        return mirror
      }
      let fallback = UUID().uuidString
      userDefaults.set(fallback, forKey: installIdMirrorDefaultsKey)
      return fallback
    }
  }

  private var usesUserDefaultsInstallId: Bool {
    guard let bundleIdentifier else { return false }
    // Any non-production com.omi.* bundle (desktop-dev + omi-*) — avoid Keychain.
    return bundleIdentifier.hasPrefix("com.omi.")
      && bundleIdentifier != AppBuild.productionBundleIdentifier
  }

  private func loadOrCreateDevInstallId() -> String {
    if let existing = userDefaults.string(forKey: devInstallIdDefaultsKey), !existing.isEmpty {
      return existing
    }
    let fresh = UUID().uuidString
    userDefaults.set(fresh, forKey: devInstallIdDefaultsKey)
    return fresh
  }

  private func readKeychainInstallId() -> ClientDeviceKeychainReadResult {
    let context = LAContext()
    context.interactionNotAllowed = true
    let query: [String: Any] = [
      kSecClass as String: kSecClassGenericPassword,
      kSecAttrService as String: keychainService,
      kSecAttrAccount as String: keychainAccount,
      kSecReturnData as String: true,
      kSecMatchLimit as String: kSecMatchLimitOne,
      kSecUseAuthenticationContext as String: context,
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
    if let keychainWriter {
      keychainWriter(value)
      return
    }
    let data = Data(value.utf8)
    let context = LAContext()
    context.interactionNotAllowed = true
    let query: [String: Any] = [
      kSecClass as String: kSecClassGenericPassword,
      kSecAttrService as String: keychainService,
      kSecAttrAccount as String: keychainAccount,
      kSecUseAuthenticationContext as String: context,
    ]
    let attributes: [String: Any] = [
      kSecValueData as String: data,
      kSecAttrAccessible as String: kSecAttrAccessibleAfterFirstUnlock,
    ]
    let updateStatus = SecItemUpdate(query as CFDictionary, attributes as CFDictionary)
    if updateStatus == errSecSuccess {
      return
    }
    if updateStatus != errSecItemNotFound {
      // Do not SecItemDelete+Add on auth failure — that can prompt. Fail closed;
      // the mirror fallback in loadOrCreateInstallId covers continuity.
      log("ClientDeviceService: keychain update unavailable (status \(updateStatus))")
      return
    }
    var addQuery = query
    addQuery[kSecValueData as String] = data
    addQuery[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlock
    let addStatus = SecItemAdd(addQuery as CFDictionary, nil)
    if addStatus != errSecSuccess {
      log("ClientDeviceService: keychain add unavailable (status \(addStatus))")
    }
  }
}
