import Foundation

/// A live Google OAuth grant. The only record that ever holds tokens, and it
/// is only ever written to the keychain.
struct GoogleOAuthConnection: Codable, Equatable {
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
  static let clientIdKey = "googleOauthClientId"
  static let clientSecretKey = "googleOauthClientSecret"

  static var clientId: String? {
    get { UserDefaults.standard.string(forKey: clientIdKey) }
    set { UserDefaults.standard.set(newValue, forKey: clientIdKey) }
  }

  static var clientSecret: String? {
    get {
      let value = UserDefaults.standard.string(forKey: clientSecretKey)
      return (value?.isEmpty ?? true) ? nil : value
    }
    set { UserDefaults.standard.set(newValue, forKey: clientSecretKey) }
  }
}

/// Where grants live: one UID-scoped JSON blob in the login keychain via
/// [DesktopKeychainStore], never UserDefaults, never plain files.
final class GoogleOAuthStore: GoogleOAuthStoring, @unchecked Sendable {
  static let shared = GoogleOAuthStore()
  static let service = "com.omi.desktop.google-oauth"
  static let account = "connections"

  func readAll() -> [GoogleOAuthConnection] {
    guard
      case .found(let raw) = DesktopKeychainStore.readString(
        service: Self.service, account: Self.account),
      let data = raw.data(using: .utf8),
      let decoded = try? JSONDecoder().decode(
        [GoogleOAuthConnection].self, from: data)
    else {
      return []
    }
    return decoded
  }

  func write(_ connections: [GoogleOAuthConnection]) {
    guard
      let data = try? JSONEncoder().encode(connections),
      let raw = String(data: data, encoding: .utf8)
    else {
      log("GoogleOAuthStore: failed to encode connections")
      return
    }
    DesktopKeychainStore.setString(
      raw, service: Self.service, account: Self.account)
  }

  func deleteAll() {
    DesktopKeychainStore.delete(service: Self.service, account: Self.account)
  }
}

protocol GoogleOAuthStoring {
  func readAll() -> [GoogleOAuthConnection]
  func write(_ connections: [GoogleOAuthConnection])
}
