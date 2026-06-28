import Foundation

/// Cortex open-core licensing (Swift port). Cortex is free and open source; a Pro
/// tier (one-time 14-day trial) unlocks cloud sync, higher automation limits and
/// priority model routing. Persisted in UserDefaults.

enum CortexTier: String { case free, trial, pro }

struct CortexProFeature: Identifiable {
  let id: String
  let label: String
  let description: String
}

enum CortexLicense {
  static let trialDuration: TimeInterval = 14 * 24 * 60 * 60

  static let proFeatures: [CortexProFeature] = [
    CortexProFeature(
      id: "cloud-sync", label: "Cloud sync",
      description: "Encrypted sync of your conversations, memories and settings across devices."),
    CortexProFeature(
      id: "priority-models", label: "Priority models",
      description: "Pin premium cloud models and get priority routing."),
    CortexProFeature(
      id: "team", label: "Team workspaces",
      description: "Shared memories and goals for your team (coming soon)."),
  ]

  private static let proKeyRegex = try! NSRegularExpression(
    pattern: "^CORTEX-PRO-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}$")

  private static let proKeyDefaultsKey = "cortexProKey"
  private static let trialStartedAtKey = "cortexTrialStartedAt"

  static func isValidProKey(_ key: String?) -> Bool {
    guard let key = key?.trimmingCharacters(in: .whitespacesAndNewlines).uppercased(), !key.isEmpty else {
      return false
    }
    let range = NSRange(key.startIndex..<key.endIndex, in: key)
    return proKeyRegex.firstMatch(in: key, range: range) != nil
  }

  private static var proKey: String? { UserDefaults.standard.string(forKey: proKeyDefaultsKey) }

  private static var trialStartedAt: Date? {
    let t = UserDefaults.standard.double(forKey: trialStartedAtKey)
    return t == 0 ? nil : Date(timeIntervalSince1970: t)
  }

  static var trialEndsAt: Date? { trialStartedAt.map { $0.addingTimeInterval(trialDuration) } }

  static func isTrialActive(now: Date = Date()) -> Bool {
    guard let ends = trialEndsAt else { return false }
    return now < ends
  }

  static func trialDaysRemaining(now: Date = Date()) -> Int {
    guard let ends = trialEndsAt else { return 0 }
    let secs = ends.timeIntervalSince(now)
    return secs <= 0 ? 0 : Int(ceil(secs / (24 * 60 * 60)))
  }

  static var tier: CortexTier {
    if isValidProKey(proKey) { return .pro }
    if isTrialActive() { return .trial }
    return .free
  }

  static var isProActive: Bool { tier == .pro || tier == .trial }

  static func hasFeature(_ id: String) -> Bool { isProActive }

  static var canStartTrial: Bool { trialStartedAt == nil && !isValidProKey(proKey) }

  @discardableResult
  static func startTrial() -> Bool {
    guard canStartTrial else { return false }
    UserDefaults.standard.set(Date().timeIntervalSince1970, forKey: trialStartedAtKey)
    return true
  }

  @discardableResult
  static func redeemProKey(_ key: String) -> Bool {
    guard isValidProKey(key) else { return false }
    UserDefaults.standard.set(key.trimmingCharacters(in: .whitespacesAndNewlines).uppercased(), forKey: proKeyDefaultsKey)
    return true
  }

  static func clear() {
    UserDefaults.standard.removeObject(forKey: proKeyDefaultsKey)
    UserDefaults.standard.removeObject(forKey: trialStartedAtKey)
  }
}
