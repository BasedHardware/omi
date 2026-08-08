import Foundation

/// A live Google OAuth grant. The only record that ever holds tokens, and it
/// is only ever written to the keychain.
struct GoogleOAuthConnection: Codable, Equatable, Sendable {
  let accessToken: String
  let expiresAt: Date
  let grantedScopes: [String]
  let refreshToken: String?
  let account: String?
  var needsReconnect: Bool

  var isExpired: Bool { Date() >= expiresAt }

  init(
    accessToken: String,
    expiresAt: Date,
    grantedScopes: [String],
    refreshToken: String?,
    account: String?,
    needsReconnect: Bool = false
  ) {
    self.accessToken = accessToken
    self.expiresAt = expiresAt
    self.grantedScopes = grantedScopes
    self.refreshToken = refreshToken
    self.account = account
    self.needsReconnect = needsReconnect
  }
}

/// Google OAuth constants. Scopes are the narrowest that read the two sources
/// Omi imports; nothing writes to either service.
enum GoogleOAuth {
  static let connectorId = "google"
  static let displayName = "Google"
  static let authorizationEndpoint = URL(
    string: "https://accounts.google.com/o/oauth2/v2/auth")!
  static let tokenEndpoint = URL(string: "https://oauth2.googleapis.com/token")!
  static let revocationEndpoint = URL(
    string: "https://oauth2.googleapis.com/revoke")!
  static let userInfoEndpoint = URL(
    string: "https://openidconnect.googleapis.com/v1/userinfo")!
  static let scopes = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/calendar.readonly",
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
  ]
  static let clientIdKey = DefaultsKey.googleOauthClientId.rawValue
  static let clientSecretKey = DefaultsKey.googleOauthClientSecret.rawValue
  static let clientSecretService = DesktopKeychainStore.scopedService("com.omi.desktop.google-oauth-client")
  static let clientSecretAccount = "client-secret"

  static var clientId: String? {
    get { UserDefaults.standard.string(forKey: clientIdKey) }
    set { UserDefaults.standard.set(newValue, forKey: clientIdKey) }
  }

  static var clientSecret: String? {
    get {
      if case .found(let value) = DesktopKeychainStore.readString(
        service: clientSecretService, account: clientSecretAccount)
      {
        return value
      }
      guard let legacy = UserDefaults.standard.string(forKey: .googleOauthClientSecret), !legacy.isEmpty else {
        return nil
      }
      guard
        DesktopKeychainStore.setString(
          legacy, service: clientSecretService, account: clientSecretAccount)
      else { return nil }
      UserDefaults.standard.removeObject(forKey: .googleOauthClientSecret)
      return legacy
    }
    set {
      if let newValue, !newValue.isEmpty {
        guard
          DesktopKeychainStore.setString(
            newValue, service: clientSecretService, account: clientSecretAccount)
        else { return }
      } else {
        DesktopKeychainStore.delete(service: clientSecretService, account: clientSecretAccount)
      }
      UserDefaults.standard.removeObject(forKey: .googleOauthClientSecret)
    }
  }
}

/// Where grants live: one UID-scoped JSON blob in the login keychain via
/// [DesktopKeychainStore], never UserDefaults, never plain files.
final class GoogleOAuthStore: GoogleOAuthStoring, @unchecked Sendable {
  static let shared = GoogleOAuthStore()
  // Team+bundle scoped so a dev/ad-hoc build cannot create an item the signed
  // app cannot silently access (and vice versa).
  static let service = DesktopKeychainStore.scopedService("com.omi.desktop.google-oauth")
  static func account(for ownerID: String?) -> String {
    "connections.\(ownerID ?? "signed-out")"
  }

  func readAll(for ownerID: String? = UserDefaults.standard.string(forKey: .authUserId)) throws
    -> [GoogleOAuthConnection]
  {
    switch DesktopKeychainStore.readString(service: Self.service, account: Self.account(for: ownerID)) {
    case .missing:
      return []
    case .unavailable(let status):
      throw GoogleOAuthStoreError.keychainUnavailable(status)
    case .found(let raw):
      guard let data = raw.data(using: .utf8) else {
        throw GoogleOAuthStoreError.invalidData
      }
      do {
        return try JSONDecoder().decode([GoogleOAuthConnection].self, from: data)
      } catch {
        throw GoogleOAuthStoreError.invalidData
      }
    }
  }

  func write(
    _ connections: [GoogleOAuthConnection],
    for ownerID: String? = UserDefaults.standard.string(forKey: .authUserId)
  ) -> Bool {
    guard
      let data = try? JSONEncoder().encode(connections),
      let raw = String(data: data, encoding: .utf8)
    else {
      log("GoogleOAuthStore: failed to encode connections")
      return false
    }
    guard
      DesktopKeychainStore.setString(
        raw, service: Self.service, account: Self.account(for: ownerID))
    else {
      log("GoogleOAuthStore: keychain write failed")
      return false
    }
    return true
  }

  func deleteAll(for ownerID: String? = UserDefaults.standard.string(forKey: .authUserId)) {
    DesktopKeychainStore.delete(service: Self.service, account: Self.account(for: ownerID))
  }
}

enum GoogleOAuthStoreError: Error {
  case keychainUnavailable(OSStatus)
  case invalidData
}

protocol GoogleOAuthStoring {
  func readAll(for ownerID: String?) throws -> [GoogleOAuthConnection]
  /// Persist the full connection list. Returns false when the keychain write
  /// fails so callers can surface the failure instead of reporting success
  /// for a grant that was never stored.
  func write(_ connections: [GoogleOAuthConnection], for ownerID: String?) -> Bool
}
