import Foundation

/// A local preference. Explicit Shortcuts remain available when indexing is off.
enum SiriIntegrationSettings {
  static let key = "siriAppleIntelligenceEnabled"

  static var isEnabled: Bool {
    get { UserDefaults.standard.object(forKey: key) as? Bool ?? true }
    set {
      UserDefaults.standard.set(newValue, forKey: key)
      NotificationCenter.default.post(name: .siriIndexPreferenceChanged, object: nil)
    }
  }
}

extension Notification.Name {
  static let siriIndexPreferenceChanged = Notification.Name("siriIndexPreferenceChanged")
}
