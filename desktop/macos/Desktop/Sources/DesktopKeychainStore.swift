import Foundation
import LocalAuthentication
import Security

/// File-based (login) keychain helpers for desktop secrets.
///
/// Design constraints (see #9167 / keychain ACL prompt fix):
/// - Never opt into the data-protection keychain (`kSecUseDataProtectionKeychain`) — this
///   non-sandboxed Developer ID app has no `keychain-access-groups` entitlement.
/// - Never present the macOS keychain password dialog. Reads/writes that would require UI
///   fail closed (`nil` / `false`).
/// - Scope service names by signing Team ID **and** bundle id so:
///   - Apple Development / named-bundle builds cannot poison notarized Beta/Prod
///   - Local contributors' Omi Dev / `omi-*` / ad-hoc rebuilds cannot poison each other
///     (path/signature ACL mismatches between same-team apps)
/// - Do **not** query the pre-scoping legacy service names from app code. Those items may
///   carry a foreign-team ACL; even with `LAContext.interactionNotAllowed`, SecItem can
///   still surface the login-keychain password sheet (`errSecUserCanceled` / -128). Leave
///   orphans alone — UserDefaults migration covers auth continuity for older installs.
enum DesktopKeychainStore {
  /// Pre-scoping service names. Kept as constants for dump/seed scripts and docs only —
  /// app runtime must not SecItem-query these (see file header).
  static let legacyAuthTokenService = "com.omi.desktop.firebase-rest-session"
  static let legacyLocalAgentTokenService = "com.omi.desktop.local-agent-api"
  static let legacyClientDeviceService = "com.omi.client-device-id"

  /// Signing Team ID of the running binary (e.g. `9536L8KLMP` for Developer ID,
  /// `JVMXE5G542` for a personal Apple Development cert). Falls back to an ad-hoc
  /// bundle-scoped token when codesign info has no Team ID.
  static var signingTeamID: String {
    if let cached = _cachedSigningTeamID {
      return cached
    }
    let resolved = resolveSigningTeamID()
    _cachedSigningTeamID = resolved
    return resolved
  }

  private static var _cachedSigningTeamID: String?

  /// Team + bundle scoped service name.
  ///
  /// Format: `<base>.v2.team.<TeamID>.bundle.<bundleID>`
  ///
  /// Beta and stable share `com.omi.computer-macos` + Developer ID team, so they keep one
  /// auth item. Every local contributor bundle (`com.omi.desktop-dev`, `com.omi.omi-*`,
  /// ad-hoc) gets its own item — dump/seed scripts write into the *target* bundle's
  /// scoped service explicitly.
  static func scopedService(
    _ base: String,
    teamID: String = signingTeamID,
    bundleID: String = Bundle.main.bundleIdentifier ?? "unknown.bundle"
  ) -> String {
    "\(base).v2.team.\(teamID).bundle.\(bundleID)"
  }

  private static func baseQuery(service: String, account: String) -> [String: Any] {
    // Use the file-based (login) keychain, NOT the iOS-style data-protection keychain.
    // Opting into the data-protection keychain requires a `keychain-access-groups` entitlement
    // this non-sandboxed Developer ID app does not have (see Omi-Release.entitlements:
    // app-sandbox=false, no keychain-access-groups). On the signed/notarized build that made
    // every SecItem write fail with errSecMissingEntitlement (-34018), so token storage failed
    // ("Could not securely store sign-in tokens") and sign-in was blocked. The default
    // file-based keychain works for a signed non-sandboxed app with no extra entitlement and
    // still keeps tokens out of UserDefaults.
    [
      kSecClass as String: kSecClassGenericPassword,
      kSecAttrService as String: service,
      kSecAttrAccount as String: account,
    ]
  }

  /// Attach silent-auth constraints so SecItem prefers failing over showing UI.
  /// Note: this does **not** reliably suppress file-based keychain ACL password sheets for
  /// foreign TrustedApplication items — callers must not query those legacy services.
  private static func applySilentAuth(_ query: inout [String: Any]) {
    let context = LAContext()
    context.interactionNotAllowed = true
    query[kSecUseAuthenticationContext as String] = context
  }

  private static func isMissing(_ status: OSStatus) -> Bool {
    status == errSecItemNotFound
  }

  /// Statuses that mean "cannot access without UI / wrong ACL / user would be prompted".
  private static func isAuthUnavailable(_ status: OSStatus) -> Bool {
    status == errSecInteractionNotAllowed
      || status == errSecAuthFailed
      || status == errSecUserCanceled
      || status == errSecMissingEntitlement
  }

