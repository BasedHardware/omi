import CryptoKit
import Foundation

/// ChatGPT / Codex subscription auth via local `~/.codex/auth.json` (same cache as Codex CLI).
/// Tokens never leave this Mac except through the loopback Codex proxy to OpenAI.
enum CodexAuthService {
  private static let enrolledKey = "codex_auth_enrolled"
  private static let preferredModelKey = "codex_preferred_model"
  private static let defaultModel = "gpt-5.4"

  struct AuthSnapshot: Equatable {
    let accessToken: String
    let accountId: String
    let refreshToken: String?
    let authFilePath: URL
  }

  /// User opted in via Settings (distinct from merely having auth.json from Codex CLI).
  static var isEnrolled: Bool {
    UserDefaults.standard.bool(forKey: enrolledKey)
  }

  static var preferredModel: String {
    let stored = UserDefaults.standard.string(forKey: preferredModelKey)?
      .trimmingCharacters(in: .whitespacesAndNewlines)
    if let stored, !stored.isEmpty { return stored }
    return defaultModel
  }

  static func setPreferredModel(_ model: String) {
    UserDefaults.standard.set(model, forKey: preferredModelKey)
  }

  /// SHA-256 fingerprint of account_id for backend enrollment (never stores tokens server-side).
  static func enrollmentFingerprint(for accountId: String) -> String {
    let digest = SHA256.hash(data: Data(accountId.utf8))
    return digest.map { String(format: "%02x", $0) }.joined()
  }

  static func resolveAuthFilePath() -> URL {
    if let codexHome = ProcessInfo.processInfo.environment["CODEX_HOME"],
      !codexHome.isEmpty
    {
      return URL(fileURLWithPath: codexHome).appendingPathComponent("auth.json")
    }
    return FileManager.default.homeDirectoryForCurrentUser
      .appendingPathComponent(".codex/auth.json")
  }

  static func loadSnapshot() -> AuthSnapshot? {
    let url = resolveAuthFilePath()
    guard let data = try? Data(contentsOf: url),
      let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
      let fields = parseAuthFields(from: json)
    else {
      return nil
    }
    return AuthSnapshot(
      accessToken: fields.accessToken,
      accountId: fields.accountId,
      refreshToken: fields.refreshToken,
      authFilePath: url
    )
  }

  /// Codex CLI stores tokens at the top level (legacy) or under `tokens` (current format).
  private static func parseAuthFields(from json: [String: Any]) -> (
    accessToken: String, accountId: String, refreshToken: String?
  )? {
    if let parsed = parseAuthFields(fromTokenContainer: json) {
      return parsed
    }
    if let tokens = json["tokens"] as? [String: Any] {
      return parseAuthFields(fromTokenContainer: tokens)
    }
    return nil
  }

  private static func parseAuthFields(fromTokenContainer json: [String: Any]) -> (
    accessToken: String, accountId: String, refreshToken: String?
  )? {
    guard let accessToken = json["access_token"] as? String,
      !accessToken.isEmpty,
      let accountId = json["account_id"] as? String,
      !accountId.isEmpty
    else {
      return nil
    }
    let refresh = (json["refresh_token"] as? String).flatMap { $0.isEmpty ? nil : $0 }
    return (accessToken, accountId, refresh)
  }

  /// True when enrolled and a valid auth file is present.
  static var isActive: Bool {
    isEnrolled && loadSnapshot() != nil
  }

  static func markEnrolled() {
    UserDefaults.standard.set(true, forKey: enrolledKey)
  }

  static func clearEnrollment() {
    UserDefaults.standard.set(false, forKey: enrolledKey)
  }

  static func enrollmentFingerprintIfActive() -> String? {
    guard let snap = loadSnapshot(), isEnrolled else { return nil }
    return enrollmentFingerprint(for: snap.accountId)
  }
}
