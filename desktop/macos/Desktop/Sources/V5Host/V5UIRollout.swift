import Foundation

enum V5UIRollout {
  static var localOverrideEnabled: Bool {
    localOverrideEnabled(in: .standard)
  }

  static func localOverrideEnabled(in defaults: UserDefaults) -> Bool {
    #if DEBUG
      defaults.bool(forKey: .v5UILocalOverride)
    #else
      false
    #endif
  }
}