  enum ReadResult: Equatable {
    case found(String)
    case missing
    case unavailable(OSStatus)
  }

  static func readString(service: String, account: String) -> ReadResult {
    var query = baseQuery(service: service, account: account)
    query[kSecReturnData as String] = true
    query[kSecMatchLimit as String] = kSecMatchLimitOne
    applySilentAuth(&query)

    var item: CFTypeRef?
    let status = SecItemCopyMatching(query as CFDictionary, &item)
    if status == errSecSuccess {
      guard let data = item as? Data, let value = String(data: data, encoding: .utf8), !value.isEmpty else {
        return .missing
      }
      return .found(value)
    }
    if isMissing(status) {
      return .missing
    }
    if isAuthUnavailable(status) {
      log("DesktopKeychainStore: silent read unavailable for \(service)/\(account) (status \(status))")
      return .unavailable(status)
    }
    log("DesktopKeychainStore: read failed for \(service)/\(account) (status \(status))")
    return .unavailable(status)
  }

  static func string(service: String, account: String) -> String? {
    if case .found(let value) = readString(service: service, account: account) {
      return value
    }
    return nil
  }

  @discardableResult
  static func setString(_ value: String, service: String, account: String) -> Bool {
    let data = Data(value.utf8)
    var query = baseQuery(service: service, account: account)
    applySilentAuth(&query)
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
    if !isMissing(updateStatus) {
      if isAuthUnavailable(updateStatus) {
        // Existing item is unreadable/unwritable under silent auth. Do not prompt; try a
        // fresh add after a silent delete. If delete also fails, fail closed.
        delete(service: service, account: account)
      } else {
        log("DesktopKeychainStore: update failed for \(service)/\(account) (status \(updateStatus))")
        return false
      }
    }

    var addQuery = baseQuery(service: service, account: account)
    applySilentAuth(&addQuery)
    addQuery[kSecValueData as String] = data
    addQuery[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
    let addStatus = SecItemAdd(addQuery as CFDictionary, nil)
    if addStatus == errSecSuccess {
      return true
    }
    if addStatus == errSecDuplicateItem {
      let retry = SecItemUpdate(query as CFDictionary, attributes as CFDictionary)
      if retry == errSecSuccess {
        return true
      }
      log("DesktopKeychainStore: add/update race failed for \(service)/\(account) (status \(retry))")
      return false
    }
    log("DesktopKeychainStore: add failed for \(service)/\(account) (status \(addStatus))")
    return false
  }

  static func delete(service: String, account: String) {
    var query = baseQuery(service: service, account: account)
    applySilentAuth(&query)
    let status = SecItemDelete(query as CFDictionary)
    if status != errSecSuccess && !isMissing(status) {
      // Wrong-team / ACL-blocked deletes must stay silent — never escalate to a prompt.
      log("DesktopKeychainStore: delete failed for \(service)/\(account) (status \(status))")
    }
  }

  private static func resolveSigningTeamID() -> String {
    var code: SecCode?
    var status = SecCodeCopySelf([], &code)
    guard status == errSecSuccess, let code else {
      log("DesktopKeychainStore: SecCodeCopySelf failed (\(status)); using unknown team scope")
      return "unknown"
    }

    var staticCode: SecStaticCode?
    status = SecCodeCopyStaticCode(code, [], &staticCode)
    guard status == errSecSuccess, let staticCode else {
      log("DesktopKeychainStore: SecCodeCopyStaticCode failed (\(status)); using unknown team scope")
      return "unknown"
    }

    var info: CFDictionary?
    status = SecCodeCopySigningInformation(staticCode, SecCSFlags(rawValue: kSecCSSigningInformation), &info)
    guard status == errSecSuccess, let info = info as? [String: Any] else {
      log("DesktopKeychainStore: SecCodeCopySigningInformation failed (\(status)); using unknown team scope")
      return "unknown"
    }

    if let team = info[kSecCodeInfoTeamIdentifier as String] as? String, !team.isEmpty {
      return team
    }
    // Ad-hoc / unsigned local builds have no Team ID. Scope by bundle id so they still
    // cannot collide with Developer ID / Apple Development items.
    if let bundleID = Bundle.main.bundleIdentifier, !bundleID.isEmpty {
      return "adhoc.\(bundleID)"
    }
    return "unknown"
  }
}
